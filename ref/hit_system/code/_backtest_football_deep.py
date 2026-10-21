# -*- coding: utf-8 -*-
"""
足球/篮球深度历史回测
使用 unified_matches（含实际比分）× consensus_odds（含融合概率）
评估：隐含概率 vs 实际结果，按EV/联赛/赔率段分层
"""
import sqlite3, sys, math
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/sports_data.db')
cur = conn.cursor()

# ─── 1. 读取全量已结算比赛 + 赔率 ────────────────────────────────────────────
cur.execute("""
SELECT m.unified_id, m.sport_code, m.league_name,
       m.home_team_std, m.away_team_std,
       m.home_score, m.away_score,
       o.market, o.outcome, o.consensus_odds, o.implied_prob,
       o.sharp_odds, o.source_count,
       r.hit_score, r.value_edge, r.kelly_fraction, r.model_prob
FROM unified_matches m
JOIN consensus_odds o ON m.unified_id = o.unified_id
LEFT JOIN hit_recommendations r ON m.unified_id = r.unified_id
    AND o.market = r.market AND o.outcome = r.outcome
WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
  AND o.consensus_odds BETWEEN 1.40 AND 5.00
  AND o.market IN ('moneyline','1X2','spread','total')
ORDER BY m.kickoff_utc
""")
rows = cur.fetchall()
print(f"全量分析数据: {len(rows)} 条投注机会（{len(set(r[0] for r in rows))} 场比赛）")

# ─── 2. 判断投注结果 ──────────────────────────────────────────────────────────
def bet_result(mkt, outcome, hs, as_):
    if mkt in ('moneyline','1X2'):
        h_win = hs > as_; draw = hs == as_; a_win = as_ > hs
        if outcome in ('home','1'): return 1 if h_win else (0 if draw else -1)
        if outcome in ('away','2'): return 1 if a_win else (0 if draw else -1)
        if outcome in ('draw','X'): return 1 if draw else -1
    elif mkt == 'total':
        try:
            line = float(outcome.split('_')[-1]) if '_' in outcome else float(outcome)
            tot = hs + as_
            if abs(tot - line) < 0.01: return 0
            if 'over' in outcome or tot > line: return 1 if tot > line else -1
            return 1 if tot < line else -1
        except: pass
    return None

# ─── 3. 全量统计 ─────────────────────────────────────────────────────────────
SIM_ODDS = 1.88  # 实际下注赔率（含vig折扣）

by_mkt    = defaultdict(lambda: {'n':0,'w':0,'p':0.0})
by_sport  = defaultdict(lambda: {'n':0,'w':0,'p':0.0})
by_odds   = defaultdict(lambda: {'n':0,'w':0,'p':0.0})
by_hs     = defaultdict(lambda: {'n':0,'w':0,'p':0.0})
by_ev     = defaultdict(lambda: {'n':0,'w':0,'p':0.0})
calib     = defaultdict(lambda: {'n':0,'w':0})
league_fb = defaultdict(lambda: {'n':0,'w':0,'p':0.0})
league_bb = defaultdict(lambda: {'n':0,'w':0,'p':0.0})

all_data  = []

for uid, sport, lg, ht, at, hs, as_, mkt, outcome, odds, imp, sharp, src_cnt, hit_sc, val_e, kelly, model_p in rows:
    r = bet_result(mkt, outcome, hs, as_)
    if r is None: continue

    profit = (odds - 1) if r == 1 else (-1 if r == -1 else 0)
    win = r == 1

    by_mkt[mkt]['n'] += 1
    by_mkt[mkt]['w'] += int(win)
    by_mkt[mkt]['p'] += profit

    by_sport[sport or 'unknown']['n'] += 1
    by_sport[sport or 'unknown']['w'] += int(win)
    by_sport[sport or 'unknown']['p'] += profit

    # 赔率分段
    ob = f"{math.floor(odds*4)/4:.2f}+" if odds >= 2.0 else f"{math.floor(odds*4)/4:.2f}"
    ob2 = "1.40-1.60" if odds < 1.6 else ("1.60-1.80" if odds < 1.8 else (
          "1.80-2.00" if odds < 2.0 else ("2.00-2.50" if odds < 2.5 else "2.50+")))
    by_odds[ob2]['n'] += 1
    by_odds[ob2]['w'] += int(win)
    by_odds[ob2]['p'] += profit

    # 命中分段
    if hit_sc:
        hb = f">={math.floor(hit_sc*20)/20:.2f}"
        by_hs[hb]['n'] += 1; by_hs[hb]['w'] += int(win); by_hs[hb]['p'] += profit

    # EV分段
    if val_e is not None:
        eb = f"EV{math.floor(val_e*20)/20:+.2f}+"
        by_ev[eb]['n'] += 1; by_ev[eb]['w'] += int(win); by_ev[eb]['p'] += profit

    # 校准桶
    if imp and 0.2 <= imp <= 0.9:
        bkt = round(imp * 10) / 10
        calib[bkt]['n'] += 1; calib[bkt]['w'] += int(win)

    # 联赛
    if sport in ('football','soccer','Football','Soccer'):
        league_fb[lg or 'Unknown']['n'] += 1
        league_fb[lg or 'Unknown']['w'] += int(win)
        league_fb[lg or 'Unknown']['p'] += profit
    elif sport in ('basketball','Basketball'):
        league_bb[lg or 'Unknown']['n'] += 1
        league_bb[lg or 'Unknown']['w'] += int(win)
        league_bb[lg or 'Unknown']['p'] += profit

    all_data.append({'win': win, 'profit': profit, 'odds': odds, 'imp': imp,
                     'hit_sc': hit_sc, 'val_e': val_e, 'sport': sport, 'mkt': mkt})

