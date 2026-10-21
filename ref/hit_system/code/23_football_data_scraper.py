# -*- coding: utf-8 -*-
# 23_football_data_scraper.py — football-data.co.uk 全量历史数据爬虫
# 数据：比赛结果 + 半场/全场比分 + 射门/角球/犯规/黄红牌 + 多家博彩赔率（含亚盘/大小分）
# 覆盖：22 个主流欧洲联赛 + 17 个扩展联赛；历史深度至 1993-94
# 列名与 16_footballdata_scraper.py 统一，写入同一张 fd_matches 表
import sys, os, time, logging, re, argparse, io
from datetime import datetime
import requests
import pandas as pd
from sqlalchemy import create_engine, MetaData, text

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('_fd_scraper.log', encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

# ─────────────────────────────────────────────
# 联赛定义
# ─────────────────────────────────────────────
MAIN_LEAGUES = {
    'E0':  ('England',     'Premier League',         '9394'),
    'E1':  ('England',     'Championship',           '9394'),
    'E2':  ('England',     'League One',             '9394'),
    'E3':  ('England',     'League Two',             '9394'),
    'EC':  ('England',     'National League',        '0506'),
    'D1':  ('Germany',     'Bundesliga',             '9394'),
    'D2':  ('Germany',     '2. Bundesliga',          '9394'),
    'I1':  ('Italy',       'Serie A',                '9394'),
    'I2':  ('Italy',       'Serie B',                '9394'),
    'SP1': ('Spain',       'La Liga',                '9394'),
    'SP2': ('Spain',       'La Liga 2',              '9697'),
    'F1':  ('France',      'Ligue 1',                '9394'),
    'F2':  ('France',      'Ligue 2',                '9697'),
    'N1':  ('Netherlands', 'Eredivisie',             '9394'),
    'B1':  ('Belgium',     'First Division A',       '9596'),
    'P1':  ('Portugal',    'Primeira Liga',          '9495'),
    'T1':  ('Turkey',      'Super Lig',              '9495'),
    'G1':  ('Greece',      'Super League',           '9495'),
    'SC0': ('Scotland',    'Premiership',            '9394'),
    'SC1': ('Scotland',    'Championship',           '9394'),
    'SC2': ('Scotland',    'League One',             '9899'),
    'SC3': ('Scotland',    'League Two',             '9899'),
}

EXTRA_LEAGUES = {
    'ARG': ('argentina',   'Argentina Primera Division', 2012),
    'AUS': ('australia',   'Australia A-League',         2003),
    'AUT': ('austria',     'Austria Bundesliga',         2011),
    'BRA': ('brazil',      'Brazil Serie A',             2012),
    'CHN': ('china',       'China Super League',         2010),
    'DNK': ('denmark',     'Denmark Superliga',          2011),
    'FIN': ('finland',     'Finland Veikkausliiga',      2010),
    'IRL': ('ireland',     'Ireland Premier Division',   2011),
    'JPN': ('japan',       'Japan J1 League',            2012),
    'MEX': ('mexico',      'Mexico Liga MX',             2012),
    'NOR': ('norway',      'Norway Eliteserien',         2010),
    'POL': ('poland',      'Poland Ekstraklasa',         2011),
    'ROM': ('romania',     'Romania Liga 1',             2010),
    'RUS': ('russia',      'Russia Premier League',      2010),
    'SWE': ('sweden',      'Sweden Allsvenskan',         2010),
    'SWZ': ('switzerland', 'Switzerland Super League',   2011),
    'USA': ('usa',         'USA MLS',                    2011),
}

BASE_URL = 'https://www.football-data.co.uk'
MMZPATH  = f'{BASE_URL}/mmz4281'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Referer': BASE_URL + '/',
}

# ─────────────────────────────────────────────
# 赛季代码生成
# ─────────────────────────────────────────────
def _gen_main_seasons(first_code: str) -> list:
    all_s = []
    for y in range(93, 100):
        all_s.append(f'{y:02d}{(y+1) % 100:02d}')
    for y in range(0, 26):
        all_s.append(f'{y:02d}{(y+1) % 100:02d}')
    try:
        idx = all_s.index(first_code)
    except ValueError:
        idx = 0
    return all_s[idx:]


