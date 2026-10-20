#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企鹅体育 阵容/伤病/积分榜/交锋历史爬虫
=======================================
数据源(2026-07-30土豆抓包摸排确认，纯header认证，不需要浏览器session):
  GET  /v2/matchLineup/getPCMatchLineupListPB?matchInfoId={mid}   阵容+伤病(layOff)
  GET  /v2/statistics/vsInfoNewPB?mid={mid}                        联赛积分榜
  GET  /v2/statistics/teamVSHistoryPB?mid={mid}&flag=0             两队历史交锋(含盘口结果)
  GET  /v2/statistics/teamVsOtherTeamPB?mid={mid}&flag=0           两队近期各自交锋(含盘口结果)

比赛来源: qiety_matches (29_qiety_yb_full_scraper.py 已写入)，今日+次日窗口，
足球+篮球都覆盖(接口本身不区分sportId，只认mid)。

用法:
  python -X utf8 46_qiety_lineup_scraper.py --date 2026-07-30
"""
import os, sys, json, time, base64, gzip, hashlib, sqlite3, argparse, ssl, urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_BASE   = "https://api.fgqinxg.com/yewu11/v2"
TZ_BJ      = timezone(timedelta(hours=8))
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
TOKEN_FILE = os.path.join(_BASE_DIR, ".qiety_token.json")

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
    print("ERROR: no valid token"); sys.exit(1)


class DetailClient:
    def __init__(self, rid, cuid):
        self.rid = rid
        self.cuid = cuid

    def _check_id(self):
        ts = int(time.time() * 1000)
        return f"pc-{hashlib.md5(f'{self.cuid}-{ts}'.encode()).hexdigest()}-{self.cuid}-{ts}"

    def _headers(self):
        return {
            "Accept":       "application/json",
            "Origin":       "https://user-pc-new.lvjida8.com",
            "Referer":      "https://user-pc-new.lvjida8.com/",
            "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "checkId":      self._check_id(),
            "lang":         "zh",
            "request-code": '{"panda-bss-source":"2"}',
            "requestId":    self.rid,
        }

    def get(self, ep, params):
        q = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{API_BASE}/{ep}?{q}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=self._headers(), method="GET")
                with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as r:
                    raw = r.read().decode()
                d = json.loads(raw)
                if d.get("code") != "0000000":
                    return None  # 无数据/参数不对，不是网络故障，不重试
                data = d.get("data")
                if not data:
                    return None
                return json.loads(gzip.decompress(base64.b64decode(data)))
            except Exception as e:
                err = str(e)
                if any(x in err for x in ("EOF", "SSL", "reset", "timed out", "Connection")):
                    if attempt < 2:
                        time.sleep(3 * (attempt + 1))
                        continue
                return None
        return None

    def get_lineup(self, mid):
        return self.get("matchLineup/getPCMatchLineupListPB", {"matchInfoId": mid})

    def get_standings(self, mid):
        return self.get("statistics/vsInfoNewPB", {"mid": mid})

    def get_h2h(self, mid):
        return self.get("statistics/teamVSHistoryPB", {"mid": mid, "flag": 0})

    def get_recent_vs_others(self, mid):
        return self.get("statistics/teamVsOtherTeamPB", {"mid": mid, "flag": 0})


# ============ 数据库 ============

def init_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_lineups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT, sport_code TEXT, team_side TEXT, formation TEXT,
        role TEXT, position_name TEXT, position_en_name TEXT, shirt_number INTEGER,
        player_name TEXT, player_name_en TEXT, player_source_id TEXT,
        fetch_date TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_standings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT, sport_code TEXT, ranking_id TEXT, ranking_name TEXT, ranking_round TEXT,
        team_cn_name TEXT, team_en_name TEXT, third_team_source_id TEXT,
        position INTEGER, matches_played INTEGER, win INTEGER, draw INTEGER, loss INTEGER,
        goals_for INTEGER, goals_against INTEGER, goal_diff INTEGER, points INTEGER,
        promotion_cn_name TEXT, fetch_date TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_h2h_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT, sport_code TEXT, relation TEXT,
        home_team_id TEXT, home_team_name TEXT, home_team_score TEXT,
        away_team_id TEXT, away_team_name TEXT, away_team_score TEXT,
        begin_time TEXT, handicap_val TEXT, handicap_result INTEGER,
        overunder_val TEXT, overunder_result INTEGER, result INTEGER,
        tournament_name TEXT, third_match_id TEXT, fetch_date TEXT
    )""")
    # 断点续跑记录表：不管这场比赛抓没抓到数据(比如无阵容/无交锋都是合法的空结果)，
    # 只要4个接口都成功调用完就记一条，重跑时跳过——避免中途被杀掉重跑时把已经
    # 处理过的比赛（哪怕结果是"确认无数据"）再白跑一遍，思路跟titan007脚本的
    # resume机制一致(见_scrape_titan007_1x2_odds.py)。
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_lineup_scrape_log (
        match_id TEXT, fetch_date TEXT, scraped_at TEXT,
        UNIQUE(match_id, fetch_date)
    )""")
    conn.commit()


def _clear(conn, table, mid, fetch_date):
    conn.execute(f"DELETE FROM {table} WHERE match_id=? AND fetch_date=?", (mid, fetch_date))


def write_lineup(conn, mid, sport_code, data, fetch_date):
    if not isinstance(data, dict):
        return 0
    n = 0
    _clear(conn, "qiety_lineups", mid, fetch_date)
    for side_key, side_label in [("home", "home"), ("away", "away")]:
        side = data.get(side_key)
        if not isinstance(side, dict):
            continue
        formation = side.get(f"{side_label}Formation", "")
        groups = [("starting", side.get("up", [])), ("substitute", side.get("down", [])),
                  ("injured", side.get("layOff", []))]
        for role, players in groups:
            if not isinstance(players, list):
                continue
            for p in players:
                if not isinstance(p, dict):
                    continue
                conn.execute("""INSERT INTO qiety_lineups
                    (match_id, sport_code, team_side, formation, role, position_name,
                     position_en_name, shirt_number, player_name, player_name_en,
                     player_source_id, fetch_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (mid, sport_code, side_label, formation, role,
                     p.get("positionName"), p.get("positionEnName"), p.get("shirtNumber"),
                     p.get("thirdPlayerName"), p.get("thirdPlayerEnName"),
                     p.get("thirdPlayerSourceId"), fetch_date))
                n += 1
    return n


