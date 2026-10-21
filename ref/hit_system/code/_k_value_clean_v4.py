#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K值公式推荐单 - 清洁版 v4
日期: 2026-06-06
"""

import sqlite3
import math
from collections import defaultdict
from datetime import datetime

DB_PATH = r'F:\qqsj\data\sports_data.db'
TODAY = '2026-06-06'
OUTPUT_PATH = r'F:\qqsj\推荐单_K值_2026-06-06.md'

# ============================================================
# 1. 连接数据库，加载基础数据
# ============================================================
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# ============================================================
# 2. 加载今日比赛（排除虚拟比赛）
# ============================================================
EXCLUDE_KEYWORDS = ['VS-', '梦幻对垒', 'NBA 2K', 'PANDA独家', 'EAFC']

c.execute("""
    SELECT unified_id, league_name, home_team_std, away_team_std, kickoff_utc
    FROM unified_matches
    WHERE sport_code='football' AND fetch_date=?
""", (TODAY,))
all_matches = [dict(r) for r in c.fetchall()]

# 过滤虚拟比赛
matches = []
for m in all_matches:
    league = m['league_name'] or ''
    skip = False
    for kw in EXCLUDE_KEYWORDS:
        if kw in league:
            skip = True
            break
    if not skip:
        matches.append(m)

print(f"总比赛: {len(all_matches)}, 过滤后: {len(matches)}")

# ============================================================
# 3. 加载今日赔率，按unified_id分组
# ============================================================
c.execute("SELECT unified_id, source, market, outcome, odds_value, handicap FROM unified_odds WHERE fetch_date=?", (TODAY,))
odds_rows = c.fetchall()

odds_by_match = defaultdict(list)
for r in odds_rows:
    odds_by_match[r['unified_id']].append(dict(r))

# ============================================================
# 4. 构建赔率结构：每场比赛 → 各市场 → 各方向的最优赔率
# ============================================================
def build_odds_struct(match_id):
    """构建某场比赛的赔率结构，返回 {market: {outcome: best_odds}}"""
    rows = odds_by_match.get(match_id, [])
    struct = defaultdict(lambda: defaultdict(list))
    for r in rows:
        struct[r['market']][r['outcome']].append(r)
    
    result = {}
    for market, outcomes in struct.items():
        result[market] = {}
        for outcome, entries in outcomes.items():
            # 取最高赔率
            best = max(entries, key=lambda x: x['odds_value'])
            result[market][outcome] = {
                'odds': round(best['odds_value'], 4),
                'source': best['source'],
                'handicap': best['handicap']
            }
    return result

# ============================================================
# 5. Lambda估算：从match_results按联赛查历史场均进球
# ============================================================
c.execute("""
    SELECT league_cn, 
           AVG(CAST(home_score AS FLOAT)) as avg_hg,
           AVG(CAST(away_score AS FLOAT)) as avg_ag,
           COUNT(*) as cnt
    FROM match_results 
    WHERE home_score IS NOT NULL AND away_score IS NOT NULL 
      AND home_score >= 0 AND away_score >= 0
      AND sport='football'
    GROUP BY league_cn
