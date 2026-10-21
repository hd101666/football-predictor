# -*- coding: utf-8 -*-
"""生成全中文投注单并写入命中系统"""
import sqlite3, sys, os, argparse
from datetime import datetime, timezone, timedelta
sys.stdout.reconfigure(encoding='utf-8')

# ── 参数解析 ──────────────────────────────────────────────
_parser = argparse.ArgumentParser(description='生成投注单')
_parser.add_argument('--date', default=None, help='YYYY-MM-DD，默认今日+次日')
_parser.add_argument('--limit', type=int, default=10, help='推荐条数上限（默认10）')
_args = _parser.parse_args()

_BJT = timezone(timedelta(hours=8))
_today    = datetime.now(timezone.utc).astimezone(_BJT).strftime('%Y-%m-%d')
_tomorrow = (datetime.now(timezone.utc).astimezone(_BJT) + timedelta(days=1)).strftime('%Y-%m-%d')

if _args.date:
    _date_filter = f"fetch_date = '{_args.date}'"
    _display_date = _args.date
else:
    _date_filter = f"fetch_date IN ('{_today}', '{_tomorrow}')"
    _display_date = f"{_today}~{_tomorrow}"

# ── 联赛中文映射 ──────────────────────────────────────────
LEAGUE_CN = {
    'Spain - Segunda Division':                 '西班牙乙级联赛',
    'Spain - La Liga':                          '西班牙甲级联赛',
    'Spain - ACB':                              '西班牙ACB篮球联赛',
    'Italy - Serie A':                          '意大利甲级联赛',
    'Italy - Serie B':                          '意大利乙级联赛',
    'Italy - Lega Basket Serie A':              '意大利篮球甲级联赛',
    'Germany - Bundesliga':                     '德国甲级联赛',
    'Germany - 2. Bundesliga':                  '德国乙级联赛',
    'Germany - Bundesliga (Basketball)':        '德国篮球甲级联赛',
    'France - Ligue 1':                         '法国甲级联赛',
    'France - Ligue 2':                         '法国乙级联赛',
    'France - LNB Pro A':                       '法国篮球职业联赛',
    'England - Premier League':                 '英格兰超级联赛',
    'England - Championship':                   '英格兰冠军联赛',
    'Portugal - Primeira Liga':                 '葡萄牙超级联赛',
    'Portugal - Liga Portuguesa de Basquetebol':'葡萄牙篮球甲级联赛',
    'Portugal - Campeonato de Portugal Prio':   '葡萄牙锦标赛',
    'Turkey - Super League':                    '土耳其超级篮球联赛',
    'Turkey - Super Lig':                       '土耳其超级联赛',
    'Greece - Super League':                    '希腊超级联赛',
    'Greek Basket League':                      '希腊篮球甲级联赛',
    'Netherlands - Eredivisie':                 '荷兰甲级联赛',
    'Belgium - First Division A':               '比利时甲级联赛',
    'Russia - VTB United League':               'VTB联合篮球联赛',
    'Israel - Premier League':                  '以色列篮球超级联赛',
    'Iceland - Cup':                            '冰岛杯',
    'Sweden - Superettan':                      '瑞典乙级联赛',
    'Norway - Eliteserien':                     '挪威甲级联赛',
    'USA - MLS':                                '美国职业足球大联盟',
    'USA - USL Championship':                   '美国次级足球联赛(USL)',
    'USA - MLS Next Pro League':                '美国MLS次级联赛',
    'NBA':                                      'NBA职业篮球',
    'WNBA':                                     'WNBA女子职业篮球',
    'Brazil - Serie A':                         '巴西甲级联赛',
    'Brazil - Serie B':                         '巴西乙级联赛',
    'Brazil - LBF Women':                       '巴西女子篮球联赛',
    'Brazil - NBB':                             '巴西全国篮球联赛',
    'Argentina - Primera Division':             '阿根廷甲级联赛',
    'Argentina - Liga A':                       '阿根廷篮球甲级联赛',
    'Chile - LNB':                              '智利篮球联赛',
    'Puerto Rico - Superior Nacional':          '波多黎各超级篮球联赛',
    'Mexico - Liga MX':                         '墨西哥甲级联赛',
    'Japan - J1 League':                        '日本J1联赛',
    'China - Super League':                     '中国足球超级联赛',
    'China - CBA':                              'CBA职业篮球联赛',
    'Australia - A-League':                     '澳大利亚职业联赛',
    'Australia - NBL':                          '澳大利亚篮球联赛',
    'New Zealand - NBL':                        '新西兰篮球联赛',
    'Lebanon - Division 1':                     '黎巴嫩篮球甲级联赛',
    'Africa - BAL':                             '非洲篮球联赛',
    'Rwanda - National League':                 '卢旺达全国篮球联赛',
    'Lithuania - LKL':                          '立陶宛篮球甲级联赛',
    'Poland - Basketball League':               '波兰篮球联赛',
    'Serbia - Super League':                    '塞尔维亚篮球超级联赛',
    'Croatia - Premier League':                 '克罗地亚篮球甲级联赛',
    'Taiwan - T1 League':                       '台湾T1篮球联赛',
    'FIFA - World Cup':                         'FIFA世界杯',
    'FIFA - World Cup Qualifiers Europe Women': '女足世界杯欧洲预选赛',
    'Europe - Champions League':                '欧洲冠军联赛',
    'Europe - Europa League':                   '欧洲联赛',
    'Euroleague Basketball':                    '欧洲篮球冠军联赛',
    'ABA League':                               'ABA篮球联赛',
    'VTB United League':                        'VTB联合篮球联赛',
    'BNXT League':                              'BNXT篮球联赛',
}

