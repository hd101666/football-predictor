#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K值推荐单 - 终版 2026-06-06"""

import sys
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = r'F:\qqsj\data\sports_data.db'
LAMBDA_MAP_PATH = r'F:\qqsj\_league_lambda_map.json'
TEAM_MAP_PATH = r'F:\qqsj\_team_cn_en_map.json'

# Default lambda
DEFAULT_LAMBDA_H = 1.45
DEFAULT_LAMBDA_A = 1.15

# Load JSON files
with open(LAMBDA_MAP_PATH, 'r', encoding='utf-8') as f:
    league_lambda_map = json.load(f)

with open(TEAM_MAP_PATH, 'r', encoding='utf-8') as f:
    team_cn_en_map = json.load(f)

# Build reverse map: en -> cn for matching
en_to_cn = {}
for cn, info in team_cn_en_map.items():
    en = info.get('en')
    if en:
        en_to_cn[en.lower()] = cn

# Virtual match keywords to exclude
VIRTUAL_KEYWORDS = ['VS-', '梦幻对垒', 'NBA 2K', 'PANDA独家', 'EAFC', '电竞', 'eSports', 'Esports', 'Virtual']

def is_virtual(league_name):
    if not league_name:
        return True
    for kw in VIRTUAL_KEYWORDS:
        if kw in league_name:
            return True
    return False

def poisson_prob(lambda_h, lambda_a, outcome, line=None):
    """Calculate poisson-based probabilities for match outcomes
    line: for over/under markets, the actual handicap line (e.g. 2.5, 3.25)
    """
    from math import exp, factorial
    
    def p_goals(lam, max_goals=8):
        probs = []
        for g in range(max_goals + 1):
            probs.append(exp(-lam) * (lam ** g) / factorial(g))
        probs.append(1.0 - sum(probs))
        return probs
    
    ph = p_goals(lambda_h)
    pa = p_goals(lambda_a)
    
    if outcome in ('home', 'draw', 'away'):
        p_home = 0.0
        p_draw = 0.0
        p_away = 0.0
        for i in range(len(ph)):
            for j in range(len(pa)):
                p = ph[i] * pa[j]
                if i > j:
                    p_home += p
                elif i == j:
                    p_draw += p
                else:
                    p_away += p
        if outcome == 'home': return p_home
        elif outcome == 'draw': return p_draw
        else: return p_away
    
    elif outcome in ('over', 'under'):
        # Use actual line if available, default 2.5
        threshold = line if line is not None else 2.5
        # For half lines (e.g. 2.5): strict over/under
        # For quarter lines (e.g. 2.25, 2.75): use midpoint approximation
        int_part = int(threshold)
        frac = threshold - int_part
        if frac == 0.0:
            # Whole number: push possible, use > for over
            cutoff = int_part
        elif frac <= 0.25:
            cutoff = int_part  # approximate
        elif frac <= 0.75:
            cutoff = int_part  # use half ball
        else:
            cutoff = int_part
        
        p_under_or_equal = 0.0
        for i in range(len(ph)):
            for j in range(len(pa)):
                if i + j <= cutoff:
                    p_under_or_equal += ph[i] * pa[j]
        
        if outcome == 'over':
            return 1.0 - p_under_or_equal
        else:
            return p_under_or_equal
    
    return 0.5

def calc_k_value(p_fusion, odds):
    """K = (p * o - 1) / (o - 1)"""
    if odds <= 1.0:
        return None
    k = (p_fusion * odds - 1.0) / (odds - 1.0)
    return k

def classify_grade(k, odds, n_sources):
    """Classify into S/A/B/C grade"""
    if k >= 0.10 and 1.5 <= odds <= 3.5 and n_sources >= 2:
        return 'S'
    elif k >= 0.08 and 1.5 <= odds <= 4.0 and n_sources >= 1:
        return 'A'
    elif k >= 0.03:
        return 'B'
    elif k > 0:
        return 'C'
    return None

# Connect to DB
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get current time in Asia/Shanghai
tz_cn = timezone(timedelta(hours=8))
now_cn = datetime.now(tz_cn)
now_str = now_cn.strftime('%Y-%m-%d %H:%M:%S %Z')

print(f"=== K值推荐单 生成时间: {now_str} ===\n")

# Get all pre-match games
cur.execute("""
    SELECT unified_id, sport_code, league_code, league_name, 
           home_team_std, away_team_std, kickoff_utc, status, source_count, sources_json
    FROM unified_matches
    WHERE status IN ('pre', 'scheduled', 'upcoming', 'not_started')
       OR (kickoff_utc IS NOT NULL AND kickoff_utc > datetime('now', '-1 hours'))
""")
matches = cur.fetchall()
print(f"查询到 {len(matches)} 场未开赛比赛\n")

