# -*- coding: utf-8 -*-
"""历史数据：逐场抓公司级初盘 + 收盘价（任务13 二.3.a 完整版）。

每个 fid 抓 3 个页面：
    https://odds.500.com/fenxi/ouzhi-<fid>.shtml    1X2  初盘(tr0) + 收盘(tr1)
    https://odds.500.com/fenxi/yazhi-<fid>.shtml    亚盘 初盘(块0) + 收盘(块1)
    https://odds.500.com/fenxi/daxiao-<fid>.shtml   大小球 同上

每页 19 家左右公司，每公司 2 个阶段 → 每场约 114 条记录。

规模：2448 场 × 3 页 ≈ 7300 次请求，按 0.6s/请求 + 失败重试，约 2~3 小时。

支持断点续跑：已完成的 fid 记在 hist_company_done 表，重跑自动跳过。

用法：
    python -X utf8 collect_500_hist_company.py --histdb out/bok500_hist.db --out out/bok500_company.db
"""
import argparse
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

MIN_LEN = {"1X2": 150_000, "AH": 40_000, "OU": 40_000}
PATH = {"1X2": "ouzhi", "AH": "yazhi", "OU": "daxiao"}

COMP = re.compile(
    r'<tr[^>]*class="tr[12]"[^>]*id="(\d+)"[^>]*(?:data-time|dt)="([^"]*)"[^>]*>(.*?)'
    r'(?=<tr[^>]*class="tr[12]"[^>]*id=|\Z)', re.S)

