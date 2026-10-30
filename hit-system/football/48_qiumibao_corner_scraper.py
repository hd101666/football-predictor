# -*- coding: utf-8 -*-
"""
48_qiumibao_corner_scraper.py — 188bifen.com(直播吧镜像) 半场/全场比分+角球数据抓取

背景（2026-09-04用户指定网址 https://www.188bifen.com/record.html 新增）：
该页面是纯前端Vue单页应用，页面本身不含数据，逆向其加载的JS bundle
(record.v1.*.js / chunk-common.v1.*.js) 找到真实数据源是 qiumibao(球迷宝) 的公开
只读API，无需登录/无反爬拦截，plain requests即可访问：
  - https://matchs.qiumibao.com/mc/today_archive_cn.htm   今日(含刚结束)比赛滚动窗口
  - https://matchs.qiumibao.com/mc/{YYYY-MM-DD}_cn.htm    指定日期比赛(按北京日历日分桶)

**已验证的坑**：指定日期端点(/mc/{date}_cn.htm)对"当天/近1-2天"的比赛返回的是
未同步的旧快照（比分恒为0-0，status_code='1'），要拿到真实终场比分必须改查
today_archive_cn.htm——该端点覆盖一个滚动窗口(实测2026-09-04当天返回311-349场，
跨越"昨天深夜到今天")，其中真正结束的比赛status_code='8'。本爬虫因此固定策略：
只取status_code=='8'的比赛写库，today_archive覆盖不到的更早日期改查指定日期端点
（此时该端点数据已经落定，不再是占位0-0）。

返回JSON结构（顶层matches/leagues两个key，leagues是{league_id: [联赛名,...]}映射，
matches是数组的数组，每场比赛的字段位置是从record.v1 JS bundle里的
formatGoalPopupData()等函数反推出来的，已用本项目fotmob_match_team_stats交叉验证
比分/半场吻合，角球字段的具体列位是从数值量级(单位数到十几)+页面确有"角球"表头
两点推断，未找到显式赋值代码确认，标记为待观察置信度，见_HOME_CORNER_IDX注释）：
  match[0]=match_id  match[1]=league_id  match[2]=status_code(str,'8'=完场)
  match[3]=kickoff_unix_utc  match[5]=主队数组  match[6]=客队数组  match[19]=运动类型('1'足球/'2'篮球)
  队伍数组: [team_id, name, final_score, ht_score, yellow_card, red_card, ???(疑似角球), rank_seed, "", icon_url]

用法：
  python -X utf8 48_qiumibao_corner_scraper.py                          # 默认：赔率快照(供00_命中系统.py每日调度用)
  python -X utf8 48_qiumibao_corner_scraper.py --date 2026-09-02        # 指定日期的赔率快照
  python -X utf8 48_qiumibao_corner_scraper.py --finished-only          # 完场比分/半场/角球(供21_auto_settle.py结算管道用)
  python -X utf8 48_qiumibao_corner_scraper.py --finished-only --date 2026-09-02

注意：00_命中系统.py的爬虫调度器(_launch_scraper)对func_name前缀是"run_"的条目
只会拼出`--date`这一个CLI参数(见_launch_scraper里"非标准入口"分支的说明)，没有
通用机制传自定义flag——所以**默认行为(不带--finished-only)必须是调度器真正想要
的run_odds_snapshot()**，21_auto_settle.py是本文件唯一另一个调用方，它是手写的
subprocess.run()调用，可以自己加`--finished-only`来精确指定要跑哪个函数。两个
调用方的CLI参数需求不对称，所以默认值刻意选了对通用调度器更友好的一边。
"""
import os, sys, argparse, logging
from datetime import datetime, timezone, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import env_setup
import requests
from sqlalchemy import create_engine, MetaData
from config import DB_ENGINE_URL
from db_utils import exec_ddl, batch_upsert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("qiumibao_corner")

engine = create_engine(DB_ENGINE_URL)

_BASE = "https://matchs.qiumibao.com/mc"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Referer": "https://www.188bifen.com/",
}
_SPORT_MAP = {"1": "football", "2": "basketball"}
_FINISHED_STATUS = "8"

