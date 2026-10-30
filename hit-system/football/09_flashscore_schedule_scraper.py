# 09_flashscore_schedule_scraper.py — FlashScore 赛程数据爬虫（原名误作 soccerway）
# 真实来源: www.flashscore.com 管道协议（d.flashscore.com/x/feed）
# 数据格式：管道协议，分隔符 ~ (记录) / ¬ (字段) / ÷ (键值)
# 存储：soccerway_matches / soccerway_standings / soccerway_form / soccerway_h2h / soccerway_stats
# 反爬：curl_cffi TLS指纹伪造 + UA轮换 + 随机延迟

import sys, re, time, random, logging, json
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import exec_ddl, batch_upsert
from http_utils import StealthSession, random_sleep
from sqlalchemy import MetaData

# Bug修复(2026-08-12)：本文件原先只有 getLogger、**没有 basicConfig**，
# 独立运行时 Python 日志默认只输出 WARNING 及以上，所有 log.info 的成功信息
# （"抓取开始"/"写入N场"/"完成"）被静默丢弃，日志里只剩 http_utils 重试时打的
# log.warning 连接噪音。结果是一个**工作正常**的爬虫看起来像全线失败——
# 2026-08-12 我据此误判它失败、白跑两轮补爬、还追查了指纹/会话泄漏/网络等
# 一堆不存在的原因，实际当天它写了314行（对比前一日24行）。
# 判断爬虫成败要看**数据库有没有新数据**，不能数日志行；而日志本身也该配好。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
engine = create_engine(DB_ENGINE_URL)

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]

# ─── 常量 ────────────────────────────────────────────────────────────────────
FLASH_HOST = "https://www.flashscore.com"

SW_HEADERS = {
    "Accept-Language": "en-US,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         FLASH_HOST + "/",
    "X-Fsign":         "SW9D1eZo",
}

from leagues import FOOTBALL_LEAGUES

# Flashscore AB 字段 → 状态
STATUS_MAP = {
    "0":  "NS",   # Not started
    "1":  "1H",   # First half
    "2":  "HT",   # Half time
    "3":  "FT",   # Full time
    "31": "AET",  # After extra time
    "41": "Pen",  # After penalties
    "-1": "Canc", # Cancelled
    "-2": "Post", # Postponed
}


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS soccerway_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sw_match_id TEXT UNIQUE,
            league_code TEXT,
            league_name TEXT,
            season TEXT,
            home_team TEXT,
            away_team TEXT,
            home_team_id TEXT,
            away_team_id TEXT,
            kickoff_utc TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            home_score_ht INTEGER,
            away_score_ht INTEGER,
            venue TEXT,
            referee TEXT,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS soccerway_standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_code TEXT,
            season TEXT,
            team_name TEXT,
            team_id TEXT,
            position INTEGER,
            played INTEGER,
            won INTEGER,
            drawn INTEGER,
            lost INTEGER,
            goals_for INTEGER,
            goals_against INTEGER,
            goal_diff INTEGER,
            points INTEGER,
            form TEXT,
            fetch_date TEXT,
            UNIQUE(league_code, season, team_id)
        )""",
        """CREATE TABLE IF NOT EXISTS soccerway_form (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT,
            team_name TEXT,
            sw_match_id TEXT,
            opponent_name TEXT,
            is_home INTEGER,
            kickoff_utc TEXT,
            goals_for INTEGER,
            goals_against INTEGER,
            result TEXT,
            league_code TEXT,
            fetch_date TEXT,
            UNIQUE(team_id, sw_match_id)
        )""",
        """CREATE TABLE IF NOT EXISTS soccerway_h2h (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team1_id TEXT,
            team2_id TEXT,
            sw_match_id TEXT,
            kickoff_utc TEXT,
            home_team TEXT,
            away_team TEXT,
            home_score INTEGER,
            away_score INTEGER,
            league_code TEXT,
            fetch_date TEXT,
            UNIQUE(team1_id, team2_id, sw_match_id)
        )""",
        """CREATE TABLE IF NOT EXISTS soccerway_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sw_match_id TEXT,
            stat_key TEXT,
            home_value TEXT,
            away_value TEXT,
            fetch_date TEXT,
            UNIQUE(sw_match_id, stat_key)
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ Soccerway 数据表初始化完成")


