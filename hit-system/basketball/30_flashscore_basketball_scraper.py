# -*- coding: utf-8 -*-
# 30_flashscore_basketball_scraper.py — FlashScore 欧洲篮球全量数据爬虫（反扒绕过）
#
# 数据来源: Flashscore 篮球频道（全量欧洲联赛，含实时赔率快照）
#   ✅ 免费公开，无需账号
#   ✅ 复用已有 X-Fsign 管道协议逆向（同 08_flashscore_scraper.py）
#   ✅ 补充: SofaScore API 篮球扩展 + ACB 官方 API（acb.com）
#
# 反扒策略:
#   1. curl_cffi Chrome131 TLS 指纹（Cloudflare 绕过）
#   2. X-Fsign: SW9D1eZo（Flashscore JS 内置静态 Token，必须字段）
#   3. d.flashscore.com 管道协议：¬ 字段分隔，÷ 键值分隔
#   4. 首页热身 Cookie（flashscore.com → Cloudflare 5s 验证）
#   5. 正态分布随机延迟（均值 2s，σ=0.8）
#   6. SofaScore API: sec-fetch-* 头伪造，完整 CORS 头组
#   7. ACB 官方 API: JSON 直接请求，标准浏览器头
#
# 输出表:
#   fs_bball_matches   — Flashscore 篮球比赛赛程与结果（全欧联赛）
#   fs_bball_odds      — Flashscore 赔率快照（各庄开盘/实时）
#   sofa_bball_matches — SofaScore 篮球赛程（扩展欧洲联赛覆盖）
#   sofa_bball_stats   — SofaScore 场均统计

import sys
import re
import json
import time
import random
import logging
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import create_engine, MetaData
from sqlalchemy import text as _sa_text

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import batch_upsert, exec_ddl
from http_utils import StealthSession, random_sleep, DEFAULT_USER_AGENTS
from leagues import FLASHSCORE_BASKETBALL_LEAGUES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

# ─── Flashscore 常量 ──────────────────────────────────────────────────────────
FLASH_HOST   = "https://www.flashscore.com"
FLASH_FEED   = "https://d.flashscore.com/x/feed"
FLASH_MOBILE = "https://m.flashscore.com"

# X-Fsign：Flashscore JS 内置静态 Token（必须，否则 403）
X_FSIGN = "SW9D1eZo"

# 管道协议分隔符
SEP_MAIN = "\xac"   # ¬  U+00AC
SEP_KV   = "\xf7"   # ÷  U+00F7

# SofaScore
SOFA_BASE = "https://api.sofascore.com/api/v1"
SOFA_ORIGIN = "https://www.sofascore.com"

# ─── SofaScore 篮球联赛 tournament_id（覆盖 Flashscore 未收录的） ─────────────
SOFA_BASKETBALL_TOURNAMENTS = {
    132:  "nba",
    695:  "cba",
    685:  "euroleague",
    686:  "eurocup",
    200:  "acb",
    399:  "bbl",
    398:  "lnb",
    400:  "legabasket",
    396:  "turkey_sl",
    397:  "greece_bl",
    401:  "vtb",
    402:  "lkl",
    403:  "israel_pl",
    404:  "aba_league",
    405:  "polish_bl",
    406:  "czech_nbl",
    150:  "wnba",
    229:  "australia_nbl",
}


# ─── Flashscore 会话 ──────────────────────────────────────────────────────────
class _FlashSession(StealthSession):
    """Flashscore 专用会话：X-Fsign 静态 Token + Cloudflare bypass"""

    def __init__(self):
        super().__init__(
            base_url=FLASH_HOST,
            headers={
                "Accept":          "text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer":         FLASH_HOST + "/",
                "X-Fsign":         X_FSIGN,
                "Origin":          FLASH_HOST,
                "sec-fetch-site":  "same-site",
                "sec-fetch-mode":  "cors",
                "sec-fetch-dest":  "empty",
            },
            impersonates=["chrome131", "chrome124", "chrome123", "chrome116"],
        )

    def get_feed(self, params: dict) -> Optional[str]:
        r = self.get(FLASH_FEED, params=params, headers={
            "Accept": "text/plain, */*",
            "X-Fsign": X_FSIGN,
        })
        return r.text if r is not None else None


