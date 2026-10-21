# 17_understat_scraper.py — Understat xG 预期进球数据爬虫
# 【目标网站】 https://understat.com
# 【数据价值】 xG(预期进球)/xGA(预期失球) — 大幅提升足球预测准确率
# 【覆盖范围】 EPL / La_Liga / Bundesliga / Serie_A / Ligue_1 / RFPL，2014年至今
# 【接入方式】 直接调用 /main/getLeagueData/{league}/{year} JSON API

import sys, re, json, time, logging, argparse
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime
from sqlalchemy import create_engine, text
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

LEAGUES = ['EPL', 'La_Liga', 'Bundesliga', 'Serie_A', 'Ligue_1', 'RFPL']
BASE    = 'https://understat.com/main/getLeagueData'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
           'Accept-Language': 'en-US,en;q=0.9',
           'X-Requested-With': 'XMLHttpRequest',
           'Referer': 'https://understat.com/'}


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS understat_matches (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            us_match_id    TEXT    UNIQUE,
            league         TEXT,
            season         INTEGER,
            home_team      TEXT,
            away_team      TEXT,
            match_datetime TEXT,
            home_goals     INTEGER,
            away_goals     INTEGER,
            home_xg        REAL,
            away_xg        REAL,
            home_xga       REAL,
            away_xga       REAL,
            is_result      INTEGER,
            fetch_date     TEXT
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS understat_team_stats (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            league       TEXT,
            season       INTEGER,
            team_name    TEXT,
            matches      INTEGER,
            wins         INTEGER,
            draws        INTEGER,
            losses       INTEGER,
            scored       INTEGER,
            missed       INTEGER,
            xg           REAL,
            xga          REAL,
            npxg         REAL,
            npxga        REAL,
            ppda         REAL,
            deep         REAL,
            pts          INTEGER,
            fetch_date   TEXT,
            UNIQUE(league, season, team_name)
        )
    """)


def _decode_js_json(raw_js):
    """解析 Understat 页面嵌入的 JSON.parse('...') 字符串"""
    try:
        # 先 unicode_escape 解码，再 JSON parse
        decoded = raw_js.encode('utf-8').decode('unicode_escape')
        return json.loads(decoded)
    except Exception:
        pass
    try:
        return json.loads(raw_js)
    except Exception:
        return None


def _fi(v):
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def _ff(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def fetch_league(league, year, fetch_date):
    url = f'{BASE}/{league}/{year}'
    data = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            if attempt == 2:
                log.warning(f'  {league}/{year} 请求失败: {e}')
                return 0, 0
            time.sleep(3 ** attempt)

    if not data:
        return 0, 0

    match_count = 0
    team_count  = 0

    # ── 比赛数据 (dates) ─────────────────────────────────────
    match_rows = []
    for match in data.get('dates', []):
        try:
            h     = match.get('h', {})
            a     = match.get('a', {})
            goals = match.get('goals', {})
            xg    = match.get('xG', {})
            mid   = str(match.get('id', ''))
            home  = h.get('title', '')
            if not mid or not home:
                continue
            hxg = _ff(xg.get('h'))
            axg = _ff(xg.get('a'))
            match_rows.append({
                'us_match_id':    mid,
                'league':         league,
                'season':         int(year),
                'home_team':      home,
                'away_team':      a.get('title', ''),
                'match_datetime': match.get('datetime', ''),
                'home_goals':     _fi(goals.get('h')),
                'away_goals':     _fi(goals.get('a')),
                'home_xg':        hxg,
                'away_xg':        axg,
                'home_xga':       axg,   # xGA(home) = 对手 xG
                'away_xga':       hxg,
                'is_result':      1 if match.get('isResult') else 0,
                'fetch_date':     fetch_date,
            })
            match_count += 1
        except Exception as e:
            log.debug(f'match parse: {e}')

    if match_rows:
        tbl = _get_table(engine, 'understat_matches')
        batch_upsert(engine, tbl, match_rows, ['us_match_id'])

    # ── 球队数据 (teams) ─────────────────────────────────────
    team_rows = []
    teams_raw = data.get('teams', {})
    if isinstance(teams_raw, dict):
        for team_id, team_data in teams_raw.items():
            try:
                title = team_data.get('title', '')
                hist  = team_data.get('history', [])
                if not hist:
                    continue
                wins = draws = losses = scored = missed = 0
                xg_sum = xga_sum = npxg_sum = npxga_sum = 0.0
                ppda_sum = deep_sum = pts = n_matches = 0
                for g in hist:
                    n_matches += 1
                    pts       += _fi(g.get('pts')) or 0
                    scored    += _fi(g.get('scored')) or 0
                    missed    += _fi(g.get('missed')) or 0
                    xg_sum    += _ff(g.get('xG'))    or 0
                    xga_sum   += _ff(g.get('xGA'))   or 0
                    npxg_sum  += _ff(g.get('npxG'))  or 0
                    npxga_sum += _ff(g.get('npxGA')) or 0
                    ppda_sum  += _ff(g.get('ppda', {}).get('att', 0) or 0)
                    deep_sum  += _fi(g.get('deep')) or 0
                    r_val = _fi(g.get('result') or g.get('pts'))
                    if   r_val == 3: wins  += 1
                    elif r_val == 1: draws += 1
                    elif r_val == 0: losses += 1
                team_rows.append({
                    'league':    league,
                    'season':    int(year),
                    'team_name': title,
                    'matches':   n_matches,
                    'wins':      wins,
                    'draws':     draws,
                    'losses':    losses,
                    'scored':    scored,
                    'missed':    missed,
                    'xg':        round(xg_sum, 2),
                    'xga':       round(xga_sum, 2),
                    'npxg':      round(npxg_sum, 2),
                    'npxga':     round(npxga_sum, 2),
                    'ppda':      round(ppda_sum / max(n_matches, 1), 2),
                    'deep':      deep_sum,
                    'pts':       pts,
                    'fetch_date': fetch_date,
                })
                team_count += 1
            except Exception as e:
                log.debug(f'team parse: {e}')

    if team_rows:
        tbl = _get_table(engine, 'understat_team_stats')
        batch_upsert(engine, tbl, team_rows, ['league', 'season', 'team_name'])

    return match_count, team_count


def _default_years():
    """最近3个赛季（含当前/最近完结赛季）。understat 的 season 用赛季起始年份标注
    （如 season=2025 代表 2025-2026 赛季）。欧洲五大联赛通常8月开新赛季，
    8月前最新可用的是上一年8月开始的那个赛季。
    之前这里硬编码 [2024,2023,2022]，导致 understat_matches 一直卡在
    2025-05 就不再更新（少了整个2025-2026赛季），2026-07-12 修复。"""
    now = datetime.now()
    current = now.year if now.month >= 8 else now.year - 1
    return [current, current - 1, current - 2]


def run(leagues=None, years=None, fetch_date=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')
    if not leagues:
        leagues = LEAGUES
    if not years:
        years = _default_years()

    init_tables()
    log.info('=' * 60)
    log.info(f'Understat xG 爬虫启动  联赛: {len(leagues)}  赛季: {years}')
    log.info('=' * 60)

    total_m = total_t = 0
    for league in leagues:
        for year in years:
            mc, tc = fetch_league(league, year, fetch_date)
            log.info(f'  {league}/{year}: {mc} 场比赛, {tc} 支球队')
            total_m += mc
            total_t += tc
            time.sleep(1.2)

    log.info(f'完成: 比赛 {total_m} 场, 球队统计 {total_t} 条')
    return total_m


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Understat xG 爬虫')
    p.add_argument('--league', nargs='+', default=None)
    p.add_argument('--year',   type=int, nargs='+', default=None)
    p.add_argument('--date',   default=None)
    args = p.parse_args()
    run(leagues=args.league, years=args.year, fetch_date=args.date)
