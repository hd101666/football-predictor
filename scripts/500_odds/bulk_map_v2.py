# -*- coding: utf-8 -*-
"""大规模反建 qiety 中文队名映射（整批联合配对法）。

核心思路（比逐场锚定强得多）：
  同一联赛同一时段，若 qiety 有 n 场比赛、Pinnacle 也有 m 场，
  两边的开赛时间可以精确到分钟地一一对应。
  按时间排序后做序列对齐，配对成功的场次里 2n 个队名同时确定。

  例：意丁某轮 9 场，qiety 9 场、Pinnacle 9 场，时间表完全一致，
      则这 18 个中文队名一次性全部映射出来，不需要任何种子。

做法：
  1. 按 (联赛, 日期) 分组
  2. 组内按开赛时间排序，做贪心时间对齐（±10 分钟视为同一场）
  3. 只保留「一对一、无歧义」的配对
  4. 多轮投票确认，输出高置信映射

用法：
  python -X utf8 bulk_map_v2.py --days 365 --out qiety_team_map_bulk2.csv
"""
import argparse
import csv
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, r"D:\cl\qqsj_v2")
from match_pinnacle_v2 import LEAGUE_HINT, load_team_map  # noqa: E402


def P(t):
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\qiety_team_map_bulk2.csv")
    ap.add_argument("--tol", type=int, default=10, help="时间容差（分钟）")
    a = ap.parse_args()

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    known = load_team_map(con)
    print(f"初始映射表: {len(known)} 条")

    qy = con.execute("""
        SELECT match_key, home_team, away_team, kickoff_utc, league
        FROM soft_odds_snapshots
        WHERE source='qiety' AND kickoff_utc IS NOT NULL
          AND julianday('now') - julianday(kickoff_utc) < ?
        GROUP BY match_key
    """, (a.days,)).fetchall()
    pin = con.execute("""
        SELECT pinn_id, home_team, away_team, kickoff_utc, league_name
        FROM theodds_fixtures
        WHERE source='pinnacle' AND pinn_id IS NOT NULL AND kickoff_utc IS NOT NULL
    """).fetchall()
    print(f"qiety {len(qy)} 场 / Pinnacle {len(pin)} 场")

    # 联赛 -> 英文池
    pin_lg = defaultdict(list)
    for r in pin:
        d = P(r["kickoff_utc"])
        if d:
            pin_lg[str(r["league_name"] or "")].append(
                (d, str(r["home_team"] or ""), str(r["away_team"] or "")))

    # 按 (联赛中文, 日期) 分组 qiety
    groups = defaultdict(list)
    for r in qy:
        d = P(r["kickoff_utc"])
        if not d:
            continue
        lg = str(r["league"] or "")
        groups[(lg, d.strftime("%Y-%m-%d"))].append((d, r))

    votes = defaultdict(lambda: defaultdict(int))
    paired_total = 0

    for (lg_zh, day), qitems in groups.items():
        hints = None
        for k, v in LEAGUE_HINT.items():
            if k in lg_zh:
                hints = v
                break
        if not hints:
            continue
        pool = []
        for lg_en, items in pin_lg.items():
            if any(h.lower() in lg_en.lower() for h in hints):
                pool.extend(items)
        if not pool:
            continue
        # 同一天的 Pinnacle 场次
        dd = datetime.strptime(day, "%Y-%m-%d").date()
        day_pool = [(d, ph, pa) for d, ph, pa in pool if d.date() == dd]
        if not day_pool:
            # 允许跨日 1 天（时区差）
            day_pool = [(d, ph, pa) for d, ph, pa in pool
                        if abs((d.date() - dd).days) <= 1]
        if not day_pool:
            continue

        q_sorted = sorted(qitems, key=lambda x: x[0])
        p_sorted = sorted(day_pool, key=lambda x: x[0])

        # 贪心时间对齐：每个 qiety 场找唯一最近的 Pinnacle 场
        used = set()
        pairs = []
        for qd, qr in q_sorted:
            best = None
            for i, (pd_, ph, pa) in enumerate(p_sorted):
                if i in used:
                    continue
                diff = abs((pd_ - qd).total_seconds())
                if diff <= a.tol * 60:
                    if best is None or diff < best[0]:
                        best = (diff, i, ph, pa)
            if best:
                used.add(best[1])
                pairs.append((qr, best[2], best[3]))

        # 只保留一对一且数量相符的批次（强约束，避免错配）
        if len(pairs) < 2 or len(pairs) != len(qitems) or len(pairs) != len(p_sorted):
            continue
        paired_total += len(pairs)
        for qr, ph, pa in pairs:
            h = str(qr["home_team"] or "").strip()
            aw = str(qr["away_team"] or "").strip()
            if h and h not in known:
                votes[h][ph] += 1
            if aw and aw not in known:
                votes[aw][pa] += 1

    rows = []
    for zh, v in votes.items():
        if zh in known:
            continue
        items = sorted(v.items(), key=lambda kv: -kv[1])
        top, cnt = items[0]
        second = items[1][1] if len(items) > 1 else 0
        if cnt >= 2 and cnt >= second * 2:
            rows.append((zh, top, cnt))

    rows.sort(key=lambda r: -r[2])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "votes"])
        w.writerows(rows)

    print(f"整批配对成功 {paired_total} 场")
    print(f"推出 {len(rows)} 条映射 → {a.out}")
    for zh, en, n in rows[:30]:
        print(f"  {zh:18} -> {en:30} ({n}票)")


if __name__ == "__main__":
    main()
