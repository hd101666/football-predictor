# -*- coding: utf-8 -*-
# 12_statsbomb_national_xg_scraper.py — StatsBomb Open Data 国家队 xG 抓取
# 数据源: https://github.com/statsbomb/open-data (免费, 无需代理)
# 覆盖赛事: FIFA World Cup / UEFA Euro / Copa America / AFCON / 亚洲杯
# 表: statsbomb_national_xg_matches (场次级)
#      statsbomb_national_xg_teams   (队伍赛事汇总)

import sys
import json
import logging
import argparse
from datetime import datetime

import requests
import pandas as pd
from sqlalchemy import create_engine, MetaData

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl, batch_upsert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master"
API = "https://api.github.com/repos/statsbomb/open-data/contents"

# 目标赛事（StatsBomb competition_id）
TARGET_COMPETITIONS = {
    43:   "FIFA World Cup",
    55:   "UEFA Euro",
    223:  "Copa America",
    88:   "UEFA Nations League",
    1267: "African Cup of Nations",  # AFCON — sid=107(2023), 含刚果民主共和国
    # 281: "Asia Cup",               # 亚洲杯: StatsBomb暂无数据，已确认不可用
    # 35: "UEFA Europa League",      # 非国家队赛事，不适用
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; StatsBombFetcher/1.0)",
    "Accept": "application/json",
})
# 完全绕过系统代理（Clash等），直连 GitHub raw
SESSION.trust_env = False
SESSION.proxies = {"http": None, "https": None}


def _get_json(url: str, retries: int = 4):
    import time
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = 3 * (i + 1)
            log.warning(f"  GET 失败({i+1}/{retries}): {url} — {e} (等{wait}s)")
            time.sleep(wait)
    return None


