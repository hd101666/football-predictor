# ll: skip
import sys, os, json, sqlite3, math, re
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB = r'F:\qqsj\data\sports_data.db'
OUT = r'F:\qqsj\推荐单_K值_终版v3_2026-06-06.md'
NOW = datetime.now().strftime('%Y-%m-%d %H:%M')
TODAY = datetime.now().strftime('%Y-%m-%d')

# ============ CN→EN Team Name Map ============
CN_EN = {
    # 英超
    "阿森纳":"Arsenal","曼城":"Man City","曼彻斯特城":"Man City",
    "利物浦":"Liverpool","切尔西":"Chelsea","曼联":"Man United","曼彻斯特联":"Man United",
    "热刺":"Tottenham","托特纳姆热刺":"Tottenham",
    "纽卡斯尔":"Newcastle","纽卡斯尔联":"Newcastle",
    "阿斯顿维拉":"Aston Villa","布莱顿":"Brighton",
    "布伦特福德":"Brentford","富勒姆":"Fulham",
    "水晶宫":"Crystal Palace","埃弗顿":"Everton",
    "伯恩茅斯":"Bournemouth","诺丁汉森林":"Forest",
    "西汉姆":"West Ham","西汉姆联":"West Ham",
    "狼队":"Wolves","莱斯特城":"Leicester",
    "利兹联":"Leeds","南安普顿":"Southampton","伊普斯维奇":"Ipswich",
    # 西甲
    "皇家马德里":"Real Madrid","皇马":"Real Madrid",
    "巴塞罗那":"Barcelona","巴萨":"Barcelona",
    "马德里竞技":"Atletico","马竞":"Atletico",
    "塞维利亚":"Sevilla","皇家社会":"Real Sociedad",
    "比利亚雷亚尔":"Villarreal","贝蒂斯":"Betis",
    "毕尔巴鄂竞技":"Athletic","瓦伦西亚":"Valencia","赫罗纳":"Girona",
    # 德甲
    "拜仁慕尼黑":"Bayern","拜仁":"Bayern",
    "多特蒙德":"Dortmund","勒沃库森":"Leverkusen",
    "莱比锡":"RB Leipzig","莱比锡红牛":"RB Leipzig",
    "斯图加特":"Stuttgart","法兰克福":"Frankfurt",
    "弗赖堡":"Freiburg","霍芬海姆":"Hoffenheim",
    "门兴格拉德巴赫":"Gladbach","门兴":"Gladbach",
    "美因茨":"Mainz","沃尔夫斯堡":"Wolfsburg",
    # 意甲
    "国际米兰":"Inter","国米":"Inter",
    "AC米兰":"AC Milan","米兰":"AC Milan",
    "尤文图斯":"Juventus","尤文":"Juventus",
    "那不勒斯":"Napoli","罗马":"Roma",
    "拉齐奥":"Lazio","亚特兰大":"Atalanta","佛罗伦萨":"Fiorentina",
    # 法甲
    "巴黎圣日耳曼":"Paris SG","巴黎":"Paris SG","大巴黎":"Paris SG",
    "马赛":"Marseille","里昂":"Lyon","里尔":"Lille",
    "摩纳哥":"Monaco","尼斯":"Nice",
    # 葡超/荷甲
    "本菲卡":"Benfica","波尔图":"Porto","里斯本竞技":"Sporting",
    "阿贾克斯":"Ajax","埃因霍温":"PSV","费耶诺德":"Feyenoord",
    # 俄超
    "圣彼得堡泽尼特":"Zenit","泽尼特":"Zenit",
    "莫斯科中央陆军":"CSKA","斯巴达克莫斯科":"Spartak",
    "莫斯科火车头":"Lokomotiv",
    # 日职
    "鹿岛鹿角":"Kashima","浦和红钻":"Urawa",
    "横滨水手":"Yokohama","川崎前锋":"Kawasaki",
    "大阪钢巴":"G Osaka","大阪樱花":"C Osaka",
    "东京FC":"FC Tokyo","柏太阳神":"Kashiwa",
    "名古屋鲸八":"Nagoya","神户胜利船":"Vissel Kobe",
    "广岛三箭":"Hiroshima","清水心跳":"Shimizu",
    # 国家队 - 精确匹配 national_team_elo
    "英格兰":"England","法国":"France","德国":"Germany",
    "西班牙":"Spain","意大利":"Italy","巴西":"Brazil",
    "阿根廷":"Argentina","葡萄牙":"Portugal","荷兰":"Netherlands",
    "比利时":"Belgium","克罗地亚":"Croatia",
    "日本":"Japan","韩国":"South Korea","中国":"China",
    "乌拉圭":"Uruguay","哥伦比亚":"Colombia","墨西哥":"Mexico","智利":"Chile",
    "瑞士":"Switzerland","丹麦":"Denmark","瑞典":"Sweden",
    "挪威":"Norway","土耳其":"Turkey","波兰":"Poland",
    "奥地利":"Austria","塞尔维亚":"Serbia","捷克":"Czech Republic",
    "俄罗斯":"Russia","乌克兰":"Ukraine","威尔士":"Wales",
    "苏格兰":"Scotland","爱尔兰":"Ireland","希腊":"Greece",
    "美国":"United States","加拿大":"Canada","澳大利亚":"Australia",
    "埃及":"Egypt","尼日利亚":"Nigeria","加纳":"Ghana",
    "喀麦隆":"Cameroon","摩洛哥":"Morocco","突尼斯":"Tunisia",
    "沙特阿拉伯":"Saudi Arabia","伊朗":"Iran","卡塔尔":"Qatar",
    # 更多国家队
    "匈牙利":"Hungary","斯洛伐克":"Slovakia","斯洛文尼亚":"Slovenia",
    "罗马尼亚":"Romania","保加利亚":"Bulgaria",
    "芬兰":"Finland","冰岛":"Iceland","白俄罗斯":"Belarus",
    "北爱尔兰":"Northern Ireland","塞浦路斯":"Cyprus","卢森堡":"Luxembourg",
    "以色列":"Israel","格鲁吉亚":"Georgia","亚美尼亚":"Armenia",
    "阿塞拜疆":"Azerbaijan","哈萨克斯坦":"Kazakhstan",
    "法罗群岛":"Faroe Islands","马耳他":"Malta","爱沙尼亚":"Estonia",
    "拉脱维亚":"Latvia","立陶宛":"Lithuania","黑山":"Montenegro",
    "波黑":"Bosnia","阿尔巴尼亚":"Albania","北马其顿":"North Macedonia",
    "科索沃":"Kosovo","摩尔多瓦":"Moldova",
    "秘鲁":"Peru","巴拉圭":"Paraguay","委内瑞拉":"Venezuela",
    "厄瓜多尔":"Ecuador","玻利维亚":"Bolivia",
    "巴拿马":"Panama","哥斯达黎加":"Costa Rica","洪都拉斯":"Honduras",
    "萨尔瓦多":"El Salvador","危地马拉":"Guatemala",
    "塞内加尔":"Senegal","阿尔及利亚":"Algeria",
    "南非":"South Africa","刚果":"Congo",
    "日本(青年)":"Japan",
}
# 通用后缀去除
suffixes = ["(女)","(青年)","U21","U23","U20","U19","U17","B队","B 队","后备队"]

