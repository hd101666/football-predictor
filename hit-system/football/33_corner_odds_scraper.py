#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角球盘口赔率爬虫 v1
===================
数据源优先级:
  1. scoremer.com  — POST /ajax/score/data (corner=1)
     【已死勿复活 2026-09-13 确认】scoremer 自 2026-08-04 起 403 零产出
     （corner_live_odds 表实证：scoremer 源最后数据停在 2026-08-04），
     每日调度默认已不再跑它（--source 默认从 all 改为 500com）。
     不要试图修复/重接——该站对本环境是 IP 层拦截，非反爬技巧问题。
  2. live.500.com  — detail.php?fid=XXX（仍在产出，保留）
     提供: 比赛列表 + 角球盘口线

写入表: corner_live_odds

用法:
  python 33_corner_odds_scraper.py
  python 33_corner_odds_scraper.py --source scoremer
  python 33_corner_odds_scraper.py --source 500com
  python 33_corner_odds_scraper.py --date 2026-06-14
"""

import sys, re, json, time, argparse, sqlite3, logging, os
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sports_data.db")
TZ_BJ   = timezone(timedelta(hours=8))

try:
    from curl_cffi import requests as cf_req
    HAS_CURL = True
except ImportError:
    import requests as cf_req
    HAS_CURL = False
    log.warning("curl_cffi not available, using requests (may fail on protected sites)")

# ───── DB ─────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS corner_live_odds (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    match_id       TEXT NOT NULL,
    league_name    TEXT,
    home_team      TEXT,
    away_team      TEXT,
    match_status   TEXT,
    match_minute   TEXT,
    home_corners   INTEGER,
    away_corners   INTEGER,
    total_corners  INTEGER,
    ft_corner_line REAL,
    ft_handicap    REAL,
    ht_corner_line REAL,
    odds_over      REAL,
    odds_under     REAL,
    raw_json       TEXT,
    fetched_at     TEXT,
    fetch_date     TEXT,
    UNIQUE(source, match_id, fetch_date)
)
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute(DDL)
    conn.commit()
    return conn


def upsert_row(conn, row: dict):
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_str = ", ".join(cols)
    update_str = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("source","match_id","fetch_date"))
    conn.execute(
        f"INSERT INTO corner_live_odds ({col_str}) VALUES ({placeholders}) "
        f"ON CONFLICT(source, match_id, fetch_date) DO UPDATE SET {update_str}",
        list(row.values())
    )


# ───── SCOREMER.COM ───────────────────────────────────────────────────────────

SCOREMER_BASE = "https://lv.scoremer.com"

def scoremer_get_session():
    """建立 CF 会话并获取 csrf_token"""
    session = cf_req.Session()
    kwargs = dict(impersonate="chrome120", timeout=20, verify=False) if HAS_CURL else dict(timeout=20, verify=False)

    for attempt in range(3):
        try:
            r = session.get(f"{SCOREMER_BASE}/zh/corner", **kwargs)
            if r.status_code != 200:
                log.warning(f"scoremer GET {r.status_code}, attempt {attempt+1}")
                time.sleep(2)
                continue

            html = r.text
            # CF challenge 检测
            if "cTplV" in html or "__cf_chl" in html:
                log.warning(f"Cloudflare challenge, attempt {attempt+1}")
                time.sleep(3)
                continue

            csrf = re.search(r"csrf_token[\"':\s]+([a-f0-9]{10,})", html)
            if not csrf:
                log.warning("csrf_token not found in page")
                continue

            log.info(f"scoremer session OK, csrf={csrf.group(1)}")
            return session, csrf.group(1), kwargs
        except Exception as e:
            log.warning(f"scoremer session attempt {attempt+1}: {e}")
            time.sleep(2)

    return None, None, kwargs


def scoremer_fetch_corners(session, csrf, kwargs):
    """POST /ajax/score/data 获取角球数据"""
    payload = {
        "mt": "0",
        "csrf_token": csrf,
        "nr": "1",
        "corner": "1",
    }
    headers = {
        "Referer": f"{SCOREMER_BASE}/zh/corner",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    r = session.post(
        f"{SCOREMER_BASE}/ajax/score/data",
        data=payload, headers=headers, **kwargs
    )
    if r.status_code != 200:
        raise RuntimeError(f"AJAX POST returned {r.status_code}")
    return r.json()


def parse_scoremer_match(m: dict, fetch_date: str) -> dict:
    """解析单场比赛数据为 DB 行"""
    sd = m.get("sd", {})
    sd_f = sd.get("f", {})
    sd_h = sd.get("h", {})

    # 角球计数: heh=主队, haa=客队 (文档推断)
    home_crn = int(m.get("heh") or 0)
    away_crn = int(m.get("haa") or 0)
    total_crn = int(m.get("rcn") or 0)
    if total_crn == 0 and (home_crn + away_crn) > 0:
        total_crn = home_crn + away_crn

    # 赔率（若有）
    h_ld = m.get("h_ld") or {}
    f_ld = m.get("f_ld") or {}
    odds_over  = f_ld.get("ov") or h_ld.get("ov")
    odds_under = f_ld.get("un") or h_ld.get("un")

    status_map = {"0": "upcoming", "1": "1H", "2": "HT", "3": "2H", "4": "FT", "5": "ET"}
    status_raw = str(m.get("status", ""))
    status = status_map.get(status_raw, status_raw)

    minute = None
    ss = m.get("ss")
    if isinstance(ss, dict):
        minute = ss.get("m") or ss.get("min")

    return {
        "source":         "scoremer",
        "match_id":       str(m.get("id", "")),
        "league_name":    m.get("league", {}).get("fn") or m.get("league", {}).get("n"),
        "home_team":      m.get("host", {}).get("n"),
        "away_team":      m.get("guest", {}).get("n"),
        "match_status":   status,
        "match_minute":   str(minute) if minute else None,
        "home_corners":   home_crn or None,
        "away_corners":   away_crn or None,
        "total_corners":  total_crn or None,
        "ft_corner_line": float(sd_f["hcb"]) if sd_f.get("hcb") else None,
        "ft_handicap":    float(sd_f["hrf"]) if sd_f.get("hrf") else None,
        "ht_corner_line": float(sd_h["hcb"]) if sd_h.get("hcb") else None,
        "odds_over":      float(odds_over) if odds_over else None,
        "odds_under":     float(odds_under) if odds_under else None,
        "raw_json":       json.dumps(m, ensure_ascii=False),
        "fetched_at":     datetime.now(TZ_BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "fetch_date":     fetch_date,
    }


def scrape_scoremer(fetch_date: str):
    log.info("=== Scoremer 角球数据抓取 ===")
    session, csrf, kwargs = scoremer_get_session()
    if not session:
        log.error("无法建立 scoremer 会话，跳过")
        return 0

    try:
        data = scoremer_fetch_corners(session, csrf, kwargs)
    except Exception as e:
        log.error(f"scoremer AJAX 失败: {e}")
        return 0

    matches = data.get("rs", [])
    log.info(f"获取 {len(matches)} 场比赛")

    conn = get_conn()
    saved = 0
    for m in matches:
        try:
            row = parse_scoremer_match(m, fetch_date)
            upsert_row(conn, row)
            saved += 1
            log.info(f"  [{row['match_status']:>8}] {row['home_team']} vs {row['away_team']}"
                     f"  角球:{row['total_corners']}  线:{row['ft_corner_line']}")
        except Exception as e:
            log.warning(f"  解析失败 match {m.get('id')}: {e}")

    conn.commit()
    conn.close()
    log.info(f"scoremer 完成: {saved}/{len(matches)} 条写入")
    return saved


# ───── LIVE.500.COM ───────────────────────────────────────────────────────────

LIVE500_BASE = "https://live.500.com"

def scrape_500com(fetch_date: str, days_back: int = 2, max_matches: int = 120):
    """从 live.500.com 的**完场**页抓取已结束比赛的角球终值。

    Bug修复(2026-08-11)：原来从首页 live.500.com/ 用正则找 detail.php?fid= 来
    发现比赛，但该站已改成 socket.io WebSocket 推送比分，首页HTML里一个fid都没
    有了（实测首页HTTP 200、41KB、fid数=0），日志只会打"未找到比赛，可能需要
    登录或页面结构变更"，这个源实际上长期在空转。

    改用 /wanchang.php?e=YYYY-MM-DD（完场比分页，实测单日110个fid，仍是服务端
    渲染的静态HTML）。对结算来说这比原来的实时首页更合适——要的就是已踢完的
    终值。同时 match_status 直接标 'finished'：来源页面本身就是"完场"，不需要
    再从详情页猜（原来恒为'live'、match_minute恒为None，导致21_auto_settle.py
    无法判断比赛是否结束，角球推荐长期结算不了，这也是当初引入37号爬虫的原因）。
    """
    log.info("=== 500.com 角球数据抓取（完场页） ===")

    kwargs = dict(impersonate="chrome120", timeout=15, verify=False) if HAS_CURL else dict(timeout=15, verify=False)
    session = cf_req.Session()

    # 往前多翻几天：比赛结束到完场页收录有延迟，且本脚本一天可能只跑一两次
    base_day = datetime.strptime(fetch_date, "%Y-%m-%d")
    fids = []
    for i in range(days_back + 1):
        day = (base_day - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            r = session.get(f"{LIVE500_BASE}/wanchang.php?e={day}", **kwargs)
            if r.status_code != 200:
                log.warning(f"完场页 {day} HTTP {r.status_code}")
                continue
            html = r.content.decode("gbk", errors="replace")
            day_fids = list(dict.fromkeys(re.findall(r'detail\.php\?fid=(\d+)', html)))
            log.info(f"  完场页 {day}: {len(day_fids)} 个 fid")
            fids.extend(day_fids)
        except Exception as e:
            log.warning(f"完场页 {day} 请求失败: {e}")
        time.sleep(0.3)

    fids = list(dict.fromkeys(fids))
    log.info(f"合计发现 {len(fids)} 个已完赛 fid")
    if not fids:
        log.warning("完场页未找到比赛，可能页面结构再次变更")
        return 0

    conn = get_conn()
    saved = skipped = 0

    for fid in fids[:max_matches]:
        try:
            r2 = session.get(f"{LIVE500_BASE}/detail.php?fid={fid}&r=1", **kwargs)
            if r2.status_code != 200:
                continue

            row = parse_500com_detail(fid, r2.content, fetch_date)
            # 站上存在队名为空的占位页（title 直接就是 "VS足球比赛直播..."），
            # 这类页角球也解析成0-0，写进去就是假数据，直接跳过
            if not row or not row.get("home_team") or not row.get("away_team"):
                skipped += 1
                continue
            # 关键：500.com 对没有技术统计的比赛，角球进度条照样渲染成 "0 角球 0"，
            # 跟"真的踢了0个角球"在HTML上完全一样。足球全场零角球实际上不存在
            # （实测2026-08-10那批116场里有84场是这种0-0，占72%），一旦当成真值
            # 进结算，角球大小球盘的"小球"会被无条件判赢。因此0-0一律按缺失处理。
            if row.get("total_corners") is None or (
                row.get("home_corners") == 0 and row.get("away_corners") == 0
            ):
                skipped += 1
                continue

            row["match_status"] = "finished"  # 来源是完场页，可直接定性
            upsert_row(conn, row)
            saved += 1

            time.sleep(0.3)  # 礼貌延迟
        except Exception as e:
            log.warning(f"  fid={fid} 解析失败: {e}")

    conn.commit()
    conn.close()
    log.info(f"500.com 完成: 写入 {saved} 条，跳过 {skipped} 条（队名/角球缺失）")
    return saved


def parse_500com_detail(fid: str, raw_bytes: bytes, fetch_date: str) -> dict:
    """解析 500.com 比赛详情页角球数据（GB2312编码）"""
    html = raw_bytes.decode('gbk', errors='replace')

    # 队名从 title 提取: "玛丽港VS格尼斯坦足球比赛直播..."
    title_m = re.search(r'<title>(.*?)</title>', html, re.I)
    title_txt = title_m.group(1) if title_m else ""
    vs_m = re.search(r'^(.+?)VS(.+?)足球', title_txt)
    home_team = vs_m.group(1).strip() if vs_m else None
    away_team = vs_m.group(2).strip() if vs_m else None

    # 角球数: <td width="40" align="center">N</td> 角球 <td width="40" align="center">M</td>
    # 格式: 主队数 [角球标签] 客队数
    crn_m = re.search(
        r'<td[^>]*>\s*(\d+)\s*</td>\s*'
        r'<td[^>]*bgcolor=["\']#e4e4e4["\'][^>]*>\s*角球\s*</td>\s*'
        r'<td[^>]*>\s*(\d+)\s*</td>',
        html
    )
    home_crn = int(crn_m.group(1)) if crn_m else None
    away_crn = int(crn_m.group(2)) if crn_m else None

    # 比赛状态从比分
    score_m = re.search(r'class=["\']score["\'][^>]*>(\d+)\s*-\s*(\d+)', html)
    status = "live" if score_m else "unknown"

    return {
        "source":         "500com",
        "match_id":       str(fid),
        "league_name":    None,
        "home_team":      home_team,
        "away_team":      away_team,
        "match_status":   status,
        "match_minute":   None,
        "home_corners":   home_crn,
        "away_corners":   away_crn,
        "total_corners":  (home_crn + away_crn) if home_crn is not None and away_crn is not None else None,
        "ft_corner_line": None,   # live.500.com 只有统计，无盘口线
        "ft_handicap":    None,
        "ht_corner_line": None,
        "odds_over":      None,
        "odds_under":     None,
        "raw_json":       json.dumps({"fid": fid, "title": title_txt}, ensure_ascii=False),
        "fetched_at":     datetime.now(TZ_BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "fetch_date":     fetch_date,
    }


# ───── MAIN ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="角球盘口爬虫")
    parser.add_argument("--date", default=datetime.now(TZ_BJ).strftime("%Y-%m-%d"))
    parser.add_argument("--source", choices=["scoremer", "500com", "all"], default="500com")
    # 默认 500com（2026-09-13）：scoremer 源已死（403 零产出自 2026-08-04），
    # 日常调度不再跑；显式 --source scoremer/all 仍可手动调用（仅诊断用途）。
    args = parser.parse_args()

    fetch_date = args.date
    log.info(f"角球盘口抓取 fetch_date={fetch_date}")

    total = 0
    if args.source in ("scoremer", "all"):
        total += scrape_scoremer(fetch_date)
    if args.source in ("500com", "all"):
        total += scrape_500com(fetch_date)

    log.info(f"全部完成，共写入 {total} 条")


if __name__ == "__main__":
    main()
