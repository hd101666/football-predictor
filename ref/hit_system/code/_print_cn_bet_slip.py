#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全中文投注单"""
import sqlite3, sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
td = sqlite3.connect(r'F:\qqsj\data\sports_data.db')

# ========== 联赛中文映射 ==========
LEAGUE_CN = {
    # 今日推荐中出现的联赛
    'Australia - NBL1 Women': '澳大利亚女篮NBL1',
    'New Zealand - NBL': '新西兰篮球联赛',
    'Spain - Segunda Division': '西乙',
    'Spain - ACB': '西班牙篮球甲级联赛',
    'Argentina - Primera Division': '阿甲',
    'Argentina - Liga Nacional': '阿根廷篮球联赛',
    'International - Friendlies': '国际友谊赛',
    'Brazil - Serie B': '巴乙',
    'Japan - J League': '日职联',
    'Japan - J2/J3 League': '日乙',
    'Korea Republic - K3 League': '韩K3联',
    'Finland - Kakkonen Group C': '芬丙C',
    'Iceland - 3. Deild': '冰岛丙',
    'Sweden - Division 1 Norra': '瑞典甲北',
    'Sweden - Division 1 Sodra': '瑞典甲南',
    'Chile - Primera B': '智利乙',
    'Uruguay - Primera Division': '乌拉圭甲',
    'Uruguay - Segunda Division': '乌拉圭乙',
    'Denmark - 2nd Division': '丹乙',
    'Denmark - 3rd Division': '丹丙',
    'Australia - NPL South Australia': '澳南澳超',
    'Australia - NPL Western Australia': '澳西超',
    'Australia - NPL New South Wales': '澳新南超',
    'Australia - NPL Queensland': '澳昆超',
    'Australia - NPL Queensland Women': '澳昆女超',
    'Australia - Victoria Premier League 1': '澳维多利亚超',
    'Australia - NPL Victoria': '澳维多利亚超',
    'Australia - NPL Capital Territory': '澳首都联',
    'Australia - NPL Northern NSW': '澳北新南超',
    'Australia - NPL1 Queensland U23': '澳昆超U23',
    'Australia - Queensland Premier League 2': '澳昆甲',
    'Australia - Queensland Premier League 1': '澳昆超',
    'Australia - South Australian NPL': '澳南澳超',
    'Spain - Liga FEB': '西班牙篮球乙级',
    'USA - MLS Next Pro League': '美职联发展',
    'Canada - Premier League': '加拿大超',
    'Japan - B.League': '日本篮球联赛',
    'Korea Republic - K League 1': '韩K1联',
    'Korea Republic - K League 2': '韩K2联',
    'Korea Republic - K4 League': '韩K4联',
    'Spain - Tercera Division': '西丙',
    'Spain - Primera Federacion': '西协甲',
    'Chile - League Cup': '智利联赛杯',
    'Australia - NBL1': '澳大利亚NBL1篮球',
    'WNBA': 'WNBA',
    'NBA': 'NBA',
    'NBA - Finals': 'NBA总决赛',
    'China - CBA': 'CBA',
    'China - League Two': '中乙',
    'Algeria - Ligue 1': '阿尔及利亚甲',
    'Argentina - Primera B Nacional': '阿乙',
    'Finland - Kakkonen Group B': '芬丙B',
    'Finland - Kakkonen Group A': '芬丙A',
    'Finland - Kakkonen Group D': '芬丙D',
    'Finland - Ykkonen': '芬甲',
    'Finland - Ykkosliiga': '芬甲',
    'Iceland - 1. Deild': '冰岛甲',
    'Iceland - 2. Deild': '冰岛乙',
    'Iceland - 3. Deild': '冰岛丙',
    'Netherlands - Tweede Divisie': '荷丙',
    'Poland - 2nd Liga': '波乙',
    'South Africa - PSL': '南非超',
}

