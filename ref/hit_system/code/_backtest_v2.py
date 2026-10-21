# -*- coding: utf-8 -*-
"""
改进后策略回测 v2：
- 过滤污染赔率（只用 consensus_odds 1.40-5.00 范围）
- 模拟 HIT_SCORE_GLOBAL_THRESHOLD=0.68 的效果
- 模拟 MIN_RECOMMEND_ODDS=2.00 的效果
- 对比改进前后策略
"""
import sqlite3, sys, math
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/sports_data.db')
cur = conn.cursor()

# ─── 读取已结算推荐（连接 consensus_odds 获取干净的赔率）────────────────────────
cur.execute("""
SELECT r.unified_id, r.sport_code, r.league_name, r.market, r.outcome,
       r.hit_score, r.model_prob, r.value_edge, r.fetch_date, r.status,
       o.consensus_odds, o.implied_prob
FROM hit_recommendations r
JOIN consensus_odds o ON r.unified_id = o.unified_id
    AND r.market = o.market AND r.outcome = o.outcome
WHERE r.status IN ('win','lose')
  AND o.consensus_odds BETWEEN 1.40 AND 6.0
ORDER BY r.fetch_date
""")
rows = cur.fetchall()
print(f"可分析记录（连接 consensus_odds）: {len(rows)} 条")

# ─── 旧策略（原始设置）vs 新策略（提升后设置）────────────────────────────────
OLD_MIN_ODDS  = 1.80
OLD_THRESHOLD = 0.65
NEW_MIN_ODDS  = 2.00
NEW_THRESHOLD = 0.68

def roi_stats(subset):
    if not subset: return (0, 0, 0.0, 0.0)
    n = len(subset)
    w = sum(1 for r in subset if r['status']=='win')
    p = sum((r['consensus_odds']-1) if r['status']=='win' else -1 for r in subset)
    return (n, w, w/n, p/n)

all_recs = []
for uid, sport, lg, mkt, out, hs, mp, ev, fd, status, c_odds, imp in rows:
    all_recs.append({
        'uid': uid, 'sport': sport, 'league': lg,
        'market': mkt, 'outcome': out,
        'hit_score': hs or 0, 'model_prob': mp or 0, 'value_edge': ev or 0,
        'status': status, 'consensus_odds': c_odds,
    })

print("\n" + "="*65)
print("策略对比（使用 consensus_odds 作为实际赔率）")
print("="*65)

strategies = [
    ("旧策略（hit≥0.65, odds≥1.80, 含1X2)", lambda r:
        r['hit_score'] >= OLD_THRESHOLD and r['consensus_odds'] >= OLD_MIN_ODDS),
    ("新策略（hit≥0.68, odds≥2.00, 含1X2）", lambda r:
        r['hit_score'] >= NEW_THRESHOLD and r['consensus_odds'] >= NEW_MIN_ODDS),
    ("新策略（hit≥0.68, odds≥2.00, 排除1X2）", lambda r:
        r['hit_score'] >= NEW_THRESHOLD and r['consensus_odds'] >= NEW_MIN_ODDS
        and r['market'] != '1X2'),
    ("精选：hit≥0.70, odds 2.00-3.50, 排除1X2", lambda r:
        r['hit_score'] >= 0.70 and 2.00 <= r['consensus_odds'] <= 3.50
        and r['market'] != '1X2'),
]

print(f"  {'策略':<40} {'注数':>5} {'胜率':>7} {'ROI':>8}")
print("  " + "-"*63)
for name, filt in strategies:
    subset = [r for r in all_recs if filt(r)]
    n, w, wr, roi = roi_stats(subset)
    print(f"  {name:<40} {n:>5} {wr:>7.1%} {roi:>+8.3f}")

# ─── 按市场细分（排除1X2，新策略下）────────────────────────────────────────────
print("\n=== 按市场细分（新策略：hit≥0.68, odds≥2.00, 排除1X2）===")
by_mkt = defaultdict(list)
new_recs = [r for r in all_recs
            if r['hit_score'] >= NEW_THRESHOLD and r['consensus_odds'] >= NEW_MIN_ODDS
            and r['market'] != '1X2']
for r in new_recs:
    by_mkt[r['market']].append(r)
print(f"  {'市场':<15} {'注数':>5} {'胜率':>7} {'ROI':>8} {'均赔':>7}")
for mkt, recs in sorted(by_mkt.items(), key=lambda x: len(x[1]), reverse=True):
    n, w, wr, roi = roi_stats(recs)
    avg_o = sum(r['consensus_odds'] for r in recs)/n if n else 0
    print(f"  {mkt:<15} {n:>5} {wr:>7.1%} {roi:>+8.3f} {avg_o:>7.2f}")

# ─── 按运动类型细分───────────────────────────────────────────────────────────
print("\n=== 按运动类型（新策略，排除1X2）===")
by_sport = defaultdict(list)
for r in new_recs:
    by_sport[r['sport'] or 'unknown'].append(r)
for sport, recs in sorted(by_sport.items(), key=lambda x: len(x[1]), reverse=True):
    n, w, wr, roi = roi_stats(recs)
    print(f"  {sport:<15} {n}注  胜率{wr:.1%}  ROI{roi:+.3f}")

# ─── 按赔率段 ────────────────────────────────────────────────────────────────
print("\n=== 按赔率段（新策略，排除1X2）===")
by_odds = defaultdict(list)
for r in new_recs:
    o = r['consensus_odds']
    bkt = ("2.00-2.50" if o < 2.5 else
           ("2.50-3.00" if o < 3.0 else
            ("3.00-3.50" if o < 3.5 else "3.50+")))
    by_odds[bkt].append(r)
for bkt, recs in sorted(by_odds.items()):
    n, w, wr, roi = roi_stats(recs)
    if n >= 5:
        print(f"  {bkt:<12} {n}注  胜率{wr:.1%}  ROI{roi:+.3f}")

# ─── 命中分段 ────────────────────────────────────────────────────────────────
print("\n=== 按命中分段（新策略，排除1X2）===")
by_hs = defaultdict(list)
for r in new_recs:
    hs = r['hit_score']
    bkt = (">= 0.80" if hs >= 0.80 else
           (">= 0.75" if hs >= 0.75 else
            (">= 0.70" if hs >= 0.70 else ">= 0.68")))
    by_hs[bkt].append(r)
for bkt, recs in sorted(by_hs.items()):
    n, w, wr, roi = roi_stats(recs)
    if n >= 3:
        print(f"  {bkt:<12} {n}注  胜率{wr:.1%}  ROI{roi:+.3f}")

conn.close()
print("\n回测完成")
