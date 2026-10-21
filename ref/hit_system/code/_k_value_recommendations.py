#!/usr/bin/env python3
"""
基于K值公式标准模板的投注推荐单生成器
=============================================
融合概率: p = 0.50 × P_book + 0.30 × P_poisson + 0.20 × P_elo
K = (p × o - 1) / (o - 1)
K_1/4 = K × 0.25
"""
import sys, sqlite3, json, math, time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TZ_BJ = timezone(timedelta(hours=8))
DB = r'F:\qqsj\data\sports_data.db'
TODAY = datetime.now(TZ_BJ).strftime('%Y-%m-%d')

# ============ 概率模型 ============

def implied_prob(odds_h, odds_d, odds_a):
    """庄家隐含概率 P_book（已去除返还率）"""
    if not all(x and x > 1 for x in [odds_h, odds_d, odds_a]):
        return None, None, None
    raw_h = 1.0 / odds_h
    raw_d = 1.0 / odds_d
    raw_a = 1.0 / odds_a
    margin = raw_h + raw_d + raw_a
    return raw_h / margin, raw_d / margin, raw_a / margin

def poisson_prob(lam_h, lam_a, max_goals=6):
    """泊松模型概率 P_poisson"""
    def p(n, lam):
        return (lam ** n) * math.exp(-lam) / math.factorial(n)
    
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            pi = p(i, lam_h)
            pj = p(j, lam_a)
            if i > j:
                home_win += pi * pj
            elif i == j:
                draw += pi * pj
            else:
                away_win += pi * pj
    return home_win, draw, away_win

def elo_prob(elo_h, elo_a, hfa=65):
    """ELO模型概率 P_elo（含主场优势）"""
    if elo_h is None or elo_a is None:
        return None, None, None
    dr = (elo_h + hfa) - elo_a
    # 足球ELO胜平负（简化版，基于FIDE公式扩展）
    exp_h = 1.0 / (1.0 + 10 ** (-dr / 400.0))
    exp_a = 1.0 - exp_h
    # 简化: 平局概率约 25-28%，按实力差调整
    draw_base = 0.26
    draw_adj = draw_base - abs(dr) / 2000.0
    draw_prob = max(0.15, min(0.35, draw_adj))
    # 归一化
    home_prob = exp_h * (1 - draw_prob)
    away_prob = exp_a * (1 - draw_prob)
    total = home_prob + draw_prob + away_prob
    return home_prob / total, draw_prob / total, away_prob / total

def fusion_prob(p_book, p_poisson, p_elo):
    """融合概率 p = 0.50 × P_book + 0.30 × P_poisson + 0.20 × P_elo"""
    weights = []
    probs = []
    if p_book is not None:
        weights.append(0.50)
        probs.append(p_book)
    if p_poisson is not None:
        w = 0.30 if p_book is not None else 0.50
        weights.append(w)
        probs.append(p_poisson)
    if p_elo is not None:
        remaining = 1.0 - sum(weights)
        if remaining > 0:
            weights.append(remaining)
            probs.append(p_elo)
    if not probs:
        return None
    # 归一化权重
    wsum = sum(weights)
    return sum(w * p for w, p in zip(weights, probs)) / wsum

def kelly(p, o):
    """K = (p × o - 1) / (o - 1)"""
    if p is None or o is None or o <= 1:
        return None
    k = (p * o - 1.0) / (o - 1.0)
    return k

# ============ 数据查询 ============

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
c = conn.cursor()

# 1. 获取今日所有有赔率的足球比赛
print("=" * 70)
print(f"  基于K值公式标准模板 — 投注推荐单")
print(f"  日期: {TODAY}")
print(f"  融合概率: p = 0.50×P_book + 0.30×P_poisson + 0.20×P_elo")
print(f"  K = (p×o - 1)/(o - 1)  |  K_1/4 = K × 0.25")
print("=" * 70)

# 从 unified_matches + unified_odds 获取已统一的数据
# 同时从 qiety_matches/qiety_odds 获取企鹅赔率
# 从 understat 获取 xG
# 从 theodds/pinnacle 获取赔率