sys.path.insert(0, r"D:\cl\qqsj_v2")
from scraper_500_ouzhi import resolve_name, load_cache, AVG_CIDS  # noqa: E402
from ah_line_map import handline_to_num  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS company_odds (
    fid       TEXT NOT NULL,
    market    TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    cid       INTEGER,
    stage     TEXT NOT NULL,        -- open / close
    line_num  REAL,                 -- 亚盘/大小球的数值盘口
    line_text TEXT,                 -- 原始文字（亚盘）
    home_val  REAL,                 -- 1X2=主胜, AH=主水位, OU=大球水位
    draw_val  REAL,                 -- 1X2=平
    away_val  REAL,                 -- 1X2=客胜, AH=客水位, OU=小球水位
    book_update_bj TEXT,
    source    TEXT DEFAULT '500.com',
    PRIMARY KEY (fid, market, bookmaker, stage)
);
CREATE INDEX IF NOT EXISTS idx_co_fid ON company_odds(fid);
CREATE TABLE IF NOT EXISTS hist_company_done (
    fid TEXT PRIMARY KEY, pages INTEGER, rows INTEGER, done_utc TEXT
);
"""


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def _nums(s):
    return re.findall(r">\s*(\d+\.\d{1,3})\s*<", s)


def parse_page(fid, market, cache):
    """返回 [(bookmaker, cid, stage, line_num, line_text, h, d, a, update)]"""
    html = fetch(f"https://odds.500.com/fenxi/{PATH[market]}-{fid}.shtml")
    if len(html) < MIN_LEN[market]:
        return []
    out = []
    for cid_s, dtime, body in COMP.findall(html):
        cid = int(cid_s)
        if cid in AVG_CIDS:
            continue
        blocks = re.findall(r'<table[^>]*class="pl_table_data"[^>]*>(.*?)</table>', body, re.S)
        if not blocks:
            continue
        name = resolve_name(cid, cache)
        if "平均" in name:
            continue

        if market == "1X2":
            trows = re.findall(r"<tr[^>]*>(.*?)</tr>", blocks[0], re.S)
            if len(trows) < 2:
                continue
            v0, v1 = _nums(trows[0]), _nums(trows[1])
            if len(v0) < 3 or len(v1) < 3:
                continue
            out.append((name, cid, "open", None, None,
                        float(v0[0]), float(v0[1]), float(v0[2]), dtime))
            out.append((name, cid, "close", None, None,
                        float(v1[0]), float(v1[1]), float(v1[2]), dtime))
        else:
            if len(blocks) < 2:
                continue

            def one(blk):
                ref = re.search(r'ref="(-?\d+\.\d+)"', blk)
                txt = re.search(r'ref="[^"]*"[^>]*>([^<]*)<', blk)
                tds = re.findall(r'(<td\b[^>]*>)(.*?)</td>', blk, re.S)
                vals = []
                for tag, td in tds:
                    if "tb_tdul_pan" in tag or "tb_tdul_more" in td:
                        continue
                    m = re.search(r"(\d+\.\d+)", td)
                    if m:
                        vals.append(float(m.group(1)))
                if not ref or len(vals) < 2:
                    return None
                ln = float(ref.group(1))
                if market == "OU":
                    ln = abs(round(ln, 3))
                else:
                    ln = round(ln, 3)
                return ln, (txt.group(1).strip() if txt else ""), vals[0], vals[1]

            o = one(blocks[0])
            c = one(blocks[1])
            if o:
                out.append((name, cid, "open", o[0], o[1], o[2], None, o[3], dtime))
            if c:
                out.append((name, cid, "close", c[0], c[1], c[2], None, c[3], dtime))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--histdb", default=r"D:\cl\qqsj_v2\out\bok500_hist.db")
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\out\bok500_company.db")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--markets", default="1X2,AH,OU")
    ap.add_argument("--sleep", type=float, default=0.6)
    a = ap.parse_args()

    src = sqlite3.connect(f"file:{a.histdb}?mode=ro", uri=True, timeout=60)
    fids = [r[0] for r in src.execute("SELECT fid FROM matches ORDER BY cast(fid as int)")]
    src.close()

    con = sqlite3.connect(a.out, timeout=120)
    con.executescript(DDL)
    done = {r[0] for r in con.execute("SELECT fid FROM hist_company_done")}
    todo = [f for f in fids if f not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f"总 {len(fids)} 场，已完成 {len(done)}，待抓 {len(todo)}")

    cache = load_cache()
    markets = [x.strip() for x in a.markets.split(",")]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    t0 = time.time()
    n_rows = n_done = n_fail = 0
    for i, fid in enumerate(todo, 1):
        total_rows = 0
        pages = 0
        for mk in markets:
            rows = []
            for attempt in range(3):
                try:
                    rows = parse_page(fid, mk, cache)
                except Exception:
                    rows = []
                if rows:
                    break
                time.sleep(2 if attempt < 2 else 0)
            if rows:
                pages += 1
            for (bm, cid, stage, ln, ltxt, h, d, aw, upd) in rows:
                con.execute("""INSERT OR REPLACE INTO company_odds
                    (fid,market,bookmaker,cid,stage,line_num,line_text,home_val,draw_val,away_val,
                     book_update_bj,source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (fid, mk, bm, cid, stage, ln, ltxt, h, d, aw, upd, "500.com"))
                total_rows += 1
            time.sleep(a.sleep)
            # 进度存盘：先把这一步的入库定住，避免中断丢已完成标记
        if pages == 0:
            # 三页全失败（页面空响应/限流）—— 绝不能标记为已完成，
            # 否则断点续跑会永久跳过这场比赛（实测曾因此丢了 968 场）
            con.commit()
            n_fail += 1
            if n_fail <= 20:
                print(f"    [skip] fid={fid} 三页全失败，未标记完成")
            continue
        con.execute("INSERT OR REPLACE INTO hist_company_done VALUES (?,?,?,?)",
                    (fid, pages, total_rows, now))
        con.commit()
        n_rows += total_rows
        n_done += 1
        if i % 20 == 0 or i == len(todo):
            el = time.time() - t0
            rate = i / el * 60 if el else 0
            eta = (len(todo) - i) / rate if rate else 0
            print(f"  {i}/{len(todo)}  {n_rows} 条  速率 {rate:.1f} 场/分  ETA {eta:.0f} 分")

    print(f"\n完成: {n_done} 场成功, {n_fail} 场全失败(未标记,可重跑), {n_rows} 条, 耗时 {(time.time()-t0)/60:.1f} 分钟")
    con.close()


if __name__ == "__main__":
    main()
