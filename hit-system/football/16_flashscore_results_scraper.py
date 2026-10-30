# -*- coding: utf-8 -*-
"""
16_flashscore_results_scraper.py — FlashScore 赛果全量爬虫
从 FlashScore 网页版解析嵌入式赛果数据，覆盖全球足球/篮球联赛
用法：
  python 16_flashscore_results_scraper.py                    # 抓取今日所有联赛
  python 16_flashscore_results_scraper.py --date 2026-05-29  # 指定日期
  python 16_flashscore_results_scraper.py --league all       # 全量历史
"""
import os, sys, re, time, json, logging, argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from sqlalchemy import create_engine, text, MetaData
import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl, batch_upsert

engine = create_engine(DB_ENGINE_URL)
log = logging.getLogger("flashscore_results")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BJT = timezone(timedelta(hours=8))
UTC = timezone.utc

# SSL fix：curl_cffi 无法处理含非ASCII字符路径下的 CA 证书，
# 复制 certifi 的证书到纯 ASCII 的临时目录路径（与 15_pinnacle_oddsportal_scraper.py 一致的做法，
# 避免硬编码 F:\ssl_fix\cacert.pem 这种只在特定机器上存在的绝对路径）
from curl_cffi import requests as cffi_requests
import certifi as _certifi_mod
import shutil as _shutil
_SSL_CA_ASCII = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", "C:\\Users\\Public")), "cacert.pem")
if not os.path.exists(_SSL_CA_ASCII):
    try:
        _shutil.copy2(_certifi_mod.where(), _SSL_CA_ASCII)
    except Exception:
        _SSL_CA_ASCII = _certifi_mod.where()

