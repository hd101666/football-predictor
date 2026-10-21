#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企鹅体育 YB 全量爬虫 v3
=======================
1. structureTournamentMatchesPB → 全量比赛列表（联赛级别）
2. getMatchBaseInfoByOddsPB → 逐场赔率+队名+盘口
3. 写入 qiety_matches + multisource_odds

范围：今日 + 次日15:00以前未开赛

用法:
  python 29_qiety_yb_full_scraper.py --sport 1    # 足球
  python 29_qiety_yb_full_scraper.py --sport 2    # 篮球
  python 29_qiety_yb_full_scraper.py --all        # 全部
"""

import os, sys, json, time, base64, gzip, hashlib, sqlite3, argparse, ssl, urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_BASE   = "https://api.fgqinxg.com/yewu11"
TZ_BJ      = timezone(timedelta(hours=8))
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
TOKEN_FILE = os.path.join(_BASE_DIR, ".qiety_token.json")

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

SPORTS = {
    "1": {"euid": "3020101", "mi": "101201", "name": "足球", "code": "football"},
    "2": {"euid": "3020102", "mi": "102201", "name": "篮球", "code": "basketball"},
}

def load_token():
    if os.path.exists(TOKEN_FILE):
        try:
            d = json.load(open(TOKEN_FILE, encoding='utf-8'))
            if d.get('requestId'):
                return d
        except Exception:
            pass
    print("ERROR: no valid token"); sys.exit(1)


class YBClient:
    def __init__(self, rid, cuid):
        self.rid  = rid
        self.cuid = cuid

    def _check_id(self):
        ts = int(time.time() * 1000)
        return f"pc-{hashlib.md5(f'{self.cuid}-{ts}'.encode()).hexdigest()}-{self.cuid}-{ts}"

    def _headers(self):
        return {
            "Accept":          "application/json",
            "Content-Type":    "application/json",
            "Origin":          "https://user-pc-new.lvjida8.com",
            "Referer":         "https://user-pc-new.lvjida8.com/",
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "checkId":         self._check_id(),
            "lang":            "zh",
            "request-code":    '{"panda-bss-source":"2"}',
            "requestId":       self.rid,
        }

    def _decode(self, raw):
        d = json.loads(raw)
        if d.get("code") != "0000000":
            raise Exception(f"{d.get('code')}: {d.get('msg', '')}")
        return json.loads(gzip.decompress(base64.b64decode(d["data"])))

    def post(self, ep, body, ver="v1"):
        for attempt in range(3):
            try:
                ts  = int(time.time() * 1000)
                url = f"{API_BASE}/{ver}/w/{ep}?t={ts}"
                req = urllib.request.Request(
                    url, data=json.dumps(body).encode(),
                    headers=self._headers(), method="POST"
                )
                with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as r:
                    return self._decode(r.read().decode())
            except Exception as e:
                err = str(e)
                if any(x in err for x in ("EOF", "SSL", "reset", "timed out", "Connection")):
                    if attempt < 2:
                        wait = 5 * (attempt + 1)
                        print(f"    [retry {attempt+1}/3] 网络错误，等待{wait}s: {e}")
                        time.sleep(wait)
                        continue
                raise

    def get_match_list(self, sport_id):
        cfg = SPORTS[sport_id]
        return self.post("structureTournamentMatchesPB", {
            "cuid": self.cuid, "euid": cfg["euid"],
            "sportId": sport_id, "mi": cfg["mi"],
        }, ver="v2")

    def get_match_odds(self, mid, sport_id):
        cfg = SPORTS[sport_id]
        return self.post("getMatchBaseInfoByOddsPB", {
            "cuid": self.cuid, "euid": cfg["euid"],
            "sportId": sport_id, "mcid": "0", "mid": mid,
        })


# ============ 赔率解析 ============

def ov2dec(ov):
    return ov / 100000


def parse_hps_data(hps_data_list):
    """解析 hpsData 中的盘口赔率
    hpsData[].hps[].hl 可能是单个 dict 或 list of dict
    """
    records = []
    if not isinstance(hps_data_list, list):
        return records

    for hps_item in hps_data_list:
        if not isinstance(hps_item, dict):
            continue
        for hp in hps_item.get("hps", []):
            if not isinstance(hp, dict):
                continue
            chpid = str(hp.get("chpid", ""))
            if hp.get("hlf", 0) != 0:
                continue  # 只取全场

            hl_raw = hp.get("hl", [])
            hl_list = [hl_raw] if isinstance(hl_raw, dict) else (hl_raw if isinstance(hl_raw, list) else [])

            for hl in hl_list:
                if not isinstance(hl, dict):
                    continue
                ol = hl.get("ol", [])
                if not isinstance(ol, list) or not ol:
                    continue
                hv = hl.get("hv", None)

                try:
                    if chpid in ("1", "37") and len(ol) >= 2:   # 独赢（足球1X2 / 篮球moneyline）
                        # FIX-010-1（2026-09-14）：足球1X2(chpid=1)的ol顺序实为
                        # [主,客,平]（ot='1'/'2'/'X' 实证，布凯里耶场 ol[1]=客队名），
                        # 旧代码按[主,平,客]假设取值导致全历史 qiety_yb 1X2 行
                        # odds_draw/odds_away 互换（draw列=客胜价）。改为按 ot 标签
                        # 映射；ot 缺失时退回实证的 [主,客,平] 位置序。
                        # 注意：历史存量行未回填修正（漂移分析只用快照表新数据）。
                        ho = aw = dr = None
                        ot_map = {o.get("ot"): o for o in ol if isinstance(o, dict)}
                        if chpid == "1" and {"1", "2", "X"} <= set(ot_map):
                            ho = ov2dec(ot_map["1"].get("ov", 0))
                            aw = ov2dec(ot_map["2"].get("ov", 0))
                            dr = ov2dec(ot_map["X"].get("ov", 0))
                        elif chpid == "1" and len(ol) >= 3:
                            ho = ov2dec(ol[0].get("ov", 0)) if isinstance(ol[0], dict) else 0
                            aw = ov2dec(ol[1].get("ov", 0)) if isinstance(ol[1], dict) else 0
                            dr = ov2dec(ol[2].get("ov", 0)) if isinstance(ol[2], dict) else None
                        else:  # 篮球moneyline(chpid=37)二项盘，保持原位序
                            ho = ov2dec(ol[0].get("ov", 0)) if isinstance(ol[0], dict) else 0
                            aw = ov2dec(ol[-1].get("ov", 0)) if isinstance(ol[-1], dict) else 0
                        margin = round((1/ho + (1/dr if dr else 0) + 1/aw - 1) * 100, 2) if (ho and aw) else None
                        records.append({
                            "odds_type": "1X2",
                            "odds_home": ho, "odds_draw": dr, "odds_away": aw,
                            "handicap_line": None, "total_line": None, "margin": margin,
                        })
                    elif chpid in ("4", "39") and len(ol) >= 2:  # 亚盘/让球
                        records.append({
                            "odds_type": "asian_handicap",
                            "odds_home": ov2dec(ol[0].get("ov", 0)) if isinstance(ol[0], dict) else 0,
                            "odds_draw": None,
                            "odds_away": ov2dec(ol[1].get("ov", 0)) if isinstance(ol[1], dict) else 0,
                            "handicap_line": str(hv) if hv is not None else None,
                            "total_line": None, "margin": None,
                        })
                    elif chpid in ("2", "38") and len(ol) >= 2:  # 大小球
                        records.append({
                            "odds_type": "over_under",
                            "odds_home": ov2dec(ol[0].get("ov", 0)) if isinstance(ol[0], dict) else 0,
                            "odds_draw": None,
                            "odds_away": ov2dec(ol[1].get("ov", 0)) if isinstance(ol[1], dict) else 0,
                            "handicap_line": None,
                            "total_line": str(hv) if hv is not None else None, "margin": None,
                        })
                except Exception:
                    continue
    return records


# ============ 数据库 ============

def init_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT UNIQUE,
        sport_code TEXT, league TEXT, home_team TEXT, away_team TEXT,
        kickoff_time TEXT, status TEXT,
        home_score INTEGER, away_score INTEGER, fetch_date TEXT
    )""")
    # FIX-010-1（2026-09-14）：只增不改的赔率快照表。multisource_odds 的
    # qiety_yb 行是 DELETE+INSERT 覆盖写（与39号修复前同一病灶），重抓即
    # 抹掉上一批，"时序走弱"检测无数据地基。本表每次抓取独立一批
    # （batch_ts=北京时间），只插不改，供 _warning_weakening.py 双源确认用。
    conn.execute("""CREATE TABLE IF NOT EXISTS qiety_odds_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        sport_code TEXT,
        odds_type TEXT,
        odds_home REAL, odds_draw REAL, odds_away REAL,
        handicap_line TEXT, total_line TEXT,
        match_date TEXT,
        batch_ts TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(match_id, odds_type, batch_ts)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_qiety_snap_mid
        ON qiety_odds_snapshots(match_id, batch_ts)""")
    conn.commit()