def _gen_extra_years(first_year: int) -> list:
    return list(range(first_year, datetime.now().year + 1))


# ─────────────────────────────────────────────
# 建表 / 列升级（与 16_footballdata_scraper 共用同一张表）
# ─────────────────────────────────────────────
TABLE_DDL = """
CREATE TABLE IF NOT EXISTS fd_matches (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    season               TEXT NOT NULL,
    league_code          TEXT NOT NULL,
    league_name          TEXT,
    country              TEXT,
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
    home_fouls           INTEGER,
    away_fouls           INTEGER,
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
    bwh                  REAL,
    bwd                  REAL,
    bwa                  REAL,
    iwh                  REAL,
    iwd                  REAL,
    iwa                  REAL,
    whh                  REAL,
    whd                  REAL,
    wha                  REAL,
    vch                  REAL,
    vcd                  REAL,
    vca                  REAL,
    b365_over25          REAL,
    b365_under25         REAL,
    p_over25             REAL,
    p_under25            REAL,
    b365_ahh             REAL,
    b365_aha             REAL,
    ah_handicap          REAL,
    max_over25           REAL,
    max_under25          REAL,
    avg_over25           REAL,
    avg_under25          REAL,
    bbmxh                REAL,
    bbavh                REAL,
    bbmxd                REAL,
    bbavd                REAL,
    bbmxa                REAL,
    bbava                REAL,
    fetch_date           TEXT,
    UNIQUE(league_code, season, match_date, home_team, away_team)
)
"""

# 所有可能需要补列的新字段（旧 fd_matches 表升级用）
_UPGRADE_COLS = [
    'country TEXT', 'match_time TEXT',
    'home_fouls INTEGER', 'away_fouls INTEGER',
    'bwh REAL', 'bwd REAL', 'bwa REAL',
    'iwh REAL', 'iwd REAL', 'iwa REAL',
    'whh REAL', 'whd REAL', 'wha REAL',
    'vch REAL', 'vcd REAL', 'vca REAL',
    'p_over25 REAL', 'p_under25 REAL',
    'b365_over25 REAL', 'b365_under25 REAL',
    'b365_ahh REAL', 'b365_aha REAL', 'ah_handicap REAL',
    'max_over25 REAL', 'max_under25 REAL',
    'avg_over25 REAL', 'avg_under25 REAL',
    'bbmxh REAL', 'bbavh REAL', 'bbmxd REAL', 'bbavd REAL',
    'bbmxa REAL', 'bbava REAL',
    # 兼容 16_ 的旧列（若不存在则补）
    'home_shots INTEGER', 'away_shots INTEGER',
    'home_shots_target INTEGER', 'away_shots_target INTEGER',
    'home_corners INTEGER', 'away_corners INTEGER',
    'home_yellow INTEGER', 'away_yellow INTEGER',
    'home_red INTEGER', 'away_red INTEGER',
]


def init_table():
    exec_ddl(engine, TABLE_DDL)
    for col_def in _UPGRADE_COLS:
        try:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE fd_matches ADD COLUMN {col_def}'))
        except Exception:
            pass  # 列已存在，忽略
    log.info('fd_matches 表已就绪')


def _get_table():
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables['fd_matches']


# ─────────────────────────────────────────────
# 已有数据快照
# ─────────────────────────────────────────────
def _loaded_combos() -> set:
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text('SELECT DISTINCT league_code, season FROM fd_matches')
            ).fetchall()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


