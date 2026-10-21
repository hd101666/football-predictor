# _elo_scraper.py — Club ELO + 国家队 ELO 爬虫
# 来源: clubelo.com (俱乐部) + eloratings.net (国家队)
# 频率: 每日一次即可（ELO 周更，数据稳定）

import csv, io, logging
from datetime import datetime
import requests
import urllib3; urllib3.disable_warnings()

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'}


def init_tables():
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS club_elo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT, country TEXT, elo_rating REAL, level INTEGER,
        fetch_date TEXT, UNIQUE(team_name, fetch_date))""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS national_team_elo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT, elo_rating REAL, rank INTEGER,
        fetch_date TEXT, UNIQUE(team_name, fetch_date))""")


def _get(url, timeout=30):
    try:
        r = requests.get(url, headers=H, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.warning(f'请求失败 {url}: {e}')
        return None


def fetch_club_elo(fetch_date):
    # clubelo.com 只提供前一天数据，用昨天日期
    from datetime import timedelta
    yesterday = (datetime.strptime(fetch_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f'http://api.clubelo.com/{yesterday}'
    csv_text = _get(url)
    if not csv_text:
        return 0
    rows = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        for r in reader:
            try:
                elo_val = r.get('Elo', '').strip()
                if not elo_val:
                    continue
                rows.append({
                    "team_name": r.get('Club','').strip(),
                    "country":   r.get('Country','').strip(),
                    "elo_rating": float(elo_val),
                    "level":     int(r['Level']) if r.get('Level','').strip() else None,
                    "fetch_date": fetch_date,
                })
            except (ValueError, TypeError):
                continue
    except Exception as e:
        log.warning(f'解析 club ELO CSV 失败: {e}')
        return 0
    with engine.begin() as conn:
        for row in rows:
            conn.execute(text("""INSERT OR REPLACE INTO club_elo
                (team_name,country,elo_rating,level,fetch_date)
                VALUES(:team_name,:country,:elo_rating,:level,:fetch_date)"""), row)
    log.info(f'  club_elo: 写入 {len(rows)} 条')
    return len(rows)


def fetch_national_elo(fetch_date):
    code_text = _get('https://www.eloratings.net/en.teams.tsv')
    world_text = _get('https://www.eloratings.net/World.tsv')
    if not code_text or not world_text:
        return 0
    code_map = {}
    for line in code_text.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 2:
            code_map[parts[0]] = parts[1]
    rows = []
    for line in world_text.strip().split('\n'):
        if not line:
            continue
        fields = line.split('\t')
        if len(fields) < 4:
            continue
        try:
            rank = int(fields[0])
            code = fields[2]
            rating = float(fields[3])
            team_name = code_map.get(code, code)
            rows.append({"team_name": team_name, "elo_rating": rating,
                         "rank": rank, "fetch_date": fetch_date})
        except (ValueError, IndexError):
            continue
    with engine.begin() as conn:
        for row in rows:
            conn.execute(text("""INSERT OR REPLACE INTO national_team_elo
                (team_name,elo_rating,rank,fetch_date)
                VALUES(:team_name,:elo_rating,:rank,:fetch_date)"""), row)
    log.info(f'  national_team_elo: 写入 {len(rows)} 条')
    return len(rows)


def run(fetch_date=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')
    init_tables()
    log.info(f'ELO 爬虫启动 [{fetch_date}]')
    c1 = fetch_club_elo(fetch_date)
    c2 = fetch_national_elo(fetch_date)
    log.info(f'ELO 完成: club={c1} 国家队={c2}')
    return c1 + c2


if __name__ == '__main__':
    run()
