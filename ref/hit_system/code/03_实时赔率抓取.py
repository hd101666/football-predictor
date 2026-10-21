# 03_实时赔率抓取.py — 使用 sportsbook-api2（套利）+ odds-feed（1X2实时盘口）
import requests
import pandas as pd
import time
import json
from sqlalchemy import create_engine
from db_utils import exec_ddl
from config import (
    DB_ENGINE_URL, DB_DIR, SPORTSBOOK_BASE, ODDS_FEED_BASE,
    rapidapi_headers,
)

engine = create_engine(DB_ENGINE_URL)


def init_odds_tables():
    sqls = [
        """CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport VARCHAR(50),
            league VARCHAR(100),
            home_team VARCHAR(100),
            away_team VARCHAR(100),
            bookmaker_home VARCHAR(100),
            bookmaker_away VARCHAR(100),
            odds_home FLOAT,
            odds_away FLOAT,
            arb_profit_pct FLOAT,
            fetch_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS live_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id VARCHAR(50),
            home_team VARCHAR(100),
            away_team VARCHAR(100),
            market_name VARCHAR(50),
            outcome VARCHAR(20),
            odds FLOAT,
            bookmaker VARCHAR(100),
            period VARCHAR(50),
            placing VARCHAR(20),
            fetch_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS basketball_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league VARCHAR(50),
            match_date VARCHAR(50),
            home_team VARCHAR(100),
            away_team VARCHAR(100),
            home_odds FLOAT,
            away_odds FLOAT,
            over_odds FLOAT,
            under_odds FLOAT,
            arb_profit_pct FLOAT,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
    ]
    for sql in sqls:
        exec_ddl(engine, sql)
    print("✅ 赔率表初始化完成")


def fetch_arbitrage() -> pd.DataFrame:
    """从 sportsbook-api2 获取套利机会"""
    headers = rapidapi_headers("sportsbook-api2.p.rapidapi.com")
    rows = []
    try:
        res = requests.get(
            f"{SPORTSBOOK_BASE}/v0/advantages/",
            headers=headers,
            params={"type": "ARBITRAGE"},
            timeout=20,
        )
        if res.status_code == 200:
            body = res.json()
            items = body if isinstance(body, list) else body.get("data", body.get("results", []))
            for item in (items if isinstance(items, list) else []):
                try:
                    outcomes = item.get("outcomes", item.get("selections", []))
                    if len(outcomes) >= 2:
                        rows.append({
                            "sport":           item.get("sport", item.get("sport_key", "")),
                            "league":          item.get("league", item.get("competition", "")),
                            "home_team":       item.get("home_team", outcomes[0].get("name", "")),
                            "away_team":       item.get("away_team", outcomes[1].get("name", "")),
                            "bookmaker_home":  outcomes[0].get("bookmaker", ""),
                            "bookmaker_away":  outcomes[1].get("bookmaker", ""),
                            "odds_home":       float(outcomes[0].get("odds", outcomes[0].get("price", 0))),
                            "odds_away":       float(outcomes[1].get("odds", outcomes[1].get("price", 0))),
                            "arb_profit_pct":  float(item.get("profit_percentage", item.get("profit", 0))),
                        })
                except Exception:
                    continue
        elif res.status_code == 429:
            print("  API 限流，等待 10 秒...")
            time.sleep(10)
        else:
            print(f"  sportsbook-api2 状态码 {res.status_code}: {res.text[:200]}")
    except Exception as e:
        print(f"  套利数据请求异常: {e}")
    return pd.DataFrame(rows)


def _get_today_event_ids() -> str:
    """从 API-Sports 查询今日足球赛事，返回逗号分隔的 fixture id 字符串"""
    from config import APISPORTS_HEADERS, FOOTBALL_API_BASE
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        res = requests.get(
            f"{FOOTBALL_API_BASE}/fixtures",
            headers=APISPORTS_HEADERS,
            params={"date": today, "status": "LIVE"},
            timeout=15,
        )
        if res.status_code == 200:
            ids = [str(f["fixture"]["id"]) for f in res.json().get("response", [])]
            return ",".join(ids[:50]) if ids else ""
    except Exception:
        pass
    return ""


def fetch_live_odds_feed() -> pd.DataFrame:
    """从 odds-feed 获取实时 1X2 市场（event_ids 为必填，先从 API-Sports 查今日直播赛事）"""
    event_ids = _get_today_event_ids()
    if not event_ids:
        print("  odds-feed: 当前无进行中赛事，跳过")
        return pd.DataFrame()

    headers = rapidapi_headers("odds-feed.p.rapidapi.com")
    rows = []
    try:
        res = requests.get(
            f"{ODDS_FEED_BASE}/api/v1/markets/feed",
            headers=headers,
            params={
                "placing":     "LIVE",
                "market_name": "1X2",
                "bet_type":    "BACK",
                "page":        "0",
                "period":      "FULL_TIME_AND_OT",
                "event_ids":   event_ids,
            },
            timeout=20,
        )
        if res.status_code == 200:
            body = res.json()
            markets = body if isinstance(body, list) else body.get("markets", body.get("data", []))
            for mkt in (markets if isinstance(markets, list) else []):
                try:
                    event = mkt.get("event", {})
                    for sel in mkt.get("selections", mkt.get("outcomes", [])):
                        rows.append({
                            "event_id":    str(event.get("id", mkt.get("event_id", ""))),
                            "home_team":   event.get("home_team", ""),
                            "away_team":   event.get("away_team", ""),
                            "market_name": mkt.get("market_name", "1X2"),
                            "outcome":     sel.get("name", sel.get("outcome", "")),
                            "odds":        float(sel.get("price", sel.get("odds", 0))),
                            "bookmaker":   sel.get("bookmaker", mkt.get("bookmaker", "")),
                            "period":      mkt.get("period", "FULL_TIME"),
                            "placing":     mkt.get("placing", "LIVE"),
                        })
                except Exception:
                    continue
        else:
            print(f"  odds-feed 状态码 {res.status_code}: {res.text[:200]}")
    except Exception as e:
        print(f"  实时赔率请求异常: {e}")
    return pd.DataFrame(rows)


def merge_to_basketball_odds(df_arb: pd.DataFrame) -> pd.DataFrame:
    """将套利数据转换为 basketball_odds 格式（足球+篮球通用）"""
    if df_arb.empty:
        return pd.DataFrame()
    rows = []
    for _, r in df_arb.iterrows():
        rows.append({
            "league":          r.get("league", ""),
            "match_date":      "",
            "home_team":       r.get("home_team", ""),
            "away_team":       r.get("away_team", ""),
            "home_odds":       r.get("odds_home"),
            "away_odds":       r.get("odds_away"),
            "over_odds":       None,
            "under_odds":      None,
            "arb_profit_pct":  r.get("arb_profit_pct"),
        })
    return pd.DataFrame(rows)


def run_all():
    """命中系统调度入口：初始化表 + 抓套利 + 抓实时赔率"""
    init_odds_tables()

    df_arb = fetch_arbitrage()
    if not df_arb.empty:
        df_arb.to_sql("arbitrage_opportunities", engine, if_exists="append", index=False, chunksize=200)
        df_odds = merge_to_basketball_odds(df_arb)
        if not df_odds.empty:
            df_odds.to_sql("basketball_odds", engine, if_exists="append", index=False, chunksize=200)

    df_live = fetch_live_odds_feed()
    if not df_live.empty:
        df_live.to_sql("live_odds", engine, if_exists="append", index=False, chunksize=200)


if __name__ == "__main__":
    init_odds_tables()

    print("📡 正在获取套利机会...")
    df_arb = fetch_arbitrage()
    if not df_arb.empty:
        df_arb.to_sql("arbitrage_opportunities", engine, if_exists="append", index=False, chunksize=200)
        df_odds = merge_to_basketball_odds(df_arb)
        if not df_odds.empty:
            df_odds.to_sql("basketball_odds", engine, if_exists="append", index=False, chunksize=200)
        xlsx = rf"{DB_DIR}\arbitrage_latest.xlsx"
        df_arb.to_excel(xlsx, index=False)
        print(f"✅ 套利机会 {len(df_arb)} 条入库，导出 → {xlsx}")
    else:
        print("⚠️ 暂无套利数据")

    print("📡 正在获取实时 1X2 赔率...")
    df_live = fetch_live_odds_feed()
    if not df_live.empty:
        df_live.to_sql("live_odds", engine, if_exists="append", index=False, chunksize=200)
        xlsx2 = rf"{DB_DIR}\live_odds_latest.xlsx"
        df_live.to_excel(xlsx2, index=False)
        print(f"✅ 实时赔率 {len(df_live)} 条入库，导出 → {xlsx2}")
    else:
        print("⚠️ 暂无实时赔率数据（可能非实时营业时间）")

    print("\n✅ 赔率抓取完成")
