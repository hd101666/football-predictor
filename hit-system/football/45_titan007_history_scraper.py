#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
titan007(球探体育) 历史赛果+盘口(让球/大小球)爬虫 —— 竞彩回测数据源
=================================
数据源: bf.titan007.com/football/Over_{YYYYMMDD}.htm
    每天一页，含当天全部已结束比赛: 联赛/时间/主队/全场比分/半场比分/客队/
    收盘让球盘(hdp)/收盘大小球盘(ou)/比赛ID(用于日后按需拉取欧赔历史)。
    这是竞彩胜平负/让球/大小球回测所需的真实盘口线来源(不是奖池分摊制，
    是传统固定赔率玩法，需要真实盘口/赔率而不只是赛果)。

已验证覆盖范围: 2016-01-01 至今连续可用；2014-12下旬~2015-02-11 也有零星数据，
    但2015-02-12~2015-12-31存在缺口(该期间大量返回404占位页，原因未知，
    不影响主体范围)。默认从2016-01-01开始抓取。

用法:
  python -X utf8 45_titan007_history_scraper.py --start-date 2016-01-01 --end-date 2026-07-26
  python -X utf8 45_titan007_history_scraper.py --date 2024-01-01   # 单日测试
"""

import sys, os, re, time, sqlite3, argparse
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "data", "sports_data.db")
BASE_URL = "https://bf.titan007.com/football/Over_{date}.htm"

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_with_retry(url, retries=4, backoff=3.0, timeout=20):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last_err


_RANK_RE = re.compile(r'\[([^\]]*)\]')
_ID_RE = re.compile(r"analysis\((\d+)\)")


def _parse_score(td):
    fonts = td.find_all("font")
    if len(fonts) < 2:
        return None, None
    try:
        return int(fonts[0].get_text(strip=True)), int(fonts[1].get_text(strip=True))
    except ValueError:
        return None, None


def fetch_date(date_str: str):
    """抓取单日全部已结束比赛，返回 list[dict] 或 None(该日无数据/404)"""
    url = BASE_URL.format(date=date_str.replace("-", ""))
    resp = _get_with_retry(url)
    if resp.status_code == 404:
        return None
    resp.encoding = "gb2312"
    text = resp.text
    if "error_404" in text or len(text) < 2000:
        return None

    soup = BeautifulSoup(text, "html.parser")
    table = soup.find(id="table_live")
    if table is None:
        return None

    matches = []
    for tr in table.find_all("tr"):
        tr_id = tr.get("id", "")
        if not tr_id.startswith("tr1_"):
            continue
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue

        league = tds[0].get_text(strip=True)
        match_time = tds[1].get_text(strip=True)

        # 主队栏可能含黄牌图片，用 get_text 提取纯文本，再用 [] 剔除排名
        home_raw = tds[3].get_text(strip=True)
        home_team = _RANK_RE.sub("", home_raw).strip()

        home_score, away_score = _parse_score(tds[4])

        away_raw = tds[5].get_text(strip=True)
        away_team = _RANK_RE.sub("", away_raw).strip()

        ht_home, ht_away = _parse_score(tds[6])

        hdp_td = tds[7]
        hdp_val = hdp_td.get("val")
        hdp_label = hdp_td.get_text(strip=True)

        ou_td = tds[8]
        ou_val = ou_td.get("val")
        ou_label = ou_td.get_text(strip=True)

        # 比赛ID: 优先取 sId 属性，否则从最后一列 onclick='analysis(ID)' 提取
        match_id = tr.get("sId") or tr.get("sid")
        if not match_id:
            last_html = str(tds[-1])
            idm = _ID_RE.search(last_html)
            match_id = idm.group(1) if idm else None

        if not (home_team and away_team) or home_score is None:
            continue

        matches.append({
            "match_id": match_id,
            "league": league,
            "match_time": match_time,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "ht_home_score": ht_home,
            "ht_away_score": ht_away,
            "handicap_line": hdp_val,
            "handicap_label": hdp_label,
            "total_line": ou_val,
            "total_label": ou_label,
        })

    return matches


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS titan007_match_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_date TEXT NOT NULL,
        match_id TEXT,
        league TEXT,
        match_time TEXT,
        home_team TEXT,
        away_team TEXT,
        home_score INTEGER,
        away_score INTEGER,
        ht_home_score INTEGER,
        ht_away_score INTEGER,
        handicap_line TEXT,
        handicap_label TEXT,
        total_line TEXT,
        total_label TEXT,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_date, match_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_titan007_match_date ON titan007_match_history(match_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_titan007_teams ON titan007_match_history(home_team, away_team)")
    conn.commit()


def save_date(conn, date_str, matches, fetch_date):
    for m in matches:
        conn.execute("""
            INSERT OR REPLACE INTO titan007_match_history
                (match_date, match_id, league, match_time, home_team, away_team,
                 home_score, away_score, ht_home_score, ht_away_score,
                 handicap_line, handicap_label, total_line, total_label, fetch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_str, m["match_id"], m["league"], m["match_time"], m["home_team"], m["away_team"],
              m["home_score"], m["away_score"], m["ht_home_score"], m["ht_away_score"],
              m["handicap_line"], m["handicap_label"], m["total_line"], m["total_label"], fetch_date))
    conn.commit()


def run(start_date: str, end_date: str, delay: float = 0.8, resume: bool = True):
    run_fetch_date = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_table(conn)

    done_dates = set()
    if resume:
        done_dates = {r[0] for r in conn.execute("SELECT DISTINCT match_date FROM titan007_match_history")}
        if done_dates:
            print(f"  断点续传: 已有 {len(done_dates)} 天数据，将跳过重复抓取")

    d0 = datetime.strptime(start_date, "%Y-%m-%d")
    d1 = datetime.strptime(end_date, "%Y-%m-%d")
    cur = d0
    total_days = 0
    total_matches = 0
    empty_days = 0
    while cur <= d1:
        ds = cur.strftime("%Y-%m-%d")

        if ds in done_dates:
            total_days += 1
            cur += timedelta(days=1)
            continue

        try:
            matches = fetch_date(ds)
        except Exception as e:
            print(f"  [{ds}] 请求异常，跳过: {e}")
            matches = None

        if matches:
            save_date(conn, ds, matches, run_fetch_date)
            total_days += 1
            total_matches += len(matches)
        else:
            empty_days += 1

        if (total_days + empty_days) % 60 == 0:
            print(f"  进度: {ds}  已抓{total_days}天/{total_matches}场，空白{empty_days}天")

        cur += timedelta(days=1)
        time.sleep(delay)

    print(f"\n=== 完成: {total_days}天有数据, 共{total_matches}场比赛, {empty_days}天无数据 ===")
    conn.close()
    return total_days


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", type=str, default="2016-01-01")
    ap.add_argument("--end-date", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--date", type=str, default=None, help="单日测试")
    ap.add_argument("--delay", type=float, default=0.8)
    args = ap.parse_args()

    if args.date:
        ms = fetch_date(args.date)
        if not ms:
            print("该日无数据")
        else:
            print(f"共 {len(ms)} 场比赛")
            for m in ms[:20]:
                print(f"  [{m['match_id']}] {m['league']} {m['match_time']} "
                      f"{m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']} "
                      f"(半场{m['ht_home_score']}-{m['ht_away_score']}) "
                      f"让球={m['handicap_label']}({m['handicap_line']}) 大小球={m['total_label']}({m['total_line']})")
    else:
        run(args.start_date, args.end_date, args.delay)
