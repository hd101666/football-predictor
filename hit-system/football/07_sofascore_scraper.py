# 07_sofascore_scraper.py — SofaScore 数据爬虫
# 抓取：今日/明日赛程、赛事统计、队伍近况、H2H历史、赔率快照
# 存储：sofascore_matches / sofascore_stats / sofascore_form / sofascore_h2h / sofascore_odds

import time
import json
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import exec_ddl, batch_upsert
from http_utils import StealthSession, random_sleep
from sqlalchemy import MetaData, Table

# Bug修复(2026-08-12)：原先只有 getLogger、**没有 basicConfig**，独立运行时
# Python日志默认只输出WARNING及以上，所有 log.info 的成功信息被静默丢弃，
# 日志里只剩重试噪音——工作正常的爬虫会看起来像全线失败（09号即因此被误判）。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)


def _get_table(engine, table_name):
    """获取表对象用于 batch_upsert"""
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]


# ─── 常量 ──────────────────────────────────────────────────────────────────
# 注意：SofaScore 对所有 /api/v1/* 路径开启了 Cloudflare JS Challenge，
# curl_cffi 无法绕过。当前爬虫会尝试但大概率返回 403。
# 系统已有 football_xg_stats 兜底（490条 understat+historical），不影响预测。
BASE      = "https://api.sofascore.com/api/v1"
BASE_APP  = "https://www.sofascore.com/api/v1"
MAIN_URL  = "https://www.sofascore.com"

SOFA_HEADERS = {
    "Referer":         "https://www.sofascore.com/",
    "Origin":          "https://www.sofascore.com",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "sec-fetch-site":  "same-site",
    "sec-fetch-mode":  "cors",
    "sec-fetch-dest":  "empty",
    "sec-ch-ua":       '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform": '"Windows"',
}

# SofaScore sport slug → 我们的 sport_code
SPORT_MAP = {
    "football":   "football",
    "basketball": "basketball",
}

# 我们关注的联赛 tournament_id（SofaScore 内部 ID）
FOOTBALL_TOURNAMENT_IDS = {  # TODO: 迁移到 leagues.py 统一管理
    17:   "premier_league",
    8:    "laliga",
    23:   "serie_a",
    35:   "bundesliga",
    34:   "ligue_1",
    242:  "csl",
    600:  "j1",
    292:  "k_league_1",
    242:  "csl",
    155:  "mls",
    44:   "championship",
    679:  "serie_a_br",
}

BASKETBALL_TOURNAMENT_IDS = {  # TODO: 迁移到 leagues.py 统一管理
    132:  "nba",
    695:  "cba",
    685:  "euroleague",
}