# ── FlashScore 联赛配置 ────────────────────────────────
# sport / country-slug / league-slug / league_id
FOOTBALL_LEAGUES = [
    # ── Tier 1 顶级 ──
    ("england", "premier-league",    "英超"),
    ("spain",   "laliga",            "西甲"),
    ("italy",   "serie-a",           "意甲"),
    ("germany", "bundesliga",        "德甲"),
    ("france",  "ligue-1",           "法甲"),
    ("europe",  "champions-league",  "欧冠"),
    # ── Tier 2 优质 ──
    ("england", "championship",      "英冠"),
    ("portugal","liga-portugal",     "葡超"),
    ("netherlands","eredivisie",     "荷甲"),
    ("scotland","premiership",       "苏超"),
    ("turkey",  "super-lig",         "土超"),
    ("belgium", "first-division-a",  "比甲"),
    ("brazil",  "serie-a",           "巴甲"),
    ("argentina","liga-profesional", "阿甲"),
    ("argentina","copa-de-la-liga-profesional", "阿甲杯赛阶段"),
    ("argentina","primera-a-women", "阿根廷女甲"),
    ("japan",   "j1-league",         "日职联"),
    ("south-korea","k-league-1",     "韩K联"),
    ("china",   "super-league",      "中超"),
    ("usa",     "mls",               "美职联"),
    ("europe",  "europa-league",     "欧联"),
    ("europe",  "conference-league", "欧协联"),
    ("sweden",  "allsvenskan",       "瑞典超"),
    ("norway",  "eliteserien",       "挪超"),
    ("finland", "veikkausliiga",     "芬超"),
    ("sweden",  "superettan",        "瑞典甲"),
    ("world",   "world-cup",         "世界杯"),
    ("asia",    "asian-cup",         "亚洲杯"),
    ("conmebol","copa-libertadores", "解放者杯"),
    ("conmebol","copa-sudamericana", "南美杯"),
    # ── Tier 3 次级联赛 ──
    ("germany", "2-bundesliga",      "德乙"),
    ("italy",   "serie-b",           "意乙"),
    ("spain",   "laliga2",           "西乙"),
    ("france",  "ligue-2",           "法乙"),
    ("england", "league-one",        "英甲"),
    ("england", "league-two",        "英乙"),
    ("brazil",  "serie-b",           "巴乙"),
    ("brazil",  "serie-c",           "巴丙"),
    ("brazil",  "serie-d",           "巴丁"),
    ("argentina","primera-b-nacional","阿乙"),
    ("south-korea","k-league-2",     "韩K2联"),
    ("japan",   "j2-league",         "日职乙"),
    ("china",   "league-one",        "中甲"),
    ("usa",     "usl-championship",  "USL"),
    ("mexico",  "liga-mx",           "墨超"),
    ("chile",   "primera-division",  "智利甲"),
    ("peru",    "liga-1",            "秘鲁甲"),
    ("uruguay", "primera-division",  "乌拉圭甲"),
    ("colombia","primera-a",         "哥伦比亚甲"),
    ("ecuador", "serie-a",           "厄瓜多尔甲"),
    ("paraguay","primera-division",  "巴拉圭甲"),
    ("poland",  "ekstraklasa",       "波兰超"),
    ("croatia", "first-league",      "克甲"),
    ("serbia",  "super-liga",        "塞超"),
    ("austria", "bundesliga",        "奥超"),
    ("switzerland","super-league",   "瑞士超"),
    ("czech-republic","first-league","捷甲"),
    ("denmark", "superliga",         "丹麦超"),
    ("norway",  "1-division",        "挪甲"),
    ("norway",  "2-division",        "挪乙"),
    ("norway",  "3-division",        "挪丙"),
    ("ireland", "premier-division",  "爱尔兰超"),
    ("iceland", "besta-deild-karla", "冰岛超"),
    ("lithuania","a-lyga",           "立陶宛甲"),
    ("latvia",  "virsliga",          "拉脱维亚甲"),
    ("estonia", "meistriliiga",      "爱沙尼亚甲"),
    ("romania", "liga-1",            "罗马尼亚甲"),
    ("bulgaria","first-league",      "保加利亚甲"),
    ("hungary", "nb-i",              "匈甲"),
    ("greece",  "super-league",      "希腊超"),
    ("egypt",   "premier-league",    "埃及超"),
    ("south-africa","premier-league","南非超"),
    ("morocco", "botola-pro",        "摩洛哥甲"),
    ("australia","a-league",         "澳超"),
    ("new-zealand","national-league","新西兰甲"),
    # ── P4 新增：覆盖更多推荐联赛 ──
    ("switzerland","challenge-league","瑞士挑"),
    ("switzerland","1-liga-promotion", "瑞士Promotion"),
    ("austria",  "regionalliga-west",  "奥地RL西"),
    ("austria",  "regionalliga-east",  "奥地RL东"),
    ("austria",  "regionalliga-middle","奥地RL中"),
    ("poland",   "i-liga",            "波兰甲"),
    ("czech-republic","second-league","捷乙"),
    ("slovakia", "super-liga",        "斯洛伐克超"),
    ("slovakia", "2-liga",            "斯洛伐克甲"),
    ("denmark",  "1st-division",      "丹麦甲"),
    ("sweden",   "division-1-norra",  "瑞典甲北"),
    ("sweden",   "division-1-sodra",  "瑞典甲南"),
    ("finland",  "ykkosliiga",        "芬超"),
    ("finland",  "ykkonen",           "芬甲"),
    ("iceland",  "1-deild",           "冰岛甲"),
    ("ireland",  "first-division",    "爱尔兰甲"),
    ("faroe-islands","premier-league", "法罗超"),
    ("lithuania","1-lyga",            "立陶宛乙"),
    ("estonia",  "esiliiga",          "爱沙尼亚甲"),
    ("latvia",   "1-liga",            "拉脱维亚甲"),
    ("argentina","primera-b-metropolitana","阿B Metro"),
    ("chile",    "primera-b",         "智利乙"),
    ("chile",    "segunda-division",  "智利丙"),
    ("uruguay",  "segunda-division",  "乌拉圭乙"),
    ("algeria",  "ligue-1",           "阿尔及利亚甲"),
    ("ethiopia", "premier-league",    "埃塞俄比亚超"),
    ("israel",   "premier-league",    "以色列超"),
    ("bahrain",  "premier-league",    "巴林超"),
    ("canada",   "canadian-premier-league", "加拿大超"),
    ("canada",   "championship",      "加拿大锦标赛"),
    ("usa",      "mls-next-pro",      "MLS Next Pro"),
    ("vietnam",  "v-league",          "越南甲"),
    ("vietnam",  "v-league-2",        "越南乙"),
    ("south-america","copa-libertadores", "解放者杯"),
    ("south-america","copa-sudamericana", "南美杯"),
]

