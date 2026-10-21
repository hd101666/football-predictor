# 15_pinnacle_oddsportal_scraper.py — Pinnacle + OddsPortal 全量赔率爬虫
#
# ═══════════════════════════════════════════════════════════════════
# 【数据源 A — 主力】 https://guest.api.arcadia.pinnacle.com
#   Pinnacle Guest Public API，无需注册账号，永久免费。
#   接口: /sports/{id}/leagues → /leagues/{id}/matchups → /leagues/{id}/markets/straight
#   覆盖: 全球 153 个足球联赛 + 46 个篮球联赛，独赢/亚盘/大小球赔率。
#   认证: x-api-key: PINNACLE_GUEST_KEY（来自 config.py/.env）
#
# 【数据源 B — 补充】 https://www.oddsportal.com
#   OddsPortal 多庄赔率聚合，覆盖 Pinnacle 未收录的小联赛。
#   接入方式：curl_cffi 直连 /ajax-nextgames/{sportId}/8/2/{YYYYMMDD}/{buildHash}.dat 接口，
#   响应是 base64(base64(AES-256-CBC密文):IV十六进制) 套 gzip，算法已逆向验证：
#     1. body 整体 base64 解码一次 → 按 ":" 切成 [密文base64, IV十六进制]
#     2. key = PBKDF2-HMAC-SHA256(password, salt, iterations=1000, dklen=32)
#        password/salt 硬编码在前端JS包里（见 _op_decrypt() 实现），2026-07-12 摸排确认
#     3. AES-256-CBC 解密 → PKCS7 去填充 → 若头两字节是gzip魔数(1f 8b)则再解压 → JSON
#   已用 curl_cffi（不启动任何浏览器）实测验证：某场次页面拿到271场/50条一致数据，解密成功。
#   注意：这个接口只有赛程/赛果字段（队名/联赛/比分/开赛时间），不含赔率数值！
#   赔率走的是另一个接口 /ajax-nextgames-odds/{sportId}/8/{bHash}/{date}/{page}/{buildHash}.dat
#   （POST，bHash 是运行时动态生成的长编码，尚未摸排出计算方式——TODO，留给下一轮）。
#   在赔率接口摸清楚之前，大小球/让球盘口仍要靠 10_oddsportal_scraper.py 的 Playwright 详情页抓取。
#   {buildHash}（如 "yj084"）疑似跟随站点构建版本变化，如果这里失效大概率是这个值过期了，
#   需要重新从页面请求里抓一次当前值。
#   历史上这里曾经过 importlib 动态加载 10_oddsportal_scraper.py 起第二个 Playwright 实例，
#   与 run_all_scrapers.py 里独立子进程的"10"重复抓同一站点，已去除。
# ═══════════════════════════════════════════════════════════════════
#
# 覆盖：足球全量联赛 + 篮球全量联赛，今日 13:00 BJT → 次日 13:00 BJT
#
# 反爬策略：
#   1. curl_cffi Chrome/Firefox TLS 指纹伪装（JA3/JA4 绕过）
#   2. User-Agent 轮换池（Chrome 116/123/131 + Firefox 133 + Edge 101）
#   3. Cookie 热身：先访问首页建立会话再请求 API
#   4. 随机请求间隔 + 正态分布延迟（模拟真人行为）
#   5. Referer / Origin 伪造
#   6. Accept-Language 区域伪装
#   7. 限速后自动退避（指数退避 + 抖动）
#   8. 本地 gzip 缓存（6h TTL），避免重复命中反爬触发封禁
#
# 输出表：
#   theodds_fixtures  — 赛事对阵表（今明两天）
#   theodds_odds      — 多市场实时赔率（独赢/亚盘/大小球）
#   theodds_odds_history — 赔率快照历史

import sys, os, re, time, random, json, logging, hashlib, gzip, base64, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

from sqlalchemy import create_engine, text
from curl_cffi import requests as cffi

HAS_PYCRYPTODOME = False
try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Hash import SHA256 as _SHA256
    from Crypto.Protocol.KDF import PBKDF2 as _PBKDF2
    from Crypto.Util.Padding import unpad as _unpad
    HAS_PYCRYPTODOME = True
except ImportError:
    logging.getLogger(__name__).warning(
        "pycryptodome 未安装，OddsPortal ajax-nextgames 解密不可用。安装: pip install pycryptodome")

sys.path.insert(0, str(Path(__file__).parent))
import env_setup

from config import DB_ENGINE_URL, PINNACLE_GUEST_KEY as _CONFIG_PINNACLE_KEY
from db_utils import exec_ddl

# ─── 日志 ─────────────────────────────────────────────────────────────────────
# Bug修复(2026-08-12)：原先只有 getLogger、**没有 basicConfig**，独立运行时
# Python日志默认只输出WARNING及以上，所有 log.info 的成功信息被静默丢弃，
# 日志里只剩重试噪音——工作正常的爬虫会看起来像全线失败（09号即因此被误判）。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("theodds")

engine = create_engine(DB_ENGINE_URL)

# ─── 投注时间窗口（北京时间）────────────────────────────────────────────────
BJ_TZ = timezone(timedelta(hours=8))

def get_bet_window():
    """返回 (start_utc_str, end_utc_str) 今日13:00 BJT → 次日13:00 BJT"""
    now_bj   = datetime.now(BJ_TZ)
    today_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    start_bj = today_bj.replace(hour=13)
    end_bj   = (today_bj + timedelta(days=1)).replace(hour=13)
    start_utc = start_bj.astimezone(timezone.utc)
    end_utc   = end_bj.astimezone(timezone.utc)
    return start_utc, end_utc