# ─── HTTP 会话（使用公共 StealthSession 基类）────────────────────────────────
_sess = StealthSession(base_url=FLASH_HOST, headers=SW_HEADERS)


def _sleep(extra: float = 0):
    time.sleep(random.uniform(CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP) + extra)


# ─── 管道协议解析 ─────────────────────────────────────────────────────────────
def _parse_embedded_matches(html: str) -> list:
    """
    从 Flashscore HTML 提取内嵌管道格式的比赛数据。
    格式: KEY÷VALUE¬KEY÷VALUE¬...~KEY÷VALUE¬...
    记录分隔符: ~
    字段分隔符: ¬ (U+00AC)
    键值分隔符: ÷ (U+00F7)
    """
    idx = html.find('AA÷')
    if idx < 0:
        return []

    # 找到数据块结尾（第一个 HTML 标签）
    end = len(html)
    for marker in ['</script>', '</div>', '</body>']:
        pos = html.find(marker, idx)
        if idx < pos < end:
            end = pos

    data_block = html[idx:end]
    records = data_block.split('~')

    matches = []
    for rec in records:
        if 'AA÷' not in rec or 'CX÷' not in rec:
            continue
        fields = {}
        for part in rec.split('¬'):   # ¬
            if '÷' in part:           # ÷
                k, _, v = part.partition('÷')
                if k:
                    fields[k] = v
        if 'AA' in fields and 'CX' in fields:
            matches.append(fields)
    return matches


def _ts_to_utc(ts: str) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return ts


def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


# ─── 1. 抓取联赛比赛列表 ──────────────────────────────────────────────────────
def fetch_league_matches(league_path: str, league_code: str, fetch_date: str,
                          pages: int = 3) -> int:
    rows_to_insert = []
    total = 0
    # 抓 results 页（历史）和 fixtures 页（未来）
    for suffix in ["results/", "fixtures/"]:
        url = FLASH_HOST + league_path + suffix
        html = _sess.get_text(url)
        if not html:
            log.warning(f"  无法访问: {url}")
            continue

        records = _parse_embedded_matches(html)
        count = 0
        for fields in records:
            mid     = fields.get("AA", "")
            ts_kick = fields.get("AD", "")
            home    = fields.get("CX", "")
            away    = fields.get("AF", "")
            # Bug修复(2026-08-11)：全场比分字段代号原先写成 AS/AZ，是错的。
            # 实测拿30场巴甲/阿甲已完赛比赛跟干净的 match_results 对质：
            # AG/AH 命中93%，AS/AZ 只命中17%(纯属小数字撞巧)。本表污染程度：
            # soccerway_matches 来源的666行足球比分准确率仅 **6.7%**(626场可对质
            # 只对42场)，平局率高达96.2%(真实25-27%)——因为 AS/AZ 大量取到 1:1、
            # 2:2 这种小数字。实例：Bragantino 真实0:2 存成2:2、Flamengo 真实2:0
            # 存成1:1。这些错误比分会流进 unified_matches(21_auto_settle.py 的**主**
            # 比分来源)，只是恰好大部分结算走了 match_results 兜底才没酿成大祸。
            #
            # 顺带解开旧谜团：原代码把 AG 当"半场主队比分"，其实 AG 是**全场**主队
            # 比分——这正是 project_flashscore_09_ht_field_bug 里"AG/AT当半场已证伪"
            # 的真正原因。半场比分在列表页拿不到(需详情页 p1_home/p1_away)，
            # 与其填错不如置 None，让下游明确知道"没有半场数据"。
            hs      = fields.get("AG")
            as_     = fields.get("AH")
            hs_ht   = None
            as_ht   = None
            status_code = fields.get("AB", "0")
            status  = STATUS_MAP.get(status_code, status_code)

            if not mid or not home:
                continue

            try:
                rows_to_insert.append({
                    "sw_match_id":   mid,
                    "league_code":   league_code,
                    "league_name":   league_code,
                    "season":        "current",
                    "home_team":     home,
                    "away_team":     away,
                    "home_team_id":  fields.get("JA"),
                    "away_team_id":  fields.get("JB"),
                    "kickoff_utc":   _ts_to_utc(ts_kick),
                    "status":        status,
                    "home_score":    _safe_int(hs),
                    "away_score":    _safe_int(as_),
                    "home_score_ht": _safe_int(hs_ht),
                    "away_score_ht": _safe_int(as_ht),
                    "venue":         None,
                    "referee":       None,
                    "fetch_date":    fetch_date,
                })
                count += 1
            except Exception as e:
                log.debug(f"入库异常: {e}")

        log.info(f"  {league_code}/{suffix}: {count} 场")
        total += count
        _sleep(0.5)

    # batch write
    if rows_to_insert:
        try:
            tbl = _get_table(engine, 'soccerway_matches')
            batch_upsert(engine, tbl, rows_to_insert, unique_keys=['sw_match_id'])
        except Exception as e:
            log.warning(f'soccerway_matches batch write failed: {e}')

    return total# ─── 2. 积分榜 ────────────────────────────────────────────────────────────────
