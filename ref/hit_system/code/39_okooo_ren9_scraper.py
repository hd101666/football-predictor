#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
澳客网(okooo) 传统足彩"任选九场"对阵表+赔率爬虫
=================================
数据源: m.okooo.com/zucai/ren9.php（当期14场任九对阵表，服务端直出HTML，无JSON API）
    页面每期固定14场比赛，是"胜负彩14场"和"任九"共用的同一份官方对阵表。

用法:
  python 39_okooo_ren9_scraper.py --date 2026-07-14
  python 39_okooo_ren9_scraper.py --lottery-no 26092   # 指定期号抓取
"""

import sys, os, re, time, sqlite3, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(_BASE_DIR, "data", "sports_data.db")
REN9_URL  = "https://m.okooo.com/zucai/ren9.php"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"),
    "Referer": "https://m.okooo.com/",
}


def _get_with_retry(url: str, params: dict, retries: int = 3, backoff: float = 5.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers=HEADERS, params=params, timeout=20)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                print(f"    [retry {attempt}/{retries}] 网络错误，等待{backoff * attempt:.0f}s: {e}")
                time.sleep(backoff * attempt)
    raise last_err


def fetch_ren9(lottery_no: str | None = None) -> dict:
    """抓取当期(或指定期号)任九对阵表，返回 {'lottery_no': str, 'matches': [...]}"""
    params = {}
    if lottery_no:
        params["LotteryNo"] = lottery_no

    resp = _get_with_retry(REN9_URL, params)
    resp.encoding = "gbk"
    soup = BeautifulSoup(resp.text, "html.parser")

    qihao_el = soup.select_one("p.qihaobox")
    lottery_no_found = ""
    if qihao_el:
        m = re.search(r"第(\d+)期", qihao_el.get_text())
        if m:
            lottery_no_found = m.group(1)

    matches = []
    for item in soup.select("div.listItem"):
        xuhao_el = item.select_one("p.zc_xuhao")
        if not xuhao_el:
            continue
        seq = xuhao_el.get_text(strip=True)

        league_el = item.select_one("a.liansai")
        league = league_el.get_text(strip=True) if league_el else ""

        date_el = item.select_one("p.xuhao")
        time_el = item.select_one("time.timetxt")
        match_date = date_el.get_text(strip=True) if date_el else ""
        match_time = time_el.get_text(strip=True) if time_el else ""

        link_el = item.select_one("a.datalink")
        match_id = ""
        if link_el and link_el.get("href"):
            m = re.search(r"MatchID=(\d+)", link_el["href"])
            if m:
                match_id = m.group(1)

        home_el = item.select_one("em.ctrl_homename")
        away_el = item.select_one("em.ctrl_awayname")
        home_team = home_el.get_text(strip=True) if home_el else ""
        away_team = away_el.get_text(strip=True) if away_el else ""

        # 排名前缀/后缀（如"[3]世"），主队cite在前，客队cite在后
        pm_cites = item.select("cite.pm")
        home_rank = pm_cites[0].get_text(strip=True) if len(pm_cites) > 0 else ""
        away_rank = pm_cites[1].get_text(strip=True) if len(pm_cites) > 1 else ""

        odds_home = odds_draw = odds_away = None
        for btn in item.select("div.ctrl_betopt"):
            txt_el = btn.select_one("p.ctrl_txt")
            if not txt_el:
                continue
            txt = txt_el.get_text(strip=True)
            m = re.match(r"(胜|平|负)\s*([\d.]+)", txt)
            if not m:
                continue
            label, val = m.group(1), m.group(2)
            try:
                val = float(val)
            except ValueError:
                continue
            if label == "胜":
                odds_home = val
            elif label == "平":
                odds_draw = val
            elif label == "负":
                odds_away = val

        if not (home_team and away_team):
            continue

        matches.append({
            "seq": seq,
            "match_id": match_id,
            "league": league,
            "match_date": match_date,
            "match_time": match_time,
            "home_team": home_team,
            "away_team": away_team,
            "home_rank": home_rank,
            "away_rank": away_rank,
            "odds_home": odds_home,
            "odds_draw": odds_draw,
            "odds_away": odds_away,
        })

    return {"lottery_no": lottery_no_found or (lottery_no or ""), "matches": matches}


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS okooo_ren9_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lottery_no TEXT NOT NULL,
        seq TEXT,
        match_id TEXT,
        league TEXT,
        match_date TEXT,
        match_time TEXT,
        home_team TEXT,
        away_team TEXT,
        home_rank TEXT,
        away_rank TEXT,
        odds_home REAL,
        odds_draw REAL,
        odds_away REAL,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(lottery_no, seq, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_okooo_ren9_lottery
        ON okooo_ren9_matches(lottery_no, fetch_date)""")
    # FIX-009-1（2026-09-14）：快照留存表。主表 okooo_ren9_matches 的
    # UNIQUE(lottery_no,seq,fetch_date) + ON CONFLICT DO UPDATE 会把同日重抓
    # 覆盖写且无痕迹（created_at 只在首次INSERT时打），26124期三次抓取被吞。
    # 本表每次抓取独立一批（batch_ts=本地时刻），只插不改，历史快照永不覆盖。
    conn.execute("""CREATE TABLE IF NOT EXISTS okooo_ren9_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lottery_no TEXT NOT NULL,
        seq TEXT,
        home_team TEXT,
        away_team TEXT,
        odds_home REAL,
        odds_draw REAL,
        odds_away REAL,
        fetch_date TEXT,
        batch_ts TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(lottery_no, seq, batch_ts)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_okooo_ren9_snap_lottery
        ON okooo_ren9_snapshots(lottery_no, batch_ts)""")