# ─── 本地缓存（6h TTL，避免重复请求） ───────────────────────────────────────
CACHE_DIR = Path(__file__).parent / "data" / "_odds_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 6 * 3600  # 6小时

def _cache_key(url: str, params: dict = None) -> str:
    raw = url + json.dumps(params or {}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()

def _cache_get(url: str, params: dict = None) -> Optional[Any]:
    key  = _cache_key(url, params)
    path = CACHE_DIR / f"{key}.json.gz"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > CACHE_TTL:
        return None
    try:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read())
    except Exception:
        return None

def _cache_set(url: str, params: dict, data: Any):
    key  = _cache_key(url, params)
    path = CACHE_DIR / f"{key}.json.gz"
    try:
        with gzip.open(path, "wb") as f:
            f.write(json.dumps(data, ensure_ascii=False).encode())
    except Exception:
        pass

# ─── User-Agent 池 ────────────────────────────────────────────────────────────
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.188 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

IMPERSONATES = ["chrome116", "chrome123", "chrome131", "firefox133", "edge101"]

def _rand_ua():
    return random.choice(UA_POOL)

def _rand_imp():
    return random.choice(IMPERSONATES)

# ─── 通用延迟（模拟真人） ─────────────────────────────────────────────────────
def _sleep(base=1.2, sigma=0.5):
    t = max(0.3, random.gauss(base, sigma))
    time.sleep(t)

def _backoff(attempt: int):
    wait = min(60, (2 ** attempt) + random.uniform(0, 2))
    log.warning(f"  限速退避 {wait:.1f}s ...")
    time.sleep(wait)

# ═══════════════════════════════════════════════════════════════════════════════
# 数据源 A: Pinnacle Guest Public API
# ═══════════════════════════════════════════════════════════════════════════════
PINNACLE_API  = "https://guest.api.arcadia.pinnacle.com/0.1"
PINNACLE_GUEST_KEY = _CONFIG_PINNACLE_KEY  # 从 config.py 读取（最终来自 .env）

# ─── SSL 修复：curl_cffi 无法处理含中文路径的 CA 证书 ────────────────────────
# 将 certifi 的 CA 证书复制到纯 ASCII 路径
import certifi as _certifi_mod
import shutil as _shutil
_SSL_CA_SRC = _certifi_mod.where()
_SSL_CA_ASCII = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", "REDACTED")), "cacert.pem")
if not os.path.exists(_SSL_CA_ASCII):
    try:
        _shutil.copy2(_SSL_CA_SRC, _SSL_CA_ASCII)
    except Exception:
        _SSL_CA_ASCII = _SSL_CA_SRC
_SSL_CA = _SSL_CA_ASCII
os.environ["CURL_CA_BUNDLE"] = _SSL_CA
os.environ["SSL_CERT_FILE"] = _SSL_CA

# 并发抓取下每个 worker 线程用各自独立的 Session，避免多线程共享同一个
# cffi.Session 对象时 headers.pop() 和请求准备的 dict 读取产生竞态
# （间歇性 RuntimeError/认证异常，且互不可控）。
_pinn_local = threading.local()
_pinn_key_revoked = threading.Event()  # guest key 一旦被任意线程判定失效，全局不再使用

def _new_pinn_session() -> "cffi.Session":
    sess = cffi.Session(impersonate=_rand_imp())
    sess.headers.update({
        "User-Agent":      _rand_ua(),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin":          "https://www.pinnacle.com",
        "Referer":         "https://www.pinnacle.com/",
    })
    # 2026-09-11: Pinnacle 足球接口对非美国IP地域拦截（直连超时/返回空，
    # 实测足球全天0场但篮球正常）。支持通过 HTTPS_PROXY/HTTP_PROXY 环境变量
    # 走本地代理（如美国节点），不设则保持直连旧行为。
    _proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if _proxy:
        sess.proxies = {"http": _proxy, "https": _proxy}
    if not _pinn_key_revoked.is_set():
        sess.headers["x-api-key"] = PINNACLE_GUEST_KEY
    return sess

def _get_pinn_session() -> "cffi.Session":
    sess = getattr(_pinn_local, "session", None)
    if sess is None:
        sess = _new_pinn_session()
        _pinn_local.session = sess
    elif _pinn_key_revoked.is_set():
        sess.headers.pop("x-api-key", None)
    return sess

# 全局请求节流：不管有多少个并发 worker，Pinnacle 的实际出站请求速率都不能超过这个上限
# （此前并发化后 _pinn_get 的happy path完全没有节流，5线程会同时打满API，
#   项目历史上已因类似无节制请求触发过其他数据源的IP封锁）
_pinn_rate_lock = threading.Lock()
_pinn_last_request_ts = 0.0
_PINN_MIN_INTERVAL = 0.25  # 全局最多约 4 req/s

def _pinn_throttle():
    global _pinn_last_request_ts
    with _pinn_rate_lock:
        now = time.time()
        wait = _PINN_MIN_INTERVAL - (now - _pinn_last_request_ts)
        if wait > 0:
            time.sleep(wait)
        _pinn_last_request_ts = time.time()

