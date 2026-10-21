# 13_bet365_scraper.py — Bet365 补充爬虫
# 策略：多路并发
#   A. Playwright stealth 模式直接访问 bet365.com（最真实）
#   B. 逆向 Bet365 内部 API（OddsChange/InPlay 端点）
#   C. 通过 RapidAPI bet365-api 作为备用
# 存储：bet365_fixtures / bet365_odds / bet365_inplay
# 反爬：stealth模式 + 随机指纹 + 人工行为模拟 + 代理支持

import sys, re, time, random, json, logging
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP, RAPIDAPI_KEY
from db_utils import batch_upsert, exec_ddl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

from sqlalchemy import MetaData

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]
engine = create_engine(DB_ENGINE_URL)

# ─── 依赖检测 ─────────────────────────────────────────────────────────────────
HAS_CURL_CFFI = False
try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    log.warning("curl_cffi 未安装，Bet365 方法B不可用。安装: pip install curl_cffi")

HAS_PLAYWRIGHT = False
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    log.warning("playwright 未安装，Bet365 Playwright 模式不可用。安装: pip install playwright && playwright install")

import requests as std_requests

# ─── 常量 ─────────────────────────────────────────────────────────────────────
BET365_BASE   = "https://www.bet365.com"
# Bet365 内部分数/赔率 API（通过抓包获得，随版本变化）
BET365_OC_API = "https://odds.bet365.com/OddsChange"
BET365_IP_API = "https://in-play.bet365.com/0.1/InPlayService.svc/GetScoreboardData"

# RapidAPI Bet365 端点
RAPID_BET365_HOST = "bet365-api-inplay.p.rapidapi.com"
RAPID_BET365_BASE = "https://bet365-api-inplay.p.rapidapi.com"

# 市场类型
MARKETS = ["1X2", "AH", "O/U", "DNB", "HalfTime"]

HEADERS_STEALTH = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.bet365.com/",
    "Origin":  "https://www.bet365.com",
}


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS bet365_fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            b365_event_id TEXT UNIQUE,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            source TEXT,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS bet365_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            b365_event_id TEXT,
            market TEXT,
            outcome TEXT,
            odds_value REAL,
            handicap REAL,
            is_live INTEGER DEFAULT 0,
            source TEXT,
            fetch_date TEXT,
            recorded_at TEXT,
            UNIQUE(b365_event_id, market, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS bet365_inplay (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            b365_event_id TEXT,
            minute INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            home_odds REAL,
            draw_odds REAL,
            away_odds REAL,
            recorded_at TEXT,
            fetch_date TEXT
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ Bet365 数据表初始化完成")


def _sleep():
    time.sleep(random.uniform(CRAWL_MIN_SLEEP + 1, CRAWL_MAX_SLEEP + 2))


# ═══════════════════════════════════════════════════════════════════════════════
# 方法 A：Playwright Stealth（最可靠，需安装 chromium）
# ═══════════════════════════════════════════════════════════════════════════════
def _install_playwright_browser():
    import subprocess
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium", "--quiet"],
                   capture_output=True)


def _human_scroll(page):
    """模拟人工滚动行为"""
    for _ in range(random.randint(2, 4)):
        page.mouse.wheel(0, random.randint(200, 600))
        time.sleep(random.uniform(0.5, 1.5))


def fetch_via_playwright(sport: str, fetch_date: str) -> int:
    if not HAS_PLAYWRIGHT:
        log.warning("Playwright 不可用，跳过方法A")
        return 0

    try:
        _install_playwright_browser()
    except Exception:
        pass

    count = 0
    try:
        with sync_playwright() as pw:
            # headless=False 绕过 Bet365 "Target crashed" 检测
            browser = pw.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    f"--window-size={random.choice([1366, 1440, 1920])},{random.choice([768, 900, 1080])}",
                ]
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="en-GB",
                timezone_id="Europe/London",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={
                    "Accept-Language": "en-GB,en;q=0.9",
                    "DNT": "1",
                },
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()

            captured_odds = []

            def handle_response(response):
                try:
                    url = response.url
                    if any(kw in url for kw in ["OddsChange", "odds", "event", "market"]):
                        if response.status == 200:
                            body = response.text()
                            if body and len(body) > 10:
                                captured_odds.append({"url": url, "body": body[:5000]})
                except Exception:
                    pass

            page.on("response", handle_response)

            sport_path = "football" if sport == "football" else "basketball"
            target_url = f"{BET365_BASE}/#/IP/{sport_path}"

            try:
                page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(random.uniform(3, 6))

                # 地理封锁检测：IP 被重定向到美国版，无可用赔率
                current_url = page.url
                page_title = page.title()
                if 'usa' in current_url.lower() or 'isoCode=US' in current_url or 'bet365 US' in page_title:
                    log.warning(
                        f'Bet365 IP 地理封锁：重定向至 {current_url[:80]} — '
                        '需使用非美国 IP（VPN/代理）访问赔率数据'
                    )
                    browser.close()
                    return 0

                _human_scroll(page)

                try:
                    page.wait_for_selector(".gl-MarketGroup, .rcl-MarketHeaderLabel", timeout=15000)
                except PWTimeout:
                    pass

                _human_scroll(page)

                count += _extract_from_page(page, sport, fetch_date)

                for item in captured_odds:
                    count += _parse_xhr_odds(item["body"], item["url"], fetch_date)

            except PWTimeout:
                log.warning("Playwright 页面超时")
            except Exception as e:
                log.warning(f"Playwright 异常: {e}")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    except Exception as e:
        log.warning(f"Playwright 启动失败: {e}")

    return count