_flash = _FlashSession()


# ─── SofaScore 会话 ───────────────────────────────────────────────────────────
class _SofaSession(StealthSession):
    def __init__(self):
        super().__init__(
            base_url=SOFA_ORIGIN,
            headers={
                "Referer":          SOFA_ORIGIN + "/",
                "Origin":           SOFA_ORIGIN,
                "Accept":           "application/json, text/plain, */*",
                "Accept-Language":  "en-US,en;q=0.9",
                "sec-fetch-site":   "same-site",
                "sec-fetch-mode":   "cors",
                "sec-fetch-dest":   "empty",
                "sec-ch-ua":        '"Google Chrome";v="131", "Chromium";v="131"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
            impersonates=["chrome131", "chrome124"],
        )

    def api_get(self, path: str) -> Optional[dict]:
        r = self.get(f"{SOFA_BASE}/{path.lstrip('/')}")
        if r is None:
            return None
        try:
            return r.json()
        except Exception:
            return None


_sofa = _SofaSession()


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS fs_bball_matches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            flash_id        TEXT,
            league_code     TEXT,
            league_path     TEXT,
            home_team       TEXT,
            away_team       TEXT,
            kickoff_utc     TEXT,
            status          TEXT,
            home_score      INTEGER,
            away_score      INTEGER,
            home_score_ht   INTEGER,
            away_score_ht   INTEGER,
            home_score_q1   INTEGER,
            home_score_q2   INTEGER,
            home_score_q3   INTEGER,
            home_score_q4   INTEGER,
            away_score_q1   INTEGER,
            away_score_q2   INTEGER,
            away_score_q3   INTEGER,
            away_score_q4   INTEGER,
            fetch_date      TEXT,
            UNIQUE(flash_id)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS fs_bball_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            flash_id    TEXT,
            bookmaker   TEXT,
            market      TEXT,
            outcome     TEXT,
            odds_open   REAL,
            odds_live   REAL,
            handicap    REAL,
            fetch_date  TEXT,
            UNIQUE(flash_id, bookmaker, market, outcome)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS sofa_bball_matches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        INTEGER,
            tournament_id   INTEGER,
            league_code     TEXT,
            home_team       TEXT,
            away_team       TEXT,
            start_timestamp INTEGER,
            home_score      INTEGER,
            away_score      INTEGER,
            status          TEXT,
            round_info      TEXT,
            fetch_date      TEXT,
            UNIQUE(event_id)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS sofa_bball_stats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        INTEGER,
            team_side       TEXT,
            team_name       TEXT,
            stat_key        TEXT,
            stat_value      TEXT,
            fetch_date      TEXT,
            UNIQUE(event_id, team_side, stat_key)
        )
    """)
    # 断点续跑记录：这个爬虫历史上多次1800s超时被杀（SofaScore阶段18个联赛几乎全被
    # 403/TLS拦截、重试轮换指纹耗时巨大，实测完整跑完需1542s+），没有这张表时每次
    # 重跑都从Flashscore第一个联赛重新开始。stage区分三个阶段各自的进度
    # ('flash_league'/'flash_odds'/'sofa_tournament')，key存对应的联赛代码/flash_id。
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS fs_bball_scrape_log (
            stage TEXT, key TEXT, fetch_date TEXT, scraped_at TEXT,
            UNIQUE(stage, key, fetch_date)
        )
    """)
    log.info("Flashscore + SofaScore 篮球数据表初始化完成")