BASKETBALL_LEAGUES = [
    ("usa",     "nba",               "NBA"),
    ("usa",     "wnba",              "WNBA"),
    ("europe",  "euroleague",        "欧联杯"),
    ("europe",  "eurocup",           "欧洲杯"),
    ("china",   "cba",               "CBA"),
    ("spain",   "acb",               "西甲篮球"),
    ("turkey",  "super-lig",         "土超篮球"),
    ("greece",  "basket-league",     "希腊篮球"),
    ("germany", "bbl",               "德甲篮球"),
    ("france",  "lnb",               "法甲篮球"),
    ("australia","nbl",              "澳篮联"),
    ("australia","nbl1",             "澳NBL1"),
    ("new-zealand","nbl",            "新西兰篮联"),
    ("europe",  "bnxt-league",       "BNXT联赛"),
    ("vietnam", "vba",               "越南篮联"),
    # ── P4 新增 ──
    ("puerto-rico","bsn",            "波多黎各篮"),
    ("brazil",  "nbb",               "巴篮联"),
    ("australia","nbl1-south",       "澳NBL1南"),
    ("australia","nbl1-north",       "澳NBL1北"),
    ("australia","nbl1-east",        "澳NBL1东"),
    ("australia","nbl1-west",        "澳NBL1西"),
    ("uruguay", "liga-uruguaya",     "乌拉圭篮"),
    # 2026-07-25新增：墨西哥职业篮球联赛(LNBP)，此前完全没有赛果覆盖，导致
    # Diablos Rojos/Panteras de Aguascalientes等LNBP球队的推荐单永久卡在pending
    # 结算不了。URL slug经WebSearch核实(flashscore.com/basketball/mexico/lnbp/results/)。
    ("mexico",  "lnbp",              "墨西哥职业篮"),
]


# UA 池（curl_cffi impersonate 已模拟 TLS 指纹，UA 也轮换以分散特征）
_UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
]
_IMPERSONATE_POOL = ['chrome', 'chrome110', 'chrome116', 'chrome120', 'edge101', 'safari15_5']


