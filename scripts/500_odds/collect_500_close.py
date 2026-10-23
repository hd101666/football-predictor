# -*- coding: utf-8 -*-
"""500.com 收盘价（close）采集。

关键发现（实测 2026-10-21 已完赛比赛 ouzhi 页）：
  每家公司的第 1 张 pl_table_data 里有两个 tr：
    tr0 = 初盘  open   （1.67 / 3.30 / 4.60）
    tr1 = 收盘  close  （2.05 / 3.10 / 3.10）   ← 比赛结束后就是最终收盘价
  未开赛时 tr1 是"即时盘(live)"，比赛结束后自动固化为收盘价。

因此 close 不需要赛前抢抓，只要**赛后补抓**即可，数据更完整也更稳。

用法：
    python -X utf8 collect_500_close.py --db out/bok500.db --date 2026-10-21
    会遍历该日完场比赛，抓 ouzhi / yazhi / daxiao 三页的 tr0(open) 和 tr1(close)
"""
import argparse
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"D:\cl\qqsj_v2")
from scraper_500_results import list_finished  # noqa: E402
from scraper_500_ouzhi import resolve_name, load_cache, AVG_CIDS, KNOWN  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# 各页正常长度差异很大（实测）:
#   ouzhi  280~300 KB（30 家）
#   yazhi   60~70 KB（12 家）
#   daxiao  60~70 KB
# 阈值按最小页设，防止把正常小页当不完整页丢弃（此前的 120000 导致 AH/OU 全漏）
MIN_HTML = {1: 40_000}      # 通用下限
MIN_HTML_BY_MARKET = {"1X2": 150_000, "AH": 40_000, "OU": 40_000}

# 各页时间属性不一致（实测）:
#   ouzhi  用 data-time="2026-10-23 14:38:08"
#   yazhi  用 dt="2026-10-22 09:59:45"
#   两者都要兼容，否则 AH/OU 整页匹配 0 行
COMP = re.compile(
    r'<tr[^>]*class="tr[12]"[^>]*id="(\d+)"[^>]*(?:data-time|dt)="([^"]*)"[^>]*>(.*?)'
    r'(?=<tr[^>]*class="tr[12]"[^>]*id=|\Z)', re.S)

DDL = """
CREATE TABLE IF NOT EXISTS odds_close (
    fid          TEXT NOT NULL,
    market       TEXT NOT NULL,          -- 1X2 / AH / OU
    bookmaker    TEXT NOT NULL,
    cid          INTEGER,
    open_h       REAL, open_d REAL, open_a REAL,
    close_h      REAL, close_d REAL, close_a REAL,
    open_line    REAL, close_line REAL,
    book_update_utc TEXT,
    source       TEXT DEFAULT '500.com',
    collected_utc TEXT,
    PRIMARY KEY (fid, market, bookmaker)
);
"""


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def _nums(row):
    return re.findall(r">\s*(\d+\.\d{1,3})\s*<", row)


def _first_two_rows(block_html):
    """从一个 pl_table_data 表里取前两个 tr 的数值。返回 (tr0_vals, tr1_vals)"""
    trows = re.findall(r"<tr[^>]*>(.*?)</tr>", block_html, re.S)
    v0 = _nums(trows[0]) if len(trows) > 0 else []
    v1 = _nums(trows[1]) if len(trows) > 1 else []
    return v0, v1