def _extract_from_page(page, sport: str, fetch_date: str) -> int:
    """从 Playwright 页面提取赔率"""
    count = 0
    try:
        events = page.query_selector_all(".rcl-ParticipantFixtureDetails, .gl-MarketGroup_Wrapper")
        for ev in events[:50]:
            try:
                text_content = ev.inner_text()
                lines = [l.strip() for l in text_content.split("\n") if l.strip()]
                if len(lines) < 3:
                    continue

                home_team = lines[0] if lines else ""
                away_team = lines[1] if len(lines) > 1 else ""

                odds_vals = []
                for line in lines:
                    try:
                        v = float(line)
                        if 1.01 <= v <= 50:
                            odds_vals.append(v)
                    except Exception:
                        pass

                if len(odds_vals) >= 2:
                    ev_id = f"pw_{sport}_{hash(home_team+away_team) & 0xFFFFFF:06x}"
                    _upsert_fixture(ev_id, sport, "live", home_team, away_team,
                                    datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                                    "LIVE", None, None, "playwright", fetch_date)
                    for i, (outcome, val) in enumerate(
                            zip(["home", "draw", "away"] if len(odds_vals) >= 3 else ["home", "away"],
                                odds_vals)):
                        _upsert_odds(ev_id, "1X2", outcome, val, None, 1, "playwright", fetch_date)
                    count += 1
            except Exception:
                pass
    except Exception as e:
        log.debug(f"页面提取异常: {e}")
    return count


def _parse_xhr_odds(body: str, url: str, fetch_date: str) -> int:
    """解析拦截到的 XHR 赔率数据"""
    count = 0
    try:
        data = json.loads(body)
        events = (data.get("events") or data.get("fixtures") or
                  data.get("data", {}).get("events", []) or [])
        for ev in (events if isinstance(events, list) else []):
            ev_id = str(ev.get("id") or ev.get("eventId") or "")
            if not ev_id:
                continue
            home = ev.get("homeTeam", ev.get("home", {}).get("name", "") if isinstance(ev.get("home"), dict) else "")
            away = ev.get("awayTeam", ev.get("away", {}).get("name", "") if isinstance(ev.get("away"), dict) else "")
            odds_data = ev.get("odds") or ev.get("markets") or []
            _upsert_fixture(ev_id, "unknown", "unknown", home, away, "", "NS", None, None, "xhr", fetch_date)
            for odd in (odds_data if isinstance(odds_data, list) else []):
                market  = odd.get("type", odd.get("name", "1X2"))
                outcome = odd.get("outcome", odd.get("selection", ""))
                val     = odd.get("price", odd.get("odds", odd.get("value")))
                if val:
                    try:
                        _upsert_odds(ev_id, market, outcome, float(val), None, 0, "xhr", fetch_date)
                    except Exception:
                        pass
            count += 1
    except Exception:
        pass
    return count


