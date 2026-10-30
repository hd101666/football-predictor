# 25_transfermarkt_scraper.py — Transfermarkt 球员身价/伤停爬虫
# 数据：球队总身价（团队实力指标）、伤停名单
# 覆盖：五大联赛
import sys, time, logging, re, argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
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

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.transfermarkt.com/',
}

# league_id → (slug, display_name)
LEAGUES = [
    ('GB1',      'premier-league',  'England - Premier League'),
    ('ES1',      'laliga',          'Spain - La Liga'),
    ('IT1',      'serie-a',         'Italy - Serie A'),
    ('L1',       '1-bundesliga',    'Germany - Bundesliga'),
    ('FR1',      'ligue-1',         'France - Ligue 1'),
    ('GB2',      'championship',    'England - Championship'),
    ('GBTHREE',  'league-one',      'England - League One'),
    ('TR1',      'super-lig',       'Turkey - Super Lig'),
    ('NL1',      'eredivisie',      'Netherlands - Eredivisie'),
    ('PO1',      'liga-nos',        'Portugal - Primeira Liga'),
]

# 模块级行缓冲
_squad_rows:  list = []
_injury_rows: list = []


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS transfermarkt_squad_values (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            season       TEXT,
            league_name  TEXT,
            team         TEXT,
            squad_size   INTEGER,
            avg_age      REAL,
            total_value  TEXT,
            total_value_eur REAL,
            fetch_date   TEXT,
            UNIQUE(season, league_name, team)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS transfermarkt_injuries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            league_name  TEXT,
            team         TEXT,
            player_name  TEXT,
            position     TEXT,
            return_date  TEXT,
            injury_type  TEXT,
            market_value TEXT,
            fetch_date   TEXT,
            UNIQUE(league_name, team, player_name, fetch_date)
        )
    """)


def _get(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=H, timeout=20, verify=False)
            time.sleep(1.5)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429):
                try:
                    from curl_cffi import requests as cffi_requests
                    sess = cffi_requests.Session(impersonate='chrome131')
                    r2 = sess.get(url, headers=H, timeout=20, verify=False)
                    if r2.status_code == 200:
                        return r2.text
                except Exception:
                    pass
            log.debug(f'HTTP {r.status_code}: {url}')
        except Exception as e:
            log.debug(f'请求失败 attempt {attempt+1}: {e}')
            time.sleep(3)
    return None


def _parse_value(val_str):
    """解析 '€45.50m' → 45500000"""
    if not val_str:
        return None
    val_str = val_str.replace('€','').replace(',','').strip()
    try:
        if 'bn' in val_str.lower():
            return float(re.sub(r'[^\d.]', '', val_str)) * 1e9
        if 'm' in val_str.lower():
            return float(re.sub(r'[^\d.]', '', val_str)) * 1e6
        if 'k' in val_str.lower() or 'th' in val_str.lower():
            return float(re.sub(r'[^\d.]', '', val_str)) * 1e3
        return float(re.sub(r'[^\d.]', '', val_str))
    except Exception:
        return None


def fetch_squad_values(league_id, slug, league_name, fetch_date):
    """获取联赛所有球队身价"""
    url = f'https://www.transfermarkt.com/{slug}/startseite/wettbewerb/{league_id}'
    html = _get(url)
    if not html:
        log.warning(f'  {league_name}: 无法获取页面')
        return 0

    soup = BeautifulSoup(html, 'html.parser')
    season_el = soup.find('select', id='saison_id')
    season_str = '2025'
    if season_el:
        sel = season_el.find('option', selected=True)
        if sel:
            season_str = sel.get_text(strip=True)

    table = soup.find('table', class_=re.compile(r'items'))
    if not table:
        log.debug(f'  {league_name}: 未找到数据表')
        return 0

    count = 0
    for row in table.find('tbody').find_all('tr'):
        try:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 4:
                continue
            team_cell = row.find('td', class_='hauptlink')
            if not team_cell:
                continue
            team = team_cell.get_text(strip=True)
            if not team:
                continue

            squad_size = None
            total_val = None
            avg_age = None

            for c in cells:
                txt = c.get_text(strip=True)
                if re.match(r'^\d+$', txt) and squad_size is None:
                    squad_size = int(txt)
                if '€' in txt and total_val is None:
                    total_val = txt
                if re.match(r'^\d+\.\d+$', txt) and avg_age is None:
                    try:
                        avg_age = float(txt)
                    except Exception:
                        pass

            _squad_rows.append({
                'season':          season_str,
                'league_name':     league_name,
                'team':            team,
                'squad_size':      squad_size,
                'avg_age':         avg_age,
                'total_value':     total_val,
                'total_value_eur': _parse_value(total_val),
                'fetch_date':      fetch_date,
            })
            count += 1
        except Exception as ex:
            log.debug(f'身价行解析异常 (league={league_name}): {ex}')
    return count


def fetch_injuries(league_id, slug, league_name, fetch_date):
    """获取当前伤停名单"""
    url = f'https://www.transfermarkt.com/{slug}/verletzte-spieler/wettbewerb/{league_id}'
    html = _get(url)
    if not html:
        return 0

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_=re.compile(r'items'))
    if not table:
        return 0

    count = 0
    for row in table.find('tbody').find_all('tr', class_=re.compile(r'odd|even')):
        try:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            player_cell = row.find('td', class_='hauptlink')
            player = player_cell.get_text(strip=True) if player_cell else ''
            team_img = row.find('img', class_=re.compile(r'tiny_wappen'))
            team = team_img.get('title', '') if team_img else ''

            return_el = row.find('td', {'data-stat': 'return'})
            return_date = return_el.get_text(strip=True) if return_el else ''
            injury_el = cells[3] if len(cells) > 3 else None
            injury = injury_el.get_text(strip=True) if injury_el else ''

            if not player:
                continue
            _injury_rows.append({
                'league_name': league_name,
                'team':        team,
                'player_name': player,
                'position':    '',
                'return_date': return_date,
                'injury_type': injury,
                'market_value': '',
                'fetch_date':  fetch_date,
            })
            count += 1
        except Exception as ex:
            log.debug(f'伤停行解析异常 (league={league_name}): {ex}')
    return count


def run(fetch_date=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')

    init_tables()
    log.info('=' * 60)
    log.info(f'Transfermarkt 爬虫启动  [{fetch_date}]')
    log.info('=' * 60)

    total = 0
    for league_id, slug, league_name in LEAGUES:
        c   = fetch_squad_values(league_id, slug, league_name, fetch_date)
        inj = fetch_injuries(league_id, slug, league_name, fetch_date)
        if c or inj:
            log.info(f'  {league_name}: {c} 队身价, {inj} 伤停')
        total += c + inj
        time.sleep(2)

    # 写库
    if _squad_rows:
        tbl = _get_table(engine, 'transfermarkt_squad_values')
        batch_upsert(engine, tbl, _squad_rows, unique_keys=['season', 'league_name', 'team'])
        log.info(f'  写入 transfermarkt_squad_values: {len(_squad_rows)} 行')
    if _injury_rows:
        tbl = _get_table(engine, 'transfermarkt_injuries')
        batch_upsert(engine, tbl, _injury_rows, unique_keys=['league_name', 'team', 'player_name', 'fetch_date'])
        log.info(f'  写入 transfermarkt_injuries: {len(_injury_rows)} 行')

    log.info(f'Transfermarkt 完成: {total} 条')
    return total


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    args = p.parse_args()
    run(fetch_date=args.date)
