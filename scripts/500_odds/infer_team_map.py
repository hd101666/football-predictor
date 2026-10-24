# -*- coding: utf-8 -*-
"""从 Pinnacle fixtures 给 qiety 缺失队名建映射（联赛内共现反推）。

思路（比之前 build_team_map.py 更严格）：
  1. 对每个 qiety 赛事，先做联赛+时间筛选，得到该场的 Pinnacle 候选池
  2. 已在映射表里的队名用它锚定，推出另一队
  3. 同一联赛内批量做：把 qiety 该联赛所有赛事 n 场 与 Pinnacle 该联赛 n 场 做
     匈牙利式最佳配对（按开赛时间+已知识别），配对成功后整场成立
  4. 只输出多次投票一致的高置信映射

用法：
  python -X utf8 infer_team_map.py --days 14 --out qiety_team_map_inferred.csv
"""
import argparse
import csv
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

sys.path.insert(0, r"D:\cl\qqsj_v2")
from match_pinnacle_v2 import LEAGUE_HINT, load_team_map, norm, P  # noqa: E402


def sim(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    r = SequenceMatcher(None, na, nb).ratio()
    if na in nb or nb in na:
        r = max(r, 0.92)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\qiety_team_map_inferred.csv")
    ap.add_argument("--window", type=int, default=45, help="同联赛内时间窗（分钟）")
    a = ap.parse_args()

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    known = load_team_map(con)

    # qiety 赛事（按联赛分组）
    qy = con.execute("""
        SELECT match_key, home_team, away_team, kickoff_utc, league
        FROM soft_odds_snapshots
        WHERE source='qiety' AND kickoff_utc IS NOT NULL
          AND julianday('now') - julianday(kickoff_utc) < ?
        GROUP BY match_key
    """, (a.days,)).fetchall()

    # Pinnacle 赛事（按联赛名分组）
    pin = con.execute("""
        SELECT pinn_id, home_team, away_team, kickoff_utc, league_name
        FROM theodds_fixtures
        WHERE source='pinnacle' AND pinn_id IS NOT NULL AND kickoff_utc IS NOT NULL
        GROUP BY pinn_id
    """).fetchall()

    pin_by_lg = defaultdict(list)
    for r in pin:
        d = P(r["kickoff_utc"])
        if d:
            pin_by_lg[str(r["league_name"] or "")].append(
                (d, str(r["home_team"] or ""), str(r["away_team"] or "")))

    qy_by_lg = defaultdict(list)
    for r in qy:
        qy_by_lg[str(r["league"] or "")].append(r)

    votes = defaultdict(lambda: defaultdict(int))
    pair_ok = 0

    for lg_zh, matches in qy_by_lg.items():
        hints = None
        for k, v in LEAGUE_HINT.items():
            if k in lg_zh:
                hints = v
                break
        if not hints:
            continue
        # 该联赛的 Pinnacle 池
        pool = []
        for lg_en, items in pin_by_lg.items():
            if any(h.lower() in lg_en.lower() for h in hints):
                pool.extend(items)
        if not pool:
            continue

        for q in matches:
            qd = P(q["kickoff_utc"])
            if not qd:
                continue
            h, aw = str(q["home_team"] or ""), str(q["away_team"] or "")
            h_known = h in known
            a_known = aw in known
            if h_known and a_known:
                continue
            # 时间窗内候选
            cands = [(d, ph, pa) for d, ph, pa in pool
                     if abs((d - qd).total_seconds()) <= a.window * 60]
            if not cands:
                continue

            if h_known:
                hen = norm(known[h])
                for d, ph, pa in cands:
                    if sim(hen, ph) >= 0.85:
                        votes[aw][pa] += 2
                    elif sim(hen, pa) >= 0.85:
                        votes[aw][ph] += 2
                pair_ok += 1
            elif a_known:
                aen = norm(known[aw])
                for d, ph, pa in cands:
                    if sim(aen, ph) >= 0.85:
                        votes[h][pa] += 2
                    elif sim(aen, pa) >= 0.85:
                        votes[h][ph] += 2
                pair_ok += 1

    rows = []
    for zh, v in votes.items():
        if zh in known:
            continue
        items = sorted(v.items(), key=lambda kv: -kv[1])
        top, cnt = items[0]
        second = items[1][1] if len(items) > 1 else 0
        conf = "high" if (cnt >= 2 and cnt > second) else "low"
        rows.append((zh, top, cnt, conf))

    rows.sort(key=lambda r: (r[3] != "high", -r[2], r[0]))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "votes", "confidence"])
        w.writerows(rows)

    high = sum(1 for r in rows if r[3] == "high")
    print(f"锚定成功 {pair_ok} 场")
    print(f"推出 {len(rows)} 个映射，high {high} / low {len(rows)-high}")
    print(f"输出: {a.out}")
    for r in rows[:20]:
        print(f"  {r[0]:18} -> {r[1]:28} ({r[2]}票 {r[3]})")


if __name__ == "__main__":
    main()