def parse_close_page(fid, market, cache):
    """抓一页（ouzhi/yazhi/daxiao），返回 [{cid,bookmaker,open,close,line_open,line_close}]"""
    path = {"1X2": "ouzhi", "AH": "yazhi", "OU": "daxiao"}[market]
    html = fetch(f"https://odds.500.com/fenxi/{path}-{fid}.shtml")
    if len(html) < MIN_HTML_BY_MARKET.get(market, 40_000):
        return []
    out = []
    for cid_s, dtime, body in COMP.findall(html):
        cid = int(cid_s)
        if cid in AVG_CIDS:
            continue
        tm = re.search(r'title="([^"]*)"', body)
        masked = tm.group(1) if tm else ""
        blocks = re.findall(r'<table[^>]*class="pl_table_data"[^>]*>(.*?)</table>', body, re.S)
        if not blocks:
            continue
        v0, v1 = _first_two_rows(blocks[0])
        if market == "1X2":
            if len(v0) < 3 or len(v1) < 3:
                continue
            name = resolve_name(cid, cache)
            if "平均" in name:
                continue
            out.append({"cid": cid, "bookmaker": name,
                        "open": tuple(float(x) for x in v0[:3]),
                        "close": tuple(float(x) for x in v1[:3]),
                        "line_open": None, "line_close": None, "dtime": dtime})
        else:
            # 亚盘/大小球：结构是【2 个 pl_table_data 块，每块 1 个 tr】
            #   块0 = 初盘(open)，块1 = 收盘(close)
            # （此前错误地在同一个块里找两个 tr，导致 AH/OU 全部漏采）
            if len(blocks) < 2:
                continue

            def parse_one(block_html):
                # 实测结构（3 个 td，第 2 个含 ref）：
                #   <td width="58" row="1" class="ying">0.970↑</td>
                #   <td row="1" ref="-0.250">平手/半球<font>降</font></td>
                #   <td row="1" width="58" class="ping">0.820↓</td>
                # 注意第 3 个 td 后还有 <td width="40"><span class="tb_tdul_more">2<span></span></span></td>
                # 所以不能盲取 nums[1]，要按 td 顺序取前两个【水位】td
                ref = re.search(r'ref="(-?\d+\.\d+)"', block_html)
                if not ref:
                    return None
                # 按 td 切分（不递归，取每个 td 的首个数字）
                # 不取含盘口线的 td（class 含 tb_tdul_pan），只留水位 td
                tds = re.findall(r'(<td\b[^>]*>)(.*?)</td>', block_html, re.S)
                vals = []
                for tag, td in tds:
                    if "tb_tdul_pan" in tag:
                        continue                      # 盘口线，不是水位
                    if "tb_tdul_more" in td or "tb_tdul_more" in tag:
                        continue                      # 展开按钮
                    m2 = re.search(r"(\d+\.\d+)", td)
                    if m2:
                        vals.append(float(m2.group(1)))
                if len(vals) < 2:
                    return None
                home_p, away_p = vals[0], vals[1]
                ln = float(ref.group(1))
                ln = abs(round(ln, 3)) if market == "OU" else round(ln, 3)
                return ln, home_p, away_p

            o = parse_one(blocks[0])
            c = parse_one(blocks[1])
            if not o or not c:
                continue
            name = resolve_name(cid, cache)
            if "平均" in name:
                continue
            out.append({"cid": cid, "bookmaker": name,
                        "open": (o[1], o[2], None), "close": (c[1], c[2], None),
                        "line_open": o[0], "line_close": c[0], "dtime": dtime})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj_v2\out\bok500.db")
    ap.add_argument("--date", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--markets", default="1X2,AH,OU")
    a = ap.parse_args()

    con = sqlite3.connect(a.db, timeout=60)
    con.executescript(DDL)
    cache = load_cache()
    rows = list_finished(a.date)
    if a.limit:
        rows = rows[:a.limit]
    markets = [m.strip() for m in a.markets.split(",")]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{a.date} 完场 {len(rows)} 场，市场={markets}")

    n = 0
    for k, r in enumerate(rows, 1):
        for mk in markets:
            for attempt in range(3):
                try:
                    items = parse_close_page(r["fid"], mk, cache)
                except Exception:
                    items = []
                if items:
                    break
                if attempt < 2:
                    time.sleep(3 if attempt == 0 else 8)
            for it in items:
                con.execute("""INSERT OR REPLACE INTO odds_close
                    (fid,market,bookmaker,cid,open_h,open_d,open_a,close_h,close_d,close_a,
                     open_line,close_line,book_update_utc,source,collected_utc)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (r["fid"], mk, it["bookmaker"], it["cid"],
                             # 1X2: (h,d,a) 直接对应 open_h/open_d/open_a
                             # AH/OU: (主水位, 客水位, None) → open_h/open_a，open_d 留空
                             it["open"][0], (it["open"][1] if mk == "1X2" else None), (it["open"][2] if mk == "1X2" else it["open"][1]),
                             it["close"][0], (it["close"][1] if mk == "1X2" else None), (it["close"][2] if mk == "1X2" else it["close"][1]),
                             it["line_open"], it["line_close"], it["dtime"], "500.com", now))
                n += 1
        if k % 20 == 0:
            print(f"  {k}/{len(rows)}  累计 {n} 条")
            con.commit()
    con.commit()
    print(f"完成: {n} 条 close 记录")
    con.close()


if __name__ == "__main__":
    main()