# YB 中文联赛名映射
YB_LEAGUE_CN = {
    '澳大利亚女子NBL1篮球联赛': '澳大利亚女篮NBL1',
    '澳大利亚NBL1篮球联赛': '澳大利亚NBL1篮球',
    '澳大利亚女子NBL1篮球联赛': '澳大利亚女篮NBL1',
    '新西兰国家篮球联赛': '新西兰篮球联赛',
    '日本J1百年愿景联赛 - 附加赛': '日职联附加赛',
    '日本J2 & J3百年愿景联赛 - 附加赛': '日乙附加赛',
    '澳大利亚维多利亚超级联赛一': '澳维多利亚超',
    '澳大利亚新南威尔士国家超级联赛': '澳新南超',
    '澳大利亚新南威尔士联赛一': '澳新南甲',
    '澳大利亚昆士兰超级联赛一': '澳昆超',
    '澳大利亚昆士兰州国家超级联赛': '澳昆超',
    '西澳大利亚国家超级联赛': '澳西超',
    '韩国K3联赛': '韩K3联',
    '韩国K2联赛': '韩K2联',
    '韩国K4联赛': '韩K4联',
    '阿尔及利亚甲级联赛': '阿尔及利亚甲',
    '阿尔及利亚甲级联赛': '阿尔及利亚甲',
    '冰岛甲级联赛': '冰岛甲',
    '冰岛乙级联赛': '冰岛乙',
    '冰岛丙级联赛': '冰岛丙',
    '丹麦乙级联赛 - 附加赛': '丹乙附加赛',
    '丹麦丙级联赛 - 附加赛': '丹丙附加赛',
    '芬兰甲级联赛': '芬甲',
    '芬兰乙级联赛': '芬乙',
    '芬兰丙级联赛': '芬丙',
    '芬兰丁级联赛': '芬丁',
    '荷兰丙级联赛 - 附加赛': '荷丙附加赛',
    '波兰乙级联赛 - 附加赛': '波乙附加赛',
    '瑞典乙级联赛': '瑞典乙',
    '瑞典北部甲级联赛': '瑞典甲北',
    '瑞典南部甲级联赛': '瑞典甲南',
    '乌拉圭甲级联赛': '乌拉圭甲',
    '乌拉圭乙级联赛': '乌拉圭乙',
    '国际友谊赛': '国际友谊赛',
    '国际友谊赛U21': '国际友谊赛U21',
    '女子国际友谊赛': '女子国际友谊赛',
    '女子世界杯2027欧洲资格赛': '女足世界杯欧预赛',
    '智利乙级联赛': '智利乙',
    '智利联赛杯': '智利联赛杯',
    '南美洲足协女子国家联赛': '南美女足联赛',
    '奥地利丁级联赛': '奥地利丁',
    '奥地利丙级联赛': '奥地利丙',
    '挪威丙级联赛': '挪威丙',
    '挪威杯资格赛': '挪威杯资格赛',
    '捷克丁级联赛': '捷克丁',
    '捷克丙级联赛': '捷克丙',
    '美国女子超级联赛': '美国女足超',
    '美国MLS Next职业联赛': '美职联发展',
    '加拿大超级联赛': '加拿大超',
    '巴西乙级联赛': '巴乙',
    '巴西圣保罗联赛U20': '巴西圣保罗U20',
    '阿根廷全国联赛': '阿甲',
    '阿根廷乙级曼特波里顿联赛': '阿乙',
    '巴拉圭乙级联赛': '巴拉圭乙',
    '厄瓜多尔乙级联赛': '厄瓜多尔乙',
    '新西兰北部联赛': '新西兰北联',
    '新西兰南部联赛': '新西兰南联',
    '新西兰中央联赛': '新西兰中央联',
    '越南乙级联赛': '越南乙',
    '中国乙级联赛': '中乙',
    '马里超级联赛': '马里超',
    '津巴布韦超级联赛': '津巴布韦超',
    '立陶宛乙级联赛': '立陶宛乙',
    '爱沙尼亚丙级联赛': '爱沙尼亚丙',
    '缅甸全国联赛U20': '缅甸全国U20',
    '尼日利亚总统联合会杯': '尼日利亚总统杯',
    '土伦杯(在法国)': '土伦杯',
    '巴提杯': '巴提杯',
    '俄罗斯乙级联赛乙组': '俄乙B',
    '西班牙足协甲级联赛 - 附加赛': '西协甲附加赛',
    '匈牙利甲级联赛U19': '匈牙利甲U19',
    '日本地区足球联赛': '日本地区联赛',
    '日本女子甲级联赛': '日本女足甲',
    '美国足球乙级联赛': '美乙',
    '爱尔兰伦斯特高级联赛高级组': '爱尔兰伦斯特高级',
    '澳大利亚新南威尔士北部国家超级联赛': '澳北新南超',
    '澳大利亚新南威尔士联赛二': '澳新南乙',
    '澳大利亚新南威尔士超级联赛U20': '澳新南超U20',
    '澳大利亚南澳大利亚国家超级联赛': '澳南澳超',
    '澳大利亚昆士兰超级联赛三梅特罗': '澳昆超梅特罗',
    '澳大利亚昆士兰超级联赛二': '澳昆乙',
    '澳大利亚昆士兰超级联赛一U23': '澳昆超U23',
    '澳大利亚昆士兰国家超级联赛U23': '澳昆超U23',
    '澳大利亚维多利亚超级联赛二': '澳维多利亚乙',
    '澳大利亚维多利亚超级联赛一U23': '澳维多利亚超U23',
    '澳大利亚维多利亚国家超级联赛U23': '澳维多利亚超U23',
    '澳大利亚维多利亚女子国家超级联赛': '澳维多利亚女超',
    '澳大利亚北部特区超级联赛': '澳北区超',
    '西澳大利亚国家超级联赛U23': '澳西超U23',
    '西澳大利亚甲级联赛': '澳西甲',
    '西澳大利亚甲级联赛后备队': '澳西甲预备队',
    '澳大利亚昆士兰州女子国家超级联赛': '澳昆女超',
    '南澳大利亚甲级联赛': '澳南澳甲',
    '南澳大利亚甲级联赛后备队': '澳南澳甲预备队',
    '南澳大利亚国家超级联赛后备队': '澳南澳超预备队',
    '澳大利亚新南威尔士联赛一U20': '澳新南甲U20',
    '梦幻对垒': '梦幻对垒',
}

