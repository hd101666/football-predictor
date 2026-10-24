# -*- coding: utf-8 -*-
"""修复第 2 项：区分初盘/收盘的庄家更新时间（不依赖 500.com 的部分）。

现状（实测数据）：
  1X2    open/close 时间不同（如 19:13:40），但**同一秒** → 说明取的是行级单一 data-time
  AH/OU  open/close 时间相同，且 = 开赛时间 + 24.0h（2537/3287 场 = 77%）
         → 抓取时取错字段，拿到了固定偏移值

修复策略（分两级）：
  A. 【可立即做】把已知不可靠的时间标记出来，不让下游误用
     - AH/OU 且 (book_update_bj - kickoff) 落在 +23.5~+24.5h → 判定为 INVALID_PLACEHOLDER
     - 1X2 的 open/close 同秒 → 判定为 ROW_LEVEL_TIME（只有更新时刻，无分期）
     新增字段 book_update_quality: exact / row_level / placeholder / unknown

  B. 【需解封】重新抓 500.com 页面，从 <time> / dt 属性取各自的更新时间
     解封后由 resume_500_company.py 补抓并覆盖

用法：
  python -X utf8 fix_book_update_time.py --companydb out/bok500_company.db
"""
import argparse
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone


def P(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def P_bj(s):
    """500.com 的 book_update_bj 是北京时间字符串。"""
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone(timedelta(hours=8)))
    except ValueError:
        return None


QUALITY_DDL = """
CREATE TABLE IF NOT EXISTS book_update_quality (
    fid TEXT NOT NULL,
    market TEXT NOT NULL,
    stage TEXT NOT NULL,
    quality TEXT NOT NULL,       -- exact / row_level / placeholder / unknown
    delta_hours REAL,            -- book_update - kickoff（小时），便于审计
    note TEXT,
    checked_utc TEXT,
    PRIMARY KEY (fid, market, stage)
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--companydb", default=r"D:\cl\qqsj_v2\out\bok500_company.db")
    ap.add_argument("--histdb", default=r"D:\cl\qqsj_v2\out\bok500_hist.db")
    ap.add_argument("--write-db", action="store_true", help="把判定结果写入 book_update_quality 表")
    a = ap.parse_args()

    hist = sqlite3.connect("file:" + a.histdb + "?mode=ro", uri=True, timeout=60)
    ko = {f: k for f, k in hist.execute("SELECT fid, kickoff_utc FROM matches")}

    con = sqlite3.connect(a.companydb, timeout=120)
    con.executescript(QUALITY_DDL)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 按 (fid, market) 聚合，比较 open/close 时间是否相同
    rows = con.execute("""
        SELECT fid, market, stage, book_update_bj, MIN(bookmaker)
        FROM company_odds
        GROUP BY fid, market, stage, book_update_bj
    """).fetchall()

    per = {}   # (fid, market) -> {stage: set(times)}
    for fid, mk, st, t, _ in rows:
        per.setdefault((fid, mk), {}).setdefault(st, set()).add(t)

    out = []
    stats = Counter()
    for (fid, mk), stages in per.items():
        k = P(ko.get(fid))
        for st, times in stages.items():
            # 同 stage 内可能有多家公司不同时间，取最常见的
            t = sorted(times)[0] if times else None
            bt = P_bj(t)
            delta = None
            if k and bt:
                delta = round((bt - k).total_seconds() / 3600, 2)

            quality, note = "unknown", ""
            if bt is None:
                quality, note = "unknown", "时间为空或格式异常"
            elif mk in ("AH", "OU") and delta is not None and 23.5 <= delta <= 24.5:
                quality = "placeholder"
                note = f"开赛后 +{delta}h，为抓取固定偏移值，非真实更新时间"
            elif mk == "AH" and delta is not None and delta > 12:
                quality = "placeholder"
                note = f"开赛后 +{delta}h，明显晚于开赛，不可信"
            elif mk == "OU" and delta is not None and delta > 12:
                quality = "placeholder"
                note = f"开赛后 +{delta}h，明显晚于开赛，不可信"
            else:
                # open/close 时间完全相同 → 行级时间，无法区分分期
                allt = set()
                for s2, ts2 in stages.items():
                    allt |= ts2
                if len(allt) == 1:
                    quality = "row_level"
                    note = "open/close 共用同一时间，无法区分初盘/收盘"
                else:
                    quality = "exact"
                    note = "open/close 时间不同，可信"

            stats[quality] += 1
            out.append((fid, mk, st, quality, delta, note, now))

    print("=== 时间质量判定 ===")
    for q, n in stats.most_common():
        print(f"  {q:12} {n:6} 条")

    print("\n=== 按市场细分 ===")
    by_mk = Counter((r[1], r[3]) for r in out)
    for (mk, q), n in sorted(by_mk.items()):
        print(f"  {mk:4} {q:12} {n:5}")

    if a.write_db:
        con.executemany("""INSERT OR REPLACE INTO book_update_quality
            (fid,market,stage,quality,delta_hours,note,checked_utc)
            VALUES (?,?,?,?,?,?,?)""", out)
        con.commit()
        print(f"\n✅ 已写入 book_update_quality: {len(out)} 条")
    else:
        print("\n（未写库，加 --write-db 才写入）")

    con.close()


if __name__ == "__main__":
    main()
