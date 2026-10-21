# -*- coding: utf-8 -*-
# 12_pinnacle_scraper.py — Pinnacle 直爬补充爬虫
# 通过 Pinnacle guest public API 抓取实时盘口、封盘赔率、亚盘、大小球
# 存储：pinnacle_leagues / pinnacle_fixtures / pinnacle_odds / pinnacle_odds_history
# Pinnacle 公共 guest API 无需认证，直接请求即可

import requests, time, json, logging, random
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, MetaData, text

import env_setup
from config import (DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP, PINNACLE_GUEST_KEY,
                    CORNER_SCRAPE_TIME_BUDGET_S)
from db_utils import batch_upsert, exec_ddl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

# ─── Pinnacle Guest API ───────────────────────────────────────────────────────
GUEST_API = "https://guest.api.arcadia.pinnacle.com/0.1"

# sport_id: 29=足球, 4=篮球
SPORT_IDS = {
    "football":   29,
    "basketball":  4,
}

FOOTBALL_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "Eredivisie", "Primeira Liga", "Super Lig", "MLS", "Serie A Brazil",
    "Chinese Super League", "J1 League", "K League", "Championship",
    "Champions League", "Europa League", "Copa Libertadores",
    "Russian Premier League", "Argentine Primera",
]

BASKETBALL_LEAGUE_KEYWORDS = [
    "NBA", "EuroLeague", "CBA",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "x-api-key": PINNACLE_GUEST_KEY,
}


def _get_tables():
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables


def amer_to_dec(amer: float) -> float:
    """美式赔率 → 十进制赔率"""
    if amer > 0:
        return round(amer / 100 + 1, 4)
    else:
        return round(100 / abs(amer) + 1, 4)


