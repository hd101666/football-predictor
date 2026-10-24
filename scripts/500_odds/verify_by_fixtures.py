# -*- coding: utf-8 -*-
"""用 Pinnacle 实际赛程反向验证 LLM 翻译（最终质检）。

原理：
  若翻译正确，则「中文A vs 中文B」这场 qiety 比赛，
  用翻译后的「英文A vs 英文B」应该能在 Pinnacle 对应联赛同时段找到匹配。

  这是终极验证 —— 不看模型自信度，只看数据是否真的对得上。

输出：
  verified.csv   通过验证的映射（可用于生产）
  rejected.csv   未通过的（附原因）
"""
import argparse
import csv
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

sys.path.insert(0, r"D:\cl\qqsj_v2")
from match_pinnacle_v2 import LEAGUE_HINT, norm  # noqa: E402


def P(t):
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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
    ap.add_argument("--llm", default=r"D:\cl\qqsj_v2\qiety_team_map_llm.csv")
    ap.add_argument("--out-ok", default=r"D:\cl\qqsj_v2\map_verified.csv")
    ap.add_argument("--out-bad", default=r"D:\cl\qqsj_v2\map_rejected.csv")
    ap.add_argument("--tol", type=int, default=30)
    ap.add_argument("--min-score", type=float, default=0.85)
    a = ap.parse_args()

    # 读 LLM 翻译（未过滤的原始版，验证要独立）
    llm = {}
    if os.path.exists(a.llm):
        with open(a.llm, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en and en != "?" and not re.search("[\u4e00-\u9fff]", en):
                    llm[zh] = en
    print(f"LLM 翻译候选: {len(llm)} 条")

    con = sqlite3.connect("file:" + a.db + "?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row

    # 已有映射（作为额外证据）
    base = {}
    bp = r"D:\cl\qqsj_v2\qiety_team_map.csv"
    if os.path.exists(bp):
        with open(bp, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en:
                    base[zh] = en

    # Pinnacle 索引
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

    # qiety 赛事
    qy = con.execute("""
        SELECT home_team, away_team, kickoff_utc, league, COUNT(*) n
        FROM soft_odds_snapshots WHERE source='qiety' AND kickoff_utc IS NOT NULL
        GROUP BY home_team, away_team, kickoff_utc, league
    """).fetchall()

    # 对每个待验证队名，收集它在 qiety 赛事里的出现
    votes = defaultdict(lambda: defaultdict(int))     # zh -> en -> 成功次数
    attempts = defaultdict(int)

    for q in qy:
        h = str(q["home_team"] or "").strip()
        aw = str(q["away_team"] or "").strip()
        # 至少一队在 LLM 候选里
        if h not in llm and aw not in llm:
            continue
        qd = P(q["kickoff_utc"])
        if not qd:
            continue
        lg = str(q["league"] or "")
        hints = None
        for k, v in LEAGUE_HINT.items():
            if k in lg:
                hints = v
                break
        if not hints:
            continue
        # 该联赛池
        pool = []
        for lg_en, items in pin_by_lg.items():
            if any(hh.lower() in lg_en.lower() for hh in hints):
                pool.extend([it for it in items
                             if abs((it[0] - qd).total_seconds()) <= a.tol * 60])
        if not pool:
            continue

        h_en = llm.get(h) or base.get(h)
        a_en = llm.get(aw) or base.get(aw)
        if not h_en or not a_en:
            continue

        # 找最佳配对
        best = 0.0
        for d, ph, pa in pool:
            s1 = min(sim(h_en, ph), sim(a_en, pa))
            s2 = min(sim(h_en, pa), sim(a_en, ph))
            best = max(best, s1, s2)

        if h in llm:
            attempts[h] += 1
            if best >= a.min_score:
                votes[h][llm[h]] += 1
        if aw in llm:
            attempts[aw] += 1
            if best >= a.min_score:
                votes[aw][llm[aw]] += 1

    # 判定：至少 1 次成功验证
    ok_rows, bad_rows = [], []
    for zh, en in llm.items():
        n_ok = votes[zh].get(en, 0)
        n_try = attempts[zh]
        if n_ok >= 1:
            ok_rows.append((zh, en, n_ok, n_try, "verified"))
        else:
            reason = "no_match" if n_try else "no_data"
            bad_rows.append((zh, en, 0, n_try, reason))

    with open(a.out_ok, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "verified", "attempts", "status"])
        w.writerows(ok_rows)
    with open(a.out_bad, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "verified", "attempts", "reason"])
        w.writerows(bad_rows)

    print(f"\n✓ 验证通过: {len(ok_rows)} 条")
    print(f"✗ 未通过:   {len(bad_rows)} 条")
    print("\n=== 通过样例 ===")
    for r in ok_rows[:20]:
        print(f"  {r[0]:18} -> {r[1]:28} (验证{r[2]}/{r[3]}场)")
    print("\n=== 未通过样例 ===")
    for r in bad_rows[:15]:
        print(f"  {r[0]:18} -> {r[1]:28} ({r[4]})")
    print(f"\n输出: {a.out_ok} / {a.out_bad}")


if __name__ == "__main__":
    main()
