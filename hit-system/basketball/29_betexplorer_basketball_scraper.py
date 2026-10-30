# -*- coding: utf-8 -*-
# 29_betexplorer_basketball_scraper.py — BetExplorer 欧洲篮球赔率爬虫（反扒绕过）
#
# 数据来源: https://www.betexplorer.com/basketball/
#   ✅ 免费公开页面，无需账号，HTML + JSON AJAX 逆向
#   覆盖: EuroLeague / EuroCup / ACB / BBL / LNB / Legabasket / BSL / HEBA 等
#
# 反扒策略:
#   1. curl_cffi Chrome131/124/123 TLS 指纹随机切换（JA3/JA4 绕过）
#   2. 真实 User-Agent 池（10+ 个现代 UA）
#   3. Referer / Origin / X-Requested-With 伪造（模拟 XHR 请求）
#   4. 首页热身 Cookie（访问 betexplorer.com 首页建立会话）
#   5. 指数退避重试（429/403/503 自动轮换指纹 + 等待）
#   6. 正态分布随机延迟（均值 2s，σ=0.7，模拟真人节奏）
#   7. 逆向 AJAX 接口：/getMatchList?sport=2&type=&id=&stage= (篮球 sport_id=2)
#
# 输出表:
#   be_bball_matches   — 比赛列表（主客队、比分、时间）
#   be_bball_odds      — 多庄赔率（独赢/让分/大小球），含开盘/收盘/最高/最低

import sys
import re
import json
import time
import random
import logging
import argparse
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, MetaData

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import batch_upsert, exec_ddl
from http_utils import StealthSession, random_sleep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

BASE = "https://www.betexplorer.com"

# ─── BetExplorer 欧洲篮球联赛路径 ──────────────────────────────────────────────
# 格式: (url_path, league_code, league_name)
BE_BASKETBALL_LEAGUES = [
    ("/basketball/europe/euroleague/",          "euroleague",      "EuroLeague"),
    ("/basketball/europe/eurocup/",             "eurocup",         "EuroCup"),
    ("/basketball/europe/aba-league/",          "aba_league",      "Adriatic - ABA League"),
    ("/basketball/spain/acb-liga-endesa/",      "acb",             "Spain - ACB"),
    ("/basketball/germany/bbl/",                "bbl",             "Germany - BBL"),
    ("/basketball/france/pro-a/",               "lnb",             "France - LNB Pro A"),
    ("/basketball/italy/lega-basket-serie-a/",  "legabasket",      "Italy - Legabasket"),
    ("/basketball/turkey/super-league/",        "turkey_sl",       "Turkey - BSL"),
    ("/basketball/greece/basket-league/",       "greece_bl",       "Greece - HEBA A1"),
    ("/basketball/russia/vtb-united-league/",   "vtb",             "Russia - VTB United"),
    ("/basketball/poland/basket-liga/",         "poland_bl",       "Poland - PLK"),
    ("/basketball/lithuania/lkl/",              "lkl",             "Lithuania - LKL"),
    ("/basketball/israel/premier-league/",      "israel_pl",       "Israel - Premier League"),
    ("/basketball/serbia/aba-league-2/",        "aba2",            "Serbia - ABA League 2"),
    ("/basketball/czech-republic/nbl/",         "czech_nbl",       "Czech Republic - NBL"),
    ("/basketball/croatia/hba-premijer-liga/",  "croatia_pl",      "Croatia - HBA Premijer Liga"),
    ("/basketball/finland/korisliiga/",         "finland_kl",      "Finland - Korisliiga"),
    ("/basketball/hungary/nemzeti-bajnoksag/",  "hungary_nb",      "Hungary - Nemzeti Bajnokság"),
    ("/basketball/romania/liga-nationala/",     "romania_ln",      "Romania - Liga Națională"),
    ("/basketball/slovenia/liga-nova-kbm/",     "slovenia_lnk",    "Slovenia - Liga Nova KBM"),
    ("/basketball/ukraine/superleague/",        "ukraine_sl",      "Ukraine - Superleague"),
    ("/basketball/portugal/lpb/",               "portugal_lpb",    "Portugal - LPB"),
    ("/basketball/slovakia/sbl/",               "slovakia_sbl",    "Slovakia - SBL"),
    ("/basketball/china/cba/",                  "cba",             "China - CBA"),
    ("/basketball/australia/nbl/",              "australia_nbl",   "Australia - NBL"),
]