# ── 球队中文映射 ──────────────────────────────────────────
TEAM_CN = {
    # 足球 - 西班牙
    'Malaga': '马拉加', 'Las Palmas': '拉斯帕尔马斯',
    'Barcelona': '巴塞罗那', 'Real Madrid': '皇家马德里',
    'Atletico Madrid': '马德里竞技', 'Sevilla': '塞维利亚',
    'Valencia': '巴伦西亚', 'Almeria': '阿尔梅里亚',
    'Castellon': '卡斯特利翁',
    # 足球 - 意大利
    'Virtus Roma': '维尔图斯罗马', 'Gema Montecatini': '热马蒙特卡蒂尼',
    'Elachem Vigevano 1955': '维格瓦诺埃拉赫姆', 'Juvecaserta 2021': '卡塞尔塔青年',
    # 足球 - 美国
    'Phoenix Rising': '凤凰崛起', 'Louisville City': '路易维尔城',
    'Monterey Bay': '蒙特雷湾', 'Sporting Club Jacksonville': '杰克逊维尔体育俱乐部',
    'Vancouver Whitecaps II': '温哥华白帽二队', 'North Texas': '北德克萨斯',
    # 足球 - 葡萄牙
    'Leca': '莱卡FC', 'Vitoria Sernache': '维多利亚塞尔纳谢',
    'SL Benfica': '本菲卡', 'FC Porto': '波尔图',
    # 足球 - 巴西
    'Ceara': '塞阿拉', 'Avai': '阿瓦伊',
    'Sport Recife': '雷西费体育', 'Athletic Club': '竞技俱乐部',
    'Nautico': '诺迪科', 'Fortaleza': '福塔莱萨',
    'Ponte Preta': '庞特普雷塔', 'Cuiaba': '库亚巴',
    # 足球 - 冰岛
    'Afturelding': '阿夫图雷丁', 'Stjarnan': '斯蒂亚尔南',
    # 篮球 - 西班牙ACB
    'Valencia BC': '巴伦西亚篮球', 'Club Joventut Badalona': '巴达洛纳青春',
    'La Laguna Tenerife': '特内里费', 'Barcelona (Basketball)': '巴塞罗那篮球',
    # 篮球 - 波多黎各
    'Criollos de Caguas': '卡瓜斯土著', 'Mets de Guaynabo': '瓜伊纳沃都市',
    'Gigantes de Carolina': '卡罗莱纳巨人', 'Atleticos de San German': '圣日尔曼竞技',
    'Vaqueros de Bayamon': '巴亚蒙牛仔', 'Capitanes de Arecibo': '阿雷西博队长',
    'Piratas de Quebradillas': '克布拉迪利亚斯海盗', 'Leones de Ponce': '蓬塞雄狮',
    # 篮球 - WNBA
    'Seattle Storm': '西雅图风暴', 'Los Angeles Sparks': '洛杉矶火花',
    'Chicago Sky': '芝加哥天空', 'Atlanta Dream': '亚特兰大梦想',
    'Minnesota Lynx': '明尼苏达山猫', 'Dallas Wings': '达拉斯银翼',
    'Golden State Valkyries': '金州女武神', 'Phoenix Mercury': '菲尼克斯水星',
    'New York Liberty': '纽约自由人', 'Indiana Fever': '印第安纳狂热',
    'Toronto Tempo': '多伦多节拍', 'Connecticut Sun': '康涅狄格太阳',
    'Las Vegas Aces': '拉斯维加斯王牌', 'Washington Mystics': '华盛顿神秘人',
    # 篮球 - NBA
    'New York Knicks': '纽约尼克斯', 'San Antonio Spurs': '圣安东尼奥马刺',
    'Los Angeles Lakers': '洛杉矶湖人', 'Boston Celtics': '波士顿凯尔特人',
    'Golden State Warriors': '金州勇士', 'Miami Heat': '迈阿密热火',
    'Milwaukee Bucks': '密尔沃基雄鹿', 'Phoenix Suns': '菲尼克斯太阳',
    'Denver Nuggets': '丹佛掘金', 'Cleveland Cavaliers': '克里夫兰骑士',
    # 篮球 - 以色列
    'Hapoel Holon': '霍隆哈普尔', 'Maccabi Tel-Aviv': '特拉维夫马卡比',
    'Hapoel Jerusalem': '耶路撒冷哈普尔', 'Hapoel Tel-Aviv': '特拉维夫哈普尔',
    'Maccabi Raanana': '马卡比拉纳纳', 'Hapoel Galil Elion': '加利利哈普尔',
    # 篮球 - 土耳其
    'Besiktas JK': '贝西克塔斯篮球', 'Bahcesehir Koleji': '巴赫切谢希尔学院',
    # 篮球 - 希腊
    'Panathinaikos BC': '帕纳辛奈科斯篮球', 'Olympiakos BC': '奥林匹亚科斯篮球',
    # 篮球 - 巴西
    'Vera Cruz Campinas': '坎皮纳斯维拉克鲁兹', 'Sodie Mesquita': '索迪梅斯基塔',
    # 篮球 - 卢旺达
    'Tigers': '老虎队', 'East African University Rwanda': '东非大学卢旺达',
    # 篮球 - 智利
    'CD Universidad De Concepcion': '康塞普西翁大学', 'CD Colegio Los Leones': '洛斯莱奥内斯',
    # 篮球 - 德国
    'Alba Berlin': '柏林阿尔巴', 'Brose Bamberg': '班贝格',
    # 国家队
    'Israel': '以色列', 'Scotland': '苏格兰', 'Hungary': '匈牙利',
    'Andorra': '安道尔', 'Netherlands': '荷兰', 'Poland': '波兰',
    'Mexico': '墨西哥', 'South Africa': '南非',
    'Croatia (W)': '克罗地亚(女)', 'Bulgaria (W)': '保加利亚(女)',
    'Northern Ireland (W)': '北爱尔兰(女)', 'Switzerland (W)': '瑞士(女)',
}