def run(fetch_date: str | None = None, lottery_no: str | None = None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    data = fetch_ren9(lottery_no)
    if not data["matches"]:
        print("  ERROR: 未解析到任何比赛，页面结构可能已变化")
        return 0

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_table(conn)

    n = 0
    for m in data["matches"]:
        try:
            conn.execute("""
                INSERT INTO okooo_ren9_matches
                    (lottery_no, seq, match_id, league, match_date, match_time,
                     home_team, away_team, home_rank, away_rank,
                     odds_home, odds_draw, odds_away, fetch_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(lottery_no, seq, fetch_date) DO UPDATE SET
                    match_id=excluded.match_id, league=excluded.league,
                    match_date=excluded.match_date, match_time=excluded.match_time,
                    home_team=excluded.home_team, away_team=excluded.away_team,
                    home_rank=excluded.home_rank, away_rank=excluded.away_rank,
                    odds_home=excluded.odds_home, odds_draw=excluded.odds_draw,
                    odds_away=excluded.odds_away
            """, (data["lottery_no"], m["seq"], m["match_id"], m["league"],
                  m["match_date"], m["match_time"], m["home_team"], m["away_team"],
                  m["home_rank"], m["away_rank"],
                  m["odds_home"], m["odds_draw"], m["odds_away"], fetch_date))
            n += 1
        except sqlite3.Error as e:
            print(f"  写入失败 [{m['seq']}] {m['home_team']} vs {m['away_team']}: {e}")

    # FIX-009-1：主表 upsert 之后，整批追加一份不可变快照（每次抓取独立批次）。
    # 快照写失败只告警不吞——这是留痕功能本身，静默失败等于没修。
    batch_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snap_n = 0
    snap_err = 0
    for m in data["matches"]:
        try:
            conn.execute("""
                INSERT INTO okooo_ren9_snapshots
                    (lottery_no, seq, home_team, away_team,
                     odds_home, odds_draw, odds_away, fetch_date, batch_ts)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(lottery_no, seq, batch_ts) DO NOTHING
            """, (data["lottery_no"], m["seq"], m["home_team"], m["away_team"],
                  m["odds_home"], m["odds_draw"], m["odds_away"], fetch_date, batch_ts))
            snap_n += 1
        except sqlite3.Error as e:
            snap_err += 1
            print(f"  ⚠️ 快照写入失败 [{m['seq']}]: {e}")

    conn.commit()
    conn.close()

    print(f"  任九第{data['lottery_no']}期: {n}/{len(data['matches'])} 场写入"
          f"（快照批次 {batch_ts}: {snap_n} 场" + (f"，失败{snap_err}）" if snap_err else "）"))
    for m in data["matches"]:
        print(f"    [{m['seq']}] {m['match_date']} {m['match_time']} {m['league']} "
              f"{m['home_team']} vs {m['away_team']}  胜{m['odds_home']}/平{m['odds_draw']}/负{m['odds_away']}")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", dest="date_str", default=None, help="fetch_date，默认今日")
    ap.add_argument("--lottery-no", dest="lottery_no", default=None, help="指定期号，默认当期")
    args = ap.parse_args()
    run(fetch_date=args.date_str, lottery_no=args.lottery_no)
