#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企鹅体育 YB (亚博) 场馆全自动赔率爬虫
=====================================
- 自动从 .qiety_token.json 读取最新 token
- 获取全量比赛和赔率，写入 multisource_odds + qiety_matches
- 支持 --request-id 手动覆盖 token

使用方式:
  python 28_qiety_yb_scraper_v2.py --sport 1
  python 28_qiety_yb_scraper_v2.py --sport 2
  python 28_qiety_yb_scraper_v2.py --check-token
"""

import os
import sys
import json
import time
import base64
import gzip
import hashlib
import sqlite3
import argparse
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

# 自签证书 SSL 绕过
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============ 配置 ============

API_BASE   = "https://api.bvl8bs5.com/yewu11/v1/w"
TZ_BJ      = timezone(timedelta(hours=8))
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
TOKEN_FILE = os.path.join(_BASE_DIR, ".qiety_token.json")

# 兜底凭证（过期时报错提示更新）
_FALLBACK_REQUEST_ID = os.environ.get("QIETY_TOKEN", "")   # sanitized: 原为明文兜底 token
_FALLBACK_CUID = os.environ.get("QIETY_CUID", "")          # sanitized: 原为明文兜底 cuid
_FALLBACK_EUID       = "3020101"


def load_token() -> dict:
    """从 .qiety_token.json 读取最新 token，不存在则用兜底值"""
    if os.path.exists(TOKEN_FILE):
        try:
            d = json.load(open(TOKEN_FILE, encoding='utf-8'))
            if d.get('requestId'):
                return d
        except Exception:
            pass
    return {
        'requestId': _FALLBACK_REQUEST_ID,
        'cuid': _FALLBACK_CUID,
        'euid': _FALLBACK_EUID,
    }


# ============ API 客户端 ============

class YBApiClient:
    def __init__(self, request_id: str = None, check_id: str = None,
                 cuid: str = None, euid: str = None):
        tok = load_token()
        self.request_id = request_id or tok.get('requestId', _FALLBACK_REQUEST_ID)
        self.cuid       = cuid       or tok.get('cuid',      _FALLBACK_CUID)
        self.euid       = euid       or tok.get('euid',      _FALLBACK_EUID)
        self._check_id  = check_id

    def _gen_check_id(self) -> str:
        if self._check_id:
            return self._check_id
        ts = int(time.time() * 1000)
        raw = f"{self.cuid}-{ts}"
        md5_part = hashlib.md5(raw.encode()).hexdigest()
        return f"pc-{md5_part}-{self.cuid}-{ts}"

    def _get_headers(self) -> dict:
        return {
            "Accept":           "application/json, text/plain, */*",
            "Accept-Language":  "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type":     "application/json",
            "Origin":           "https://user-pc-new.lvjida8.com",
            "Referer":          "https://user-pc-new.lvjida8.com/",
            "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "checkId":          self._gen_check_id(),
            "lang":             "zh",
            "request-code":     '{"panda-bss-source":"2"}',
            "requestId":        self.request_id,
        }

    def _decode(self, raw_response: str) -> dict:
        d = json.loads(raw_response)
        code = d.get("code")
        if code != "0000000":
            raise Exception(f"API错误 code={code}: {d.get('msg', '')}")
        data_b64 = d["data"]
        decoded      = base64.b64decode(data_b64)
        decompressed = gzip.decompress(decoded)
        return json.loads(decompressed)

    def post(self, endpoint: str, body: dict, max_retry: int = 3) -> dict:
        last_err = None
        for attempt in range(max_retry):
            try:
                ts  = int(time.time() * 1000)
                url = f"{API_BASE}/{endpoint}?t={ts}"
                req = urllib.request.Request(
                    url, data=json.dumps(body).encode("utf-8"),
                    headers=self._get_headers(), method="POST"
                )
                with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                    raw = resp.read().decode("utf-8")
                return self._decode(raw)
            except Exception as e:
                last_err = e
                err_str = str(e)
                if any(x in err_str for x in ("EOF", "SSL", "reset", "timed out", "Connection")):
                    if attempt < max_retry - 1:
                        wait = 5 * (attempt + 1)
                        print(f"    [retry {attempt+1}/{max_retry}] SSL/网络错误，等待{wait}s: {e}")
                        time.sleep(wait)
                        continue
                raise
        raise last_err

    def get(self, endpoint: str, params: dict, max_retry: int = 3) -> dict:
        last_err = None
        for attempt in range(max_retry):
            try:
                ts        = int(time.time() * 1000)
                param_str = "&".join([f"{k}={v}" for k, v in params.items()])
                url       = f"{API_BASE}/{endpoint}?{param_str}&t={ts}"
                req       = urllib.request.Request(url, headers=self._get_headers(), method="GET")
                with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                    raw = resp.read().decode("utf-8")
                return self._decode(raw)
            except Exception as e:
                last_err = e
                err_str = str(e)
                if any(x in err_str for x in ("EOF", "SSL", "reset", "timed out", "Connection")):
                    if attempt < max_retry - 1:
                        wait = 5 * (attempt + 1)
                        time.sleep(wait)
                        continue
                raise
        raise last_err

    def is_token_valid(self) -> bool:
        try:
            result = self.post("getAddedOddsMatchesPB",
                               {"cuid": self.cuid, "euid": self.euid, "sportId": "1"})
            return True  # code=0000000即有效，即使data为空
        except Exception as e:
            return False

    def get_match_list(self, sport_id: str = "1") -> list:
        result = self.post("getAddedOddsMatchesPB",
                           {"cuid": self.cuid, "euid": self.euid, "sportId": sport_id})
        return result.get("data", [])

    def get_match_odds(self, mid: str) -> list:
        params = {"mcid": "0", "mid": mid, "cuid": self.cuid, "newUser": "0", "isMr": ""}
        return self.get("matchDetail/getMatchOddsInfo1PB", params)


# ============ 赔率解析 ============

def ov_to_decimal(ov: int) -> float:
    return ov / 100000


def parse_odds(odds_data: list, home_team: str, away_team: str,
               league: str, match_date: str, match_id: str) -> list:
    records = []
    for item in odds_data:
        chpid = item.get("chpid", "")
        hlf   = item.get("hlf", 0)
        if hlf != 0:  # 只取全场
            continue
        for h in item.get("hl", []):
            ol = h.get("ol", [])
            hv = h.get("hv", None)

            if chpid == "1" and len(ol) >= 3:   # 独赢 1X2
                ho = ov_to_decimal(ol[0].get("ov", 0))
                dr = ov_to_decimal(ol[1].get("ov", 0))
                aw = ov_to_decimal(ol[2].get("ov", 0))
                margin = round((1/ho + 1/dr + 1/aw - 1) * 100, 2) if (ho and dr and aw) else None
                records.append({
                    "match_id": match_id, "source": "qiety_yb",
                    "league": league, "home_team": home_team, "away_team": away_team,
                    "odds_type": "1X2",
                    "odds_home": ho, "odds_draw": dr, "odds_away": aw,
                    "handicap_line": None, "total_line": None,
                    "margin": margin, "match_date": match_date,
                })

            elif chpid == "4" and len(ol) >= 2:  # 亚洲让球
                records.append({
                    "match_id": match_id, "source": "qiety_yb",
                    "league": league, "home_team": home_team, "away_team": away_team,
                    "odds_type": "asian_handicap",
                    "odds_home": ov_to_decimal(ol[0].get("ov", 0)),
                    "odds_draw": None,
                    "odds_away": ov_to_decimal(ol[1].get("ov", 0)),
                    "handicap_line": str(hv) if hv is not None else None,
                    "total_line": None, "match_date": match_date,
                })

            elif chpid == "2" and len(ol) >= 2:  # 大小球
                records.append({
                    "match_id": match_id, "source": "qiety_yb",
                    "league": league, "home_team": home_team, "away_team": away_team,
                    "odds_type": "over_under",
                    "odds_home": ov_to_decimal(ol[0].get("ov", 0)),
                    "odds_draw": None,
                    "odds_away": ov_to_decimal(ol[1].get("ov", 0)),
                    "handicap_line": None,
                    "total_line": str(hv) if hv is not None else None,
                    "match_date": match_date,
                })
    return records


# ============ 数据库写入 ============

def init_tables(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT UNIQUE,
        sport_code TEXT,
        league TEXT,
        home_team TEXT,
        away_team TEXT,
        kickoff_time TEXT,
        status TEXT,
        home_score INTEGER,
        away_score INTEGER,
        fetch_date TEXT
    )""")
    conn.commit()