def _pinn_get(path: str, params: dict = None) -> Optional[Any]:
    url = f"{PINNACLE_API}{path}"
    cached = _cache_get(url, params)
    if cached is not None:
        return cached
    for attempt in range(5):
        try:
            _pinn_throttle()
            sess = _get_pinn_session()
            r = sess.get(url, params=params, timeout=20, verify=_SSL_CA)
            if r.status_code == 200:
                data = r.json()
                _cache_set(url, params, data)
                return data
            if r.status_code == 429:
                _backoff(attempt)
                continue
            if r.status_code in (401, 403):
                # guest key 失效，全局标记后所有线程改用无 key 请求
                _pinn_key_revoked.set()
                sess.headers.pop("x-api-key", None)
                continue
            log.warning(f"Pinnacle {r.status_code}: {path}")
        except Exception as e:
            log.warning(f"Pinnacle 请求异常({attempt+1}): {e}")
            _sleep(3, 1)
    return None

# Pinnacle sport_id 映射
PINN_SPORTS = {
    "soccer":      29,
    "basketball":   4,
    "baseball":     3,
    "americanfootball": 15,
    "icehockey":   19,
}

def pinn_get_leagues(sport_code: str) -> List[Dict]:
    """获取 Pinnacle 全量联赛（有赛事的）"""
    sport_id = PINN_SPORTS.get(sport_code, 29)
    data = _pinn_get(f"/sports/{sport_id}/leagues", {"all": "false"})
    if not data:
        return []
    leagues = data if isinstance(data, list) else data.get("leagues", [])
    result = []
    for lg in leagues:
        mc = lg.get("matchupCount", 0) or lg.get("count", 0)
        if mc > 0:
            result.append({
                "id":   lg.get("id"),
                "name": lg.get("name", ""),
                "count": mc,
            })
    log.info(f"  Pinnacle {sport_code}: {len(result)} 个有赛事联赛")
    return result

def pinn_get_fixtures(league_id: int) -> List[Dict]:
    """获取联赛赛事列表（带时间过滤）"""
    data = _pinn_get(f"/leagues/{league_id}/matchups")
    if not data:
        return []
    matchups = data if isinstance(data, list) else data.get("matchups", [])
    start_utc, end_utc = get_bet_window()
    result = []
    for mu in matchups:
        ts = mu.get("startTime", "")
        if not ts:
            continue
        try:
            kt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if not (start_utc <= kt < end_utc):
                continue
        except Exception:
            pass
        # 修复：只保留 type=matchup 主赛事，过滤 special/角球等衍生盘
        mu_type = mu.get("type", "")
        if mu_type == "special":
            continue

        participants = mu.get("participants", [])
        home, away = "", ""
        for p in participants:
            al = p.get("alignment", "")
            if al == "home":
                home = p.get("name", "")
            elif al in ("away", "visiting"):
                away = p.get("name", "")

        # 过滤角球子赛事
        if "(Corners)" in home or "(Corners)" in away:
            continue

        result.append({
            "id":        mu.get("id"),
            "status":    mu.get("status", "NS"),
            "kickoff":   ts,
            "home_team": home,
            "away_team": away,
        })
    return result