total_n = sum(s['n'] for s in by_mkt.values())
total_w = sum(s['w'] for s in by_mkt.values())
total_p = sum(s['p'] for s in by_mkt.values())

print(f"\n总注数: {total_n}  胜: {total_w}  胜率: {total_w/total_n:.1%}  ROI: {total_p/total_n:+.3f}")

# ─── 4. 按市场 ───────────────────────────────────────────────────────────────
print("\n=== 按市场 ===")
print(f"  {'市场':<12} {'注数':<6} {'胜率':<8} {'ROI':>8}")
for mkt, s in sorted(by_mkt.items(), key=lambda x: x[1]['n'], reverse=True):
    if s['n'] > 0:
        print(f"  {mkt:<12} {s['n']:<6} {s['w']/s['n']:<8.1%} {s['p']/s['n']:>+8.3f}")

# ─── 5. 按运动 ───────────────────────────────────────────────────────────────
print("\n=== 按运动类型 ===")
for sport, s in sorted(by_sport.items(), key=lambda x: x[1]['n'], reverse=True):
    if s['n'] > 0:
        print(f"  {sport:<15} {s['n']}注  胜率{s['w']/s['n']:.1%}  ROI{s['p']/s['n']:+.3f}")

# ─── 6. 按赔率段 ─────────────────────────────────────────────────────────────
print("\n=== 按赔率段 ===")
for ob, s in sorted(by_odds.items()):
    if s['n'] >= 10:
        be = 1 / (float(ob.split('-')[0].replace('+','').strip()) + 0.1) if '-' in ob else 0
        print(f"  {ob:<12} {s['n']}注  胜率{s['w']/s['n']:.1%}  ROI{s['p']/s['n']:+.3f}")

# ─── 7. 庄家校准分析 ─────────────────────────────────────────────────────────
print("\n=== 庄家隐含概率 vs 实际胜率（校准分析）===")
print(f"  {'隐含P':<8} {'注数':<6} {'实际胜率':<10} {'误差':<8} {'质量'}")
print("  " + "-" * 48)
for bkt in sorted(calib.keys()):
    s = calib[bkt]
    if s['n'] < 20: continue
    actual = s['w'] / s['n']
    diff = actual - bkt
    qual = "✅" if abs(diff) < 0.03 else ("↑偏高" if diff > 0 else "↓偏低")
    print(f"  {bkt:<8.1f} {s['n']:<6} {actual:<10.3f} {diff:<+8.3f} {qual}")

# ─── 8. 按EV门槛分层（模拟只投正EV盘口）─────────────────────────────────────
print("\n=== EV门槛策略回测 ===")
print(f"  {'EV门槛':<10} {'注数':<6} {'胜率':<8} {'ROI':>8}  说明")
print("  " + "-" * 50)
ev_data = [d for d in all_data if d['val_e'] is not None]
for thr in [None, 0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]:
    if thr is None:
        subset = all_data
        label = "全量（无过滤）"
    else:
        subset = [d for d in ev_data if d['val_e'] >= thr]
        label = f"EV≥{thr:.0%}"
    if not subset: continue
    n = len(subset); w = sum(1 for d in subset if d['win'])
    p = sum(d['profit'] for d in subset)
    print(f"  {label:<10} {n:<6} {w/n:<8.1%} {p/n:>+8.3f}")

# ─── 9. 足球联赛Top/Bottom ────────────────────────────────────────────────────
print("\n=== 足球联赛 Top10（按胜率，≥10注）===")
fb_sorted = [(lg, s) for lg, s in league_fb.items() if s['n'] >= 10]
fb_sorted.sort(key=lambda x: x[1]['w']/x[1]['n'], reverse=True)
for lg, s in fb_sorted[:10]:
    wr = s['w']/s['n']
    print(f"  {lg[:35]:<37} {s['n']}注  胜率{wr:.1%}  ROI{s['p']/s['n']:+.3f}")

print("\n=== 足球联赛 Bottom10（按胜率，≥10注）===")
for lg, s in fb_sorted[-10:]:
    wr = s['w']/s['n']
    print(f"  {lg[:35]:<37} {s['n']}注  胜率{wr:.1%}  ROI{s['p']/s['n']:+.3f}")

print("\n=== 篮球联赛 Top10（按胜率，≥10注）===")
bb_sorted = [(lg, s) for lg, s in league_bb.items() if s['n'] >= 10]
bb_sorted.sort(key=lambda x: x[1]['w']/x[1]['n'], reverse=True)
for lg, s in bb_sorted[:10]:
    wr = s['w']/s['n']
    print(f"  {lg[:35]:<37} {s['n']}注  胜率{wr:.1%}  ROI{s['p']/s['n']:+.3f}")

# ─── 10. 命中分 vs 实际胜率校准 ───────────────────────────────────────────────
print("\n=== 命中分 vs 实际胜率（校准曲线）===")
hs_calib = defaultdict(lambda: {'n':0,'w':0})
for d in all_data:
    if d['hit_sc']:
        bkt = round(d['hit_sc'] * 10) / 10
        hs_calib[bkt]['n'] += 1
        hs_calib[bkt]['w'] += int(d['win'])
print(f"  {'命中分':<8} {'注数':<6} {'实际胜率':<10} {'误差':<8}")
print("  " + "-" * 38)
for bkt in sorted(hs_calib.keys()):
    s = hs_calib[bkt]
    if s['n'] < 10: continue
    actual = s['w'] / s['n']
    diff = actual - bkt
    print(f"  {bkt:<8.1f} {s['n']:<6} {actual:<10.3f} {diff:<+8.3f}")

conn.close()
print("\n深度回测完成")
