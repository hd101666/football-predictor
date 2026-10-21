# -*- coding: utf-8 -*-
# 31_nba_official_scraper.py — NBA官方数据源(stats.nba.com, nba_api库封装)每日增量抓取
# 【目标网站】 stats.nba.com（nba_api 官方封装库，无需API Key，公开数据接口）
# 【数据价值】 NBA常规赛/季后赛赛程、比分、球队检验数据(FG%/篮板/助攻/抢断/盖帽/失误)、节次比分
# 【覆盖范围】 仅真实NBA(常规赛+季后赛)，不含夏季联赛——夏季联赛球员构成/强度与常规赛完全不同，
#            混入会污染球队评级，NBA夏季联赛数据见 18_espn_scores_scraper.py
# 【与历史数据关系】 与 import_nba.py 一次性历史回补共用同一张 nba_matches 表，按 game_id upsert 增量更新

import sys, time, logging, argparse
from datetime import datetime, timedelta

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl
from sqlalchemy import create_engine, MetaData

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

SEASON_TYPES = [('Regular Season', 'RS'), ('Playoffs', 'PO')]

NBA_HEADERS = {
    'User-Agent':          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Referer':             'https://www.nba.com/',
    'Origin':              'https://www.nba.com',
    'Accept':              'application/json, text/plain, */*',
    'x-nba-stats-origin':  'stats',
    'x-nba-stats-token':   'true',
}


