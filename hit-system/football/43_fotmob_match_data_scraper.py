# -*- coding: utf-8 -*-
"""
43_fotmob_match_data_scraper.py — FotMob 全量比赛数据爬虫
数据源: fotmob.com 非官方公开API（www.fotmob.com/api/data/...），无需登录/无Cloudflare拦截，
        curl_cffi 简单请求即可访问（已实测验证，不同于 fbref 需要 nodriver 真实浏览器）。

背景（2026-07-20）：22_fbref_scraper.py 的 xG 数据源已失效（fbref把schedule页xG列撤掉了，
详见00_命中系统.py里22号调度的停用注释）。排查FotMob替代方案时发现它不仅有xG，还有一整套
逐场高阶统计（控球/射门细分/传球/防守/对抗/体能）+ 逐次射门坐标 + 逐球员数据 + 阵容，
比fbref当年能提供的还全，因此不只做xG替代，直接做成全量比赛数据爬虫。

覆盖联赛（fbref付费墙/schedule页xG失效后新扩的13个非五大联赛 + 欧冠欧联，
逐一实测验证 shotmap.expectedGoals 字段确认真实有xG数据）：
    葡超/荷甲/土超/日职联/澳超/沙特联赛/印超/墨超/哥伦比亚甲/巴西乙/美职联/英冠/欧冠/欧联
另外中超、韩K联虽然FotMob没有xG模型（shotmap为空），但仍有基础团队统计（控球/射门/角球），
一并纳入抓取（这两联赛没有xG不是本脚本的bug，是数据源本身没覆盖）。

五大联赛+俄超(2026-07-21新增)：虽然 Understat(10_understat_xg_scraper.py) 已100%覆盖
这6个联赛的真实xG，但Understat只有xG一个字段，FotMob独有的角球/传球成功率/对抗/阵容/
逐次射门坐标等~40个字段这几个联赛完全没有替代来源(尤其角球市场需要英超等主流联赛
数据，之前排除掉的52联赛清单里角球覆盖的都是冷门联赛，没有五大联赛)。不会跟
Understat冲突：00_命中系统.py里get_fotmob_xg_probs()等FotMob信号函数只在
fotmob_1x2/fotmob_totals/fotmob_team_total这几个独立影子桶里调用，从来不进入
主流程poisson_probs融合(那里五大联赛该用Understat还是用Understat，两条路径
完全不相交)，FotMob的xG字段在这几个联赛只是"多存一份、影子桶专用"，不重复计入。

表:
    fotmob_matches            — 比赛结果 + 球队级xG汇总（场次级，主表）
    fotmob_match_team_stats   — 逐场逐队完整统计（控球/射门/传球/防守/对抗/体能等约40个字段
                                 + raw_stats_json兜底存全量原始分组，防止列映射遗漏）
    fotmob_shots              — 逐次射门（坐标+单次xG+是否射正+射门方式+比赛阶段）
    fotmob_player_match_stats — 逐球员逐场数据（评分/位置/进球助攻等关键字段
                                 + stats_json兜底存该球员完整嵌套统计）
    fotmob_lineups            — 逐场逐队阵容（阵型/教练/首发替补JSON/平均年龄/身价）

用法:
    python -X utf8 43_fotmob_match_data_scraper.py --date 2026-07-20
"""
import os, sys, re, time, json, logging, argparse
from datetime import datetime, timedelta, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from sqlalchemy import create_engine, text, MetaData
from curl_cffi import requests as cffi_requests

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl, batch_upsert

# 来源证据层（2026-10-09 专项）：原始响应留存 + 扩展字段 + 赛前/赛后统一解析
import source_evidence as SE
import fotmob_extract as FX