def upsert_match(conn: sqlite3.Connection, match_id: str, sport_code: str,
                 league: str, home: str, away: str, kickoff: str, fetch_date: str):
    conn.execute("""INSERT INTO qiety_matches
        (match_id, sport_code, league, home_team, away_team, kickoff_time, status, fetch_date)
        VALUES (?, ?, ?, ?, ?, ?, 'NS', ?)
        ON CONFLICT(match_id, fetch_date) DO UPDATE SET
            league=excluded.league, home_team=excluded.home_team,
            away_team=excluded.away_team, kickoff_time=excluded.kickoff_time
    """, (match_id, sport_code, league, home, away, kickoff, fetch_date))


def write_odds(conn: sqlite3.Connection, records: list):
    """写入赔率。

    ★2026-10-09 修复「同键互相覆盖」：
      28(本脚本, getAddedOddsMatchesPB) 与 29(getMatchBaseInfoByOddsPB) 都写
      source='qiety_yb' 且 odds_type ∈ {1X2, asian_handicap, over_under} —— 键完全相同，
      谁后跑谁覆盖。29 覆盖面更广（全量赛事列表），是主源；28 只抓「新增赔率」的场次。
      规则：**若同 (match_id, source, odds_type) 当日已被写过，则 28 不覆盖**
      （避免后跑且数据更少的 28 抹掉 29 的完整批次）。跨日仍允许刷新。
    """
    if not records:
        return 0
    now = datetime.now(TZ_BJ).strftime("%Y-%m-%d %H:%M:%S")
    today = now[:10]
    inserted = skipped = 0
    for rec in records:
        try:
            # ★守卫：当日同键已存在 → 不覆盖（保留先写入者的数据）
            row = conn.execute("""SELECT scraped_at FROM multisource_odds
                WHERE match_id=? AND source=? AND odds_type=?""",
                (rec["match_id"], rec["source"], rec["odds_type"])).fetchone()
            if row and str(row[0] or "")[:10] == today:
                skipped += 1
                continue
            # 先删同 match_id + odds_type 的旧记录再插入（保持最新）
            conn.execute("""DELETE FROM multisource_odds
                WHERE match_id=? AND source=? AND odds_type=?""",
                (rec["match_id"], rec["source"], rec["odds_type"]))
            ot = rec["odds_type"]
            over_v  = rec.get("odds_home") if ot == "over_under" else None
            under_v = rec.get("odds_away") if ot == "over_under" else None
            conn.execute("""INSERT INTO multisource_odds
                (match_id, source, league, home_team, away_team, odds_type,
                 odds_home, odds_draw, odds_away, handicap_line, total_line,
                 over_odds, under_odds, margin, scraped_at, match_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec["match_id"], rec["source"], rec["league"],
                rec["home_team"], rec["away_team"], ot,
                rec.get("odds_home") or 0, rec.get("odds_draw"),
                rec.get("odds_away") or 0,
                rec.get("handicap_line"), rec.get("total_line"),
                over_v, under_v,
                rec.get("margin"), now, rec.get("match_date"),
            ))
            inserted += 1
        except Exception as e:
            print(f"    写入错误: {e}")
    if skipped:
        print(f"    （跳过 {skipped} 条：当日同键已写入，避免覆盖主源批次）")
    return inserted


# ============ 主抓取流程 ============

def run_scrape(client: YBApiClient, db_path: str, sport_id: str = "1",
               sport_name: str = "足球"):
    now_str    = datetime.now(TZ_BJ).strftime("%H:%M:%S")
    fetch_date = datetime.now(TZ_BJ).strftime("%Y-%m-%d")
    sport_code = "football" if sport_id == "1" else "basketball"
    print(f"[{now_str}] 开始抓取 {sport_name} YB 赔率... (fetch_date={fetch_date})")

    matches = client.get_match_list(sport_id)
    print(f"  发现 {len(matches)} 场比赛")
    if not matches:
        print(f"  ℹ️  {sport_name} 今日无待开赛场次（Qiety 平台暂未上架赔率，非 token 问题）")
        return False, 0

    conn = sqlite3.connect(db_path)
    init_tables(conn)

    all_odds   = []
    success_ct = 0

    for i, match in enumerate(matches):
        mid    = str(match.get("mid", ""))
        league = match.get("tn", "")
        home   = match.get("mhn", "")
        away   = match.get("man", "")
        mgt    = match.get("mgt", "")

        kickoff = ""
        match_date = fetch_date
        if mgt:
            try:
                dt         = datetime.fromtimestamp(int(mgt) / 1000, tz=TZ_BJ)
                kickoff    = dt.strftime("%Y-%m-%d %H:%M")
                match_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # 写 qiety_matches
        if mid:
            upsert_match(conn, mid, sport_code, league, home, away, kickoff, fetch_date)

        print(f"  [{i+1}/{len(matches)}] {home} vs {away}...", end=" ")
        sys.stdout.flush()

        try:
            odds_data = client.get_match_odds(mid)
        except Exception as e:
            print(f"❌ {e}")
            continue

        if not odds_data:
            print("⚠️ 无赔率")
            continue

        records = parse_odds(odds_data, home, away, league, match_date, mid)
        types   = {r["odds_type"] for r in records}
        labels  = [t for t in ["1X2", "asian_handicap", "over_under"] if t in types]
        print(f"✅ {', '.join(labels)} ({len(records)}条)")

        all_odds.extend(records)
        success_ct += 1
        time.sleep(0.3)

    inserted = write_odds(conn, all_odds)
    conn.commit()
    conn.close()

    print(f"\n✅ {sport_name} 完成: {success_ct}/{len(matches)} 场, {inserted} 条赔率写入")
    return True, inserted


# ============ 命中系统集成入口 ============

def run():
    """00_命中系统.py 统一调度入口：足球+篮球各跑一次"""
    client = YBApiClient()
    tok = load_token()
    saved = tok.get('saved_at', '未知')
    print(f"  企鹅体育 YB Token 时间: {saved}")
    print("  requestId: ***")

    ok1, n1 = run_scrape(client, DB_PATH, "1", "足球")
    if ok1:
        print("  等待10s避免服务端限速...")
        time.sleep(10)
    ok2, n2 = run_scrape(client, DB_PATH, "2", "篮球")

    if not ok1 and not ok2:
        print("❌ 企鹅体育 YB 全部失败，请运行 get_yb_token_win.py 刷新 token")


# ============ CLI ============

def main():
    parser = argparse.ArgumentParser(description="企鹅体育YB赔率全自动爬虫")
    parser.add_argument("--sport", type=str, default="1", choices=["1", "2"],
                        help="1=足球, 2=篮球")
    parser.add_argument("--request-id", type=str, default=None,
                        help="登录 token (覆盖 .qiety_token.json)")
    parser.add_argument("--cuid",       type=str, default=None)
    parser.add_argument("--check-id",   type=str, default=None)
    parser.add_argument("--db-path",    type=str, default=DB_PATH)
    parser.add_argument("--check-token", action="store_true",
                        help="只检查 token 是否有效")
    args = parser.parse_args()

    client = YBApiClient(
        request_id=args.request_id,
        check_id=getattr(args, 'check_id', None),
        cuid=args.cuid,
    )

    tok = load_token()
    saved = tok.get('saved_at', '未知')
    print(f"  Token 来源: {TOKEN_FILE if os.path.exists(TOKEN_FILE) else '兜底硬编码'}")
    print(f"  Token 保存时间: {saved}")
    print("  requestId: ***")

    if args.check_token:
        valid = client.is_token_valid()
        print(f"{'✅ Token 有效' if valid else '❌ Token 已过期，请重新获取'}")
        if not valid:
            print("  方法: 访问 https://user-pc-new.lvjida8.com/ 登录后")
            print(f"  运行 get_yb_token_win.py 更新 {TOKEN_FILE}")
        return

    sport_name = {"1": "足球", "2": "篮球"}.get(args.sport, f"sport{args.sport}")
    success, count = run_scrape(client, args.db_path, args.sport, sport_name)

    if not success:
        print(f"\n❌ 抓取失败! 请更新 token:")
        print(f"  python get_yb_token_win.py")


if __name__ == "__main__":
    main()
