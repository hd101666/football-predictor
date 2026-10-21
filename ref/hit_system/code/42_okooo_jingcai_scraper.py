#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
澳客网(okooo) 竞彩足球/篮球对阵+赔率爬虫（sporttery.cn 限流时的备份源）
=================================
数据源:
  足球: www.okooo.com/jingcai/ （胜平负 + 让球胜平负，服务端直出HTML）
  篮球: m.okooo.com/jclq/     （让分胜负 + 大小分，服务端直出HTML）
    注: 足球比分/大小球/半全场、篮球胜负(不让分)/胜分差 不在这两个默认页面内，
    暂未实现，目前只覆盖两边最常用的核心市场(独赢/让球，spread/total)，
    用途是 sporttery_source.py 被限流/失败时的备份，不是完整替代。

用法:
  python 42_okooo_jingcai_scraper.py --date 2026-07-14
"""

import sys, os, re, time, sqlite3, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(_BASE_DIR, "data", "sports_data.db")
FOOTBALL_URL = "https://www.okooo.com/jingcai/"
BASKETBALL_URL = "https://m.okooo.com/jclq/"

DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MOBILE_UA  = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def _get_with_retry(url: str, ua: str, retries: int = 3, backoff: float = 5.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers={"User-Agent": ua}, timeout=20)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                print(f"    [retry {attempt}/{retries}] 网络错误，等待{backoff * attempt:.0f}s: {e}")
                time.sleep(backoff * attempt)
    raise last_err


def fetch_football(fetch_date: str) -> list:
    # 2026-08-05修复：原来固定请求裸 FOOTBALL_URL(/jingcai/)，那是站点"当前滚动窗口"
    # 页面，混杂了已结束的前一批和刚开的下一批，跟fetch_date对不上号，导致每天只
    # 抓到个位数场次(实测22天239条，覆盖率严重偏低)。okooo支持按日期路径
    # /jingcai/{date}/，实测该URL返回的场次跟当天竞彩官方开出的场次完全一致(逐场
    # 赔率核对吻合)，改用它才能抓到当天完整批次。篮球端(m.okooo.com/jclq/)不支持
    # 该日期路径(实测404)，是站点本身限制，保持原样。
    url = f"{FOOTBALL_URL}{fetch_date}/"
    resp = _get_with_retry(url, DESKTOP_UA)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for m in soup.select("div.touzhu_1"):
        if m.get("data-end") == "1":
            continue  # 已结束/已截止，跳过

        match_id = m.get("data-mid", "")
        if not match_id:
            continue

        league_el = m.select_one("a.saiming")
        league = league_el.get("title") or (league_el.get_text(strip=True) if league_el else "")

        time_el = m.select_one("div.shijian")
        kickoff = ""
        if time_el and time_el.get("title"):
            mt = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", time_el["title"])
            if mt:
                kickoff = mt.group(1)

        # 2026-07-29修复：data-hname/data-aname属性是2字符截断缩写("库普"/"沙巴")，
        # 队名匹配到其他数据源时几乎全部失败。页面上div.zhum(队名显示div)每场
        # 比赛出现4次，前2个是完整队名("库普斯"/"沙巴巴库")，后2个是跟属性
        # 一样的截断重复渲染——取前2个。
        zhums = m.select("div.zhum")
        home_team = zhums[0].get_text(strip=True) if len(zhums) > 0 else m.get("data-hname", "")
        away_team = zhums[1].get_text(strip=True) if len(zhums) > 1 else m.get("data-aname", "")

        # 胜平负: class="shenpf" 区块内 zhu/ping/fu 三个 peilv
        spf_box = m.select_one("div.shenpf")
        odds_home = odds_draw = odds_away = None
        if spf_box:
            zhu = spf_box.select_one("div.zhu .peilv")
            ping = spf_box.select_one("div.ping .peilv")
            fu = spf_box.select_one("div.fu .peilv")
            odds_home = _to_float(zhu.get_text(strip=True)) if zhu else None
            odds_draw = _to_float(ping.get_text(strip=True)) if ping else None
            odds_away = _to_float(fu.get_text(strip=True)) if fu else None

        # 让球胜平负: class="rangqiuspf" 区块，让球数在 span.rangqiu
        ah_box = m.select_one("div.rangqiuspf")
        ah_home = ah_draw = ah_away = ah_line = None
        if ah_box:
            zhu = ah_box.select_one("div.zhu .peilv")
            ping = ah_box.select_one("div.ping .peilv")
            fu = ah_box.select_one("div.fu .peilv")
            rq = ah_box.select_one("span.rangqiu")
            ah_home = _to_float(zhu.get_text(strip=True)) if zhu else None
            ah_draw = _to_float(ping.get_text(strip=True)) if ping else None
            ah_away = _to_float(fu.get_text(strip=True)) if fu else None
            ah_line = _to_float(rq.get_text(strip=True)) if rq else None

        rows.append({
            "match_id": match_id, "league": league, "kickoff": kickoff,
            "home_team": home_team, "away_team": away_team,
            "odds_1x2_home": odds_home, "odds_1x2_draw": odds_draw, "odds_1x2_away": odds_away,
            "ah_line": ah_line, "odds_ah_home": ah_home, "odds_ah_draw": ah_draw, "odds_ah_away": ah_away,
            "fetch_date": fetch_date,
        })

    return rows


def fetch_basketball(fetch_date: str) -> list:
    resp = _get_with_retry(BASKETBALL_URL, MOBILE_UA)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for m in soup.select("div.ctrl_eachmatch"):
        if m.get("end") == "1":
            continue  # 已结束

        match_id_a = m.select_one("a.xuhao")
        match_id = ""
        if match_id_a and match_id_a.get("href"):
            mm = re.search(r"MatchID=(\d+)", match_id_a["href"])
            if mm:
                match_id = mm.group(1)
        if not match_id:
            continue

        league_el = m.select_one("a.liansai")
        league = league_el.get_text(strip=True) if league_el else ""
        time_el = m.select_one("a.timetxt")
        kickoff_time = time_el.get_text(strip=True) if time_el else ""

        home_el = m.select_one("em.ctrl_homename")
        away_el = m.select_one("em.ctrl_awayname")
        home_team = home_el.get_text(strip=True) if home_el else ""
        away_team = away_el.get_text(strip=True) if away_el else ""

        spread_line = spread_home = spread_away = None
        total_line = total_over = total_under = None
        for betway_box in m.select("div.ctrl_betway_wrap"):
            special = betway_box.select_one("div.ctrl_special")
            if not special:
                continue
            dtype = special.get("data-type", "")
            val = _to_float(special.get_text(strip=True))
            opts = betway_box.select("div.ctrl_betopt")
            if dtype == "rangfen":
                spread_line = val
                for opt in opts:
                    txt_el = opt.select_one("p.ctrl_txt")
                    odds_el = opt.select_one("p.ctrl_odds")
                    if not (txt_el and odds_el):
                        continue
                    txt = txt_el.get_text(strip=True)
                    odds_v = _to_float(odds_el.get_text(strip=True))
                    if txt == "主胜":
                        spread_home = odds_v
                    elif txt == "客胜":
                        spread_away = odds_v
            elif dtype == "daxiaofen":
                total_line = val
                for opt in opts:
                    txt_el = opt.select_one("p.ctrl_txt")
                    odds_el = opt.select_one("p.ctrl_odds")
                    if not (txt_el and odds_el):
                        continue
                    txt = txt_el.get_text(strip=True)
                    odds_v = _to_float(odds_el.get_text(strip=True))
                    if txt == "大分":
                        total_over = odds_v
                    elif txt == "小分":
                        total_under = odds_v

        rows.append({
            "match_id": match_id, "league": league, "kickoff_time": kickoff_time,
            "home_team": home_team, "away_team": away_team,
            "spread_line": spread_line, "odds_spread_home": spread_home, "odds_spread_away": spread_away,
            "total_line": total_line, "odds_over": total_over, "odds_under": total_under,
            "fetch_date": fetch_date,
        })

    return rows


def _to_float(s: str):
    s = (s or "").strip()
    if not s or s in ("-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def init_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS okooo_football_odds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        league TEXT,
        kickoff TEXT,
        home_team TEXT,
        away_team TEXT,
        odds_1x2_home REAL, odds_1x2_draw REAL, odds_1x2_away REAL,
        ah_line REAL, odds_ah_home REAL, odds_ah_draw REAL, odds_ah_away REAL,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_id, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_okooo_fb_odds_match
        ON okooo_football_odds(match_id, fetch_date)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS okooo_basketball_odds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        league TEXT,
        kickoff_time TEXT,
        home_team TEXT,
        away_team TEXT,
        spread_line REAL, odds_spread_home REAL, odds_spread_away REAL,
        total_line REAL, odds_over REAL, odds_under REAL,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_id, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_okooo_bb_odds_match
        ON okooo_basketball_odds(match_id, fetch_date)""")