# 队伍子数组里"疑似角球"字段的下标——见文件头注释，置信度：中高(非官方文档确认)
_HOME_CORNER_IDX = 6


def _get_tables():
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS qiumibao_match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_match_id INTEGER UNIQUE,
            sport_code TEXT,
            league_id INTEGER,
            league_name TEXT,
            status_code TEXT,
            kickoff_utc TEXT,
            home_team TEXT,
            away_team TEXT,
            home_score INTEGER,
            away_score INTEGER,
            home_score_ht INTEGER,
            away_score_ht INTEGER,
            home_corners INTEGER,
            away_corners INTEGER,
            corners_confidence TEXT DEFAULT 'unconfirmed_field_index',
            fetch_date TEXT,
            updated_at TEXT
        )
    """)
    # 2026-09-04新增：赛前/滚动赔率快照，供将来跟titan007同思路的跨源赔率分歧
    # 信号回测用(见project memory里titan007因联赛覆盖不足暂时用不上的记录——
    # qiumibao覆盖的正好是竞彩/十四场/任九候选池那批带彩票期号的比赛，可能补上
    # 这个缺口，但目前完全没有历史样本，本表只负责每天存一份快照攒数据，
    # **不接入任何推荐/预测逻辑**，要等样本积累到能回测的量级才评估是否有用)。
    # unique_keys=(match_id, fetch_date)：同一天多次跑只保留当天最新一次快照，
    # 不是逐小时的赔率走势记录(那需要更高频调度，当前需求只是"每天一份"够回测用)。
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS qiumibao_odds_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_match_id INTEGER,
            sport_code TEXT,
            league_id INTEGER,
            league_name TEXT,
            status_code TEXT,
            kickoff_utc TEXT,
            home_team TEXT,
            away_team TEXT,
            lottery_periods TEXT,
            odds_raw TEXT,
            fetch_date TEXT,
            fetched_at TEXT,
            UNIQUE(source_match_id, fetch_date)
        )
    """)


def _fetch(url: str):
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            log.warning(f"HTTP {r.status_code}: {url}")
            return None
        return r.json()
    except Exception as e:
        log.warning(f"请求/解析失败 {url}: {e}")
        return None


