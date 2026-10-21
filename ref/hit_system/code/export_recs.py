import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
from team_zh import team_zh

conn = sqlite3.connect('data/sports_data.db')
cur = conn.cursor()

LEAGUE_ZH = [
    ('FIFA - World Cup','FIFA世界杯'),('UEFA - Champions','UEFA欧冠'),('UEFA - Europa','UEFA欧联'),
    ('England - Premier','英超'),('England - Championship','英冠'),
    ('Spain - La Liga','西甲'),('Spain - Segunda','西乙'),('Spain - Primera','西丙'),
    ('Germany - Bundesliga 2','德乙'),('Germany - Bundesliga','德甲'),
    ('Germany - Pro A','德国篮球甲'),('Germany - BBL','德国篮球'),
    ('Italy - Serie A','意甲'),('Italy - Serie B','意乙'),('Italy - Lega A','意大利篮球'),
    ('Italy - Primavera','意大利青年'),
    ('France - Ligue 1','法甲'),('France - Ligue 2','法乙'),('France - LNB','法国篮球'),
    ('France - National','法国三级'),('France - Champion','法国篮球联赛'),
    ('Netherlands - Eredivisie','荷甲'),('Portugal - Primeira','葡超'),('Portugal - Liga','葡乙'),
    ('Turkey - Super','土超'),('Russia - Premier','俄超'),('Russia - VTB','俄VTB联赛'),
    ('China - Super League','中超'),('China - CBA','CBA'),
    ('Japan - J League','日本J联赛'),('Japan - J1','日本J1'),
    ('Korea Republic - K League','韩K联赛'),
    ('USA - MLS','美职联'),('USA - National Women','美国女足'),('USA - USL Championship','美国USL'),
    ('USA - USL League','美国USL二级'),
    ('Brazil - Serie A','巴甲'),('Brazil - Serie B','巴乙'),('Brazil - NBB','巴西篮球'),
    ('Brazil - Brasileirao','巴西杯'),('Brazil - LBF','巴西女篮'),('Brazil - Novo','巴西篮球新'),
    ('Argentina - Primera','阿甲'),('Argentina - Liga','阿根廷职联'),('Argentina - Cup','阿根廷杯'),
    ('Australia - NBL','澳洲篮球'),('Australia - NPL','澳洲NPL'),
    ('Greece - Basket','希腊篮球'),('Israel - Super','以色列篮球'),('Israel - Premier','以色列篮球'),
    ('Lithuania - LKL','立陶宛篮球'),('Lithuania - Liet','立陶宛联赛'),('Lithuania - A Ly','立陶宛A级'),
    ('Poland - Basket','波兰篮球'),('Poland - 1st Lig','波兰一级'),
    ('Serbia - Super','塞尔维亚篮球'),
    ('Europe - Euroleague','欧冠篮球'),('ABA - Adriatic','亚德里亚联赛'),
    ('Europe - VTB','欧洲VTB'),('BNXT','BNXT联赛'),
    ('Africa - BAL','非洲篮球'),('FIBA - Basket','FIBA篮球'),
    ('Lebanon','黎巴嫩篮球'),
    ('Norway - Eliteserien','挪威超级'),('Norway - 1st Div','挪威一级'),
    ('Sweden - Allsvenskan','瑞典超级'),('Sweden - Superet','瑞典超级乙'),
    ('Denmark - Superliga','丹麦超级'),('Denmark - Elited','丹麦精英'),('Denmark - Divisi','丹麦二级'),
    ('Denmark - Denmar','丹麦联赛'),
    ('Scotland - Premiership','苏超'),
    ('Belgium - Pro League','比甲'),('Ireland - Premier','爱超'),('Ireland - Division','爱乙'),
    ('Uruguay - Primera','乌拉圭甲'),('Uruguay - Liga','乌拉圭篮球'),
    ('Chile - Primera','智利甲'),('Chile - LNB','智利篮球'),
    ('Colombia','哥伦比亚'),('Mexico','墨西哥联赛'),
    ('Egypt - Premier','埃及超级'),('Romania - Liga','罗马尼亚'),('Romania - Divisi','罗马尼亚二级'),
    ('Bulgaria - First','保加利亚甲'),
    ('International - Friend','国际友谊赛'),
    ('CONMEBOL - Copa','南美解放者杯'),
    ('SAFF - Champions','南亚锦标赛'),
    ('Paraguay - Prime','巴拉圭甲'),('Paraguay - LNCF','巴拉圭篮球'),
    ('Venezuela - Supe','委内瑞拉超级'),
    ('Ecuador - Serie','厄瓜多尔甲'),
    ('Peru - Liga','秘鲁甲'),
    ('Kazakhstan - Pre','哈萨克斯坦超级'),
    ('Slovakia - Extra','斯洛伐克特级'),
    ('Finland - Veikka','芬兰甲'),('Finland - Ykkone','芬兰一级'),('Finland - Ykkosl','芬兰南部'),
    ('Georgia - Super','格鲁吉亚超级'),
    ('Iceland - Premie','冰岛超级'),
    ('Faroe Islands','法罗群岛'),
    ('New Zealand','新西兰'),
    ('El Salvador','萨尔瓦多'),
    ('Costa Rica','哥斯达黎加'),
    ('Indonesia - Bask','印尼篮球'),
    ('Chinese Taipei','中国台湾'),
    ('Croatia','克罗地亚联赛'),
    ('Estonia - Meistr','爱沙尼亚超级'),
    ('Kuwait - Premier','科威特超级'),
    ('Spain Tercera','西班牙丙级'),('Spain - Liga FEB','西班牙篮球'),
    ('Czech Republic','捷克联赛'),
    ('WNBA','WNBA'),('NBA','NBA'),
]
MARKET_ZH = {
    'moneyline':'独赢','1X2':'独赢','spread':'让球','total':'大小球',
    'team_total':'球队大小','draw_no_bet':'平局无效','asian_handicap':'亚盘'
}
OUTCOME_ZH = {
    'home':'主胜','away':'客胜','draw':'平局','over':'大球','under':'小球',
    'home_over':'主队大','home_under':'主队小','away_over':'客队大','away_under':'客队小'
}