def init_tables():
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS statsbomb_national_xg_matches (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id        INTEGER UNIQUE,
        competition_id  INTEGER,
        competition_name TEXT,
        season_name     TEXT,
        match_date      TEXT,
        home_team       TEXT,
        away_team       TEXT,
        home_score      INTEGER,
        away_score      INTEGER,
        home_xg         REAL,
        away_xg         REAL,
        fetch_date      TEXT
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS statsbomb_national_xg_teams (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        competition_name TEXT,
        season_name      TEXT,
        team_name        TEXT,
        matches_played   INTEGER,
        total_xg         REAL,
        total_xga        REAL,
        avg_xg           REAL,
        avg_xga          REAL,
        goals_scored     INTEGER,
        goals_conceded   INTEGER,
        update_time      TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(competition_name, season_name, team_name)
    )""")
    log.info("✅ StatsBomb 国家队数据表初始化完成")


def _fetch_competitions() -> list:
    """获取所有赛事列表。"""
    data = _get_json(f"{RAW}/data/competitions.json")
    if not data:
        log.error("无法获取赛事列表")
        return []
    return data


def _fetch_matches(competition_id: int, season_id: int) -> list:
    url = f"{RAW}/data/matches/{competition_id}/{season_id}.json"
    data = _get_json(url)
    return data if data else []


def _fetch_events(match_id: int) -> list:
    """获取单场比赛所有事件（用于计算 xG）。"""
    url = f"{RAW}/data/events/{match_id}.json"
    data = _get_json(url)
    return data if data else []


def _calc_match_xg(events: list, home_team: str, away_team: str) -> tuple[float, float]:
    """从事件列表中汇总主客队 xG（Shot 事件中的 shot.statsbomb_xg）。"""
    home_xg = away_xg = 0.0
    for ev in events:
        if ev.get("type", {}).get("name") != "Shot":
            continue
        shot = ev.get("shot", {})
        xg = float(shot.get("statsbomb_xg", 0) or 0)
        team = ev.get("team", {}).get("name", "")
        if team == home_team:
            home_xg += xg
        elif team == away_team:
            away_xg += xg
    return round(home_xg, 4), round(away_xg, 4)


def process_competition(comp_id: int, comp_name: str, seasons: list, fetch_date: str):
    """抓取某赛事所有赛季的比赛 xG 数据。"""
    match_rows = []
    team_stats: dict = {}  # (comp, season, team) → {...}

    for season in seasons:
        season_id   = season["season_id"]
        season_name = season["season_name"]
        log.info(f"  {comp_name} {season_name} (season_id={season_id})")

        matches = _fetch_matches(comp_id, season_id)
        log.info(f"    共 {len(matches)} 场")

        for m in matches:
            mid        = m["match_id"]
            home_team  = m.get("home_team", {}).get("home_team_name", "")
            away_team  = m.get("away_team", {}).get("away_team_name", "")
            home_score = m.get("home_score", 0) or 0
            away_score = m.get("away_score", 0) or 0
            match_date = m.get("match_date", "")

            # 从事件计算 xG
            events = _fetch_events(mid)
            home_xg, away_xg = _calc_match_xg(events, home_team, away_team)

            match_rows.append({
                "match_id":         mid,
                "competition_id":   comp_id,
                "competition_name": comp_name,
                "season_name":      season_name,
                "match_date":       match_date,
                "home_team":        home_team,
                "away_team":        away_team,
                "home_score":       int(home_score),
                "away_score":       int(away_score),
                "home_xg":          home_xg,
                "away_xg":          away_xg,
                "fetch_date":       fetch_date,
            })

            # 队伍汇总
            for team, xg_f, xg_a, gf, ga in [
                (home_team, home_xg, away_xg, home_score, away_score),
                (away_team, away_xg, home_xg, away_score, home_score),
            ]:
                if not team:
                    continue
                k = (comp_name, season_name, team)
                if k not in team_stats:
                    team_stats[k] = {"mp": 0, "xg": 0.0, "xga": 0.0, "gf": 0, "ga": 0}
                team_stats[k]["mp"]  += 1
                team_stats[k]["xg"]  += xg_f
                team_stats[k]["xga"] += xg_a
                team_stats[k]["gf"]  += int(gf)
                team_stats[k]["ga"]  += int(ga)

    if match_rows:
        md = MetaData()
        md.reflect(bind=engine)
        tbl = md.tables["statsbomb_national_xg_matches"]
        batch_upsert(engine, tbl, match_rows, unique_keys=["match_id"])
        log.info(f"  ✅ statsbomb_national_xg_matches 写入 {len(match_rows)} 场 ({comp_name})")

    team_rows = []
    for (comp_name_k, season_name_k, team), s in team_stats.items():
        mp = s["mp"]
        if mp == 0:
            continue
        team_rows.append({
            "competition_name": comp_name_k,
            "season_name":      season_name_k,
            "team_name":        team,
            "matches_played":   mp,
            "total_xg":         round(s["xg"],  4),
            "total_xga":        round(s["xga"], 4),
            "avg_xg":           round(s["xg"]  / mp, 4),
            "avg_xga":          round(s["xga"] / mp, 4),
            "goals_scored":     s["gf"],
            "goals_conceded":   s["ga"],
            "update_time":      fetch_date,
        })

    if team_rows:
        md = MetaData()
        md.reflect(bind=engine)
        tbl = md.tables["statsbomb_national_xg_teams"]
        batch_upsert(engine, tbl, team_rows,
                     unique_keys=["competition_name", "season_name", "team_name"])
        log.info(f"  ✅ statsbomb_national_xg_teams 写入 {len(team_rows)} 队 ({comp_name})")


def run(comp_ids: list = None, latest_only: bool = False):
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")

    all_comps = _fetch_competitions()
    if not all_comps:
        return

    # 筛选目标赛事
    target_ids = comp_ids or list(TARGET_COMPETITIONS.keys())
    # 按赛事分组
    grouped: dict = {}
    for c in all_comps:
        cid = c["competition_id"]
        if cid not in target_ids:
            continue
        cname = TARGET_COMPETITIONS.get(cid, c.get("competition_name", str(cid)))
        if cid not in grouped:
            grouped[cid] = {"name": cname, "seasons": []}
        grouped[cid]["seasons"].append({
            "season_id":   c["season_id"],
            "season_name": c["season_name"],
        })

    if not grouped:
        log.warning("无匹配赛事，请检查 comp_ids 或 TARGET_COMPETITIONS")
        return

    log.info(f"=== StatsBomb 国家队 xG 抓取 | 赛事数={len(grouped)} ===")

    for cid, info in grouped.items():
        seasons = info["seasons"]
        if latest_only:
            # 只取最新赛季（season_name 字符串最大值）
            seasons = sorted(seasons, key=lambda x: x["season_name"], reverse=True)[:1]
        log.info(f"赛事: {info['name']} | {len(seasons)} 个赛季")
        process_competition(cid, info["name"], seasons, fetch_date)

    log.info("=== StatsBomb 国家队 xG 抓取完成 ===")


# ── 查询接口（供预测模型调用）────────────────────────────────────────────────

def get_national_team_xg(team: str, competition: str = None) -> dict:
    """
    查询国家队 xG，返回最近赛事的场均数据。
    返回: {'avg_xg': float, 'avg_xga': float, 'competition': str, 'season': str}
    """
    DEFAULT = {"avg_xg": 1.3, "avg_xga": 1.3, "competition": "", "season": ""}
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            base = """SELECT avg_xg, avg_xga, competition_name, season_name
                      FROM statsbomb_national_xg_teams
                      WHERE LOWER(team_name) = LOWER(:t)"""
            params: dict = {"t": team}
            if competition:
                base += " AND LOWER(competition_name) LIKE LOWER(:c)"
                params["c"] = f"%{competition}%"
            base += " ORDER BY season_name DESC LIMIT 1"
            r = conn.execute(text(base), params).fetchone()
        if r:
            return {
                "avg_xg":      r[0],
                "avg_xga":     r[1],
                "competition": r[2],
                "season":      r[3],
            }
    except Exception as e:
        log.warning(f"查询国家队 xG 失败: {e}")
    return DEFAULT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StatsBomb Open Data 国家队 xG 抓取")
    parser.add_argument("--comps",  nargs="+", type=int, default=None,
                        help="赛事 ID 列表，如 43 55 223（默认抓全部目标赛事）")
    parser.add_argument("--latest", action="store_true",
                        help="每个赛事只抓最新赛季（速度更快）")
    args = parser.parse_args()
    run(comp_ids=args.comps, latest_only=args.latest)
