# -*- coding: utf-8 -*-
"""补抓 500.com 缺失的 968 场公司级赔率 —— 极慢速 + 遇挑战即停。

设计原则（针对 EdgeOne 风控）：
  1. 每个请求间隔 8-10 秒（比原 0.6 秒慢 15 倍）
  2. 【遇到挑战页立即全局停止】—— 不重试、不换 UA、不继续
     一旦返回 Security Verification / 0 字节，说明 IP 被标记，继续请求只会加重封禁
  3. 断点续跑：只抓 hist_company_done 里 pages=0 的场次
  4. 每场抓完立即 commit，中断不丢进度
  5. 全程记录到日志，便于判断是否要再等

用法：
  # 先探测（只发 1 个请求，判断当前 IP 是否已解封）
  python -X utf8 resume_500_company.py --probe

  # 正式补抓（会自动跳过已完成的）
  python -X utf8 resume_500_company.py --run
"""
import argparse
import random
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"D:\cl\qqsj_v2")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROBE_URL = "https://odds.500.com/fenxi/ouzhi-1430753.shtml"
CHALLENGE_MARKS = ("Security Verification", "TEOCaptchaWidget", "EO_Bot_Ssid")
MIN_OK = 100_000


def fetch(url, timeout=30):
    """返回 (html, status)，status: ok / challenge / empty / error"""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "--noproxy", "*",
             "-A", UA, "-H", "Referer: https://odds.500.com/", url],
            capture_output=True)
        raw = r.stdout
    except Exception:
        return "", "error"
    if not raw:
        return "", "empty"
    html = raw.decode("gb18030", "replace")
    if len(html) < 5000:
        if any(m in html for m in CHALLENGE_MARKS) or len(html) < 3000:
            return html, "challenge"
        return html, "short"
    if any(m in html for m in CHALLENGE_MARKS):
        return html, "challenge"
    if "pl_table_data" not in html:
        return html, "no_table"
    return html, "ok"


def probe():
    """单请求探测当前 IP 是否可用。"""
    html, st = fetch(PROBE_URL)
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] 探测 500.com: {st}  len={len(html)}")
    if st == "ok":
        print("  ✅ IP 可用，可以开始补抓")
        return 0
    print("  🚫 IP 仍被拦截/挑战 —— 不要继续请求，等待冷却")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--histdb", default=r"D:\cl\qqsj_v2\out\bok500_hist.db")
    ap.add_argument("--companydb", default=r"D:\cl\qqsj_v2\out\bok500_company.db")
    ap.add_argument("--sleep-min", type=float, default=8.0)
    ap.add_argument("--sleep-max", type=float, default=12.0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--probe", action="store_true", help="只探测，不抓")
    ap.add_argument("--run", action="store_true", help="正式补抓")
    a = ap.parse_args()

    if a.probe or not a.run:
        return probe()

    # 先探测，避免一上来就撞墙
    if probe() != 0:
        print("\n中止：IP 未解封。建议冷却 12-24 小时后再试，或换出口 IP。")
        return 2

    from collect_500_close import parse_close_page, DDL as CLOSE_DDL      # noqa: E402
    from scraper_500_ouzhi import load_cache                              # noqa: E402

    con = sqlite3.connect(a.companydb, timeout=120)
    con.executescript(CLOSE_DDL)
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS company_odds (
                fid TEXT NOT NULL, market TEXT NOT NULL, bookmaker TEXT NOT NULL,
                cid INTEGER, stage TEXT NOT NULL, line_num REAL, line_text TEXT,
                home_val REAL, draw_val REAL, away_val REAL,
                book_update_bj TEXT, source TEXT DEFAULT '500.com',
                PRIMARY KEY (fid, market, bookmaker, stage));
            CREATE TABLE IF NOT EXISTS hist_company_done (
                fid TEXT PRIMARY KEY, pages INTEGER, rows INTEGER, done_utc TEXT);
        """)
    except sqlite3.OperationalError:
        pass

    # 待补：done 表里 pages=0 的（以及完全没有 done 记录的）
    have = {r[0]: r[1] for r in con.execute("SELECT fid, pages FROM hist_company_done")}
    hist = sqlite3.connect("file:" + a.histdb + "?mode=ro", uri=True, timeout=60)
    all_fids = [r[0] for r in hist.execute("SELECT fid FROM matches ORDER BY cast(fid as int)")]
    todo = [f for f in all_fids if have.get(f, -1) == 0 or f not in have]
    if a.limit:
        todo = todo[:a.limit]
    print(f"\n待补 {len(todo)} 场（已完成 {len(all_fids)-len(todo)}）")

    cache = load_cache()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_ok = n_rows = 0
    t0 = time.time()

    for i, fid in enumerate(todo, 1):
        pages = total = 0
        aborted = False
        for mk in ("1X2", "AH", "OU"):
            html, st = fetch(f"https://odds.500.com/fenxi/"
                             f"{ {'1X2':'ouzhi','AH':'yazhi','OU':'daxiao'}[mk] }-{fid}.shtml")
            if st == "challenge" or st == "empty":
                print(f"  🛑 fid={fid} {mk} 返回 {st} —— 全局停止（不重试）")
                aborted = True
                break
            if st != "ok":
                time.sleep(random.uniform(a.sleep_min, a.sleep_max))
                continue
            rows = parse_close_page_from_html(html, mk)
            if rows:
                pages += 1
                for r in rows:
                    con.execute("""INSERT OR REPLACE INTO company_odds
                        (fid,market,bookmaker,cid,stage,line_num,line_text,home_val,draw_val,away_val,book_update_bj,source)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (fid, mk, r["bookmaker"], r["cid"], r["stage"], r["line"],
                                 r.get("line_text"), r["h"], r["d"], r["a"], r.get("upd"), "500.com"))
                    total += 1
            time.sleep(random.uniform(a.sleep_min, a.sleep_max))

        if aborted:
            con.commit()
            break

        if pages > 0:
            con.execute("INSERT OR REPLACE INTO hist_company_done VALUES (?,?,?,?)",
                        (fid, pages, total, now))
            con.commit()
            n_ok += 1
            n_rows += total

        if i % 10 == 0:
            el = time.time() - t0
            rate = i / el * 60 if el else 0
            eta = (len(todo) - i) / rate if rate else 0
            print(f"  {i}/{len(todo)}  成功 {n_ok} 场 / {n_rows} 条  {rate:.1f}场/分  ETA {eta:.0f}分")

    print(f"\n本轮: 成功 {n_ok} 场, {n_rows} 条, 耗时 {(time.time()-t0)/60:.1f} 分钟")
    left = con.execute("SELECT COUNT(*) FROM hist_company_done WHERE pages=0").fetchone()[0]
    print(f"仍缺: {left} 场")
    con.close()
    return 0


