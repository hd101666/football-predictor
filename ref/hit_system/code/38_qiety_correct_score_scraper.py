#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企鹅体育(qiety/YB) 比分盘口爬虫
=================================
数据源: matchDetail/getMatchOddsInfo1PB（"更多玩法"全量盘口接口，chpid=7 为全场比分）
    注意: 主赔率接口 getMatchBaseInfoByOddsPB（29_qiety_yb_full_scraper.py 用的那个）
    不含比分盘口，比分盘口只能从这个"比赛详情"全量接口里按 chpid=7 过滤取得，
    是实测枚举了某场比赛全部150+种chpid类型后确认的（其余多为半场比分/高比分区/混合过关等衍生盘）。

用法:
  python 38_qiety_correct_score_scraper.py --date 2026-07-06
"""

import sys, os, json, time, base64, gzip, hashlib, sqlite3, argparse, ssl, urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_BASE   = "https://api.fgqinxg.com/yewu11"
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
TOKEN_FILE = os.path.join(_BASE_DIR, ".qiety_token.json")
CORRECT_SCORE_CHPID = "7"  # 全场比分（实测枚举确认，非半场/非高比分区变种）

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def load_token():
    if os.path.exists(TOKEN_FILE):
        try:
            d = json.load(open(TOKEN_FILE, encoding='utf-8'))
            if d.get('requestId'):
                return d
        except Exception:
            pass
    print("ERROR: no valid token")
    sys.exit(1)


def _check_id(cuid):
    ts = int(time.time() * 1000)
    return f"pc-{hashlib.md5(f'{cuid}-{ts}'.encode()).hexdigest()}-{cuid}-{ts}"


def fetch_match_detail(rid, cuid, mid):
    """调用 matchDetail/getMatchOddsInfo1PB 拿全量盘口列表（含 chpid=7 比分盘）"""
    ts = int(time.time() * 1000)
    url = f"{API_BASE}/v1/w/matchDetail/getMatchOddsInfo1PB?mcid=0&mid={mid}&cuid={cuid}&newUser=0&isMr=&t={ts}"
    headers = {
        "Accept": "application/json",
        "requestId": rid,
        "checkId": _check_id(cuid),
        "lang": "zh",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://user-pc-new.lvjida8.com",
        "Referer": "https://user-pc-new.lvjida8.com/",
        "request-code": '{"panda-bss-source":"2"}',
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
        d = json.loads(r.read().decode())
        if d.get("code") != "0000000":
            return None
        data_raw = d["data"]
        if isinstance(data_raw, str):
            return json.loads(gzip.decompress(base64.b64decode(data_raw)))
        return data_raw


def parse_correct_score(detail_items: list) -> dict:
    """从全量盘口列表里过滤 chpid=7，返回 {'H-A': decimal_odds, ...}"""
    result = {}
    if not detail_items:
        return result
    for item in detail_items:
        if str(item.get("chpid")) != CORRECT_SCORE_CHPID:
            continue
        for hl in item.get("hl", []):
            for ol in hl.get("ol", []):
                cs_key = (ol.get("on") or "").strip()
                ov = ol.get("ov")
                if not cs_key or ov is None:
                    continue
                try:
                    dec_odds = round(float(ov) / 100000, 3)
                except (TypeError, ValueError):
                    continue
                if dec_odds > 1.0:
                    result[cs_key] = dec_odds
    return result


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS yb_correct_score_odds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        correct_score TEXT NOT NULL,
        decimal_odds REAL,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(match_id, correct_score, fetch_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_yb_cs_match
        ON yb_correct_score_odds(match_id, fetch_date)""")


def run(fetch_date: str = None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    tok = load_token()
    rid, cuid = tok["requestId"], tok.get("cuid", "")

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_table(conn)

    cur = conn.cursor()
    # 今日 + 次日中午前未开赛的足球比赛（跟 29_qiety_yb_full_scraper 抓到的比赛列表保持一致）
    next_date = (datetime.strptime(fetch_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    cur.execute("""
        SELECT DISTINCT match_id FROM qiety_matches
        WHERE sport_code='football' AND fetch_date IN (?, ?)
    """, (fetch_date, next_date))
    match_ids = [r[0] for r in cur.fetchall()]

    # Bug修复(2026-08-20)：本脚本依赖29_qiety_yb_full_scraper.run_football先把
    # qiety_matches表的今天数据写好，但两者在00_命中系统.py调度里分属Priority2/3——
    # 正常情况下Priority严格串行没问题，但实测2026-08-20当天29号因为跟外部结算
    # 管道撞库报"database is locked"失败，Priority仍然照常往下走到Priority3，
    # 本脚本查到qiety_matches是空的，抓到0场比赛，仍然正常退出(exit 0)——
    # scraper_run_log记成status='ok'，断点续跑机制认为"今天已成功"，即使29号
    # 后续重试补上了数据，也没人再叫本脚本重跑一次，当天比分盘口永久缺失。
    # 现在显式检查upstream依赖：qiety_matches里如果一场football比赛都没有（且
    # 明显不是"今天真的没有比赛"这种情况——用unified_matches的足球比赛数做
    # 交叉验证），就判定upstream还没写完，本次直接失败退出，让外层重试机制
    # 在29号成功之后有机会重新跑一次，而不是悄悄产出0条然后被标记"成功"。
    if not match_ids:
        cur.execute("""
            SELECT COUNT(DISTINCT unified_id) FROM unified_matches
            WHERE sport_code='football' AND fetch_date IN (?, ?)
        """, (fetch_date, next_date))
        _uni_football_n = cur.fetchone()[0]
        conn.close()
        if _uni_football_n > 0:
            print(f"  ⚠ qiety_matches今日无football比赛，但unified_matches有{_uni_football_n}场，"
                  f"判定upstream(29_qiety_yb_full_scraper.run_football)数据未就绪，失败退出等待重试", flush=True)
            sys.exit(1)
        print("  比分盘口抓取: 0 场候选比赛（unified_matches当天也无足球比赛，视为正常）", flush=True)
        return 0

    print(f"  比分盘口抓取: {len(match_ids)} 场候选比赛", flush=True)

    written = ok = fail = 0
    for i, mid in enumerate(match_ids):
        try:
            detail = fetch_match_detail(rid, cuid, mid)
        except Exception as e:
            fail += 1
            time.sleep(0.5)
            continue
        cs_odds = parse_correct_score(detail)
        if cs_odds:
            for cs_key, dec_odds in cs_odds.items():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO yb_correct_score_odds
                        (match_id, correct_score, decimal_odds, fetch_date)
                        VALUES (?, ?, ?, ?)
                    """, (mid, cs_key, dec_odds, fetch_date))
                    written += 1
                except Exception:
                    pass
            conn.commit()
            ok += 1
        time.sleep(0.4)

    conn.close()
    print(f"  qiety比分盘口: {ok}场有数据, {fail}场失败, {written}条赔率写入", flush=True)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="企鹅体育YB比分盘口爬虫")
    ap.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD，默认今日")
    args = ap.parse_args()
    run(args.date)