# ═══════════════════════════════════════════════════════════════════════════════
# 方法 B：curl_cffi 直接请求 Bet365 OddsChange API
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_via_direct_api(sport: str, fetch_date: str) -> int:
    if not HAS_CURL_CFFI:
        log.warning("curl_cffi 不可用，跳过方法B")
        return 0

    count = 0
    sess = cffi_requests.Session(impersonate=random.choice(["chrome116", "chrome123", "firefox133", "edge99"]))
    sess.headers.update(HEADERS_STEALTH)

    # 先获取主页 cookies
    try:
        sess.get(BET365_BASE, timeout=20)
        time.sleep(random.uniform(2, 4))
    except Exception:
        pass

    sport_id = "1" if sport == "football" else "2"
    endpoints = [
        f"{BET365_OC_API}?sport={sport_id}&format=json",
        f"{BET365_BASE}/defaultapi/SportsBook.API/Web?sport={sport_id}&lang=1&country=1",
    ]

    for url in endpoints:
        try:
            r = sess.get(url, timeout=25)
            if r.status_code == 200:
                try:
                    data = r.json()
                    count += _parse_direct_api(data, sport, fetch_date)
                    if count > 0:
                        break
                except Exception:
                    pass
        except Exception as e:
            log.debug(f"直连API异常: {e}")
        _sleep()

    return count


def _parse_direct_api(data: dict, sport: str, fetch_date: str) -> int:
    count = 0
    events = (data.get("events") or data.get("Fixtures") or
              data.get("data", {}).get("events", []) or [])
    for ev in (events if isinstance(events, list) else []):
        try:
            ev_id    = str(ev.get("id") or ev.get("EventId") or "")
            home     = ev.get("homeTeam") or ev.get("Home", "")
            away     = ev.get("awayTeam") or ev.get("Away", "")
            kickoff  = ev.get("startTime") or ev.get("Date", "")
            league   = ev.get("leagueName") or ev.get("Competition", "")
            hs       = ev.get("homeScore") or ev.get("HomeScore")
            as_      = ev.get("awayScore") or ev.get("AwayScore")
            status   = "FT" if hs is not None else "NS"

            if not ev_id or not home:
                continue

            _upsert_fixture(ev_id, sport, league, home, away, str(kickoff),
                            status, hs, as_, "direct_api", fetch_date)

            # 赔率
            for market in (ev.get("markets") or ev.get("Odds") or []):
                market_name = market.get("type") or market.get("Name", "1X2")
                for sel in (market.get("selections") or market.get("Prices") or []):
                    outcome = sel.get("name") or sel.get("Name", "")
                    val     = sel.get("price") or sel.get("Odds")
                    if val:
                        try:
                            _upsert_odds(ev_id, market_name, outcome, float(val),
                                         sel.get("handicap"), 0, "direct_api", fetch_date)
                        except Exception:
                            pass
            count += 1
        except Exception as e:
            log.debug(f"direct_api解析: {e}")
    return count


# ═══════════════════════════════════════════════════════════════════════════════
# 方法 C：RapidAPI bet365 备用
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_via_rapidapi(sport: str, fetch_date: str) -> int:
    if not RAPIDAPI_KEY or RAPIDAPI_KEY == "***":
        log.info("RapidAPI Key 未配置，跳过方法C")
        return 0

    count = 0
    headers = {
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": RAPID_BET365_HOST,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    endpoints = [
        f"{RAPID_BET365_BASE}/inplay",
        f"{RAPID_BET365_BASE}/bet365/get_prematch_odds",
    ]

    for url in endpoints:
        try:
            params = {"sport": sport, "page": "1"}
            r = std_requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                count += _parse_rapidapi_bet365(data, sport, fetch_date)
            elif r.status_code == 429:
                log.warning("RapidAPI 限流")
                break
        except Exception as e:
            log.debug(f"RapidAPI异常: {e}")
        _sleep()

    return count


