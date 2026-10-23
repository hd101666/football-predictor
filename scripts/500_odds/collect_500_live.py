# -*- coding: utf-8 -*-
"""500.com 实时快照采集器（任务13 二.3.b）

从 live.500.com 拿当日赛程（含 lid/fid/赛季/队名），
逐场解析 ouzhi 页的 19 家欧赔，写入 SQLite 快照库。

用法：
    python -X utf8 collect_500_live.py --out D:\\cl\\qqsj_v2\\out\\bok500.db --loop 1
    --loop N: 每轮间隔 --interval 秒，共 N 轮（N=0 表示一直跑）
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

sys.path.insert(0, r"D:\cl\qqsj_v2")
from scraper_500_ouzhi import parse_ouzhi, load_cache, KNOWN  # noqa: E402
from scraper_500_ah_ou import parse_yazhi, parse_daxiao  # noqa: E402

LIVE_URL = "https://live.500.com/"

DDL = """
CREATE TABLE IF NOT EXISTS matches (
    fid          TEXT PRIMARY KEY,
    lid          TEXT,
    sid          TEXT,
    league_zh    TEXT,
    league_tw    TEXT,
    home_zh      TEXT,
    away_zh      TEXT,
    home_tw      TEXT,
    away_tw      TEXT,
    title        TEXT,
    first_seen_utc TEXT,
    last_seen_utc  TEXT
);
CREATE TABLE IF NOT EXISTS odds_1x2 (
    fid          TEXT NOT NULL,
    bookmaker    TEXT NOT NULL,
    cid          INTEGER,
    snapshot_utc TEXT NOT NULL,
    stage        TEXT NOT NULL,        -- open / live
    home_odds    REAL,
    draw_odds    REAL,
    away_odds    REAL,
    book_update_utc TEXT,
    source       TEXT DEFAULT '500.com',
    PRIMARY KEY (fid, bookmaker, snapshot_utc, stage)
);
CREATE INDEX IF NOT EXISTS idx_odds_fid ON odds_1x2(fid);
CREATE INDEX IF NOT EXISTS idx_odds_snap ON odds_1x2(snapshot_utc);
CREATE TABLE IF NOT EXISTS odds_ah (
    fid          TEXT NOT NULL,
    bookmaker    TEXT NOT NULL,
    cid          INTEGER,
    snapshot_utc TEXT NOT NULL,
    stage        TEXT NOT NULL,
    line         REAL,                  -- 主队视角，如 -0.75
    home_price   REAL,
    away_price   REAL,
    price_format TEXT DEFAULT 'HK',     -- 香港盘 0.7~1.0
    book_update_utc TEXT,
    source       TEXT DEFAULT '500.com',
    PRIMARY KEY (fid, bookmaker, snapshot_utc, stage)
);
CREATE TABLE IF NOT EXISTS odds_ou (
    fid          TEXT NOT NULL,
    bookmaker    TEXT NOT NULL,
    cid          INTEGER,
    snapshot_utc TEXT NOT NULL,
    stage        TEXT NOT NULL,
    line         REAL,                  -- 总进球线，如 3.25
    over_price   REAL,
    under_price  REAL,
    price_format TEXT DEFAULT 'HK',
    book_update_utc TEXT,
    source       TEXT DEFAULT '500.com',
    PRIMARY KEY (fid, bookmaker, snapshot_utc, stage)
);
CREATE INDEX IF NOT EXISTS idx_ah_fid ON odds_ah(fid);
CREATE INDEX IF NOT EXISTS idx_ou_fid ON odds_ou(fid);
CREATE TABLE IF NOT EXISTS collect_log (
    ts_utc    TEXT,
    fid       TEXT,
    companies INTEGER,
    ok        INTEGER,
    note      TEXT
);
"""


def fetch(url, timeout=25, enc="gb18030"):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode(enc, "replace")


TR_RE = re.compile(r'<tr[^>]*\bfid="(\d+)"[^>]*>')


def list_today():
    """从 live.500.com 解析当日赛程。返回 [{fid,lid,sid,league_zh,home_zh,away_zh,...}]"""
    html = fetch(LIVE_URL)
    out = []
    for m in re.finditer(r'<tr[^>]*\bfid="(\d+)"[^>]*>', html):
        tag = m.group(0)
        fid = m.group(1)

        def attr(name):
            mm = re.search(rf'\b{name}="([^"]*)"', tag)
            return mm.group(1) if mm else ""

        gy = attr("gy").split(",")          # 简体: 联赛,主,客
        yy = attr("yy").split(",")          # 繁体
        out.append({
            "fid": fid,
            "lid": attr("lid"),
            "sid": attr("sid"),
            "league_zh": gy[0] if len(gy) > 0 else "",
            "home_zh": gy[1] if len(gy) > 1 else "",
            "away_zh": gy[2] if len(gy) > 2 else "",
            "league_tw": yy[0] if len(yy) > 0 else "",
            "home_tw": yy[1] if len(yy) > 1 else "",
            "away_tw": yy[2] if len(yy) > 2 else "",
        })
    return out


def get_title(fid):
    """从 ouzhi 页取标题（含联赛+赛季+队名）。"""
    html = fetch(f"https://odds.500.com/fenxi/ouzhi-{fid}.shtml", timeout=20)
    m = re.search(r"<title>([^<]*)</title>", html)
    return m.group(1) if m else ""


def init_db(path):
    con = sqlite3.connect(path, timeout=60)
    con.executescript(DDL)
    con.commit()
    return con


def run_once(con, cache, only_leagues=None, limit=None, verbose=True):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    matches = list_today()
    if only_leagues:
        matches = [m for m in matches if any(k in m["league_zh"] for k in only_leagues)]
    if limit:
        matches = matches[:limit]
    if verbose:
        print(f"[{now}] 赛程 {len(matches)} 场")

    n_odds = 0
    n_ok = 0
    for k, m in enumerate(matches, 1):
        fid = m["fid"]
        # 带重试解析：500.com 会偶发返回空响应体（HTTP 200 但 body=38 字节纯响应头）。
        # 实测 7 场"失败"里 6 场重试即成功，所以退避要够长（3/8/20/40 秒，共 5 次）。
        rows, meta, tries = [], {}, 0
        BACKOFF = (3, 8, 20, 40)
        for attempt in range(5):
            tries = attempt + 1
            try:
                rows, meta = parse_ouzhi(fid, cache)
            except Exception as e:
                meta = {"err": str(e), "html_len": 0}
                rows = []
            if rows:
                break
            if attempt < 4:
                time.sleep(BACKOFF[attempt])
        if not rows:
            note = f"no companies (tries={tries}, html={meta.get('html_len', 0)})"
            con.execute("INSERT INTO collect_log VALUES (?,?,?,?,?)", (now, fid, 0, 0, note))
            continue
        # 比赛元信息
        title = get_title(fid)
        con.execute("""INSERT INTO matches
            (fid,lid,sid,league_zh,league_tw,home_zh,away_zh,home_tw,away_tw,title,first_seen_utc,last_seen_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(fid) DO UPDATE SET last_seen_utc=excluded.last_seen_utc, title=excluded.title""",
                    (fid, m["lid"], m["sid"], m["league_zh"], m["league_tw"],
                     m["home_zh"], m["away_zh"], m["home_tw"], m["away_tw"],
                     title, now, now))
        # 赔率：open + live 各一行
        for r in rows:
            bu = r["data_time"].replace(" ", "T") + "+08:00" if r["data_time"] else None
            for stage, vals in (("open", r["open"]), ("live", r["live"])):
                con.execute("""INSERT OR REPLACE INTO odds_1x2
                    (fid,bookmaker,cid,snapshot_utc,stage,home_odds,draw_odds,away_odds,book_update_utc,source)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (fid, r["bookmaker"], r["cid"], now, stage,
                             vals[0], vals[1], vals[2], bu, "500.com"))
                n_odds += 1
        # ── 亚盘 + 大小球 ──
        for fn, tbl in ((parse_yazhi, "odds_ah"), (parse_daxiao, "odds_ou")):
            ar, _ = [], {}
            for attempt in range(2):
                try:
                    ar, _ = fn(fid, cache)
                except Exception:
                    ar = []
                if ar:
                    break
                if attempt == 0:
                    time.sleep(2)
            for r in ar:
                bu = (r["live_time"] or "").strip()
                for stage, v in (("open", r["open"]), ("live", r["live"])):
                    if tbl == "odds_ah":
                        con.execute("""INSERT OR REPLACE INTO odds_ah
                            (fid,bookmaker,cid,snapshot_utc,stage,line,home_price,away_price,price_format,book_update_utc,source)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                    (fid, r["bookmaker"], r["cid"], now, stage, v["line"],
                                     v["home"], v["away"], "HK", bu or None, "500.com"))
                    else:
                        con.execute("""INSERT OR REPLACE INTO odds_ou
                            (fid,bookmaker,cid,snapshot_utc,stage,line,over_price,under_price,price_format,book_update_utc,source)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                    (fid, r["bookmaker"], r["cid"], now, stage, v["line"],
                                     v["over"], v["under"], "HK", bu or None, "500.com"))
                n_odds += 1
        n_ok += 1
        con.execute("INSERT INTO collect_log VALUES (?,?,?,?,?)", (now, fid, len(rows), 1, "ok"))
        con.commit()
        if verbose and k % 10 == 0:
            print(f"  {k}/{len(matches)}  {m['league_zh']} {m['home_zh']}vs{m['away_zh']}  {len(rows)} 家")
        time.sleep(0.5)          # 礼貌间隔
    return n_ok, n_odds, len(matches)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\out\bok500.db")
    ap.add_argument("--loop", type=int, default=1, help="轮数，0=无限")
    ap.add_argument("--interval", type=int, default=900, help="轮间隔秒（默认15分钟）")
    ap.add_argument("--leagues", default=None, help="逗号分隔的联赛关键词过滤")
    ap.add_argument("--limit", type=int, default=None, help="最多抓 N 场（测试用）")
    a = ap.parse_args()

    con = init_db(a.out)
    cache = load_cache()
    only = [x.strip() for x in a.leagues.split(",")] if a.leagues else None

    i = 0
    while True:
        i += 1
        t0 = time.time()
        ok, n, tot = run_once(con, cache, only, a.limit)
        print(f"第 {i} 轮完成: {ok}/{tot} 场成功, {n} 条赔率, 耗时 {time.time()-t0:.0f}s")
        if a.loop and i >= a.loop:
            break
        print(f"  等待 {a.interval}s ...")
        time.sleep(a.interval)
    con.close()


if __name__ == "__main__":
    main()
