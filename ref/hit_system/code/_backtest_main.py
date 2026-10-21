# -*- coding: utf-8 -*-
"""
命中系统主回测
数据来源: hit_recommendations + unified_matches + consensus_odds
"""
import sqlite3, sys, math
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/sports_data.db')
cur = conn.cursor()

# ─── A. 已结算推荐总览 ────────────────────────────────────────────────────────
print("=" * 70)
print("A. 已结算推荐总览（2026-05-28 ~ 2026-06-14）")
print("=" * 70)

cur.execute("""
SELECT status, COUNT(*) FROM hit_recommendations GROUP BY status ORDER BY COUNT(*) DESC
""")
status_cnt = dict(cur.fetchall())
total_settled = status_cnt.get('win',0) + status_cnt.get('lose',0)
wr_overall = status_cnt.get('win',0) / total_settled if total_settled else 0
print(f"  胜: {status_cnt.get('win',0)}  负: {status_cnt.get('lose',0)}  "
      f"平: {status_cnt.get('push',0)}  待结算: {status_cnt.get('pending',0)}")
print(f"  总体胜率: {wr_overall:.1%}  已结算: {total_settled}注")

# ─── B. 按市场/方向分析 ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("B. 按市场/方向胜率")
print("=" * 70)
print(f"  {'运动':<10} {'市场':<12} {'方向':<14} {'总':<5} {'胜':<5} {'胜率':<8} {'均赔':>6} {'均EV':>7} {'ROI':>8}")
print("  " + "-" * 70)

cur.execute("""
SELECT sport_code, market, outcome,
       COUNT(*) total,
       SUM(CASE status WHEN 'win' THEN 1 ELSE 0 END) wins,
       AVG(best_odds) avg_odds,
       AVG(value_edge) avg_ev
FROM hit_recommendations
WHERE status IN ('win','lose')
GROUP BY sport_code, market, outcome
ORDER BY total DESC LIMIT 30
""")
for sport, mkt, out, tot, w, odds, ev in cur.fetchall():
    l = tot - w
    wr = w / tot if tot > 0 else 0
    roi = wr * (odds - 1) - (1 - wr) if odds else 0
    print(f"  {(sport or '')[:9]:<10} {(mkt or '')[:11]:<12} {(out or '')[:13]:<14} "
          f"{tot:<5} {w:<5} {wr:<8.1%} {(odds or 0):>6.2f} {(ev or 0):>7.3f} {roi:>+8.3f}")

# ─── C. 命中分段胜率 ─────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("C. 按命中分段胜率（核心校准表）")
print("=" * 70)
print(f"  {'分段':<12} {'注数':<6} {'胜率':<8} {'均赔':>6} {'模型EV':>8} {'实际ROI':>8}")
print("  " + "-" * 55)

cur.execute("""
SELECT
  CASE
    WHEN hit_score >= 0.90 THEN '0.90+'
    WHEN hit_score >= 0.85 THEN '0.85-0.90'
    WHEN hit_score >= 0.80 THEN '0.80-0.85'
    WHEN hit_score >= 0.75 THEN '0.75-0.80'
    WHEN hit_score >= 0.70 THEN '0.70-0.75'
    WHEN hit_score >= 0.65 THEN '0.65-0.70'
    ELSE '<0.65'
  END tier,
  COUNT(*) total,
  SUM(CASE status WHEN 'win' THEN 1 ELSE 0 END) wins,
  AVG(best_odds) avg_odds,
  AVG(value_edge) avg_ev
FROM hit_recommendations
WHERE status IN ('win','lose')
GROUP BY tier
ORDER BY tier DESC
""")
for tier, tot, w, odds, ev in cur.fetchall():
    wr = w / tot if tot > 0 else 0
    roi = wr * ((odds or 2.0) - 1) - (1 - wr)
    print(f"  {tier:<12} {tot:<6} {wr:<8.1%} {(odds or 0):>6.2f} {(ev or 0):>8.3f} {roi:>+8.3f}")

