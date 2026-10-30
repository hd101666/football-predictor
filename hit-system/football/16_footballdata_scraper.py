# 16_footballdata_scraper.py — football-data.co.uk 历史数据爬虫
# 【目标网站】 https://www.football-data.co.uk
# 【数据价值】 132字段CSV，含：半场比分/角球/射门/牌/Bet365+Pinnacle多庄赔率/亚盘
# 【覆盖范围】 18个欧洲联赛，历史数据2000年至今，无需认证直接下载
# 【用途】     补充 sofascore/soccerway 缺口，提供角球/半场/多庄赔率字段

import sys, csv, io, time, logging, argparse
import requests
from datetime import datetime
from sqlalchemy import create_engine, text
import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl as _ddl_init  # unused after refactor

# Bug修复(2026-08-12)：原先只有 getLogger、**没有 basicConfig**，独立运行时
# Python日志默认只输出WARNING及以上，所有 log.info 的成功信息被静默丢弃，
# 日志里只剩重试噪音——工作正常的爬虫会看起来像全线失败（09号即因此被误判）。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
engine = create_engine(DB_ENGINE_URL)

from sqlalchemy import MetaData
from db_utils import batch_upsert, exec_ddl

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]

# 主站联赛 (mmz4281/) — 欧洲20联赛
LEAGUES = {
    'E0':  'England - Premier League',
    'E1':  'England - Championship',
    'E2':  'England - League One',
    'E3':  'England - League Two',
    'EC':  'England - Conference',
    'D1':  'Germany - Bundesliga',
    'D2':  'Germany - Bundesliga 2',
    'SP1': 'Spain - La Liga',
    'SP2': 'Spain - Segunda',
    'I1':  'Italy - Serie A',
    'I2':  'Italy - Serie B',
    'F1':  'France - Ligue 1',
    'F2':  'France - Ligue 2',
    'N1':  'Netherlands - Eredivisie',
    'B1':  'Belgium - Jupiler Pro League',
    'P1':  'Portugal - Primeira Liga',
    'SC0': 'Scotland - Premiership',
    'SC1': 'Scotland - Championship',
    'T1':  'Turkey - Super Lig',
    'G1':  'Greece - Super League',
}

# 扩展联赛 (new/) — 覆盖更多角球数据
LEAGUES_NEW = {
    'ARG': 'Argentina - Primera Division',
    'AUT': 'Austria - Bundesliga',
    'BRA': 'Brazil - Serie A',
    'CHN': 'China - Super League',
    'DNK': 'Denmark - Superliga',
    'FIN': 'Finland - Veikkausliiga',
    'IRL': 'Ireland - Premier Division',
    'JPN': 'Japan - J1 League',
    'MEX': 'Mexico - Liga MX',
    'NOR': 'Norway - Eliteserien',
    'POL': 'Poland - Ekstraklasa',
    'ROU': 'Romania - Liga 1',
    'RUS': 'Russia - Premier League',
    'SWE': 'Sweden - Allsvenskan',
    'SWZ': 'Switzerland - Super League',
    'USA': 'USA - MLS',
}