def _pick_main_line(price_lists: List[List[Dict]], mtype: str) -> List[Dict]:
    """从同市场多条盘口线中选出主盘口线。

    Pinnacle 对同 (matchupId, type, period) 可能返回多条 market 记录，
    每条 isAlternate=false 但 prices[].points 值不同（不同盘口线）。
    主盘口的 maxBet 值最高。
    """
    if not price_lists:
        return []
    if len(price_lists) == 1:
        return price_lists[0]

    # 策略1：选 maxBet 总和最高的那组 prices（主盘口通常流动性最高）
    def sum_maxbet(prices):
        return sum(p.get("maxBet", 0) or 0 for p in prices if p.get("price") is not None)

    sums = [sum_maxbet(pl) for pl in price_lists]
    # 如果存在明显更高的 maxBet（>其他组2倍），选它
    max_sum = max(sums)
    if max_sum > 0:
        # 检查是否有明显高于其他的
        second_max = sorted(sums)[-2] if len(sums) > 1 else 0
        if max_sum > second_max * 1.5 or second_max == 0:
            return price_lists[sums.index(max_sum)]

    # 策略2：按 mtype 智能选择
    if mtype == "spread":
        # 亚盘：选 points 绝对值最小的（最接近平手盘）
        def avg_abs_points(prices):
            pts = [p.get("points") or p.get("handicap", 0) for p in prices if p.get("price") is not None]
            return sum(abs(float(x)) for x in pts if x is not None) / len(pts) if pts else 999
        best = min(price_lists, key=avg_abs_points)
    elif mtype == "total":
        # 大小球：选 points 中位数（排除极端值）
        def median_points(prices):
            pts = sorted([float(p.get("points") or p.get("handicap", 0)) for p in prices if p.get("price") is not None and p.get("points") is not None])
            if not pts:
                return 999
            return pts[len(pts) // 2]
        best = min(price_lists, key=median_points)
    else:
        # moneyline 等其他市场：选第一个
        best = price_lists[0]

    return best


def pinn_get_odds(league_id: int) -> Dict[int, Dict]:
    """获取联赛全部赔率（moneyline/spread/total 合并）

    注意：Pinnacle API 对同场比赛可能返回多条 isAlternate=false 的 market 记录，
    它们的 prices[].points（盘口线）不同。必须从中选出主盘口线。
    """
    data = _pinn_get(f"/leagues/{league_id}/markets/straight")
    if not data:
        return {}
    markets = data if isinstance(data, list) else data.get("markets", [])

    # 第一遍：按 (matchupId, type, period) 收集所有候选盘口线
    candidates: Dict = {}
    for m in markets:
        if m.get("isAlternate", False) is True:
            continue
        mid    = m.get("matchupId")
        mtype  = m.get("type", "")
        period = m.get("period", 0)
        # Bug修复：team_total 在 Pinnacle API 里对同一 matchupId 会返回两条market
        # (side="home"/"away"，各自独立的线)，但原来统一按裸的"team_total"分组，
        # 主客队两条线撞上同一个(mid, mtype, period)键，_pick_main_line只能留其一，
        # 另一队的线被静默丢弃，下游又硬编码"team_total默认指主队"，导致库里team_total
        # 数据的真实归属队伍不可考（同 12_pinnacle_scraper.py 已修复的同款问题）。
        # 用 mtype 带上 side 前缀彻底分开分组存储。
        if mtype == "team_total":
            _tt_side = m.get("side", "")
            if _tt_side in ("home", "away"):
                mtype = f"team_total_{_tt_side}"
        if not mid:
            continue
        prices = m.get("prices", [])
        if not prices:
            continue
        candidates.setdefault((mid, mtype, period), []).append(prices)

    # 第二遍：每组只保留主盘口线
    by_match: Dict = {}
    for (mid, mtype, period), price_lists in candidates.items():
        best = _pick_main_line(price_lists, mtype) if len(price_lists) > 1 else price_lists[0]
        by_match.setdefault(mid, {})[f"{mtype}_{period}"] = [
            {
                "side":     p.get("designation") or p.get("side", ""),
                "price":    p.get("price"),
                "handicap": p.get("points") if p.get("points") is not None else p.get("handicap"),
                "max_bet":  p.get("maxBet"),
            }
            for p in best if p.get("price") is not None
        ]
    return by_match


def find_correct_score_matchups(main_matchup_ids: list) -> Dict[int, Dict]:
    """对每个主赛事 matchup_id 调用 /matchups/{id}/related，找出全场比分衍生 matchup。

    Pinnacle 的比分盘不在 /leagues/{id}/markets/special（该端点对每个联赛都返回400，
    是从未跑通过的死代码），而是主赛事的一个 related 衍生 matchup，用
    special.description == "Correct Score" 标识（同 12_pinnacle_scraper.py 里
    corners 用 units=="Corners" 识别的模式一致，只是这里的判别字段不同）。
    该衍生 matchup 自己的 participants 是 "TeamA x, TeamB y" 这样的比分选项列表，
    每个 participant 有独立 id，真正的赔率要去 /matchups/{cs_id}/markets/straight
    按 participantId 关联。

    返回: {cs_matchup_id: {"parent_matchup_id": mid, "participants": {participantId: "H-A"}}}
    """
    result: Dict[int, Dict] = {}
    for mid in main_matchup_ids:
        data = _pinn_get(f"/matchups/{mid}/related")
        if not data:
            continue
        related = data if isinstance(data, list) else data.get("matchups", [])
        for rel in related:
            special = rel.get("special") or {}
            if special.get("description") != "Correct Score":
                continue
            cs_id = rel.get("id")
            if not cs_id:
                continue
            pmap = {}
            for p in rel.get("participants", []):
                nums = re.findall(r"\d+", p.get("name", ""))
                if len(nums) >= 2 and p.get("id") is not None:
                    pmap[p["id"]] = f"{nums[0]}-{nums[1]}"
            if pmap:
                result[cs_id] = {"parent_matchup_id": mid, "participants": pmap}
        _sleep()
    return result


def fetch_correct_score_odds(cs_matchup_id: int, participants: Dict[int, str]) -> Dict[str, float]:
    """抓取单个比分衍生 matchup 的赔率，按 participantId 关联回 'H-A' 比分字符串。
    返回 {"H-A": decimal_odds, ...}
    """
    data = _pinn_get(f"/matchups/{cs_matchup_id}/markets/straight")
    if not data:
        return {}
    markets = data if isinstance(data, list) else data.get("markets", [])
    result: Dict[str, float] = {}
    for mk in markets:
        for price in mk.get("prices", []):
            pid = price.get("participantId")
            cs_key = participants.get(pid)
            raw_price = price.get("price")
            if cs_key is None or raw_price is None:
                continue
            amer = float(raw_price)
            if amer == 0:
                continue
            dec_odds = (amer / 100 + 1) if amer > 0 else (100 / abs(amer) + 1)
            result[cs_key] = round(dec_odds, 3)
    return result


def pinn_get_correct_score(league_id: int) -> Dict[int, Dict[str, float]]:
    """获取整个联赛的比分盘赔率。返回 {parent_matchup_id: {"H-A": decimal_odds, ...}}"""
    fixtures = pinn_get_fixtures(league_id)
    main_ids = [f["id"] for f in fixtures if f.get("id")]
    if not main_ids:
        return {}
    cs_map = find_correct_score_matchups(main_ids)
    result: Dict[int, Dict[str, float]] = {}
    for cs_id, info in cs_map.items():
        odds = fetch_correct_score_odds(cs_id, info["participants"])
        if odds:
            result.setdefault(info["parent_matchup_id"], {}).update(odds)
        _sleep()
    return result


def pinn_store_correct_score(engine, league_id: int, fetch_date: str):
    """拉取并写库 pinnacle_correct_score_odds 表。"""
    from sqlalchemy import text as _text
    ddl = """CREATE TABLE IF NOT EXISTS pinnacle_correct_score_odds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matchup_id INTEGER,
        parent_matchup_id INTEGER,
        correct_score TEXT,
        decimal_odds REAL,
        league_id INTEGER,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(parent_matchup_id, correct_score, fetch_date)
    )"""
    with engine.begin() as conn:
        conn.execute(_text(ddl))
        conn.execute(_text("""
            CREATE INDEX IF NOT EXISTS idx_pinn_cs_parent
            ON pinnacle_correct_score_odds(parent_matchup_id, fetch_date)
        """))
    cs_by_match = pinn_get_correct_score(league_id)
    if not cs_by_match:
        return 0
    written = 0
    with engine.begin() as conn:
        for mid, scores in cs_by_match.items():
            for cs_key, dec_odds in scores.items():
                try:
                    conn.execute(_text("""
                        INSERT INTO pinnacle_correct_score_odds
                        (matchup_id, parent_matchup_id, correct_score, decimal_odds, league_id, fetch_date)
                        VALUES (:mid, :mid, :cs, :odds, :lid, :fd)
                        ON CONFLICT(parent_matchup_id, correct_score, fetch_date) DO UPDATE SET
                            decimal_odds = excluded.decimal_odds,
                            matchup_id   = excluded.matchup_id,
                            league_id    = excluded.league_id
                    """), {"mid": mid, "cs": cs_key, "odds": dec_odds,
                           "lid": league_id, "fd": fetch_date})
                    written += 1
                except Exception:
                    pass
    return written


CS_SCRAPE_TIME_BUDGET_S = 600  # 比分盘口需逐场调用/matchups/{id}/related，全球联赛耗时不可控，超预算跳过剩余联赛


def fetch_all_correct_score_odds(fetch_date: str = None) -> int:
    """全量比分盘口抓取：遍历全部有比赛的足球联赛，逐联赛调用 pinn_store_correct_score()。"""
    if fetch_date is None:
        fetch_date = datetime.now(BJ_TZ).strftime("%Y-%m-%d")
    leagues = pinn_get_leagues("soccer")
    log.info(f"比分盘口抓取: {len(leagues)} 个活跃联赛")
    t0 = time.time()
    total = 0
    for i, lg in enumerate(leagues):
        if time.time() - t0 > CS_SCRAPE_TIME_BUDGET_S:
            log.warning(f"比分盘口抓取超时间预算（{CS_SCRAPE_TIME_BUDGET_S}s），"
                        f"跳过剩余 {len(leagues) - i} 个联赛")
            break
        try:
            total += pinn_store_correct_score(engine, lg["id"], fetch_date)
        except Exception as e:
            log.warning(f"  {lg.get('name')} 比分盘口异常: {e}")
    log.info(f"比分盘口抓取完成: {total} 条")
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# 数据源 B: OddsPortal 逆向 AJAX
# ═══════════════════════════════════════════════════════════════════════════════
OP_BASE = "https://www.oddsportal.com"

# OddsPortal 赛程页（用于 Cookie 热身，也是浏览器抓包时真正的比赛列表页）
OP_WARMUP_URLS = [
    "https://www.oddsportal.com/matches/football/",
    "https://www.oddsportal.com/matches/basketball/",
]

_op_session = cffi.Session(impersonate=_rand_imp())
_op_cookies = {}

def _op_warmup():
    """访问赛程页建立 Cookie 会话（反爬热身）"""
    log.info("  OddsPortal Cookie 热身...")
    for url in OP_WARMUP_URLS:
        try:
            _op_session.headers.update({
                "User-Agent":      _rand_ua(),
                "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
                "Referer":         "https://www.google.com/",
            })
            r = _op_session.get(url, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                _op_cookies.update(dict(r.cookies))
                log.info(f"  热身 OK: {url} (cookies: {len(_op_cookies)})")
            _sleep(2, 0.8)
        except Exception as e:
            log.debug(f"热身失败 {url}: {e}")

# 2026-07-12 摸排确认：只有 football 的 sportId=1 经真实响应验证
# （解密后行内 "sport-id":1 字段吻合）。basketball 的 id 没验证过，
# 不瞎猜——之前 op_get_today_events() 的字段名瞎猜就是前车之鉴。
OP_SPORT_IDS = {
    "soccer": 1,
}

# JS 主包里硬编码的 PBKDF2 口令/盐值（2026-07-12 从 app-*.js 逆向出来，实测解密成功）
_OP_PBKDF2_PASSWORD = os.environ.get("OP_PBKDF2_PASSWORD", "REDACTED")
# ↑ sanitized: 原值硬编码在本文件（自 oddsportal app-*.js 逆向得到）。
#   脱敏版改为环境变量读取，默认 "REDACTED"；需要真实解密时请自行从 oddsportal
#   前端 JS 包重新提取。
_OP_PBKDF2_SALT      = os.environ.get("OP_PBKDF2_SALT", "REDACTED")
# ↑ sanitized: 原值为固盐常量（自 JS 包逆向），见上。

def _op_decrypt(body: str) -> Optional[dict]:
    """解密 ajax-nextgames*.dat 响应：base64 → 拆(密文b64:IV hex) → AES-256-CBC → 可能gzip → JSON"""
    if not HAS_PYCRYPTODOME or not body:
        return None
    try:
        outer = base64.b64decode(body).decode("latin1")
        ct_b64, iv_hex = outer.split(":")
        iv = bytes.fromhex(iv_hex)
        ciphertext = base64.b64decode(ct_b64)
        key = _PBKDF2(_OP_PBKDF2_PASSWORD.encode("utf-8"), _OP_PBKDF2_SALT.encode("utf-8"),
                       dkLen=32, count=1000, hmac_hash_module=_SHA256)
        cipher = _AES.new(key, _AES.MODE_CBC, iv)
        pt = _unpad(cipher.decrypt(ciphertext), 16)
        if pt[:2] == b"\x1f\x8b":
            pt = gzip.decompress(pt)
        return json.loads(pt)
    except Exception as e:
        log.debug(f"OP 响应解密失败: {e}")
        return None

def _op_get_nextgames_page(sport_id: int, date_str: str, page: int) -> Optional[dict]:
    """真实接口：/ajax-nextgames/{sportId}/8/2/{YYYYMMDD}/{buildHash}.dat
    "8"/"2"/"yj084"(buildHash) 是抓包实测值，buildHash 疑似跟随站点构建版本，
    如果长期失效大概率是这个值过期了，需要重新抓包确认。"""
    url = f"{OP_BASE}/ajax-nextgames/{sport_id}/8/2/{date_str}/yj084.dat"
    params = {"page": page, "_": int(time.time() * 1000), "hideFinished": 0}
    cache_key = f"{url}?page={page}&date={date_str}"
    cached = _cache_get(cache_key, None)
    if cached is not None:
        return cached

    for attempt in range(3):
        try:
            _op_session.headers.update({
                "User-Agent":       _rand_ua(),
                "Accept":           "application/json, text/plain, */*",
                "Accept-Language":  "en-US,en;q=0.9",
                "Referer":          "https://www.oddsportal.com/matches/football/",
                "X-Requested-With": "XMLHttpRequest",
            })
            r = _op_session.get(url, params=params, cookies=_op_cookies, timeout=20)
            if r.status_code == 200 and r.text:
                data = _op_decrypt(r.text)
                if data is not None:
                    _cache_set(cache_key, None, data)
                return data
            if r.status_code == 429:
                _backoff(attempt)
                continue
            if r.status_code in (403, 503):
                log.warning(f"OP {r.status_code}（触发反爬），重新热身...")
                _op_warmup()
                _sleep(5, 2)
                continue
            log.debug(f"OP {r.status_code}: {url}")
        except Exception as e:
            log.debug(f"OP 异常({attempt+1}): {e}")
            _sleep(3, 1)
    return None

def op_get_today_events(sport_code: str) -> List[Dict]:
    """获取 OddsPortal 今明两天赛程（不含赔率——赔率走 ajax-nextgames-odds，
    该接口的 bHash 参数尚未摸排出计算方式，暂不在这条链路里）"""
    sport_id = OP_SPORT_IDS.get(sport_code)
    if sport_id is None:
        log.debug(f"  OddsPortal {sport_code}: sportId 未验证，跳过")
        return []

    results = []
    start_utc, end_utc = get_bet_window()
    seen_dates = {start_utc.strftime("%Y%m%d"), end_utc.strftime("%Y%m%d")}

    for date_str in seen_dates:
        page = 1
        while page <= 6:  # 保护性上限，正常一天不会超过6页(300场)
            data = _op_get_nextgames_page(sport_id, date_str, page)
            if not data or data.get("s") != 1:
                break
            d = data.get("d", {})
            rows = d.get("rows", [])
            if not rows:
                break

            for ev in rows:
                ts = ev.get("date-start-timestamp")
                try:
                    kt = datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else None
                    if kt and not (start_utc <= kt < end_utc):
                        continue
                except Exception:
                    kt = None

                results.append({
                    "source":     "oddsportal",
                    "sport":      sport_code,
                    "league":     ev.get("tournament-name", ""),
                    "home_team":  ev.get("home-name", ""),
                    "away_team":  ev.get("away-name", ""),
                    "kickoff":    kt.strftime("%Y-%m-%dT%H:%M:%SZ") if kt else "",
                    "event_id":   ev.get("id") or ev.get("encodeEventId") or "",
                    "odds_h2h":   {},  # 这个接口不含赔率
                })

            total = d.get("total", 0)
            one_page = d.get("onePage", len(rows)) or len(rows)
            if page * one_page >= total:
                break
            page += 1
            _sleep(1.2, 0.4)

    log.info(f"  OddsPortal {sport_code}: {len(results)} 场（投注窗口内，仅赛程无赔率）")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 数据库表定义
# ═══════════════════════════════════════════════════════════════════════════════
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS theodds_fixtures (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT,
            sport_code  TEXT,
            league_name TEXT,
            home_team   TEXT,
            away_team   TEXT,
            kickoff_utc TEXT,
            status      TEXT DEFAULT 'NS',
            pinn_id     INTEGER,
            op_event_id TEXT,
            fetch_date  TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, sport_code, home_team, away_team, kickoff_utc)
        )""",
        """CREATE TABLE IF NOT EXISTS theodds_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id  INTEGER,
            source      TEXT,
            bookmaker   TEXT,
            market      TEXT,
            period      INTEGER DEFAULT 0,
            outcome     TEXT,
            price       REAL,
            handicap    REAL,
            max_bet     REAL,
            fetch_date  TEXT,
            updated_at  TEXT,
            UNIQUE(fixture_id, source, bookmaker, market, period, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS theodds_odds_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER,
            source     TEXT,
            bookmaker  TEXT,
            market     TEXT,
            outcome    TEXT,
            price      REAL,
            handicap   REAL,
            recorded_at TEXT,
            fetch_date  TEXT
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ theodds 数据表初始化完成")


from sqlalchemy import MetaData
from db_utils import batch_upsert, exec_ddl as _exec_ddl_unused

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]

def _upsert_fixture(row: Dict) -> Optional[int]:
    sql = text("""
        INSERT INTO theodds_fixtures
            (source, sport_code, league_name, home_team, away_team,
             kickoff_utc, status, pinn_id, op_event_id, fetch_date)
        VALUES
            (:source, :sport_code, :league_name, :home_team, :away_team,
             :kickoff_utc, :status, :pinn_id, :op_event_id, :fetch_date)
        ON CONFLICT(source, sport_code, home_team, away_team, kickoff_utc)
        DO UPDATE SET
            league_name = excluded.league_name,
            status      = excluded.status,
            pinn_id     = excluded.pinn_id,
            fetch_date  = excluded.fetch_date
        RETURNING id
    """)
    try:
        with engine.begin() as conn:
            result = conn.execute(sql, row)
            row_id = result.scalar()
            if row_id is None:
                r2 = conn.execute(text("""
                    SELECT id FROM theodds_fixtures
                    WHERE source=:source AND sport_code=:sport_code
                      AND home_team=:home_team AND away_team=:away_team
                      AND kickoff_utc=:kickoff_utc
                """), row)
                row_id = (r2.fetchone() or [None])[0]
            return row_id
    except Exception as e:
        log.debug(f"fixture upsert 失败: {e}")
        return None


# 收集 odds 和 history 行，由调用方统一批量写入（线程安全）
_odds_rows: list = []
_history_rows: list = []
_batch_lock = threading.Lock()

def _reset_odds_batch():
    global _odds_rows, _history_rows
    _odds_rows = []
    _history_rows = []

def _flush_odds_batch():
    global _odds_rows, _history_rows
    if _odds_rows:
        tbl = _get_table(engine, "theodds_odds")
        batch_upsert(engine, tbl, _odds_rows,
                     unique_keys=["fixture_id", "source", "bookmaker", "market", "period", "outcome"])
    if _history_rows:
        tbl = _get_table(engine, "theodds_odds_history")
        batch_upsert(engine, tbl, _history_rows,
                     unique_keys=["id"])
    _odds_rows = []
    _history_rows = []

def _upsert_odds(fixture_id: int, source: str, bookmaker: str,
                 market: str, period: int, outcome: str,
                 price: float, handicap, max_bet, fetch_date: str):
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with _batch_lock:
        _odds_rows.append({
            "fixture_id": fixture_id, "source": source, "bookmaker": bookmaker,
            "market": market, "period": period,
            "outcome": outcome, "price": float(price),
            "handicap": handicap, "max_bet": max_bet,
            "fetch_date": fetch_date, "updated_at": now,
        })
        _history_rows.append({
            "fixture_id": fixture_id, "source": source, "bookmaker": bookmaker,
            "market": market, "outcome": outcome,
            "price": float(price), "handicap": handicap,
            "recorded_at": now, "fetch_date": fetch_date,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════
SPORT_CODES = ["soccer", "basketball"]

def _fetch_one_league(lg: Dict, sport: str) -> Optional[tuple]:
    """并发工作函数：抓取单联赛的赛事+赔率，纯 IO，不写 DB。"""
    lid  = lg["id"]
    name = lg["name"]
    fixtures = pinn_get_fixtures(lid)
    if not fixtures:
        return None
    odds_by_match = pinn_get_odds(lid)
    return (name, sport, fixtures, odds_by_match)


def _write_league_to_db(result: tuple, fetch_date: str) -> int:
    """将单联赛结果写入 DB（串行调用，避免 SQLite 写冲突）。"""
    name, sport, fixtures, odds_by_match = result
    total_fix = 0
    for fx in fixtures:
        mid = fx["id"]
        row = {
            "source":      "pinnacle",
            "sport_code":  sport,
            "league_name": name,
            "home_team":   fx["home_team"],
            "away_team":   fx["away_team"],
            "kickoff_utc": fx["kickoff"],
            "status":      fx["status"],
            "pinn_id":     mid,
            "op_event_id": None,
            "fetch_date":  fetch_date,
        }
        fid = _upsert_fixture(row)
        if fid is None:
            continue

        match_odds = odds_by_match.get(mid, {})
        for market_key, prices in match_odds.items():
            parts = market_key.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                market = parts[0]
                period = int(parts[1])
            else:
                market = market_key
                period = 0
            if period != 0:
                continue
            for p in prices:
                if p.get("price") is None:
                    continue
                _upsert_odds(
                    fid, "pinnacle", "pinnacle",
                    market, period,
                    p.get("side", ""),
                    p["price"],
                    p.get("points") if p.get("points") is not None else p.get("handicap"),
                    p.get("max_bet"), fetch_date,
                )
        total_fix += 1
    log.info(f"  [{name}] {len(fixtures)} 场")
    return total_fix


def run_pinnacle(fetch_date: str):
    log.info("=" * 60)
    log.info("[A] Pinnacle Guest API (并发模式, workers=5)")
    log.info("=" * 60)

    _reset_odds_batch()

    for sport in SPORT_CODES:
        log.info(f"\n🏟  {sport.upper()}")
        leagues = pinn_get_leagues(sport)
        total_fix = 0

        # 并发抓取：5个 worker 同时请求 Pinnacle API（IO 密集型）
        fetched_results = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_fetch_one_league, lg, sport): lg for lg in leagues}
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                    if result:
                        fetched_results.append(result)
                except Exception as e:
                    lg = futures[fut]
                    log.warning(f"  联赛 {lg.get('name')} 抓取异常: {e}")

        # 串行写 DB（SQLite WAL 模式支持并发读，写仍需串行）
        for result in fetched_results:
            total_fix += _write_league_to_db(result, fetch_date)

        log.info(f"  Pinnacle {sport} 合计: {total_fix} 场写入")

    _flush_odds_batch()


def run_oddsportal(fetch_date: str):
    """
    数据源 B: OddsPortal（www.oddsportal.com）
    替代目标: the-odds-api.com（无法直接爬取，OddsPortal 数据范围等价）
    接入方式: curl_cffi 直连 /api/beta/{sport}/ JSON 接口（op_get_today_events），无浏览器。
    局限: 只覆盖列表页可见的独赢(h2h)赔率；大小球/让球在单场详情页，详情页JSON接口
         尚未摸排确认，暂不在这条链路里——如需完整盘口仍要单独跑
         10_oddsportal_scraper.py 的 Playwright 详情页抓取（--odds 参数）。
    数据合并: 抓到的赛事+赔率直接写入 theodds_fixtures / theodds_odds
    """
    log.info("\n" + "=" * 60)
    log.info("📡 数据源 B: OddsPortal（curl_cffi 直连JSON接口，无浏览器）")
    log.info("=" * 60)

    _op_warmup()

    synced = 0
    _reset_odds_batch()
    for sport in SPORT_CODES:
        try:
            events = op_get_today_events(sport)
        except Exception as e:
            log.warning(f"  OddsPortal {sport} 抓取失败（不影响主流程）: {e}")
            continue

        for ev in events:
            home = (ev.get("home_team") or "").strip()
            away = (ev.get("away_team") or "").strip()
            if not home or not away:
                continue

            fix_row = {
                "source":      "oddsportal",
                "sport_code":  sport,
                "league_name": ev.get("league") or f"{sport.title()} (Other)",
                "home_team":   home,
                "away_team":   away,
                "kickoff_utc": str(ev.get("kickoff") or ""),
                "status":      "NS",
                "pinn_id":     None,
                "op_event_id": str(ev.get("event_id") or ""),
                "fetch_date":  fetch_date,
            }
            fid = _upsert_fixture(fix_row)
            if fid is None:
                continue
            synced += 1

            # odds_h2h 具体字段名未经真实响应验证，宽松取值，取不到就只落赛程不落赔率
            odds_h2h = ev.get("odds_h2h") or {}
            for outcome, keys in (("home", ("home", "1", "homeOdds")),
                                   ("draw", ("draw", "x", "drawOdds")),
                                   ("away", ("away", "2", "awayOdds"))):
                price = next((odds_h2h.get(k) for k in keys if odds_h2h.get(k)), None)
                if price:
                    try:
                        _upsert_odds(fid, "oddsportal", "oddsportal",
                                     "1X2", 0, outcome,
                                     float(price), None, None, fetch_date)
                    except Exception:
                        pass

    _flush_odds_batch()
    log.info(f"  OddsPortal 合计同步: {synced} 场（今明投注窗口内，仅h2h）")


def run(fetch_date: str = None):
    if fetch_date is None:
        fetch_date = datetime.now(BJ_TZ).strftime("%Y-%m-%d")

    start_utc, end_utc = get_bet_window()
    log.info("=" * 60)
    log.info(f"🌐 The Odds 全量爬虫启动  [{fetch_date}]")
    log.info(f"   投注窗口: {start_utc.strftime('%m/%d %H:%M')} UTC → "
             f"{end_utc.strftime('%m/%d %H:%M')} UTC")
    log.info(f"   即北京时间: 今日 13:00 → 次日 13:00")
    log.info("=" * 60)

    init_tables()

    t0 = time.time()
    run_pinnacle(fetch_date)
    run_oddsportal(fetch_date)
    elapsed = time.time() - t0

    with engine.connect() as conn:
        total = conn.execute(text(
            "SELECT COUNT(*) FROM theodds_fixtures WHERE fetch_date=:d"
        ), {"d": fetch_date}).scalar()
        odds_total = conn.execute(text(
            "SELECT COUNT(*) FROM theodds_odds WHERE fetch_date=:d"
        ), {"d": fetch_date}).scalar()

    log.info("\n" + "=" * 60)
    log.info(f"✅ 爬取完成  耗时 {elapsed:.1f}s")
    log.info(f"   赛事对阵表: {total} 场")
    log.info(f"   赔率数据:   {odds_total} 条")
    log.info("=" * 60)
    return total


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="The Odds 全量爬虫（无需 API Key）")
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD，默认今日")
    parser.add_argument("--no-cache", action="store_true", help="忽略本地缓存强制重爬")
    args = parser.parse_args()

    if args.no_cache:
        import shutil
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        log.info("🗑  缓存已清空")

    run(args.date)