def write_standings(conn, mid, sport_code, data, fetch_date):
    if not isinstance(data, list):
        return 0
    n = 0
    _clear(conn, "qiety_standings", mid, fetch_date)
    for group in data:
        if not isinstance(group, dict):
            continue
        for rk in group.get("rankingInfo", []):
            if not isinstance(rk, dict):
                continue
            for t in rk.get("teamRankings", []):
                if not isinstance(t, dict):
                    continue
                conn.execute("""INSERT INTO qiety_standings
                    (match_id, sport_code, ranking_id, ranking_name, ranking_round,
                     team_cn_name, team_en_name, third_team_source_id, position,
                     matches_played, win, draw, loss, goals_for, goals_against, goal_diff,
                     points, promotion_cn_name, fetch_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (mid, sport_code, t.get("rankingId"), t.get("rankingCnName"), t.get("rankingCnRound"),
                     t.get("teamCnName"), t.get("teamEnName"), t.get("thirdTeamSourceId"),
                     t.get("positionTotal"), t.get("matchCount"), t.get("winTotal"), t.get("drawTotal"),
                     t.get("lossTotal"), t.get("goalsForTotal"), t.get("goalsAgainstTotal"),
                     t.get("goalDiffTotal"), t.get("pointsTotal"), t.get("promotionCnName"), fetch_date))
                n += 1
    return n


def _write_h2h_rows(conn, mid, sport_code, rows, relation, fetch_date):
    n = 0
    if not isinstance(rows, list):
        return 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        bt = r.get("beginTime")
        try:
            bt_str = datetime.fromtimestamp(int(bt) / 1000, tz=TZ_BJ).strftime("%Y-%m-%d %H:%M") if bt else None
        except Exception:
            bt_str = None
        conn.execute("""INSERT INTO qiety_h2h_history
            (match_id, sport_code, relation, home_team_id, home_team_name, home_team_score,
             away_team_id, away_team_name, away_team_score, begin_time, handicap_val,
             handicap_result, overunder_val, overunder_result, result, tournament_name,
             third_match_id, fetch_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, sport_code, relation, r.get("homeTeamId"), r.get("homeTeamName"), r.get("homeTeamScore"),
             r.get("awayTeamId"), r.get("awayTeamName"), r.get("awayTeamScore"), bt_str,
             r.get("handicapVal"), r.get("handicapResult"), r.get("overunderVal"),
             r.get("overunderResult"), r.get("result"), r.get("tournamentName"),
             r.get("thirdMatchId"), fetch_date))
        n += 1
    return n


def write_h2h(conn, mid, sport_code, h2h_data, vs_others_data, fetch_date):
    _clear(conn, "qiety_h2h_history", mid, fetch_date)
    n = 0
    n += _write_h2h_rows(conn, mid, sport_code, h2h_data, "h2h", fetch_date)
    if isinstance(vs_others_data, dict):
        n += _write_h2h_rows(conn, mid, sport_code, vs_others_data.get("home"), "home_recent", fetch_date)
        n += _write_h2h_rows(conn, mid, sport_code, vs_others_data.get("away"), "away_recent", fetch_date)
    return n