def upsert_match(conn, mid, code, league, home, away, kickoff, fetch_date, status="NS"):
    conn.execute("""INSERT INTO qiety_matches
        (match_id, sport_code, league, home_team, away_team, kickoff_time, status, fetch_date)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(match_id, fetch_date) DO UPDATE SET
            league=excluded.league, home_team=excluded.home_team,
            away_team=excluded.away_team, kickoff_time=excluded.kickoff_time,
            status=excluded.status
    """, (mid, code, league, home, away, kickoff, status, fetch_date))


def write_odds(conn, mid, league, home, away, match_date, records, sport_code, batch_ts=None):
    if not records:
        return 0
    now = datetime.now(TZ_BJ).strftime("%Y-%m-%d %H:%M:%S")
    batch_ts = batch_ts or now
    inserted = 0
    for rec in records:
        try:
            ot = rec["odds_type"]
            conn.execute("DELETE FROM multisource_odds WHERE match_id=? AND source='qiety_yb' AND odds_type=?",
                         (mid, ot))
            conn.execute("""INSERT INTO multisource_odds
                (match_id, source, league, home_team, away_team, odds_type,
                 odds_home, odds_draw, odds_away, handicap_line, total_line,
                 over_odds, under_odds, margin, scraped_at, match_date, sport)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, "qiety_yb", league, home, away, ot,
                 rec.get("odds_home") or 0, rec.get("odds_draw"),
                 rec.get("odds_away") or 0,
                 rec.get("handicap_line"), rec.get("total_line"),
                 rec.get("odds_home") if ot == "over_under" else None,
                 rec.get("odds_away") if ot == "over_under" else None,
                 rec.get("margin"), now, match_date, sport_code))
            inserted += 1
        except Exception as e:
            print(f"    db err: {e}")
        # FIX-010-1：快照追加（只插不改）。快照失败必须显式可见——这是
        # 时序检测的地基，静默失败等于没修（CLAUDE.md 影子写库异常规则）。
        try:
            conn.execute("""INSERT INTO qiety_odds_snapshots
                (match_id, sport_code, odds_type, odds_home, odds_draw, odds_away,
                 handicap_line, total_line, match_date, batch_ts)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id, odds_type, batch_ts) DO NOTHING""",
                (mid, sport_code, rec["odds_type"],
                 rec.get("odds_home"), rec.get("odds_draw"), rec.get("odds_away"),
                 rec.get("handicap_line"), rec.get("total_line"),
                 match_date, batch_ts))
        except Exception as e:
            print(f"    ⚠️ 快照写入失败 mid={mid} {rec['odds_type']}: {e}")
    return inserted


# ============ 主抓取流程 ============

def scrape_sport(client, sport_id, force_refresh=False):
    cfg       = SPORTS[sport_id]
    now_bj    = datetime.now(TZ_BJ)
    fetch_date = now_bj.strftime("%Y-%m-%d")
    # 抓取窗口：当前时间 → 次日 19:00（北京）
    tomorrow_19 = (now_bj + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)

    print(f"\n{'='*60}")
    print(f"[{now_bj.strftime('%H:%M:%S')}] {cfg['name']} 全量抓取 (mi={cfg['mi']})")
    print(f"  窗口: 现在 → {tomorrow_19.strftime('%m-%d %H:%M')} 北京时间")
    print(f"{'='*60}")

    # 1. 全量比赛列表
    try:
        result = client.get_match_list(sport_id)
    except Exception as e:
        # FIX-011-3（2026-09-14）：token生命周期管理——0401013=账户信息已过期
        # （09-14 11:37 全量跑批足球+篮球双零的实证根因，与09-06同款；两次失败
        # 都能被token过期解释，已排除编排环境差异）。显式大字告警让跑批日志
        # 一眼可辨、可grep；不做自动刷新——需人工提供最新入口URL后走
        # _refresh_qiety_token_20260907.py 既有流程更新 .qiety_token.json。
        if "0401013" in str(e) or "账户信息已过期" in str(e):
            print("!" * 64)
            print("!! QIETY TOKEN 已过期（0401013 账户信息已过期）!!")
            print("!! 处置：索取企鹅体育最新入口URL → 走既有刷新流程更新")
            print("!! .qiety_token.json → 重跑本爬虫。刷新前本源将持续0产出。")
            print("!" * 64)
        print(f"  ERROR 获取比赛列表: {e}")
        return 0

    # 2. 从 nolivedata / livedata 提取
    entries = []
    # 虚假/电竞赛事关键词过滤（PANDA独家、EA游戏模拟、梦幻对垒等）
    FAKE_KW = ["PANDA独家", "VS-", "梦幻对垒", "梦幻", "2K23", "2K24", "2K25",
               "EAFC", "EA FC", "电竞", "Esports", "esports", "虚拟"]

    live_count = 0
    filtered_count = 0
    for dk in ['nolivedata', 'livedata']:
        is_live = (dk == 'livedata')
        for item in result.get(dk, []):
            mid = str(item.get("mids", ""))
            tn  = item.get("tn", "")
            mgt = item.get("mgt", "")
            if not mid or not mgt:
                continue
            # 过滤虚假赛事
            if any(kw in tn for kw in FAKE_KW):
                filtered_count += 1
                continue
            try:
                kickoff = datetime.fromtimestamp(int(mgt) / 1000, tz=TZ_BJ)
            except Exception:
                continue
            if is_live:
                # 进行中比赛：只要今日的都收录
                entries.append({"mid": mid, "tn": tn, "kickoff": kickoff, "live": True})
                live_count += 1
            else:
                # 未开赛：过滤到次日 19:00 之前
                if kickoff <= now_bj:
                    continue
                if kickoff > tomorrow_19:
                    continue
                entries.append({"mid": mid, "tn": tn, "kickoff": kickoff, "live": False})
    if filtered_count:
        print(f"  🚫 已过滤虚假/电竞赛事: {filtered_count} 场")

    entries.sort(key=lambda x: x["kickoff"])
    nolive_count = len(entries) - live_count
    print(f"  进行中: {live_count} 场  未开赛(在窗口内): {nolive_count} 场  合计: {len(entries)} 场")
    if not entries:
        print("  ⚠️ 无比赛数据")
        return 0

    # 3. 逐场抓赔率
    # Bug修复：默认5s忙等超时太短，Priority2并行跑多个爬虫时经常撞上"database is locked"，
    # 加长超时+开WAL模式与其他爬虫的写库方式保持一致
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_tables(conn)
    total_odds = 0
    ok = fail = 0

    # 断点续跑：跳过今天已经成功抓到赔率的比赛。此前没有这层检查时，1800s
    # 超时被杀后重跑会从第1场重新抓起，比赛量大(300+场)时永远追不上进度、
    # 多轮重跑也无法收敛(2026-08-09验证：连续两轮都精确卡在1800s超时)。
    already_done = set() if force_refresh else {r[0] for r in conn.execute(
        "SELECT DISTINCT match_id FROM multisource_odds WHERE source='qiety_yb' AND sport=? AND scraped_at LIKE ?",
        (cfg["code"], f"{fetch_date}%"))}
    if already_done:
        print(f"  ⏭  今日已抓过 {len(already_done)} 场，将跳过（断点续跑）")

    skip = 0
    for i, e in enumerate(entries):
        mid      = e["mid"]
        tn       = e["tn"]
        kf       = e["kickoff"]
        is_live  = e.get("live", False)
        kf_str   = kf.strftime("%Y-%m-%d %H:%M")
        md       = kf.strftime("%Y-%m-%d")
        tag      = "🔴" if is_live else "  "

        if mid in already_done:
            skip += 1
            continue

        print(f"  {tag}[{i+1}/{len(entries)}] {kf_str} {tn} | mid={mid}...", end=" ")
        sys.stdout.flush()

        try:
            data = client.get_match_odds(mid, sport_id)
        except Exception as ex:
            print(f"FAIL ({ex})")
            fail += 1
            time.sleep(0.5)
            continue

        data_list = data.get("data", [])
        home = away = ""
        hps_data = []
        if data_list:
            d0       = data_list[0]
            home     = d0.get("mhn", "")
            away     = d0.get("man", "")
            tn       = d0.get("tn", tn) or tn
            hps_data = d0.get("hpsData", [])

        records = parse_hps_data(hps_data)
        types   = {r["odds_type"] for r in records}
        labels  = [t for t in ["1X2", "asian_handicap", "over_under"] if t in types]

        if labels:
            n = write_odds(conn, mid, tn, home, away, md, records, cfg["code"],
                           batch_ts=now_bj.strftime("%Y-%m-%d %H:%M:%S"))
            total_odds += n
            print(f"✅ {home} vs {away} ({', '.join(labels)}, {n}条)")
        else:
            print(f"⚠️  {home} vs {away} (无盘口)")

        status = "LIVE" if is_live else "NS"
        upsert_match(conn, mid, cfg["code"], tn, home, away, kf_str, fetch_date, status)
        conn.commit()
        ok += 1
        time.sleep(0.4)

    conn.close()
    print(f"\n  {cfg['name']}: {ok}场成功, {fail}场失败, {skip}场跳过(今日已抓), {total_odds}条赔率写入")
    return total_odds


# ============ 命中系统集成入口 ============

def run():
    """00_命中系统.py 统一调度入口"""
    tok = load_token()
    print(f"  企鹅体育 YB(全量) Token: {tok.get('saved_at','未知')}")
    client = YBClient(tok["requestId"], tok.get("cuid", ""))
    total = 0
    for sid in ["1", "2"]:
        total += scrape_sport(client, sid)
        if sid == "1":
            print("  等待10s避免限速...")
            time.sleep(10)
    print(f"  qiety全量: {total} 条写入")


# ============ CLI ============

def main():
    ap = argparse.ArgumentParser(description="企鹅体育YB全量赔率爬虫")
    ap.add_argument("--sport", choices=["1", "2"], help="1=足球, 2=篮球")
    ap.add_argument("--all",   action="store_true", help="足球+篮球全部")
    ap.add_argument("--force-refresh", action="store_true", help="强制重新抓取当天已抓比赛，用于临场时序快照")
    args = ap.parse_args()

    tok = load_token()
    print(f"Token: {tok['requestId'][:25]}... (saved: {tok.get('saved_at', '')})")
    client = YBClient(tok["requestId"], tok.get("cuid", ""))

    sports = ["1", "2"] if (args.all or not args.sport) else [args.sport]
    total = 0
    for sid in sports:
        total += scrape_sport(client, sid, force_refresh=args.force_refresh)
        if sid == "1" and "2" in sports:
            print("  等待10s...")
            time.sleep(10)

    print(f"\n{'='*60}")
    print(f"  总计: {total} 条赔率写入 {DB_PATH}")
    print(f"{'='*60}")
    if total == 0:
        # Bug修复(2026-09-06)：scrape_sport()对get_match_list()异常(如token过期
        # "账户信息已过期")只打印ERROR后return 0，main()此前从不据此退出非零码——
        # 00_命中系统.py的_launch_scraper()断点续跑判断只看returncode，这会把
        # "token失效/接口报错导致0条"误记成status='ok'，"今日已成功"缓存机制
        # 从此永久跳过重试，当天该数据源整体失踪也不会被发现（2026-09-06实测：
        # 09-06 token过期，18:49跑出0条被记ok，后续20:42全量分析仍照常跳过）。
        sys.exit(1)


if __name__ == "__main__":
    main()