def parse_close_page_from_html(html, market):
    """从已抓到的 HTML 解析（复用 collect_500_close 的逻辑）。"""
    import importlib
    C = importlib.import_module("collect_500_close")
    out = []
    cache = C.load_cache() if hasattr(C, "load_cache") else {}
    for cid_s, dtime, body in C.COMP.findall(html):
        cid = int(cid_s)
        if cid in C.AVG_CIDS:
            continue
        blocks = re.findall(r'<table[^>]*class="pl_table_data"[^>]*>(.*?)</table>', body, re.S)
        if not blocks:
            continue
        name = C.resolve_name(cid, cache)
        if "平均" in name:
            continue
        if market == "1X2":
            trows = re.findall(r"<tr[^>]*>(.*?)</tr>", blocks[0], re.S)
            if len(trows) < 2:
                continue
            v0 = re.findall(r">\s*(\d+\.\d{1,3})\s*<", trows[0])
            v1 = re.findall(r">\s*(\d+\.\d{1,3})\s*<", trows[1])
            if len(v0) < 3 or len(v1) < 3:
                continue
            out.append({"bookmaker": name, "cid": cid, "stage": "open",
                        "line": None, "line_text": None,
                        "h": float(v0[0]), "d": float(v0[1]), "a": float(v0[2]), "upd": dtime})
            out.append({"bookmaker": name, "cid": cid, "stage": "close",
                        "line": None, "line_text": None,
                        "h": float(v1[0]), "d": float(v1[1]), "a": float(v1[2]), "upd": dtime})
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
                ln = abs(round(ln, 3)) if market == "OU" else round(ln, 3)
                return ln, (txt.group(1).strip() if txt else ""), vals[0], vals[1]

            o, c = one(blocks[0]), one(blocks[1])
            for stage, v in (("open", o), ("close", c)):
                if v:
                    out.append({"bookmaker": name, "cid": cid, "stage": stage,
                                "line": v[0], "line_text": v[1], "h": v[2], "d": None,
                                "a": v[3], "upd": dtime})
    return out


if __name__ == "__main__":
    sys.exit(main())