MARKET_CN = {'total': '大小球', 'spread': '让球/让分', 'moneyline': '独赢'}
OUTCOME_CN = {'over': '大球', 'under': '小球', 'home': '主胜', 'away': '客胜', 'draw': '平局'}

def cn_league(name):
    if not name: return name
    return LEAGUE_CN.get(name, name)

def cn_team(name):
    if not name: return name
    return TEAM_CN.get(name, name)

def cn_play(market, outcome, handicap):
    m = MARKET_CN.get(market, market)
    h = '' if handicap is None or handicap == 0.0 else str(handicap)
    if market == 'total':
        d = '大球' if outcome == 'over' else '小球'
        return f"{m}/{d}{h}"
    elif market == 'spread':
        d = '主胜' if outcome == 'home' else '客胜'
        return f"{m}/{d}{h}"
    else:
        d = OUTCOME_CN.get(outcome, outcome)
        return f"{m}/{d}"

def utc_to_bjt(s):
    BJT = timezone(timedelta(hours=8))
    s = str(s).strip()
    try:
        if 'T' in s:
            dt = datetime.fromisoformat(s.replace('Z','+00:00'))
        else:
            dt = datetime.strptime(s[:16],'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        return dt.astimezone(BJT).strftime('%m月%d日%H:%M')
    except:
        return s

# ── 读取推荐 ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DB_ENGINE_URL
_db_path = DB_ENGINE_URL.replace('sqlite:///', '')

conn = sqlite3.connect(_db_path)
c = conn.cursor()
c.execute(f"""
SELECT id, league_name, home_team, away_team, kickoff_utc, market, outcome,
       best_odds, model_prob, kelly_fraction, hit_score, handicap
FROM hit_recommendations
WHERE {_date_filter}
  AND is_filtered = 0
  AND status = 'pending'
  AND (formula_version = 'v1' OR formula_version IS NULL)
ORDER BY hit_score DESC LIMIT {_args.limit * 3}
""")
_raw = c.fetchall()

# 跨日去重：同一 (unified_id, market, outcome) 只保留 hit_score 最高的一条
# 防止同一场比赛在今日和次日两次运行中被重复写入
_seen_key: dict = {}
for row in _raw:
    # row: (id, league, home, away, kick, market, outcome, odds, prob, kelly, score, hcap)
    _key = (row[1], row[2], row[3], row[5], row[6])  # league+teams+market+outcome
    if _key not in _seen_key or row[10] > _seen_key[_key][10]:
        _seen_key[_key] = row
recs = sorted(_seen_key.values(), key=lambda r: r[10], reverse=True)[:_args.limit]

now_bjt = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
date_str = _display_date
time_str = now_bjt.strftime('%H%M')

# ── 构建单注 ──────────────────────────────────────────────
singles = recs[:min(len(recs), _args.limit)]
single_total = 0
rows = []
for i, r in enumerate(singles):
    rid, league, home, away, kick, market, outcome, odds, prob, kelly, score, hcap = r
    tbj   = utc_to_bjt(kick)
    play  = cn_play(market, outcome, hcap)
    sz    = 4 if score >= 0.74 else 3
    mark  = '✅' if score >= 0.74 else '⬇'
    single_total += sz
    rows.append((i+1, tbj, cn_league(league), cn_team(home), cn_team(away), play, odds, prob, kelly, mark, sz, score))

# ── 构建串关用的前8场（K₁/₄>0 才入串关池） ──────────────────
top8 = [(r[7], utc_to_bjt(r[4]), cn_team(r[2]), cn_team(r[3]), cn_play(r[5],r[6],r[11]), cn_league(r[1]))
        for r in singles[:8] if r[9] > 0]
# (odds, time, home_cn, away_cn, play_cn, league_cn)

def co(idxs):
    o = 1.0
    for i in idxs: o *= top8[i][0]
    return round(o, 1)

def win(idxs, stake):
    return round(co(idxs)*stake - stake, 1)

def _valid(combos):
    """过滤掉索引超出 top8 长度的串关组合"""
    n = len(top8)
    return [(idxs, stake) for idxs, stake in combos if all(i < n for i in idxs)]

W = 108
sep = '─' * W

lines = []
lines.append('')
lines.append('=' * W)
lines.append(f"  💰 今日投注计划  [{date_str}]  本金 200元")
lines.append(f"  📐 K₁/₄ = (p融合×赔率-1)/(赔率-1)×0.25")
lines.append('=' * W)
lines.append('')

# 单注
lines.append(f"  ┌─ 📌 单注（共{len(singles)}注，合计 {single_total}元）")
lines.append(f"  │  基准单注 4元，按命中分动态调整")
lines.append(f"  ├─{sep}")
lines.append(f"  │   序  开赛时间           联赛                主队         vs     客队          玩法/方向              赔率   p融合   K₁/₄     投注  命中分")
lines.append(f"  ├─{sep}")
for seq, tbj, lg, home, away, play, odds, prob, kelly, mark, sz, score in rows:
    lg_s   = lg[:14]
    home_s = home[:10]
    away_s = away[:10]
    play_s = play[:20]
    lines.append(f"  │  {seq:2d}. {tbj:<14}  {lg_s:<15} {home_s:<12} vs  {away_s:<12}  {play_s:<21} {odds:.2f}  {prob:.3f} {kelly:.4f}  {mark} {sz}元  {score:.3f}")
lines.append(f"  └─{sep}")
lines.append('')

# ── 串关动态生成（根据 top8 实际长度决定输出层级）──────────────
_PARLAY_DEFS = [
    (2, "🔗 2串1·稳健",   4, [([0,1],4),([1,3],4),([0,2],4),([0,5],4)]),
    (3, "🎰 3串1·进取",   2, [([0,1,2],2),([1,3,4],2),([4,6,7],2)]),
    (4, "🎯 4串1·博取",   2, [([0,1,2,3],2),([0,3,5,6],2)]),
    (5, "🚀 5串1·高博",   2, [([0,1,2,3,4],2)]),
    (6, "💫 6串1·以小博大",2, [([0,1,2,3,4,5],2)]),
    (7, "🌟 7串1·以小博大",2, [([0,1,2,3,4,5,6],2)]),
    (8, "💎 8串1·以小博大",2, [([0,1,2,3,4,5,6,7],2)]),
]
serial_n = 0
for min_top, label, stake, combos in _PARLAY_DEFS:
    if len(top8) < min_top:
        continue
    valid = _valid(combos)
    if not valid:
        continue
    total_stake = sum(stake for _, stake in valid)
    serial_n += len(valid)
    lines.append(f"  ┌─ {label}（每单 {stake}元 × {len(valid)}单 = {total_stake}元）")
    lines.append(f"  ├─{sep}")
    for k, (idxs, s) in enumerate(valid):
        prize = win(idxs, s)
        prize_str = f"💰{prize}元" if prize >= 100 else f"{prize}元"
        lines.append(f"  │  [{k+1}] 组合赔率 {co(idxs)}  中奖可赢 {prize_str}")
        for i in idxs:
            lines.append(f"  │      ✦ {top8[i][1]} {top8[i][2]}vs{top8[i][3]} {top8[i][4]} @{top8[i][0]:.2f}")
    lines.append(f"  └─{sep}")
    lines.append('')

serial_t = sum(
    s * len(_valid(combos))
    for min_top, _lbl, s, combos in _PARLAY_DEFS
    if len(top8) >= min_top
)
total_t  = single_total + serial_t
pct      = round(total_t/200*100,1)
lines.append(f"  ╔{'═'*W}╗")
lines.append(f"  ║  📊 资金汇总：单注 {len(singles)}注（{single_total}元） + 串关 {serial_n}单（{serial_t}元）= 总投注 {total_t}元 / 200元本金（占 {pct}%）")
lines.append(f"  ║  🛡 风控：日亏上限 60元 | 连亏3注停手 | 本金<120元减半")
lines.append(f"  ╚{'═'*W}╝")
lines.append('')

# 明细推荐表
lines.append('=' * (W+10))
lines.append(f"  📋 今日投注推荐单  [{date_str}]  （北京时间）")
lines.append(f"  📐 概率口径：p融合 = 0.50×P庄家 + 0.30×P泊松 + 0.20×P_ELO  |  K值 = (p×赔率-1)/(赔率-1)×0.25（1/4 Kelly）")
lines.append('=' * (W+10))
lines.append(f"  {'开赛时间':<14} {'联赛':<16} {'主队':<16} {'客队':<16} {'市场':<6} {'方向':<18} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} 命中分")
lines.append('-' * (W+10))
for r in recs:
    rid, league, home, away, kick, market, outcome, odds, prob, kelly, score, hcap = r
    tbj    = utc_to_bjt(kick)
    lg_cn  = cn_league(league)[:14]
    hm_cn  = cn_team(home)[:14]
    aw_cn  = cn_team(away)[:14]
    mkt_cn = MARKET_CN.get(market, market)
    dir_cn = cn_play(market, outcome, hcap)
    lines.append(f"  {tbj:<14} {lg_cn:<16} {hm_cn:<16} {aw_cn:<16} {mkt_cn:<6} {dir_cn:<18} {odds:.2f}   {prob:.3f}   {kelly:.4f}  {score:.3f}")
lines.append('=' * (W+10))
lines.append(f"  共 {len(recs)} 条推荐（门槛 ≥ 0.45，每场 ≤ 1 条，日限 20）")

out = '\n'.join(lines)
print(out)

# ── 保存到桌面 ─────────────────────────────────────────────
desktop = r"D:\lucky"
os.makedirs(desktop, exist_ok=True)
fname   = f"投注单_{date_str}_{time_str}.txt"
fpath   = os.path.join(desktop, fname)
with open(fpath, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"\n✅ 桌面文件: {fname}", file=sys.stderr)

# ── 写入命中系统：更新状态 + 记录投注单快照 ─────────────────
try:
    # 确保 betting_slips 表存在
    c.execute("""CREATE TABLE IF NOT EXISTS betting_slips (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        slip_date   TEXT,
        slip_time   TEXT,
        file_name   TEXT,
        total_invest REAL,
        single_count INTEGER,
        serial_count INTEGER,
        content     TEXT,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""INSERT INTO betting_slips(slip_date,slip_time,file_name,total_invest,single_count,serial_count,content)
                 VALUES(?,?,?,?,?,?,?)""",
              (date_str, time_str, fname, total_t, len(singles), serial_n, out))
    # 更新 hit_recommendations 状态为 in_slip
    ids = [r[0] for r in recs]
    c.executemany("UPDATE hit_recommendations SET status='in_slip' WHERE id=?", [(i,) for i in ids])
    conn.commit()
    print(f"✅ 命中系统已写入: betting_slips + {len(ids)} 条推荐标记 in_slip", file=sys.stderr)
except Exception as e:
    print(f"⚠️  写入命中系统异常: {e}", file=sys.stderr)
finally:
    conn.close()