# ─── D. 按运动分类 ────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("D. 足球 vs 篮球")
print("=" * 70)
cur.execute("""
SELECT sport_code,
  COUNT(*) total,
  SUM(CASE status WHEN 'win' THEN 1 ELSE 0 END) wins,
  AVG(best_odds) avg_odds, AVG(hit_score) avg_hs, AVG(value_edge) avg_ev
FROM hit_recommendations
WHERE status IN ('win','lose')
GROUP BY sport_code
""")
for sport, tot, w, odds, hs, ev in cur.fetchall():
    wr = w / tot if tot > 0 else 0
    roi = wr * ((odds or 2.0) - 1) - (1 - wr)
    print(f"  {(sport or ''):<12}: {tot}注  胜率{wr:.1%}  ROI{roi:+.3f}  均赔@{(odds or 0):.2f}  "
          f"均分{(hs or 0):.3f}  均EV{(ev or 0):.3f}")

# ─── E. 按联赛胜率（足球，≥3注）─────────────────────────────────────────────
print("\n" + "=" * 70)
print("E. 足球联赛胜率排名（≥3注）")
print("=" * 70)
cur.execute("""
SELECT league_name,
  COUNT(*) total,
  SUM(CASE status WHEN 'win' THEN 1 ELSE 0 END) wins,
  AVG(best_odds) avg_odds, AVG(hit_score) avg_hs
FROM hit_recommendations
WHERE status IN ('win','lose')
  AND sport_code IN ('football','soccer','Football','Soccer')
GROUP BY league_name HAVING COUNT(*) >= 3
ORDER BY wins * 1.0 / COUNT(*) DESC
""")
rows = cur.fetchall()
print(f"  {'联赛':<35} {'注':<5} {'胜率':<8} {'均赔':>6} {'均分':>7}")
print("  " + "-" * 60)
for lg, tot, w, odds, hs in rows[:20]:
    wr = w / tot
    print(f"  {(lg or '')[:34]:<35} {tot:<5} {wr:<8.1%} {(odds or 0):>6.2f} {(hs or 0):>7.3f}")

# ─── F. 历史回测：用unified_matches结果匹配consensus_odds ────────────────────
print("\n" + "=" * 70)
print("F. 历史回测：全量已结算比赛 × consensus_odds（模拟过去18天）")
print("=" * 70)

cur.execute("""
SELECT m.unified_id, m.sport_code, m.league_name,
       m.home_team_std, m.away_team_std,
       m.home_score, m.away_score, m.kickoff_utc,
       o.market, o.outcome, o.consensus_odds, o.implied_prob
FROM unified_matches m
JOIN consensus_odds o ON m.unified_id = o.unified_id
WHERE m.home_score IS NOT NULL
  AND m.away_score IS NOT NULL
  AND o.consensus_odds >= 1.50
  AND o.consensus_odds <= 4.00
  AND o.market IN ('moneyline','1X2','spread','total')
ORDER BY m.kickoff_utc DESC
""")
all_bets = cur.fetchall()
print(f"  可分析投注机会: {len(all_bets)}")

# 判断投注结果
def check_outcome(sport, mkt, outcome, hs, as_, odds_outcome):
    """返回 True=胜, False=负, None=push"""
    if mkt == 'moneyline':
        if outcome == 'home': return hs > as_
        if outcome == 'away': return as_ > hs
        if outcome == 'draw': return hs == as_
    elif mkt == '1X2':
        if outcome == '1': return hs > as_
        if outcome == 'X': return hs == as_
        if outcome == '2': return as_ > hs
    elif mkt == 'spread':
        try:
            hcap = float(odds_outcome.split('_')[-1].replace('m','-'))
        except:
            return None
        adj = hs + hcap - as_
        if abs(adj) < 0.01: return None
        return adj > 0
    elif mkt == 'total':
        try:
            line = float(odds_outcome.split('_')[-1])
            total = hs + as_
            if outcome == 'over': return total > line
            if outcome == 'under': return total < line
        except:
            return None
    return None

# 模拟全量投注（无EV过滤，看基础胜率）
mkt_stats = defaultdict(lambda: {'bets':0,'wins':0,'push':0,'profit':0.0})
sport_stats = defaultdict(lambda: {'bets':0,'wins':0,'profit':0.0})