# 先获取今日所有有1x2赔率的比赛
c.execute("""
    SELECT DISTINCT 
        um.unified_id, um.home_team_std, um.away_team_std, 
        um.league_name, um.kickoff_utc, um.sport_code,
        um.sources_json
    FROM unified_matches um
    WHERE um.fetch_date = ? AND um.sport_code = 'football'
    AND um.kickoff_utc IS NOT NULL
    ORDER BY um.kickoff_utc
""", (TODAY,))

matches = c.fetchall()
print(f"\n今日统一足球比赛: {len(matches)} 场\n")

# 2. 对每场获取赔率和xG
candidates = []

for m in matches:
    uid = m['unified_id']
    home = m['home_team_std'] or '?'
    away = m['away_team_std'] or '?'
    league = m['league_name'] or '?'
    kickoff = m['kickoff_utc'] or ''
    sources = m['sources_json'] or '{}'
    
    # 获取最佳赔率（取最高赔率作为投注赔率）
    c.execute("""
        SELECT source, market, outcome, odds_value, weight
        FROM unified_odds 
        WHERE unified_id = ? AND fetch_date = ? AND market = 'moneyline'
        AND odds_value > 1.0
    """, (uid, TODAY))
    
    odds_by_outcome = defaultdict(list)
    for o in c.fetchall():
        odds_by_outcome[o['outcome']].append({
            'source': o['source'],
            'odds': o['odds_value'],
            'weight': o['weight'],
        })
    
    # 取各方向最佳赔率
    best_h = max(odds_by_outcome.get('home', []), key=lambda x: x['odds']) if odds_by_outcome.get('home') else None
    best_d = max(odds_by_outcome.get('draw', []), key=lambda x: x['odds']) if odds_by_outcome.get('draw') else None
    best_a = max(odds_by_outcome.get('away', []), key=lambda x: x['odds']) if odds_by_outcome.get('away') else None
    
    if not (best_h and best_d and best_a):
        continue
    
    oh = best_h['odds']
    od = best_d['odds']
    oa = best_a['odds']
    
    # P_book: 庄家隐含概率
    pb_h, pb_d, pb_a = implied_prob(oh, od, oa)
    if pb_h is None:
        continue
    
    # P_poisson: 从xG计算（先查understat）
    # 查主客队 xG
    pp_h, pp_d, pp_a = None, None, None
    
    # 尝试从 qiety_matches 的 source 找 mid，再查 xG
    try:
        src_data = json.loads(sources)
        qiety_mid = src_data.get('qiety_yb', '')
        if qiety_mid:
            # 查 understat 中匹配的比赛 xG
            c.execute("""
                SELECT ux.xg_avg, ux.xga_avg, ts.team_name_std
                FROM understat_team_stats ux
                JOIN team_master ts ON ux.team_id = ts.team_id
                WHERE ts.team_name_std IN (?, ?)
                ORDER BY ux.season DESC LIMIT 2
            """, (home, away))
            xg_rows = c.fetchall()
            if len(xg_rows) >= 2:
                lam_h = xg_rows[0]['xg_avg'] or 1.3
                lam_a = xg_rows[1]['xg_avg'] or 1.1
                pp_h, pp_d, pp_a = poisson_prob(lam_h, lam_a)
    except:
        pass
    
    # 如果没有 xG，用赔率反推泊松参数（fallback）
    if pp_h is None:
        # 从隐含概率反推期望进球
        lam_h = -math.log(max(1 - pb_h + pb_a * 0.3, 0.01))
        lam_a = -math.log(max(1 - pb_a + pb_h * 0.3, 0.01))
        lam_h = max(0.5, min(3.0, lam_h))
        lam_a = max(0.5, min(3.0, lam_a))
        pp_h, pp_d, pp_a = poisson_prob(lam_h, lam_a)
    
    # P_elo: 暂用赔率隐含近似（未来可接真实ELO）
    pe_h, pe_d, pe_a = elo_prob(pb_h * 1500 + 1000, pb_a * 1500 + 1000)
    # ELO fallback: 直接用隐含概率
    if pe_h is None:
        pe_h, pe_d, pe_a = pb_h * 0.95, pb_d * 1.0, pb_a * 0.95
    
    # 融合概率
    pf_h = fusion_prob(pb_h, pp_h, pe_h)
    pf_d = fusion_prob(pb_d, pp_d, pe_d)
    pf_a = fusion_prob(pb_a, pp_a, pe_a)
    
    if pf_h is None:
        continue
    
    # K值计算
    k_h = kelly(pf_h, oh)
    k_d = kelly(pf_d, od)
    k_a = kelly(pf_a, oa)
    
    # 大小球 - 从亚盘/大小球赔率获取
    c.execute("""
        SELECT source, market, outcome, odds_value, handicap
        FROM unified_odds 
        WHERE unified_id = ? AND fetch_date = ? 
        AND market IN ('total', 'spread')
        AND odds_value > 1.0
    """, (uid, TODAY))
    
    totals = defaultdict(list)
    spreads = defaultdict(list)
    for o in c.fetchall():
        if o['market'] == 'total':
            totals[o['outcome']].append({
                'odds': o['odds'],
                'handicap': o['handicap'],
                'source': o['source'],
            })
        elif o['market'] == 'spread':
            spreads[o['outcome']].append({
                'odds': o['odds'],
                'handicap': o['handicap'],
                'source': o['source'],
            })
    
    # 大小球K值
    k_over = None
    k_under = None
    o_over = None
    o_under = None
    total_line = None
    
    best_over = max(totals.get('over', []), key=lambda x: x['odds']) if totals.get('over') else None
    best_under = max(totals.get('under', []), key=lambda x: x['odds']) if totals.get('under') else None
    
    if best_over and best_under:
        o_over = best_over['odds']
        o_under = best_under['odds']
        total_line = best_over['handicap']
        
        # 大小球隐含概率
        to = 1.0 / o_over
        tu = 1.0 / o_under
        tm = to + tu
        pb_over = to / tm
        pb_under = tu / tm
        
        # 泊松大小球概率（基于之前算的lambda）
        if pp_h is not None:
            lam_total = lam_h + lam_a
            # 近似: P(总进球>line)
            p_under_line = 0.0
            for n in range(int(total_line * 2) + 1):
                p_under_line += (lam_total ** n) * math.exp(-lam_total) / math.factorial(n)
            pp_over = 1.0 - p_under_line
            pp_under = p_under_line
        else:
            pp_over = pb_over
            pp_under = pb_under
        
        pf_over = fusion_prob(pb_over, pp_over, pb_over)
        pf_under = fusion_prob(pb_under, pp_under, pb_under)
        
        k_over = kelly(pf_over, o_over)
        k_under = kelly(pf_under, o_under)
    
    # 亚盘K值
    k_ah_h = None
    k_ah_a = None
    ah_line = None
    best_ah_h = max(spreads.get('home', []), key=lambda x: x['odds']) if spreads.get('home') else None
    best_ah_a = max(spreads.get('away', []), key=lambda x: x['odds']) if spreads.get('away') else None
    o_ah_h = None
    o_ah_a = None
    if best_ah_h and best_ah_a:
        o_ah_h = best_ah_h['odds']
        o_ah_a = best_ah_a['odds']
        ah_line = best_ah_h['handicap']
        # 亚盘隐含概率
        ah_margin = 1.0/o_ah_h + 1.0/o_ah_a
        pb_ah_h = (1.0/o_ah_h) / ah_margin
        pb_ah_a = (1.0/o_ah_a) / ah_margin
        # 泊松概率: P(主-客 > handicap)
        if pp_h is not None:
            # 简化: 用胜率差估算
            pp_ah_h = pb_h + pb_d * 0.4 if ah_line and ah_line >= 0 else pb_h * 0.7
            pp_ah_a = pb_a + pb_d * 0.4 if ah_line and ah_line < 0 else pb_a * 0.7
        else:
            pp_ah_h = pb_ah_h
            pp_ah_a = pb_ah_a
        pf_ah_h = fusion_prob(pb_ah_h, pp_ah_h, pb_ah_h)
        pf_ah_a = fusion_prob(pb_ah_a, pp_ah_a, pb_ah_a)
        k_ah_h = kelly(pf_ah_h, o_ah_h)
        k_ah_a = kelly(pf_ah_a, o_ah_a)
    
    # 收集所有方向的K值
    directions = []
    
    if k_h is not None and oh > 1:
        directions.append({
            'dir': f'{home}胜', 'market': '1X2', 'outcome': 'home',
            'odds': oh, 'p_book': pb_h, 'p_poisson': pp_h, 'p_elo': pe_h,
            'p_fusion': pf_h, 'k': k_h, 'k_q': k_h * 0.25,
            'source': best_h['source'],
        })
    if k_d is not None and od > 1:
        directions.append({
            'dir': '平局', 'market': '1X2', 'outcome': 'draw',
            'odds': od, 'p_book': pb_d, 'p_poisson': pp_d, 'p_elo': pe_d,
            'p_fusion': pf_d, 'k': k_d, 'k_q': k_d * 0.25,
            'source': best_d['source'],
        })
    if k_a is not None and oa > 1:
        directions.append({
            'dir': f'{away}胜', 'market': '1X2', 'outcome': 'away',
            'odds': oa, 'p_book': pb_a, 'p_poisson': pp_a, 'p_elo': pe_a,
            'p_fusion': pf_a, 'k': k_a, 'k_q': k_a * 0.25,
            'source': best_a['source'],
        })
    
    if k_over is not None and o_over and o_over > 1:
        directions.append({
            'dir': f'大{total_line}', 'market': 'OU', 'outcome': 'over',
            'odds': o_over, 'p_book': pb_over, 'p_poisson': pp_over, 'p_elo': pb_over,
            'p_fusion': pf_over, 'k': k_over, 'k_q': k_over * 0.25,
            'source': best_over['source'], 'line': total_line,
        })
    if k_under is not None and o_under and o_under > 1:
        directions.append({
            'dir': f'小{total_line}', 'market': 'OU', 'outcome': 'under',
            'odds': o_under, 'p_book': pb_under, 'p_poisson': pp_under, 'p_elo': pb_under,
            'p_fusion': pf_under, 'k': k_under, 'k_q': k_under * 0.25,
            'source': best_under['source'], 'line': total_line,
        })
    
    if k_ah_h is not None and o_ah_h and o_ah_h > 1:
        directions.append({
            'dir': f'{home}({ah_line})', 'market': 'AH', 'outcome': 'home',
            'odds': o_ah_h, 'p_book': pb_ah_h, 'p_fusion': pf_ah_h,
            'k': k_ah_h, 'k_q': k_ah_h * 0.25,
            'source': best_ah_h['source'], 'line': ah_line,
        })
    if k_ah_a is not None and o_ah_a and o_ah_a > 1:
        directions.append({
            'dir': f'{away}({ah_line})', 'market': 'AH', 'outcome': 'away',
            'odds': o_ah_a, 'p_book': pb_ah_a, 'p_fusion': pf_ah_a,
            'k': k_ah_a, 'k_q': k_ah_a * 0.25,
            'source': best_ah_a['source'], 'line': ah_line,
        })
    
    for d in directions:
        d['match'] = f'{home} vs {away}'
        d['league'] = league
        d['kickoff'] = kickoff
        d['unified_id'] = uid

    candidates.extend(directions)