# ─────────────────────────────────────────────
# CSV 列名映射（football-data.co.uk → fd_matches 列名）
# ─────────────────────────────────────────────
COL_MAP = {
    # 基础信息
    'Div':      'league_code',
    'Date':     'match_date',
    'Time':     'match_time',
    'HomeTeam': 'home_team',
    'AwayTeam': 'away_team',
    'Home':     'home_team',
    'Away':     'away_team',
    # 比分
    'FTHG': 'fthg', 'FTHome': 'fthg',
    'FTAG': 'ftag', 'FTAway': 'ftag',
    'FTR':  'ftr',
    'HTHG': 'hthg', 'HTAG': 'htag', 'HTR': 'htr',
    # 射门（统一为 16_ 的命名）
    'HS':  'home_shots',        'AS':  'away_shots',
    'HST': 'home_shots_target', 'AST': 'away_shots_target',
    # 角球
    'HC': 'home_corners', 'AC': 'away_corners',
    # 犯规
    'HF': 'home_fouls',   'AF': 'away_fouls',
    # 黄红牌
    'HY': 'home_yellow',  'AY': 'away_yellow',
    'HR': 'home_red',     'AR': 'away_red',
    # Bet365 1X2
    'B365H': 'b365h', 'B365D': 'b365d', 'B365A': 'b365a',
    # Pinnacle
    'PSH': 'psh', 'PSD': 'psd', 'PSA': 'psa',
    'PH':  'psh', 'PD':  'psd', 'PA':  'psa',
    # Betway / BetWinner
    'BWH': 'bwh', 'BWD': 'bwd', 'BWA': 'bwa',
    # Interwetten
    'IWH': 'iwh', 'IWD': 'iwd', 'IWA': 'iwa',
    # William Hill
    'WHH': 'whh', 'WHD': 'whd', 'WHA': 'wha',
    # VC Bet
    'VCH': 'vch', 'VCD': 'vcd', 'VCA': 'vca',
    # Bet365 大小分
    'B365>2.5': 'b365_over25', 'B365<2.5': 'b365_under25',
    # Pinnacle 大小分
    'P>2.5': 'p_over25', 'P<2.5': 'p_under25',
    # Bet365 亚盘
    'B365AHH': 'b365_ahh', 'B365AHA': 'b365_aha', 'AHh': 'ah_handicap',
    # Betbrain 大小分共识
    'Max>2.5':  'max_over25',  'Max<2.5':  'max_under25',
    'Avg>2.5':  'avg_over25',  'Avg<2.5':  'avg_under25',
    'BbMx>2.5': 'max_over25',  'BbMx<2.5': 'max_under25',
    'BbAv>2.5': 'avg_over25',  'BbAv<2.5': 'avg_under25',
    # Betbrain 1X2 共识
    'BbMxH': 'bbmxh', 'BbAvH': 'bbavh',
    'BbMxD': 'bbmxd', 'BbAvD': 'bbavd',
    'BbMxA': 'bbmxa', 'BbAvA': 'bbava',
}

# 表中存在的可写列集合
DB_COLS = {
    'league_code', 'league_name', 'country', 'season',
    'match_date', 'match_time', 'home_team', 'away_team',
    'fthg', 'ftag', 'ftr', 'hthg', 'htag', 'htr',
    'home_shots', 'away_shots', 'home_shots_target', 'away_shots_target',
    'home_corners', 'away_corners', 'home_fouls', 'away_fouls',
    'home_yellow', 'away_yellow', 'home_red', 'away_red',
    'b365h', 'b365d', 'b365a',
    'psh', 'psd', 'psa',
    'bwh', 'bwd', 'bwa',
    'iwh', 'iwd', 'iwa',
    'whh', 'whd', 'wha',
    'vch', 'vcd', 'vca',
    'b365_over25', 'b365_under25', 'p_over25', 'p_under25',
    'b365_ahh', 'b365_aha', 'ah_handicap',
    'max_over25', 'max_under25', 'avg_over25', 'avg_under25',
    'bbmxh', 'bbavh', 'bbmxd', 'bbavd', 'bbmxa', 'bbava',
    'fetch_date',
}


# ─────────────────────────────────────────────
# 解析工具
# ─────────────────────────────────────────────
def _parse_date(raw) -> str | None:
    if not raw or str(raw).strip() in ('', 'nan', 'NaT', 'NaN'):
        return None
    s = str(raw).strip()
    for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s