engine = create_engine(DB_ENGINE_URL)
log = logging.getLogger("fotmob_match_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE = "https://www.fotmob.com/api/data"

# ── 目标联赛：fotmob联赛id → 项目内统一联赛名 ──────────────────────────
# id 来自 fotmob.com/api/data/allLeagues 全量赛事索引（2026-07-20核对，五大联赛+俄超
# 的id于2026-07-21用同一接口二次核对，见下方"五大联赛+俄超"分组）。
# 下面这份是全量556个赛事逐一实测 shotmap.expectedGoals 后筛出的清单：
#   - 剔除各类杯赛/超级杯/资格赛/慈善表演赛（如FA Cup/Coppa Italia/Supercopa/
#     Qualification/Charity Match等，价值低且非常规联赛赛程，不纳入——2026-07-21
#     用户明确拍板只扩五大联赛+俄超，不做556个赛事的全量扩展）
#   - 保留常规主联赛+有实际竞技意义的国际赛事（欧冠/欧联/欧协联/欧洲杯/美洲解放者杯/
#     欧国联B-D组/女足欧洲杯）+ 女足联赛（项目本身已在追踪阿根廷女甲等女足联赛）
# 不要凭猜测改动，改动前先用该接口核对新id。
LEAGUES = {
    # 五大联赛+俄超(2026-07-21新增，理由见文件头部docstring)
    47: "England - Premier League",
    87: "Spain - LaLiga",
    55: "Italy - Serie A",
    54: "Germany - Bundesliga",
    53: "France - Ligue 1",
    63: "Russia - Premier League",
    10007: "Argentina - Copa de la Liga Profesional",
    112:   "Argentina - Liga Profesional",
    8965:  "Argentina - Primera B Nacional",
    113:   "Australia - A-League",
    9495:  "Australia - A-League Women",
    38:    "Austria - Bundesliga",
    40:    "Belgium - First Division A",
    264:   "Belgium - First Division B",
    10244: "Brazil - Paulista A1",
    268:   "Brazil - Serie A",
    8814:  "Brazil - Serie B",
    274:   "Colombia - Primera A",
    9125:  "Colombia - Primera B",
    46:    "Denmark - Superligaen",
    519:   "Egypt - Premier League",
    48:    "England - Championship",
    108:   "England - League One",
    109:   "England - League Two",
    9227:  "England - WSL",
    110:   "France - Ligue 2",
    9677:  "France - Premiere Ligue Feminine",
    146:   "Germany - 2. Bundesliga",
    135:   "Greece - Super League 1",
    9478:  "India - Super League",
    42:    "Europe - Champions League",
    10216: "Europe - Conference League",
    45:    "International - Copa Libertadores",
    50:    "International - EURO",
    # World Cup(2026-08-10新增)：此前LEAGUES字典里从未配置这个赛事ID，导致大量
    # 角球推荐(corner_recommendations)长期停留pending无法结算——实测id=77接口
    # 完全可用(104场2026世界杯，含已完赛比赛的真实比分/角球数据)，纯粹是调度
    # 遗漏，不是接口被封锁/无数据。联赛名沿用corner_recommendations历史记录里
    # 已经在用的"FIFA - World Cup"，避免模糊匹配对不上老记录。
    77:    "FIFA - World Cup",
    73:    "Europe - Europa League",
    9807:  "International - UEFA Nations League B",
    9808:  "International - UEFA Nations League C",
    9809:  "International - UEFA Nations League D",
    292:   "International - Women's EURO",
    126:   "Ireland - Premier Division",
    86:    "Italy - Serie B",
    223:   "Japan - J1 League",
    230:   "Mexico - Liga MX",
    57:    "Netherlands - Eredivisie",
    59:    "Norway - Eliteserien",
    196:   "Poland - Ekstraklasa",
    61:    "Portugal - Primeira Liga",
    536:   "Saudi Arabia - Pro League",
    64:    "Scotland - Premiership",
    10791: "Scotland - SWPL 1",
    537:   "South Africa - Premier Soccer League",
    140:   "Spain - LaLiga2",
    67:    "Sweden - Allsvenskan",
    69:    "Switzerland - Super League",
    8984:  "Thailand - Thai League",
    71:    "Turkey - Super Lig",
    130:   "USA - MLS",
    9134:  "USA - NWSL",
    # 无xG(FotMob本身没对这两个联赛跑xG模型)，但仍有控球/射门/角球等基础团队统计，
    # 仍值得抓——不是本脚本bug，是数据源没覆盖，详见开发时的实测记录
    120:   "China - Super League",
    9080:  "South Korea - K League 1",
}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


# Bug修复(2026-08-10)：原来_get_json()每次都调用_session()新建一个Session/
# 隐式新建一条独立TLS连接，跟37_corner_stats_scraper.py修复前是同一类问题——
# 高频对同一域名创建独立连接会触发"curl: TLS connect error:
# OPENSSL_internal:invalid library"崩溃(2026-08-10抓World Cup时104场只成功
# 19场、大量请求超时正是这个问题的表现，当时因为这里只有except Exception捕获+
# debug级别日志，没把具体报错打到警告级别，误判成了限流)。改成模块级复用
# 同一个Session对象，让libcurl内部连接池正常工作。
_SESSION = cffi_requests.Session(impersonate="chrome120")
_SESSION.headers.update({"User-Agent": _UA, "Accept": "application/json"})


def _get_json(url: str, retries: int = 4, base_delay: float = 1.5):
    for i in range(retries):
        try:
            r = _SESSION.get(url, timeout=25)
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    data = None
                if data is not None:
                    return data
        except Exception as e:
            log.debug(f"  GET失败({i+1}/{retries}): {url} — {e}")
        time.sleep(base_delay * (i + 1))
    return None


def _get_raw(url: str, retries: int = 4, base_delay: float = 1.5):
    """带证据采集的 GET：返回 (json_data, evidence)，evidence 含原始 body/哈希/观察时间/头部。

    与 _get_json 同源（复用同一 Session/重试节流），额外保留 provider 原始 bytes 供证据层入库。
    """
    for i in range(retries):
        started = SE.now_utc_iso()
        try:
            r = _SESSION.get(url, timeout=25)
            ev = {
                "url": url,
                "request_started_at_utc": started,
                "observed_at_utc": SE.now_utc_iso(),
                "http_status": r.status_code,
                "raw_body": r.text,
                "etag": r.headers.get("ETag"),
                "last_modified": r.headers.get("Last-Modified"),
                "content_type": r.headers.get("Content-Type"),
            }
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    data = None
                if data is not None:
                    return data, ev
            # 非 200 或无有效 JSON：保留本次证据并在重试后返回
            last_ev = ev
        except Exception as e:
            log.debug(f"  GET失败({i+1}/{retries}): {url} — {e}")
            last_ev = None
        time.sleep(base_delay * (i + 1))
    return None, locals().get("last_ev")


# P2：本次运行的请求计数（供采集运行日志收尾使用）
_FM_STATS = {"requests": 0, "requests_ok": 0, "requests_failed": 0,
             "bodies_new": 0, "bodies_deduplicated": 0}


def _get_json_ev(url: str, *, endpoint: str, source_match_id=None, source_league_id=None):
    """抓取 + 落地原始响应证据 + 分派回执，返回 (data, observed_at_utc, observation_id)。

    注意：**无论成功或失败都会写一条分派回执**（source_request_ledger），
    这才是「实际发生了多少次 HTTP 请求」的权威依据。
    """
    data, ev = _get_raw(url)
    observed_at = ev.get("observed_at_utc") if ev else SE.now_utc_iso()
    obs_id = None
    if ev:
        body = ev.get("raw_body")
        obs_id = SE.save_raw_response(
            engine, provider=SE.PROVIDER_FOTMOB, endpoint=endpoint,
            raw_body=body, source_match_id=source_match_id,
            source_league_id=source_league_id, request_url=url,
            request_started_at_utc=ev.get("request_started_at_utc"),
            observed_at_utc=observed_at, http_status=ev.get("http_status"),
            etag=ev.get("etag"), last_modified=ev.get("last_modified"),
            content_type=ev.get("content_type"),
            source_version=None,
            source_version_note="FotMob 未提供官方数据版本号；本地 sha256 仅为内容哈希，非官方版本",
        )
        SE.record_dispatch(
            engine, provider=SE.PROVIDER_FOTMOB, endpoint=endpoint,
            request_started_at_utc=ev.get("request_started_at_utc"),
            request_finished_at_utc=ev.get("observed_at_utc"), observed_at_utc=observed_at,
            http_status=ev.get("http_status"),
            outcome=SE.classify_outcome(ev.get("http_status")),
            response_sha256=SE.sha256_text(body or ""),
            response_bytes=len((body or "").encode("utf-8")),
            raw_response_id=obs_id,
            body_deduplicated=SE.body_was_deduplicated(engine, SE.PROVIDER_FOTMOB, obs_id),
            etag=ev.get("etag"), last_modified=ev.get("last_modified"),
            content_type=ev.get("content_type"), source_match_id=source_match_id,
            source_league_id=source_league_id, request_url=url)
        # ── P2 运行计数 ──
        _FM_STATS["requests"] += 1
        _code = ev.get("http_status")
        if _code is not None and 200 <= int(_code) < 300:
            _FM_STATS["requests_ok"] += 1
        else:
            _FM_STATS["requests_failed"] += 1
        if SE.body_was_deduplicated(engine, SE.PROVIDER_FOTMOB, obs_id):
            _FM_STATS["bodies_deduplicated"] += 1
        else:
            _FM_STATS["bodies_new"] += 1
    if not data:
        return None, None, obs_id
    return data, observed_at, obs_id


# ── 建表 ────────────────────────────────────────────────────────────────
def init_tables():
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS fotmob_matches (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id        INTEGER UNIQUE,
        league_id       INTEGER,
        league_name     TEXT,
        season          TEXT,
        match_date      TEXT,
        home_team       TEXT,
        away_team       TEXT,
        home_team_id    INTEGER,
        away_team_id    INTEGER,
        home_score      INTEGER,
        away_score      INTEGER,
        home_xg         REAL,
        away_xg         REAL,
        home_score_ht   INTEGER,
        away_score_ht   INTEGER,
        fetch_date      TEXT
    )""")
    # 存量表补列（2026-07-24新增：半全场市场需要半场比分，从matchDetails的进球事件
    # 反推，见 _extract_ht_score()）
    for _mig in [
        "ALTER TABLE fotmob_matches ADD COLUMN home_score_ht INTEGER",
        "ALTER TABLE fotmob_matches ADD COLUMN away_score_ht INTEGER",
    ]:
        try:
            exec_ddl(engine, _mig)
        except Exception:
            pass
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS fotmob_match_team_stats (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id                INTEGER,
        team_id                 INTEGER,
        side                    TEXT,
        possession_pct          REAL,
        total_shots             REAL,
        shots_on_target         REAL,
        shots_off_target        REAL,
        blocked_shots           REAL,
        hit_woodwork            REAL,
        shots_inside_box        REAL,
        shots_outside_box       REAL,
        big_chances             REAL,
        big_chances_missed      REAL,
        touches_opp_box         REAL,
        xg                      REAL,
        xg_open_play            REAL,
        xg_set_play             REAL,
        xg_non_penalty          REAL,
        xgot                    REAL,
        distance_covered        REAL,
        walking_distance        REAL,
        running_distance        REAL,
        sprint_distance         REAL,
        num_sprints             REAL,
        passes_total            REAL,
        accurate_passes         REAL,
        accurate_passes_pct     REAL,
        passes_own_half         REAL,
        passes_opp_half         REAL,
        accurate_long_balls     REAL,
        accurate_long_balls_pct REAL,
        accurate_crosses        REAL,
        accurate_crosses_pct    REAL,
        throws                  REAL,
        offsides                REAL,
        tackles                 REAL,
        interceptions           REAL,
        blocks                  REAL,
        clearances              REAL,
        keeper_saves            REAL,
        duels_won               REAL,
        ground_duels_won        REAL,
        ground_duels_won_pct    REAL,
        aerial_duels_won        REAL,
        aerial_duels_won_pct    REAL,
        successful_dribbles     REAL,
        successful_dribbles_pct REAL,
        yellow_cards            REAL,
        red_cards               REAL,
        fouls_committed         REAL,
        corners                 REAL,
        raw_stats_json          TEXT,
        UNIQUE(match_id, team_id)
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS fotmob_shots (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id                INTEGER,
        shot_id                 INTEGER,
        team_id                 INTEGER,
        player_id               INTEGER,
        player_name             TEXT,
        minute                  INTEGER,
        min_added               INTEGER,
        x                       REAL,
        y                       REAL,
        expected_goals          REAL,
        expected_goals_on_target REAL,
        is_on_target            INTEGER,
        is_blocked              INTEGER,
        shot_type               TEXT,
        situation               TEXT,
        period                  TEXT,
        is_own_goal             INTEGER,
        event_type              TEXT,
        UNIQUE(shot_id)
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS fotmob_player_match_stats (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id        INTEGER,
        player_id       INTEGER,
        player_name     TEXT,
        team_id         INTEGER,
        is_goalkeeper   INTEGER,
        usual_position  TEXT,
        rating          REAL,
        minutes_played  REAL,
        goals           REAL,
        assists         REAL,
        stats_json      TEXT,
        UNIQUE(match_id, player_id)
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS fotmob_lineups (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id                INTEGER,
        team_id                 INTEGER,
        side                    TEXT,
        formation               TEXT,
        coach_name              TEXT,
        avg_starter_age         REAL,
        total_starter_mkt_value REAL,
        starters_json           TEXT,
        subs_json               TEXT,
        UNIQUE(match_id, team_id)
    )""")
    log.info("✅ FotMob 全量数据表初始化完成")
    # 来源证据层表/视图（幂等新增，不动既有表）
    SE.create_evidence_tables(engine)