# Get all odds for these matches
match_ids = [m['unified_id'] for m in matches]
if not match_ids:
    print("没有未开赛比赛，退出。")
    sys.exit(0)

# Build odds data structure
# For each match+market+outcome, collect odds from different sources
placeholders = ','.join(['?'] * len(match_ids))
cur.execute(f"""
    SELECT unified_id, source, market, outcome, odds_value, handicap, fetch_date
    FROM unified_odds
    WHERE unified_id IN ({placeholders})
""", match_ids)
all_odds = cur.fetchall()

# Group odds by match -> market -> outcome -> source
odds_by_match = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
for o in all_odds:
    if o['odds_value'] and o['odds_value'] > 1.0:
        odds_by_match[o['unified_id']][o['market']][o['outcome']][o['source']] = {
            'odds': o['odds_value'],
            'handicap': o['handicap'],
            'fetch_date': o['fetch_date']
        }

# Process each match
recommendations = []
blacklist = []  # K < -0.05
stats = {
    'total': 0,
    'lambda_from_json': 0,
    'multi_source': 0,
    'xg_available': 0,
    'grades': {'S': 0, 'A': 0, 'B': 0, 'C': 0}
}

# Check understat for xG (by team name matching)
cur.execute("SELECT DISTINCT home_team, away_team FROM understat_matches")
understat_teams = set()
for r in cur.fetchall():
    if r[0]: understat_teams.add(r[0].lower())
    if r[1]: understat_teams.add(r[1].lower())

for m in matches:
    if is_virtual(m['league_name']):
        continue
    
    sport = m['sport_code']
    if sport and sport not in ('football', 'soccer', None, ''):
        continue
    
    uid = m['unified_id']
    league = m['league_name'] or ''
    home = m['home_team_std'] or ''
    away = m['away_team_std'] or ''
    
    # Skip matches with empty team names
    if not home.strip() or not away.strip():
        continue
    
    if uid not in odds_by_match:
        continue
    
    # Get lambda for this league
    lambda_info = league_lambda_map.get(league, None)
    if lambda_info and lambda_info.get('source') != 'default':
        lambda_h = lambda_info.get('avg_hg', DEFAULT_LAMBDA_H)
        lambda_a = lambda_info.get('avg_ag', DEFAULT_LAMBDA_A)
        lambda_source = f"JSON({league})"
        stats['lambda_from_json'] += 1
    else:
        lambda_h = DEFAULT_LAMBDA_H
        lambda_a = DEFAULT_LAMBDA_A
        lambda_source = "全局默认"
    
    # Check xG by matching team names in understat
    has_xg = (home.lower() in understat_teams) and (away.lower() in understat_teams)
    if has_xg:
        stats['xg_available'] += 1
    
    match_odds = odds_by_match[uid]
    
    # For each market+outcome, compute K
    match_k_values = []
    
    for market in match_odds:
        for outcome in match_odds[market]:
            sources = match_odds[market][outcome]
            n_sources = len(sources)
            
            # Get best available odds (highest for back)
            best_odds = max(s['odds'] for s in sources.values())
            
            # Get average odds for book probability
            avg_odds = sum(s['odds'] for s in sources.values()) / n_sources
            
            # P_book from odds (using average)
            if market == 'moneyline' or market == 'spread':
                # For moneyline/spread: P_book = 1/odds normalized
                # We'll use the raw 1/odds as probability (simplified, ignoring margin)
                p_book = 1.0 / avg_odds
            elif market in ('total', 'totals'):
                p_book = 1.0 / avg_odds
            else:
                p_book = 1.0 / avg_odds
            
            # P_poisson
            handicap_for_poisson = None
            # Collect handicap from sources
            for s in sources.values():
                if s['handicap'] is not None:
                    handicap_for_poisson = s['handicap']
                    break
            
            if market == 'moneyline' and outcome in ('home', 'draw', 'away'):
                p_poisson = poisson_prob(lambda_h, lambda_a, outcome)
            elif market in ('total', 'totals') and outcome in ('over', 'under'):
                p_poisson = poisson_prob(lambda_h, lambda_a, outcome, line=handicap_for_poisson)
            elif market == 'spread' and outcome in ('home', 'away'):
                p_poisson = poisson_prob(lambda_h, lambda_a, outcome)
            elif market == 'team_total' and outcome in ('over', 'under'):
                p_poisson = poisson_prob(lambda_h, lambda_a * 0.5 if outcome == 'over' else lambda_a * 0.5, outcome, line=handicap_for_poisson)
            else:
                p_poisson = 0.5
            
            # P_elo ≈ P_book (approximation)
            p_elo = p_book
            
            # P_fusion
            p_fusion = 0.50 * p_book + 0.30 * p_poisson + 0.20 * p_elo
            
            # K value using best odds
            k = calc_k_value(p_fusion, best_odds)
            if k is None:
                continue
            
            k_quarter = k * 0.25
            
            # Get handicap for display (already computed above)
            handicap = handicap_for_poisson
            
            source_names = list(sources.keys())
            
            match_k_values.append({
                'market': market,
                'outcome': outcome,
                'best_odds': best_odds,
                'avg_odds': avg_odds,
                'n_sources': n_sources,
                'source_names': source_names,
                'p_book': p_book,
                'p_poisson': p_poisson,
                'p_elo': p_elo,
                'p_fusion': p_fusion,
                'k': k,
                'k_quarter': k_quarter,
                'handicap': handicap,
                'lambda_source': lambda_source,
                'lambda_h': lambda_h,
                'lambda_a': lambda_a,
                'has_xg': has_xg,
                'league': league,
                'home': home,
                'away': away,
                'uid': uid,
            })
    
    if not match_k_values:
        continue
    
    stats['total'] += 1
    if any(v['n_sources'] >= 2 for v in match_k_values):
        stats['multi_source'] += 1
    
    # Keep only the best K direction per match
    best = max(match_k_values, key=lambda x: x['k'])
    
    # Check blacklist
    if best['k'] < -0.05:
        blacklist.append(best)
        continue
    
    # Classify
    grade = classify_grade(best['k'], best['best_odds'], best['n_sources'])
    if grade is None:
        continue
    
    best['grade'] = grade
    stats['grades'][grade] += 1
    recommendations.append(best)