def lg(name):
    for k, v in LEAGUE_ZH:
        if k.lower() in (name or '').lower():
            return v
    return (name or '')[:16]

def ft(utc):
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(utc.replace('Z', '+00:00'))
        bj = dt.astimezone(timezone(timedelta(hours=8)))
        return bj.strftime('%m/%d %H:%M')
    except:
        return '--:--'

def cw(s, w):
    r, used = '', 0
    for c in str(s):
        cw2 = 2 if ord(c) > 127 else 1
        if used + cw2 > w:
            break
        r += c
        used += cw2
    return r + ' ' * (w - used)

cur.execute("""
SELECT sport_code, league_name, home_team, away_team,
       kickoff_utc, market, outcome, best_odds, hit_score
FROM hit_recommendations
WHERE fetch_date='2026-05-28'
ORDER BY hit_score DESC, best_odds DESC
""")
rows = cur.fetchall()
conn.close()

SEP = '=' * 114
lines = []
lines.append(SEP)
lines.append(f'  今日投注推荐单  [2026-05-28]  （北京时间）  共 {len(rows)} 条（命中分 >= 0.50）')
lines.append(SEP)
lines.append(f'  {cw("序号",5)}{cw("开赛时间",12)}{cw("联赛",16)}{cw("主队",14)}{cw("客队",14)}{cw("市场",8)}{cw("方向",6)}{cw("赔率",7)}命中分')
lines.append('-' * 114)
for i, row in enumerate(rows, 1):
    sport, league, home, away, kickoff, market, outcome, odds, score = row
    t  = ft(kickoff or '')
    lz = cw(lg(league or ''), 16)
    hz = cw('[主]' + team_zh(home or ''), 14)
    az = cw('[客]' + team_zh(away or ''), 14)
    mz = cw(MARKET_ZH.get(market, market or ''), 8)
    oz = cw(OUTCOME_ZH.get(outcome, outcome or ''), 6)
    lines.append(f'  {str(i)+".":<5}{t:<12}{lz}{hz}{az}{mz}{oz}{odds:<7.2f}{score:.3f}')
lines.append(SEP)

output = '\n'.join(lines)

# 保存到文件
with open('推荐单_2026-05-28.txt', 'w', encoding='utf-8') as f:
    f.write(output)

# 也打印到stdout
print(output)