# ── 团队统计字段名归一化 ──────────────────────────────────────────────
# key: fotmob显示的英文标题(小写) → 表列名。未命中的标题不会丢失——
# 完整原始分组另存 raw_stats_json，供以后扩展列时回填。
_STAT_TITLE_MAP = {
    "ball possession": "possession_pct",
    "expected goals (xg)": "xg",
    "total shots": "total_shots",
    "shots on target": "shots_on_target",
    "shots off target": "shots_off_target",
    "blocked shots": "blocked_shots",
    "hit woodwork": "hit_woodwork",
    "shots inside box": "shots_inside_box",
    "shots outside box": "shots_outside_box",
    "big chances": "big_chances",
    "big chances missed": "big_chances_missed",
    "touches in opposition box": "touches_opp_box",
    "xg open play": "xg_open_play",
    "xg set play": "xg_set_play",
    "xg non-penalty": "xg_non_penalty",
    "xg on target (xgot)": "xgot",
    "distance covered": "distance_covered",
    "walking distance": "walking_distance",
    "running distance": "running_distance",
    "sprinting distance": "sprint_distance",
    "number of sprints": "num_sprints",
    "passes": "passes_total",
    "accurate passes": "accurate_passes",
    "own half": "passes_own_half",
    "opposition half": "passes_opp_half",
    "accurate long balls": "accurate_long_balls",
    "accurate crosses": "accurate_crosses",
    "throws": "throws",
    "offsides": "offsides",
    "tackles": "tackles",
    "interceptions": "interceptions",
    "blocks": "blocks",
    "clearances": "clearances",
    "keeper saves": "keeper_saves",
    "duels won": "duels_won",
    "ground duels won": "ground_duels_won",
    "aerial duels won": "aerial_duels_won",
    "successful dribbles": "successful_dribbles",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
    "fouls committed": "fouls_committed",
    "corners": "corners",
}
# 这些字段的值是 "123 (45%)" 这种格式，取百分比部分（fractionWithPercentage）
_PCT_FIELDS = {
    "accurate_passes", "accurate_long_balls", "accurate_crosses",
    "ground_duels_won", "aerial_duels_won", "successful_dribbles",
}