def _parse_rapidapi_bet365(data: dict, sport: str, fetch_date: str) -> int:
    count = 0
    events = (data.get("results") or data.get("data") or
              data.get("events") or [])
    for ev in (events if isinstance(events, list) else []):
        try:
            ev_id   = str(ev.get("id") or ev.get("event_id") or "")
            home    = ev.get("home") or ev.get("home_team", "")
            away    = ev.get("away") or ev.get("away_team", "")
            league  = ev.get("league") or ev.get("competition", "")
            kickoff = ev.get("time") or ev.get("start_time", "")
            hs      = ev.get("ss", "").split("-")[0] if ev.get("ss") else None
            as_     = ev.get("ss", "").split("-")[-1] if ev.get("ss") else None

            try:
                hs = int(hs) if hs else None
                as_ = int(as_) if as_ else None
            except Exception:
                hs = as_ = None

            if not ev_id or not home:
                continue

            _upsert_fixture(ev_id, sport, league, home, away, str(kickoff),
                            "NS", hs, as_, "rapidapi", fetch_date)

            # 赔率
            odds = ev.get("odds") or {}
            if isinstance(odds, dict):
                for market_name, market_odds in odds.items():
                    if isinstance(market_odds, dict):
                        for outcome, val in market_odds.items():
                            try:
                                _upsert_odds(ev_id, market_name, outcome, float(val),
                                             None, 0, "rapidapi", fetch_date)
                            except Exception:
                                pass
            count += 1
        except Exception as e:
            log.debug(f"rapidapi解析: {e}")
    return count


# ─── 数据库写入缓冲 ───────────────────────────────────────────────────────────
_fixture_rows: list = []
_odds_rows:    list = []


def _upsert_fixture(ev_id, sport, league, home, away, kickoff, status,
                     hs, as_, source, fetch_date):
    _fixture_rows.append({
        "b365_event_id": ev_id, "sport_code": sport, "league_name": league,
        "home_team": home, "away_team": away, "kickoff_utc": str(kickoff),
        "status": status, "home_score": hs, "away_score": as_,
        "source": source, "fetch_date": fetch_date,
    })


def _upsert_odds(ev_id, market, outcome, odds_val, handicap, is_live, source, fetch_date):
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _odds_rows.append({
        "b365_event_id": ev_id, "market": market, "outcome": outcome,
        "odds_value": odds_val, "handicap": handicap, "is_live": is_live,
        "source": source, "fetch_date": fetch_date, "recorded_at": now,
    })


def _flush(engine):
    from sqlalchemy import MetaData as _MD
    written = 0
    if _fixture_rows:
        try:
            md = _MD(); md.reflect(bind=engine)
            batch_upsert(engine, md.tables['bet365_fixtures'], _fixture_rows,
                         unique_keys=['b365_event_id'])
            written += len(_fixture_rows)
        except Exception as e:
            log.warning(f"bet365_fixtures写库失败: {e}")
        _fixture_rows.clear()
    if _odds_rows:
        try:
            md = _MD(); md.reflect(bind=engine)
            batch_upsert(engine, md.tables['bet365_odds'], _odds_rows,
                         unique_keys=['b365_event_id', 'market', 'outcome'])
            written += len(_odds_rows)
        except Exception as e:
            log.warning(f"bet365_odds写库失败: {e}")
        _odds_rows.clear()
    return written


# ─── 主流程 ───────────────────────────────────────────────────────────────────
def run():
    global _fixture_rows, _odds_rows
    init_tables()
    _fixture_rows, _odds_rows = [], []
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    log.info(f"Bet365 多路爬取开始 [{fetch_date}]")

    total = 0
    for sport in ["football", "basketball"]:
        log.info(f"  {sport}")

        n = fetch_via_playwright(sport, fetch_date)
        log.info(f"    Playwright: {n} 条")
        total += n
        _sleep()

        n2 = fetch_via_direct_api(sport, fetch_date)
        log.info(f"    直连API: {n2} 条")
        total += n2
        _sleep()

        n3 = fetch_via_rapidapi(sport, fetch_date)
        log.info(f"    RapidAPI: {n3} 条")
        total += n3
        _sleep()

    written = _flush(engine)
    log.info(f"Bet365 完成: {total} 条计数, {written} 条写库")


if __name__ == "__main__":
    run()
