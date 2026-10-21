# -*- coding: utf-8 -*-
# 28_livescore_basketball_scraper.py — LiveScore.com 篮球全量数据爬虫（反扒绕过）
#
# 数据来源: https://prod-public-api.livescore.com (免费公开 API)
#   ✅ 无需账号，无需 API Key
#   ✅ 覆盖 30+ 篮球联赛（NBA/EuroLeague/ACB/BBL/LNB/Legabasket/BSL/HEBA 等）
#   ✅ 含逐场四节比分，支持历史日期查询
#
# 反扒策略:
#   1. curl_cffi Chrome131/124/123 TLS 指纹随机轮换（JA3/JA4 绕过）
#   2. 真实 User-Agent 池（10+ 个现代 UA）
#   3. Referer 伪造（模拟 livescore.com 正常浏览）
#   4. 正态分布随机延迟（均值 1s，σ=0.4，模拟真人节奏）
#   5. 指数退避重试（429/403/503 自动轮换指纹 + 等待）
#
# 输出表:
#   ls_bball_games     — 比赛结果（主客队、总分、四节比分、状态）
#   ls_bball_leagues   — 联赛参考表（联赛名+国家）

import sys
import json
import logging
import argparse
from datetime import datetime, timedelta

from sqlalchemy import create_engine, MetaData

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl
from http_utils import StealthSession, random_sleep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

LS_BASE = "https://prod-public-api.livescore.com"

# 目标篮球联赛关键词过滤（空列表 = 全部）
# 含顶级欧洲联赛、NBA、WNBA、澳大利亚等
TARGET_LEAGUES = set()  # empty = fetch all


class _LSSession(StealthSession):
    def __init__(self):
        super().__init__(
            base_url="https://www.livescore.com",
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer":         "https://www.livescore.com/",
                "sec-fetch-site":  "same-site",
                "sec-fetch-mode":  "cors",
                "sec-fetch-dest":  "empty",
            },
        )

    def get_basketball_day(self, date_str: str) -> dict:
        url = f"{LS_BASE}/v1/api/app/date/basketball/{date_str}/5"
        r = self.get(url, params={"MD": 1}, headers={"Accept": "application/json"})
        if r is None:
            return {}
        try:
            return r.json()
        except Exception:
            return {}


_sess = _LSSession()


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS ls_bball_games (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id      TEXT,
            league_country TEXT,
            league_name   TEXT,
            stage_name    TEXT,
            home_team     TEXT,
            away_team     TEXT,
            home_team_id  TEXT,
            away_team_id  TEXT,
            kickoff_dt    TEXT,
            status        TEXT,
            home_score    INTEGER,
            away_score    INTEGER,
            home_q1       INTEGER,
            away_q1       INTEGER,
            home_q2       INTEGER,
            away_q2       INTEGER,
            home_q3       INTEGER,
            away_q3       INTEGER,
            home_q4       INTEGER,
            away_q4       INTEGER,
            fetch_date    TEXT,
            UNIQUE(event_id)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS ls_bball_leagues (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            league_country TEXT,
            league_name   TEXT,
            stage_name    TEXT,
            first_seen    TEXT,
            last_seen     TEXT,
            UNIQUE(league_country, league_name, stage_name)
        )
    """)
    log.info("LiveScore 篮球数据表初始化完成")


def _safe_int(v) -> int | None:
    try:
        return int(v) if v not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None


def fetch_day(date_str: str, fetch_date: str) -> int:
    """
    拉取指定日期所有篮球比赛。返回写入行数。
    date_str: YYYYMMDD 格式（如 20260604）
    """
    data = _sess.get_basketball_day(date_str)
    if not data:
        return 0

    stages = data.get("Stages", [])
    game_rows = []
    league_rows = []

    for stage in stages:
        country = stage.get("Cnm", "")
        league  = stage.get("Snm", "")
        stage_nm = stage.get("Scd", "") or ""

        league_rows.append({
            "league_country": country,
            "league_name":    league,
            "stage_name":     stage_nm,
            "first_seen":     fetch_date,
            "last_seen":      fetch_date,
        })

        for e in stage.get("Events", []):
            t1_list = e.get("T1", [{}])
            t2_list = e.get("T2", [{}])
            t1 = t1_list[0] if t1_list else {}
            t2 = t2_list[0] if t2_list else {}

            esd = str(e.get("Esd", ""))
            # Parse YYYYMMDDHHMMSS
            kickoff = None
            if len(esd) >= 8:
                try:
                    kickoff = datetime.strptime(esd[:14], "%Y%m%d%H%M%S").strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    kickoff = esd[:8]

            game_rows.append({
                "event_id":      str(e.get("Eid", "")),
                "league_country": country,
                "league_name":   league,
                "stage_name":    stage_nm,
                "home_team":     t1.get("Nm", ""),
                "away_team":     t2.get("Nm", ""),
                "home_team_id":  str(t1.get("ID", "")),
                "away_team_id":  str(t2.get("ID", "")),
                "kickoff_dt":    kickoff,
                "status":        e.get("Eps", ""),
                "home_score":    _safe_int(e.get("Tr1")),
                "away_score":    _safe_int(e.get("Tr2")),
                "home_q1":       _safe_int(e.get("Tr1Q1")),
                "away_q1":       _safe_int(e.get("Tr2Q1")),
                "home_q2":       _safe_int(e.get("Tr1Q2")),
                "away_q2":       _safe_int(e.get("Tr2Q2")),
                "home_q3":       _safe_int(e.get("Tr1Q3")),
                "away_q3":       _safe_int(e.get("Tr2Q3")),
                "home_q4":       _safe_int(e.get("Tr1Q4")),
                "away_q4":       _safe_int(e.get("Tr2Q4")),
                "fetch_date":    fetch_date,
            })

    md = MetaData()
    md.reflect(bind=engine)
    written = 0
    if game_rows:
        batch_upsert(engine, md.tables["ls_bball_games"], game_rows, ["event_id"])
        written = len(game_rows)
    if league_rows:
        batch_upsert(engine, md.tables["ls_bball_leagues"], league_rows,
                     ["league_country", "league_name", "stage_name"])
    return written


def run(fetch_date: str = None, lookback_days: int = 30) -> int:
    if not fetch_date:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    init_tables()
    log.info("=" * 60)
    log.info(f"LiveScore 篮球全量爬虫启动 [{fetch_date}]")
    log.info(f"  回溯天数: {lookback_days}")
    log.info(f"  TLS 指纹伪装: chrome131/124/123 随机轮换")
    log.info("=" * 60)

    total = 0
    base_dt = datetime.strptime(fetch_date, "%Y-%m-%d")

    for day_offset in range(lookback_days):
        target_dt = base_dt - timedelta(days=day_offset)
        date_str = target_dt.strftime("%Y%m%d")
        n = fetch_day(date_str, fetch_date)
        if n > 0:
            log.info(f"  {target_dt.strftime('%Y-%m-%d')}: {n} 场")
        total += n
        random_sleep(0.8, 0.3)

    log.info(f"\nLiveScore 完成: 共写入 {total} 场比赛")
    return total


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="LiveScore 篮球全量爬虫")
    p.add_argument("--date", default=None)
    p.add_argument("--days", type=int, default=30, help="回溯天数")
    args = p.parse_args()
    run(fetch_date=args.date, lookback_days=args.days)