def _parse_stat_value(col: str, raw):
    """把 '809 (91%)' / '1.72' / 21 这类原始值解析成 (count_or_value, pct_or_None)"""
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    s = str(raw).strip()
    m = re.match(r"^([\d.]+)\s*\((\d+)%\)$", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    try:
        return float(s), None
    except ValueError:
        return None, None


def _extract_team_stats(stats_content: dict, match_id, home_id, away_id) -> list:
    """解析 content.stats.Periods.All.stats，返回 [home_row_dict, away_row_dict]"""
    # 安全取值：赛前(prematch)比赛 stats 为空，FotMob 可能返回
    # {"Periods": {"All": None}} —— 中间任何一级为 None 都要归一为 {}/[]，
    # 否则 .get(...) 链会在 None 上 AttributeError（2026-10-11 修复）。
    _periods = (stats_content or {}).get("Periods") or {}
    _all = _periods.get("All") or {}
    groups = _all.get("stats") or []
    home_row = {"match_id": match_id, "team_id": home_id, "side": "home"}
    away_row = {"match_id": match_id, "team_id": away_id, "side": "away"}
    for g in groups:
        for s in g.get("stats", []):
            vals = s.get("stats")
            if not vals or vals == [None, None]:
                continue
            title = (s.get("title") or "").strip().lower()
            col = _STAT_TITLE_MAP.get(title)
            if not col:
                continue
            hv, hp = _parse_stat_value(col, vals[0])
            av, ap = _parse_stat_value(col, vals[1])
            if col in _PCT_FIELDS:
                home_row[col] = hv
                home_row[col + "_pct"] = hp if hp is not None else home_row.get(col + "_pct")
                away_row[col] = av
                away_row[col + "_pct"] = ap if ap is not None else away_row.get(col + "_pct")
            else:
                home_row[col] = hv
                away_row[col] = av
    raw_json = json.dumps(groups, ensure_ascii=False)
    home_row["raw_stats_json"] = raw_json
    away_row["raw_stats_json"] = raw_json
    return [home_row, away_row]


def _extract_shots(shotmap: dict, match_id) -> list:
    shots = (shotmap or {}).get("shots", []) or []
    rows = []
    for sh in shots:
        rows.append({
            "match_id": match_id,
            "shot_id": sh.get("id"),
            "team_id": sh.get("teamId"),
            "player_id": sh.get("playerId"),
            "player_name": sh.get("playerName") or sh.get("fullName"),
            "minute": sh.get("min"),
            "min_added": sh.get("minAdded"),
            "x": sh.get("x"),
            "y": sh.get("y"),
            "expected_goals": sh.get("expectedGoals"),
            "expected_goals_on_target": sh.get("expectedGoalsOnTarget"),
            "is_on_target": 1 if sh.get("isOnTarget") else 0,
            "is_blocked": 1 if sh.get("isBlocked") else 0,
            "shot_type": sh.get("shotType"),
            "situation": sh.get("situation"),
            "period": sh.get("period"),
            "is_own_goal": 1 if sh.get("isOwnGoal") else 0,
            "event_type": sh.get("eventType"),
        })
    return rows


def _extract_players(player_stats: dict, match_id) -> list:
    rows = []
    for pid, p in (player_stats or {}).items():
        top = None
        for g in p.get("stats", []) or []:
            if g.get("key") == "top_stats":
                top = g.get("stats", {})
                break

        def _v(name):
            if not top or name not in top:
                return None
            return (top[name].get("stat") or {}).get("value")

        rows.append({
            "match_id": match_id,
            "player_id": p.get("id"),
            "player_name": p.get("name"),
            "team_id": p.get("teamId"),
            "is_goalkeeper": 1 if p.get("isGoalkeeper") else 0,
            "usual_position": p.get("usualPosition"),
            "rating": _v("FotMob rating"),
            "minutes_played": _v("Minutes played"),
            "goals": _v("Goals"),
            "assists": _v("Assists"),
            "stats_json": json.dumps(p.get("stats", []), ensure_ascii=False),
        })
    return rows


def _extract_lineups(lineup: dict, match_id, home_id, away_id) -> list:
    rows = []
    for side, tid in (("home", home_id), ("away", away_id)):
        team = (lineup or {}).get(f"{side}Team", {}) or {}
        if not team:
            continue
        rows.append({
            "match_id": match_id,
            "team_id": tid,
            "side": side,
            "formation": team.get("formation"),
            "coach_name": (team.get("coach") or {}).get("name") if isinstance(team.get("coach"), dict) else team.get("coach"),
            "avg_starter_age": team.get("averageStarterAge"),
            "total_starter_mkt_value": team.get("totalStarterMarketValue"),
            "starters_json": json.dumps(team.get("starters", []), ensure_ascii=False),
            "subs_json": json.dumps(team.get("subs", []), ensure_ascii=False),
        })
    return rows


def _extract_ht_score(content: dict) -> tuple:
    """从进球事件反推半场比分(主队/客队上半场各进几球)。2026-07-24新增，半全场(HT/FT)
    市场需要半场比分，FotMob没有现成的"半场比分"字段，但每个进球事件(Goal)自带
    isHome和shotmapEvent.period(FirstHalf/SecondHalf)，比猜测嵌入协议字段代号
    (见09_flashscore_schedule_scraper.py的教训)可靠得多。
    - 乌龙球(ownGoal=true)不需要额外反转isHome：实测确认FotMob的isHome字段本身
      已经是"这个球算在哪一方账上"（乌龙球事件的isHome已经指向受益方，不是乌龙
      球员所在队），一度按"乌龙球该反转"的直觉加了反转逻辑，结果验证时发现某场
      0-4比赛被反推出主队半场1-1（半场比分比全场还高，物理不可能），查明是反转
      逻辑把已经算好的账又反了一次，现已去掉反转，直接信任isHome。
    - 少数进球事件缺shotmapEvent.period(实测存在)，退化用time<=45分钟判断上半场
      (常规比赛上半场伤停补时也算在45分钟标记里，第二半场不会早于46分钟开始)。
    没有任何进球事件时返回(0, 0)（0-0战平也是合法的半场比分，不是"未知"）。
    events列表本身缺失/取不到时返回(None, None)，调用方应视为无法判定。"""
    events = ((content or {}).get("matchFacts", {}) or {}).get("events", {}) or {}
    event_list = events.get("events")
    if event_list is None:
        return None, None

    hs_ht = as_ht = 0
    for e in event_list:
        if e.get("type") != "Goal":
            continue
        period = (e.get("shotmapEvent") or {}).get("period")
        if period is None:
            is_first_half = (e.get("time") or 0) <= 45
        else:
            is_first_half = (period == "FirstHalf")
        if not is_first_half:
            continue
        if e.get("isHome"):
            hs_ht += 1
        else:
            as_ht += 1
    return hs_ht, as_ht


# ── 抓取单场比赛完整数据并入库 ────────────────────────────────────────
def _existing_identity(match_id):
    """取既有身份行中**需要跨次保留**的字段。

    ★2026-10-09 修复：此前只保留 first_seen_utc / schedule_change_history，
      导致重复抓取（如 lineup 轮询）把已解析的 season_id/season_name **覆盖回 NULL**。
      现在一并保留：赛季身份、首次观察时间、赛程变更历史。
    """
    try:
        with engine.connect() as conn:
            r = conn.execute(text(
                "SELECT first_seen_utc, schedule_change_history, season_id, season_name"
                " FROM fotmob_match_identity WHERE match_id=:m"), {"m": match_id}).fetchone()
    except Exception:
        return None
    if not r:
        return None
    return {"first_seen_utc": r[0], "schedule_change_history": r[1],
            "season_id": r[2], "season_name": r[3]}


def fetch_and_save_match(match_id: int, league_id=None, league_name: str = None,
                         season: str = None, fetch_date: str = None,
                         league_code=None, season_id=None) -> bool:
    """抓取单场 matchDetails：写既有 5 张表（向后兼容）+ 证据层 5 张扩展表。"""
    data, observed_at, obs_id = _get_json_ev(
        f"{BASE}/matchDetails?matchId={match_id}",
        endpoint="matchDetails", source_match_id=match_id, source_league_id=league_id)
    if not data:
        return False

    general = data.get("general", {}) or {}
    content = data.get("content", {}) or {}
    home = general.get("homeTeam", {}) or {}
    away = general.get("awayTeam", {}) or {}
    header_teams = (data.get("header", {}) or {}).get("teams", []) or []
    home_score = header_teams[0].get("score") if len(header_teams) > 0 else None
    away_score = header_teams[1].get("score") if len(header_teams) > 1 else None
    home_id, away_id = home.get("id"), away.get("id")

    # ── 身份/来源证据（先解析，作为 match_row 的权威来源） ──
    identity = FX.extract_identity(
        data, league_id=league_id, league_code=league_code, league_name=league_name,
        season_name=season, season_id=season_id, source_endpoint="matchDetails",
        observed_at_utc=observed_at, observation_id=obs_id, prev=_existing_identity(match_id))

    team_stats = _extract_team_stats(content.get("stats", {}), match_id, home_id, away_id)
    xg_by_team = {r["team_id"]: r.get("xg") for r in team_stats}
    home_score_ht, away_score_ht = _extract_ht_score(content)

    match_row = {
        "match_id": match_id,
        "league_id": league_id or identity.get("league_id"),
        "league_name": league_name or identity.get("league_name"),
        "season": season or identity.get("season_name"),
        "match_date": general.get("matchTimeUTC") or identity.get("kickoff_utc_raw"),
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "home_xg": xg_by_team.get(home_id),
        "away_xg": xg_by_team.get(away_id),
        "home_score_ht": home_score_ht,
        "away_score_ht": away_score_ht,
        "fetch_date": fetch_date,
    }

    shot_rows = _extract_shots(content.get("shotmap", {}), match_id)
    player_rows = _extract_players(content.get("playerStats", {}), match_id)
    lineup_rows = _extract_lineups(content.get("lineup", {}), match_id, home_id, away_id)

    # ── 既有 5 张「比赛结果」表：仅对已开赛/已完赛写入 ──
    # 赛前比赛没有比分/射门/xG，写进结果表会与赛后数据混淆（违反「不混淆赛前与赛后」原则）。
    # 赛前数据一律落在证据层（fotmob_match_identity / fotmob_lineup_players / fotmob_raw_responses）。
    is_prematch = (identity.get("match_state") == "prematch")
    if not is_prematch:
        md = MetaData()
        md.reflect(bind=engine, only=[
            "fotmob_matches", "fotmob_match_team_stats", "fotmob_shots",
            "fotmob_player_match_stats", "fotmob_lineups",
        ])
        batch_upsert(engine, md.tables["fotmob_matches"], [match_row], unique_keys=["match_id"])
        batch_upsert(engine, md.tables["fotmob_match_team_stats"], team_stats, unique_keys=["match_id", "team_id"])
        if shot_rows:
            batch_upsert(engine, md.tables["fotmob_shots"], shot_rows, unique_keys=["shot_id"])
        if player_rows:
            batch_upsert(engine, md.tables["fotmob_player_match_stats"], player_rows, unique_keys=["match_id", "player_id"])
        if lineup_rows:
            batch_upsert(engine, md.tables["fotmob_lineups"], lineup_rows, unique_keys=["match_id", "team_id"])
    else:
        log.debug(f"  match {match_id}: 赛前状态，仅写证据层（不写结果表）")

    # ── 证据层扩展表（新增，失败不影响主流程） ──
    try:
        SE.write_rows(engine, "fotmob_match_identity", [identity], ["match_id"])
        SE.write_rows(engine, "fotmob_match_stats_raw",
                      FX.extract_stats_raw(content.get("stats", {}), match_id, home_id, away_id,
                                           observed_at, obs_id),
                      ["match_id", "team_id", "period", "group_key", "stat_key", "stat_title"])
        SE.write_rows(engine, "fotmob_match_events",
                      FX.extract_events(content, match_id, observed_at, obs_id),
                      ["match_id", "event_key"])
        # ★2026-10-09 落库补全：比赛天气（shotmap 改为复用既有 fotmob_shots）
        _raw_sha = SE.sha256_text(json.dumps(data, ensure_ascii=False, sort_keys=True))
        _wx = FX.extract_weather(content, match_id, observed_at, obs_id, _raw_sha)
        if _wx:
            SE.write_rows(engine, "fotmob_match_weather", _wx, ["match_id"])
        # ★2026-10-09 修正：逐射门**不建新表** —— 既有 `fotmob_shots`（39 万行，含 xG/xGOT）
        #   已完整覆盖该需求（V3 矩阵亦指向它）。此前误建 fotmob_shotmap 属重复，已废弃。
        #   注：fotmob_shots 由主流程的 shot_rows 路径写入（见上方 batch_upsert），此处无需重复。
        # ★落库补全：近期战绩 + 历史交锋（form / 对手强度特征基础）
        _tf = FX.extract_team_form(content, match_id, home_id, away_id, observed_at, obs_id, _raw_sha)
        if _tf:
            SE.write_rows(engine, "fotmob_team_form", _tf, ["row_key"])
        _h2h = FX.extract_h2h(content, match_id, observed_at, obs_id, _raw_sha)
        if _h2h:
            SE.write_rows(engine, "fotmob_h2h_matches", _h2h, ["row_key"])
        SE.write_rows(engine, "fotmob_lineup_players",
                      FX.extract_lineup_players(content.get("lineup", {}), match_id, home_id, away_id,
                                                observed_at, obs_id,
                                                match_started=bool(identity.get("started"))),
                      ["match_id", "team_id", "lineup_type", "player_id"])
        avail = FX.extract_availability(content, match_id, home_id, away_id, observed_at, obs_id)
        if not avail:
            avail = [FX.availability_placeholder(match_id, home_id, away_id, observed_at, obs_id)]
        SE.write_rows(engine, "fotmob_match_availability", avail,
                      ["match_id", "team_id", "player_id", "availability_type"])
        # ★2026-10-09 修正：真实伤停/停赛同时写入 Task D 规范表 player_availability
        #   （来源路径 content.lineup.*.unavailable[].unavailability，此前误判为「来源不提供」）
        if avail and avail[0].get("provided") == 1:
            SE.upsert_availability(engine, [dict(
                provider=SE.PROVIDER_FOTMOB,
                source_team_id=None if a.get("team_id") is None else str(a["team_id"]),
                source_player_id=None if a.get("player_id") is None else str(a["player_id"]),
                source_event_id=str(match_id),
                player_name=a.get("player_name"), team_name=None,
                injury_type=a.get("availability_type"),
                injury_description=a.get("injury_description"),
                suspension_type=a.get("suspension_type"),
                availability_status=a.get("status"),
                sidelined_start_at=None,
                expected_return_at=a.get("expected_return_date") or a.get("expected_return_text"),
                actual_return_at=None, source_updated_at=a.get("source_updated_at"),
                observed_at_utc=a.get("observed_at_utc"), first_seen_status="PROVEN",
                receipt_id=a.get("observation_id"), provided=1,
                source_json=a.get("source_json"), notes=a.get("null_reasons"),
                side=a.get("side"), age=a.get("age"), position_id=a.get("position_id"),
                country_code=a.get("country_code"), country_name=a.get("country_name"),
                market_value=a.get("market_value"), injury_id=a.get("injury_id"),
                expected_return_text=a.get("expected_return_text"),
                expected_return_date=a.get("expected_return_date"),
                null_reasons=a.get("null_reasons")) for a in avail])
    except Exception as e:
        log.warning(f"  match {match_id}: 证据层写入异常（主表已入库）— {e}")
    return True


def _already_have(match_id: int) -> bool:
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT 1 FROM fotmob_matches WHERE match_id=:mid"
        ), {"mid": match_id}).fetchone()
    return row is not None