# 3. 筛选: K > 0 的方向（有价值）
positive = [c for c in candidates if c['k'] is not None and c['k'] > 0]
positive.sort(key=lambda x: x['k'], reverse=True)

print(f"总方向数: {len(candidates)} | K>0 有价值: {len(positive)}\n")

# 4. S/A/B/C 分级
S = []  # K >= 0.15, odds 1.5-3.0
A = []  # K >= 0.08
B = []  # K >= 0.03
C = []  # K > 0

for c in positive:
    k = c['k']
    o = c['odds']
    if k >= 0.15 and 1.5 <= o <= 3.0:
        S.append(c)
    elif k >= 0.08:
        A.append(c)
    elif k >= 0.03:
        B.append(c)
    else:
        C.append(c)

# 5. 输出推荐单
print("=" * 70)
print("  📊 基于K值公式 — 足球投注推荐单")
print("=" * 70)

def print_section(title, items, emoji):
    if not items:
        return
    print(f"\n{'─' * 70}")
    print(f"  {emoji} {title} ({len(items)}场)")
    print(f"{'─' * 70}")
    for i, c in enumerate(items[:15]):
        k_q_str = f"{c['k_q']:.4f}" if c['k_q'] is not None else '-'
        p_str = f"{c['p_fusion']:.3f}" if c.get('p_fusion') else '-'
        pb_str = f"{c.get('p_book',0):.3f}" if c.get('p_book') else '-'
        pp_str = f"{c.get('p_poisson',0):.3f}" if c.get('p_poisson') else '-'
        print(f"  {i+1:2}. [{c['league'][:10]:10}] {c['match'][:22]:22}")
        print(f"      方向: {c['dir']:18} | 赔率: {c['odds']:.2f}")
        print(f"      P_book={pb_str} P_poisson={pp_str} P_fusion={p_str}")
        print(f"      K={c['k']:.4f} | K_1/4={k_q_str}")
        print(f"      赔率来源: {c['source']}")
        if c.get('line'):
            print(f"      盘口线: {c['line']}")
        print()

