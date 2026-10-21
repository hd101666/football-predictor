# -*- coding: utf-8 -*-
# 27_euroleague_feeds_scraper.py — EuroLeague/EuroCup 官方公开 Feeds 爬虫
#
# 数据来源: feeds.incrowdsports.com（EuroLeague 官方 APP 后端，Sportradar 基础设施）
#   ✅ 无需 API Key，公开可访问（官方 App 同接口）
#   ✅ EuroLeague + EuroCup 全量：赛程、积分榜、盒型统计
#
# 反扒策略:
#   1. curl_cffi Chrome131 TLS 指纹伪装（JA3/JA4 绕过 Cloudflare）
#   2. 正常浏览器 User-Agent + Referer 伪造（来自 EuroLeague 官网）
#   3. 首次访问首页热身获取 Cookie
#   4. 正态分布随机延迟（均值 1.5s）
#   5. 指数退避重试（最多 4 次，429/503 自动等待）
#
# 输出表:
#   euroleague_clubs      — 球队信息
#   euroleague_games      — 赛程 + 比赛结果
#   euroleague_standings  — 积分榜快照
#   euroleague_boxscores  — 逐场技术统计（得分/助攻/篮板/命中率）

import sys
import time
import json
import logging
import argparse
import random
from datetime import datetime

from sqlalchemy import create_engine, MetaData

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl
from http_utils import StealthSession, random_sleep, DEFAULT_USER_AGENTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

# ─── EuroLeague Feeds 端点 ──────────────────────────────────────────────────────
# 来源: EuroLeague 官方 App 抓包逆向（公开接口，无鉴权）
FEEDS_BASE = "https://feeds.incrowdsports.com/provider/euroleague-feeds/v2"
FEEDS_ORIGIN = "https://www.euroleague.net"

COMPETITIONS = [
    ("E", "E2024", "EuroLeague"),
    ("U", "U2024", "EuroCup"),
]

# 阶段代码: RS=常规赛  PO=季后赛  FF=最终四强
PHASE_CODES = ["RS", "PO", "FF"]


# ─── 会话（Sportradar CDN 无强力反爬，但用指纹伪装保持稳健） ─────────────────────
class _ELSession(StealthSession):
    def __init__(self):
        super().__init__(
            base_url=FEEDS_BASE,
            headers={
                "Origin":          FEEDS_ORIGIN,
                "Referer":         FEEDS_ORIGIN + "/",
                "Accept":          "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "sec-fetch-site":  "cross-site",
                "sec-fetch-mode":  "cors",
                "sec-fetch-dest":  "empty",
            },
            impersonates=["chrome131", "chrome124", "chrome123"],
        )

    def warm_up(self, path="/"):
        # 热身访问 EuroLeague 首页以获取 Cookie
        if self._warmed:
            return
        try:
            r = self._sess.get(FEEDS_ORIGIN, timeout=15)
            log.info(f"  热身 HTTP {r.status_code}")
            random_sleep(1.5, 0.5)
        except Exception as e:
            log.warning(f"热身失败: {e}")
        self._warmed = True


_sess = _ELSession()