def to_en_name(cn_name):
    """中文队名→英文队名，支持后缀处理和模糊匹配"""
    # 精确匹配
    if cn_name in CN_EN:
        return CN_EN[cn_name]
    # 去除后缀再试
    clean = cn_name
    for s in suffixes:
        clean = clean.replace(s, "").strip()
    if clean in CN_EN:
        return CN_EN[clean]
    return None

# ============ Load Lambda Map ============
with open(r'F:\qqsj\_league_lambda_map.json', encoding='utf-8') as f:
    lambda_data = json.load(f)
lambda_map = lambda_data  # key=联赛名, value=dict

# ============ Load DB Data ============
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Load ELO dicts
c.execute("SELECT team_name, elo_rating FROM club_elo")
club_elo = {r[0]: r[1] for r in c.fetchall()}
c.execute("SELECT team_name, elo_rating FROM national_team_elo")
nat_elo = {r[0]: r[1] for r in c.fetchall()}

# Load Understat xG dict
c.execute("SELECT team_name, league, xg, xga, matches FROM understat_team_stats WHERE matches > 0")
understat = {}
for r in c.fetchall():
    understat[r[0]] = {"xg": r[2], "xga": r[3], "matches": r[4], "league": r[1]}

# Load qiety odds into dict by match_id (schema: match_id, bookmaker, market_type, line, odds_home, odds_draw, odds_away, over_odds, under_odds)
c.execute("SELECT match_id, market_type, line, odds_home, odds_draw, odds_away, over_odds, under_odds FROM qiety_odds")
qiety_odds_data = {}
for r in c.fetchall():
    mid = r[0]
    if mid not in qiety_odds_data:
        qiety_odds_data[mid] = []
    mkt = r[1]  # 1x2, ah, ou
    line = r[2]
    # Convert each market into direction entries
    if mkt == '1x2':
        if r[3]: qiety_odds_data[mid].append({"market": "1X2", "outcome": "主胜", "odds": r[3], "handicap": None})
        if r[4]: qiety_odds_data[mid].append({"market": "1X2", "outcome": "平局", "odds": r[4], "handicap": None})
        if r[5]: qiety_odds_data[mid].append({"market": "1X2", "outcome": "客胜", "odds": r[5], "handicap": None})
    elif mkt == 'ah':
        if r[3]: qiety_odds_data[mid].append({"market": "亚盘", "outcome": "主队", "odds": r[3], "handicap": line})
        if r[5]: qiety_odds_data[mid].append({"market": "亚盘", "outcome": "客队", "odds": r[5], "handicap": line})
    elif mkt == 'ou':
        if r[6]: qiety_odds_data[mid].append({"market": "大小球", "outcome": "大球", "odds": r[6], "handicap": line})
        if r[7]: qiety_odds_data[mid].append({"market": "大小球", "outcome": "小球", "odds": r[7], "handicap": line})