# ========== 队名中文映射（综合）==========
TEAM_CN = {}

# 从config.py加载（通过导入方式不可行，直接硬编码覆盖需要的）
# 用TEA_CN_MAP简版
TEAM_CN = {
    # 日职
    'Vissel Kobe': '神户胜利船', 'Yokohama F. Marinos': '横滨水手',
    'Kawasaki Frontale': '川崎前锋', 'Urawa Red Diamonds': '浦和红钻',
    'Kashima Antlers': '鹿岛鹿角', 'FC Tokyo': 'FC东京',
    'Sanfrecce Hiroshima': '广岛三箭', 'Nagoya Grampus': '名古屋鲸八',
    'Cerezo Osaka': '大阪樱花', 'Gamba Osaka': '大阪钢巴',
    'Sagan Tosu': '鸟栖砂岩', 'Avispa Fukuoka': '福冈黄蜂',
    'Kashiwa Reysol': '柏太阳神', 'Consadole Sapporo': '札幌冈萨多',
    'Shonan Bellmare': '湘南海洋', 'Albirex Niigata': '新潟天鹅',
    'Kyoto Sanga': '京都不死鸟', 'Jubilo Iwata': '磐田喜悦',
    'Tochigi': '枥木SC', 'Nagano Parceiro': '长野帕塞罗',
    'Imabari': '今治',
    # 西乙
    'Castellon': '卡斯特利翁', 'Almeria': '阿尔梅里亚',
    'Tenerife': '特内里费', 'Real Madrid': '皇家马德里',
    # 阿甲
    'Los Andes': '洛斯安第斯', 'Estudiantes de Caseros': '学生队',
    # NBA球队
    'New York Knicks': '纽约尼克斯', 'Orlando Magic': '奥兰多魔术',
    'New Orleans Pelicans': '新奥尔良鹈鹕', 'Dallas Mavericks': '达拉斯独行侠',
    'Oklahoma City Thunder': '俄克拉荷马城雷霆',
    'Boston Celtics': '波士顿凯尔特人',
    'Denver Nuggets': '丹佛掘金',
    'Minnesota Timberwolves': '明尼苏达森林狼',
    'LA Clippers': '洛杉矶快船',
    'Milwaukee Bucks': '密尔沃基雄鹿',
    'Cleveland Cavaliers': '克利夫兰骑士',
    'Philadelphia 76ers': '费城76人',
    'Miami Heat': '迈阿密热火',
    'Indiana Pacers': '印第安纳步行者',
    'Los Angeles Lakers': '洛杉矶湖人',
    'Phoenix Suns': '菲尼克斯太阳',
    'Sacramento Kings': '萨克拉门托国王',
    'Golden State Warriors': '金州勇士',
    'Houston Rockets': '休斯顿火箭',
    'San Antonio Spurs': '圣安东尼奥马刺',
    'Memphis Grizzlies': '孟菲斯灰熊',
    'Chicago Bulls': '芝加哥公牛',
    'Atlanta Hawks': '亚特兰大老鹰',
    'Brooklyn Nets': '布鲁克林篮网',
    'Toronto Raptors': '多伦多猛龙',
    'Charlotte Hornets': '夏洛特黄蜂',
    'Detroit Pistons': '底特律活塞',
    'Portland Trail Blazers': '波特兰开拓者',
    'Utah Jazz': '犹他爵士',
    'Washington Wizards': '华盛顿奇才',
    # 国家队
    'Portugal': '葡萄牙', 'Chile': '智利', 'Scotland': '苏格兰',
    'Bolivia': '玻利维亚', 'Cape Verde': '佛得角', 'Bermuda': '百慕大',
    'England': '英格兰', 'Croatia': '克罗地亚', 'Belgium': '比利时',
    'Egypt': '埃及', 'Czech Republic': '捷克', 'South Africa': '南非',
    # 篮球
    'Real Madrid': '皇家马德里', 'La Laguna Tenerife': '特内里费',
    'Asociacion Atletica Quimsa': '基姆萨竞技协会',
    'Club Gimnasia y Esgrima': '体操击剑俱乐部',
    'Rockingham Flames': '罗金厄姆火焰',
    'East Perth Eagles': '东珀斯老鹰',
    'Wellington Saints': '惠灵顿圣徒',
    'Otago Nuggets': '奥塔哥掘金',
    'North Gold Coast Seahawks': '北黄金海岸海鹰',
    'Ipswich Force': '伊普斯维奇力量',
    'South West Slammers': '西南猛击者',
    'Perry Lakes Hawks': '佩里湖老鹰',
    'Kalamunda Eastern Suns': '卡拉蒙达东太阳',
    'Joondalup Wolves': '琼达拉普狼',
    'Taranaki Mountainairs': '塔拉纳基山航',
    'Auckland Tuatara': '奥克兰蜥蜴',
    'Criciuma': '克里丘马', 'Londrina': '隆德里纳',
}