BASE     = 'https://www.football-data.co.uk/mmz4281'
BASE_NEW = 'https://www.football-data.co.uk/new'
# new/ 联赛无赛季子目录，URL 格式: BASE_NEW/{code}.csv（含全部历史赛季）
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0'}


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS fd_matches (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            season               TEXT,
            league_code          TEXT,
            league_name          TEXT,
            match_date           TEXT,
            match_time           TEXT,
            home_team            TEXT,
            away_team            TEXT,
            fthg                 INTEGER,
            ftag                 INTEGER,
            ftr                  TEXT,
            hthg                 INTEGER,
            htag                 INTEGER,
            htr                  TEXT,
            home_shots           INTEGER,
            away_shots           INTEGER,
            home_shots_target    INTEGER,
            away_shots_target    INTEGER,
            home_corners         INTEGER,
            away_corners         INTEGER,
            home_yellow          INTEGER,
            away_yellow          INTEGER,
            home_red             INTEGER,
            away_red             INTEGER,
            b365h                REAL,
            b365d                REAL,
            b365a                REAL,
            psh                  REAL,
            psd                  REAL,
            psa                  REAL,
            b365_over25          REAL,
            b365_under25         REAL,
            b365_ahh             REAL,
            b365_aha             REAL,
            ah_handicap          REAL,
            max_over25           REAL,
            max_under25          REAL,
            avg_over25           REAL,
            avg_under25          REAL,
            fetch_date           TEXT,
            UNIQUE(league_code, season, match_date, home_team, away_team)
        )
    """)


def _fi(v):
    try:
        return int(float(v)) if v and str(v).strip() else None
    except Exception:
        return None


def _ff(v):
    try:
        return float(v) if v and str(v).strip() else None
    except Exception:
        return None


def _parse_date(raw):
    raw = (raw or '').strip()
    for fmt in ('%d/%m/%y', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except Exception:
            pass
    return raw


def fetch_league(season, league_code, league_name, fetch_date, use_new_base=False):
    if use_new_base:
        url = f'{BASE_NEW}/{league_code}.csv'   # new/ 无赛季子目录
    else:
        url = f'{BASE}/{season}/{league_code}.csv'
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                return 0
            r.raise_for_status()
            break
        except Exception as e:
            if attempt == 2:
                log.warning(f'  {league_code}/{season} 请求失败: {e}')
                return 0
            time.sleep(2 ** attempt)

    content = r.content.decode('utf-8-sig', errors='replace')
    rows_to_insert = []
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        home = (row.get('HomeTeam') or '').strip()
        away = (row.get('AwayTeam') or '').strip()
        if not home or not away:
            continue
        params = {
            'season': season, 'league_code': league_code, 'league_name': league_name,
            'match_date': _parse_date(row.get('Date', '')),
            'match_time': (row.get('Time') or '').strip(),
            'home_team': home, 'away_team': away,
            'fthg': _fi(row.get('FTHG')), 'ftag': _fi(row.get('FTAG')),
            'ftr':  (row.get('FTR') or '').strip(),
            'hthg': _fi(row.get('HTHG')), 'htag': _fi(row.get('HTAG')),
            'htr':  (row.get('HTR') or '').strip(),
            'home_shots':        _fi(row.get('HS')),
            'away_shots':        _fi(row.get('AS')),
            'home_shots_target': _fi(row.get('HST')),
            'away_shots_target': _fi(row.get('AST')),
            'home_corners':      _fi(row.get('HC')),
            'away_corners':      _fi(row.get('AC')),
            'home_yellow':       _fi(row.get('HY')),
            'away_yellow':       _fi(row.get('AY')),
            'home_red':          _fi(row.get('HR')),
            'away_red':          _fi(row.get('AR')),
            'b365h': _ff(row.get('B365H')), 'b365d': _ff(row.get('B365D')),
            'b365a': _ff(row.get('B365A')),
            'psh':   _ff(row.get('PSH')),   'psd':   _ff(row.get('PSD')),
            'psa':   _ff(row.get('PSA')),
            'b365_over25':  _ff(row.get('B365>2.5')),
            'b365_under25': _ff(row.get('B365<2.5')),
            'b365_ahh':     _ff(row.get('B365AHH')),
            'b365_aha':     _ff(row.get('B365AHA')),
            'ah_handicap':  _ff(row.get('AHh')),
            'max_over25':   _ff(row.get('Max>2.5')),
            'max_under25':  _ff(row.get('Max<2.5')),
            'avg_over25':   _ff(row.get('Avg>2.5')),
            'avg_under25':  _ff(row.get('Avg<2.5')),
            'fetch_date': fetch_date,
        }
        try:
            rows_to_insert.append(params)
            count += 1
        except Exception as e:
            log.debug(f'insert error: {e}')
    # batch write
    if rows_to_insert:
        try:
            tbl = _get_table(engine, 'fd_matches')
            batch_upsert(engine, tbl, rows_to_insert, unique_keys=['season', 'league_code', 'match_date', 'home_team', 'away_team'])
        except Exception as e:
            log.warning(f'batch write failed: {e}')
    return count


def run(seasons=None, leagues=None, fetch_date=None, include_new=True):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')
    if not seasons:
        seasons = ['2526', '2425', '2324']

    init_tables()
    log.info('=' * 60)
    log.info('football-data.co.uk 爬虫启动')
    log.info(f'  赛季: {seasons}')
    log.info('=' * 60)

    total = 0
    for season in seasons:
        season_total = 0

        # 主站联赛 (欧洲20联赛)
        target_leagues = leagues if leagues else list(LEAGUES.keys())
        for code in target_leagues:
            name = LEAGUES.get(code, code)
            n = fetch_league(season, code, name, fetch_date, use_new_base=False)
            if n:
                log.info(f'  [{season}] {name}: {n} 场')
            season_total += n
            time.sleep(0.4)

        # 扩展联赛只跑一次（new/目录含全部历史，无需按赛季循环）
        if include_new and not leagues and season == seasons[0]:
            log.info(f'  [new/] 扩展联赛抓取...')
            for code, name in LEAGUES_NEW.items():
                n = fetch_league(season, code, name, fetch_date, use_new_base=True)
                if n:
                    log.info(f'  [new/] {name}: {n} 场')
                season_total += n
                time.sleep(0.4)

        log.info(f'  赛季 {season} 合计: {season_total} 场')
        total += season_total

    log.info(f'完成: 共写入 {total} 场')
    return total


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='football-data.co.uk 爬虫')
    p.add_argument('--season', nargs='+', default=None)
    p.add_argument('--league', nargs='+', default=None)
    p.add_argument('--date',   default=None)
    p.add_argument('--no-new', action='store_true', help='跳过扩展联赛(new/目录)')
    args = p.parse_args()
    run(seasons=args.season, leagues=args.league, fetch_date=args.date,
        include_new=not args.no_new)