print_section("S级 主仓单关", S, "🔴")
print_section("A级 次主仓", A, "🟠")
print_section("B级 补充参考", B, "🟡")
print_section("C级 仅观察", C, "⚪")

# 6. 串关建议
print(f"\n{'═' * 70}")
print(f"  📋 串关建议")
print(f"{'═' * 70}")

if len(S) >= 2:
    s_pair = S[:2]
    combo_odds = s_pair[0]['odds'] * s_pair[1]['odds']
    print(f"\n  S+S 2串一:")
    for s in s_pair:
        print(f"    {s['match']} → {s['dir']} @ {s['odds']:.2f} (K={s['k']:.4f})")
    print(f"    组合赔率: {combo_odds:.2f}")

if len(S) >= 1 and len(A) >= 1:
    sa_pair = [S[0], A[0]]
    combo_odds = sa_pair[0]['odds'] * sa_pair[1]['odds']
    print(f"\n  S+A 2串一:")
    for s in sa_pair:
        print(f"    {s['match']} → {s['dir']} @ {s['odds']:.2f} (K={s['k']:.4f})")
    print(f"    组合赔率: {combo_odds:.2f}")

# 7. 禁入名单
print(f"\n{'═' * 70}")
print(f"  🚫 禁入/降级名单")
print(f"{'═' * 70}")
negative = [c for c in candidates if c['k'] is not None and c['k'] < -0.05]
for c in sorted(negative, key=lambda x: x['k'])[:10]:
    print(f"  {c['match'][:25]:25} | {c['dir']:15} | K={c['k']:.4f} | 赔率={c['odds']:.2f}")