# Load unified odds for cross-source
c.execute("SELECT unified_id, source, market, outcome, odds_value, handicap FROM unified_odds WHERE odds_value > 1")
unified = {}
for r in c.fetchall():
    uid = r[0]
    if uid not in unified:
        unified[uid] = []
    unified[uid].append({"source": r[1], "market": r[2], "outcome": r[3], "odds": r[4], "handicap": r[5]})

# Load matches
c.execute("""
SELECT match_id, league, home_team, away_team, kickoff_time, status 
FROM qiety_matches WHERE status != 'finished'
""")
matches = list(c.fetchall())

print(f"Loaded: {len(club_elo)} club ELO, {len(nat_elo)} nat ELO, {len(understat)} understat teams")
print(f"Loaded: {len(matches)} matches, {len(qiety_odds_data)} with odds")

# ============ Poisson ============
def poisson_pmf(k, lam):
    if lam <= 0:
        return 0.0 if k > 0 else 1.0
    return math.exp(-lam) * lam**k / math.factorial(k)

def match_probs(lambda_h, lambda_a, max_g=8):
    """返回 主胜/平/客胜 概率，以及 0-max_g 球的总分概率"""
    grid = {}
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            grid[(i, j)] = poisson_pmf(i, lambda_h) * poisson_pmf(j, lambda_a)
    p_home = sum(grid[(i, j)] for (i, j) in grid if i > j)
    p_draw = sum(grid[(i, j)] for (i, j) in grid if i == j)
    p_away = sum(grid[(i, j)] for (i, j) in grid if i < j)
    return p_home, p_draw, p_away, grid

def total_probs(grid, line):
    """给定总球数分布和盘口线，返回大球/小球概率"""
    p_over = sum(p for (i, j), p in grid.items() if i + j > line)
    p_under = sum(p for (i, j), p in grid.items() if i + j < line)
    # push = i+j == line
    return p_over, p_under

def total_probs_half_line(grid, line):
    """盘口线可能是 .5 / .25 / .75 等"""
    # line 如 2.5: >2.5 大球, <2.5 小球
    p_over = sum(p for (i, j), p in grid.items() if i + j > line)
    p_under = 1.0 - p_over  # 含push（半盘没有push）
    return p_over, p_under

# ============ ELO → Win Rate ============
def elo_to_probs(elo_h, elo_a):
    """ELO差值→主队期望胜率→胜平负概率"""
    diff = elo_a - elo_h
    E = 1.0 / (1.0 + 10.0 ** (diff / 400.0))
    draw_ratio = 0.26
    p_home = E * (1 - draw_ratio)
    p_draw = draw_ratio
    p_away = (1 - E) * (1 - draw_ratio)
    return p_home, p_draw, p_away