def normalize_name(name):
    """函数：英文队名→中文（先精确匹配，再模糊匹配）"""
    name = name.strip()
    if name in TEAM_CN:
        return TEAM_CN[name]
    # 尝试去掉部分后缀
    for suffix in [' W', ' Women', ' (W)', ' Womens', ' Ladies']:
        if name.endswith(suffix) and name[:-len(suffix)] in TEAM_CN:
            return TEAM_CN[name[:-len(suffix)]] + '(女)'
    return name

def get_league_cn(league, source):
    """联赛中文名"""
    if source == 'qiety_yb':
        return YB_LEAGUE_CN.get(league, league)
    return LEAGUE_CN.get(league, league)

def utc_to_bj(utc_str):
    try:
        dt = datetime.strptime(utc_str.replace('Z',''), '%Y-%m-%dT%H:%M:%S')
        return (dt + timedelta(hours=8)).strftime('%m/%d %H:%M')
    except:
        return utc_str[:16]

def mkt_cn(m):
    return {'moneyline':'独赢','spread':'让分','total':'大小分','team_total':'队大小分'}.get(m, m)
def out_cn(o):
    return {'home':'主胜','away':'客胜','draw':'平局','over':'大分','under':'小分'}.get(o, o)

# ========== 读取推荐 ==========
recs = td.execute("""
    SELECT r.home_team, r.away_team, r.league_name, r.market, r.outcome,
           r.best_odds, r.best_source, r.hit_score, r.kickoff_utc, r.handicap
    FROM hit_recommendations r
    WHERE r.fetch_date='2026-06-06'
    ORDER BY r.hit_score DESC
""").fetchall()

