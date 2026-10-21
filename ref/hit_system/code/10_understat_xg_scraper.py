# -*- coding: utf-8 -*-
# 10_understat_xg_scraper.py — Understat xG 数据抓取（6大欧洲联赛）
# 覆盖: EPL / La Liga / Bundesliga / Serie A / Ligue 1 / RFPL
# 表: understat_xg_matches (场次级) + understat_xg_teams (队伍赛季汇总)

import sys
import logging
import argparse
from datetime import datetime
from sqlalchemy import create_engine, MetaData

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl, batch_upsert
from http_utils import StealthSession, random_sleep

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

BASE_URL = "https://understat.com"

# Understat URL slug → 内部联赛标识
UNDERSTAT_LEAGUES = {
    "EPL":        "premier_league",
    "La_liga":    "laliga",
    "Bundesliga": "bundesliga",
    "Serie_A":    "serie_a",
    "Ligue_1":    "ligue_1",
    "RFPL":       "rfpl",
}

# Understat 使用 AJAX 接口加载数据，需带 XHR 请求头
_session = StealthSession(base_url=BASE_URL, headers={
    "Referer":           "https://understat.com/",
    "Accept":            "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":   "en-US,en;q=0.9",
    "X-Requested-With":  "XMLHttpRequest",
})


def _current_season_year() -> int:
    """返回当前赛季起始年份：7月前取上一年，7月起取当前年。"""
    now = datetime.now()
    return now.year if now.month >= 7 else now.year - 1


def init_tables():
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS understat_xg_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id    TEXT UNIQUE,
        league_slug TEXT,
        season      INTEGER,
        home_team   TEXT,
        away_team   TEXT,
        home_goals  INTEGER,
        away_goals  INTEGER,
        home_xg     REAL,
        away_xg     REAL,
        match_date  TEXT,
        is_result   INTEGER DEFAULT 1,
        fetch_date  TEXT
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS understat_xg_teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league_slug    TEXT,
        season         INTEGER,
        team_name      TEXT,
        matches_played INTEGER,
        xg_off         REAL,
        xg_def         REAL,
        npxg_off       REAL,
        npxg_def       REAL,
        update_time    TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(league_slug, season, team_name)
    )""")
    log.info("✅ Understat 数据表初始化完成")



def fetch_league(league_slug: str, season_year: int, fetch_date: str):
    """抓取单个联赛的 teams + dates，写入数据库。"""
    url_slug = next((k for k, v in UNDERSTAT_LEAGUES.items() if v == league_slug), None)
    if not url_slug:
        log.error(f"未知联赛标识: {league_slug}")
        return

    # 先访问页面获取 Cookie（热身），再请求 AJAX 接口
    page_url = f"{BASE_URL}/league/{url_slug}/{season_year}"
    api_url  = f"{BASE_URL}/getLeagueData/{url_slug}/{season_year}"
    log.info(f"抓取 {url_slug} {season_year}赛季")

    # 热身：访问联赛页面
    _session.warm_up(f"/league/{url_slug}/{season_year}")

    data = _session.get_json(api_url, retries=4)
    if not data:
        log.warning(f"  API 返回空: {api_url}")
        return

    teams_data = data.get("teams", {})   # dict: team_id → {id, title, history}
    dates_data  = data.get("dates", [])  # list of match dicts

    log.info(f"  teams={len(teams_data)} 支, dates={len(dates_data)} 场")

    # ── 1. 场次级 xG ──────────────────────────────────────────
    if dates_data:
        _save_matches(dates_data, league_slug, season_year, fetch_date)

    # ── 2. 队伍赛季汇总 xG ────────────────────────────────────
    if teams_data:
        _save_teams(teams_data, league_slug, season_year, fetch_date)


def _save_matches(dates_data: list, league_slug: str, season: int, fetch_date: str):
    """dates 是 list of match dicts，每条含 id/h/a/goals/xG/datetime/isResult。"""
    rows = []
    for m in dates_data:
        try:
            h_xg = float(m.get("xG", {}).get("h", 0) or 0)
            a_xg = float(m.get("xG", {}).get("a", 0) or 0)
            h_g  = int(m.get("goals", {}).get("h", 0) or 0)
            a_g  = int(m.get("goals", {}).get("a", 0) or 0)
            rows.append({
                "match_id":    str(m["id"]),
                "league_slug": league_slug,
                "season":      season,
                "home_team":   m.get("h", {}).get("title", ""),
                "away_team":   m.get("a", {}).get("title", ""),
                "home_goals":  h_g,
                "away_goals":  a_g,
                "home_xg":     h_xg,
                "away_xg":     a_xg,
                "match_date":  m.get("datetime", ""),
                "is_result":   1 if m.get("isResult") else 0,
                "fetch_date":  fetch_date,
            })
        except Exception as e:
            log.debug(f"解析场次异常: {e}")

    if not rows:
        return
    md = MetaData()
    md.reflect(bind=engine)
    tbl = md.tables["understat_xg_matches"]
    batch_upsert(engine, tbl, rows, unique_keys=["match_id"])
    log.info(f"  ✅ understat_xg_matches 写入 {len(rows)} 条 ({league_slug} {season})")


def _save_teams(teams_data: dict, league_slug: str, season: int, fetch_date: str):
    """teams_data: {team_id: {id, title, history}}，从 history 计算场均 xG。"""
    rows = []
    for _tid, tdata in teams_data.items():
        team_name = tdata.get("title", "")
        history   = tdata.get("history", [])
        if not team_name or not history:
            continue
        try:
            n = len(history)
            xg_off   = sum(float(h.get("xG",    0) or 0) for h in history) / n
            xg_def   = sum(float(h.get("xGA",   0) or 0) for h in history) / n
            npxg_off  = sum(float(h.get("npxG",  0) or 0) for h in history) / n
            npxg_def  = sum(float(h.get("npxGA", 0) or 0) for h in history) / n
            rows.append({
                "league_slug":    league_slug,
                "season":         season,
                "team_name":      team_name,
                "matches_played": n,
                "xg_off":         round(xg_off,   4),
                "xg_def":         round(xg_def,   4),
                "npxg_off":       round(npxg_off,  4),
                "npxg_def":       round(npxg_def,  4),
                "update_time":    fetch_date,
            })
        except Exception as e:
            log.debug(f"汇总 {team_name} 异常: {e}")

    if not rows:
        return
    md = MetaData()
    md.reflect(bind=engine)
    tbl = md.tables["understat_xg_teams"]
    batch_upsert(engine, tbl, rows, unique_keys=["league_slug", "season", "team_name"])
    log.info(f"  ✅ understat_xg_teams 写入 {len(rows)} 支球队 ({league_slug} {season})")


def run(leagues: list = None, season_year: int = None):
    init_tables()
    fetch_date  = datetime.now().strftime("%Y-%m-%d")
    season_year = season_year or _current_season_year()
    target_slugs = leagues or list(UNDERSTAT_LEAGUES.values())

    log.info(f"=== Understat xG 抓取 | 赛季={season_year} | 联赛={target_slugs} ===")

    for slug in target_slugs:
        fetch_league(slug, season_year, fetch_date)
        random_sleep(base=3.0, sigma=1.0)

    log.info("=== Understat xG 抓取完成 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=None, help="赛季起始年份，如 2025")
    parser.add_argument("--leagues", nargs="+", default=None,
                        help="联赛标识列表，如 premier_league laliga")
    args = parser.parse_args()
    run(leagues=args.leagues, season_year=args.season)