def _needs_refresh(match_id: int, max_age_hours: float = 6.0) -> bool:
    """赛前刷新判定：无身份记录 / 未完赛 / 距上次观察超过 max_age_hours → 需要刷新。"""
    try:
        with engine.connect() as conn:
            r = conn.execute(text(
                "SELECT match_state, last_seen_utc FROM fotmob_match_identity WHERE match_id=:m"),
                {"m": match_id}).fetchone()
    except Exception:
        return True
    if not r:
        return True
    state, last_seen = r[0], r[1]
    if state == "finished":
        return False
    if not last_seen:
        return True
    try:
        t = datetime.strptime(last_seen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return (datetime.now(timezone.utc) - t).total_seconds() > max_age_hours * 3600


def _upcoming(m: dict, now: datetime, past_hours: float = 3.0, future_days: float = 14.0) -> bool:
    raw = (m.get("status") or {}).get("utcTime") or m.get("utcTime")
    k = SE.normalize_kickoff_utc(raw)
    if not k:
        return False
    try:
        t = datetime.strptime(k, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return (-past_hours * 3600) <= (t - now).total_seconds() <= (future_days * 86400)


def _league_meta(d: dict):
    details = d.get("details", {}) or {}
    season = details.get("selectedSeason") or ""
    season_id = details.get("selectedSeasonId") or details.get("seasonId")
    league_code = details.get("code") or details.get("leagueCode")
    return season, (str(season_id) if season_id is not None else None), league_code


def scrape_league(league_id: int, league_name: str, fetch_date: str, max_matches: int = 400,
                  scope: str = "finished", max_age_hours: float = 6.0,
                  future_days: float = 14.0, past_hours: float = 3.0):
    d, _oa, _oi = _get_json_ev(f"{BASE}/leagues?id={league_id}", endpoint="leagues",
                               source_league_id=league_id)
    if not d:
        log.warning(f"  {league_name}: 联赛接口获取失败")
        return 0
    allm = (d.get("fixtures", {}) or {}).get("allMatches", []) or []
    season, season_id, league_code = _league_meta(d)

    if scope == "prematch":
        now = datetime.now(timezone.utc)
        targets = [m for m in allm
                   if not (m.get("status", {}) or {}).get("finished")
                   and _upcoming(m, now, past_hours=past_hours, future_days=future_days)]
        log.info(f"  {league_name}: 未开赛/进行中 {len(targets)} 场（赛季 {season}，窗口 {future_days}天）")
    else:
        finished = [m for m in allm if (m.get("status", {}) or {}).get("finished")]
        # Bug修复(2026-07-21)：默认赛季0场完赛时改用上一已完成赛季重试
        if not finished:
            _avail = d.get("allAvailableSeasons") or []
            if len(_avail) >= 2 and season and season in _avail:
                _cur_idx = _avail.index(season)
                if _cur_idx + 1 < len(_avail):
                    _prev_season = _avail[_cur_idx + 1]
                    d2, _oa2, _oi2 = _get_json_ev(
                        f"{BASE}/leagues?id={league_id}&season={_prev_season}",
                        endpoint="leagues", source_league_id=league_id)
                    if d2:
                        allm2 = (d2.get("fixtures", {}) or {}).get("allMatches", []) or []
                        finished2 = [m for m in allm2 if (m.get("status", {}) or {}).get("finished")]
                        if finished2:
                            allm, season, finished = allm2, _prev_season, finished2
                            season_id = (_league_meta(d2)[1]) or season_id
                            league_code = (_league_meta(d2)[2]) or league_code
                            log.info(f"  {league_name}: 默认赛季0场完赛，改用上一赛季 {_prev_season}")
        targets = finished
        log.info(f"  {league_name}: 本赛季 {len(finished)} 场已完赛 / 共 {len(allm)} 场")

    saved = 0
    for m in targets[:max_matches]:
        mid = m.get("id")
        if not mid:
            continue
        need = _needs_refresh(mid, max_age_hours) if scope == "prematch" else (not _already_have(mid))
        if not need:
            continue
        ok = fetch_and_save_match(mid, league_id, league_name, season, fetch_date,
                                  league_code=league_code, season_id=season_id)
        if ok:
            saved += 1
        time.sleep(0.5)
    log.info(f"  {league_name}: 新写入/刷新 {saved} 场完整数据")
    return saved


def fetch_one(match_id: int, fetch_date: str = None) -> bool:
    """显式单场抓取（用户授权范围内的 target-only 调用）。"""
    fetch_date = fetch_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    init_tables()
    ok = fetch_and_save_match(match_id, None, None, None, fetch_date)
    log.info(f"target match {match_id}: {'OK' if ok else 'FAILED'}")
    return ok


def backfill_identity(fetch_date: str, limit: int = 500) -> int:
    """为既有 fotmob_matches 行回填身份/证据表（可选、分批、可控，避免一次全量重抓）。"""
    init_tables()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT m.match_id, m.league_id, m.league_name, m.season FROM fotmob_matches m "
            "LEFT JOIN fotmob_match_identity i ON i.match_id=m.match_id "
            "WHERE i.match_id IS NULL ORDER BY m.match_id DESC LIMIT :n"), {"n": limit}).fetchall()
    n = 0
    for mid, lid, lname, season in rows:
        if fetch_and_save_match(mid, lid, lname, season, fetch_date):
            n += 1
        time.sleep(0.3)
    log.info(f"身份回填完成：{n}/{len(rows)}")
    return n