def find_elo(home_cn, away_cn, is_national=False):
    """查找主客队ELO评分"""
    h_en = to_en_name(home_cn)
    a_en = to_en_name(away_cn)
    elo_src = club_elo if not is_national else nat_elo
    h_elo, a_elo = None, None
    
    if h_en:
        if h_en in elo_src: h_elo = elo_src[h_en]
        else:  # fuzzy
            for name, v in elo_src.items():
                if h_en.lower() in name.lower() or name.lower() in h_en.lower():
                    h_elo = v; break
    if a_en:
        if a_en in elo_src: a_elo = elo_src[a_en]
        else:
            for name, v in elo_src.items():
                if a_en.lower() in name.lower() or name.lower() in a_en.lower():
                    a_elo = v; break
    return h_elo, a_elo

def find_xg(home_cn, away_cn):
    """查找主客队xG"""
    h_en = to_en_name(home_cn)
    a_en = to_en_name(away_cn)
    h_xg, a_xg = None, None
    if h_en:
        if h_en in understat: h_xg = understat[h_en]
        else:
            for name, v in understat.items():
                if h_en.lower() in name.lower() or name.lower() in h_en.lower():
                    h_xg = v; break
    if a_en:
        if a_en in understat: a_xg = understat[a_en]
        else:
            for name, v in understat.items():
                if a_en.lower() in name.lower() or name.lower() in a_en.lower():
                    a_xg = v; break
    return h_xg, a_xg

# ============ Main Loop ============
recommendations = []
virtual_keywords = ["VS-", "梦幻对垒", "NBA 2K", "PANDA", "EAFC", "电竞"]
is_nt = lambda league: any(kw in league for kw in ["国际友谊", "世界杯", "欧洲杯", "亚洲杯", "美洲杯", "资格赛", "土伦"])

for m in matches:
    mid, league, ht, at, ko, status = m
    # Filter virtual
    if any(kw in league for kw in virtual_keywords):
        continue
    if status in ("finished", "canceled"):
        continue
    
    # Get odds
    my_odds = qiety_odds_data.get(mid, [])
    my_uid = mid  # unified match uses match_id
    
    # Check unified for cross-source
    uni_odds = unified.get(my_uid, [])
    uni_sources = set(o["source"] for o in uni_odds)
    
    # Determine if national team match
    national = is_nt(league)
    
    # Get lambda
    lam = lambda_map.get(league, {"avg_hg": 1.45, "avg_ag": 1.15, "avg_total": 2.60})
    lambda_h = lam.get("avg_hg", 1.45)
    lambda_a = lam.get("avg_ag", 1.15)
    lam_source = "联赛λ" if league in lambda_map else "默认"
    
    # Try xG
    h_xg, a_xg = find_xg(ht, at)
    has_xg = False
    if h_xg and a_xg:
        # Use per-match xG
        lambda_h = h_xg["xg"] / h_xg["matches"] if h_xg["matches"] else lambda_h
        lambda_a = a_xg["xga"] / a_xg["matches"] if a_xg["matches"] else lambda_a
        lam_source = "xG"
        has_xg = True
    
    # Try ELO
    h_elo, a_elo = find_elo(ht, at, national)
    has_elo = h_elo is not None and a_elo is not None
    
    # Poisson probs
    p_h, p_d, p_a, grid = match_probs(lambda_h, lambda_a)
    
    # For each available direction, compute K
    best_k = -999
    best_rec = None
    
    for o in my_odds:
        odds = o["odds"]
        market = o["market"]
        outcome = o["outcome"]
        handicap = o["handicap"]
        if odds <= 1.0:
            continue
        
        # P_book from odds
        p_book = 1.0 / odds * 0.95  # adjust for book margin
        p_book = min(0.95, max(0.05, p_book))
        
        # P_elo
        if has_elo:
            ph_e, pd_e, pa_e = elo_to_probs(h_elo, a_elo)
            if outcome in ("Home", "主胜", "主队"):
                p_elo = ph_e
            elif outcome in ("Draw", "平局"):
                p_elo = pd_e
            elif outcome in ("Away", "客胜", "客队"):
                p_elo = pa_e
            else:
                p_elo = p_book  # fallback for OU
            elo_label = "真实"
        else:
            p_elo = p_book
            elo_label = "近似"
        
        # P_poisson
        if market == "1X2" or market == "match_winner":
            if outcome in ("Home", "主胜", "主队"):
                p_poisson = p_h
            elif outcome in ("Draw", "平局"):
                p_poisson = p_d
            else:
                p_poisson = p_a
        elif market in ("total", "totals", "总局") or "总" in market:
            if handicap is not None:
                p_over, p_under = total_probs_half_line(grid, float(handicap))
                if outcome in ("Over", "大", "大球"):
                    p_poisson = p_over
                else:
                    p_poisson = p_under
            else:
                continue
        elif market in ("asian_handicap", "handicap", "让球") or "让球" in market:
            # Approximate with 1X2
            if outcome in ("Home", "主胜", "主队"):
                p_poisson = p_h
            elif outcome in ("Away", "客胜", "客队"):
                p_poisson = p_a
            else:
                p_poisson = p_d
        elif market in ("team_total", "team_total/over", "team_total/under"):
            # Approximate
            p_poisson = p_h if "Home" in outcome or "主" in outcome else p_a
        else:
            continue  # unknown market
        
        # Fusion
        p_fusion = 0.50 * p_book + 0.30 * p_poisson + 0.20 * p_elo
        
        # Kelly
        if odds <= 1.0:
            continue
        K = (p_fusion * odds - 1) / (odds - 1)
        K_q = K * 0.25
        
        # Direction label
        dir_label = market
        if outcome:
            dir_label = f"{market}/{outcome}"
        
        rec = {
            "league": league, "home": ht, "away": at, "ko": ko,
            "market": market, "outcome": outcome, "odds": odds,
            "handicap": handicap, "K": K, "K14": K_q,
            "p_book": p_book, "p_poisson": p_poisson, "p_elo": p_elo,
            "p_fusion": p_fusion, "lam_source": lam_source,
            "elo_label": elo_label, "has_xg": has_xg, "has_elo": has_elo,
            "n_sources": len(uni_sources),
            "sources": ", ".join(uni_sources) if uni_sources else "qiety_yb",
        }
        
        if K > best_k:
            best_k = K
            best_rec = rec
    
    # Only keep best direction per match
    if best_rec and best_k > -999:
        recommendations.append(best_rec)

