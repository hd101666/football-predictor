# 24_betfair_scraper.py — Betfair 交易所赔率爬虫
# WARNING: 实验性爬虫 - Betfair Exchange 是重度 JS 渲染 SPA，当前方案可能返回 0 条数据
# 数据：交易所真实概率（最锐利市场信号，优于Pinnacle）
# 方法：直接请求Betfair公开JSON端点，无需API Key
import sys, time, logging, re, json, argparse
import requests
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
import urllib3; urllib3.disable_warnings()

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl
from http_utils import DEFAULT_USER_AGENTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

from sqlalchemy import MetaData

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]
engine = create_engine(DB_ENGINE_URL)

H = {
    'User-Agent': DEFAULT_USER_AGENTS[0],
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Referer': 'https://www.betfair.com/exchange/plus/',
    'X-Requested-With': 'XMLHttpRequest',
}

# Betfair 事件类型
EVENT_TYPES = {
    'soccer':     1,
    'basketball': 7522,
}


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS betfair_exchange_odds (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id       TEXT,
            market_id      TEXT,
            event_name     TEXT,
            competition    TEXT,
            match_date     TEXT,
            home_team      TEXT,
            away_team      TEXT,
            market_type    TEXT,
            selection      TEXT,
            back_price     REAL,
            lay_price      REAL,
            back_size      REAL,
            implied_prob   REAL,
            fetch_date     TEXT,
            UNIQUE(market_id, selection, fetch_date)
        )
    """)


def _get_json(url, params=None):
    for attempt in range(3):
        try:
            headers = {**H, 'User-Agent': DEFAULT_USER_AGENTS[0]}
            r = requests.get(url, headers=headers, params=params, timeout=15, verify=False)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.debug(f'请求失败 (attempt {attempt+1}): {e}')
            time.sleep(2 ** attempt)
    return None


def _extract_json_arrays(html, key='markets'):
    """从HTML中提取嵌入的JSON数组（使用括号平衡匹配，避免正则陷阱）"""
    results = []
    pattern = f'"{key}"\\s*:\\s*\\['
    for m in re.finditer(pattern, html):
        start = m.end() - 1  # 指向 '['
        depth = 0
        i = start
        in_string = False
        escape_next = False
        while i < len(html):
            ch = html[i]
            if escape_next:
                escape_next = False
                i += 1
                continue
            if ch == '\\' and in_string:
                escape_next = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                i += 1
                continue
            if in_string:
                i += 1
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    try:
                        arr = json.loads(html[start:i+1])
                        if isinstance(arr, list):
                            results.append(arr)
                    except json.JSONDecodeError as ex:
                        log.debug(f'JSON解析失败 (pos {start}-{i}): {ex}')
                    break
            i += 1
    return results


def _check_betfair_accessible() -> bool:
    """快速探测 Betfair 是否可访问（非 IP 封锁）"""
    try:
        import requests as _req
        r = _req.get('https://www.betfair.com/', headers=H, timeout=8, verify=False)
        if r.status_code == 403:
            log.warning('Betfair IP 封锁（HTTP 403）— 需要注册官方 Exchange API Key: https://developer.betfair.com')
            return False
        return True
    except Exception as e:
        log.warning(f'Betfair 连接失败: {e}')
        return False


def fetch_via_exchange_api(fetch_date):
    """通过 Betfair Exchange 官方 API 获取赔率（需配置 BETFAIR_API_KEY）"""
    import config as _cfg
    api_key = getattr(_cfg, 'BETFAIR_API_KEY', None)
    if not api_key:
        log.info('Betfair Exchange API Key 未配置，跳过（config.py 中设置 BETFAIR_API_KEY）')
        return 0

    import requests as _req
    endpoint = 'https://api.betfair.com/exchange/betting/json-rpc/v1'
    headers = {**H, 'X-Application': api_key, 'X-Authentication': api_key,
               'Content-Type': 'application/json'}
    payload = [{"jsonrpc":"2.0","method":"SportsAPING/v1.0/listMarketCatalogue",
                "params":{"filter":{"eventTypeIds":["1"],
                "marketTypeCodes":["MATCH_ODDS", "CORRECT_SCORE"],
                "marketStartTime":{"from": fetch_date + "T00:00:00Z",
                                   "to":   fetch_date + "T23:59:59Z"}},
                "maxResults":"200","marketProjection":["COMPETITION","EVENT","RUNNER_DESCRIPTION","MARKET_START_TIME"]},
                "id":1}]
    try:
        r = _req.post(endpoint, json=payload, headers=headers, timeout=15, verify=False)
        if r.status_code != 200:
            log.warning(f'Betfair API 响应 HTTP {r.status_code}')
            return 0
        data = r.json()
        markets = data[0].get('result', []) if isinstance(data, list) else []
        log.info(f'Betfair API: {len(markets)} 场市场')
        cs_markets = [m for m in markets if m.get('marketName', '').lower().startswith('correct score')
                      or m.get('description', {}).get('marketType') == 'CORRECT_SCORE']
        if not cs_markets:
            return len(markets)

        # 逐个 CORRECT_SCORE 市场取实时报价（listMarketBook），写入 betfair_exchange_odds
        # listMarketBook 单次请求最多 50 个 marketId，超出的静默丢弃，这里记一下丢了多少
        if len(cs_markets) > 50:
            log.warning(f'Betfair CORRECT_SCORE 市场数 {len(cs_markets)} 超过单次请求上限50，'
                        f'丢弃 {len(cs_markets) - 50} 个市场')
        rows = []
        book_payload = [{"jsonrpc":"2.0","method":"SportsAPING/v1.0/listMarketBook",
                          "params":{"marketIds": [m['marketId'] for m in cs_markets[:50]],
                                    "priceProjection": {"priceData": ["EX_BEST_OFFERS"]}},
                          "id":1}]
        rb = _req.post(endpoint, json=book_payload, headers=headers, timeout=15, verify=False)
        books = {}
        if rb.status_code == 200:
            bd = rb.json()
            for b in (bd[0].get('result', []) if isinstance(bd, list) else []):
                books[b['marketId']] = b

        for mkt in cs_markets:
            book = books.get(mkt['marketId'])
            if not book:
                continue
            runner_names = {r['selectionId']: r.get('runnerName', '')
                            for r in mkt.get('runners', [])}
            event = mkt.get('event', {})
            for runner in book.get('runners', []):
                ex = runner.get('ex', {})
                backs = ex.get('availableToBack', [])
                if not backs:
                    continue
                back_price = backs[0].get('price')
                if not back_price:
                    continue
                event_name = event.get('name', '')
                parts = event_name.split(' v ') if ' v ' in event_name else event_name.split(' vs ')
                rows.append({
                    'event_id':     mkt.get('event', {}).get('id', ''),
                    'market_id':    mkt['marketId'],
                    'event_name':   event_name,
                    'competition':  mkt.get('competition', {}).get('name', ''),
                    'match_date':   fetch_date,
                    'home_team':    parts[0].strip() if len(parts) >= 2 else event_name,
                    'away_team':    parts[1].strip() if len(parts) >= 2 else '',
                    'market_type':  'CORRECT_SCORE',
                    'selection':    runner_names.get(runner.get('selectionId'), ''),
                    'back_price':   float(back_price),
                    'lay_price':    None,
                    'back_size':    None,
                    'implied_prob': round(1.0 / float(back_price), 4),
                    'fetch_date':   fetch_date,
                })
        if rows:
            tbl = _get_table(engine, 'betfair_exchange_odds')
            batch_upsert(engine, tbl, rows, unique_keys=['market_id', 'selection', 'fetch_date'])
            log.info(f'Betfair CORRECT_SCORE: {len(rows)} 条写入')
        return len(markets)
    except Exception as e:
        log.warning(f'Betfair API 请求失败: {e}')
    return 0


def fetch_via_public_endpoint(fetch_date):
    """通过 Betfair 公开页面 API 获取足球赔率"""
    count = 0
    rows_to_insert = []

    if not _check_betfair_accessible():
        return 0

    try:
        from curl_cffi import requests as cffi_requests
        sess = cffi_requests.Session(impersonate='chrome131')

        r = sess.get(
            'https://www.betfair.com/exchange/plus/football/',
            headers=H, timeout=20, verify=False
        )
        html = r.text

        # 使用括号平衡匹配提取嵌入的市场数据（替代脆弱的正则）
        markets_arrays = _extract_json_arrays(html, key='markets')
        # 也尝试从 "event" 数据中提取
        events_arrays = _extract_json_arrays(html, key='events')
        all_blocks = markets_arrays + events_arrays

        if not all_blocks:
            log.warning('Betfair 页面未找到嵌入的JSON市场数据（可能需要JS渲染）')
            return 0

        log.info(f'  Betfair: 找到 {len(all_blocks)} 个JSON数据块')

        for block in all_blocks[:5]:
            for mkt in block[:80]:
                if not isinstance(mkt, dict):
                    continue
                market_id = mkt.get('id', mkt.get('marketId', ''))
                event_name = mkt.get('eventName', mkt.get('event', {}).get('name', ''))
                runners = mkt.get('runners', [])

                for runner in runners:
                    if not isinstance(runner, dict):
                        continue
                    selection = runner.get('runnerName', runner.get('name', ''))
                    ex = runner.get('ex', {})
                    back_prices = ex.get('availableToBack', [])
                    lay_prices = ex.get('availableToLay', [])

                    back_p = back_prices[0].get('price') if back_prices else None
                    lay_p = lay_prices[0].get('price') if lay_prices else None
                    back_s = back_prices[0].get('size') if back_prices else None

                    if not back_p:
                        continue

                    implied = round(1.0 / float(back_p), 4) if back_p else None

                    try:
                        parts = event_name.split(' v ') if ' v ' in event_name else event_name.split(' vs ')
                        rows_to_insert.append({
                            'event_id':    market_id,
                            'market_id':   market_id,
                            'event_name':  event_name,
                            'competition': '',
                            'match_date':  fetch_date,
                            'home_team':   parts[0].strip() if len(parts) >= 2 else event_name,
                            'away_team':   parts[1].strip() if len(parts) >= 2 else '',
                            'market_type': mkt.get('marketType', '1X2'),
                            'selection':   selection,
                            'back_price':  float(back_p) if back_p else None,
                            'lay_price':   float(lay_p)  if lay_p  else None,
                            'back_size':   float(back_s) if back_s else None,
                            'implied_prob': implied,
                            'fetch_date':  fetch_date,
                        })
                        count += 1
                    except Exception as ex:
                        log.warning(f'Betfair 行构建失败 (market={market_id}, sel={selection}): {ex}')

    except Exception as e:
        log.warning(f'Betfair 获取失败: {e}')

    # 写库
    if rows_to_insert:
        try:
            tbl = _get_table(engine, 'betfair_exchange_odds')
            batch_upsert(engine, tbl, rows_to_insert,
                         unique_keys=['market_id', 'selection', 'fetch_date'])
        except Exception as e:
            log.warning(f'Betfair 写库失败: {e}')

    return count


def fetch_betfair_via_scraping(fetch_date):
    """通过网页抓取获取Betfair赔率（备用方案 — 提取嵌入的价格数据）"""
    count = 0
    sport_urls = [
        ('football', 'https://www.betfair.com/exchange/plus/football/'),
        ('basketball', 'https://www.betfair.com/exchange/plus/basketball/'),
    ]

    try:
        from curl_cffi import requests as cffi_requests
        sess = cffi_requests.Session(impersonate='chrome131')

        for sport, url in sport_urls:
            try:
                r = sess.get(url, headers=H, timeout=20, verify=False)
                if r.status_code != 200:
                    log.debug(f'  Betfair {sport}: HTTP {r.status_code}')
                    continue

                html = r.text
                # 尝试用括号平衡匹配提取市场数据
                arrays = _extract_json_arrays(html, key='markets')
                if not arrays:
                    arrays = _extract_json_arrays(html, key='priceData')
                if arrays:
                    log.info(f'  Betfair {sport}: 找到 {len(arrays)} 个数据块')
                else:
                    log.debug(f'  Betfair {sport}: 未找到嵌入JSON数据')
            except Exception as ex:
                log.warning(f'Betfair {sport} 抓取失败: {ex}')
            time.sleep(2)

    except ImportError:
        log.warning('Betfair 备用抓取需要 curl_cffi 库')
    except Exception as e:
        log.warning(f'Betfair 抓取异常: {e}')

    if count == 0:
        log.info('  Betfair 备用抓取: 未能提取结构化数据（页面可能需要JS渲染）')
    return count


def run(fetch_date=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')

    init_tables()
    log.info('=' * 60)
    log.info(f'Betfair 交易所赔率爬虫启动  [{fetch_date}]')
    log.info('=' * 60)

    # 优先尝试官方 API（需配置 BETFAIR_API_KEY）
    c_api = fetch_via_exchange_api(fetch_date)
    if c_api:
        log.info(f'Betfair 完成（官方API）: {c_api} 条')
        return c_api

    # 公开端点（需 IP 可访问 betfair.com）
    c1 = fetch_via_public_endpoint(fetch_date)
    if c1:
        log.info(f'  交易所赔率: {c1} 条')
    else:
        c2 = fetch_betfair_via_scraping(fetch_date)
        log.info(f'  备用抓取: {c2} 条')

    log.info('Betfair 完成')
    return c1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    args = p.parse_args()
    run(fetch_date=args.date)