def _api(path: str) -> dict | None:
    url = f"{FEEDS_BASE}/{path.lstrip('/')}"
    r = _sess.get(url, retries=4, timeout=20)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:
        return None


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS euroleague_clubs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            comp        TEXT,
            season      TEXT,
            club_code   TEXT,
            club_name   TEXT,
            country     TEXT,
            arena       TEXT,
            logo_url    TEXT,
            fetch_date  TEXT,
            UNIQUE(comp, season, club_code)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS euroleague_games (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            comp            TEXT,
            season          TEXT,
            game_code       INTEGER,
            phase           TEXT,
            round           INTEGER,
            game_date       TEXT,
            home_code       TEXT,
            home_name       TEXT,
            away_code       TEXT,
            away_name       TEXT,
            home_score      INTEGER,
            away_score      INTEGER,
            played          INTEGER,
            arena           TEXT,
            fetch_date      TEXT,
            UNIQUE(comp, season, game_code)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS euroleague_standings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            comp            TEXT,
            season          TEXT,
            phase           TEXT,
            group_name      TEXT,
            club_code       TEXT,
            club_name       TEXT,
            position        INTEGER,
            games_played    INTEGER,
            wins            INTEGER,
            losses          INTEGER,
            points_scored   INTEGER,
            points_against  INTEGER,
            fetch_date      TEXT,
            UNIQUE(comp, season, phase, club_code)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS euroleague_boxscores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            comp            TEXT,
            season          TEXT,
            game_code       INTEGER,
            team_side       TEXT,
            club_code       TEXT,
            club_name       TEXT,
            score           INTEGER,
            fg_made         INTEGER,
            fg_attempted    INTEGER,
            fg2_made        INTEGER,
            fg3_made        INTEGER,
            ft_made         INTEGER,
            ft_attempted    INTEGER,
            assists         INTEGER,
            rebounds        INTEGER,
            off_rebounds    INTEGER,
            def_rebounds    INTEGER,
            steals          INTEGER,
            blocks          INTEGER,
            turnovers       INTEGER,
            fouls           INTEGER,
            fetch_date      TEXT,
            UNIQUE(comp, season, game_code, team_side)
        )
    """)
    log.info("EuroLeague 数据表初始化完成")


# ─── 功能函数 ─────────────────────────────────────────────────────────────────
def fetch_clubs(comp: str, season: str, league_name: str, fetch_date: str) -> int:
    data = _api(f"competitions/{comp}/seasons/{season}/clubs")
    if not data:
        return 0
    items = data if isinstance(data, list) else data.get("data", [])
    rows = []
    for club in items:
        country = club.get("country", {})
        images  = club.get("images", {})
        rows.append({
            "comp":       comp,
            "season":     season,
            "club_code":  club.get("code", ""),
            "club_name":  club.get("name", ""),
            "country":    country.get("code", "") if isinstance(country, dict) else str(country),
            "arena":      club.get("city", "") or club.get("venueCode", ""),   # 真实字段
            "logo_url":   images.get("crest", "") if isinstance(images, dict) else "",
            "fetch_date": fetch_date,
        })
    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["euroleague_clubs"], rows, ["comp", "season", "club_code"])
    log.info(f"  {league_name} 球队: {len(rows)} 支")
    return len(rows)


def fetch_games(comp: str, season: str, league_name: str, fetch_date: str) -> int:
    data = _api(f"competitions/{comp}/seasons/{season}/games")
    if not data:
        return 0
    rows = []
    for g in data.get("data", []):
        home     = g.get("home", {})
        away     = g.get("away", {})
        rd       = g.get("round", {})
        phase_d  = g.get("phaseType", {}) or {}
        rows.append({
            "comp":       comp,
            "season":     season,
            "game_code":  g.get("code"),                                    # 实际字段: code
            "phase":      phase_d.get("code", ""),                          # phaseType.code
            "round":      rd.get("round") if isinstance(rd, dict) else rd,  # round 是 dict
            "game_date":  (g.get("date") or g.get("utcDate") or "")[:10],
            "home_code":  home.get("code", "") or home.get("tla", ""),      # 直接在 home 层
            "home_name":  home.get("name", ""),
            "away_code":  away.get("code", "") or away.get("tla", ""),
            "away_name":  away.get("name", ""),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "played":     1 if g.get("status") == "result" else 0,          # status=="result"
            "arena":      g.get("arenaName") or g.get("venue", {}).get("name", "") if isinstance(g.get("venue"), dict) else g.get("arenaName", ""),
            "fetch_date": fetch_date,
        })
    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["euroleague_games"], rows, ["comp", "season", "game_code"])
    log.info(f"  {league_name} 赛程: {len(rows)} 场")
    return len(rows)


def fetch_standings(comp: str, season: str, league_name: str, fetch_date: str) -> int:
    """
    EuroLeague Feeds v2 无独立 /standings 接口（返回404）。
    改从已落库的 euroleague_games 表计算积分榜（胜负/得失分）。
    """
    import sqlite3
    try:
        with sqlite3.connect(engine.url.database) as conn:
            cur = conn.execute(
                "SELECT home_code, home_name, away_code, away_name, "
                "       home_score, away_score, phase "
                "FROM euroleague_games "
                "WHERE comp=? AND season=? AND played=1",
                (comp, season)
            )
            games = cur.fetchall()
    except Exception:
        return 0

    if not games:
        log.info(f"  {league_name} 积分榜: 无已完成比赛，跳过")
        return 0

    from collections import defaultdict
    teams = defaultdict(lambda: {"name": "", "played": 0, "wins": 0, "losses": 0,
                                  "pts_for": 0, "pts_against": 0})
    for h_code, h_name, a_code, a_name, h_score, a_score, phase in games:
        if h_score is None or a_score is None:
            continue
        teams[h_code]["name"] = h_name
        teams[h_code]["played"] += 1
        teams[h_code]["pts_for"] += h_score
        teams[h_code]["pts_against"] += a_score
        teams[a_code]["name"] = a_name
        teams[a_code]["played"] += 1
        teams[a_code]["pts_for"] += a_score
        teams[a_code]["pts_against"] += h_score
        if h_score > a_score:
            teams[h_code]["wins"] += 1
            teams[a_code]["losses"] += 1
        else:
            teams[a_code]["wins"] += 1
            teams[h_code]["losses"] += 1

    sorted_teams = sorted(teams.items(), key=lambda x: (-x[1]["wins"], -(x[1]["pts_for"] - x[1]["pts_against"])))
    rows = []
    for pos, (code, t) in enumerate(sorted_teams, 1):
        rows.append({
            "comp":           comp,
            "season":         season,
            "phase":          "RS",
            "group_name":     "",
            "club_code":      code,
            "club_name":      t["name"],
            "position":       pos,
            "games_played":   t["played"],
            "wins":           t["wins"],
            "losses":         t["losses"],
            "points_scored":  t["pts_for"],
            "points_against": t["pts_against"],
            "fetch_date":     fetch_date,
        })
    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["euroleague_standings"], rows,
                 ["comp", "season", "phase", "club_code"])
    log.info(f"  {league_name} 积分榜（计算）: {len(rows)} 支")
    return len(rows)


def fetch_boxscores(comp: str, season: str, league_name: str,
                    fetch_date: str, max_games: int = 100) -> int:
    """拉取已完成比赛的盒型统计（只取已打完的场次）"""
    import sqlite3
    try:
        with sqlite3.connect(engine.url.database) as conn:
            cur = conn.execute(
                "SELECT game_code FROM euroleague_games "
                "WHERE comp=? AND season=? AND played=1 "
                "AND game_code NOT IN (SELECT DISTINCT game_code FROM euroleague_boxscores WHERE comp=?) "
                "ORDER BY game_code DESC LIMIT ?",
                (comp, season, comp, max_games)
            )
            game_codes = [r[0] for r in cur.fetchall()]
    except Exception:
        return 0

    rows = []
    # 实际路径: /games/{code}/stats，响应结构: {local:{team,total,players}, road:{...}}
    for game_code in game_codes:
        data = _api(f"competitions/{comp}/seasons/{season}/games/{game_code}/stats")
        if not data:
            random_sleep(1.0)
            continue
        for side, side_key in [("home", "local"), ("away", "road")]:
            sd = data.get(side_key, {})
            if not sd:
                continue
            team   = sd.get("team", {}) if isinstance(sd.get("team"), dict) else {}
            totals = sd.get("total", {}) if isinstance(sd.get("total"), dict) else {}
            rows.append({
                "comp":         comp,
                "season":       season,
                "game_code":    game_code,
                "team_side":    side,
                "club_code":    team.get("code", ""),
                "club_name":    team.get("name", ""),
                "score":        totals.get("points"),
                "fg_made":      totals.get("fieldGoalsMadeTotal"),
                "fg_attempted": totals.get("fieldGoalsAttemptedTotal"),
                "fg2_made":     totals.get("fieldGoalsMade2"),
                "fg3_made":     totals.get("fieldGoalsMade3"),
                "ft_made":      totals.get("freeThrowsMade"),
                "ft_attempted": totals.get("freeThrowsAttempted"),
                "assists":      totals.get("assistances"),       # assistances 非 assists
                "rebounds":     totals.get("totalRebounds"),
                "off_rebounds": totals.get("offensiveRebounds"),
                "def_rebounds": totals.get("defensiveRebounds"),
                "steals":       totals.get("steals"),
                "blocks":       totals.get("blocksFavour"),      # blocksFavour 非 blocks
                "turnovers":    totals.get("turnovers"),
                "fouls":        totals.get("foulsCommited"),     # foulsCommited 非 fouls
                "fetch_date":   fetch_date,
            })
        random_sleep(0.8, 0.3)

    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["euroleague_boxscores"], rows,
                 ["comp", "season", "game_code", "team_side"])
    log.info(f"  {league_name} 盒型统计: {len(rows)//2} 场")
    return len(rows)


# ─── 主入口 ─────────────────────────────────────────────────────────────────────
def run(fetch_date: str = None) -> int:
    if not fetch_date:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    init_tables()
    log.info("=" * 60)
    log.info(f"EuroLeague/EuroCup 官方 Feeds 爬虫启动 [{fetch_date}]")
    log.info("=" * 60)

    total = 0
    for comp, season, league_name in COMPETITIONS:
        log.info(f"\n📊 {league_name} ({comp}/{season})")
        total += fetch_clubs(comp, season, league_name, fetch_date)
        random_sleep(1.0)
        total += fetch_games(comp, season, league_name, fetch_date)
        random_sleep(1.0)
        total += fetch_standings(comp, season, league_name, fetch_date)
        random_sleep(1.5)
        total += fetch_boxscores(comp, season, league_name, fetch_date, max_games=50)
        random_sleep(2.0)

    log.info(f"\nEuroLeague Feeds 完成: 共写入 {total} 条数据")
    return total


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="EuroLeague/EuroCup 官方 Feeds 爬虫")
    p.add_argument("--date", default=None)
    p.add_argument("--full", action="store_true", help="拉取全量历史盒型统计（慢）")
    args = p.parse_args()
    run(fetch_date=args.date)