def _safe_int(v):
    try:
        f = float(v)
        return int(f) if not pd.isna(f) else None
    except Exception:
        return None


def _safe_float(v):
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, 4)
    except Exception:
        return None


def _parse_csv(content: bytes, league_code: str, league_name: str,
               country: str, season: str, fetch_date: str) -> list:
    for enc in ('latin-1', 'utf-8', 'cp1252'):
        try:
            df = pd.read_csv(io.StringIO(content.decode(enc)),
                             dtype=str, on_bad_lines='skip')
            break
        except Exception:
            continue
    else:
        log.warning(f'  CSV 解码失败: {league_code} {season}')
        return []

    if df.empty:
        return []

    df.rename(columns={c: COL_MAP.get(c, c) for c in df.columns}, inplace=True)

    int_cols   = {'fthg', 'ftag', 'hthg', 'htag',
                  'home_shots', 'away_shots', 'home_shots_target', 'away_shots_target',
                  'home_corners', 'away_corners', 'home_fouls', 'away_fouls',
                  'home_yellow', 'away_yellow', 'home_red', 'away_red'}
    float_cols = {'b365h', 'b365d', 'b365a', 'psh', 'psd', 'psa',
                  'bwh', 'bwd', 'bwa', 'iwh', 'iwd', 'iwa',
                  'whh', 'whd', 'wha', 'vch', 'vcd', 'vca',
                  'b365_over25', 'b365_under25', 'p_over25', 'p_under25',
                  'b365_ahh', 'b365_aha', 'ah_handicap',
                  'max_over25', 'max_under25', 'avg_over25', 'avg_under25',
                  'bbmxh', 'bbavh', 'bbmxd', 'bbavd', 'bbmxa', 'bbava'}

    rows = []
    for _, row in df.iterrows():
        home = str(row.get('home_team', '')).strip()
        away = str(row.get('away_team', '')).strip()
        if not home or home == 'nan' or not away or away == 'nan':
            continue

        rec = {
            'league_code': league_code,
            'league_name': league_name,
            'country':     country,
            'season':      season,
            'match_date':  _parse_date(row.get('match_date', '')),
            'match_time':  str(row.get('match_time', '')).strip() or None,
            'home_team':   home,
            'away_team':   away,
            'ftr':  str(row.get('ftr', '')).strip() or None,
            'htr':  str(row.get('htr', '')).strip() or None,
            'fetch_date':  fetch_date,
        }
        for col in int_cols:
            rec[col] = _safe_int(row.get(col))
        for col in float_cols:
            rec[col] = _safe_float(row.get(col))

        rows.append({k: v for k, v in rec.items() if k in DB_COLS})

    return rows


# ─────────────────────────────────────────────
# 下载
# ─────────────────────────────────────────────
_session = requests.Session()
_session.headers.update(HEADERS)


def _download(url: str) -> bytes | None:
    try:
        resp = _session.get(url, timeout=20)
        if resp.status_code == 200 and len(resp.content) > 100:
            return resp.content
        return None
    except Exception as e:
        log.debug(f'  请求异常: {e} ({url})')
        return None


# ─────────────────────────────────────────────
# 主流联赛抓取
# ─────────────────────────────────────────────
def fetch_main_league(code, country, league_name, first_season,
                      loaded, fetch_date, force=False) -> int:
    seasons = _gen_main_seasons(first_season)
    tbl = _get_table()
    total = 0
    for season in seasons:
        if not force and (code, f'{season[:2]}-{season[2:]}') in loaded:
            continue
        url = f'{MMZPATH}/{season}/{code}.csv'
        content = _download(url)
        if content is None:
            continue
        season_str = f'{season[:2]}-{season[2:]}'
        rows = _parse_csv(content, code, league_name, country, season_str, fetch_date)
        if not rows:
            continue
        n = batch_upsert(engine, tbl, rows,
                         ['league_code', 'season', 'match_date', 'home_team', 'away_team'])
        log.info(f'  {code} {season_str}: {n} 场')
        total += n
        time.sleep(0.5)
    return total