def _session():
    import random as _r
    imp = _r.choice(_IMPERSONATE_POOL)
    try:
        s = cffi_requests.Session(impersonate=imp)
    except Exception:
        s = cffi_requests.Session(impersonate='chrome')
    s.headers.update({
        'User-Agent': _r.choice(_UA_POOL),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return s


# ── 1. 解析 FlashScore 嵌入式数据 ─────────────────────
def _parse_feed(raw: str) -> list:
    """
    解析 FlashScore 的 ¬ 分隔格式。
    返回 list of dict: 每场已完成比赛的信息。
    """
    matches = []
    # 每场比赛以 ~AA÷ 开头（AA=match_id）
    # 先按 ~ 分割出区段
    segments = raw.split('~')
    
    current = {}
    for seg in segments:
        fields = seg.split('¬')
        for f in fields:
            f = f.strip()
            if '÷' in f:
                k, v = f.split('÷', 1)
                if k == 'AA':  # 新比赛开始
                    if current.get('AA'):
                        matches.append(current)
                    current = {'AA': v}
                else:
                    current[k] = v
    
    if current.get('AA'):
        matches.append(current)
    
    return matches


def _extract_results_from_page(html: str) -> tuple[list, bool]:
    """从FlashScore页面HTML中提取赛果数据。
    返回 (matches, feed_found)：feed_found=True 表示页面结构正常、
    initialFeeds['results'] 字段已找到（即使内容为空也代表联赛当前确实
    没有赛果，比如7月欧洲主流联赛休赛期，这是正常情况不该重试）；
    feed_found=False 表示页面里压根没找到这个字段（页面结构异常/被拦截），
    才是真实抓取失败，需要重试。"""
    pat = r"initialFeeds\['results'\]\s*=\s*\{[^`]*`([^`]*)`"
    feeds = re.findall(pat, html)

    all_matches = []
    for feed in feeds:
        matches = _parse_feed(feed)
        all_matches.extend(matches)

    return all_matches, bool(feeds)


# ── 2. 解码字段 ────────────────────────────────────────
def _decode_match(m: dict) -> dict | None:
    """
    FlashScore 字段映射（已验证）:
      AA = match_id
      AE = home_team  (主队名)
      AF = away_team  (客队名)
      AG = home_score (主队得分)
      AH = away_score (客队得分)
      AD = start_timestamp (unix)
      ER = round_info
      WM = home_abbr
      WN = away_abbr
      WU = home_slug
      WV = away_slug
    """
    mid = m.get('AA', '')
    if not mid:
        return None
    
    ts = m.get('AD', '')
    kickoff_utc = None
    try:
        if ts:
            kickoff_utc = datetime.fromtimestamp(int(ts), tz=UTC)
    except (ValueError, OSError):
        pass
    
    home_team = m.get('AE', '') or m.get('CX', '')
    away_team = m.get('AF', '')
    
    home_score = None
    away_score = None
    try:
        if m.get('AG') is not None:
            home_score = int(m['AG'])
        if m.get('AH') is not None:
            away_score = int(m['AH'])
    except (ValueError, TypeError):
        pass
    
    return {
        'flashscore_id': mid,
        'kickoff_utc': kickoff_utc,
        'home_team': home_team,
        'away_team': away_team,
        'home_score': home_score,
        'away_score': away_score,
        'round': m.get('ER', ''),
        'home_abbr': m.get('WM', ''),
        'away_abbr': m.get('WN', ''),
        'home_slug': m.get('WU', ''),
        'away_slug': m.get('WV', ''),
    }


# ── 3. 抓取联赛页 ─────────────────────────────────────
def scrape_league_results(sess, country: str, league: str, cn_name: str, 
                          sport: str = 'football') -> list:
    """抓取一个联赛的赛果页（含最多 2 次重试，连接被掐断时换 session 重试）"""
    base = 'football' if sport == 'football' else 'basketball'
    url = f'https://www.flashscore.com/{base}/{country}/{league}/results/'
    
    last_err = None
    for attempt in range(3):  # 原始 + 重试2次
        try:
            # 重试时换一个新 session（新 TLS 指纹 + 新 UA）
            use_sess = sess if attempt == 0 else _session()
            r = use_sess.get(url, verify=_SSL_CA_ASCII, timeout=25)
            if r.status_code == 200:
                matches, feed_found = _extract_results_from_page(r.text)
                if not matches:
                    if not feed_found and attempt < 2:
                        # 页面里没找到 initialFeeds['results'] 字段本身，说明页面结构
                        # 异常/被拦截，是真实失败，值得重试
                        log.debug(f"  {cn_name}: 页面结构异常，未找到结果字段 (尝试 {attempt+1}/3), 重试...")
                        time.sleep(3 + (time.time()*7) % 4)  # 3-7s 抖动
                        continue
                    if not feed_found:
                        log.warning(f"  {cn_name}: 全部重试后仍未找到结果字段，可能被拦截")
                    else:
                        # feed_found=True 但内容为空：联赛当前确实没有赛果（如休赛期），
                        # 不是抓取失败，不重试，直接当作0场结果返回
                        log.debug(f"  {cn_name}: 0 matches（该联赛当前无赛果，如休赛期，正常情况）")
                    return []
                results = []
                for m in matches:
                    decoded = _decode_match(m)
                    if decoded and decoded.get('home_team'):
                        decoded['league_cn'] = cn_name
                        decoded['country'] = country
                        decoded['league_slug'] = league
                        decoded['sport'] = sport
                        results.append(decoded)
                scored = sum(1 for r in results if r.get('home_score') is not None)
                log.info(f"  {cn_name}: {len(results)} 场赛果 ({scored} 场有比分){' [重试成功]' if attempt>0 else ''}")
                return results
            elif r.status_code == 404:
                log.warning(f"  {cn_name}: HTTP 404")
                return []  # 404 是结构问题，不重试
            else:
                last_err = f"HTTP {r.status_code}"
                if attempt < 2:
                    time.sleep(3 + (time.time()*7) % 4)
                    continue
                log.warning(f"  {cn_name}: HTTP {r.status_code}")
                return []
        except Exception as e:
            last_err = str(e)
            if attempt < 2:
                log.debug(f"  {cn_name}: {e} (尝试 {attempt+1}/3), 重试...")
                time.sleep(4 + (time.time()*11) % 5)  # 4-9s 较长抖动
                continue
            log.warning(f"  {cn_name}: ERROR {e} [重试{attempt}次后放弃]")
            return []
    log.warning(f"  {cn_name}: 全部重试失败 ({last_err})")
    return []


def _sleep():
    """请求间随机停顿 2.5-6s，打散请求节奏"""
    time.sleep(2.5 + (time.time() % 3.5))


# ── 4. 入库 ────────────────────────────────────────────
def save_to_db(results: list):
    """将赛果写入 match_results 表"""
    if not results:
        return 0
    
    # 建表（已存在则忽略）
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flashscore_id TEXT UNIQUE,
            sport TEXT,
            country TEXT,
            league_slug TEXT,
            league_cn TEXT,
            home_team TEXT,
            away_team TEXT,
            home_score INTEGER,
            away_score INTEGER,
            kickoff_utc TEXT,
            match_date TEXT,
            round_info TEXT,
            raw_data TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    saved = 0
    rows_to_insert = []
    for r in results:
        try:
            kt = r.get('kickoff_utc', '')
            rows_to_insert.append({
                'flashscore_id': r.get('flashscore_id', ''),
                'sport':         r.get('sport', ''),
                'country':       r.get('country', ''),
                'league_slug':   r.get('league_slug', ''),
                'league_cn':     r.get('league_cn', ''),
                'home_team':     r.get('home_team', ''),
                'away_team':     r.get('away_team', ''),
                'home_score':    r.get('home_score'),
                'away_score':    r.get('away_score'),
                'kickoff_utc':   str(kt),
                'match_date':    kt.strftime('%Y-%m-%d') if hasattr(kt, 'strftime') else str(kt)[:10],
                'round_info':    r.get('round', ''),
                'raw_data':      json.dumps({k: v for k, v in r.items() if k != 'kickoff_utc'}, ensure_ascii=False),
            })
            saved += 1
        except Exception as e:
            log.debug(f"  skip {r.get('flashscore_id')}: {e}")

    if rows_to_insert:
        md = MetaData()
        md.reflect(bind=engine, only=['match_results'])
        batch_upsert(engine, md.tables['match_results'], rows_to_insert,
                     unique_keys=['flashscore_id'])

    return saved


# ── 5. 回验推荐 ────────────────────────────────────────
def verify_recommendations(results: list) -> dict:
    """用赛果验证 pending 推荐"""
    if not results:
        return {'win': 0, 'lose': 0, 'no_match': 0}
    
    # 构建比分索引
    score_index = {}
    for r in results:
        if r.get('home_score') is not None and r.get('away_score') is not None:
            key = (_norm(r.get('home_team', '')), _norm(r.get('away_team', '')))
            score_index[key] = r
    
    log.info(f"  比分索引: {len(score_index)} 场")
    
    win, lose, no_match = 0, 0, 0
    with engine.begin() as conn:
        recs = conn.execute(text(
            "SELECT id, home_team, away_team, market, outcome FROM hit_recommendations WHERE status='pending'"
        )).fetchall()
        
        for rid, ht, at, market, outcome in recs:
            # 过滤特殊市场（Corners等）
            if '(Corners)' in ht or '(Corners)' in at:
                no_match += 1
                continue
            
            score = None
            swapped = False
            
            # 方法1: 归一化精确匹配
            key1 = (_norm(ht), _norm(at))
            key2 = (_norm(at), _norm(ht))
            if key1 in score_index:
                score = score_index[key1]
            elif key2 in score_index:
                score = score_index[key2]
                swapped = True
            
            # 方法2: 模糊匹配（遍历比分索引）
            if not score:
                for (fh, fa), s in score_index.items():
                    matched, sw = _fuzzy_match(ht, at, s.get('home_team',''), s.get('away_team',''))
                    if matched:
                        score = s
                        swapped = sw
                        break
            
            if not score or score.get('home_score') is None:
                no_match += 1
                continue
            
            hs = score['home_score']
            as_ = score['away_score']
            result = _judge(market, outcome, hs, as_)
            
            if result == 'win':
                win += 1
            elif result == 'lose':
                lose += 1
            else:
                no_match += 1
                continue
            
            conn.execute(text("""
                UPDATE hit_recommendations SET status=:st, 
                reason=COALESCE(reason,'') || ' | 回验:' || :sc
                WHERE id=:id
            """), {'st': result, 'sc': f'{hs}-{as_}', 'id': rid})
    
    return {'win': win, 'lose': lose, 'no_match': no_match}


def _norm(name):
    """队名归一化：去掉空格、标点、统一小写"""
    name = name.lower().strip()
    # 去掉常见后缀
    for suffix in [' (corners)', '(corners)', ' fc', ' cf', ' sc', ' ac']:
        name = name.replace(suffix, '')
    return re.sub(r'[^a-z0-9]', '', name)


def _fuzzy_match(rec_home, rec_away, fs_home, fs_away, threshold=0.6):
    """
    模糊匹配：尝试多种方式匹配推荐和赛果
    返回 True if match, 以及是否需要swap
    """
    rh = _norm(rec_home)
    ra = _norm(rec_away)
    fh = _norm(fs_home)
    fa = _norm(fs_away)
    
    # 1. 精确匹配
    if rh == fh and ra == fa:
        return True, False
    if rh == fa and ra == fh:
        return True, True
    
    # 2. 包含匹配（一方名包含另一方）
    def _contains(a, b):
        return a in b or b in a
    
    if _contains(rh, fh) and _contains(ra, fa):
        return True, False
    if _contains(rh, fa) and _contains(ra, fh):
        return True, True
    
    # 3. 前缀匹配（队名缩写）
    if len(rh) >= 4 and len(ra) >= 4:
        if fh.startswith(rh[:4]) and fa.startswith(ra[:4]):
            return True, False
        if fh.startswith(ra[:4]) and fa.startswith(rh[:4]):
            return True, True
    
    return False, False


def _judge(market, outcome, hs, as_):
    if market == 'moneyline':
        if outcome == 'home':
            return 'win' if hs > as_ else ('lose' if hs < as_ else 'lose')
        elif outcome == 'away':
            return 'win' if hs < as_ else ('lose' if hs > as_ else 'lose')
        elif outcome == 'draw':
            return 'win' if hs == as_ else 'lose'
    # spread/total 需要 handicap，暂返回 None
    return None


# ── Main ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD")
    parser.add_argument("--sport", choices=["football", "basketball", "both"], default="both")
    parser.add_argument("--verify", action="store_true", help="同时回验pending推荐")
    parser.add_argument("--debug", action="store_true", help="输出原始解码数据")
    args = parser.parse_args()
    
    log.info("═══ FlashScore 赛果爬虫启动 ═══")
    sess = _session()
    all_results = []
    
    # 抓取足球
    if args.sport in ('football', 'both'):
        log.info("⚽ 抓取足球赛果...")
        for country, league, cn_name in FOOTBALL_LEAGUES:
            results = scrape_league_results(sess, country, league, cn_name, 'football')
            if args.debug and results:
                for r in results[:2]:
                    print(f"    DEBUG: {r}")
            all_results.extend(results)
            _sleep()
    
    # 抓取篮球
    if args.sport in ('basketball', 'both'):
        log.info("🏀 抓取篮球赛果...")
        for country, league, cn_name in BASKETBALL_LEAGUES:
            results = scrape_league_results(sess, country, league, cn_name, 'basketball')
            all_results.extend(results)
            _sleep()
    
    # 入库
    saved = save_to_db(all_results)
    log.info(f"📊 入库: {saved} 场赛果")
    
    # 回验
    if args.verify and all_results:
        v = verify_recommendations(all_results)
        log.info(f"✅ 回验: win={v['win']}, lose={v['lose']}, 未匹配={v['no_match']}")
    
    # 统计
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM match_results")).fetchone()[0]
        log.info(f"📊 match_results 表总计: {total} 场")
    
    log.info("═══ FlashScore 赛果爬虫完成 ═══")


if __name__ == "__main__":
    main()