# 8. 统计
print(f"\n{'═' * 70}")
print(f"  📈 统计")
print(f"{'═' * 70}")
print(f"  总方向: {len(candidates)}")
print(f"  K>0 有价值: {len(positive)}")
print(f"  S级: {len(S)} | A级: {len(A)} | B级: {len(B)} | C级: {len(C)}")
print(f"  K<0 方向: {len(negative)}")

# 9. 仓位分配建议（10u预算）
print(f"\n{'═' * 70}")
print(f"  💰 仓位分配建议（10u 总预算）")
print(f"{'═' * 70}")
s_count = min(len(S), 2)
a_count = min(len(A), 2)
s_u = min(3.0, 10.0 / max(s_count + a_count * 0.5, 1)) if s_count else 0
a_u = s_u * 0.5 if a_count else 0
parlay_u = 2.0 if (s_count >= 1 or a_count >= 1) else 0
used = s_count * s_u + a_count * a_u + parlay_u
remaining = max(0, 10.0 - used)

if s_count:
    print(f"  S级单关 ×{s_count}: {s_u:.1f}u/场 × {s_count} = {s_count*s_u:.1f}u")
if a_count:
    print(f"  A级单关 ×{a_count}: {a_u:.1f}u/场 × {a_count} = {a_count*a_u:.1f}u")
if parlay_u:
    print(f"  2串一: {parlay_u:.1f}u")
print(f"  合计: {used:.1f}u / 10u")
print(f"\n  注: 每场 K_1/4 为该方向建议仓位比例")
for s in S[:5]:
    print(f"    {s['dir']:15} K_1/4={s['k_q']:.4f} → 建议投{s['k_q']*100:.1f}%资金")

conn.close()
print(f"\n{'═' * 70}")
print(f"  概率口径: p = 0.50×P_book + 0.30×P_poisson + 0.20×P_elo")
print(f"  K值公式: K = (p×o - 1)/(o - 1)")
print(f"  缩放: K_1/4 = K × 0.25")
print(f"{'═' * 70}")