# Sort by K descending
recommendations.sort(key=lambda x: (-{'S': 0, 'A': 1, 'B': 2, 'C': 3}.get(x['grade'], 9), -x['k']))

# Limit per grade
grade_limits = {'S': 999, 'A': 20, 'B': 10, 'C': 5}
grade_counts = defaultdict(int)
filtered_recs = []
for r in recommendations:
    g = r['grade']
    if grade_counts[g] < grade_limits[g]:
        filtered_recs.append(r)
        grade_counts[g] += 1

recommendations = filtered_recs

# Output direction labels
def outcome_label(market, outcome):
    if market == 'moneyline':
        return {'home': '主胜', 'draw': '平局', 'away': '客胜'}.get(outcome, outcome)
    elif market in ('total', 'totals'):
        return {'over': '大球', 'under': '小球'}.get(outcome, outcome)
    elif market == 'spread':
        return {'home': '主队让球', 'away': '客队让球'}.get(outcome, outcome)
    return f"{market}/{outcome}"

# Build output
output_lines = []
output_lines.append(f"# K值推荐单 - 终版")
output_lines.append(f"生成时间: {now_str}")
output_lines.append(f"")
output_lines.append(f"## 公式")
output_lines.append(f"`p_fusion = 0.50 × P_book + 0.30 × P_poisson + 0.20 × P_elo`")
output_lines.append(f"`K = (p × o - 1) / (o - 1)`")
output_lines.append(f"`K_1/4 = K × 0.25`")
output_lines.append(f"")
output_lines.append(f"---")
output_lines.append(f"")

for grade in ['S', 'A', 'B', 'C']:
    grade_recs = [r for r in recommendations if r['grade'] == grade]
    if not grade_recs:
        continue
    
    output_lines.append(f"## {grade}级推荐 ({len(grade_recs)}场)")
    output_lines.append(f"")
    
    for i, r in enumerate(grade_recs, 1):
        direction = outcome_label(r['market'], r['outcome'])
        handicap_str = ""
        if r['market'] in ('total', 'totals', 'spread') and r['handicap'] is not None:
            handicap_str = f"\n    盘口线: {r['handicap']}"
        
        sources_str = ', '.join(r['source_names'])
        n_src_label = f"{r['n_sources']}源"
        
        output_lines.append(f"{i}. [{r['league']}] {r['home']} vs {r['away']}")
        output_lines.append(f"    → {direction} | 赔率: {r['best_odds']:.2f} | {n_src_label} | Lambda来源: {r['lambda_source']}")
        output_lines.append(f"    P_book={r['p_book']:.3f} P_poisson={r['p_poisson']:.3f} P_elo={r['p_elo']:.3f}(近似) P_fusion={r['p_fusion']:.3f}")
        output_lines.append(f"    K={r['k']:.4f} K_1/4={r['k_quarter']:.4f}")
        if handicap_str:
            output_lines.append(f"    盘口线: {r['handicap']}")
        output_lines.append(f"    来源: {sources_str}")
        output_lines.append(f"")

