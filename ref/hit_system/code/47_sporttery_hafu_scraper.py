#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竞彩官网(sporttery.cn) 半全场(hafu)+完整赔率 落库爬虫
=================================
背景：sporttery_source.py 早就写好了完整的竞彩赔率解析(含半全场hafu/比分crs)，
但它只是一个返回内存dict的纯函数，从未真正写过数据库——2026-07-29审查发现
之前的调度项只是调用它拿到返回值就直接扔掉，从未产生过任何持久化数据，因此
被移除。顶替它的备份源42_okooo_jingcai_scraper.py(澳客网)明确只覆盖独赢/让球/
大小球，半全场(hafu)从未被任何来源真正落库——这是HT/FT市场的shadow桶
(_run_one_date()里的_htft_shadow_multi)从2026-07-24建成以来一直只能用
"模型隐含公平赔率(1/model_prob)"占位结算、无法验证真实市场edge的根本原因
(见00_命中系统.py里"best_odds暂时用模型隐含公平赔率占位"那段注释)。

本脚本是sporttery_source.py的真正消费者：调用其fetch_all_sporttery_odds()，
把返回的完整字段(含hafu 9格半全场赔率、crs比分赔率)落库到sporttery_odds_football/
sporttery_odds_basketball两张表，而不是像之前那样拿到就扔。

已知限制(2026-08-01沙盒环境验证)：这台机器出口IP是美国Akamai机房，sporttery.cn
的腾讯云EdgeOne WAF直接拦截(HTTP 567，"请求已被站点的安全策略拦截")，不是
header/TLS指纹能绕过的反爬挑战，是IP层面的硬拦截。本脚本在这台沙盒机器上无法
端到端验证，需要在真机(F:\qqsj\，网络环境不同)上实测。写这份代码时严格照抄
sporttery_source.py已验证过的返回字段结构，没有猜测字段名。

用法:
  python -X utf8 47_sporttery_hafu_scraper.py --date 2026-08-01
"""

import sys, os, json, sqlite3, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sporttery_source import fetch_all_sporttery_odds

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "data", "sports_data.db")

_HAFU_KEYS = ['hh', 'hd', 'ha', 'dh', 'dd', 'da', 'ah', 'ad', 'aa']


def init_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sporttery_odds_football (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        match_num TEXT,
        league_code TEXT,
        league_name TEXT,
        league_name_cn TEXT,
        league_id INTEGER,
        home_team TEXT,
        away_team TEXT,
        match_datetime TEXT,
        match_date TEXT,
        match_time TEXT,
        status TEXT,
        odds_1x2_home REAL, odds_1x2_draw REAL, odds_1x2_away REAL,
        ah_line REAL, odds_ah_home REAL, odds_ah_draw REAL, odds_ah_away REAL,
        odds_over REAL, odds_under REAL, total_line REAL,
        hafu_hh REAL, hafu_hd REAL, hafu_ha REAL,
        hafu_dh REAL, hafu_dd REAL, hafu_da REAL,
        hafu_ah REAL, hafu_ad REAL, hafu_aa REAL,
        crs_odds_json TEXT,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_id, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_sporttery_fb_match
        ON sporttery_odds_football(match_id, fetch_date)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_sporttery_fb_teams
        ON sporttery_odds_football(home_team, away_team, fetch_date)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS sporttery_odds_basketball (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        match_num TEXT,
        league_code TEXT,
        league_name TEXT,
        league_name_cn TEXT,
        league_id INTEGER,
        home_team TEXT,
        away_team TEXT,
        match_datetime TEXT,
        match_date TEXT,
        match_time TEXT,
        status TEXT,
        odds_moneyline_home REAL, odds_moneyline_away REAL,
        spread_line REAL, odds_spread_home REAL, odds_spread_away REAL,
        total_line REAL, odds_over REAL, odds_under REAL,
        wnm_odds_json TEXT,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_id, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_sporttery_bb_match
        ON sporttery_odds_basketball(match_id, fetch_date)""")
    conn.commit()


_FB_COLS = ["match_id", "match_num", "league_code", "league_name", "league_name_cn", "league_id",
            "home_team", "away_team", "match_datetime", "match_date", "match_time", "status",
            "odds_1x2_home", "odds_1x2_draw", "odds_1x2_away",
            "ah_line", "odds_ah_home", "odds_ah_draw", "odds_ah_away",
            "odds_over", "odds_under", "total_line",
            "hafu_hh", "hafu_hd", "hafu_ha", "hafu_dh", "hafu_dd", "hafu_da",
            "hafu_ah", "hafu_ad", "hafu_aa", "crs_odds_json", "fetch_date"]

_BB_COLS = ["match_id", "match_num", "league_code", "league_name", "league_name_cn", "league_id",
            "home_team", "away_team", "match_datetime", "match_date", "match_time", "status",
            "odds_moneyline_home", "odds_moneyline_away",
            "spread_line", "odds_spread_home", "odds_spread_away",
            "total_line", "odds_over", "odds_under", "wnm_odds_json", "fetch_date"]


def _upsert(conn, table, cols, row):
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("match_id", "fetch_date"))
    conn.execute(f"""
        INSERT INTO {table} ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(match_id, fetch_date) DO UPDATE SET {updates}
    """, tuple(row.get(c) for c in cols))


def _football_row(f: dict, fetch_date: str) -> dict:
    hafu = f.get('hafu_odds', {}) or {}
    row = {c: f.get(c) for c in _FB_COLS if c not in ("crs_odds_json", "fetch_date")
           and not c.startswith("hafu_")}
    for k in _HAFU_KEYS:
        row[f"hafu_{k}"] = hafu.get(k)
    crs = f.get('crs_odds')
    row["crs_odds_json"] = json.dumps(crs, ensure_ascii=False) if crs else None
    row["fetch_date"] = fetch_date
    return row


def _basketball_row(f: dict, fetch_date: str) -> dict:
    row = {c: f.get(c) for c in _BB_COLS if c not in ("wnm_odds_json", "fetch_date")}
    wnm = f.get('wnm_odds')
    row["wnm_odds_json"] = json.dumps(wnm, ensure_ascii=False) if wnm else None
    row["fetch_date"] = fetch_date
    return row


def run(fetch_date: str | None = None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_tables(conn)

    data = fetch_all_sporttery_odds(fetch_date, before_13=False)

    total = 0
    fb_hafu_count = 0
    for f in data.get('football', []):
        try:
            row = _football_row(f, fetch_date)
            _upsert(conn, "sporttery_odds_football", _FB_COLS, row)
            total += 1
            if any(row.get(f"hafu_{k}") for k in _HAFU_KEYS):
                fb_hafu_count += 1
        except sqlite3.Error as e:
            print(f"  足球写入失败 [{f.get('match_id')}]: {e}")
    print(f"  竞彩(官方)足球: {len(data.get('football', []))} 场写入，其中{fb_hafu_count}场有半全场赔率")

    for f in data.get('basketball', []):
        try:
            row = _basketball_row(f, fetch_date)
            _upsert(conn, "sporttery_odds_basketball", _BB_COLS, row)
            total += 1
        except sqlite3.Error as e:
            print(f"  篮球写入失败 [{f.get('match_id')}]: {e}")
    print(f"  竞彩(官方)篮球: {len(data.get('basketball', []))} 场写入")

    conn.commit()
    conn.close()
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", dest="date_str", default=None, help="fetch_date，默认今日")
    args = ap.parse_args()
    n = run(fetch_date=args.date_str)
    print(f"共写入 {n} 条")
