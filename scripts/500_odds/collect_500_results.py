# -*- coding: utf-8 -*-
"""采集指定日期的完场赛果，写入 bok500.db 的 results 表。

用法：
    python -X utf8 collect_500_results.py --db out/bok500.db --date 2026-10-21
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"D:\cl\qqsj_v2")
from scraper_500_results import list_finished, _scores_from_row, parse_stat, parse_detail  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS results (
    fid          TEXT PRIMARY KEY,
    league_zh    TEXT,
    home_zh      TEXT,
    away_zh      TEXT,
    ft_home      INTEGER,
    ft_away      INTEGER,
    ht_home      INTEGER,
    ht_away      INTEGER,
    corners_home INTEGER,
    corners_away INTEGER,
    status       TEXT,
    source       TEXT DEFAULT '500.com',
    collected_utc TEXT
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj_v2\out\bok500.db")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--with-corners", action="store_true", help="逐场抓 stat 页取角球（慢）")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    con = sqlite3.connect(a.db, timeout=60)
    con.executescript(DDL)
    rows = list_finished(a.date)
    if a.limit:
        rows = rows[:a.limit]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{a.date} 完场 {len(rows)} 场  (角球={'抓' if a.with_corners else '跳过'})")

    n_ft = n_corner = 0
    for k, r in enumerate(rows, 1):
        # 比分来源优先级：detail 页 > 完场列表页
        # 实测 fid=1458184：detail 显示 FT 7-0 / HT 3-0（自洽），
        # 而列表页只显示 3-0（等于半场分，明显不是最终比分）。
        # 因此以 detail 为准，列表页仅在 detail 取不到时兜底。
        ft = None
        ht = None
        d = None
        for _try in range(2):
            try:
                d = parse_detail(r["fid"])
            except Exception:
                d = None
            if d and d.get("ft"):
                break
            if _try == 0:
                time.sleep(2)
        if d and d.get("ft"):
            ft = d["ft"]
            ht = d.get("ht")
        else:
            ft = _scores_from_row(r["raw_row"])
        ch = ca = None
        if a.with_corners:
            st = parse_stat(r["fid"])
            if st:
                ch, ca = st.get("corners_home"), st.get("corners_away")
                if ch is not None:
                    n_corner += 1
            time.sleep(0.4)
        if ft:
            n_ft += 1
        con.execute("""INSERT OR REPLACE INTO results
            (fid,league_zh,home_zh,away_zh,ft_home,ft_away,ht_home,ht_away,
             corners_home,corners_away,status,source,collected_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["fid"], r["league"], r["home"], r["away"],
                     ft[0] if ft else None, ft[1] if ft else None,
                     ht[0] if ht else None, ht[1] if ht else None,
                     ch, ca, "完场", "500.com", now))
        if k % 50 == 0:
            print(f"  {k}/{len(rows)}")
    con.commit()
    print(f"写入 {len(rows)} 场  有比分 {n_ft}  有角球 {n_corner}")
    con.close()


if __name__ == "__main__":
    main()