def _get_table(table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS nba_matches (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id        TEXT    UNIQUE,
            season         TEXT,
            season_type    TEXT,
            game_date      TEXT,
            home_team      TEXT,
            home_abbr      TEXT,
            away_team      TEXT,
            away_abbr      TEXT,
            home_pts       INTEGER,
            away_pts       INTEGER,
            home_q1 INTEGER, home_q2 INTEGER, home_q3 INTEGER, home_q4 INTEGER,
            away_q1 INTEGER, away_q2 INTEGER, away_q3 INTEGER, away_q4 INTEGER,
            home_fg_pct    REAL,
            home_3p_pct    REAL,
            home_ft_pct    REAL,
            away_fg_pct    REAL,
            away_3p_pct    REAL,
            away_ft_pct    REAL,
            home_reb INTEGER, home_ast INTEGER, home_stl INTEGER, home_blk INTEGER, home_tov INTEGER,
            away_reb INTEGER, away_ast INTEGER, away_stl INTEGER, away_blk INTEGER, away_tov INTEGER,
            source         TEXT DEFAULT 'nba_api',
            created_at     TEXT DEFAULT (datetime('now'))
        )
    """)


def _check_nba_accessible() -> bool:
    """快速探测 stats.nba.com 是否可访问（NBA对机房/海外IP有反爬拦截，与Bet365/Betfair同类问题）"""
    import requests as _req
    try:
        r = _req.get(
            'https://stats.nba.com/stats/leaguegamefinder',
            params={'LeagueID': '00', 'Season': '2024-25', 'SeasonType': 'Regular Season',
                     'DateFrom': '01/01/2025', 'DateTo': '01/01/2025'},
            headers=NBA_HEADERS, timeout=8,
        )
        if r.status_code == 403:
            log.warning('stats.nba.com IP 封锁（HTTP 403）— 需代理/更换出口IP，与 Bet365/Betfair 同类拦截')
            return False
        if r.status_code != 200:
            log.warning(f'stats.nba.com 探测异常 HTTP {r.status_code}')
            return False
        return True
    except Exception as e:
        log.warning(f'stats.nba.com 连接失败/超时: {e}')
        return False


def _season_label(d: datetime):
    """NBA赛季以10月为起点：10-12月属于当年起始赛季，1-9月属于上一年起始赛季"""
    start_year = d.year if d.month >= 10 else d.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}", str(start_year)


def _f(row, col, cast=float):
    if row is None:
        return None
    v = row.get(col)
    try:
        if v is None or (isinstance(v, float) and v != v):  # NaN
            return None
        return cast(v)
    except Exception:
        return None


def fetch_range(date_from: str, date_to: str, season_label: str, season_code: str) -> list:
    """date_from/date_to 格式 MM/DD/YYYY（nba_api要求），返回待写入 nba_matches 的行字典列表"""
    from nba_api.stats.endpoints import leaguegamefinder
    rows_map = {}
    for stype, stype_code in SEASON_TYPES:
        try:
            result = leaguegamefinder.LeagueGameFinder(
                league_id_nullable='00',
                season_nullable=season_label,
                season_type_nullable=stype,
                date_from_nullable=date_from,
                date_to_nullable=date_to,
                headers=NBA_HEADERS,
                timeout=20,
            )
            df = result.get_data_frames()[0]
        except Exception as e:
            log.warning(f'  LeagueGameFinder[{stype}] 失败: {e}')
            continue

        if df.empty:
            continue

        home_df = df[df['MATCHUP'].str.contains(' vs. ', na=False)]
        away_df = df[df['MATCHUP'].str.contains(' @ ', na=False)]

        for gid in home_df['GAME_ID'].unique():
            h = home_df[home_df['GAME_ID'] == gid].iloc[0]
            a_rows = away_df[away_df['GAME_ID'] == gid]
            a = a_rows.iloc[0] if len(a_rows) else None

            rows_map[gid] = {
                'game_id':      gid,
                'season':       season_code,
                'season_type':  stype_code,
                'game_date':    str(h['GAME_DATE'])[:10],
                'home_team':    h['TEAM_NAME'],
                'home_abbr':    h['TEAM_ABBREVIATION'],
                'away_team':    a['TEAM_NAME'] if a is not None else '',
                'away_abbr':    a['TEAM_ABBREVIATION'] if a is not None else '',
                'home_pts':     _f(h, 'PTS', int),
                'away_pts':     _f(a, 'PTS', int),
                'home_fg_pct':  _f(h, 'FG_PCT'),
                'home_3p_pct':  _f(h, 'FG3_PCT'),
                'home_ft_pct':  _f(h, 'FT_PCT'),
                'away_fg_pct':  _f(a, 'FG_PCT'),
                'away_3p_pct':  _f(a, 'FG3_PCT'),
                'away_ft_pct':  _f(a, 'FT_PCT'),
                'home_reb':     _f(h, 'REB', int), 'home_ast': _f(h, 'AST', int),
                'home_stl':     _f(h, 'STL', int), 'home_blk': _f(h, 'BLK', int), 'home_tov': _f(h, 'TOV', int),
                'away_reb':     _f(a, 'REB', int), 'away_ast': _f(a, 'AST', int),
                'away_stl':     _f(a, 'STL', int), 'away_blk': _f(a, 'BLK', int), 'away_tov': _f(a, 'TOV', int),
                'source':       'nba_api',
            }
        time.sleep(0.6)
    return list(rows_map.values())


def enrich_quarters(rows: list):
    """已结束比赛补充Q1-Q4节次比分（BoxScoreSummaryV2的LineScore结果集）"""
    from nba_api.stats.endpoints import boxscoresummaryv2
    for row in rows:
        if row['home_pts'] is None:
            continue
        try:
            summary = boxscoresummaryv2.BoxScoreSummaryV2(
                game_id=row['game_id'], headers=NBA_HEADERS, timeout=15
            )
            line_score = None
            for fr in summary.get_data_frames():
                if 'PTS_QTR1' in fr.columns:
                    line_score = fr
                    break
            if line_score is None:
                continue
            home_ls = line_score[line_score['TEAM_ABBREVIATION'] == row['home_abbr']]
            away_ls = line_score[line_score['TEAM_ABBREVIATION'] == row['away_abbr']]
            if len(home_ls):
                hl = home_ls.iloc[0]
                for i, q in enumerate(['q1', 'q2', 'q3', 'q4'], start=1):
                    row[f'home_{q}'] = _f(hl, f'PTS_QTR{i}', int)
            if len(away_ls):
                al = away_ls.iloc[0]
                for i, q in enumerate(['q1', 'q2', 'q3', 'q4'], start=1):
                    row[f'away_{q}'] = _f(al, f'PTS_QTR{i}', int)
        except Exception as e:
            log.debug(f'  节次比分获取失败 {row["game_id"]}: {e}')
        time.sleep(0.5)


def run(fetch_date=None, days_back=2, days_forward=1):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')

    log.info('=' * 60)
    log.info(f'NBA官方数据爬虫启动  [{fetch_date}]')
    log.info('=' * 60)

    init_tables()

    if not _check_nba_accessible():
        log.warning('NBA官方接口不可访问，本次跳过（不影响其他数据源）')
        return 0

    base_dt   = datetime.strptime(fetch_date, '%Y-%m-%d')
    range_from = base_dt - timedelta(days=days_back)
    range_to   = base_dt + timedelta(days=days_forward)
    season_label, season_code = _season_label(base_dt)

    rows = fetch_range(
        range_from.strftime('%m/%d/%Y'), range_to.strftime('%m/%d/%Y'),
        season_label, season_code,
    )

    if not rows:
        log.info(f'NBA完成: 窗口 [{range_from:%Y-%m-%d} ~ {range_to:%Y-%m-%d}] 内无场次(常规赛/季后赛均未开打时属正常)')
        return 0

    enrich_quarters(rows)

    table = _get_table('nba_matches')
    written = batch_upsert(engine, table, rows, unique_keys=['game_id'])
    log.info(f'NBA完成: 写入/更新 {written} 场 (窗口 {range_from:%Y-%m-%d} ~ {range_to:%Y-%m-%d})')
    return written


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='NBA官方数据(stats.nba.com)每日增量爬虫')
    p.add_argument('--date',          default=None, help='指定日期 YYYY-MM-DD（默认今日）')
    p.add_argument('--days-back',     type=int, default=2)
    p.add_argument('--days-forward',  type=int, default=1)
    args = p.parse_args()
    run(fetch_date=args.date, days_back=args.days_back, days_forward=args.days_forward)