def _upsert(conn, table, cols, row, fetch_date):
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("match_id", "fetch_date"))
    conn.execute(f"""
        INSERT INTO {table} ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(match_id, fetch_date) DO UPDATE SET {updates}
    """, tuple(row.get(c) for c in cols))


def run(fetch_date: str | None = None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_tables(conn)

    total = 0

    fb_rows = fetch_football(fetch_date)
    fb_cols = ["match_id", "league", "kickoff", "home_team", "away_team",
               "odds_1x2_home", "odds_1x2_draw", "odds_1x2_away",
               "ah_line", "odds_ah_home", "odds_ah_draw", "odds_ah_away", "fetch_date"]
    for r in fb_rows:
        try:
            _upsert(conn, "okooo_football_odds", fb_cols, r, fetch_date)
            total += 1
        except sqlite3.Error as e:
            print(f"  足球写入失败 [{r['match_id']}]: {e}")
    print(f"  竞彩足球: {len(fb_rows)} 场写入")

    bb_rows = fetch_basketball(fetch_date)
    bb_cols = ["match_id", "league", "kickoff_time", "home_team", "away_team",
               "spread_line", "odds_spread_home", "odds_spread_away",
               "total_line", "odds_over", "odds_under", "fetch_date"]
    for r in bb_rows:
        try:
            _upsert(conn, "okooo_basketball_odds", bb_cols, r, fetch_date)
            total += 1
        except sqlite3.Error as e:
            print(f"  篮球写入失败 [{r['match_id']}]: {e}")
    print(f"  竞彩篮球: {len(bb_rows)} 场写入")

    conn.commit()
    conn.close()
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", dest="date_str", default=None, help="fetch_date，默认今日")
    args = ap.parse_args()
    run(fetch_date=args.date_str)
