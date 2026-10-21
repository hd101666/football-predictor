# 23_bball_ref_scraper.py — Basketball-Reference NBA 高级数据爬虫
# 数据：四因素(eFG%/TOV%/ORB%/FT率)、进攻/防守效率、节奏
# 覆盖：NBA 当前赛季 + 近3年
import sys, time, logging, re, argparse, random
import requests
from bs4 import BeautifulSoup
from datetime import datetime
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
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.basketball-reference.com/',
}


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS bballref_team_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            season      TEXT,
            team        TEXT,
            games       INTEGER,
            wins        INTEGER,
            losses      INTEGER,
            pace        REAL,
            ortg        REAL,
            drtg        REAL,
            nrtg        REAL,
            efg_pct     REAL,
            tov_pct     REAL,
            orb_pct     REAL,
            ft_rate     REAL,
            opp_efg_pct REAL,
            opp_tov_pct REAL,
            drb_pct     REAL,
            opp_ft_rate REAL,
            fetch_date  TEXT,
            UNIQUE(season, team)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS bballref_game_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            season      TEXT,
            game_date   TEXT,
            home_team   TEXT,
            away_team   TEXT,
            home_pts    INTEGER,
            away_pts    INTEGER,
            home_pace   REAL,
            fetch_date  TEXT,
            UNIQUE(season, game_date, home_team, away_team)
        )
    """)


def _get(url, delay=4):
    try:
        headers = {**H, 'User-Agent': random.choice(DEFAULT_USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=20, verify=False)
        time.sleep(delay)
        if r.status_code == 200:
            return r.text
        if r.status_code == 429:
            log.warning('限速429，等待60s')
            time.sleep(60)
        else:
            log.warning(f'HTTP {r.status_code}: {url[:80]}')
    except Exception as e:
        log.warning(f'请求失败: {e}')
    return None


def _parse_table(html, table_id):
    soup = BeautifulSoup(html, 'html.parser')
    # Remove comments that hide tables
    for comment in soup.find_all(string=lambda t: isinstance(t, str) and '<!--' in t):
        pass
    import re as _re
    html_clean = _re.sub(r'<!--(.*?)-->', r'\1', html, flags=_re.DOTALL)
    soup2 = BeautifulSoup(html_clean, 'html.parser')
    return soup2.find('table', id=table_id)


def fetch_advanced_team(season_year, fetch_date):
    """获取球队高级统计（效率/节奏）"""
    url = f'https://www.basketball-reference.com/leagues/NBA_{season_year}.html'
    html = _get(url)
    if not html:
        return 0

    season_str = f'{season_year-1}-{str(season_year)[2:]}'
    table = _parse_table(html, 'advanced-team')
    if not table:
        table = _parse_table(html, 'misc_stats')
    if not table:
        log.warning(f'找不到高级统计表: NBA {season_year}')
        return 0

    count = 0
    tbody = table.find('tbody')
    if not tbody:
        return 0

    for row in tbody.find_all('tr'):
        if 'thead' in row.get('class', []) or 'partial_table' in row.get('class', []):
            continue
        try:
            def _td(stat):
                c = row.find('td', {'data-stat': stat})
                if not c:
                    return None
                txt = c.get_text(strip=True)
                try:
                    return float(txt) if txt else None
                except ValueError:
                    return None

            def _th(stat):
                c = row.find(['td','th'], {'data-stat': stat})
                return c.get_text(strip=True) if c else ''

            team = _th('team_name') or _th('team')
            if not team or team == 'League Average':
                continue

            pace  = _td('pace')
            ortg  = _td('off_rtg')
            drtg  = _td('def_rtg')
            nrtg  = (ortg - drtg) if ortg and drtg else None
            efg   = _td('efg_pct')
            tov   = _td('tov_pct')
            orb   = _td('orb_pct')
            ftr   = _td('ft_rate')
            opp_efg = _td('opp_efg_pct')
            opp_tov = _td('opp_tov_pct')
            opp_ftr = _td('opp_ft_rate')

            rows_to_insert.append({'s': season_str, 't': team, 'pace': pace,
                                       'ortg': ortg, 'drtg': drtg, 'nrtg': nrtg,
                                       'efg': efg, 'tov': tov, 'orb': orb, 'ftr': ftr,
                                       'oefg': opp_efg, 'otov': opp_tov, 'oftr': opp_ftr,
                                       'fd': fetch_date})
            count += 1
        except Exception as ex:
            log.debug(f'行解析: {ex}')
    return count


def fetch_four_factors(season_year, fetch_date):
    """获取四因素数据"""
    url = f'https://www.basketball-reference.com/leagues/NBA_{season_year}.html'
    html = _get(url, delay=4)
    if not html:
        return 0

    season_str = f'{season_year-1}-{str(season_year)[2:]}'
    table = _parse_table(html, 'team-stats-per_game') or _parse_table(html, 'four_factors')
    if not table:
        return 0

    count = 0
    tbody = table.find('tbody')
    if not tbody:
        return 0

    for row in tbody.find_all('tr'):
        if 'thead' in row.get('class', []):
            continue
        try:
            def _td(stat):
                c = row.find('td', {'data-stat': stat})
                if not c:
                    return None
                txt = c.get_text(strip=True)
                try:
                    return float(txt) if txt else None
                except ValueError:
                    return None

            team_c = row.find(['td','th'], {'data-stat': 'team_name'}) or row.find(['td','th'], {'data-stat': 'team'})
            if not team_c:
                continue
            team = team_c.get_text(strip=True)
            if not team:
                continue

            efg  = _td('efg_pct')
            tov  = _td('tov_pct')
            orb  = _td('orb_pct')
            ftr  = _td('ft_rate')

            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE bballref_team_stats
                    SET efg_pct=:efg, tov_pct=:tov, orb_pct=:orb, ft_rate=:ftr, fetch_date=:fd
                    WHERE season=:s AND team=:t
                """), {'s': season_str, 't': team, 'efg': efg,
                       'tov': tov, 'orb': orb, 'ftr': ftr, 'fd': fetch_date})
            count += 1
        except Exception as ex:
            log.debug(f'四因素行解析异常: {ex}')
    return count


def run(fetch_date=None, seasons=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')
    if not seasons:
        seasons = [2026, 2025]

    init_tables()
    log.info('=' * 60)
    log.info(f'Basketball-Reference 爬虫启动  [{fetch_date}]')
    log.info('=' * 60)

    total = 0
    for yr in seasons:
        c = fetch_advanced_team(yr, fetch_date)
        if c:
            log.info(f'  [NBA {yr}] 高级统计: {c} 队')
            total += c
        fetch_four_factors(yr, fetch_date)

    log.info(f'Basketball-Reference 完成: {total} 条球队统计')
    return total


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    p.add_argument('--seasons', nargs='+', type=int, default=None)
    args = p.parse_args()
    run(fetch_date=args.date, seasons=args.seasons)