for uid, sport, lg, ht, at, hs, as_, kick, mkt, outcome, odds, imp in all_bets:
    result = check_outcome(sport, mkt, outcome, hs, as_, outcome)
    if result is None:
        mkt_stats[mkt]['push'] += 1
        continue
    mkt_stats[mkt]['bets'] += 1
    sport_stats[sport]['bets'] += 1
    if result:
        mkt_stats[mkt]['wins'] += 1
        mkt_stats[mkt]['profit'] += (odds - 1)
        sport_stats[sport]['wins'] += 1
        sport_stats[sport]['profit'] += (odds - 1)
    else:
        mkt_stats[mkt]['profit'] -= 1.0
        sport_stats[sport]['profit'] -= 1.0

print(f"\n  {'市场':<12} {'注数':<6} {'胜率':<8} {'ROI':>8}")
print("  " + "-" * 38)
for mkt, s in sorted(mkt_stats.items(), key=lambda x: x[1]['bets'], reverse=True):
    if s['bets'] > 0:
        wr = s['wins'] / s['bets']
        roi = s['profit'] / s['bets']
        print(f"  {mkt:<12} {s['bets']:<6} {wr:<8.1%} {roi:>+8.3f}")

print(f"\n  {'运动':<12} {'注数':<6} {'胜率':<8} {'ROI':>8}")
print("  " + "-" * 38)
for sport, s in sport_stats.items():
    if s['bets'] > 0:
        wr = s['wins'] / s['bets']
        roi = s['profit'] / s['bets']
        print(f"  {sport:<12} {s['bets']:<6} {wr:<8.1%} {roi:>+8.3f}")

# ─── G. 隐含概率校准分析 ──────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("G. 庄家隐含概率校准（实际胜率 vs 隐含概率）")
print("=" * 70)
print("  测试庄家隐含概率是否准确（越准=越难有EV）")

calib = defaultdict(lambda: {'bets':0,'wins':0})
cur.execute("""
SELECT m.sport_code, m.home_score, m.away_score,
       o.market, o.outcome, o.implied_prob, o.consensus_odds
FROM unified_matches m
JOIN consensus_odds o ON m.unified_id = o.unified_id
WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
  AND o.market IN ('moneyline','1X2')
  AND o.implied_prob BETWEEN 0.3 AND 0.9
""")
for sport, hs, as_, mkt, outcome, imp, odds in cur.fetchall():
    result = check_outcome(sport, mkt, outcome, hs, as_, outcome)
    if result is None: continue
    bucket = round(imp * 10) / 10
    calib[bucket]['bets'] += 1
    calib[bucket]['wins'] += int(result)

print(f"  {'隐含概率':<10} {'注数':<6} {'实际胜率':<10} {'误差':<8} {'校准质量'}")
print("  " + "-" * 50)
for bucket in sorted(calib.keys()):
    s = calib[bucket]
    if s['bets'] < 20: continue
    actual = s['wins'] / s['bets']
    diff = actual - bucket
    quality = "✅ 准确" if abs(diff) < 0.03 else ("⚠ 偏高" if diff > 0 else "⚠ 偏低")
    bar = '▓' * int(actual*20) + '░' * (20-int(actual*20))
    print(f"  {bucket:<10.1f} {s['bets']:<6} {actual:<10.3f} {diff:<+8.3f} {quality}")

# ─── H. 问题诊断总结 ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("H. 问题诊断总结")
print("=" * 70)

cur.execute("""
SELECT AVG(best_odds), AVG(value_edge), AVG(hit_score)
FROM hit_recommendations WHERE status IN ('win','lose')
""")
r = cur.fetchone()
avg_odds, avg_edge, avg_hs = r
break_even = 1 / avg_odds if avg_odds else 0.5
print(f"\n  均赔率: @{avg_odds:.3f}  盈亏平衡胜率: {break_even:.1%}")
print(f"  实际胜率: {wr_overall:.1%}  vs 盈亏平衡: {break_even:.1%}")
print(f"  缺口: {wr_overall - break_even:+.1%}")
print(f"  模型平均EV: {avg_edge:.3f}  平均命中分: {avg_hs:.3f}")
print()

if wr_overall < break_even:
    print("  ❌ 当前模型亏损：实际胜率低于盈亏平衡胜率")
elif wr_overall < break_even + 0.03:
    print("  ⚠  当前模型接近盈亏平衡，需要提高")
else:
    print("  ✅ 当前模型盈利")

conn.close()
print("\n回测完成")
