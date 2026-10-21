# -*- coding: utf-8 -*-
"""Generate full Chinese betting slip + parlay recommendations"""
import sqlite3
from datetime import datetime, timezone, timedelta
from itertools import combinations

conn = sqlite3.connect(r'F:\qqsj\data\sports_data.db')
BJT = timezone(timedelta(hours=8))

# ══════════════════════════════════════════════════════════════
# 中文映射表
# ══════════════════════════════════════════════════════════════
LEAGUE_ZH = {
    "nba": "NBA", "csl": "中超联赛", "j1": "日职联", "j2": "日职乙",
    "China - Super League": "中超联赛", "China - League One": "中甲联赛",
    "Japan - J League": "日职联", "Japan - J2/J3 League": "日职乙/丙",
    "Japan - Regional League": "日本地区联赛",
    "Japan - Nadeshiko Division 2 Women": "日本女足联赛2部",
    "Korea Republic - K League 2": "韩K2联", "Korea Republic - K League Women": "韩国女足联赛",
    "Korea Republic - K3 League": "韩国K3联赛", "Korea Republic - K4 League": "韩国K4联赛",
    "Australia - NPL Victoria": "澳维超", "Australia - NPL Queensland": "澳昆超",
    "Australia - NPL New South Wales": "澳新南超", "Australia - NPL South Australia": "澳南超",
    "Australia - NPL Western Australia": "澳西超", "Australia - NPL Capital Territory": "澳首都超",
    "Australia - NPL Northern NSW": "澳北新超", "Australia - NPL Tasmania": "澳塔超",
    "Australia - NPL Victoria Women": "澳维女超",
    "Australia - NPL Queensland Women": "澳昆女超",
    "Australia - NPL South Australia Women": "澳南女超",
    "Australia - New South Wales League 1": "澳新南甲",
    "Australia - New South Wales League 2": "澳新南乙",
    "Australia - Queensland Premier League": "澳昆超联",
    "Australia - Queensland Premier League 2": "澳昆甲",
    "Australia - Queensland Premier League 3": "澳昆乙",
    "Australia - South Australia State League 1": "澳南甲",
    "Australia - Victoria Premier League 1": "澳维甲",
    "Australia - Victoria Premier League 2": "澳维乙",
    "Australia - Western Australia State League 1": "澳西甲",
    "Australia - Tasmania Super League Women": "澳塔女超联",
    "Australia - Northern NSW Reserves League": "澳北新预备队",
    "Australia - NPL Victoria U23": "澳维U23",
    "Australia - NPL Queensland U23": "澳昆U23",
    "Australia - NPL 2 New South Wales U20": "澳新南U20",
    "Australia - NPL New South Wales U20": "澳新南U20",
    "Australia - NPL New South Wales Women": "澳新南女超",
    "Australia - NPL Northern NSW Women": "澳北新女超",
    "Australia - NorZone Premier League": "澳北超",
    "Australia - Big V": "澳大利亚Big V联赛", "Australia - Big V Women": "澳大利亚Big V女子",
    "Australia - NBL1": "澳大利亚NBL1联赛", "Australia - NBL1 Women": "澳大利亚NBL1女子",
    "Norway - Eliteserien": "挪超", "Norway - 1st Division": "挪甲",
    "Norway - 2nd Division": "挪乙", "Norway - 3rd Division": "挪丙",
    "Norway - Toppserien Women": "挪威女足顶级联赛", "Norway - 1st Division Women": "挪威女甲",
    "Sweden - Allsvenskan": "瑞典超", "Sweden - Superettan": "瑞典甲",
    "Sweden - Division 1 Norra": "瑞典北甲", "Sweden - Division 1 Sodra": "瑞典南甲",
    "Sweden - 2nd Division": "瑞典乙", "Sweden - Damallsvenskan": "瑞典女超",
    "Sweden - Elitettan Women": "瑞典女甲",
    "Denmark - Division 1": "丹麦甲", "Denmark - 2nd Division": "丹麦乙",
    "Denmark - 3rd Division": "丹麦丙", "Denmark - Denmark Series": "丹麦丁",
    "Denmark - Elitedivisionen Women": "丹麦女超",
    "Finland - Veikkausliiga": "芬超",
    "Iceland - 3. Deild": "冰岛丙", "Iceland - 1. Deild Women": "冰岛女甲",
    "Iceland - Urvalsdeild Women": "冰岛女超",
    "Estonia - Meistriliiga": "爱沙超", "Estonia - Meistriliiga Women": "爱沙女超",
    "Latvia - Virsliga": "拉脱超", "Lithuania - A Lyga": "立陶甲", "Lithuania - 1 Lyga": "立陶乙",
    "Faroe Islands - Premier League": "法罗超",
    "Brazil - Serie A": "巴甲", "Brazil - Serie B": "巴乙",
    "Brazil - Serie C": "巴丙", "Brazil - Serie D": "巴丁",
    "Brazil - Carioca A2": "里约甲",
    "Argentina - Cup": "阿根廷杯", "Argentina - Primera B Nacional": "阿乙",
    "Argentina - Primera B Metropolitana": "阿大都会乙",
    "Argentina - Primera C Metropolitana": "阿大都会丙",
    "Chile - Primera Division": "智利甲", "Chile - Primera B": "智利乙",
    "Chile - Segunda Division": "智利丙", "Chile - Tercera Division A": "智利丁",
    "Chile - Primera Division Women": "智利女子甲",
    "Chile - LNB Women": "智利女子篮球联赛",
    "Ecuador - Serie A": "厄瓜甲", "Ecuador - Serie B": "厄瓜乙",
    "Peru - Liga 1": "秘鲁甲",
    "Uruguay - Primera Division": "乌拉圭甲", "Uruguay - Segunda Division": "乌拉圭乙",
    "Paraguay - Division Intermedia": "巴拉圭乙",
    "Venezuela - Primera Division": "委内瑞拉甲",
    "USA - MLS Next Pro League": "美职联发展",
    "USA - USL Championship": "美国冠军联赛", "USA - USL League One": "美国联一",
    "USA - National Womens Soccer League": "美国女足联赛",
    "Canada - Premier League": "加拿超",
    "Mexico - Liga de Expansion MX": "墨超发展",
    "Spain - Segunda Division": "西乙", "Spain - Primera Federacion": "西足协甲",
    "Spain - Segunda Federacion": "西足协乙", "Spain - Tercera Division": "西丙",
    "Spain - Segunda FEB": "西班牙篮球乙级", "Spain Tercera FEB": "西班牙篮球丙级",
    "Portugal - Liga 2": "葡甲",
    "Portugal - Nacional Championship Women": "葡萄牙女足联赛",
    "Portugal - Proliga": "葡萄牙篮球甲级",
    "Italy - Serie D": "意丁", "Italy - Primavera 2 U19": "意青乙",
    "Netherlands - Tweede Divisie": "荷丙", "Netherlands - U21 Divisie": "荷U21",
    "Belgium - Women Cup": "比利时女足杯",
    "Croatia - Prva NL": "克罗乙",
    "Czech Republic - First Liga": "捷克甲",
    "Czech Republic - 3. Liga": "捷克丙", "Czech Republic - 4. Liga": "捷克丁",
    "Slovakia - 3. Liga": "斯洛伐克丙",
    "Poland - 2nd Liga": "波兰乙", "Poland - 4th Liga": "波兰丁",
    "Poland - Ekstraliga Women": "波兰女超",
    "Georgia - Erovnuli Liga": "格鲁吉亚超",
    "Austria - Regionalliga Mitte": "奥地丙中",
    "Austria - Regionalliga Ost": "奥地丙东", "Austria - Regionalliga West": "奥地丙西",
    "Austria - Bundesliga Women": "奥地利女超",
    "Austria - Landesliga": "奥地利州联赛",
    "Austria - SuperLiga": "奥地利篮球超级联赛",
    "Switzerland - Promotion League": "瑞士甲级联赛",
    "Morocco - Botola Pro": "摩洛哥超",
    "Ethiopia - Premier League": "埃塞超",
    "South Africa - PSL": "南非超",
    "Bahrain - Premier League": "巴林超",
    "Kuwait - Premier League": "科威特超",
    "Vietnam - V League 2": "越南乙",
    "Philippines - PFL": "菲律宾联",
    "Hong Kong - FA Cup": "香港足总杯",
    "Chinese Taipei - Premier League": "中国台湾企甲",
    "Chinese Taipei - Mulan Football League Women": "中国台湾木兰女足联赛",
    "International - Friendlies": "国际友谊赛",
    "International - Friendlies U21": "国际U21友谊赛",
    "UEFA - Champions League": "欧冠",
    "Ukraine - Persha Liga": "乌克兰甲",
    "Hungary - U19 League": "匈牙利U19",
    "Algeria - Ligue 1": "阿尔及利亚甲",
    "CONCACAF - Champions Cup": "中北美冠",
    "Germany - Bundesliga": "德国篮球甲级",
    "France - Championnat Pro A": "法国篮球甲级",
    "France - LNB Espoirs U21": "法国篮球U21",
    "Italy - Lega A": "意大利篮球甲级",
    "Greek Basket League": "希腊篮球甲级",
    "Turkey - Super League": "土耳其篮球超联",
    "New Zealand - NBL": "新西兰篮球联赛",
    "Argentina - Liga Nacional": "阿根廷篮球国家联赛",
    "Puerto Rico - Superior Nacional": "波多黎各篮球联赛",
    "Venezuela - Superliga Women": "委内瑞拉女子篮球联赛",
    "Uruguay - Liga Femenina": "乌拉圭女子篮球联赛",
    "Lebanon - Lebanese Basketball League": "黎巴嫩篮球联赛",
    "Indonesia - Basketball League": "印尼篮球联赛",
    "Slovenia - 1. SKL": "斯洛文尼亚篮球甲级",
    "Bulgaria - NBL": "保加利亚篮球联赛",
    "Switzerland - NLB": "瑞士篮球乙级",
    "Uganda NBL": "乌干达篮球联赛",
    "El Salvador - Liga Mayor de Baloncesto": "萨尔瓦多篮球联赛",
}

