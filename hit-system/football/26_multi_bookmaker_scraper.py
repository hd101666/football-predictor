# 26_multi_bookmaker_scraper.py — 多庄家赔率爬虫
# 覆盖: William Hill / DraftKings / FanDuel / Unibet / Bovada
# 全部使用公开JSON端点或低防护HTML，无需API Key
import sys, time, logging, re, json, argparse
import requests
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
import urllib3; urllib3.disable_warnings()

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

from sqlalchemy import MetaData

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]
engine = create_engine(DB_ENGINE_URL)


_pending_rows: list = []  # 模块级缓冲，_save() 写入，run() 末尾刷库


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS multi_bookie_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT,
            event_id    TEXT,
            sport       TEXT,
            competition TEXT,
            home_team   TEXT,
            away_team   TEXT,
            match_time  TEXT,
            market      TEXT,
            selection   TEXT,
            odds        REAL,
            handicap    REAL,
            fetch_date  TEXT,
            UNIQUE(source, event_id, market, selection, fetch_date)
        )
    """)


def _get(url, headers=None, params=None, use_cffi=False):
    H = headers or {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
        'Accept': 'application/json, */*',
    }
    for attempt in range(3):
        try:
            if use_cffi:
                from curl_cffi import requests as cffi_requests
                sess = cffi_requests.Session(impersonate='chrome131')
                r = sess.get(url, headers=H, params=params, timeout=15, verify=False)
            else:
                r = requests.get(url, headers=H, params=params, timeout=15, verify=False)
            time.sleep(1)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    return r.text
            log.debug(f'HTTP {r.status_code}: {url[:60]}')
        except Exception as e:
            log.debug(f'请求失败 attempt {attempt+1}: {e}')
            time.sleep(2 ** attempt)
    return None


def _save(source, event_id, sport, competition, home, away, match_time,
          market, selection, odds, handicap, fetch_date):
    if not odds or float(odds) <= 1.0:
        return
    try:
        _pending_rows.append({
            'source': source, 'event_id': str(event_id), 'sport': sport,
            'competition': competition, 'home_team': home, 'away_team': away,
            'match_time': match_time, 'market': market, 'selection': selection,
            'odds': float(odds), 'handicap': handicap, 'fetch_date': fetch_date,
        })
    except Exception as e:
        log.debug(f"save skip: {e}")


# ── William Hill ───────────────────────────────────────────────────────────
# WARNING: William Hill 前端为 SPA，正则提取不稳定
# 已死（FIX-015-2，2026-09-15 实测）：sports.williamhill.com 对本机出口
# 直接 403（WAF/地域封锁，curl_cffi chrome131 伪装亦被拦）——"每日✅但零落库"
# 的真因是 _get 三次 403 返回 None，函数静默 return 0。函数保留勿删，
# 将来有英国代理时可评估复活。
def fetch_william_hill(fetch_date):
    count = 0
    # William Hill 公开 API
    urls = [
        'https://sports.williamhill.com/betting/en-gb/football/matches',
        'https://sports.williamhill.com/api/v2/markets?sport=FOOTBALL&count=50',
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
        'Accept': 'application/json',
        'Referer': 'https://sports.williamhill.com/',
    }
    data = _get('https://sports.williamhill.com/betting/en-gb/football/matches',
                headers=headers, use_cffi=True)
    if isinstance(data, str) and len(data) > 1000:
        # Parse embedded JSON
        matches = re.findall(r'"eventId"\s*:\s*"?(\w+)"?.*?"name"\s*:\s*"([^"]+)"', data)
        prices = re.findall(r'"price"\s*:\s*"([\d./]+)"', data)
        log.info(f'  William Hill: 找到 {len(matches)} 赛事, {len(prices)} 价格点')

        # Extract structured data
        events = re.findall(
            r'"eventId"\s*:\s*"?(\w+)"?[^}]*"name"\s*:\s*"([^"]+)"[^}]*"price"\s*:\s*"([\d./]+)"',
            data
        )
        for eid, name, price in events[:100]:
            teams = name.split(' v ')
            if len(teams) == 2:
                odds = _decimal_odds(price)
                if odds:
                    _save('william_hill', eid, 'football', '', teams[0], teams[1],
                          '', 'moneyline', 'home', odds, None, fetch_date)
                    count += 1
    return count


def _decimal_odds(price_str):
    """转换 '5/4' 或 '2.25' 为小数赔率"""
    if not price_str:
        return None
    try:
        if '/' in str(price_str):
            num, den = price_str.split('/')
            return round(int(num)/int(den) + 1, 3)
        return float(price_str)
    except Exception:
        return None


# ── DraftKings ─────────────────────────────────────────────────────────────
# 已死（FIX-015-2，2026-09-15 实测）：sportsbook-nash.draftkings.com 对本机
# 出口 403 Access Denied（Akamai 地域拦截，DK 仅服务美国本土）。函数保留，
# 将来有美国代理时可评估复活（15号 Pinnacle 已有 HTTPS_PROXY 先例）。
def fetch_draftkings(fetch_date):
    count = 0
    # DraftKings 公开 API
    sports = [
        ('soccer', 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusny/v1/leagues?format=json&sport=SOCCER'),
        ('basketball', 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusny/v1/leagues?format=json&sport=BASKETBALL'),
    ]
    H = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
        'Accept': 'application/json',
        'Referer': 'https://sportsbook.draftkings.com/',
    }
    for sport, url in sports:
        data = _get(url, headers=H)
        if not data or not isinstance(data, dict):
            continue
        leagues = data.get('leagues', [])
        for league in leagues[:10]:
            lid = league.get('leagueId')
            lname = league.get('leagueName', '')
            if not lid:
                continue
            # Get events for this league
            events_url = f'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusny/v1/leagues/{lid}/categories?format=json'
            edata = _get(events_url, headers=H)
            if not edata or not isinstance(edata, dict):
                continue

            events = edata.get('events', [])
            for evt in events[:30]:
                home = evt.get('teamName1', '')
                away = evt.get('teamName2', '')
                event_id = evt.get('eventId', '')
                start_time = evt.get('startDateEastern', '')

                offers = evt.get('offers', [])
                for offer in offers:
                    market = offer.get('label', '')
                    outcomes = offer.get('outcomes', [])
                    for oc in outcomes:
                        sel = oc.get('label', '')
                        odds_am = oc.get('oddsAmerican', '')
                        odds_dec = oc.get('oddsDecimal', '')
                        if odds_dec:
                            _save('draftkings', event_id, sport, lname,
                                  home, away, start_time, market, sel,
                                  float(odds_dec), None, fetch_date)
                            count += 1
            time.sleep(0.5)
    return count


# ── FanDuel ────────────────────────────────────────────────────────────────
# 已死（FIX-015-2，2026-09-15 实测）：content-managed-page?customPageId=soccer
# 端点返回 404 {"error":true}——端点已下线/改版（非封锁，HTTP层是通的）。
# 函数保留，待新端点摸排后再复活。
def fetch_fanduel(fetch_date):
    count = 0
    H = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
        'Accept': 'application/json',
        'Referer': 'https://sportsbook.fanduel.com/',
    }
    sports_tabs = [
        ('soccer', 'https://sbapi.ny.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=soccer&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York'),
        ('basketball', 'https://sbapi.ny.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=nba&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York'),
    ]
    for sport, url in sports_tabs:
        data = _get(url, headers=H)
        if not data or not isinstance(data, dict):
            continue
        try:
            attached = data.get('attachments', {})
            events = attached.get('events', {})
            markets = attached.get('markets', {})

            for event_id, evt in list(events.items())[:50]:
                home = evt.get('homeTeam', {}).get('teamName', '')
                away = evt.get('awayTeam', {}).get('teamName', '')
                comp = evt.get('competitionName', '')
                start = evt.get('openDate', '')
                evt_mkts = evt.get('marketIds', [])

                for mkt_id in evt_mkts:
                    mkt = markets.get(str(mkt_id), {})
                    mkt_name = mkt.get('marketType', '')
                    for runner in mkt.get('runners', []):
                        sel = runner.get('runnerName', '')
                        win_run = runner.get('winRunnerOdds', {})
                        decimal_odds = win_run.get('decimalDisplayOdds', {}).get('decimalOdds')
                        if decimal_odds:
                            _save('fanduel', event_id, sport, comp,
                                  home, away, start, mkt_name, sel,
                                  float(decimal_odds), None, fetch_date)
                            count += 1
        except Exception as e:
            log.debug(f'FanDuel 解析: {e}')
    return count


# ── Unibet ─────────────────────────────────────────────────────────────────
# FIX-015-2（2026-09-15 修复，接回）：旧端点 unibet.com/sportsbook-feeds/views/
# filter/... 已改版——HTTP 200 但 layout 里只剩赌场推广 widget，无任何赛事，
# 是"每日✅但四家零落库"中唯一"端点活着只是解析对不上"的一家。
# Unibet 实际是 Kambi 平台，改接 Kambi 公开 JSON feed
# （实测：足球 255 场、243/256 场 Match 盘三向赔率完整、篮球 39 场；
# 赔率为千分位整数，沿用既有 /1000 换算逻辑）。
def fetch_unibet(fetch_date):
    count = 0
    H = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
        'Accept': 'application/json',
        'Referer': 'https://www.unibet.com/',
    }
    urls = [
        ('football',   'https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/football.json'),
        ('basketball', 'https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/basketball.json'),
    ]
    for sport, url in urls:
        data = _get(url, headers=H, params={'lang': 'en_GB', 'market': 'GB'})
        if not data or not isinstance(data, dict):
            continue
        try:
            for item in data.get('events', [])[:300]:
                evt = item.get('event', {})
                home = evt.get('homeName', '')
                away = evt.get('awayName', '')
                event_id = evt.get('id', '')
                comp = evt.get('group', '')
                start = evt.get('start', '')
                for offer in item.get('betOffers', []):
                    mkt = offer.get('betOfferType', {}).get('name', '')
                    for outcome in offer.get('outcomes', []):
                        sel = outcome.get('label', '')
                        odds = outcome.get('odds')
                        if odds:
                            if isinstance(odds, int) and odds > 100:
                                odds = odds / 1000.0
                            _save('unibet', event_id, sport, comp,
                                  home, away, start, mkt, sel,
                                  float(odds), None, fetch_date)
                            count += 1
        except Exception as e:
            log.debug(f'Unibet 解析: {e}')
        time.sleep(1)
    return count


# ── Bovada ─────────────────────────────────────────────────────────────────
def fetch_bovada(fetch_date):
    count = 0
    H = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
        'Accept': 'application/json',
        'Referer': 'https://www.bovada.lv/',
    }
    urls = [
        ('football', 'https://www.bovada.lv/services/sports/event/coupon/events/A/description/soccer/soccer-europe/premier-league?lang=en'),
        ('basketball', 'https://www.bovada.lv/services/sports/event/coupon/events/A/description/basketball/nba?lang=en'),
    ]
    for sport, url in urls:
        data = _get(url, headers=H, use_cffi=True)
        if not data or not isinstance(data, list):
            continue
        try:
            for section in data:
                for event in section.get('events', [])[:50]:
                    competitors = event.get('competitors', [])
                    if len(competitors) >= 2:
                        home = competitors[0].get('name', '')
                        away = competitors[1].get('name', '')
                    else:
                        continue
                    event_id = event.get('id', '')
                    comp = event.get('description', '')
                    start = event.get('startTime', '')

                    for disp in event.get('displayGroups', []):
                        mkt_name = disp.get('description', '')
                        for market in disp.get('markets', []):
                            for outcome in market.get('outcomes', []):
                                sel = outcome.get('description', '')
                                price = outcome.get('price', {})
                                dec = price.get('decimal')
                                if dec:
                                    _save('bovada', event_id, sport, comp,
                                          home, away, str(start), mkt_name, sel,
                                          float(dec), None, fetch_date)
                                    count += 1
        except Exception as e:
            log.debug(f'Bovada 解析: {e}')
        time.sleep(1)
    return count


def _flush_pending(fetch_date):
    global _pending_rows
    if not _pending_rows:
        return 0
    try:
        tbl = _get_table(engine, 'multi_bookie_odds')
        batch_upsert(engine, tbl, _pending_rows,
                     unique_keys=['source', 'event_id', 'market', 'selection', 'fetch_date'])
        n = len(_pending_rows)
        _pending_rows = []
        return n
    except Exception as e:
        log.warning(f'flush_pending 失败: {e}')
        _pending_rows = []
        return 0


def run(fetch_date=None, bookmakers=None):
    global _pending_rows
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')
    if not bookmakers:
        bookmakers = ['william_hill', 'draftkings', 'fanduel', 'unibet', 'bovada']

    init_tables()
    _pending_rows = []  # 清空上次残留
    log.info('=' * 60)
    log.info(f'多庄家赔率爬虫启动  [{fetch_date}]')
    log.info('=' * 60)

    total_count = 0
    runners = {
        'william_hill': fetch_william_hill,
        'draftkings':   fetch_draftkings,
        'fanduel':      fetch_fanduel,
        'unibet':       fetch_unibet,
        'bovada':       fetch_bovada,
    }
    for name, func in runners.items():
        if name not in bookmakers:
            continue
        try:
            before = len(_pending_rows)
            func(fetch_date)
            added = len(_pending_rows) - before
            if added:
                log.info(f'  [{name}]: {added} 条待写入')
            total_count += added
        except Exception as e:
            log.warning(f'  [{name}] 失败: {e}')

    written = _flush_pending(fetch_date)
    log.info(f'多庄家赔率完成: 写入 {written} 条')
    return written


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    p.add_argument('--bookmakers', nargs='+', default=None)
    args = p.parse_args()
    run(fetch_date=args.date, bookmakers=args.bookmakers)