# ============ Sort & Grade ============
recommendations.sort(key=lambda x: x["K"], reverse=True)

grades = {"S": [], "A": [], "B": [], "C": [], "D": []}
for r in recommendations:
    K = r["K"]
    odds = r["odds"]
    ns = r["n_sources"]
    if K >= 0.10 and 1.5 <= odds <= 3.5 and ns >= 2:
        grades["S"].append(r)
    elif K >= 0.08 and 1.5 <= odds <= 4.0:
        grades["A"].append(r)
    elif K >= 0.03:
        grades["B"].append(r)
    elif K > 0:
        grades["C"].append(r)
    else:
        grades["D"].append(r)

# ============ Output ============
lines = []
lines.append(f"# 🔥 K值推荐单 终版 v3")
lines.append(f"## 生成时间: {NOW}")
lines.append(f"## 数据基准: 企鹅体育(盘口) + 真实ELO(630队) + xG(156队/6联赛) + 联赛λ(109联赛)")
lines.append("")
lines.append(f"## 📊 数据概况")
lines.append(f"- 有效比赛: {len(recommendations)} 个方向(Max)")
lines.append(f"- S级: {len(grades['S'])} | A级: {len(grades['A'])} | B级: {len(grades['B'])} | C级: {len(grades['C'])} | 负K: {len(grades['D'])}")
elo_count = sum(1 for r in recommendations if r["has_elo"])
xg_count = sum(1 for r in recommendations if r["has_xg"])
lam_count = sum(1 for r in recommendations if r["lam_source"] == "联赛λ")
lines.append(f"- 有真实ELO: {elo_count}/{len(recommendations)} ({100*elo_count/max(1,len(recommendations)):.1f}%)")
lines.append(f"- 有真实xG: {xg_count}/{len(recommendations)} ({100*xg_count/max(1,len(recommendations)):.1f}%)")
lines.append(f"- 有联赛λ: {lam_count}/{len(recommendations)} ({100*lam_count/max(1,len(recommendations)):.1f}%)")
lines.append("")