def run(fetch_date: str | None = None, scope: str = "finished", max_age_hours: float = 6.0,
        future_days: float = 14.0, past_hours: float = 3.0, leagues=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime("%Y-%m-%d")
    init_tables()
    _leagues = leagues if leagues is not None else LEAGUES
    log.info(f"=== FotMob 全量比赛数据抓取 [{fetch_date}] | scope={scope} | {len(_leagues)} 个联赛 ===")
    # ── P2 采集运行日志：由爬虫自写，直调/subprocess 也留痕 ──
    _run_id = SE.begin_collection_run(
        engine, provider=SE.PROVIDER_FOTMOB, script="43_fotmob_match_data_scraper.py",
        scope=f"{scope}|leagues={len(_leagues)}|future_days={future_days}|past_hours={past_hours}",
        args={"fetch_date": fetch_date, "scope": scope, "max_age_hours": max_age_hours,
              "future_days": future_days, "past_hours": past_hours})
    _run_started = SE.now_utc_iso()
    for _k in _FM_STATS:
        _FM_STATS[_k] = 0
    total = 0
    _league_errors = 0
    for lid, name in _leagues.items():
        try:
            total += scrape_league(lid, name, fetch_date, scope=scope, max_age_hours=max_age_hours,
                                   future_days=future_days, past_hours=past_hours)
        except Exception as e:
            _league_errors += 1
            log.warning(f"  {name}: 抓取异常 — {e}")
            # 异常审计：联赛级失败也留痕（区分"正常空结果"与"抓取故障"）
            SE.record_exception(engine, provider=SE.PROVIDER_FOTMOB, run_id=_run_id,
                                severity="error", category="league_scrape",
                                exception_type=type(e).__name__, message=str(e),
                                source_entity_id=lid, context={"league_name": name,
                                                               "fetch_date": fetch_date, "scope": scope})
    log.info(f"✅ FotMob 全量数据抓取完成，共写入/刷新 {total} 场")
    SE.finish_collection_run(
        engine, _run_id,
        status=("partial" if _league_errors else "ok"),
        blocked_reason=("league_errors" if _league_errors else None),
        started_at_utc=_run_started,
        requests_total=_FM_STATS.get("requests"), requests_ok=_FM_STATS.get("requests_ok"),
        requests_failed=_FM_STATS.get("requests_failed"),
        bodies_new=_FM_STATS.get("bodies_new"), bodies_deduplicated=_FM_STATS.get("bodies_deduplicated"),
        rows_written={"matches_touched": total},
        notes=f"league_errors={_league_errors}")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD")
    parser.add_argument("--match-id", type=int, default=None,
                        help="仅抓取指定 FotMob match id（target-only，用户显式授权）")
    parser.add_argument("--scope", choices=["finished", "prematch", "all"], default="finished",
                        help="finished=已完赛（默认，行为不变）；prematch=未开赛/进行中；all=两者")
    parser.add_argument("--max-age-hours", type=float, default=6.0, help="赛前刷新最小间隔（小时）")
    parser.add_argument("--future-days", type=float, default=14.0, help="赛前窗口：未来 N 天内的未完赛比赛")
    parser.add_argument("--past-hours", type=float, default=3.0, help="赛前窗口：已开赛但未完赛 N 小时内")
    parser.add_argument("--league-ids", default=None,
                        help="逗号分隔的 FotMob 联赛 id（限定范围，如 47=英超）；默认全部 61 个")
    parser.add_argument("--backfill-identity", type=int, default=None,
                        help="为既有比赛回填身份/证据表，参数为本次上限条数")
    args = parser.parse_args()
    if args.match_id:
        sys.exit(0 if fetch_one(args.match_id, args.date) else 1)
    _sel = None
    if args.league_ids:
        _wanted = {int(x) for x in args.league_ids.split(",") if x.strip()}
        _sel = {k: v for k, v in LEAGUES.items() if k in _wanted}
    if args.backfill_identity:
        backfill_identity(args.date or datetime.now().strftime("%Y-%m-%d"), args.backfill_identity)
        sys.exit(0)
    if args.scope == "all":
        run(fetch_date=args.date, scope="prematch", max_age_hours=args.max_age_hours,
            future_days=args.future_days, past_hours=args.past_hours, leagues=_sel)
        run(fetch_date=args.date, scope="finished", max_age_hours=args.max_age_hours,
            future_days=args.future_days, past_hours=args.past_hours, leagues=_sel)
    else:
        run(fetch_date=args.date, scope=args.scope, max_age_hours=args.max_age_hours,
            future_days=args.future_days, past_hours=args.past_hours, leagues=_sel)