# ─── DDL ────────────────────────────────────────────────────────────────────
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS sofascore_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER UNIQUE,
            sport_code TEXT,
            tournament_id INTEGER,
            league_name TEXT,
            season_name TEXT,
            home_team_id INTEGER,
            home_team_name TEXT,
            away_team_id INTEGER,
            away_team_name TEXT,
            kickoff_utc TEXT,
            status_code TEXT,
            home_score INTEGER,
            away_score INTEGER,
            home_score_ht INTEGER,
            away_score_ht INTEGER,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS sofascore_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            period TEXT,
            stat_key TEXT,
            home_value REAL,
            away_value REAL,
            fetch_date TEXT,
            UNIQUE(event_id, period, stat_key)
        )""",
        """CREATE TABLE IF NOT EXISTS sofascore_form (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER,
            event_id INTEGER,
            opponent_id INTEGER,
            opponent_name TEXT,
            is_home INTEGER,
            kickoff_utc TEXT,
            goals_for INTEGER,
            goals_against INTEGER,
            result TEXT,
            fetch_date TEXT,
            UNIQUE(team_id, event_id)
        )""",
        """CREATE TABLE IF NOT EXISTS sofascore_h2h (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team1_id INTEGER,
            team2_id INTEGER,
            event_id INTEGER,
            kickoff_utc TEXT,
            home_team_id INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            fetch_date TEXT,
            UNIQUE(team1_id, team2_id, event_id)
        )""",
        """CREATE TABLE IF NOT EXISTS sofascore_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            bookmaker TEXT,
            outcome TEXT,
            odds_value REAL,
            fetch_date TEXT,
            UNIQUE(event_id, bookmaker, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS sofascore_xg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER UNIQUE,
            home_team_name TEXT,
            away_team_name TEXT,
            kickoff_utc TEXT,
            league_name TEXT,
            home_xg REAL,
            away_xg REAL,
            home_xg_ht REAL,
            away_xg_ht REAL,
            home_xg_ft REAL,
            away_xg_ft REAL,
            fetch_date TEXT
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ SofaScore 数据表初始化完成")


# ─── HTTP 会话（使用公共 StealthSession 基类）───────────────────────────────
# 注意：SofaScore 对 api.sofascore.com 开启了 Cloudflare IP 封锁，
# curl_cffi 和 Playwright headless 均返回 403。sofascore 已从调度队列移除，
# 系统通过 theodds (Pinnacle+OddsPortal) 获取赔率，不依赖此数据源。
_session = StealthSession(base_url=MAIN_URL, headers=SOFA_HEADERS)


def _get(path: str, params: dict = None, retries: int = 4) -> Optional[dict]:
    for base in [BASE, BASE_APP]:
        url = f"{base}{path}"
        result = _session.get_json(url, retries=retries, params=params)
        if result is not None:
            return result
    return None


def _sleep():
    time.sleep(CRAWL_MIN_SLEEP + (CRAWL_MAX_SLEEP - CRAWL_MIN_SLEEP) * 0.5)


# ─── 1. 赛程抓取 ─────────────────────────────────────────────────────────────
def fetch_scheduled_events(sport: str, date_str: str) -> list:
    """抓取某日某运动的全部赛事"""
    data = _get(f"/sport/{sport}/scheduled-events/{date_str}")
    if not data:
        return []
    events = data.get("events", [])
    log.info(f"  {sport} {date_str}: {len(events)} 场")
    return events


def upsert_matches(events: list, sport_code: str, fetch_date: str):
    """将赛事列表写入 sofascore_matches"""
    rows = []
    for ev in events:
        try:
            ht = ev.get("homeTeam", {})
            at = ev.get("awayTeam", {})
            sc = ev.get("homeScore", {})
            ac = ev.get("awayScore", {})
            ts = ev.get("tournament", {})
            se = ev.get("season", {})
            rows.append({
                "event_id":       ev["id"],
                "sport_code":     sport_code,
                "tournament_id":  ts.get("id"),
                "league_name":    ts.get("name", ""),
                "season_name":    se.get("name", ""),
                "home_team_id":   ht.get("id"),
                "home_team_name": ht.get("name", ""),
                "away_team_id":   at.get("id"),
                "away_team_name": at.get("name", ""),
                "kickoff_utc":    datetime.fromtimestamp(
                    ev.get("startTimestamp", 0), tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S") if ev.get("startTimestamp") else "",
                "status_code":    ev.get("status", {}).get("code", ""),
                "home_score":     sc.get("current"),
                "away_score":     ac.get("current"),
                "home_score_ht":  sc.get("period1"),
                "away_score_ht":  ac.get("period1"),
                "fetch_date":     fetch_date,
            })
        except Exception as e:
            log.debug(f"解析赛事异常: {e}")
    if not rows:
        return
    tbl = _get_table(engine, "sofascore_matches")
    batch_upsert(engine, tbl, rows, unique_keys=["event_id"])
    log.info(f"  ✅ 写入 sofascore_matches {len(rows)} 条")


# ─── 2. 赛事统计 ─────────────────────────────────────────────────────────────
def fetch_and_store_stats(event_id: int, fetch_date: str):
    """抓取并存储单场赛事统计数据"""
    data = _get(f"/event/{event_id}/statistics")
    if not data:
        return
    rows = []
    for period_group in data.get("statistics", []):
        period = period_group.get("period", "ALL")
        for group in period_group.get("groups", []):
            for stat in group.get("statisticsItems", []):
                key = stat.get("key") or stat.get("name", "")
                try:
                    home_val = float(str(stat.get("home", "0")).replace("%", "").strip() or 0)
                    away_val = float(str(stat.get("away", "0")).replace("%", "").strip() or 0)
                except (ValueError, TypeError):
                    continue
                rows.append({
                    "event_id":   event_id,
                    "period":     period,
                    "stat_key":   key,
                    "home_value": home_val,
                    "away_value": away_val,
                    "fetch_date": fetch_date,
                })
    if not rows:
        return
    tbl = _get_table(engine, "sofascore_stats")
    batch_upsert(engine, tbl, rows, unique_keys=["event_id", "period", "stat_key"])


# ─── xG 专项提取 ─────────────────────────────────────────────────────────────
_XG_KEYS = {
    'expected_goals', 'expectedgoals', 'xg', 'xexpectedgoals',
    'expected_goals_ht', 'expectedgoalsht',
}

def fetch_and_store_xg(event_id: int, home_name: str, away_name: str,
                       kickoff: str, league: str, fetch_date: str):
    """从 /statistics 端点提取 xG 数据，落库到 sofascore_xg"""
    data = _get(f"/event/{event_id}/statistics")
    if not data:
        return

    xg_map: dict = {}  # period -> {home, away}
    for period_group in data.get("statistics", []):
        period = period_group.get("period", "ALL").upper()
        for group in period_group.get("groups", []):
            for stat in group.get("statisticsItems", []):
                key = (stat.get("key") or stat.get("name") or "").lower().replace(" ", "_").replace("-", "_")
                if key not in _XG_KEYS:
                    continue
                try:
                    hv = float(str(stat.get("home", 0) or 0))
                    av = float(str(stat.get("away", 0) or 0))
                except (ValueError, TypeError):
                    continue
                if period not in xg_map:
                    xg_map[period] = {}
                xg_map[period]['home'] = hv
                xg_map[period]['away'] = av

    if not xg_map:
        return

    all_p  = xg_map.get('ALL', {})
    ht_p   = xg_map.get('1ST', xg_map.get('FIRST', {}))
    ft_p   = xg_map.get('2ND', xg_map.get('SECOND', {}))

    row = {
        'event_id':       event_id,
        'home_team_name': home_name,
        'away_team_name': away_name,
        'kickoff_utc':    kickoff,
        'league_name':    league,
        'home_xg':        all_p.get('home'),
        'away_xg':        all_p.get('away'),
        'home_xg_ht':     ht_p.get('home'),
        'away_xg_ht':     ht_p.get('away'),
        'home_xg_ft':     ft_p.get('home'),
        'away_xg_ft':     ft_p.get('away'),
        'fetch_date':     fetch_date,
    }

    if row['home_xg'] is None and row['home_xg_ht'] is None:
        return

    tbl = _get_table(engine, "sofascore_xg")
    batch_upsert(engine, tbl, [row], unique_keys=["event_id"])
    log.info(f"  [xG] event={event_id} {home_name} {row['home_xg']:.2f} vs {away_name} {row['away_xg']:.2f}")


# ─── 3. 队伍近10场形态 ──────────────────────────────────────────────────────
def fetch_and_store_form(team_id: int, fetch_date: str):
    """抓取队伍近10场比赛结果"""
    data = _get(f"/team/{team_id}/last/0")
    if not data:
        return
    rows = []
    for ev in data.get("events", [])[:10]:
        try:
            ht = ev.get("homeTeam", {})
            at = ev.get("awayTeam", {})
            sc = ev.get("homeScore", {})
            ac = ev.get("awayScore", {})
            is_home = (ht.get("id") == team_id)
            opp_id   = at.get("id") if is_home else ht.get("id")
            opp_name = at.get("name", "") if is_home else ht.get("name", "")
            gf = sc.get("current", 0) if is_home else ac.get("current", 0)
            ga = ac.get("current", 0) if is_home else sc.get("current", 0)
            if gf is None or ga is None:
                continue
            result = "W" if gf > ga else ("D" if gf == ga else "L")
            rows.append({
                "team_id":       team_id,
                "event_id":      ev["id"],
                "opponent_id":   opp_id,
                "opponent_name": opp_name,
                "is_home":       1 if is_home else 0,
                "kickoff_utc":   datetime.fromtimestamp(
                    ev.get("startTimestamp", 0), tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S") if ev.get("startTimestamp") else "",
                "goals_for":     int(gf),
                "goals_against": int(ga),
                "result":        result,
                "fetch_date":    fetch_date,
            })
        except Exception:
            continue
    if not rows:
        return
    tbl = _get_table(engine, "sofascore_form")
    batch_upsert(engine, tbl, rows, unique_keys=["team_id", "event_id"])


# ─── 4. H2H 历史 ─────────────────────────────────────────────────────────────
def fetch_and_store_h2h(event_id: int, home_team_id: int, away_team_id: int, fetch_date: str):
    """抓取两队历史对阵记录（最近20场）"""
    data = _get(f"/event/{event_id}/h2h/events")
    if not data:
        return
    rows = []
    for section in ("homeTeamEvents", "awayTeamEvents", "previousEvents"):
        for ev in data.get(section, [])[:20]:
            try:
                ht = ev.get("homeTeam", {})
                sc = ev.get("homeScore", {})
                ac = ev.get("awayScore", {})
                rows.append({
                    "team1_id":     home_team_id,
                    "team2_id":     away_team_id,
                    "event_id":     ev["id"],
                    "kickoff_utc":  datetime.fromtimestamp(
                        ev.get("startTimestamp", 0), tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S") if ev.get("startTimestamp") else "",
                    "home_team_id": ht.get("id"),
                    "home_score":   sc.get("current"),
                    "away_score":   ac.get("current"),
                    "fetch_date":   fetch_date,
                })
            except Exception:
                continue
    if not rows:
        return
    tbl = _get_table(engine, "sofascore_h2h")
    batch_upsert(engine, tbl, rows, unique_keys=["team1_id", "team2_id", "event_id"])


# ─── 5. 赔率快照 ─────────────────────────────────────────────────────────────
def fetch_and_store_odds(event_id: int, fetch_date: str):
    """抓取 1X2 赔率（market_id=1）"""
    data = _get(f"/event/{event_id}/odds/1/all")
    if not data:
        return
    rows = []
    for provider in data.get("markets", [data]) if "markets" in data else []:
        bookmaker = provider.get("marketName", provider.get("sourceName", "unknown"))
        for choice in provider.get("choices", []):
            try:
                rows.append({
                    "event_id":   event_id,
                    "bookmaker":  bookmaker,
                    "outcome":    choice.get("name", ""),
                    "odds_value": float(choice.get("fractionalValue", choice.get("initialFractionalValue", 0)) or 0),
                    "fetch_date": fetch_date,
                })
            except Exception:
                continue
    # 另一种格式
    if not rows:
        for item in data.get("odds", []):
            try:
                rows.append({
                    "event_id":   event_id,
                    "bookmaker":  item.get("source", ""),
                    "outcome":    item.get("choice", ""),
                    "odds_value": float(item.get("decimalValue", 0) or 0),
                    "fetch_date": fetch_date,
                })
            except Exception:
                continue
    if not rows:
        return
    tbl = _get_table(engine, "sofascore_odds")
    batch_upsert(engine, tbl, rows, unique_keys=["event_id", "bookmaker", "outcome"])


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def run(days_ahead: int = 1, fetch_stats: bool = True,
        fetch_form: bool = True, fetch_h2h: bool = True, fetch_odds_flag: bool = True):
    """
    主入口
    days_ahead : 抓取今日 + 未来 N 天的赛程（默认今明两天）
    fetch_stats : 是否抓取已完赛赛事统计
    fetch_form  : 是否抓取队伍近期形态
    fetch_h2h   : 是否抓取历史对阵
    fetch_odds_flag : 是否抓取赔率快照
    """
    init_tables()
    today = datetime.now()
    fetch_date = today.strftime("%Y-%m-%d")

    all_upcoming = []  # 未开赛赛事，用于抓取 form/h2h/odds

    for delta in range(days_ahead + 1):
        d = (today + timedelta(days=delta)).strftime("%Y-%m-%d")

        for sport_slug, sport_code in SPORT_MAP.items():
            log.info(f"📅 抓取 {sport_slug} {d} 赛程...")
            events = fetch_scheduled_events(sport_slug, d)
            if not events:
                _sleep()
                continue

            upsert_matches(events, sport_code, fetch_date)

            for ev in events:
                status_code = ev.get("status", {}).get("code", 0)
                ev_id = ev["id"]
                ht_id = ev.get("homeTeam", {}).get("id")
                at_id = ev.get("awayTeam", {}).get("id")

                # 已完赛 → 抓统计 + xG
                if fetch_stats and status_code == 100:
                    fetch_and_store_stats(ev_id, fetch_date)
                    _sleep()
                    ht_name = ev.get("homeTeam", {}).get("name", "")
                    at_name = ev.get("awayTeam", {}).get("name", "")
                    ko      = ev.get("startTimestamp", 0)
                    ko_str  = datetime.fromtimestamp(ko, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if ko else ""
                    lg      = ev.get("tournament", {}).get("name", "")
                    fetch_and_store_xg(ev_id, ht_name, at_name, ko_str, lg, fetch_date)
                    _sleep()

                # 未开赛(0) 或 预告(7) → 抓 form / h2h / odds
                if status_code in (0, 7):
                    all_upcoming.append((ev_id, ht_id, at_id))

    log.info(f"\n🔍 未开赛赛事 {len(all_upcoming)} 场，开始抓取 form / h2h / odds ...")
    seen_teams = set()

    for ev_id, ht_id, at_id in all_upcoming:
        if fetch_form:
            for tid in (ht_id, at_id):
                if tid and tid not in seen_teams:
                    log.info(f"  队伍形态 team_id={tid}")
                    fetch_and_store_form(tid, fetch_date)
                    seen_teams.add(tid)
                    _sleep()

        if fetch_h2h:
            log.info(f"  H2H event_id={ev_id}")
            fetch_and_store_h2h(ev_id, ht_id, at_id, fetch_date)
            _sleep()

        if fetch_odds_flag:
            log.info(f"  赔率 event_id={ev_id}")
            fetch_and_store_odds(ev_id, fetch_date)
            _sleep()

    log.info("✅ SofaScore 抓取完成")


if __name__ == "__main__":
    run(days_ahead=1, fetch_stats=True, fetch_form=True, fetch_h2h=True, fetch_odds_flag=True)