def _parse(payload: dict, fetch_date: str) -> list[dict]:
    if not payload or "matches" not in payload:
        return []
    leagues = payload.get("leagues") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for m in payload["matches"]:
        try:
            status = str(m[2])
            if status != _FINISHED_STATUS:
                continue  # 未同步/未完场的占位数据不入库，见文件头坑点说明
            match_id = m[0]
            league_id = m[1]
            league_name = (leagues.get(str(league_id)) or leagues.get(league_id) or [None])[0]
            kickoff_utc = datetime.fromtimestamp(m[3], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            sport = _SPORT_MAP.get(str(m[19]), "unknown")
            home, away = m[5], m[6]
            rows.append({
                "source_match_id": match_id,
                "sport_code": sport,
                "league_id": league_id,
                "league_name": league_name,
                "status_code": status,
                "kickoff_utc": kickoff_utc,
                "home_team": home[1],
                "away_team": away[1],
                "home_score": home[2],
                "away_score": away[2],
                "home_score_ht": home[3],
                "away_score_ht": away[3],
                "home_corners": home[_HOME_CORNER_IDX] if sport == "football" else None,
                "away_corners": away[_HOME_CORNER_IDX] if sport == "football" else None,
                "fetch_date": fetch_date,
                "updated_at": now,
            })
        except (IndexError, TypeError, KeyError, OSError, ValueError) as e:
            log.debug(f"跳过解析失败的一场: {e}")
            continue
    return rows


def _parse_odds_snapshot(payload: dict, fetch_date: str) -> list[dict]:
    """跟_parse()不同：不过滤完场状态(赔率恰恰是赛前/未开赛时才有意义)，只挑
    出index32(赔率数组)/index10(彩票期号数组)至少有一项非空的场次——绝大多数
    比赛这两个字段是空的(不在官方彩票销售池里)，见文件头赔率覆盖率实测记录。"""
    if not payload or "matches" not in payload:
        return []
    leagues = payload.get("leagues") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for m in payload["matches"]:
        try:
            periods = [p for p in (m[10] or []) if p]
            odds_list = [o for o in (m[32] or []) if o]
            if not periods and not odds_list:
                continue
            match_id = m[0]
            league_id = m[1]
            league_name = (leagues.get(str(league_id)) or leagues.get(league_id) or [None])[0]
            kickoff_utc = datetime.fromtimestamp(m[3], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            sport = _SPORT_MAP.get(str(m[19]), "unknown")
            home, away = m[5], m[6]
            rows.append({
                "source_match_id": match_id,
                "sport_code": sport,
                "league_id": league_id,
                "league_name": league_name,
                "status_code": str(m[2]),
                "kickoff_utc": kickoff_utc,
                "home_team": home[1],
                "away_team": away[1],
                "lottery_periods": "|".join(periods),
                "odds_raw": "|".join(odds_list),
                "fetch_date": fetch_date,
                "fetched_at": now,
            })
        except (IndexError, TypeError, KeyError, OSError, ValueError) as e:
            log.debug(f"跳过解析失败的一场(赔率快照): {e}")
            continue
    return rows


def run_odds_snapshot(fetch_date: str | None = None) -> int:
    """每日赔率快照——供00_命中系统.py每日调度调用(Priority2，跟39/40/41号
    okooo爬虫同一批次)，只存数据攒样本，不参与任何推荐/预测计算，见
    qiumibao_odds_snapshot建表注释。同时查today_archive(今日临近/进行中)+
    today_future(未来赛程)两个端点，覆盖面比单查一个端点更全。"""
    fetch_date = fetch_date or datetime.now().strftime("%Y-%m-%d")
    init_tables()

    all_rows: dict[int, dict] = {}
    for path in ("today_archive_cn.htm", "today_future_cn.htm"):
        payload = _fetch(f"{_BASE}/{path}")
        for row in _parse_odds_snapshot(payload, fetch_date):
            all_rows[row["source_match_id"]] = row

    rows = list(all_rows.values())
    if not rows:
        log.info("本次无带赔率/彩票期号标记的场次")
        return 0

    tables = _get_tables()
    n = batch_upsert(engine, tables["qiumibao_odds_snapshot"], rows,
                      unique_keys=["source_match_id", "fetch_date"])
    log.info(f"共写入 {n} 场赔率快照（仅存档攒样本，未接入推荐逻辑）")
    return n


def run(fetch_date: str | None = None) -> int:
    fetch_date = fetch_date or datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    init_tables()

    all_rows: dict[int, dict] = {}

    # today_archive覆盖的滚动窗口是拿到真实完场比分的可靠源，始终抓一次
    payload = _fetch(f"{_BASE}/today_archive_cn.htm")
    for row in _parse(payload, fetch_date):
        all_rows[row["source_match_id"]] = row

    # 若目标日期不在today_archive的滚动窗口内(比如补抓几天前的历史日期)，
    # 改查指定日期端点兜底——同样只收完场(status_code='8')的行
    if fetch_date != today:
        payload2 = _fetch(f"{_BASE}/{fetch_date}_cn.htm")
        for row in _parse(payload2, fetch_date):
            all_rows.setdefault(row["source_match_id"], row)

    rows = list(all_rows.values())
    if not rows:
        log.info("本次无可写入的完场比赛数据")
        return 0

    tables = _get_tables()
    n = batch_upsert(engine, tables["qiumibao_match_results"], rows, unique_keys=["source_match_id"])
    log.info(f"共写入 {n} 场完场比赛（含比分/半场/角球字段，角球字段置信度见表注释）")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD，默认今日")
    ap.add_argument("--finished-only", action="store_true",
                     help="抓完场比分/半场/角球(供21_auto_settle.py结算管道用)，"
                          "不带此flag时默认跑赔率快照(供00_命中系统.py每日调度用，见文件头说明)")
    args = ap.parse_args()
    if args.finished_only:
        run(fetch_date=args.date)
    else:
        run_odds_snapshot(fetch_date=args.date)