# ─────────────────────────────────────────────
# 扩展联赛抓取
# ─────────────────────────────────────────────
def fetch_extra_league(code, country_path, league_name, first_year,
                       loaded, fetch_date, force=False) -> int:
    tbl = _get_table()
    total = 0
    for yr in _gen_extra_years(first_year):
        season_str = f'{yr}-{yr+1}'
        if not force and (code, season_str) in loaded:
            continue
        for url in [
            f'{BASE_URL}/{country_path}/{yr}.csv',
            f'{BASE_URL}/{country_path}/{yr}-{yr+1}.csv',
            f'{BASE_URL}/{country_path}/season{yr}-{yr+1}.csv',
        ]:
            content = _download(url)
            if content:
                break
        else:
            continue
        rows = _parse_csv(content, code, league_name, country_path.title(),
                          season_str, fetch_date)
        if not rows:
            continue
        n = batch_upsert(engine, tbl, rows,
                         ['league_code', 'season', 'match_date', 'home_team', 'away_team'])
        log.info(f'  {code} {season_str}: {n} 场')
        total += n
        time.sleep(0.5)
    return total


# ─────────────────────────────────────────────
# 公开入口（被 00_命中系统 / run_all_scrapers 调用）
# ─────────────────────────────────────────────
def run(fetch_date=None, full=False, leagues=None, seasons_back=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')

    init_table()

    loaded = set() if full else _loaded_combos()
    log.info(f'已有数据: {len(loaded)} 个 league+season 组合')

    target_main  = MAIN_LEAGUES  if not leagues else {k: v for k, v in MAIN_LEAGUES.items()  if k in {l.upper() for l in leagues}}
    target_extra = EXTRA_LEAGUES if not leagues else {k: v for k, v in EXTRA_LEAGUES.items() if k in {l.upper() for l in leagues}}

    all_main = _gen_main_seasons('9394')
    cutoff_main = all_main[-seasons_back] if seasons_back and seasons_back < len(all_main) else None
    cutoff_year = (datetime.now().year - seasons_back) if seasons_back else None

    total = 0
    log.info('=' * 60)
    log.info(f'football-data.co.uk 全量抓取 [{fetch_date}]')
    log.info(f'主流: {len(target_main)} | 扩展: {len(target_extra)} | 已有: {len(loaded)} 个赛季')
    log.info('=' * 60)

    for code, (country, name, first_s) in target_main.items():
        actual_first = first_s
        if cutoff_main:
            # 取两者中更晚的起点
            a_idx = all_main.index(actual_first) if actual_first in all_main else 0
            c_idx = all_main.index(cutoff_main)  if cutoff_main  in all_main else 0
            actual_first = all_main[max(a_idx, c_idx)]
        log.info(f'[主流] {code} — {country} {name}  (从 {actual_first})')
        n = fetch_main_league(code, country, name, actual_first, loaded, fetch_date, force=full)
        log.info(f'  小计: {n} 场')
        total += n

    for code, (country_path, name, first_y) in target_extra.items():
        actual_y = max(first_y, cutoff_year) if cutoff_year else first_y
        log.info(f'[扩展] {code} — {name}  (从 {actual_y})')
        n = fetch_extra_league(code, country_path, name, actual_y, loaded, fetch_date, force=full)
        log.info(f'  小计: {n} 场')
        total += n

    log.info('=' * 60)
    log.info(f'完成: 共写入 {total} 场')
    return total


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='football-data.co.uk 全量数据爬虫')
    p.add_argument('--date',         default=None)
    p.add_argument('--full',         action='store_true', help='强制全量重下载')
    p.add_argument('--leagues',      nargs='+')
    p.add_argument('--seasons-back', type=int, dest='seasons_back')
    args = p.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    run(fetch_date=args.date, full=args.full,
        leagues=args.leagues, seasons_back=args.seasons_back)