# ============ 主流程 ============

def get_target_matches(conn, fetch_date, resume=True, sport=None):
    next_date = (datetime.strptime(fetch_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if sport:
        rows = conn.execute("""
            SELECT DISTINCT match_id, sport_code FROM qiety_matches
            WHERE fetch_date IN (?, ?) AND sport_code=?
        """, (fetch_date, next_date, sport)).fetchall()
    else:
        rows = conn.execute("""
            SELECT DISTINCT match_id, sport_code FROM qiety_matches
            WHERE fetch_date IN (?, ?)
        """, (fetch_date, next_date)).fetchall()
    if resume:
        done = {r[0] for r in conn.execute(
            "SELECT match_id FROM qiety_lineup_scrape_log WHERE fetch_date=?", (fetch_date,)
        )}
        before = len(rows)
        rows = [r for r in rows if r[0] not in done]
        if before - len(rows):
            print(f"  断点续跑: 跳过{before - len(rows)}场今天已处理过的比赛")
    return rows


def scrape(fetch_date, resume=True, sport=None):
    tok = load_token()
    client = DetailClient(tok["requestId"], tok.get("cuid", ""))

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_tables(conn)

    matches = get_target_matches(conn, fetch_date, resume=resume, sport=sport)
    print(f"  目标比赛数: {len(matches)}")

    stat = {"lineup": 0, "standings": 0, "h2h": 0, "matches_ok": 0, "matches_fail": 0}

    for i, (mid, sport_code) in enumerate(matches):
        print(f"  [{i+1}/{len(matches)}] mid={mid} ({sport_code})...", end=" ")
        sys.stdout.flush()
        try:
            lu = client.get_lineup(mid)
            st = client.get_standings(mid)
            h2h = client.get_h2h(mid)
            vso = client.get_recent_vs_others(mid)

            n_lu = write_lineup(conn, mid, sport_code, lu, fetch_date)
            n_st = write_standings(conn, mid, sport_code, st, fetch_date)
            n_h2h = write_h2h(conn, mid, sport_code, h2h, vso, fetch_date)
            conn.execute("""INSERT OR IGNORE INTO qiety_lineup_scrape_log (match_id, fetch_date, scraped_at)
                             VALUES (?,?,?)""", (mid, fetch_date, datetime.now(TZ_BJ).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

            stat["lineup"] += n_lu
            stat["standings"] += n_st
            stat["h2h"] += n_h2h
            stat["matches_ok"] += 1
            print(f"阵容{n_lu} 积分{n_st} 交锋{n_h2h}")
        except Exception as e:
            # 不写scrape_log，留到下次resume重跑重新尝试——只有真正跑完(哪怕结果是
            # 合法的0条)才算"处理过"，网络异常导致的失败不能被断点续跑永久跳过
            stat["matches_fail"] += 1
            print(f"FAIL ({e})")
        time.sleep(0.5)

    conn.close()
    print(f"\n  完成: {stat['matches_ok']}场成功 {stat['matches_fail']}场失败 | "
          f"阵容{stat['lineup']}条 积分榜{stat['standings']}条 交锋历史{stat['h2h']}条")
    return stat


# ============ 命中系统集成入口 ============

def run(fetch_date: str | None = None, sport: str | None = None):
    """00_命中系统.py 统一调度入口"""
    if fetch_date is None:
        fetch_date = datetime.now(TZ_BJ).strftime("%Y-%m-%d")
    print(f"  企鹅体育 阵容/积分榜/交锋历史 抓取 (fetch_date={fetch_date}, sport={sport or '全部'})")
    scrape(fetch_date, sport=sport)


# ============ CLI ============

def main():
    ap = argparse.ArgumentParser(description="企鹅体育阵容/伤病/积分榜/交锋历史爬虫")
    ap.add_argument("--date", type=str, default=None, help="YYYY-MM-DD，默认今天")
    ap.add_argument("--no-resume", action="store_true", help="忽略断点续跑记录，全部重新抓取")
    # 2026-08-02新增：按sport拆分football/basketball两个独立子进程并行跑，同29号
    # qiety_yb_full_scraper的拆分修复——单进程处理全部比赛(459场×4次请求/场)
    # 长期反复1800s超时(07-30起就有记录)，拆分后两个进程各自独立拿到完整预算。
    ap.add_argument("--sport", choices=["football", "basketball"], default=None, help="只抓指定运动")
    args = ap.parse_args()

    fetch_date = args.date or datetime.now(TZ_BJ).strftime("%Y-%m-%d")
    scrape(fetch_date, resume=not args.no_resume, sport=args.sport)


if __name__ == "__main__":
    main()