# Parlay suggestions
s_recs = [r for r in recommendations if r['grade'] == 'S']
a_recs = [r for r in recommendations if r['grade'] == 'A']

output_lines.append(f"---")
output_lines.append(f"")
output_lines.append(f"## 串关建议")
output_lines.append(f"")

if len(s_recs) >= 2:
    output_lines.append(f"### S+S 串关")
    for i in range(0, min(len(s_recs), 5)):
        for j in range(i+1, min(len(s_recs), 6)):
            r1, r2 = s_recs[i], s_recs[j]
            combined_odds = r1['best_odds'] * r2['best_odds']
            d1 = outcome_label(r1['market'], r1['outcome'])
            d2 = outcome_label(r2['market'], r2['outcome'])
            output_lines.append(f"- {r1['home']}vs{r1['away']}({d1}@{r1['best_odds']:.2f}) × {r2['home']}vs{r2['away']}({d2}@{r2['best_odds']:.2f}) = {combined_odds:.2f}")
    output_lines.append(f"")

if len(s_recs) >= 1 and len(a_recs) >= 1:
    output_lines.append(f"### S+A 串关")
    for s in s_recs[:3]:
        for a in a_recs[:3]:
            combined_odds = s['best_odds'] * a['best_odds']
            ds = outcome_label(s['market'], s['outcome'])
            da = outcome_label(a['market'], a['outcome'])
            output_lines.append(f"- {s['home']}vs{s['away']}({ds}@{s['best_odds']:.2f}) × {a['home']}vs{a['away']}({da}@{a['best_odds']:.2f}) = {combined_odds:.2f}")
    output_lines.append(f"")

# Blacklist
output_lines.append(f"## 禁入名单 (K < -0.05)")
output_lines.append(f"")
if blacklist:
    for r in blacklist:
        d = outcome_label(r['market'], r['outcome'])
        output_lines.append(f"- [{r['league']}] {r['home']} vs {r['away']} → {d} @ {r['best_odds']:.2f} K={r['k']:.4f}")
else:
    output_lines.append(f"(无)")
output_lines.append(f"")

# Position allocation
output_lines.append(f"## 仓位分配 (10u预算)")
output_lines.append(f"")
single_budget = round(10 * 0.65, 1)
parlay_budget = round(10 * 0.30, 1)
reserve = round(10 - single_budget - parlay_budget, 1)

output_lines.append(f"- 单关: {single_budget}u (60-70%)")
output_lines.append(f"- 串关: {parlay_budget}u (20-30%)")
output_lines.append(f"- 预留: {reserve}u")

# Per-match allocation for singles
if s_recs:
    per_s = round(single_budget * 0.4 / max(len(s_recs), 1), 2)
    output_lines.append(f"  - S级单场: {per_s}u × {len(s_recs)}场")
if a_recs:
    per_a = round(single_budget * 0.3 / max(len(a_recs), 1), 2)
    output_lines.append(f"  - A级单场: {per_a}u × {min(len(a_recs), 20)}场")
remaining_single = single_budget
if s_recs:
    remaining_single -= round(single_budget * 0.4 / max(len(s_recs), 1), 2) * len(s_recs)
if a_recs:
    remaining_single -= round(single_budget * 0.3 / max(len(a_recs), 1), 2) * min(len(a_recs), 20)
output_lines.append(f"  - B/C级: 共{round(max(remaining_single, 0), 2)}u 分散")
output_lines.append(f"  - 串关分配: 每组串关 {round(parlay_budget / max(len(s_recs), 1), 2)}u")
output_lines.append(f"")

# Statistics
output_lines.append(f"## 统计")
output_lines.append(f"")
output_lines.append(f"- 总场次: {stats['total']}")
output_lines.append(f"- S级: {stats['grades']['S']} | A级: {stats['grades']['A']} | B级: {stats['grades']['B']} | C级: {stats['grades']['C']}")
if stats['total'] > 0:
    output_lines.append(f"- 有联赛历史lambda的场次: {stats['lambda_from_json']} ({stats['lambda_from_json']/stats['total']*100:.1f}%)")
    output_lines.append(f"- 有2+源交叉的场次: {stats['multi_source']} ({stats['multi_source']/stats['total']*100:.1f}%)")
    output_lines.append(f"- 有xG数据的场次: {stats['xg_available']} ({stats['xg_available']/stats['total']*100:.1f}%)")
output_lines.append(f"")

output_text = '\n'.join(output_lines)
print(output_text)

# Save to file
output_path = r'F:\qqsj\推荐单_K值_终版_2026-06-06.md'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(output_text)
print(f"\n已保存到: {output_path}")

conn.close()