# ─── BetExplorer 专用会话 ───────────────────────────────────────────────────────
class _BESession(StealthSession):
    def __init__(self):
        super().__init__(
            base_url=BASE,
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Referer":         BASE + "/",
                "DNT":             "1",
                "Sec-GPC":         "1",
            },
        )

    def get_html(self, url: str, retries: int = 4) -> Optional[str]:
        r = self.get(url, retries=retries, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        return r.text if r is not None else None

    def get_json(self, url: str, params: dict = None) -> Optional[dict]:
        r = self.get(url, headers={
            "Accept":           "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }, params=params)
        if r is None:
            return None
        try:
            return r.json()
        except Exception:
            return None


_sess = _BESession()


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS be_bball_matches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        TEXT,
            league_code     TEXT,
            league_name     TEXT,
            season          TEXT,
            home_team       TEXT,
            away_team       TEXT,
            kickoff_utc     TEXT,
            home_score      INTEGER,
            away_score      INTEGER,
            home_score_ht   INTEGER,
            away_score_ht   INTEGER,
            status          TEXT,
            fetch_date      TEXT,
            UNIQUE(match_id)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS be_bball_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id    TEXT,
            market      TEXT,
            bookmaker   TEXT,
            outcome     TEXT,
            odds_open   REAL,
            odds_close  REAL,
            odds_max    REAL,
            odds_min    REAL,
            handicap    REAL,
            fetch_date  TEXT,
            UNIQUE(match_id, market, bookmaker, outcome)
        )
    """)
    log.info("BetExplorer 篮球数据表初始化完成")


# ─── HTML 解析工具 ────────────────────────────────────────────────────────────
def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _parse_score(text: str):
    m = re.match(r"(\d+)[:\-–](\d+)", (text or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _extract_match_id(href: str) -> str | None:
    m = re.search(r"/([a-zA-Z0-9]{6,16})/?(?:#[a-z0-9]+)?$", href or "")
    return m.group(1) if m else None


# ─── 1. 联赛比赛列表 ──────────────────────────────────────────────────────────
def fetch_league_matches(path: str, league_code: str, league_name: str,
                          fetch_date: str, pages: int = 3) -> list:
    """
    抓取联赛结果页，返回 match_id 列表。
    BetExplorer 结果页分页通过 ?offset=0,20,40 实现。
    """
    match_ids = []
    rows = []

    # 获取当前赛季 slug
    main_html = _sess.get_html(f"{BASE}{path}results/")
    if not main_html:
        log.warning(f"  无法访问: {path}")
        return match_ids
    soup = _soup(main_html)

    # 获取当前赛季
    season_el = (soup.select_one("select#selSeason option[selected]")
                 or soup.select_one("h2.main-filter__filter span"))
    season = season_el.get_text(strip=True) if season_el else "current"

    all_match_links = []
    for offset_idx in range(pages):
        offset = offset_idx * 25
        if offset == 0:
            page_html = main_html
        else:
            page_html = _sess.get_html(f"{BASE}{path}results/?offset={offset}")
        if not page_html:
            break
        page_soup = _soup(page_html)
        # BetExplorer uses <a class="in-match" data-test="{id}"> for each game row
        links = page_soup.find_all("a", class_="in-match")
        if not links:
            break
        all_match_links.extend(links)
        random_sleep(1.5, 0.5)

    odds_rows = []
    for link_el in all_match_links:
        try:
            # match_id from data-test attribute (numeric), fallback to href slug
            mid = link_el.get("data-test") or _extract_match_id(link_el.get("href", ""))
            if not mid:
                continue

            # Home team = first span text, away team = second span text
            spans = link_el.find_all("span", recursive=False)
            home_team = spans[0].get_text(strip=True) if len(spans) > 0 else ""
            away_team = spans[1].get_text(strip=True) if len(spans) > 1 else ""

            # Parent row for score and date
            row = link_el.find_parent("tr")
            if not row:
                continue
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Score in td[1] (class h-text-center)
            score_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            h_score, a_score = _parse_score(score_text)

            # Date in last td (class h-text-right h-text-no-wrap)
            kickoff = cells[-1].get_text(strip=True) if cells else ""

            rows.append({
                "match_id":    mid,
                "league_code": league_code,
                "league_name": league_name,
                "season":      season,
                "home_team":   home_team,
                "away_team":   away_team,
                "kickoff_utc": kickoff,
                "home_score":  h_score,
                "away_score":  a_score,
                "home_score_ht": None,
                "away_score_ht": None,
                "status":      "finished" if h_score is not None else "scheduled",
                "fetch_date":  fetch_date,
            })
            match_ids.append(mid)

            # Extract inline closing odds from results table (td[2]=home, td[3]=away)
            # td[2]: <span data-odd="X.XX"> or data-odd on td itself
            if len(cells) >= 4:
                def _get_inline_odd(td):
                    span = td.find("span", attrs={"data-odd": True})
                    if span:
                        return _safe_float(span.get("data-odd"))
                    return _safe_float(td.get("data-odd"))

                home_odd = _get_inline_odd(cells[2])
                away_odd = _get_inline_odd(cells[3]) if len(cells) > 3 else None
                if home_odd:
                    odds_rows.append({
                        "match_id": mid, "market": "ml", "bookmaker": "betexplorer_avg",
                        "outcome": "home", "odds_open": None, "odds_close": home_odd,
                        "odds_max": None, "odds_min": None, "handicap": None,
                        "fetch_date": fetch_date,
                    })
                if away_odd:
                    odds_rows.append({
                        "match_id": mid, "market": "ml", "bookmaker": "betexplorer_avg",
                        "outcome": "away", "odds_open": None, "odds_close": away_odd,
                        "odds_max": None, "odds_min": None, "handicap": None,
                        "fetch_date": fetch_date,
                    })
        except Exception as e:
            log.debug(f"  解析行失败: {e}")

    md = MetaData(); md.reflect(bind=engine)
    if rows:
        batch_upsert(engine, md.tables["be_bball_matches"], rows, ["match_id"])
    if odds_rows:
        batch_upsert(engine, md.tables["be_bball_odds"], odds_rows,
                     ["match_id", "market", "bookmaker", "outcome"])
    log.info(f"  {league_name}: {len(rows)} 场, {len(odds_rows)} 条赔率")
    return match_ids


# ─── 2. 逐场赔率（BetExplorer AJAX 接口逆向） ────────────────────────────────
def fetch_match_odds(match_id: str, fetch_date: str) -> int:
    """
    逆向 BetExplorer AJAX 赔率接口：
      GET /getOdds/?id={match_id}&type=1x2    (独赢 1x2)
      GET /getOdds/?id={match_id}&type=ah     (亚盘让分)
      GET /getOdds/?id={match_id}&type=ou     (大小球)
    response: {"d": [{n: bookmaker, o_1: odds_1, o_X: odds_draw, o_2: odds_2, ...}]}
    """
    MARKET_TYPES = [
        ("1x2", {"o_1": "home", "o_X": "draw", "o_2": "away"}),
        ("ah",  {"o_1": "home", "o_2": "away"}),
        ("ou",  {"o_1": "over", "o_2": "under"}),
    ]
    rows = []
    for market_type, outcome_map in MARKET_TYPES:
        data = _sess.get_json(f"{BASE}/getOdds/",
                              params={"id": match_id, "type": market_type, "xbet": 1})
        if not data:
            continue
        for bk in data.get("d", data.get("bets", [])):
            bk_name = bk.get("n", bk.get("name", ""))
            for field, outcome_label in outcome_map.items():
                open_val  = _safe_float(bk.get(f"{field}_o") or bk.get(f"{field}_open"))
                close_val = _safe_float(bk.get(field))
                max_val   = _safe_float(bk.get(f"{field}_max"))
                min_val   = _safe_float(bk.get(f"{field}_min"))
                if close_val is None and open_val is None:
                    continue
                rows.append({
                    "match_id":  match_id,
                    "market":    market_type,
                    "bookmaker": bk_name,
                    "outcome":   outcome_label,
                    "odds_open": open_val,
                    "odds_close": close_val,
                    "odds_max":  max_val,
                    "odds_min":  min_val,
                    "handicap":  _safe_float(bk.get("ah") or bk.get("handicap") or bk.get("add")),
                    "fetch_date": fetch_date,
                })
        random_sleep(0.4, 0.15)

    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["be_bball_odds"], rows,
                 ["match_id", "market", "bookmaker", "outcome"])
    return len(rows)


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─── 主入口 ─────────────────────────────────────────────────────────────────────
def run(fetch_date: str = None) -> int:
    if not fetch_date:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    init_tables()
    log.info("=" * 60)
    log.info(f"BetExplorer 欧洲篮球赔率爬虫启动 [{fetch_date}]")
    log.info(f"  TLS 指纹伪装: chrome131/124/123 随机轮换")
    log.info(f"  覆盖联赛: {len(BE_BASKETBALL_LEAGUES)} 个")
    log.info("=" * 60)

    total_matches = 0

    for path, code, name in BE_BASKETBALL_LEAGUES:
        log.info(f"\n📊 {name}")
        mids = fetch_league_matches(path, code, name, fetch_date, pages=2)
        total_matches += len(mids)
        random_sleep(2.5, 0.8)

    log.info(f"\nBetExplorer 完成: {total_matches} 场比赛")
    return total_matches


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="BetExplorer 欧洲篮球赔率爬虫")
    p.add_argument("--date", default=None)
    args = p.parse_args()
    run(fetch_date=args.date)
