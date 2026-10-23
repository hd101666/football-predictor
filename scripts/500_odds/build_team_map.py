# -*- coding: utf-8 -*-
"""补充 qiety 中文队名 → 英文 映射（基于 Pinnacle fixtures 反查）。

思路：
  1. 收集 qiety 里所有"未映射"的中文队名
  2. 对每个中文名，在 Pinnacle fixtures 里按【开赛时间 ±30 分钟】找候选英文队
     （同一时段的比赛大概率同行——队名对不上就是这场的对手）
  3. 用赛程共现关系交叉验证：若 A 场 (中1, 中2) 对应 P 场 (en1, en2)，
     且时间完全一致，则 中1->en1、中2->en2 高置信
  4. 输出到 qiety_team_map_extra.csv，人工可复核

用法：
  python -X utf8 build_team_map.py --db D:\\cl\\qqsj\\data\\sports_data.db \
      --out D:\\cl\\qqsj_v2\\qiety_team_map_extra.csv
"""
import argparse
import csv
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

sys.path.insert(0, r"D:\cl\qqsj_v2")
BASE_MAP = r"D:\cl\qqsj_v2\qiety_team_map.csv"


def ro(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def load_map(path=BASE_MAP):
    m = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en:
                    m[zh] = en
    return m


def norm(x):
    import re
    s = str(x or "").lower()
    s = s.replace("-", " ").replace(".", " ").replace("'", "")
    s = re.sub(r"[（(].*?[)）]", " ", s)
    s = re.sub(r"\b(fc|cf|sc|ac|afc|cd|ud|sv|fk|nk|bk|if|ff)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\qiety_team_map_extra.csv")
    ap.add_argument("--window", type=int, default=30, help="时间窗（分钟）")
    a = ap.parse_args()

    con = ro(a.db)
    known = load_map()

    # qiety 赛事（中文队名 + 开赛）
    qy = con.execute("""
        SELECT DISTINCT home_team, away_team, kickoff_utc
        FROM soft_odds_snapshots
        WHERE source='qiety' AND kickoff_utc IS NOT NULL
    """).fetchall()

    # Pinnacle 赛事
    pin = con.execute("""
        SELECT DISTINCT home_team, away_team, kickoff_utc
        FROM theodds_fixtures
        WHERE source='pinnacle' AND kickoff_utc IS NOT NULL
    """).fetchall()

    def parse(t):
        try:
            return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except ValueError:
            return None

    pin_by_time = []
    for p in pin:
        d = parse(p["kickoff_utc"])
        if d:
            pin_by_time.append((d, str(p["home_team"]).strip(), str(p["away_team"]).strip()))
    pin_by_time.sort(key=lambda x: x[0])

    # 只处理"两队都未映射"的 qiety 赛事——这种场次整场都对不上，共现关系最可靠
    votes = defaultdict(lambda: defaultdict(int))   # 中文名 -> 英文名 -> 票数
    total_cand = 0

    for q in qy:
        h, aw = str(q["home_team"] or "").strip(), str(q["away_team"] or "").strip()
        if not h or not aw:
            continue
        if h in known and aw in known:
            continue
        kd = parse(q["kickoff_utc"])
        if not kd:
            continue
        # 时间窗内所有 Pinnacle 赛事
        cands = [(d, ph, pa) for d, ph, pa in pin_by_time
                 if abs((d - kd).total_seconds()) <= a.window * 60]
        if not cands:
            continue
        # 已知一队时用它锚定；两队都未知时，靠"同场共现"无法单独定，先跳过
        if h in known or aw in known:
            if h in known:
                anchor_en = norm(known[h])
                other_zh = aw
                for _d, ph, pa in cands:
                    if norm(ph) == anchor_en or anchor_en in norm(ph):
                        votes[other_zh][pa] += 3
                    elif norm(pa) == anchor_en or anchor_en in norm(pa):
                        votes[other_zh][ph] += 3
            if aw in known:
                anchor_en = norm(known[aw])
                other_zh = h
                for _d, ph, pa in cands:
                    if norm(ph) == anchor_en or anchor_en in norm(ph):
                        votes[other_zh][pa] += 3
                    elif norm(pa) == anchor_en or anchor_en in norm(pa):
                        votes[other_zh][ph] += 3
        total_cand += 1

    # 输出高置信（>=3 票且唯一最高）
    rows = []
    for zh, v in votes.items():
        if zh in known:
            continue
        items = sorted(v.items(), key=lambda kv: -kv[1])
        if not items:
            continue
        top, cnt = items[0]
        second = items[1][1] if len(items) > 1 else 0
        conf = "high" if (cnt >= 3 and cnt > second) else "low"
        rows.append((zh, top, cnt, conf))

    rows.sort(key=lambda r: (r[3] != "high", -r[2], r[0]))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "votes", "confidence"])
        for r in rows:
            w.writerow(r)

    high = sum(1 for r in rows if r[3] == "high")
    print(f"参照 {total_cand} 场未映射赛事")
    print(f"推出 {len(rows)} 个中文队名，其中 high {high} / low {len(rows)-high}")
    print(f"输出: {a.out}")
    for r in rows[:15]:
        print(f"  {r[0]:16} -> {r[1]:24} ({r[2]}票, {r[3]})")


if __name__ == "__main__":
    main()
