#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
澳客网(okooo) 伤停信息爬虫
=================================
数据源: www.okooo.com/jingcai/shuju/injured/dqjc/（当期竞彩足球比赛主客队伤停名单）
    是独立于赔率的球队级真实信号（球员/位置/出场数据/是否缺阵/原因），
    符合CLAUDE.md"推荐单数据支撑规则"对独立模型信号的要求。

用法:
  python 40_okooo_injury_scraper.py --date 2026-07-14
"""

import sys, os, re, time, sqlite3, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
INJURY_URL = "https://www.okooo.com/jingcai/shuju/injured/dqjc/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _parse_team_injuries(box, match_id: str, side: str, team: str, fetch_date: str) -> list:
    """解析单侧(主/客)伤停表格，返回行列表；无伤停/暂无数据返回空列表"""
    rows = []
    table_div = box.select_one("div.injuredTable")
    if not table_div:
        return rows
    for tr in table_div.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        player_a = tds[2].select_one("a")
        player_name = player_a.get_text(strip=True) if player_a else tds[2].get_text(strip=True)
        player_id = ""
        if player_a and player_a.get("href"):
            m = re.search(r"/player/(\d+)/", player_a["href"])
            if m:
                player_id = m.group(1)
        rows.append({
            "match_id": match_id, "side": side, "team": team,
            "number": tds[0].get_text(strip=True),
            "position": tds[1].get_text(strip=True),
            "player_name": player_name, "player_id": player_id,
            "appearances": tds[3].get_text(strip=True),
            "minutes": tds[4].get_text(strip=True),
            "goals": tds[5].get_text(strip=True),
            "assists": tds[6].get_text(strip=True),
            "will_miss": tds[7].get_text(strip=True),
            "reason": tds[8].get_text(strip=True),
            "fetch_date": fetch_date,
        })
    return rows


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


def fetch_injuries(fetch_date: str) -> list:
    resp = _get_with_retry(INJURY_URL)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    all_rows = []
    for block in soup.select("div.injuredData"):
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
        boxes = block.select("div.injuredBox")
        if len(boxes) >= 1:
            all_rows.extend(_parse_team_injuries(boxes[0], match_id, "home", home_team, fetch_date))
        if len(boxes) >= 2:
            all_rows.extend(_parse_team_injuries(boxes[1], match_id, "away", away_team, fetch_date))

    return all_rows


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS okooo_injuries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        side TEXT,
        team TEXT,
        number TEXT,
        position TEXT,
        player_name TEXT,
        player_id TEXT,
        appearances TEXT,
        minutes TEXT,
        goals TEXT,
        assists TEXT,
        will_miss TEXT,
        reason TEXT,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_id, side, player_id, player_name, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_okooo_injuries_match
        ON okooo_injuries(match_id, fetch_date)""")


def run(fetch_date: str | None = None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    rows = fetch_injuries(fetch_date)
    if not rows:
        print("  ERROR: 未解析到任何伤停数据，页面结构可能已变化")
        return 0

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_table(conn)

    n = 0
    matches_seen = set()
    players_seen = 0
    for r in rows:
        matches_seen.add(r["match_id"])
        if r["player_name"]:
            players_seen += 1
        try:
            conn.execute("""
                INSERT INTO okooo_injuries
                    (match_id, side, team, number, position, player_name, player_id,
                     appearances, minutes, goals, assists, will_miss, reason, fetch_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id, side, player_id, player_name, fetch_date) DO UPDATE SET
                    team=excluded.team, number=excluded.number, position=excluded.position,
                    appearances=excluded.appearances, minutes=excluded.minutes,
                    goals=excluded.goals, assists=excluded.assists,
                    will_miss=excluded.will_miss, reason=excluded.reason
            """, (r["match_id"], r["side"], r["team"], r["number"], r["position"],
                  r["player_name"], r["player_id"], r["appearances"], r["minutes"],
                  r["goals"], r["assists"], r["will_miss"], r["reason"], r["fetch_date"]))
            n += 1
        except sqlite3.Error as e:
            print(f"  写入失败 [{r['match_id']}] {r.get('player_name')}: {e}")

    conn.commit()
    conn.close()

    print(f"  伤停数据: {len(matches_seen)} 场比赛，{players_seen} 名球员记录写入 ({n} 行)")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", dest="date_str", default=None, help="fetch_date，默认今日")
    args = ap.parse_args()
    run(fetch_date=args.date_str)