bankroll = 200
single_per = 4
single_cnt = min(10, len(recs))
single_total = single_cnt * single_per

print('=' * 68)
print('  📋 今日投注计划  [2026年6月6日]')
print('  本金：%d元  |  数据源：Pinnacle + 企鹅体育YB  |  以Pinnacle为主' % bankroll)
print('=' * 68)

# ========== 单注 ==========
print()
print('━' * 68)
print('  🟦 单注 %d 注 × %d元 = %d元' % (single_cnt, single_per, single_total))
print('━' * 68)
print()

for i, r in enumerate(recs[:10], 1):
    home, away, league, market, outcome, odds, source, score, kickoff, hc = r
    ov = float(odds) if odds else 0
    hc_str = ''
    if hc and float(hc) != 0:
        hc_str = '%+g' % float(hc)
    bj = utc_to_bj(kickoff) if kickoff else 'N/A'
    win = round(ov * single_per, 1)
    
    # 中文队名
    if source == 'qiety_yb':
        home_cn = home
        away_cn = away
    else:
        home_cn = normalize_name(home)
        away_cn = normalize_name(away)
    
    league_cn = get_league_cn(league, source)
    
    src_tag = '🐧企鹅YB' if source == 'qiety_yb' else '🎯Pinnacle' if source == 'theodds' else '⚖️共识加权'
    
    print('  %2d. %s  %s' % (i, src_tag, bj))
    print('      %s' % league_cn)
    print('      %s  vs  %s' % (home_cn, away_cn))
    print('      %s%s | %s | @ %.2f | 赢 %d元' % (mkt_cn(market), hc_str, out_cn(outcome), ov, round(win)))
    print()

# ========== 串关 ==========
print('━' * 68)
print('  🟩 串关组合（剩余 %d 元）' % (bankroll - single_total))
print('━' * 68)
print()

pool = recs[:8]
parlay_budget = {2:4, 3:3, 4:2, 5:2, 6:2, 7:1, 8:1}

print('  🏀 串关选池（8场，按命中分排序）：')
print()
for i, r in enumerate(pool, 1):
    home, away, league, market, outcome, odds, source, score, kickoff, hc = r
    ov = float(odds) if odds else 0
    hc_str = ''
    if hc and float(hc) != 0:
        hc_str = '%+g' % float(hc)
    
    if source == 'qiety_yb':
        home_cn = home
        away_cn = away
    else:
        home_cn = normalize_name(home)
        away_cn = normalize_name(away)
    
    league_cn = get_league_cn(league, source)
    
    src_tag = '🐧' if source == 'qiety_yb' else '🎯' if source == 'theodds' else '⚖️'
    
    print('  %2d. %s %s | %s vs %s' % (i, src_tag, league_cn, home_cn, away_cn))
    print('      %s%s | %s | @ %.2f' % (mkt_cn(market), hc_str, out_cn(outcome), ov))
    print()

