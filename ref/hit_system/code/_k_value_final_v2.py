#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K值推荐单终版 v2 修复 - 2026-06-06
修复: 篮球poisson范围, 联赛λ匹配, 队名映射
"""

import sys, os, json, math, re, sqlite3
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ========== 配置 ==========
DB_PATH = r'F:\qqsj\data\sports_data.db'
OUTPUT_PATH = r'F:\qqsj\推荐单_K值_终版v2_2026-06-06.md'
BASE_DIR = r'F:\qqsj'
TODAY = '2026-06-06'
NOW = datetime.now()

# ========== 泊松分布（不用scipy） ==========
def poisson_pmf(k, lam):
    """手写泊松概率质量函数"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    if k > 300:
        return 0.0
    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except (OverflowError, ValueError):
        # 用Gamma近似极值
        return 0.0

# 预计算阶乘缓存
_fact_cache = {}
def _get_fact(n):
    if n in _fact_cache:
        return _fact_cache[n]
    result = 1.0
    for i in range(1, n + 1):
        result *= i
    _fact_cache[n] = result
    return result

def poisson_pmf_fast(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    if k > 300:
        return 0.0
    try:
        return math.exp(-lam) * (lam ** k) / _get_fact(k)
    except:
        return 0.0

def poisson_prob_matrix(lam_h, lam_a, max_range):
    """计算泊松比分概率矩阵 (0 to max_range)"""
    # 只计算有意义的部分
    h_mean = lam_h
    a_mean = lam_a
    # 计算到 lam + 5*sigma
    h_max = min(max_range, int(h_mean + 5 * math.sqrt(max(h_mean, 1))))
    a_max = min(max_range, int(a_mean + 5 * math.sqrt(max(a_mean, 1))))
    h_max = max(h_max, int(max_range * 0.3))
    a_max = max(a_max, int(max_range * 0.3))
    
    prob = {}
    for i in range(h_max + 1):
        pi = poisson_pmf_fast(i, lam_h)
        if pi < 1e-10 and i > h_mean + 10:
            continue
        for j in range(a_max + 1):
            pj = poisson_pmf_fast(j, lam_a)
            if pj < 1e-10 and j > a_mean + 10:
                continue
            prob[(i, j)] = pi * pj
    return prob

def calc_poisson_probs(lam_h, lam_a, sport='football', line=None, market='1x2'):
    """从泊松矩阵计算胜平负/大小球概率"""
    if sport == 'basketball':
        max_range = 250
    else:
        max_range = 10
    
    matrix = poisson_prob_matrix(lam_h, lam_a, max_range)
    
    if sport == 'football':
        p_home = sum(p for (i, j), p in matrix.items() if i > j)
        p_draw = sum(p for (i, j), p in matrix.items() if i == j)
        p_away = sum(p for (i, j), p in matrix.items() if i < j)
        
        total = p_home + p_draw + p_away
        if total > 0:
            p_home /= total
            p_draw /= total
            p_away /= total
    else:
        # 篮球：直接算主客胜从lambda比例
        total_lam = lam_h + lam_a
        p_home = lam_h / total_lam if total_lam > 0 else 0.5
        p_draw = 0.0
        p_away = lam_a / total_lam if total_lam > 0 else 0.5
    
    result = {'home': p_home, 'draw': p_draw, 'away': p_away}
    
    # 大小球
    if line is not None:
        p_over = sum(p for (i, j), p in matrix.items() if i + j > line)
        p_under = sum(p for (i, j), p in matrix.items() if i + j < line)
        total_ou = p_over + p_under
        if total_ou > 1e-10:
            p_over /= total_ou
            p_under /= total_ou
        else:
            p_over = 0.5
            p_under = 0.5
        result['over'] = p_over
        result['under'] = p_under
    
    return result

# ========== 解析盘口线 ==========
def parse_handicap_line(line_str):
    if line_str is None:
        return None
    line_str = str(line_str).strip()
    try:
        if '/' in line_str:
            parts = line_str.split('/')
            vals = []
            for p in parts:
                p_clean = p.strip().replace('−', '-')
                if p_clean == '' or p_clean == '-':
                    continue
                vals.append(float(p_clean))
            if vals:
                return sum(vals) / len(vals)
        return float(line_str.replace('−', '-'))
    except:
        return None

# ========== 队名匹配工具 ==========
def fast_normalize(name):
    """快速标准化队名"""
    return re.sub(r'[\(\)（）\s\-\.&,]+', '', name).lower().strip()

# 已知队名映射（中文→英文常用名）
KNOWN_TEAMS = {
    '皇马': 'Real Madrid', '皇家马德里': 'Real Madrid',
    '巴萨': 'Barcelona', '巴塞罗那': 'Barcelona',
    '马竞': 'Atletico', '马德里竞技': 'Atletico',
    '拜仁': 'Bayern', '拜仁慕尼黑': 'Bayern',
    '多特': 'Dortmund', '多特蒙德': 'Dortmund',
    '曼城': 'Man City', '曼彻斯特城': 'Man City',
    '曼联': 'Man United', '曼彻斯特联': 'Man United',
    '利物浦': 'Liverpool',
    '阿森纳': 'Arsenal',
    '切尔西': 'Chelsea',
    '热刺': 'Tottenham', '托特纳姆热刺': 'Tottenham',
    '巴黎': 'Paris SG', '巴黎圣日耳曼': 'Paris SG',
    '尤文': 'Juventus', '尤文图斯': 'Juventus',
    '国米': 'Inter', '国际米兰': 'Inter',
    '米兰': 'Milan', 'AC米兰': 'Milan',
    '那不勒斯': 'Napoli',
    '罗马': 'Roma',
    '拉齐奥': 'Lazio',
    '亚特兰大': 'Atalanta',
    '莱比锡': 'Leipzig', 'RB莱比锡': 'Leipzig',
    '勒沃库森': 'Leverkusen',
    '多德勒支': 'Dordrecht',
    '莫斯科斯巴达': 'Spartak M',
    '莫斯科火车头': 'Lokomotiv M',
    '莫斯科中央陆军': 'CSKA',
    '莫斯科迪纳摩': 'Dinamo Mosc',
    '泽尼特': 'Zenit',
    '克拉斯诺达尔': 'Krasnodar',
    '阿贾克斯': 'Ajax',
    '埃因霍温': 'PSV',
    '费耶诺德': 'Feyenoord',
    '本菲卡': 'Benfica',
    '波尔图': 'Porto',
    '阿尔克马尔': 'AZ',
}

# 国家队名映射
NAT_MAP = {
    '白俄罗斯': 'Belarus', '格鲁吉亚': 'Georgia', '斯洛伐克': 'Slovakia',
    '黑山': 'Montenegro', '圣马力诺': 'San Marino', '孟加拉国': 'Bangladesh',
    '摩尔多瓦': 'Moldova', '保加利亚': 'Bulgaria', '俄罗斯': 'Russia',
    '布基纳法索': 'Burkina Faso', '卡塔尔': 'Qatar', '沙特阿拉伯': 'Saudi Arabia',
    '伊朗': 'Iran', '伊拉克': 'Iraq', '阿联酋': 'UAE', '阿曼': 'Oman',
    '科威特': 'Kuwait', '巴林': 'Bahrain', '叙利亚': 'Syria',
    '黎巴嫩': 'Lebanon', '约旦': 'Jordan', '日本': 'Japan',
    '韩国': 'Korea Republic', '朝鲜': 'Korea DPR', '中国': 'China',
    '澳大利亚': 'Australia', '新西兰': 'New Zealand',
    '乌兹别克斯坦': 'Uzbekistan', '塔吉克斯坦': 'Tajikistan',
    '土库曼斯坦': 'Turkmenistan', '吉尔吉斯斯坦': 'Kyrgyzstan',
    '越南': 'Vietnam', '泰国': 'Thailand', '印度尼西亚': 'Indonesia',
    '马来西亚': 'Malaysia', '新加坡': 'Singapore', '菲律宾': 'Philippines',
    '缅甸': 'Myanmar', '印度': 'India', '尼泊尔': 'Nepal',
    '法国': 'France', '德国': 'Germany', '意大利': 'Italy',
    '西班牙': 'Spain', '英格兰': 'England', '荷兰': 'Netherlands',
    '葡萄牙': 'Portugal', '比利时': 'Belgium', '克罗地亚': 'Croatia',
    '塞尔维亚': 'Serbia', '波黑': 'Bosnia', '黑山': 'Montenegro',
    '斯洛文尼亚': 'Slovenia', '北马其顿': 'Macedonia',
    '奥地利': 'Austria', '瑞士': 'Switzerland', '丹麦': 'Denmark',
    '瑞典': 'Sweden', '挪威': 'Norway', '芬兰': 'Finland',
    '冰岛': 'Iceland', '爱尔兰': 'Ireland', '苏格兰': 'Scotland',
    '威尔士': 'Wales', '北爱尔兰': 'Northern Ireland',
    '希腊': 'Greece', '土耳其': 'Turkey', '塞浦路斯': 'Cyprus',
    '以色列': 'Israel', '捷克': 'Czechia', '匈牙利': 'Hungary',
    '罗马尼亚': 'Romania', '波兰': 'Poland', '乌克兰': 'Ukraine',
    '阿尔巴尼亚': 'Albania', '阿塞拜疆': 'Azerbaijan',
    '亚美尼亚': 'Armenia', '爱沙尼亚': 'Estonia', '拉脱维亚': 'Latvia',
    '立陶宛': 'Lithuania', '卢森堡': 'Luxembourg', '马耳他': 'Malta',
    '安道尔': 'Andorra', '列支敦士登': 'Liechtenstein',
    '直布罗陀': 'Gibraltar', '法罗群岛': 'Faroe Islands',
    '科索沃': 'Kosovo', '哈萨克斯坦': 'Kazakhstan',
    '埃及': 'Egypt', '阿尔及利亚': 'Algeria', '摩洛哥': 'Morocco',
    '突尼斯': 'Tunisia', '尼日利亚': 'Nigeria', '塞内加尔': 'Senegal',
    '加纳': 'Ghana', '喀麦隆': 'Cameroon', '南非': 'South Africa',
    '马里': 'Mali', '刚果': 'Congo', '赞比亚': 'Zambia',
    '津巴布韦': 'Zimbabwe', '安哥拉': 'Angola',
    '墨西哥': 'Mexico', '阿根廷': 'Argentina', '巴西': 'Brazil',
    '乌拉圭': 'Uruguay', '哥伦比亚': 'Colombia', '智利': 'Chile',
    '秘鲁': 'Peru', '厄瓜多尔': 'Ecuador', '巴拉圭': 'Paraguay',
    '委内瑞拉': 'Venezuela', '玻利维亚': 'Bolivia',
    '哥斯达黎加': 'Costa Rica', '洪都拉斯': 'Honduras', '巴拿马': 'Panama',
    '牙买加': 'Jamaica', '萨尔瓦多': 'El Salvador',
    '加拿大': 'Canada', '古巴': 'Cuba',
    '佛得角共和国': 'Cape Verde',
}

# ========== 数据加载 ==========
def load_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. 加载今日企鹅比赛
    cur.execute("""
        SELECT * FROM qiety_matches 
        WHERE fetch_date = ?
        AND sport_code IN ('football', 'basketball')
        AND status = 'pre'
    """, (TODAY,))
    matches = [dict(r) for r in cur.fetchall()]
    print(f"📊 加载比赛: {len(matches)} 场")
    
    # 2. 加载企鹅赔率
    cur.execute("SELECT * FROM qiety_odds WHERE fetch_date = ?", (TODAY,))
    odds_rows = [dict(r) for r in cur.fetchall()]
    odds_by_match = defaultdict(lambda: {'1x2': [], 'ah': [], 'ou': []})
    for row in odds_rows:
        mt = row.get('market_type', '')
        if mt in ('1x2', 'ah', 'ou'):
            odds_by_match[row['match_id']][mt].append(row)
    print(f"📊 加载赔率: {len(odds_rows)} 条")
    
    # 3. understat xG
    cur.execute("SELECT * FROM understat_team_stats")
    understat = {}
    for r in cur.fetchall():
        d = dict(r)
        understat[d['team_name'].lower()] = d
    print(f"📊 加载understat xG: {len(understat)} 队")
    
    # 4. football_xg_stats
    cur.execute("SELECT * FROM football_xg_stats")
    xg_stats = defaultdict(dict)
    for r in cur.fetchall():
        d = dict(r)
        xg_stats[d['league'].lower()][d['team'].lower()] = d
    print(f"📊 加载football_xg_stats: {sum(len(v) for v in xg_stats.values())} 条")
    
    # 5. club_elo
    cur.execute("SELECT * FROM club_elo")
    club_elo = {}
    for r in cur.fetchall():
        d = dict(r)
        club_elo[d['team_name'].lower()] = d
    print(f"📊 加载club_elo: {len(club_elo)} 队")
    
    # 6. national_team_elo
    cur.execute("SELECT * FROM national_team_elo")
    nt_elo = {}
    for r in cur.fetchall():
        d = dict(r)
        nt_elo[d['team_name'].lower()] = d
    print(f"📊 加载national_team_elo: {len(nt_elo)} 队")
    
    # 7. 联赛λ
    try:
        with open(os.path.join(BASE_DIR, '_league_lambda_map.json'), 'r', encoding='utf-8') as f:
            league_lambda = json.load(f)
        print(f"📊 加载联赛λ: {len(league_lambda)} 项")
    except:
        league_lambda = {}
        print("⚠️ 联赛λ文件未找到")
    
    # 8. 队名映射
    try:
        with open(os.path.join(BASE_DIR, '_team_cn_en_map.json'), 'r', encoding='utf-8') as f:
            team_cn_en = json.load(f)
        print(f"📊 加载队名映射: {len(team_cn_en)} 项")
    except:
        team_cn_en = {}
    
    # 9. football_team_stats 联赛均值
    cur.execute("SELECT league, AVG(avg_scored) as avg_gf FROM football_team_stats WHERE avg_scored>0 GROUP BY league")
    league_avg_goals = {r['league'].lower(): r['avg_gf'] for r in cur.fetchall()}
    print(f"📊 联赛进球均值: {len(league_avg_goals)} 项")
    
    # 10. 加载hit_recommendations最近的多源信息
    cur.execute("""
        SELECT league_name, home_team, away_team, quality_tier, model_prob, best_odds
        FROM hit_recommendations
        WHERE fetch_date = ?
    """, (TODAY,))
    hit_recs = [dict(r) for r in cur.fetchall()]
    print(f"📊 加载hit_recommendations: {len(hit_recs)} 条")
    
    conn.close()
    
    return {
        'matches': matches,
        'odds_by_match': odds_by_match,
        'understat': understat,
        'xg_stats': xg_stats,
        'club_elo': club_elo,
        'nt_elo': nt_elo,
        'league_lambda': league_lambda,
        'team_cn_en': team_cn_en,
        'league_avg_goals': league_avg_goals,
        'hit_recs': hit_recs,
    }

# ========== 转换中文队名 ==========
def cn_to_en_name(cn_name, team_cn_en):
    """尽量把中文队名转英文"""
    # 1. 直接查映射文件
    if cn_name in team_cn_en:
        entry = team_cn_en[cn_name]
        if isinstance(entry, dict) and entry.get('en'):
            return entry['en']
        elif isinstance(entry, str):
            return entry
    
    # 2. 查已知映射
    if cn_name in KNOWN_TEAMS:
        return KNOWN_TEAMS[cn_name]
    
    # 3. 对于国家队（直接翻译）
    if cn_name in NAT_MAP:
        return NAT_MAP[cn_name]
    
    # 4. 对于含U21/U20/U23/U19/女等后缀
    for suffix in ['U21', 'U20', 'U23', 'U19']:
        if cn_name.endswith(suffix):
            base = cn_name[:-len(suffix)]
            base_en = None
            if base in NAT_MAP:
                base_en = NAT_MAP[base]
            elif base in team_cn_en:
                entry = team_cn_en[base]
                if isinstance(entry, dict) and entry.get('en'):
                    base_en = entry['en']
                elif isinstance(entry, str):
                    base_en = entry
            if base_en:
                return f"{base_en} {suffix}"
    
    # 5. (女) 后缀
    if '(女)' in cn_name or '（女）' in cn_name:
        base = cn_name.replace('(女)', '').replace('（女）', '')
        base_en = None
        if base in NAT_MAP:
            base_en = NAT_MAP[base]
        elif base in team_cn_en:
            entry = team_cn_en[base]
            if isinstance(entry, dict) and entry.get('en'):
                base_en = entry['en']
        if base_en:
            return f"{base_en} W"
    
    # 6. 部分匹配 (前缀/子串)
    for cn_key, en_val in KNOWN_TEAMS.items():
        if cn_key in cn_name and len(cn_key) >= 2:
            return en_val
    
    return cn_name

# ========== ELO查找 ==========
def find_elo(team_en, elo_dict):
    """在ELO表中查找球队"""
    clean = fast_normalize(team_en)
    
    # 直接匹配
    if clean in elo_dict:
        return elo_dict[clean]
    if team_en.lower() in elo_dict:
        return elo_dict[team_en.lower()]
    
    # 部分匹配
    for name, data in elo_dict.items():
        if clean in name or name in clean:
            return data
    
    # 单词重叠
    words = clean.split()
    if len(words) >= 2:
        for name, data in elo_dict.items():
            name_parts = name.split()
            common = sum(1 for w in words if w in name_parts)
            if common >= len(words) * 0.5:
                return data
    
    return None

# ========== P_book ==========
def get_p_book(odds_row, sport='football'):
    oh = odds_row.get('odds_home', 0) or 0
    od = odds_row.get('odds_draw', 0) if sport == 'football' else None
    oa = odds_row.get('odds_away', 0) or 0
    
    if oh <= 0 or oa <= 0:
        return None
    
    if sport == 'basketball' or od is None or od <= 0:
        imp_h = 1.0 / oh
        imp_a = 1.0 / oa
        total = imp_h + imp_a
        if total > 0:
            return {'home': imp_h / total, 'draw': 0.0, 'away': imp_a / total}
        return None
    
    imp_h = 1.0 / oh
    imp_d = 1.0 / od
    imp_a = 1.0 / oa
    total = imp_h + imp_d + imp_a
    if total > 0:
        return {'home': imp_h / total, 'draw': imp_d / total, 'away': imp_a / total}
    return None

def get_p_book_ou(ou_row):
    over = ou_row.get('over_odds', 0) or 0
    under = ou_row.get('under_odds', 0) or 0
    if over <= 0 or under <= 0:
        return None
    imp_o = 1.0 / over
    imp_u = 1.0 / under
    total = imp_o + imp_u
    if total > 0:
        return {'over': imp_o / total, 'under': imp_u / total}
    return None

# ========== P_elo ==========
def get_p_elo(home_en, away_en, sport, league, data):
    club_elo = data['club_elo']
    nt_elo = data['nt_elo']
    
    is_national = any(kw in (league or '') for kw in [
        '国际友谊', '世界杯', '欧洲杯', '亚洲杯', '非洲杯', '美洲杯',
        '欧国联', '国家联赛', '资格赛', '预选赛', 'U21', 'U20', 'U19',
        'U23', '巴提杯', '土伦杯', '女子世界杯', '女子欧洲', '南美洲足协'
    ])
    
    if is_national or sport != 'football':
        elo_h = find_elo(home_en, nt_elo)
        elo_a = find_elo(away_en, nt_elo)
        elo_source = 'national_team_elo'
    else:
        elo_h = find_elo(home_en, club_elo)
        elo_a = find_elo(away_en, club_elo)
        elo_source = 'club_elo'
    
    if elo_h is None or elo_a is None:
        # 尝试反向查询
        if not is_national:
            elo_h2 = find_elo(home_en, nt_elo)
            elo_a2 = find_elo(away_en, nt_elo)
            if elo_h2 and elo_a2:
                elo_h, elo_a = elo_h2, elo_a2
                elo_source = 'national_team_elo(fallback)'
        if elo_h is None or elo_a is None:
            return None, '无ELO数据'
    
    rating_h = elo_h['elo_rating']
    rating_a = elo_a['elo_rating']
    
    e_home = 1.0 / (1.0 + 10.0 ** ((rating_a - rating_h) / 400.0))
    
    if sport == 'football':
        diff = rating_h - rating_a
        p_draw_base = max(0.10, min(0.35, 0.26 - abs(diff) * 0.0004))
        p_home = e_home * (1.0 - p_draw_base)
        p_away = (1.0 - e_home) * (1.0 - p_draw_base)
        p_draw = p_draw_base
        total = p_home + p_draw + p_away
        if total > 0:
            return {
                'home': p_home / total,
                'draw': p_draw / total,
                'away': p_away / total,
                'elo_home': rating_h,
                'elo_away': rating_a,
                'source': elo_source,
                'team_h': elo_h.get('team_name', '?'),
                'team_a': elo_a.get('team_name', '?'),
            }, '真实'
        return None, '计算错误'
    else:
        return {
            'home': e_home,
            'draw': 0,
            'away': 1.0 - e_home,
            'elo_home': rating_h,
            'elo_away': rating_a,
            'source': elo_source,
            'team_h': elo_h.get('team_name', '?'),
            'team_a': elo_a.get('team_name', '?'),
        }, '真实'

# ========== P_poisson ==========
def get_league_lambda_fast(league, data):
    """快速获取联赛lambda"""
    league_lambda = data['league_lambda']
    
    # 精确匹配
    if league in league_lambda:
        d = league_lambda[league]
        if isinstance(d, dict):
            hg = d.get('avg_hg', d.get('avg_home', 1.45))
            ag = d.get('avg_ag', d.get('avg_away', 1.15))
            return float(hg), float(ag), f"联赛λ({league}:{(float(hg)+float(ag)):.2f})"
    
    # 模糊匹配
    league_keywords = {
        '国际友谊': '国际友谊赛',
        '芬兰': '芬兰甲级联赛' if '甲级' in league else '芬兰乙级联赛' if '乙级' in league else '芬兰丙级联赛' if '丙级' in league else '芬兰丁级联赛' if '丁级' in league else None,
        '瑞典': '瑞典乙级联赛' if '乙级' in league else '瑞典北部甲级联赛' if '北部甲级' in league else '瑞典南部甲级联赛' if '南部甲级' in league else None,
        '冰岛': '冰岛甲级联赛' if '甲级' in league else '冰岛乙级联赛' if '乙级' in league else '冰岛丙级联赛' if '丙级' in league else '冰岛丁级联赛' if '丁级' in league else None,
        '挪威': '挪威丙级联赛' if '丙级' in league else '挪威杯资格赛' if '杯' in league else None,
        '丹麦': '丹麦乙级联赛' if '乙级' in league else '丹麦丙级联赛' if '丙级' in league else '丹麦丁级联赛' if '丁级' in league else None,
        '奥地利': '奥地利丙级联赛' if '丙级' in league else '奥地利丁级联赛' if '丁级' in league else None,
        '捷克': '捷克丙级联赛' if '丙级' in league else '捷克丁级联赛' if '丁级' in league else None,
        '荷兰': '荷兰丙级联赛' if '丙级' in league else None,
        '波兰': '波兰乙级联赛' if '乙级' in league else None,
        '爱沙尼亚': '爱沙尼亚丙级联赛' if '丙级' in league else None,
        '越南': '越南乙级联赛' if '乙级' in league else None,
        '日本J1': '日本J1百年愿景联赛' if 'J1' in league else None,
        '日本J2': '日本J2 & J3百年愿景联赛' if 'J2' in league or 'J3' in league else None,
        '日本女子': '日本女子甲级联赛' if '女子' in league else None,
        '韩国K2': '韩国K2联赛' if 'K2' in league else None,
        '韩国K3': '韩国K3联赛' if 'K3' in league else None,
        '韩国K4': '韩国K4联赛' if 'K4' in league else None,
        '中国乙级': '中国乙级联赛' if '乙级' in league else None,
        '阿尔及利亚': '阿尔及利亚甲级联赛',
        '巴拉圭乙级': '巴拉圭乙级联赛' if '乙级' in league else None,
        '巴西乙级': '巴西乙级联赛' if '乙级' in league else None,
        '厄瓜多尔乙级': '厄瓜多尔乙级联赛' if '乙级' in league else None,
        '乌拉圭乙级': '乌拉圭乙级联赛' if '乙级' in league else None,
        '乌拉圭甲级': '乌拉圭甲级联赛' if '甲级' in league else None,
        '阿根廷': '阿根廷乙级曼特波里顿联赛' if '乙级' in league else '阿根廷全国联赛' if '全国' in league else None,
        '智利乙级': '智利乙级联赛' if '乙级' in league else None,
        '智利全国': '智利全国联赛' if '全国' in league else None,
        '智利联赛杯': '智利联赛杯' if '杯' in league else None,
        '哥斯达黎加': '哥斯达黎加超级联赛',
        '加拿大': '加拿大超级联赛',
        '爱尔兰': '爱尔兰伦斯特高级联赛',
        '津巴布韦': '津巴布韦超级联赛',
        '马里': '马里超级联赛',
        '缅甸': '缅甸全国联赛U20',
    }
    
    for kw, mapped in league_keywords.items():
        if kw in league:
            if mapped and mapped in league_lambda:
                d = league_lambda[mapped]
                if isinstance(d, dict):
                    hg = d.get('avg_hg', 1.45)
                    ag = d.get('avg_ag', 1.15)
                    return float(hg), float(ag), f"联赛λ({mapped}:{(float(hg)+float(ag)):.2f})"
    
    return 1.45, 1.15, "全局默认(1.45/1.15)"

def get_xg_lambda(home_en, away_en, data):
    """从xG数据获取lambda"""
    understat = data['understat']
    xg_stats = data['xg_stats']
    
    home_lower = home_en.lower().strip()
    away_lower = away_en.lower().strip()
    
    # 1. understat (top 6 leagues)
    if home_lower in understat and away_lower in understat:
        hd = understat[home_lower]
        ad = understat[away_lower]
        mh = hd.get('matches', 38)
        ma = ad.get('matches', 38)
        if mh > 0 and ma > 0:
            hxg = hd['xg'] / mh
            hxga = hd['xga'] / mh
            axg = ad['xg'] / ma
            axga = ad['xga'] / ma
            lam_h = (hxg + axga) / 2
            lam_a = (axg + hxga) / 2
            return lam_h, lam_a, f"understat_xG({hd['team_name']})"
    
    # 2. football_xg_stats
    for lg, teams in xg_stats.items():
        if home_lower in teams and away_lower in teams:
            hxg = teams[home_lower]
            axg = teams[away_lower]
            lam_h = (hxg['xg_off'] + axg['xg_def']) / 2
            lam_a = (axg['xg_off'] + hxg['xg_def']) / 2
            return lam_h, lam_a, f"football_xg_stats({lg})"
    
    return None, None, None

def get_p_poisson(home_en, away_en, sport, league, market, line_val, data):
    if sport == 'basketball':
        return get_p_poisson_basketball(home_en, away_en, league, market, line_val, data)
    
    # 尝试xG
    lam_h, lam_a, xg_source = get_xg_lambda(home_en, away_en, data)
    
    if lam_h is None:
        # 用联赛λ
        lam_h, lam_a, xg_source = get_league_lambda_fast(league, data)
    
    probs = calc_poisson_probs(lam_h, lam_a, 'football', line_val if market in ('ou', 'total') else None, market)
    probs['lambda_source'] = xg_source
    probs['lam_h'] = lam_h
    probs['lam_a'] = lam_a
    return probs

def get_p_poisson_basketball(home_en, away_en, league, market, line_val, data):
    # 篮球: 用联赛场均总分
    league_avg_pts = {
        'nba': 220, 'wnba': 162, 'cba': 195, 'euroleague': 155,
        'bbl': 160, 'nbl': 170, 'lnb': 150, 'acb': 160,
    }
    
    total = 160  # default
    league_lower = (league or '').lower()
    for kw, pts in league_avg_pts.items():
        if kw in league_lower or kw.replace(' ','') in league_lower.replace(' ',''):
            total = pts
            break
    
    # 如果联赛名含"女子"，平均分更低
    if '女子' in league or '女' in league or 'w' in league_lower:
        total = min(total, 150)
    
    lam_h = total * 0.51
    lam_a = total * 0.49
    lambda_source = f"篮球平均({total}分)"
    
    probs = calc_poisson_probs(lam_h, lam_a, 'basketball', line_val if market in ('ou', 'total') else None, market)
    probs['lambda_source'] = lambda_source
    probs['lam_h'] = lam_h
    probs['lam_a'] = lam_a
    return probs

# ========== 虚拟比赛过滤 ==========
def is_virtual(league):
    virtual_kw = ['VS-', '梦幻对垒', 'NBA 2K', 'PANDA独家', 'EAFC', '电竞', '瓦尔哈拉']
    for kw in virtual_kw:
        if kw in (league or ''):
            return True
    return False

# ========== K值 ==========
def calc_k(p, odds):
    if odds <= 1.0 or p <= 0:
        return None
    return (p * odds - 1) / (odds - 1)

# ========== 主流程 ==========
def process_all(data):
    matches = data['matches']
    odds_by_match = data['odds_by_match']
    
    all_recs = []
    stats = {
        'total_matches': 0, 'filtered_virtual': 0,
        'football': 0, 'basketball': 0,
        'with_elo_real': 0, 'with_xg_real': 0,
        'with_league_lambda': 0, 'with_2plus': 0,
    }
    
    for match in matches:
        mid = match['match_id']
        league = match['league']
        home_cn = match['home_team']
        away_cn = match['away_team']
        sport = match['sport_code']
        kickoff = match['kickoff_time']
        
        if is_virtual(league):
            stats['filtered_virtual'] += 1
            continue
        
        try:
            ko_dt = datetime.strptime(kickoff, '%Y-%m-%d %H:%M')
            if ko_dt <= NOW:
                continue
        except:
            pass
        
        stats['total_matches'] += 1
        if sport == 'football':
            stats['football'] += 1
        else:
            stats['basketball'] += 1
        
        # 队名转换
        home_en = cn_to_en_name(home_cn, data['team_cn_en'])
        away_en = cn_to_en_name(away_cn, data['team_cn_en'])
        
        odds_data = odds_by_match.get(mid, {})
        
        # === 1x2 ===
        odds_1x2 = odds_data.get('1x2', [])
        if odds_1x2:
            row_1x2 = odds_1x2[0]
            p_book = get_p_book(row_1x2, sport)
            
            if p_book:
                p_elo, elo_label = get_p_elo(home_en, away_en, sport, league, data)
                if p_elo is None:
                    p_elo = dict(p_book)
                    elo_label = '赔率近似'
                
                p_elo_real = (elo_label == '真实')
                
                p_poisson = get_p_poisson(home_en, away_en, sport, league, '1x2', None, data)
                lam_src = p_poisson.get('lambda_source', '默认')
                
                has_xg = 'xG' in lam_src
                has_lam = ('联赛λ' in lam_src and '默认' not in lam_src) or 'xG' in lam_src
                
                directions = [
                    ('主胜', 'home', row_1x2.get('odds_home')),
                    ('平局', 'draw', row_1x2.get('odds_draw')),
                    ('客胜', 'away', row_1x2.get('odds_away')),
                ]
                
                match_recs = []
                for dir_name, dir_key, odds_val in directions:
                    if odds_val is None or odds_val <= 1.0:
                        continue
                    if sport == 'basketball' and dir_key == 'draw':
                        continue
                    
                    pb = p_book.get(dir_key, 0) or 0
                    pp = p_poisson.get(dir_key, 0) or 0
                    pe = p_elo.get(dir_key, 0) or 0
                    
                    pf = 0.50 * pb + 0.30 * pp + 0.20 * pe
                    k = calc_k(pf, odds_val)
                    
                    if k is not None:
                        ns = 3 if p_elo_real else 2
                        match_recs.append({
                            'match_id': mid, 'league': league,
                            'home': home_cn, 'away': away_cn,
                            'sport': sport, 'kickoff': kickoff,
                            'direction': dir_name, 'odds': odds_val,
                            'p_book': pb, 'p_poisson': pp, 'p_elo': pe,
                            'elo_label': elo_label, 'p_fusion': pf,
                            'k': k, 'k_quarter': k * 0.25,
                            'lam_source': lam_src,
                            'lam_h': p_poisson.get('lam_h', 0),
                            'lam_a': p_poisson.get('lam_a', 0),
                            'bookmaker': 'qiety_yb',
                            'num_sources': ns,
                            'has_elo_real': p_elo_real,
                            'has_xg': has_xg,
                            'handicap': None,
                            'handicap_source': 'N/A',
                            'market_type': '1x2',
                        })
                
                if match_recs:
                    match_recs.sort(key=lambda x: x['k'], reverse=True)
                    all_recs.append(match_recs[0])
        
        # === OU ===
        odds_ou = odds_data.get('ou', [])
        if odds_ou:
            for ou_row in odds_ou:
                line_str = ou_row.get('line', '')
                line_val = parse_handicap_line(line_str)
                if line_val is None:
                    continue
                
                p_book_ou = get_p_book_ou(ou_row)
                if p_book_ou is None:
                    continue
                
                p_poisson_ou = get_p_poisson(home_en, away_en, sport, league, 'ou', line_val, data)
                
                for dir_name, dir_key in [('大球', 'over'), ('小球', 'under')]:
                    odds_key = 'over_odds' if dir_key == 'over' else 'under_odds'
                    odds_val = ou_row.get(odds_key)
                    if odds_val is None or odds_val <= 1.0:
                        continue
                    
                    pb = p_book_ou.get(dir_key, 0) or 0
                    pp = p_poisson_ou.get(dir_key, 0) or 0
                    pe = pb  # OU没有独立的ELO
                    
                    pf = 0.50 * pb + 0.30 * pp + 0.20 * pe
                    k = calc_k(pf, odds_val)
                    
                    if k is not None:
                        all_recs.append({
                            'match_id': mid, 'league': league,
                            'home': home_cn, 'away': away_cn,
                            'sport': sport, 'kickoff': kickoff,
                            'direction': f'{dir_name} {line_str}',
                            'odds': odds_val,
                            'p_book': pb, 'p_poisson': pp, 'p_elo': pe,
                            'elo_label': '赔率近似', 'p_fusion': pf,
                            'k': k, 'k_quarter': k * 0.25,
                            'lam_source': p_poisson_ou.get('lambda_source', '默认'),
                            'lam_h': p_poisson_ou.get('lam_h', 0),
                            'lam_a': p_poisson_ou.get('lam_a', 0),
                            'bookmaker': 'qiety_yb',
                            'num_sources': 2,
                            'has_elo_real': False,
                            'has_xg': 'xG' in p_poisson_ou.get('lambda_source', ''),
                            'handicap': line_str,
                            'handicap_source': 'qiety_yb',
                            'market_type': 'ou',
                        })
    
    # ====== 过滤: 每场比赛每市场只保留K最高 ======
    match_best = {}
    for rec in all_recs:
        mid = rec['match_id']
        mt = rec['market_type']
        key = f"{mid}_{mt}"
        if key not in match_best or rec['k'] > match_best[key]['k']:
            match_best[key] = rec
    
    final_recs = list(match_best.values())
    final_recs.sort(key=lambda x: x['k'], reverse=True)
    
    # ====== 分级 ======
    s_recs, a_recs, b_recs, c_recs = [], [], [], []
    
    for rec in final_recs:
        k = rec['k']
        odds = rec['odds']
        has_xg = rec.get('has_xg', False)
        has_elo = rec.get('has_elo_real', False)
        
        # S: K≥0.10, 赔率1.5-3.5, 2源交叉
        if k >= 0.10 and 1.5 <= odds <= 3.5 and (has_xg or has_elo):
            s_recs.append(rec)
        elif k >= 0.08 and 1.5 <= odds <= 4.0:
            a_recs.append(rec)
        elif k >= 0.03:
            b_recs.append(rec)
        elif k > 0:
            c_recs.append(rec)
    
    a_recs = a_recs[:30]
    b_recs = b_recs[:10]
    c_recs = c_recs[:5]
    
    # 统计
    total_with_elo = sum(1 for r in final_recs if r.get('has_elo_real'))
    total_with_xg = sum(1 for r in final_recs if r.get('has_xg'))
    total_with_lambda = sum(1 for r in final_recs if 'xG' in r.get('lam_source', '') or ('联赛λ' in r.get('lam_source', '') and '默认' not in r.get('lam_source', '')))
    total_with_2plus = sum(1 for r in final_recs if r.get('num_sources', 1) >= 2)
    
    return {
        'all': final_recs,
        'S': s_recs, 'A': a_recs, 'B': b_recs, 'C': c_recs,
        'total': len(final_recs),
        'stats': {
            'total_matches': stats['total_matches'],
            'filtered_virtual': stats['filtered_virtual'],
            'football': stats['football'],
            'basketball': stats['basketball'],
            'with_elo_real': total_with_elo,
            'with_xg_real': total_with_xg,
            'with_league_lambda': total_with_lambda,
            'with_2plus_sources': total_with_2plus,
            'total_recs': len(final_recs),
        }
    }

# ========== 输出 ==========
def fmt_time(kickoff):
    try:
        return datetime.strptime(kickoff, '%Y-%m-%d %H:%M').strftime('%H:%M')
    except:
        return kickoff[-5:]

def generate_output(result):
    lines = []
    lines.append("# 🔥 K值推荐单 终版 v2")
    lines.append(f"## 生成时间: {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"## 数据基准: 企鹅体育 + ELO + xG + 联赛λ")
    lines.append("")
    
    s = result['stats']
    nr = max(s['total_recs'], 1)
    lines.append("## 📊 数据概况")
    lines.append(f"- 总计有效比赛: {s['total_matches']} 场 (足球{s['football']}|篮球{s['basketball']})")
    lines.append(f"- 过滤虚拟比赛: {s['filtered_virtual']} 场")
    lines.append(f"- 产生推荐方向: {s['total_recs']} 个")
    lines.append(f"- 有真实ELO数据: {s['with_elo_real']} 个 ({s['with_elo_real']/nr*100:.1f}%)")
    lines.append(f"- 有真实xG数据: {s['with_xg_real']} 个 ({s['with_xg_real']/nr*100:.1f}%)")
    lines.append(f"- 有联赛λ数据: {s['with_league_lambda']} 个 ({s['with_league_lambda']/nr*100:.1f}%)")
    lines.append(f"- 有2+源交叉: {s['with_2plus_sources']} 个 ({s['with_2plus_sources']/nr*100:.1f}%)")
    lines.append("")
    
    grades = [
        ('S', '🌟 S级推荐 (K≥0.10, 赔率1.5-3.5, 2源验证)', result['S']),
        ('A', '🔥 A级推荐 (K≥0.08, 赔率1.5-4.0)', result['A']),
        ('B', '📌 B级推荐 (K≥0.03)', result['B']),
        ('C', '💡 C级推荐 (K>0)', result['C']),
    ]
    
    seq = 0
    
    for grade, title, recs in grades:
        if not recs:
            continue
        lines.append(f"## {title} ({len(recs)}场)")
        lines.append("")
        
        for rec in recs:
            seq += 1
            t = fmt_time(rec['kickoff'])
            lines.append(f"{seq}. [{rec['league']}] {rec['home']} vs {rec['away']} ⏰{t}")
            
            hc = f" | 盘口线:{rec['handicap']}({rec.get('handicap_source','?')})" if rec.get('handicap') else ""
            lines.append(f"    → {rec['direction']} | 赔率:{rec['odds']:.2f} | {rec['num_sources']}源{hc}")
            
            lines.append(f"    P_book={rec['p_book']:.4f} P_poisson={rec['p_poisson']:.4f} P_elo={rec['p_elo']:.4f}({rec['elo_label']}) P_fusion={rec['p_fusion']:.4f}")
            lines.append(f"    K={rec['k']:.4f} K_1/4={rec['k_quarter']:.4f}")
            lines.append(f"    Lambda: {rec['lam_source']}")
            lines.append(f"    数据源: {rec['bookmaker']}")
            lines.append("")
    
    # S级串关
    s_recs = result['S']
    if len(s_recs) >= 2:
        lines.append("---")
        lines.append("## 🎯 S级串关建议")
        lines.append("")
        combos = []
        for i in range(len(s_recs)):
            for j in range(i + 1, len(s_recs)):
                r1, r2 = s_recs[i], s_recs[j]
                total_odds = r1['odds'] * r2['odds']
                combo_k = r1['k'] * r2['k']
                combos.append((r1, r2, total_odds, combo_k))
        
        combos.sort(key=lambda x: x[3], reverse=True)
        for idx, (r1, r2, to, ck) in enumerate(combos[:10], 1):
            lines.append(f"{idx}. [{r1['league']}] {r1['home']}vs{r1['away']}({r1['direction']}@{r1['odds']:.2f})")
            lines.append(f"   × [{r2['league']}] {r2['home']}vs{r2['away']}({r2['direction']}@{r2['odds']:.2f})")
            lines.append(f"   = 串关赔率:{to:.2f} | 组合K:{ck:.4f}")
            lines.append("")
    
    # 禁入名单
    bans = [r for r in result['all'] if r['k'] < -0.05]
    lines.append("---")
    lines.append("## ⛔ 禁入名单")
    lines.append("")
    if bans:
        for i, r in enumerate(bans, 1):
            lines.append(f"{i}. [{r['league']}] {r['home']}vs{r['away']} → {r['direction']} | K={r['k']:.4f} ⏰{fmt_time(r['kickoff'])}")
    else:
        lines.append("无K<-0.05的方向")
    lines.append("")
    
    # 仓位
    lines.append("---")
    lines.append("## 💰 仓位分配 (10u预算)")
    lines.append("")
    lines.append("| 类型 | 预算 | 建议 |")
    lines.append("|------|------|------|")
    if len(s_recs) >= 2:
        lines.append("| 单关 | 6.0u | S级主推(3u) + A级品(3u) |")
        lines.append("| 串关 | 2.5u | S级2串1组合(2.5u) |")
        lines.append("| 预留 | 1.5u | 临场追加 |")
    elif len(s_recs) == 1:
        lines.append("| 单关 | 7.5u | S级主推(3u) + A/爆品(4.5u) |")
        lines.append("| 预留 | 2.5u | 临场追加 |")
    else:
        lines.append("| 单关 | 8.0u | A级品(5u) + B级品(3u) |")
        lines.append("| 预留 | 2.0u | 临场追加 |")
    lines.append("| **合计** | **10.0u** | |")
    lines.append("")
    
    # 最终统计
    lines.append("---")
    lines.append("## 📈 最终统计")
    lines.append(f"- 总场次: {s['total_matches']}")
    lines.append(f"- S级: {len(result['S'])} | A级: {len(result['A'])} | B级: {len(result['B'])} | C级: {len(result['C'])}")
    lines.append(f"- 有真实ELO数据场次比例: {s['with_elo_real']}/{nr} = {s['with_elo_real']/nr*100:.1f}%")
    lines.append(f"- 有真实xG数据场次比例: {s['with_xg_real']}/{nr} = {s['with_xg_real']/nr*100:.1f}%")
    lines.append(f"- 有联赛λ场次比例: {s['with_league_lambda']}/{nr} = {s['with_league_lambda']/nr*100:.1f}%")
    lines.append(f"- 有2+源交叉场次比例: {s['with_2plus_sources']}/{nr} = {s['with_2plus_sources']/nr*100:.1f}%")
    lines.append("")
    
    return '\n'.join(lines)

# ========== Main ==========
if __name__ == '__main__':
    print("=" * 60)
    print("🔥 K值推荐单 终版 v2 计算中...")
    print("=" * 60)
    
    data = load_data()
    
    print("\n🧮 开始计算K值...")
    result = process_all(data)
    
    print(f"\n📊 结果统计:")
    print(f"  有效比赛: {result['stats']['total_matches']}")
    print(f"  总推荐方向: {result['total']}")
    print(f"  S级: {len(result['S'])}")
    print(f"  A级: {len(result['A'])}")
    print(f"  B级: {len(result['B'])}")
    print(f"  C级: {len(result['C'])}")
    
    output = generate_output(result)
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"\n✅ 推荐单已保存至: {OUTPUT_PATH}")
    
    print("\n" + "=" * 60)
    print("📄 输出预览 (前60行):")
    print("=" * 60)
    for line in output.split('\n')[:60]:
        print(line)