def _load_done(stage: str, fetch_date: str) -> set:
    try:
        with engine.connect() as conn:
            rows = conn.execute(_sa_text(
                "SELECT key FROM fs_bball_scrape_log WHERE stage=:s AND fetch_date=:fd"
            ), {"s": stage, "fd": fetch_date}).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _mark_done(stage: str, key: str, fetch_date: str):
    try:
        with engine.begin() as conn:
            conn.execute(_sa_text("""
                INSERT OR IGNORE INTO fs_bball_scrape_log (stage, key, fetch_date, scraped_at)
                VALUES (:s, :k, :fd, :now)
            """), {"s": stage, "k": key, "fd": fetch_date,
                    "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception:
        pass


# ─── Flashscore 管道协议解析 ──────────────────────────────────────────────────
def _parse_pipe(text: str) -> list[dict]:
    """解析 Flashscore ¬ 管道协议为字典列表"""
    records = []
    for block in text.strip().split("÷ZA÷"):
        kv = {}
        for part in block.split(SEP_MAIN):
            if SEP_KV in part:
                k, _, v = part.partition(SEP_KV)
                kv[k.strip()] = v.strip()
        if kv:
            records.append(kv)
    return records


def _safe_int(v) -> int | None:
    try:
        return int(v) if v not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None

def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─── Flashscore 管道数据从 HTML 提取 ─────────────────────────────────────────
def _parse_embedded_flash(html: str) -> list:
    """从 Flashscore HTML 提取内嵌管道格式比赛数据（与 08_flashscore_scraper 一致）"""
    idx = html.find("AA÷")
    if idx < 0:
        return []
    end = len(html)
    for marker in ["</script>", "</div>", "</body>"]:
        pos = html.find(marker, idx)
        if idx < pos < end:
            end = pos
    data_block = html[idx:end]
    results = []
    for rec in data_block.split("~"):
        if "AA÷" not in rec or "CX÷" not in rec:
            continue
        fields = {}
        for part in rec.split("¬"):
            if "÷" in part:
                k, _, v = part.partition("÷")
                if k:
                    fields[k] = v
        if "AA" in fields and "CX" in fields:
            results.append(fields)
    return results


# ─── Flashscore 比赛列表（HTML 内嵌管道协议） ─────────────────────────────────
def flash_fetch_league(path: str, league_code: str, fetch_date: str) -> list:
    """
    拉取联赛结果，直接解析 Flashscore HTML 内嵌管道数据。
    path: 如 /basketball/spain/acb/
    """
    match_ids = []
    rows = []

    _flash.warm_up("/basketball/")

    for suffix in ["results/", "fixtures/"]:
        url = f"{FLASH_HOST}{path}{suffix}"
        r = _flash.get(url, headers={"Accept": "text/html,application/xhtml+xml,*/*"})
        if r is None:
            continue

        for kv in _parse_embedded_flash(r.text):
            mid = kv.get("AA", "")
            if not mid:
                continue
            home = kv.get("CX", "")
            away = kv.get("AF", "")
            ts   = kv.get("AD", "")

            kickoff_utc = ""
            if ts:
                try:
                    from datetime import timezone
                    kickoff_utc = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    kickoff_utc = ts

            status_map = {"0": "NS", "1": "1H", "2": "HT", "3": "FT",
                          "31": "AET", "41": "Pen", "-1": "Canc", "-2": "Post"}
            status = status_map.get(kv.get("AB", ""), kv.get("AB", ""))

            rows.append({
                "flash_id":    mid,
                "league_code": league_code,
                "league_path": path,
                "home_team":   home,
                "away_team":   away,
                "kickoff_utc": kickoff_utc,
                "status":      status,
                "home_score":  _safe_int(kv.get("AG")),
                "away_score":  _safe_int(kv.get("AH")),
                "home_score_ht": None,
                "away_score_ht": None,
                # Basketball quarter scores: BA/BC/BE/BG = home Q1-Q4, BB/BD/BF/BH = away Q1-Q4
                "home_score_q1": _safe_int(kv.get("BA")),
                "home_score_q2": _safe_int(kv.get("BC")),
                "home_score_q3": _safe_int(kv.get("BE")),
                "home_score_q4": _safe_int(kv.get("BG")),
                "away_score_q1": _safe_int(kv.get("BB")),
                "away_score_q2": _safe_int(kv.get("BD")),
                "away_score_q3": _safe_int(kv.get("BF")),
                "away_score_q4": _safe_int(kv.get("BH")),
                "fetch_date":  fetch_date,
            })
            match_ids.append(mid)
        random_sleep(1.5, 0.5)

    if rows:
        md = MetaData(); md.reflect(bind=engine)
        batch_upsert(engine, md.tables["fs_bball_matches"], rows, ["flash_id"])

    log.info(f"  Flashscore {league_code}: {len(rows)} 场")
    return match_ids




# ─── Flashscore 赔率快照 ──────────────────────────────────────────────────────
def flash_fetch_odds(flash_id: str, fetch_date: str) -> int:
    """拉取单场 Flashscore 赔率快照（通过 /x/feed 接口）"""
    params = {"p": "2", "id": flash_id, "v": "1"}
    text = _flash.get_feed(params)
    if not text:
        return 0
    rows = []
    for kv in _parse_pipe(text):
        bk   = kv.get("XA", kv.get("BC", ""))
        odds1 = _safe_float(kv.get("XI") or kv.get("XB"))
        oddsX = _safe_float(kv.get("XJ") or kv.get("XC"))
        odds2 = _safe_float(kv.get("XK") or kv.get("XD"))
        hcp   = _safe_float(kv.get("XL") or kv.get("XE"))
        if not bk or (odds1 is None and odds2 is None):
            continue
        for outcome, val in [("home", odds1), ("draw", oddsX), ("away", odds2)]:
            if val is None:
                continue
            rows.append({
                "flash_id":  flash_id,
                "bookmaker": bk,
                "market":    "1x2",
                "outcome":   outcome,
                "odds_open": val,
                "odds_live": _safe_float(kv.get(f"X{outcome[0].upper()}l")),
                "handicap":  hcp,
                "fetch_date": fetch_date,
            })
    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["fs_bball_odds"], rows,
                 ["flash_id", "bookmaker", "market", "outcome"])
    return len(rows)


# ─── SofaScore 篮球扩展 ───────────────────────────────────────────────────────
def sofa_fetch_tournament(tournament_id: int, league_code: str, fetch_date: str) -> int:
    """拉取 SofaScore 某联赛最近赛程"""
    # 获取联赛最新赛季 ID
    data = _sofa.api_get(f"tournament/{tournament_id}/seasons")
    if not data:
        return 0
    seasons = data.get("seasons", [])
    if not seasons:
        return 0
    season_id = seasons[0].get("id")
    if not season_id:
        return 0

    rows = []
    for page in range(6):   # 最多 6 页
        data2 = _sofa.api_get(f"tournament/{tournament_id}/season/{season_id}/events/last/{page}")
        if not data2:
            break
        events = data2.get("events", [])
        if not events:
            break
        for ev in events:
            home = ev.get("homeTeam", {})
            away = ev.get("awayTeam", {})
            hs   = ev.get("homeScore", {})
            as_  = ev.get("awayScore", {})
            status = ev.get("status", {})
            rd = ev.get("roundInfo", {})
            rows.append({
                "event_id":      ev.get("id"),
                "tournament_id": tournament_id,
                "league_code":   league_code,
                "home_team":     home.get("name", ""),
                "away_team":     away.get("name", ""),
                "start_timestamp": ev.get("startTimestamp"),
                "home_score":    hs.get("current"),
                "away_score":    as_.get("current"),
                "status":        status.get("description", ""),
                "round_info":    str(rd.get("round", "") or rd.get("name", "")),
                "fetch_date":    fetch_date,
            })
        random_sleep(0.8, 0.3)
        if not data2.get("hasNextPage", True):
            break

    if not rows:
        return 0
    md = MetaData(); md.reflect(bind=engine)
    batch_upsert(engine, md.tables["sofa_bball_matches"], rows, ["event_id"])

    # 顺手拉取最近 20 场的统计
    stats_count = sofa_fetch_stats_batch(rows[:20], fetch_date)
    log.info(f"  SofaScore {league_code}: {len(rows)} 场  {stats_count} 条统计")
    return len(rows)


def sofa_fetch_stats_batch(events: list[dict], fetch_date: str) -> int:
    """批量拉取 SofaScore 技术统计"""
    total = 0
    md = MetaData(); md.reflect(bind=engine)
    tbl = md.tables["sofa_bball_stats"]
    for ev in events:
        eid = ev.get("event_id")
        if not eid:
            continue
        data = _sofa.api_get(f"event/{eid}/statistics")
        if not data:
            continue
        rows = []
        for grp in data.get("statistics", []):
            for stat in grp.get("groups", []):
                for item in stat.get("statisticsItems", []):
                    key = item.get("key", item.get("name", ""))
                    for side, val_key in [("home", "home"), ("away", "away")]:
                        val = item.get(val_key)
                        if val is None:
                            continue
                        rows.append({
                            "event_id":  eid,
                            "team_side": side,
                            "team_name": ev.get(f"{side}_team", ""),
                            "stat_key":  key,
                            "stat_value": str(val),
                            "fetch_date": fetch_date,
                        })
        if rows:
            batch_upsert(engine, tbl, rows, ["event_id", "team_side", "stat_key"])
            total += len(rows)
        random_sleep(0.5, 0.2)
    return total


# ─── 主入口 ─────────────────────────────────────────────────────────────────────
def run(fetch_date: str = None, resume: bool = True) -> int:
    if not fetch_date:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    init_tables()
    log.info("=" * 60)
    log.info(f"Flashscore + SofaScore 欧洲篮球全量爬虫启动 [{fetch_date}]")
    log.info(f"  Flashscore 联赛: {len(FLASHSCORE_BASKETBALL_LEAGUES)} 个")
    log.info(f"  SofaScore 联赛: {len(SOFA_BASKETBALL_TOURNAMENTS)} 个")
    log.info(f"  反扒: curl_cffi Chrome131/124 + X-Fsign + Cookie 热身")
    log.info("=" * 60)

    total = 0
    all_flash_ids = []

    done_league = _load_done("flash_league", fetch_date) if resume else set()
    done_odds   = _load_done("flash_odds", fetch_date) if resume else set()
    done_sofa   = _load_done("sofa_tournament", fetch_date) if resume else set()
    if done_league or done_odds or done_sofa:
        log.info(f"  断点续跑: 联赛跳过{len(done_league)} / 赔率跳过{len(done_odds)} / SofaScore跳过{len(done_sofa)}")

    # ── 阶段 1: Flashscore 全联赛赛程 ──
    log.info("\n📡 Flashscore 模块")
    for path, league_code in FLASHSCORE_BASKETBALL_LEAGUES.items():
        if league_code in done_league:
            continue
        log.info(f"\n  📊 {league_code} ({path})")
        mids = flash_fetch_league(path, league_code, fetch_date)
        all_flash_ids.extend(mids)
        total += len(mids)
        _mark_done("flash_league", league_code, fetch_date)
        random_sleep(2.0, 0.8)

    # Bug修复：断点续跑跳过已完成联赛时，那些联赛的match_id不会进入本次运行的
    # all_flash_ids(只在内存里，跨进程不保留)，导致阶段2漏抓这部分比赛的赔率。
    # 跳过联赛存在时，从数据库把今天已入库的flash_id也补进来，保证阶段2覆盖全量。
    if done_league:
        try:
            with engine.connect() as conn:
                rows = conn.execute(_sa_text(
                    "SELECT DISTINCT flash_id FROM fs_bball_matches WHERE fetch_date=:fd"
                ), {"fd": fetch_date}).fetchall()
            existing = {r[0] for r in rows} - set(all_flash_ids)
            all_flash_ids.extend(existing)
        except Exception:
            pass

    # ── 阶段 2: Flashscore 赔率（今日赛事，最多 60 场）──
    log.info(f"\n📡 Flashscore 赔率快照（{min(len(all_flash_ids), 60)} 场）")
    odds_count = 0
    for fid in all_flash_ids[:60]:
        if fid in done_odds:
            continue
        odds_count += flash_fetch_odds(fid, fetch_date)
        _mark_done("flash_odds", fid, fetch_date)
        random_sleep(0.5, 0.2)
    log.info(f"  赔率: {odds_count} 条")
    total += odds_count

    # ── 阶段 3: SofaScore 篮球扩展 ──
    log.info("\n📡 SofaScore 模块")
    for tid, code in SOFA_BASKETBALL_TOURNAMENTS.items():
        if code in done_sofa:
            continue
        log.info(f"\n  📊 {code} (tournament_id={tid})")
        cnt = sofa_fetch_tournament(tid, code, fetch_date)
        total += cnt
        _mark_done("sofa_tournament", code, fetch_date)
        random_sleep(1.5, 0.5)

    log.info(f"\nFlashscore + SofaScore 完成: 共写入 {total} 条数据")
    return total


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Flashscore + SofaScore 欧洲篮球全量爬虫")
    p.add_argument("--date", default=None)
    p.add_argument("--no-resume", action="store_true", help="忽略断点续跑记录，全部重新抓取")
    args = p.parse_args()
    run(fetch_date=args.date, resume=not args.no_resume)
