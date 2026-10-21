# 19_whoscored_scraper.py — WhoScored 技术统计爬虫（camoufox Firefox 绕过Cloudflare）
# WARNING: 实验性爬虫 - WhoScored 受 Cloudflare 保护，camoufox 解析成功率不稳定
# 数据：射门/射正、控球率、传球成功率、关键传球、评分
# 覆盖：五大联赛 + 欧冠，需要 camoufox 已安装
import sys, time, logging, re, json, argparse
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

# WhoScored region/tournament IDs
LEAGUES = [
    (252, 2,   'England - Premier League'),
    (206, 4,   'Spain - La Liga'),
    (108, 5,   'Italy - Serie A'),
    (81,  3,   'Germany - Bundesliga'),
    (74,  22,  'France - Ligue 1'),
    (250, 2,   'Europe - Champions League'),
]


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS whoscored_team_stats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            season          TEXT,
            league_name     TEXT,
            team            TEXT,
            games           INTEGER,
            goals           REAL,
            shots_pg        REAL,
            shots_ot_pg     REAL,
            possession_pct  REAL,
            pass_success    REAL,
            aerials_won     REAL,
            rating          REAL,
            fetch_date      TEXT,
            UNIQUE(season, league_name, team)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS whoscored_match_stats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            season          TEXT,
            league_name     TEXT,
            match_date      TEXT,
            home_team       TEXT,
            away_team       TEXT,
            home_score      INTEGER,
            away_score      INTEGER,
            home_possession REAL,
            away_possession REAL,
            home_shots      INTEGER,
            away_shots      INTEGER,
            home_shots_ot   INTEGER,
            away_shots_ot   INTEGER,
            home_rating     REAL,
            away_rating     REAL,
            fetch_date      TEXT,
            UNIQUE(season, league_name, match_date, home_team, away_team)
        )
    """)


def _get_browser():
    from camoufox.sync_api import Camoufox
    return Camoufox(headless=True)


def fetch_team_stats(region_id, tournament_id, league_name, season_str, fetch_date):
    """从 WhoScored 球队统计摘要页提取数据"""
    url = (f'https://www.whoscored.com/Regions/{region_id}/Tournaments/{tournament_id}/'
           f'Seasons/*/Stages/*/TeamStatistics/Summary')

    try:
        from camoufox.sync_api import Camoufox
        with Camoufox(headless=True) as browser:
            page = browser.new_page()
            # Navigate to league home first
            base_url = f'https://www.whoscored.com/Regions/{region_id}/Tournaments/{tournament_id}/'
            page.goto(base_url, timeout=30000)
            time.sleep(3)

            content = page.content()
            # Extract JSON data from require.config.params
            json_matches = re.findall(
                r'require\.config\.params\[[\'"]\w+[\'"]\]\s*=\s*(\{.*?\});',
                content, re.DOTALL
            )

            teams_data = []
            for jm in json_matches:
                try:
                    # Fix JS object to JSON
                    jm_fixed = re.sub(r'(\w+):', r'"\1":', jm)
                    jm_fixed = re.sub(r'"(\w+)"\s*:', r'"\1":', jm_fixed)
                    data = json.loads(jm_fixed)
                    if 'teams' in str(data) or 'teamStats' in str(data):
                        teams_data.append(data)
                except Exception:
                    pass

            page.close()

        count = 0
        for td in teams_data:
            # Try to extract team statistics
            teams = td.get('teams', td.get('teamStats', []))
            if isinstance(teams, list):
                for team in teams:
                    if not isinstance(team, dict):
                        continue
                    name = team.get('name', team.get('teamName', ''))
                    if not name:
                        continue
                    rows_to_insert.append({
                        's': season_str, 'lg': league_name, 't': name,
                        'sh': team.get('shotsPerGame'),
                        'sot': team.get('shotsOnTargetPerGame'),
                        'pos': team.get('possession'),
                        'ps': team.get('passSuccess'),
                        'rat': team.get('rating'),
                        'fd': fetch_date,
                    })
                    count += 1
        return count

    except Exception as e:
        log.warning(f'WhoScored {league_name} 失败: {e}')
        return 0


def fetch_match_stats_html(region_id, tournament_id, league_name, season_str, fetch_date):
    """从 WhoScored 比赛列表页提取逐场统计"""
    count = 0
    try:
        from camoufox.sync_api import Camoufox
        from bs4 import BeautifulSoup

        with Camoufox(headless=True) as browser:
            page = browser.new_page()
            url = f'https://www.whoscored.com/Regions/{region_id}/Tournaments/{tournament_id}/'
            page.goto(url, timeout=30000)
            time.sleep(4)

            # Click on "Results" tab if available
            try:
                page.click('a[href*="Results"]', timeout=3000)
                time.sleep(3)
            except Exception:
                pass

            html = page.content()
            page.close()

        soup = BeautifulSoup(html, 'html.parser')

        # Find match rows
        for row in soup.find_all('tr', class_=re.compile(r'match-fixture')):
            try:
                home = row.find('td', class_='home').get_text(strip=True)
                away = row.find('td', class_='away').get_text(strip=True)
                score_el = row.find('td', class_='result')
                if not score_el:
                    continue
                score_text = score_el.get_text(strip=True)
                parts = re.split(r'[:\-–]', score_text)
                if len(parts) != 2:
                    continue
                hs, as_ = int(parts[0].strip()), int(parts[1].strip())

                date_el = row.find('td', class_='date')
                match_date = date_el.get_text(strip=True) if date_el else ''

                rows_to_insert.append({'s': season_str, 'lg': league_name, 'd': match_date,
                                               'h': home, 'a': away, 'hs': hs, 'as_': as_, 'fd': fetch_date})
                count += 1
            except Exception:
                pass

    except Exception as e:
        log.warning(f'WhoScored match stats {league_name}: {e}')

    return count


def run(fetch_date=None):
    try:
        from camoufox.sync_api import Camoufox  # noqa: F401
    except ImportError:
        log.warning("WhoScored 爬虫跳过：camoufox 未安装。安装: pip install camoufox")
        return 0

    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')

    init_tables()
    log.info('=' * 60)
    log.info(f'WhoScored 爬虫启动  [{fetch_date}]  (camoufox)')
    log.info('=' * 60)

    season_str = '2025-26'
    total = 0

    for region_id, tournament_id, league_name in LEAGUES:
        c = fetch_team_stats(region_id, tournament_id, league_name, season_str, fetch_date)
        if c:
            log.info(f'  {league_name}: {c} 支球队')
            total += c
        time.sleep(3)

    log.info(f'WhoScored 完成: {total} 条球队统计')
    return total


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    args = p.parse_args()
    run(fetch_date=args.date)