""")
league_lambda = {}
for r in c.fetchall():
    league_lambda[r['league_cn']] = {
        'avg_hg': r['avg_hg'] or 1.45,
        'avg_ag': r['avg_ag'] or 1.15,
        'cnt': r['cnt']
    }

# 联赛名映射：企鹅联赛名 → match_results联赛名（模糊匹配）
def map_league_name(league_name):
    """尝试将企鹅联赛名映射到match_results的联赛名"""
    if not league_name:
        return None
    
    # 直接匹配
    if league_name in league_lambda:
        return league_name
    
    # 去掉后缀尝试匹配
    base = league_name.replace(' - 附加赛', '').replace(' - 季后赛', '').strip()
    if base in league_lambda:
        return base
    
    # 模糊：包含关系
    for k in league_lambda:
        if k in league_name or league_name in k:
            return k
    
    # 关键词映射
    mapping = {
        '英超': '英超', '英冠': '英冠', '英甲': '英甲', '英乙': '英乙',
        '西甲': '西甲', '西乙': '西乙', '意甲': '意甲', '意乙': '意乙',
        '德甲': '德甲', '德乙': '德乙', '法甲': '法甲', '法乙': '法乙',
        '中超': '中超', '中甲': '中甲', '中乙': '中乙',
        '韩K': '韩K联', '日职': '日职联',
        '美职': '美职联', 'MLS': '美职联',
        '巴甲': '巴甲' if '巴甲' in league_lambda else None,
        '阿根廷': '阿甲', '澳超': '澳超', '瑞典': '瑞典超' if '瑞典超' in league_lambda else '瑞典甲',
        '挪威': '挪超', '冰岛': '冰岛超', '芬兰': '芬超' if '芬超' in league_lambda else '芬甲',
        '葡萄牙': '葡超', '荷兰': '荷甲', '土耳其': '土超',
        '智利': '智利丙' if '智利丙' in league_lambda else None,
        '乌拉圭': '乌拉圭乙' if '乌拉圭乙' in league_lambda else None,
        '阿尔及利亚': '阿尔及利亚甲',
        '越南': '越南乙',
        '波兰': '波兰超',
        '奥地利': '奥超',
        '丹麦': '丹麦超', '匈牙利': '匈甲', '希腊': '希腊超',
        '哥伦比亚': '哥伦比亚甲',
        '苏格兰': '苏超', '瑞士': '瑞士超',
        '爱尔兰': '爱尔兰超',
        '俄罗斯': None, '新西兰': '新西兰甲',
        '韩国': '韩K联', '日本': '日职联',
        '巴西': '巴乙' if '巴乙' in league_lambda else None,
    }
    
    for kw, mapped in mapping.items():
        if kw in league_name and mapped and mapped in league_lambda:
            return mapped
    
    return None

# ============================================================
# 6. 加载understat xG数据
# ============================================================
c.execute("SELECT league, team_name, matches, xg, xga, npxg, npxga FROM understat_team_stats")
xg_data = {}
for r in c.fetchall():
    key = (r['league'], r['team_name'])
    if r['matches'] and r['matches'] > 0:
        xg_data[key] = {
            'xg_per_game': (r['xg'] or 0) / r['matches'],
            'xga_per_game': (r['xga'] or 0) / r['matches'],
            'npxg_per_game': (r['npxg'] or 0) / r['matches'],
            'npxga_per_game': (r['npxga'] or 0) / r['matches'],
        }

# understat联赛映射
USTAT_LEAGUES = {
    'EPL': ['英超', '英格兰超级联赛', '英格兰超级'],
    'La Liga': ['西甲', '西班牙甲级联赛'],
    'Serie A': ['意甲', '意大利甲级联赛'],
    'Bundesliga': ['德甲', '德国甲级联赛'],
    'Ligue 1': ['法甲', '法国甲级联赛'],
}

def find_xg(team_name, league_name):
    """尝试在understat中找到匹配的xG数据"""
    results = []
    for (lig, tn), data in xg_data.items():
        if lig not in USTAT_LEAGUES:
            continue
        # 简单匹配：队名包含关系
        if tn.lower() in team_name.lower() or team_name.lower() in tn.lower():
            results.append(data)
        # 常见英文名匹配
    return results[0] if results else None

# ============================================================
# 7. Poisson模型
# ============================================================
def poisson_prob(lambda_h, lambda_a, max_goals=8):
    """计算Poisson概率矩阵"""
    def poisson_pdf(lam, k):
        if lam <= 0:
            return 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    
    p_home = sum(
        sum(poisson_pdf(lambda_h, i) * poisson_pdf(lambda_a, j) for j in range(max_goals))
        for i in range(1, max_goals)
    )
    p_draw = sum(
        poisson_pdf(lambda_h, i) * poisson_pdf(lambda_a, i) for i in range(max_goals)
    )
    p_away = 1.0 - p_home - p_draw
    return max(p_home, 0), max(p_draw, 0), max(p_away, 0)

def poisson_totals(lambda_h, lambda_a, line, max_goals=8):
    """计算大小球概率"""
    def poisson_pdf(lam, k):
        if lam <= 0:
            return 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    
    p_under = 0
    for i in range(max_goals):
        for j in range(max_goals):
            if i + j < line:
                p_under += poisson_pdf(lambda_h, i) * poisson_pdf(lambda_a, j)
    p_over = 1.0 - p_under
    return max(p_over, 0), max(p_under, 0)

# ============================================================
# 8. ELO模型（简化：用赔率隐含概率的保守估计）
# ============================================================
def elo_prob_from_odds(odds_h, odds_d, odds_a):
    """用赔率反推隐含概率作为ELO近似"""
    if not all(x and x > 1 for x in [odds_h, odds_d, odds_a]):
        return None, None, None
    inv_sum = 1/odds_h + 1/odds_d + 1/odds_a
    return 1/(odds_h * inv_sum), 1/(odds_d * inv_sum), 1/(odds_a * inv_sum)

# ============================================================
# 9. 主计算逻辑
# ============================================================
results = []

for match in matches:
    mid = match['unified_id']
    league = match['league_name'] or ''
    home = match['home_team_std'] or ''
    away = match['away_team_std'] or ''
    kickoff = match['kickoff_utc'] or ''
    
    # 获取赔率结构
    odds_struct = build_odds_struct(mid)
    
    # 判断是否有1X2赔率
    ml = odds_struct.get('moneyline', {})
    has_ml = len(ml) >= 3
    
    if not has_ml:
        continue  # 没有胜平负赔率则跳过
    
    # 提取赔率
    o_h = ml.get('home', {}).get('odds')
    o_d = ml.get('draw', {}).get('odds')
    o_a = ml.get('away', {}).get('odds')
    
    if not all(x and x > 1 for x in [o_h, o_d, o_a]):
        continue
    
    # P_book: 赔率隐含概率（去水）
    inv_sum = 1/o_h + 1/o_d + 1/o_a
    p_book_h = (1/o_h) / inv_sum
    p_book_d = (1/o_d) / inv_sum
    p_book_a = (1/o_a) / inv_sum
    
    # Lambda估算
    mapped_league = map_league_name(league)
    lambda_h = 1.45
    lambda_a = 1.15
    lambda_source = '默认'
    
    if mapped_league and mapped_league in league_lambda:
        ll = league_lambda[mapped_league]
        lambda_h = ll['avg_hg']
        lambda_a = ll['avg_ag']
        lambda_source = f'历史({mapped_league}, {ll["cnt"]}场)'
    
    # 尝试xG
    xg_h = find_xg(home, league)
    xg_a = find_xg(away, league)
    if xg_h and xg_a:
        lambda_h = xg_h['xg_per_game']
        lambda_a = xg_a['xga_per_game']  # 用对手的xGA
        lambda_source = 'xG+历史'
    
    # P_poisson
    p_poisson_h, p_poisson_d, p_poisson_a = poisson_prob(lambda_h, lambda_a)
    
    # P_elo (简化用赔率隐含)
    p_elo_h, p_elo_d, p_elo_a = elo_prob_from_odds(o_h, o_d, o_a)
    
    # P_fusion
    p_fusion_h = 0.50 * p_book_h + 0.30 * p_poisson_h + 0.20 * p_elo_h
    p_fusion_d = 0.50 * p_book_d + 0.30 * p_poisson_d + 0.20 * p_elo_d
    p_fusion_a = 0.50 * p_book_a + 0.30 * p_poisson_a + 0.20 * p_elo_a
    
    # K值计算 - 胜平负
    directions = []
    for label, p_f, odds, p_b, p_p, src in [
        ('主胜', p_fusion_h, o_h, p_book_h, p_poisson_h, ml.get('home', {}).get('source', '')),
        ('平局', p_fusion_d, o_d, p_book_d, p_poisson_d, ml.get('draw', {}).get('source', '')),
        ('客胜', p_fusion_a, o_a, p_book_a, p_poisson_a, ml.get('away', {}).get('source', '')),
    ]:
        if odds and odds > 1:
            k = (p_f * odds - 1) / (odds - 1) if odds != 1 else 0
            directions.append({
                'label': label, 'odds': odds, 'p_fusion': p_f, 'p_book': p_b,
                'p_poisson': p_p, 'k': k, 'k_quarter': k * 0.25,
                'source': src, 'line': None
            })
    
    # 大小球
    totals = odds_struct.get('totals', {})
    if 'over' in totals and 'under' in totals:
        o_over = totals['over']['odds']
        o_under = totals['under']['odds']
        hc = totals['over'].get('handicap') or totals['under'].get('handicap')
        
        if o_over and o_under and o_over > 1 and o_under > 1 and hc:
            inv_t = 1/o_over + 1/o_under
            p_book_over = (1/o_over) / inv_t
            p_book_under = (1/o_under) / inv_t
            
            p_p_over, p_p_under = poisson_totals(lambda_h, lambda_a, hc)
            
            # ELO用赔率
            p_elo_over = p_book_over
            p_elo_under = p_book_under
            
            p_f_over = 0.50 * p_book_over + 0.30 * p_p_over + 0.20 * p_elo_over
            p_f_under = 0.50 * p_book_under + 0.30 * p_p_under + 0.20 * p_elo_under
            
            k_over = (p_f_over * o_over - 1) / (o_over - 1) if o_over != 1 else 0
            k_under = (p_f_under * o_under - 1) / (o_under - 1) if o_under != 1 else 0
            
            src_o = totals['over'].get('source', '')
            src_u = totals['under'].get('source', '')
            
            directions.append({
                'label': f'大{hc}', 'odds': o_over, 'p_fusion': p_f_over, 'p_book': p_book_over,
                'p_poisson': p_p_over, 'k': k_over, 'k_quarter': k_over * 0.25,
                'source': src_o, 'line': hc
            })
            directions.append({
                'label': f'小{hc}', 'odds': o_under, 'p_fusion': p_f_under, 'p_book': p_book_under,
                'p_poisson': p_p_under, 'k': k_under, 'k_quarter': k_under * 0.25,
                'source': src_u, 'line': hc
            })
    
    # 亚盘
    spreads = odds_struct.get('spread', {})
    if 'home' in spreads and 'away' in spreads:
        o_sh = spreads['home']['odds']
        o_sa = spreads['away']['odds']
        hc = spreads['home'].get('handicap')
        
        if o_sh and o_sa and o_sh > 1 and o_sa > 1 and hc is not None:
            inv_s = 1/o_sh + 1/o_sa
            p_book_sh = (1/o_sh) / inv_s
            p_book_sa = (1/o_sa) / inv_s
            
            # Poisson估算亚盘概率
            def poisson_spread(lambda_h, lambda_a, hc, max_goals=8):
                def pdf(lam, k):
                    if lam <= 0: return 0.0
                    return math.exp(-lam) * (lam ** k) / math.factorial(k)
                p_home_cover = 0  # 主队赢盘: 主队-客队 > -hc
                for i in range(max_goals):
                    for j in range(max_goals):
                        if i - j > -hc:  # 主队净胜 > 盘口
                            p_home_cover += pdf(lambda_h, i) * pdf(lambda_a, j)
                p_away_cover = 1.0 - p_home_cover
                return max(p_home_cover, 0), max(p_away_cover, 0)
            
            p_p_sh, p_p_sa = poisson_spread(lambda_h, lambda_a, hc)
            
            # P_elo: 用赔率隐含
            p_elo_sh = p_book_sh
            p_elo_sa = p_book_sa
            
            p_f_sh = 0.50 * p_book_sh + 0.30 * p_p_sh + 0.20 * p_elo_sh
            p_f_sa = 0.50 * p_book_sa + 0.30 * p_p_sa + 0.20 * p_elo_sa
            
            k_sh = (p_f_sh * o_sh - 1) / (o_sh - 1) if o_sh != 1 else 0
            k_sa = (p_f_sa * o_sa - 1) / (o_sa - 1) if o_sa != 1 else 0
            
            directions.append({
                'label': f'亚盘主{hc:+.2f}' if hc else '亚盘主',
                'odds': o_sh, 'p_fusion': p_f_sh, 'p_book': p_book_sh,
                'p_poisson': p_p_sh, 'k': k_sh, 'k_quarter': k_sh * 0.25,
                'source': spreads['home'].get('source', ''), 'line': hc
            })
            directions.append({
                'label': f'亚盘客{hc:+.2f}' if hc else '亚盘客',
                'odds': o_sa, 'p_fusion': p_f_sa, 'p_book': p_book_sa,
                'p_poisson': p_p_sa, 'k': k_sa, 'k_quarter': k_sa * 0.25,
                'source': spreads['away'].get('source', ''), 'line': hc
            })
    
    # 每场只保留K最高的方向
    if directions:
        best = max(directions, key=lambda x: x['k'])
        # 统计数据源数（全场级别）
        match_sources = set()
        for r in odds_by_match.get(mid, []):
            if r['source']:
                match_sources.add(r['source'])
        
        best['sources_count'] = len(match_sources)
        best['league'] = league
        best['home'] = home
        best['away'] = away
        best['kickoff'] = kickoff
        best['lambda_source'] = lambda_source
        best['lambda_h'] = lambda_h
        best['lambda_a'] = lambda_a
        
        # 分级
        k = best['k']
        o = best['odds']
        sc = best['sources_count']
        
        if k >= 0.10 and 1.5 <= o <= 3.5 and sc >= 2:
            best['grade'] = 'S'
        elif k >= 0.06 and 1.3 <= o <= 4.0:
            best['grade'] = 'A'
        elif k >= 0.02:
            best['grade'] = 'B'
        elif k > 0:
            best['grade'] = 'C'
        else:
            best['grade'] = '-'
        
        results.append(best)

# 排序：按K值降序
results.sort(key=lambda x: x['k'], reverse=True)

# ============================================================
# 10. 输出
# ============================================================
lines = []
lines.append(f"# 🥔 土豆K值推荐单 — {TODAY}")
lines.append(f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
lines.append(f"> 公式: P_fusion = 0.50×P_book + 0.30×P_poisson + 0.20×P_elo")
lines.append(f"> K = (p×o-1)/(o-1), K_1/4 = K×0.25")
lines.append(f"> Lambda来源: 联赛历史场均进球 > xG > 默认(1.45/1.15)")
lines.append("")

# 分级统计
grades = defaultdict(int)
for r in results:
    if r['grade'] in ('S', 'A', 'B', 'C'):
        grades[r['grade']] += 1

lines.append(f"## 📊 总览")
lines.append(f"- 总场次: **{len(results)}**")
lines.append(f"- S级: {grades['S']} | A级: {grades['A']} | B级: {grades['B']} | C级: {grades['C']}")
lines.append("")

# 按级别输出
for grade in ['S', 'A', 'B', 'C']:
    grade_results = [r for r in results if r['grade'] == grade]
    if not grade_results:
        continue
    
    grade_emoji = {'S': '🔴', 'A': '🟠', 'B': '🟡', 'C': '🟢'}
    lines.append(f"## {grade_emoji.get(grade, '')} {grade}级推荐 ({len(grade_results)}场)")
    lines.append("")
    
    for i, r in enumerate(grade_results, 1):
        lines.append(f"**{i}. [{r['league']}] {r['home']} vs {r['away']}**")
        lines.append(f"  → **{r['label']}** | 赔率: {r['odds']:.2f} | {r['sources_count']}源 | {r['lambda_source']}")
        lines.append(f"  P_book={r['p_book']:.4f}  P_poisson={r['p_poisson']:.4f}  P_fusion={r['p_fusion']:.4f}")
        lines.append(f"  K={r['k']:.4f}  K_¼={r['k_quarter']:.4f}")
        if r['line'] is not None and ('大' in r['label'] or '小' in r['label']):
            lines.append(f"  盘口线: {r['line']}")
        lines.append(f"  λ_h={r['lambda_h']:.3f}  λ_a={r['lambda_a']:.3f}")
        lines.append("")
    lines.append("---")
    lines.append("")

# ============================================================
# 串关建议
# ============================================================
s_list = [r for r in results if r['grade'] == 'S']
a_list = [r for r in results if r['grade'] == 'A']

lines.append("## 🔗 串关建议")
lines.append("")

if len(s_list) >= 2:
    lines.append("### S+S 串关")
    for i in range(min(3, len(s_list))):
        for j in range(i+1, min(5, len(s_list))):
            r1, r2 = s_list[i], s_list[j]
            combo_odds = r1['odds'] * r2['odds']
            lines.append(f"- {r1['home']} vs {r1['away']} **{r1['label']}** ({r1['odds']:.2f}) × "
                        f"{r2['home']} vs {r2['away']} **{r2['label']}** ({r2['odds']:.2f}) "
                        f"= **{combo_odds:.2f}**")
    lines.append("")

if s_list and a_list:
    lines.append("### S+A 串关")
    for i in range(min(2, len(s_list))):
        for j in range(min(3, len(a_list))):
            r1, r2 = s_list[i], a_list[j]
            combo_odds = r1['odds'] * r2['odds']
            lines.append(f"- {r1['home']} vs {r1['away']} **{r1['label']}** ({r1['odds']:.2f}) × "
                        f"{r2['home']} vs {r2['away']} **{r2['label']}** ({r2['odds']:.2f}) "
                        f"= **{combo_odds:.2f}**")
    lines.append("")

# ============================================================
# 禁入名单
# ============================================================
ban_list = [r for r in results if r['k'] < -0.05]
lines.append("## 🚫 禁入名单 (K < -0.05)")
lines.append("")
if ban_list:
    for r in ban_list:
        lines.append(f"- [{r['league']}] {r['home']} vs {r['away']} → {r['label']} K={r['k']:.4f}")
else:
    lines.append("无")
lines.append("")

# ============================================================
# 仓位分配 (10u预算)
# ============================================================
lines.append("## 💰 仓位分配 (总预算10u)")
lines.append("")

total_s = len(s_list)
total_a = len(a_list)
total_b = len([r for r in results if r['grade'] == 'B'])

budget_used = 0
if total_s > 0:
    s_budget = min(total_s * 1.5, 5.0)
    per_s = round(s_budget / total_s, 2)
    lines.append(f"- S级: {total_s}场 × {per_s}u = **{s_budget:.1f}u**")
    budget_used += s_budget

if total_a > 0:
    a_budget = min(total_a * 1.0, 3.0)
    per_a = round(a_budget / total_a, 2)
    lines.append(f"- A级: {total_a}场 × {per_a}u = **{a_budget:.1f}u**")
    budget_used += a_budget

if total_b > 0:
    b_budget = min(10.0 - budget_used, total_b * 0.5)
    per_b = round(b_budget / total_b, 2) if total_b > 0 else 0
    lines.append(f"- B级: {total_b}场 × {per_b}u = **{b_budget:.1f}u**")
    budget_used += b_budget

lines.append(f"- **合计: {min(budget_used, 10.0):.1f}u / 10u**")
lines.append("")

# ============================================================
# 统计
# ============================================================
xg_matches = sum(1 for r in results if 'xG' in r.get('lambda_source', ''))
lines.append("## 📈 统计")
lines.append(f"- 总场次: {len(results)}")
lines.append(f"- S级: {grades['S']} | A级: {grades['A']} | B级: {grades['B']} | C级: {grades['C']}")
lines.append(f"- 有xG数据: {xg_matches}/{len(results)} ({100*xg_matches/max(len(results),1):.1f}%)")
lines.append(f"- 有2+源: {sum(1 for r in results if r['sources_count'] >= 2)}/{len(results)}")
lines.append("")

# 写入文件
output = '\n'.join(lines)
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(output)

print(f"推荐单已写入: {OUTPUT_PATH}")
print(f"总场次: {len(results)}, S:{grades['S']} A:{grades['A']} B:{grades['B']} C:{grades['C']}")

# 打印前20条预览
for i, r in enumerate(results[:20]):
    print(f"{r['grade']} | {r['league'][:8]:8s} | {r['home'][:6]:6s} vs {r['away'][:6]:6s} | {r['label']:8s} | O={r['odds']:.2f} | K={r['k']:.4f}")

conn.close()
