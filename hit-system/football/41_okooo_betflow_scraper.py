#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
澳客网(okooo) "必发盈亏"(球路走势/资金流向) 爬虫
=================================
数据源: www.okooo.com/jingcai/shuju/betfa/dqjc/（当期竞彩足球比赛必发指数+资金流向）
    每场比赛3行(主胜/平局/客胜)，含总成交额/冷热指数/市场指数/必发赔率&比例/
    99家平均赔率&比例/模拟盈亏，是庄家资金流向类信号，不同于普通赔率快照。
    页面只保留近期未开赛/刚开赛的比赛，无历史归档，需按天定期抓取积累。

用法:
  python 41_okooo_betflow_scraper.py --date 2026-07-14
"""

import sys, os, re, time, sqlite3, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
BETFA_URL  = "https://www.okooo.com/jingcai/shuju/betfa/dqjc/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_OPTION_MAP = {"主胜": "home", "平局": "draw", "客胜": "away"}


def _get_with_retry(url: str, retries: int = 3, backoff: float = 5.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                print(f"    [retry {attempt}/{retries}] 网络错误，等待{backoff * attempt:.0f}s: {e}")
                time.sleep(backoff * attempt)
    raise last_err


def fetch_betflow(fetch_date: str) -> list:
    resp = _get_with_retry(BETFA_URL)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    rows_out = []
    for block in soup.select("div.betfa"):
        title_p = block.select_one("p.float_l")
        title_bs = title_p.find_all("b") if title_p else []
        league = title_bs[1].get_text(strip=True) if len(title_bs) > 1 else ""
        match_time = title_bs[2].get_text(strip=True) if len(title_bs) > 2 else ""

        name_box = block.select_one("div.titnamebox")
        home_team = away_team = ""
        if name_box:
            spans = name_box.find_all("span", recursive=False)
            bs = name_box.find_all("b", recursive=False)
            home_team = spans[0].get_text(strip=True) if spans else ""
            away_team = bs[-1].get_text(strip=True) if bs else ""

        link_el = block.select_one("p.float_r a")
        match_id = ""
        if link_el and link_el.get("href"):
            m = re.search(r"/match/(\d+)/", link_el["href"])
            if m:
                match_id = m.group(1)
        if not match_id:
            continue

        table = block.select_one("table#table")
        if not table:
            continue
        for tr in table.select("tr"):
            if tr.select_one("th"):
                continue
            tds = tr.find_all("td")
            if len(tds) < 14:
                continue
            option_cn = tds[0].get_text(strip=True)
            outcome = _OPTION_MAP.get(option_cn, option_cn)

            def _num(el):
                t = el.get_text(strip=True).replace("%", "")
                if not t:
                    return None
                try:
                    return float(t)
                except ValueError:
                    return None

            rows_out.append({
                "match_id": match_id, "league": league, "match_time": match_time,
                "home_team": home_team, "away_team": away_team,
                "outcome": outcome,
                "turnover": _num(tds[5]),
                "hot_cold_index": _num(tds[6]),
                "market_index": _num(tds[7]),
                "betfair_odds": _num(tds[8]),
                "betfair_pct": _num(tds[9]),
                "avg99_odds": _num(tds[10]),
                "avg99_pct": _num(tds[11]),
                "jingcai_pct": _num(tds[12]),
                "sim_pnl": _num(tds[13]),
                "fetch_date": fetch_date,
                "fetch_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            })

    return rows_out


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS okooo_bet_flow (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        league TEXT,
        match_time TEXT,
        home_team TEXT,
        away_team TEXT,
        outcome TEXT,
        turnover REAL,
        hot_cold_index REAL,
        market_index REAL,
        betfair_odds REAL,
        betfair_pct REAL,
        avg99_odds REAL,
        avg99_pct REAL,
        jingcai_pct REAL,
        sim_pnl REAL,
        fetch_date TEXT,
        fetch_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_okooo_betflow_match
        ON okooo_bet_flow(match_id, fetch_date)""")


def run(fetch_date: str | None = None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    rows = fetch_betflow(fetch_date)
    if not rows:
        print("  ERROR: 未解析到任何球路走势数据，页面结构可能已变化")
        return 0

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_table(conn)

    n = 0
    for r in rows:
        try:
            conn.execute("""
                INSERT INTO okooo_bet_flow
                    (match_id, league, match_time, home_team, away_team, outcome,
                     turnover, hot_cold_index, market_index, betfair_odds, betfair_pct,
                     avg99_odds, avg99_pct, jingcai_pct, sim_pnl, fetch_date, fetch_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (r["match_id"], r["league"], r["match_time"], r["home_team"], r["away_team"],
                  r["outcome"], r["turnover"], r["hot_cold_index"], r["market_index"],
                  r["betfair_odds"], r["betfair_pct"], r["avg99_odds"], r["avg99_pct"],
                  r["jingcai_pct"], r["sim_pnl"], r["fetch_date"], r["fetch_at"]))
            n += 1
        except sqlite3.Error as e:
            print(f"  写入失败 [{r['match_id']}] {r['outcome']}: {e}")

    conn.commit()
    conn.close()

    matches = len({r["match_id"] for r in rows})
    print(f"  球路走势: {matches} 场比赛，{n} 行(每场胜/平/负各1行)写入")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", dest="date_str", default=None, help="fetch_date，默认今日")
    args = ap.parse_args()
    run(fetch_date=args.date_str)