# Read team_zh.py mapping
TEAM_ZH = {}
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("team_zh", r"F:\qqsj\team_zh.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, 'TEAM_ZH'):
        TEAM_ZH = mod.TEAM_ZH
    elif hasattr(mod, 'TEAM_ZH_MAP'):
        TEAM_ZH = mod.TEAM_ZH_MAP
except:
    pass

# Extra manual mappings for missing teams
EXTRA_TEAMS = {
    "qingdao west coast": "青岛西海岸", "shanghai shenhua": "上海申花",
    "chongqing tonglianglong": "重庆铜梁龙", "beijing guoan": "北京国安",
    "chengdu rongcheng": "成都蓉城", "shandong taishan": "山东泰山",
    "sanfrecce hiroshima": "广岛三箭", "kawasaki frontale": "川崎前锋",
    "vissel kobe": "神户胜利船", "kashima antlers": "鹿岛鹿角",
    "cerezo osaka": "大阪樱花", "fc tokyo": "FC东京",
    "avispa fukuoka": "福冈黄蜂", "jef united chiba": "千叶市原",
    "oklahoma city thunder": "俄克拉荷马城雷霆", "san antonio spurs": "圣安东尼奥马刺",
    "athletic club": "竞技俱乐部", "fortaleza": "福塔雷萨",
    "metrostars": "都市之星", "campbelltown city": "坎贝尔敦城",
    "flamengo": "弗拉门戈", "coritiba": "科里蒂巴",
    "al riyadi": "阿尔里亚迪", "sagesse": "智者",
}
TEAM_ZH.update(EXTRA_TEAMS)

def zh_team(name):
    clean = name.replace(" (Corners)", "").replace(" (Bookings)", "")
    suffix = ""
    if "(Corners)" in name: suffix = "（角球）"
    elif "(Bookings)" in name: suffix = "（红黄牌）"
    return TEAM_ZH.get(clean.lower(), TEAM_ZH.get(clean, clean)) + suffix

def zh_league(league):
    return LEAGUE_ZH.get(league, LEAGUE_ZH.get(league.lower(), league))

def zh_market(market, outcome):
    m = {"moneyline": "独赢", "spread": "让球", "total": "大小球", "team_total": "球队大小球"}
    o = {"home": "主胜", "away": "客胜", "draw": "平局", "over": "大", "under": "小"}
    return f"{m.get(market, market)}/{o.get(outcome, outcome)}"

def fmt_bjt(kickoff):
    try:
        s = str(kickoff).replace("Z", "+00:00")
        if "+" not in s and "T" in s:
            s += "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.astimezone(BJT).strftime("%m-%d %H:%M")
    except:
        return str(kickoff)

# ══════════════════════════════════════════════════════════════
# PART 1: 单场推荐单
# ══════════════════════════════════════════════════════════════
print("=" * 70)
print("  🏆 全球体育投注推荐单（单场）")
print(f"  日期：2026-05-30 北京时间13:00 ~ 次日13:00")
print(f"  数据源：Pinnacle Guest API（652场比赛）")
print(f"  统一比赛：713场 | 总推荐：2805条")
print("=" * 70)
print()

# Top 50 by hit_score
rows = conn.execute("""
    SELECT sport_code, league_name, home_team, away_team, kickoff_utc,
           market, outcome, best_odds, best_source,
           value_edge, kelly_fraction, hit_score, confidence, reason
    FROM hit_recommendations WHERE fetch_date='2026-05-30'
    ORDER BY hit_score DESC LIMIT 50
""").fetchall()

for i, r in enumerate(rows, 1):
    sport, league, home, away, kickoff = r[0], r[1], r[2], r[3], r[4]
    market, outcome, odds, src = r[5], r[6], r[7], r[8]
    vedge, kelly, hit, conf, reason = r[9], r[10], r[11], r[12], r[13]
    
    icon = "⚽" if sport in ("football", "soccer") else "🏀"
    lzh = zh_league(league)
    hzh = zh_team(home)
    azh = zh_team(away)
    mzh = zh_market(market, outcome)
    bjt = fmt_bjt(kickoff)
    
    # Star rating
    stars = "⭐" * min(5, max(1, int(hit * 5)))
    
    print(f"{i:2d}. {icon} [{lzh}] {stars}")
    print(f"    {hzh} vs {azh}  开赛:{bjt}(北京)")
    print(f"    推荐: {mzh} @ {odds:.2f}  命中={hit:.3f} 价值差={vedge:+.1%}")
    print()

# Stats
stats = conn.execute("""
    SELECT 
        COUNT(CASE WHEN hit_score >= 0.75 THEN 1 END) as tier1,
        COUNT(CASE WHEN hit_score >= 0.65 AND hit_score < 0.75 THEN 1 END) as tier2,
        COUNT(CASE WHEN hit_score >= 0.55 AND hit_score < 0.65 THEN 1 END) as tier3,
        COUNT(*) as total
    FROM hit_recommendations WHERE fetch_date='2026-05-30'
""").fetchone()
print(f"  命中分分布: ≥0.75={stats[0]}条 | 0.65~0.75={stats[1]}条 | 0.55~0.65={stats[2]}条 | 总计={stats[3]}条")
print()

# ══════════════════════════════════════════════════════════════
# PART 2: 串关推荐单
# ══════════════════════════════════════════════════════════════
print("=" * 70)
print("  🎯 串关推荐单")
print("=" * 70)
print()

# Deduplicate: best pick per match
all_rows = conn.execute("""
    SELECT sport_code, league_name, home_team, away_team, kickoff_utc,
           market, outcome, best_odds, best_source,
           value_edge, kelly_fraction, hit_score, confidence, reason
    FROM hit_recommendations WHERE fetch_date='2026-05-30' AND hit_score >= 0.63
    ORDER BY hit_score DESC
""").fetchall()

seen = {}
for r in all_rows:
    mk = (r[2], r[3], str(r[4]))
    if mk not in seen:
        seen[mk] = r
picks = list(seen.values())
picks.sort(key=lambda x: x[11], reverse=True)

print(f"  去重后独立比赛: {len(picks)} 场 (命中分≥0.63)")
fb = [p for p in picks if p[0] in ("football", "soccer")]
bk = [p for p in picks if p[0] == "basketball"]
print(f"  ⚽足球 {len(fb)} 场 | 🏀篮球 {len(bk)} 场")
print()

def info_line(x):
    icon = "⚽" if x[0] in ("football", "soccer") else "🏀"
    return f"{icon} {zh_league(x[1])} | {zh_team(x[2])} vs {zh_team(x[3])} ({fmt_bjt(x[4])})"

def pick_line(x):
    return f"    {zh_market(x[5],x[6])} @ {x[7]:.2f} 命中分={x[11]:.3f}"

# ── A. 稳胆2串1 ──
print("━" * 70)
print("  📌 A. 稳胆2串1（命中分最高的2场组合）")
print("━" * 70)
print()

top8 = picks[:8]
combos2 = list(combinations(range(len(top8)), 2))[:6]
for ci, (i, j) in enumerate(combos2, 1):
    a, b = top8[i], top8[j]
    codds = a[7] * b[7]
    cprob = a[11] * b[11]
    print(f"  【稳胆{ci}】 2串1  赔率={codds:.2f}  预估命中={cprob:.1%}")
    print(f"    ① {info_line(a)}")
    print(f"       {pick_line(a)}")
    print(f"    ② {info_line(b)}")
    print(f"       {pick_line(b)}")
    print()

# ── B. 跨运动混合2串1 ──
print("━" * 70)
print("  📌 B. 足球+篮球混合2串1（分散风险）")
print("━" * 70)
print()

cross = []
for f in fb[:5]:
    for b in bk[:3]:
        cross.append((f, b, f[11] * b[11]))
cross.sort(key=lambda x: x[2], reverse=True)

for ci, (f, b, cprob) in enumerate(cross[:5], 1):
    codds = f[7] * b[7]
    print(f"  【混合{ci}】 2串1  赔率={codds:.2f}  预估命中={cprob:.1%}")
    print(f"    ⚽ {zh_league(f[1])} | {zh_team(f[2])} vs {zh_team(f[3])} ({fmt_bjt(f[4])})")
    print(f"       {pick_line(f)}")
    print(f"    🏀 {zh_league(b[1])} | {zh_team(b[2])} vs {zh_team(b[3])} ({fmt_bjt(b[4])})")
    print(f"       {pick_line(b)}")
    print()

# ── C. 3串1高赔 ──
print("━" * 70)
print("  📌 C. 3串1 高赔博冷")
print("━" * 70)
print()

high_odds = sorted(picks[:12], key=lambda x: x[7], reverse=True)[:8]
combos3 = list(combinations(range(len(high_odds)), 3))[:4]
for ci, (i, j, k) in enumerate(combos3, 1):
    a, b, c = high_odds[i], high_odds[j], high_odds[k]
    codds = a[7] * b[7] * c[7]
    cprob = a[11] * b[11] * c[11]
    print(f"  【高赔{ci}】 3串1  赔率={codds:.2f}  预估命中={cprob:.1%}")
    for idx, x in enumerate([a, b, c], 1):
        print(f"    {idx}. {info_line(x)}")
        print(f"       {pick_line(x)}")
    print()

# ── D. 容错串关 ──
print("━" * 70)
print("  📌 D. 容错串关（降低风险）")
print("━" * 70)
print()

def m_of_n_prob(probs, m):
    n = len(probs)
    total = 0.0
    for k in range(m, n + 1):
        for indices in combinations(range(n), k):
            p = 1.0
            for i in range(n):
                p *= probs[i] if i in indices else (1 - probs[i])
            total += p
    return total

def print_m_of_n(picks_list, m, n, label):
    combo = picks_list[:n]
    if len(combo) < n:
        return
    codds = 1
    for p in combo:
        codds *= p[7]
    probs = [p[11] for p in combo]
    survival = m_of_n_prob(probs, m)
    
    print(f"  【{label}】 {m}串{n}容错  单注赔率={codds:.2f}")
    for idx, p in enumerate(combo, 1):
        icon = "⚽" if p[0] in ("football", "soccer") else "🏀"
        print(f"    {idx}. {icon} {zh_league(p[1])} | {zh_team(p[2])} vs {zh_team(p[3])} ({fmt_bjt(p[4])})")
        print(f"       {pick_line(p)}")
    print(f"    ✅ ≥{m}场命中概率: {survival:.1%}")
    print()

print_m_of_n(picks, 2, 3, "3串4容错1场")
print_m_of_n(picks, 3, 4, "4串5容错1场")
print_m_of_n(picks, 2, 4, "4串11容错2场")

# ── E. 亚洲联赛专场 ──
print("━" * 70)
print("  📌 E. 亚洲联赛专场串关（中超+日职+韩K）")
print("━" * 70)
print()

asian = [p for p in picks if p[1].lower() in ("csl", "j1", "j2", "japan - j league", "japan - j2/j3 league",
    "china - super league", "korea republic - k league 2", "korea republic - k3 league",
    "korea republic - k4 league")]
if len(asian) >= 2:
    for ci, (i, j) in enumerate(list(combinations(range(len(asian)), 2))[:6], 1):
        a, b = asian[i], asian[j]
        codds = a[7] * b[7]
        cprob = a[11] * b[11]
        print(f"  【亚洲{ci}】 2串1  赔率={codds:.2f}  预估命中={cprob:.1%}")
        print(f"    ① {info_line(a)}")
        print(f"       {pick_line(a)}")
        print(f"    ② {info_line(b)}")
        print(f"       {pick_line(b)}")
        print()
    
    if len(asian) >= 3:
        print_m_of_n(asian, 2, 3, "亚洲3串4容错1场")

# ── Footer ──
print("=" * 70)
print("  ⚠️ 风险提示")
print("  • 串关赔率虽高，但命中难度成倍增加")
print("  • 建议单注投注额不超过总资金2%（Kelly公式）")
print("  • 2串1=选2场全中赢 | 3串1=选3场全中赢")
print("  • 3串4=容错1场 | 4串5=容错1场 | 4串11=容错2场")
print("=" * 70)

conn.close()