print('  ～～～ 串关组合表 ～～～')
print()
print('  ╔═══════╦═══════╦══════╦══════╦═══════╦══════════╗')
print('  ║ 组合  ║ 每注  ║ 注数  ║ 投入  ║ 赔率   ║  最高赢  ║')
print('  ╠═══════╬═══════╬══════╬══════╬═══════╬══════════╣')

total_bet = single_total
for n_legs, bet in sorted(parlay_budget.items()):
    picks = pool[:n_legs]
    total_odds = 1.0
    for _, _, _, _, _, odds_val, _, _, _, _ in picks:
        if odds_val:
            total_odds *= float(odds_val)
    total_odds = round(total_odds, 2)
    win_amount = round(bet * total_odds, 1)
    cost = bet
    total_bet += cost
    print('  ║ %d串1  ║ %5d元 ║  %3d注 ║ %4d元 ║  %5.1f ║  %7.1f元║' % (n_legs, bet, bet, cost, total_odds, win_amount))

print('  ╚═══════╩═══════╩══════╩══════╩═══════╩══════════╝')
print()

# ========== 汇总 ==========
print('━' * 68)
print('  📊 投注汇总')
print('━' * 68)
print()
print('  总投入：%d 元（%d%% 本金）' % (total_bet, total_bet*100//bankroll))
print('  剩余：  %d 元' % (bankroll - total_bet))
print()
print('  盈亏速算（单注10场）：')
for n in range(11):
    if n == 0:
        pnl = -single_total
    else:
        # 取前n场的平均赔率
        odds_sum = 0
        cnt = 0
        for r in recs[:n]:
            if r[5]:
                odds_sum += float(r[5])
                cnt += 1
        avg_odds = odds_sum / cnt if cnt else 1.0
        pnl = round(n * avg_odds * single_per - single_total)
    print('  %2d/10 命中 → %+d元' % (n, pnl))

print()
print('  串关命中任一种：')
for n_legs, bet in sorted(parlay_budget.items()):
    picks = pool[:n_legs]
    total_odds = 1.0
    for _, _, _, _, _, odds_val, _, _, _, _ in picks:
        if odds_val:
            total_odds *= float(odds_val)
    total_odds = round(total_odds, 2)
    win_amount = round(bet * total_odds, 1)
    net = round(win_amount - total_bet)
    print('  %d串1 → 赢 %d元（净 %+d元）' % (n_legs, round(win_amount), net))

print()

# ========== YB 独有推荐 ==========
yb_recs = [r for r in recs if r[6] == 'qiety_yb']
if yb_recs:
    print('━' * 68)
    print('  🐧 企鹅体育 YB 来源推荐（%d条）' % len(yb_recs))
    print('━' * 68)
    print()
    for r in yb_recs:
        home, away, league, market, outcome, odds, source, score, kickoff, hc = r
        ov = float(odds) if odds else 0
        hc_str = ''
        if hc and float(hc) != 0:
            hc_str = '%+g' % float(hc)
        bj = utc_to_bj(kickoff) if kickoff else 'N/A'
        league_cn = get_league_cn(league, source)
        
        win = round(ov * single_per, 1)
        print('  🐧 %s' % bj)
        print('     %s' % league_cn)
        print('     %s  vs  %s' % (home, away))
        print('     %s%s | %s | @ %.2f | 命中分 %.3f | 单注4元 → 赢%d元' % (mkt_cn(market), hc_str, out_cn(outcome), ov, float(score), round(win)))
        print()

print('=' * 68)
print('  💡 说明')
print('=' * 68)
print()
print('  • Pinnacle = 🎯 主力信源（American Odds转Decimal，以1.xx格式显示）')
print('  • 企鹅YB = 🐧 补充源（覆盖亚洲联赛、低级别联赛、部分女篮女足）')
print('  • 共识 = ⚖️ 多源加权平均')
print('  • 单注4元/注 = 2%本金（符合凯利1/4原则）')
print('  • 串关采用固定注额策略，2串1博小、6~8串1博取高倍')
print('  • 剩余 %d元作为滚动资金' % (bankroll - total_bet))

td.close()