def fetch_standings(league_path: str, league_code: str, fetch_date: str):
    standings_rows = []
    url = FLASH_HOST + league_path + "standings/"
    html = _sess.get_text(url)
    if not html:
        return

    # Flashscore 积分榜以 SA÷ 字段嵌入在 HTML 中
    # 格式: SA÷team_id¬SB÷team_name¬SC÷pos¬SD÷played¬...
    idx = html.find('SA÷')
    if idx < 0:
        log.debug(f"standings: 无SA字段: {league_path}")
        return

    end = len(html)
    for m in ['</script>', '</div>']:
        pos = html.find(m, idx)
        if idx < pos < end:
            end = pos

    block = html[idx:end]
    records = [r for r in block.split('~') if 'SA÷' in r and 'SB÷' in r]
    count = 0
    for rec in records:
        fields = {}
        for part in rec.split('¬'):
            if '÷' in part:
                k, _, v = part.partition('÷')
                if k:
                    fields[k] = v
        team_id   = fields.get("SA", "")
        team_name = fields.get("SB", "")
        if not team_name:
            continue
        try:
            standings_rows.append({
                    "league_code": league_code, "season": "current",
                    "team_name": team_name, "team_id": team_id,
                    "position":  _safe_int(fields.get("SC")),
                    "played":    _safe_int(fields.get("SD")),
                    "won":       _safe_int(fields.get("SE")),
                    "drawn":     _safe_int(fields.get("SF")),
                    "lost":      _safe_int(fields.get("SG")),
                    "goals_for": _safe_int(fields.get("SH")),
                    "goals_against": _safe_int(fields.get("SI")),
                    "goal_diff": _safe_int(fields.get("SJ")),
                    "points":    _safe_int(fields.get("SK")),
                    "form":      fields.get("SL"),
                    "fetch_date": fetch_date,
                })
            count += 1
        except Exception:
            pass
    # batch write
    if standings_rows:
        try:
            tbl = _get_table(engine, 'soccerway_standings')
            batch_upsert(engine, tbl, standings_rows, unique_keys=['league_code', 'season', 'team_name'])
        except Exception as e:
            log.warning(f'soccerway_standings batch write failed: {e}')
    log.info(f"  积分榜 {league_code}: {count} 支球队")


# ─── 主流程 ───────────────────────────────────────────────────────────────────
def run(fetch_standings_flag: bool = True):
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    log.info(f"🌐 Soccerway(Flashscore) 全量数据抓取开始 [{fetch_date}]")

    total = 0
    for path, code in FOOTBALL_LEAGUES.items():
        log.info(f"\n⚽ {code}")
        n = fetch_league_matches(path, code, fetch_date)
        total += n
        _sleep(0.5)

        if fetch_standings_flag:
            fetch_standings(path, code, fetch_date)
            _sleep(0.5)

    log.info(f"\n✅ Soccerway 抓取完成，共 {total} 场")


if __name__ == "__main__":
    run()