def emit_recommendations(grade_label, recs, max_count=999):
    if not recs:
        return
    lines.append(f"## {grade_label}")
    lines.append("")
    for i, r in enumerate(recs[:max_count], 1):
        hand = f" | 盘口线:{r['handicap']}(qiety_yb)" if r['handicap'] else ""
        lines.append(f"{i}. [{r['league']}] {r['home']} vs {r['away']} ⏰{r['ko']}")
        lines.append(f"    → {r['market']}/{r['outcome']} | 赔率:{r['odds']:.2f}{hand} | {r['n_sources']}源")
        lines.append(f"    P_book={r['p_book']:.4f} P_poisson={r['p_poisson']:.4f} P_elo={r['p_elo']:.4f}({r['elo_label']}) P_fusion={r['p_fusion']:.4f}")
        lines.append(f"    K={r['K']:.4f} K_1/4={r['K14']:.4f}")
        lines.append(f"    Lambda: {r['lam_source']}")
        lines.append(f"    数据源: {r['sources']}")
        lines.append("")

emit_recommendations("🔥 S级推荐", grades["S"])
emit_recommendations("📌 A级推荐", grades["A"], 30)
emit_recommendations("💡 B级推荐", grades["B"], 10)
emit_recommendations("⚪ C级推荐", grades["C"], 5)

# Forbidden zone
d_recs = [r for r in recommendations if r["K"] < -0.05]
if d_recs:
    lines.append("---")
    lines.append("## ⛔ 禁入名单")
    lines.append("")
    for i, r in enumerate(d_recs[:15], 1):
        lines.append(f"{i}. [{r['league']}] {r['home']}vs{r['away']} → {r['market']}/{r['outcome']} | K={r['K']:.4f} ⏰{r['ko']}")

# Parlay
s_recs = grades["S"]
if len(s_recs) >= 2:
    lines.append("")
    lines.append("---")
    lines.append("## 🎯 S级串关建议")
    lines.append("")
    for i in range(min(len(s_recs), 8)):
        for j in range(i + 1, min(len(s_recs), 8)):
            r1, r2 = s_recs[i], s_recs[j]
            odd = r1["odds"] * r2["odds"]
            lines.append(f"- {r1['home']}vs{r1['away']}({r1['market']}@{r1['odds']:.2f}) × {r2['home']}vs{r2['away']}({r2['market']}@{r2['odds']:.2f}) = {odd:.2f}")

# Budget
lines.append("")
lines.append("---")
lines.append("## 💰 仓位分配 (10u预算)")
lines.append("")
lines.append("| 类型 | 预算 | 建议 |")
lines.append("|------|------|------|")
s_count = min(len(s_recs), 10)
a_count = min(len(grades["A"]), 20)
lines.append(f"| S级单关 | {s_count * 0.15:.1f}u | {s_count}场 × 0.15u |")
lines.append(f"| A级单关 | {a_count * 0.08:.1f}u | {a_count}场 × 0.08u |")
parlay_u = 2.0 if len(s_recs) >= 2 else 0
lines.append(f"| 串关 | {parlay_u:.1f}u | S级2串1 |")
single_total = s_count * 0.15 + a_count * 0.08
reserve = 10.0 - single_total - parlay_u
lines.append(f"| 预留 | {reserve:.1f}u | 临场追加 |")
lines.append(f"| **合计** | **{single_total + parlay_u + reserve:.1f}u** | |")

# Final stats
lines.append("")
lines.append("---")
lines.append("## 📈 最终统计")
lines.append(f"- S级: {len(grades['S'])} | A级: {len(grades['A'])} | B级: {len(grades['B'])} | C级: {len(grades['C'])}")
lines.append(f"- 真实ELO匹配率: {100*elo_count/max(1,len(recommendations)):.1f}%")
lines.append(f"- 真实xG匹配率: {100*xg_count/max(1,len(recommendations)):.1f}%")
lines.append(f"- 联赛λ覆盖率: {100*lam_count/max(1,len(recommendations)):.1f}%")

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"\nOutput saved to {OUT}")
print(f"Total recommendations: {len(recommendations)}")
print(f"S:{len(grades['S'])} A:{len(grades['A'])} B:{len(grades['B'])} C:{len(grades['C'])}")
print(f"ELO real: {elo_count}/{len(recommendations)} ({100*elo_count/max(1,len(recommendations)):.1f}%)")
print(f"xG real: {xg_count}/{len(recommendations)} ({100*xg_count/max(1,len(recommendations)):.1f}%)")

conn.close()