def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS pinnacle_leagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER UNIQUE,
            sport_code TEXT,
            league_name TEXT,
            is_featured INTEGER DEFAULT 0,
            match_count INTEGER DEFAULT 0,
            fetch_date TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS pinnacle_fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matchup_id INTEGER UNIQUE,
            sport_code TEXT,
            league_id INTEGER,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS pinnacle_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matchup_id INTEGER,
            market_type TEXT,
            period INTEGER DEFAULT 0,
            side TEXT,
            price REAL,
            handicap REAL,
            max_bet REAL,
            fetch_date TEXT,
            recorded_at TEXT,
            UNIQUE(matchup_id, market_type, period, side)
        )""",
        """CREATE TABLE IF NOT EXISTS pinnacle_odds_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matchup_id INTEGER,
            market_type TEXT,
            period INTEGER DEFAULT 0,
            side TEXT,
            price REAL,
            handicap REAL,
            recorded_at TEXT,
            fetch_date TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS pinnacle_corner_odds (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            corner_matchup_id INTEGER NOT NULL,
            parent_matchup_id INTEGER,
            league_name       TEXT,
            home_team         TEXT,
            away_team         TEXT,
            kickoff_utc       TEXT,
            market_type       TEXT,
            period            INTEGER DEFAULT 0,
            side              TEXT,
            team_side         TEXT,
            line              REAL,
            price_amer        REAL,
            price_dec         REAL,
            is_alternate      INTEGER DEFAULT 0,
            max_bet           REAL,
            status            TEXT,
            fetch_date        TEXT,
            recorded_at       TEXT,
            UNIQUE(corner_matchup_id, market_type, period, side, team_side, line, fetch_date)
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ Pinnacle 数据表初始化完成")


_session = requests.Session()
_session.headers.update(HEADERS)


def _get(path: str, params: dict = None, retries: int = 4) -> Optional[dict]:
    url = f"{GUEST_API}{path}"
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = 20 * (attempt + 1)
                log.warning(f"429限流，等待{wait}s...")
                time.sleep(wait)
                continue
            if r.status_code == 401:
                log.warning("401认证失败，尝试无key请求...")
                _session.headers.pop("x-api-key", None)
                continue
            if r.status_code == 403:
                # 403 = 该matchup/market已关闭或过期(资源存在但拒绝访问)，不是限流，
                # 重试不会变好——实测角球抓取里大量已开赛/已结束matchup的
                # markets/straight会连续403，原来跟通用分支一样傻等重试满retries次
                # (每次仍有真实网络往返耗时)，成千上万个这种请求叠加起来会显著
                # 拖慢整体抓取速度，是CORNER_SCRAPE_TIME_BUDGET_S(1500s)提前耗尽、
                # 跳过大量联赛的重要原因之一。直接放弃这次请求，把时间留给别的联赛。
                log.debug(f"HTTP 403(资源已关闭，不重试): {path}")
                return None
            log.warning(f"HTTP {r.status_code}: {path}")
        except Exception as e:
            log.warning(f"请求异常({attempt+1}): {e}")
            time.sleep(3)
    return None


def _sleep():
    time.sleep(random.uniform(CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP))


# ─── 1. 获取联赛列表 ──────────────────────────────────────────────────────────
def fetch_leagues(sport_code: str) -> list:
    sport_id = SPORT_IDS.get(sport_code, 29)
    data = _get(f"/sports/{sport_id}/leagues", params={"all": "false"})
    if not data:
        return []

    leagues = data if isinstance(data, list) else data.get("leagues", [])
    keywords = FOOTBALL_LEAGUE_KEYWORDS if sport_code == "football" else BASKETBALL_LEAGUE_KEYWORDS

    result = []
    rows = []
    fetch_date = datetime.now().strftime("%Y-%m-%d")

    for lg in leagues:
        league_id   = lg.get("id")
        league_name = lg.get("name", "")
        is_featured = 1 if lg.get("isPromoted") or lg.get("isFeatured") else 0
        match_count = lg.get("matchupCount", 0) or lg.get("count", 0)

        is_target = any(kw.lower() in league_name.lower() for kw in keywords)
        if not is_target and match_count == 0:
            continue

        rows.append({
            "league_id": league_id, "sport_code": sport_code,
            "league_name": league_name, "is_featured": is_featured,
            "match_count": match_count, "fetch_date": fetch_date,
        })

        if is_target or match_count > 0:
            result.append({"id": league_id, "name": league_name})

    if rows:
        tables = _get_tables()
        if "pinnacle_leagues" in tables:
            batch_upsert(engine, tables["pinnacle_leagues"], rows, unique_keys=["league_id"])

    log.info(f"  {sport_code} 联赛: {len(result)} 个")
    return result


# ─── 2. 抓取赛事 ──────────────────────────────────────────────────────────────
def fetch_fixtures(league_id: int, league_name: str, sport_code: str, fetch_date: str) -> list:
    data = _get(f"/leagues/{league_id}/matchups")
    if not data:
        return []

    matchups = data if isinstance(data, list) else data.get("matchups", [])
    ids = []
    rows = []

    for mu in matchups:
        try:
            mid    = mu.get("id")
            status = mu.get("status", "NS")
            ts     = mu.get("startTime", "")
            kickoff = ts[:19].replace("T", " ") if ts else ""

            mu_type = mu.get("type", "")
            if mu_type == "special":
                continue

            participants = mu.get("participants", [])
            home_team, away_team = "", ""
            home_score, away_score = None, None

            for p in participants:
                alignment = p.get("alignment", "")
                name      = p.get("name", "")
                score     = p.get("score")
                if alignment == "home":
                    home_team  = name
                    home_score = score
                elif alignment in ("away", "visiting"):
                    away_team  = name
                    away_score = score

            if "(Corners)" in home_team or "(Corners)" in away_team:
                continue

            if not mid:
                continue

            ids.append(mid)
            rows.append({
                "matchup_id": mid, "sport_code": sport_code,
                "league_id": league_id, "league_name": league_name,
                "home_team": home_team, "away_team": away_team,
                "kickoff_utc": kickoff, "status": status,
                "home_score": home_score, "away_score": away_score,
                "fetch_date": fetch_date,
            })
        except Exception as e:
            log.debug(f"fixture解析异常: {e}")

    if rows:
        tables = _get_tables()
        if "pinnacle_fixtures" in tables:
            batch_upsert(engine, tables["pinnacle_fixtures"], rows, unique_keys=["matchup_id"])

    return ids


# ─── 3. 抓取赔率 ──────────────────────────────────────────────────────────────
def fetch_odds_for_league(league_id: int, sport_code: str, fetch_date: str):
    """一次性抓取联赛所有赛事的赔率（Straight market）"""
    data = _get(f"/leagues/{league_id}/markets/straight")
    if not data:
        return

    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    markets = data if isinstance(data, list) else data.get("markets", [])

    odds_rows = []
    hist_rows = []

    for market in markets:
        matchup_id  = market.get("matchupId")
        market_type = market.get("type", "")   # moneyline / spread / total / team_total
        period      = market.get("period", 0)
        prices      = market.get("prices", [])

        # Bug修复：team_total 在 Pinnacle API 里对同一 matchupId 会返回两条market
        # (side="home"/"away"，各自独立的线，如实测 home线6.5/away线3.5)，但market_type
        # 原来统一存成裸的"team_total"，跟下面(matchup_id,market_type,period,side)的
        # side(over/under designation)组成唯一键——home/away两条会撞上同一个键，
        # 后写入的静默覆盖先写入的，下游又硬编码"team_total默认指主队"，两个问题叠加导致
        # 库里team_total数据的真实归属队伍不可考。用market_type带上side前缀彻底分开存储。
        if market_type == "team_total":
            _tt_side = market.get("side", "")
            if _tt_side in ("home", "away"):
                market_type = f"team_total_{_tt_side}"

        if not matchup_id:
            continue

        # 只保留全场盘口（period=0）
        if period != 0:
            continue

        # ⚡ 过滤 alternate 盘口：只保留主盘口（isAlternate=false 或字段不存在）
        if market.get("isAlternate", False) is True:
            continue

        for price_entry in prices:
            side     = price_entry.get("designation", price_entry.get("side", ""))
            price    = price_entry.get("price")
            handicap = price_entry.get("points") if price_entry.get("points") is not None else price_entry.get("handicap")
            max_bet  = price_entry.get("maxBet")

            if price is None:
                continue

            try:
                price_f = float(price)
            except Exception:
                continue

            # 存储原始美式赔率，由 build_unified_odds 统一转换为十进制
            odds_rows.append({
                "matchup_id": matchup_id, "market_type": market_type,
                "period": period, "side": side,
                "price": price_f, "handicap": handicap,
                "max_bet": max_bet, "fetch_date": fetch_date,
                "recorded_at": now_str,
            })
            hist_rows.append({
                "matchup_id": matchup_id, "market_type": market_type,
                "period": period, "side": side,
                "price": price_f, "handicap": handicap,
                "recorded_at": now_str, "fetch_date": fetch_date,
            })

    if odds_rows or hist_rows:
        tables = _get_tables()
        if odds_rows and "pinnacle_odds" in tables:
            batch_upsert(engine, tables["pinnacle_odds"], odds_rows,
                         unique_keys=["matchup_id", "market_type", "period", "side"])
        if hist_rows and "pinnacle_odds_history" in tables:
            batch_upsert(engine, tables["pinnacle_odds_history"], hist_rows,
                         unique_keys=[])

    log.info(f"    odds: {len(odds_rows)} 条")


# ─── 4. 特殊赔率：亚盘 + 大小球（已由 fetch_odds_for_league 涵盖，此函数保留兼容） ───
def fetch_special_markets(league_id: int, fetch_date: str):
    """spread/total/moneyline 已在 fetch_odds_for_league 中一次性抓取，此处无需重复"""
    pass


# ─── 5. 角球市场 ──────────────────────────────────────────────────────────────

def find_corner_matchups(main_matchup_ids: list) -> dict:
    """
    对每个主赛事 matchup_id 调用 /matchups/{id}/related，
    找出 units="Corners" 的衍生 matchup。
    返回: {corner_matchup_id: parent_matchup_id}
    """
    corner_map = {}
    for mid in main_matchup_ids:
        data = _get(f"/matchups/{mid}/related")
        if not data:
            continue
        related = data if isinstance(data, list) else data.get("matchups", [])
        for rel in related:
            if rel.get("units") == "Corners":
                corner_map[rel["id"]] = mid
        _sleep()
    return corner_map


def fetch_corner_markets(corner_matchup_id: int, parent_matchup_id: int,
                         fixture_info: dict, fetch_date: str) -> list:
    """
    抓取单个角球 matchup 的全部直盘赔率并转换为 DB 行。
    fixture_info: {home_team, away_team, league_name, kickoff_utc}
    """
    data = _get(f"/matchups/{corner_matchup_id}/markets/straight")
    if not data:
        return []

    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    markets = data if isinstance(data, list) else data.get("markets", [])
    rows = []

    for mk in markets:
        if mk.get("status") != "open":
            continue
        market_type  = mk.get("type", "")       # total / spread / team_total
        period       = mk.get("period", 0)       # 0=全场, 1=上半场
        is_alternate = 1 if mk.get("isAlternate", False) else 0
        team_side    = mk.get("side", "")        # team_total 特有: home/away
        max_bet      = None
        for lim in mk.get("limits", []):
            if lim.get("type") == "maxRiskStake":
                max_bet = lim.get("amount")

        for price_entry in mk.get("prices", []):
            designation = price_entry.get("designation", "")
            line        = price_entry.get("points")
            price_amer  = price_entry.get("price")
            if price_amer is None or line is None:
                continue
            try:
                price_dec = amer_to_dec(float(price_amer))
            except Exception:
                continue

            rows.append({
                "corner_matchup_id": corner_matchup_id,
                "parent_matchup_id": parent_matchup_id,
                "league_name":       fixture_info.get("league_name"),
                "home_team":         fixture_info.get("home_team"),
                "away_team":         fixture_info.get("away_team"),
                "kickoff_utc":       fixture_info.get("kickoff_utc"),
                "market_type":       market_type,
                "period":            period,
                "side":              designation,
                "team_side":         team_side or None,
                "line":              float(line),
                "price_amer":        float(price_amer),
                "price_dec":         price_dec,
                "is_alternate":      is_alternate,
                "max_bet":           max_bet,
                "status":            "open",
                "fetch_date":        fetch_date,
                "recorded_at":       now_str,
            })

    return rows


def fetch_all_corner_odds(fetch_date: str):
    """
    全量角球赔率抓取流程:
      1. 获取所有足球联赛 (all=true)
      2. 对每个有比赛的联赛, 获取 matchups
      3. 找 units=Corners 的关联 matchup
      4. 抓赔率写入 pinnacle_corner_odds
    """
    sport_id = SPORT_IDS["football"]
    data = _get(f"/sports/{sport_id}/leagues", params={"all": "false"})
    if not data:
        log.warning("无法获取联赛列表")
        return 0

    leagues = data if isinstance(data, list) else data.get("leagues", [])
    active_leagues = [l for l in leagues if l.get("matchupCount", 0) > 0]
    log.info(f"角球抓取: {len(active_leagues)} 个活跃联赛")

    tables = _get_tables()
    total_saved = 0
    _t0 = time.time()

    for _li, lg in enumerate(active_leagues):
        # 时间预算：逐场遍历全球联赛耗时不可控，超预算跳过剩余联赛，
        # 保留已抓部分，避免被外层爬虫调度的 1800s 超时强杀导致本次 0 条落库
        if time.time() - _t0 > CORNER_SCRAPE_TIME_BUDGET_S:
            log.warning(f"角球抓取超时间预算（{CORNER_SCRAPE_TIME_BUDGET_S}s），"
                        f"跳过剩余 {len(active_leagues) - _li} 个联赛")
            break

        league_id   = lg["id"]
        league_name = lg["name"]

        # 1) 获取主赛事 matchup 列表
        mu_data = _get(f"/leagues/{league_id}/matchups")
        if not mu_data:
            _sleep()
            continue
        matchups = mu_data if isinstance(mu_data, list) else mu_data.get("matchups", [])

        # 只保留主赛事（type=matchup 且非 special）
        main_matchups = [m for m in matchups if m.get("type") == "matchup"]
        if not main_matchups:
            _sleep()
            continue

        # 构建 fixture 信息 map: {matchup_id: {home, away, league, kickoff}}
        fixture_map = {}
        for m in main_matchups:
            mid  = m["id"]
            ts   = m.get("startTime", "")
            kick = ts[:19].replace("T", " ") if ts else ""
            parts = m.get("participants", [])
            home, away = "", ""
            for p in parts:
                if p.get("alignment") == "home":
                    home = p.get("name", "")
                elif p.get("alignment") in ("away", "visiting"):
                    away = p.get("name", "")
            fixture_map[mid] = {
                "league_name": league_name,
                "home_team": home,
                "away_team": away,
                "kickoff_utc": kick,
            }

        main_ids = list(fixture_map.keys())
        log.info(f"  {league_name}: {len(main_ids)} 场主赛事, 搜索角球关联...")

        # 2) 找 corner matchups
        corner_map = find_corner_matchups(main_ids)
        if not corner_map:
            log.info(f"    → 无角球市场")
            _sleep()
            continue

        log.info(f"    → 发现 {len(corner_map)} 个角球 matchup")

        # 3) 逐一抓取角球赔率
        league_rows = []
        for corner_mid, parent_mid in corner_map.items():
            fi = fixture_map.get(parent_mid, {})
            rows = fetch_corner_markets(corner_mid, parent_mid, fi, fetch_date)
            league_rows.extend(rows)
            _sleep()

        if league_rows and "pinnacle_corner_odds" in tables:
            batch_upsert(engine, tables["pinnacle_corner_odds"], league_rows,
                         unique_keys=["corner_matchup_id", "market_type", "period",
                                      "side", "team_side", "line", "fetch_date"])
            total_saved += len(league_rows)
            log.info(f"    → 写入 {len(league_rows)} 条角球赔率")

        _sleep()

    log.info(f"✅ 角球赔率全部完成: {total_saved} 条")
    return total_saved


# ─── 主流程 ───────────────────────────────────────────────────────────────────
def run(corners_only: bool = False):
    import argparse
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")

    if corners_only:
        log.info(f"⚽ Pinnacle 角球赔率抓取 [{fetch_date}]")
        fetch_all_corner_odds(fetch_date)
        return

    log.info(f"🌐 Pinnacle 全量数据抓取开始 [{fetch_date}]")

    for sport_code in ["football", "basketball"]:
        log.info(f"\n📊 运动: {sport_code}")
        leagues = fetch_leagues(sport_code)
        _sleep()

        for lg in leagues:
            league_id   = lg["id"]
            league_name = lg["name"]
            log.info(f"  联赛: {league_name} (id={league_id})")

            fetch_fixtures(league_id, league_name, sport_code, fetch_date)
            _sleep()

            fetch_odds_for_league(league_id, sport_code, fetch_date)
            _sleep()

    # 追加角球赔率
    log.info("\n⚽ 开始抓取角球赔率...")
    fetch_all_corner_odds(fetch_date)

    log.info("✅ Pinnacle 抓取完成")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--corners", action="store_true", help="只抓取角球赔率")
    args = parser.parse_args()
    run(corners_only=args.corners)
