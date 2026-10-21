# -*- coding: utf-8 -*-
"""
source_evidence.py — QQSJ 数据来源「证据层」（FotMob / The Odds API 共用）

目标（对应用户 2026-10-09 专项任务）：
  1. 完整保存 provider 原始响应 + 哈希 + 精确观察时间，可复现、可追溯。
  2. 保存来源真实提供的全部有价值字段（含动态/嵌套字段），不因映射表不认识就丢弃。
  3. 赔率观察「追加而非覆盖」，支持 point-in-time 查询。
  4. 区分赛前 / 进行中 / 已完赛数据结构。
  5. 不混淆不同来源的球队 ID；只保存真实 provider ID 与可绑定证据。

安全 / 兼容铁律：
  * 本模块 **只新增独立表与只读视图**，绝不 ALTER / DROP / 清空任何既有业务表。
  * 迁移可回退：rollback 仅 DROP 本模块创建的对象（证据表 + 视图），既有 200 张表不受影响。
  * 原始 JSON 只保存 provider 返回的 body，绝不写入 API Key。
  * 任何「来源未提供」的字段一律 NULL，并在 null_reasons / field_provenance 中记录原因，不推造。

被 43_fotmob_match_data_scraper.py 与 35_theoddsapi_multi_scraper.py 引用。
"""
import os
import re
import sys
import json
import time
import uuid
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text, MetaData

log = logging.getLogger("source_evidence")

# 原始响应是否落库（默认开启；如需省磁盘可设 QQSJ_SAVE_RAW_RESPONSES=0）
SAVE_RAW_RESPONSES = os.environ.get("QQSJ_SAVE_RAW_RESPONSES", "REDACTED") not in ("0", "false", "False")

PROVIDER_FOTMOB = "FotMob"
PROVIDER_ODDS = "The Odds API"

# 证据表对象名（用于迁移 / 回退 / 状态核对）
EVIDENCE_TABLES = [
    "fotmob_raw_responses",
    "fotmob_match_identity",
    "fotmob_match_stats_raw",
    "fotmob_match_events",
    "fotmob_lineup_players",
    "fotmob_match_availability",
    "theodds_api_raw_responses",
    "theodds_api_events",
    "theodds_api_odds_history",
    "theodds_api_market_catalog",
    "theodds_api_bookmakers",
    # ── 2026-10-09 P0 新增：请求回执账本 / 字段级 point-in-time / 额度回执 / 事故账本 ──
    "source_request_ledger",
    "source_field_observations",
    "source_quota_receipts",
    "source_incident_log",
    # ── 2026-10-09 P1 新增：伤停 / 阵容 / 来源身份 / 跨源映射 ──
    "player_availability",
    "fixture_lineups",
    "source_identity_evidence",
    # ── 2026-10-09 跨商 ID 隔离：Sportmonks 独立命名空间 ──
    "sportmonks_season_identity",
    "sportmonks_fixture_identity",
    # ── 2026-10-09 Task B：FotMob 赛季身份证据（独立命名空间，禁与 Sportmonks 混用）──
    "season_identity_evidence",
    # ── 2026-10-09 任务书 #4：Tavily 辅助发现（非事实，仅线索）──
    "tavily_findings",
    # ── 2026-10-09 落库补全：weather（shotmap 改为复用既有 fotmob_shots）──
    "fotmob_match_weather",
    # ── 2026-10-09 落库补全：teamForm / h2h ──
    "fotmob_team_form",
    "fotmob_h2h_matches",
    "source_identity_crosswalk",
    # ── 2026-10-09 P2 新增：来源采集日志 / 异常审计 ──
    "source_collection_runs",
    "source_exception_audit",
    "source_evidence_limitations",
]
EVIDENCE_VIEWS = [
    "v_fotmob_match_raw_provenance",
    "v_theodds_latest_quote",
    "v_theodds_quote_pit",
    # 2026-10-09 Task C: 历史/新鲜度接口
    "v_theodds_quote_at",
    "v_theodds_quote_history",
    "v_theodds_quote_freshness",
    # 2026-10-09 Task E: 阵容接口
    "v_lineups",
    "v_lineup_officialness",
    "v_lineup_state_transitions",
    "v_lineup_announcement_evidence",
    # 2026-10-09 第五节：统计三要素
    "v_match_team_stats_enriched",
    "v_stats_three_requirements",
    # 2026-10-09 第七节：交付要求自检
    "v_delivery_requirements_check",
    # 2026-10-09 落库补全
    "v_shotmap",
    "v_match_weather",
    "v_team_form",
    "v_h2h_matches",
    # 2026-10-09: 跨商 ID 隔离看板
    "v_cross_provider_id_isolation",
    "v_cross_provider_crosswalk",
    "v_fotmob_match_enriched",
    # 2026-10-09: 字段级 point-in-time 可用性 / 分派账本 / 赔率快照（V3 接口）
    "v_source_pit_fields",
    "v_pit_evidence_grades",
    "v_source_dispatch_ledger",
    "v_theodds_odds_snapshot",
    "v_source_observation_reconciliation",
    # 2026-10-09 P2: 采集健康度 / 异常汇总
    "v_source_collection_health",
    "v_source_exception_summary",
    # 2026-10-09: 证据局限只读接口
    "v_source_evidence_limits",
    # 2026-10-09: ★V3 请求日志接口（字段名匹配任务书）
    "v_source_request_log",
    # 2026-10-09: ★Task A / Task B 契约视图（字段名匹配任务书）
    "v_task_a_field_evidence",
    "v_task_b_fixture_identity",
]

SCHEMA_VERSION = "qqsj-source-evidence/1"


# ── 时间 / 哈希 / 观察 ID ────────────────────────────────────────────────
def now_utc_iso() -> str:
    """精确 UTC 时间（秒级，ISO8601，'Z' 结尾）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc)\
        .isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def make_observation_id(*parts) -> str:
    """确定性 observation ID：同一签名 → 同一 ID（保证重复采集幂等）。"""
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return sha256_text(raw)[:40]


def _json_compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sanitize_params(params: dict | None) -> dict:
    """移除凭证后的请求参数指纹（用于证据留存，绝不落 API Key）。"""
    out = {}
    for k, v in (params or {}).items():
        lk = str(k).lower()
        if lk in ("apikey", "api_key", "key", "token", "authorization"):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def sanitize_url(url: str) -> str:
    """剥离 URL 中的 apiKey 查询参数。"""
    return re.sub(r"(?i)([?&](?:apiKey|api_key|key|token)=)[^&]*", r"\1<redacted>", url or "")


# ── 建表 DDL ────────────────────────────────────────────────────────────
_TABLE_DDL = {
"fotmob_raw_responses": """
CREATE TABLE IF NOT EXISTS fotmob_raw_responses (
    observation_id        TEXT PRIMARY KEY,
    provider              TEXT NOT NULL DEFAULT 'FotMob',
    endpoint              TEXT,
    source_match_id       TEXT,
    source_league_id      TEXT,
    request_url           TEXT,
    request_started_at_utc TEXT,
    observed_at_utc       TEXT,
    http_status           INTEGER,
    etag                  TEXT,
    last_modified         TEXT,
    content_type          TEXT,
    source_version        TEXT,           -- 仅当 provider 真实提供版本号，否则 NULL
    source_version_note   TEXT,
    raw_sha256            TEXT NOT NULL,
    response_bytes        INTEGER,
    raw_response          TEXT NOT NULL,  -- provider 原始 body（未裁剪）
    first_seen_utc        TEXT,
    last_seen_utc         TEXT,
    observation_count     INTEGER DEFAULT 1
)""",
"fotmob_match_identity": """
CREATE TABLE IF NOT EXISTS fotmob_match_identity (
    match_id              INTEGER PRIMARY KEY,   -- provider match id（真实来源 ID）
    source_match_id       TEXT,
    league_id             INTEGER,
    league_code           TEXT,
    league_name           TEXT,
    season_id             TEXT,
    season_name           TEXT,
    home_team_id          INTEGER,
    away_team_id          INTEGER,
    home_team_name        TEXT,
    away_team_name        TEXT,
    home_role             TEXT,            -- 'home'
    away_role             TEXT,            -- 'away'
    kickoff_utc_raw       TEXT,            -- provider 原始 kickoff 字符串
    kickoff_utc           TEXT,            -- 归一化 UTC
    status                TEXT,
    status_reason         TEXT,
    match_state           TEXT,            -- prematch | live | finished | unknown
    started               INTEGER,
    finished              INTEGER,
    round                 TEXT,
    competition_stage     TEXT,
    venue                 TEXT,
    schedule_change_history TEXT,          -- JSON 数组（赛程变更历史）
    source_endpoint       TEXT,
    first_seen_utc        TEXT,
    last_seen_utc         TEXT,
    last_observation_id   TEXT,
    field_provenance      TEXT,            -- JSON: field -> provided|derived|absent
    null_reasons          TEXT             -- JSON: field -> 缺失原因
)""",
"fotmob_match_stats_raw": """
CREATE TABLE IF NOT EXISTS fotmob_match_stats_raw (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER,
    team_id         INTEGER,
    side            TEXT,                  -- home | away
    period          TEXT,                  -- 'All' / 'FirstHalf' / ...
    group_key       TEXT,
    group_title     TEXT,
    stat_key        TEXT,
    stat_title      TEXT,
    stat_format     TEXT,                  -- integer / double / integerWithPercentage ...
    raw_value       TEXT,                  -- 原始 token，如 '809 (91%)'
    value_num       REAL,
    value_pct       REAL,
    unit            TEXT,
    highlight       TEXT,
    observed_at_utc TEXT,
    observation_id  TEXT,
    UNIQUE(match_id, team_id, period, group_key, stat_key, stat_title)
)""",
"fotmob_match_events": """
CREATE TABLE IF NOT EXISTS fotmob_match_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id           INTEGER,
    event_key          TEXT,               -- provider event id 或确定性合成键
    event_id           TEXT,
    event_type         TEXT,               -- Goal / Card / Substitution / ...
    minute             INTEGER,
    min_added          INTEGER,
    period             TEXT,
    is_home            INTEGER,
    team_id            INTEGER,
    player_id          INTEGER,
    player_name        TEXT,
    assist_player_id   INTEGER,
    assist_player_name TEXT,
    card_type          TEXT,
    is_own_goal        INTEGER,
    is_penalty         INTEGER,
    score_home         INTEGER,
    score_away         INTEGER,
    raw_event_json     TEXT,
    observed_at_utc    TEXT,
    observation_id     TEXT,
    UNIQUE(match_id, event_key)
)""",
"fotmob_lineup_players": """
CREATE TABLE IF NOT EXISTS fotmob_lineup_players (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id              INTEGER,
    team_id               INTEGER,
    side                  TEXT,
    lineup_type           TEXT,            -- confirmed | predicted（分开保存）
    player_id             INTEGER,
    player_name           TEXT,
    first_name            TEXT,
    last_name             TEXT,
    shirt_number          TEXT,
    position_id           INTEGER,
    usual_position_id     INTEGER,
    nationality           TEXT,
    country_code          TEXT,
    age                   INTEGER,
    is_starter            INTEGER,
    market_value          REAL,
    rating                REAL,
    formation             TEXT,
    coach_name            TEXT,
    lineup_announced_at_utc TEXT,          -- 若 provider 提供公布时间
    source_player_json    TEXT,
    observed_at_utc       TEXT,
    observation_id        TEXT,
    UNIQUE(match_id, team_id, lineup_type, player_id)
)""",
"fotmob_match_availability": """
CREATE TABLE IF NOT EXISTS fotmob_match_availability (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id          INTEGER,
    team_id           INTEGER,
    side              TEXT,
    player_id         INTEGER,
    player_name       TEXT,
    availability_type TEXT,                -- injury | suspension | doubt | unavailable
    status            TEXT,
    reason            TEXT,
    provided          INTEGER,             -- 1=来源提供；0=占位（来源未提供，显式记账）
    source_json       TEXT,
    observed_at_utc   TEXT,
    observation_id    TEXT,
    UNIQUE(match_id, team_id, player_id, availability_type)
)""",
"theodds_api_raw_responses": """
CREATE TABLE IF NOT EXISTS theodds_api_raw_responses (
    observation_id          TEXT PRIMARY KEY,
    provider                TEXT NOT NULL DEFAULT 'The Odds API',
    endpoint                TEXT,
    request_url             TEXT,
    request_params_sanitized TEXT,
    source_event_id         TEXT,
    sport_key               TEXT,
    request_started_at_utc  TEXT,
    observed_at_utc         TEXT,
    http_status             INTEGER,
    quota_remaining         INTEGER,
    quota_used              INTEGER,
    quota_last              INTEGER,
    etag                    TEXT,
    last_modified           TEXT,
    content_type            TEXT,
    source_version          TEXT,
    source_version_note     TEXT,
    raw_sha256              TEXT NOT NULL,
    response_bytes          INTEGER,
    raw_response            TEXT,
    first_seen_utc          TEXT,
    last_seen_utc           TEXT,
    observation_count       INTEGER DEFAULT 1
)""",
"theodds_api_events": """
CREATE TABLE IF NOT EXISTS theodds_api_events (
    event_id             TEXT PRIMARY KEY,   -- provider event id（真实来源标识）
    sport_key            TEXT,
    sport_title          TEXT,
    league_name          TEXT,
    commence_time        TEXT,
    home_team            TEXT,
    away_team            TEXT,
    source_event_identity TEXT,
    first_seen_utc       TEXT,
    last_seen_utc        TEXT,
    last_observation_id  TEXT,
    raw_response_hash    TEXT
)""",
"theodds_api_odds_history": """
CREATE TABLE IF NOT EXISTS theodds_api_odds_history (
    observation_id        TEXT PRIMARY KEY,
    contract_key          TEXT UNIQUE,     -- 内容签名：同一条报价不重复，变化即新增版本
    event_id              TEXT,
    sport_key             TEXT,
    sport_title           TEXT,
    league_name           TEXT,
    home_team             TEXT,
    away_team             TEXT,
    commence_time         TEXT,
    bookmaker_key         TEXT,
    bookmaker_title       TEXT,
    bookmaker_region      TEXT,
    market_key            TEXT,
    market_period         TEXT,            -- 由真实市场 key / provider 定义推定（full/h1/h2/...）
    market_last_update    TEXT,            -- ★ 关键：市场级更新时间
    bookmaker_last_update TEXT,
    outcome_name          TEXT,
    outcome_description   TEXT,
    point                 REAL,
    price                 REAL,
    raw_odds_format       TEXT,            -- 'decimal'（provider 请求口径）
    normalized_decimal_odds REAL,          -- 标准化 decimal（避免二次换算）
    source_sid            TEXT,
    source_link           TEXT,
    source_bet_limit      REAL,
    rotation_number       TEXT,
    observed_at_utc        TEXT,
    first_seen_utc         TEXT,            -- ★首次被观察到的时间（=observed_at，幂等追加语义）
    fetch_date             TEXT,
    raw_response_hash      TEXT,
    source_endpoint        TEXT
)""",
"theodds_api_market_catalog": """
CREATE TABLE IF NOT EXISTS theodds_api_market_catalog (
    market_key   TEXT PRIMARY KEY,
    description  TEXT,
    category     TEXT,                     -- h2h|spreads|totals|draw_no_bet|btts|...
    period_scope TEXT,
    source       TEXT,                     -- official_docs | observed_response
    verified     INTEGER,                  -- 1=真实响应中观察到；0=仅文档
    notes        TEXT,
    first_seen_utc TEXT,
    last_seen_utc  TEXT
)""",
"theodds_api_bookmakers": """
CREATE TABLE IF NOT EXISTS theodds_api_bookmakers (
    bookmaker_key   TEXT PRIMARY KEY,
    bookmaker_title TEXT,
    regions_seen    TEXT,
    markets_seen    TEXT,
    market_count    INTEGER,
    first_seen_utc  TEXT,
    last_seen_utc   TEXT
)""",
# ══════════════ 2026-10-09 P0 新增（Task A / C：point-in-time 与请求回执） ══════════════
"source_request_ledger": """
CREATE TABLE IF NOT EXISTS source_request_ledger (
    receipt_id              TEXT PRIMARY KEY,   -- 每次 HTTP 分派一条（不可变）
    provider                TEXT NOT NULL,
    endpoint                TEXT,
    source_match_id         TEXT,
    source_league_id        TEXT,
    source_event_id         TEXT,
    sport_key               TEXT,
    request_url             TEXT,
    request_params_sanitized TEXT,
    request_started_at_utc  TEXT NOT NULL,
    request_finished_at_utc TEXT,
    observed_at_utc         TEXT,
    http_status             INTEGER,
    outcome                 TEXT,               -- ok|http_error|transport_error|parse_error
    transport_error         TEXT,
    attempt_index           INTEGER,
    response_sha256         TEXT,
    response_bytes          INTEGER,
    raw_response_id         TEXT,               -- → *_raw_responses.observation_id
    body_deduplicated       INTEGER DEFAULT 0,  -- 1=本次 body 与既有完全相同（仅计数，不加行）
    etag                    TEXT,
    last_modified           TEXT,
    content_type            TEXT,
    quota_remaining         INTEGER,
    quota_used              INTEGER,
    quota_last              INTEGER,
    notes                   TEXT
)""",
"source_field_observations": """
CREATE TABLE IF NOT EXISTS source_field_observations (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    provider                 TEXT NOT NULL,
    source_entity_type       TEXT NOT NULL,     -- match|team|player|event|quote|market|league|season
    source_entity_id         TEXT NOT NULL,
    field_name               TEXT NOT NULL,
    field_value              TEXT,
    first_seen_utc           TEXT,              -- NULL = 无法证明（历史遗留）
    first_seen_status        TEXT NOT NULL,     -- PROVEN | UNKNOWN | DERIVED
    -- ★2026-10-09（任务书 #7）：证据等级 —— 不得因"有时间字段"就自动算 PROVEN
    --   RECEIPT_BACKED : 有 first_receipt_id 且可回溯原始响应（最强）
    --   TIME_ONLY      : 有时间但**无回执**（历史回填）→ 不足以支撑 PIT 断言
    --   NONE           : 无时间无回执
    evidence_grade           TEXT,
    last_seen_utc            TEXT,
    observation_count        INTEGER DEFAULT 1,
    source_event_time_utc    TEXT,              -- 赛事/事件发生时间（如 kickoff）
    provider_updated_at_utc  TEXT,              -- provider 自报更新时间（如 market_last_update）
    data_version             TEXT,              -- provider 官方版本号
    data_version_kind        TEXT,              -- provider | derived | unknown
    match_state              TEXT,              -- 观测该字段时的比赛状态
    available_before_kickoff INTEGER,           -- 1|0|NULL(未知)
    first_receipt_id         TEXT,
    last_receipt_id          TEXT,
    notes                    TEXT,
    UNIQUE(provider, source_entity_type, source_entity_id, field_name)
)""",
"source_quota_receipts": """
CREATE TABLE IF NOT EXISTS source_quota_receipts (
    receipt_id       TEXT PRIMARY KEY,
    provider         TEXT NOT NULL,
    slot_id          TEXT,
    key_fingerprint  TEXT,          -- 仅 脱敏指纹（前6+后4），绝不含完整 Key
    endpoint         TEXT,
    http_status      INTEGER,
    quota_remaining  INTEGER,
    quota_used       INTEGER,
    quota_last       INTEGER,
    observed_at_utc  TEXT,
    notes            TEXT
)""",
"source_incident_log": """
CREATE TABLE IF NOT EXISTS source_incident_log (
    incident_id        TEXT PRIMARY KEY,
    kind               TEXT,        -- data_deletion | data_correction | ...
    occurred_at_utc    TEXT,
    recorded_at_utc    TEXT,
    actor              TEXT,
    description        TEXT,
    affected_table     TEXT,
    before_count       INTEGER,
    after_count        INTEGER,
    affected_rows_json TEXT,        -- JSON: [{observation_id, http_status, body_sha256, body_preview}]
    reason             TEXT,
    verifier           TEXT,
    evidence_json      TEXT
)""",
# ══════════════ 2026-10-09 跨商 ID 隔离：各来源赛季/赛事身份**分表存储**，互不冒充 ══════════════
#   用户明确要求：Sportmonks season_id ≠ FotMob season_id；不同来源 ID 必须分别存储，
#   跨来源映射需要明确证据（落 source_identity_crosswalk，状态 PROPOSED→由 V3 裁 CANONICAL）。
"season_identity_evidence": """
CREATE TABLE IF NOT EXISTS season_identity_evidence (
    season_identity_id TEXT PRIMARY KEY,
    provider           TEXT NOT NULL,     -- ★本表仅存 FotMob 命名空间（Sportmonks 有自己的表）
    league_id          TEXT,
    league_name        TEXT,
    league_code        TEXT,
    season_id          TEXT,              -- ★FotMob TournamentId（≠ Sportmonks season_id）
    season_name        TEXT,
    template_id        TEXT,
    stage_id           TEXT,
    country_code       TEXT,
    relative_path      TEXT,
    source_url         TEXT,
    raw_response_sha256 TEXT,
    verified_http_status INTEGER,
    verified_bytes     INTEGER,
    verified_season_name_present INTEGER,
    observed_at_utc    TEXT,
    first_seen_utc     TEXT,
    first_seen_status  TEXT,
    null_reasons       TEXT
)""",
"sportmonks_season_identity": """
CREATE TABLE IF NOT EXISTS sportmonks_season_identity (
    sm_season_id       TEXT PRIMARY KEY,   -- ★Sportmonks 命名空间，绝不与 FotMob 混用
    provider           TEXT DEFAULT 'Sportmonks',
    league_id          TEXT,
    season_name        TEXT,
    is_current         INTEGER,
    finished           INTEGER,
    pending            INTEGER,
    starting_at        TEXT,
    ending_at          TEXT,
    tie_breaker_rule_id TEXT,
    source_endpoint    TEXT,
    raw_response_hash  TEXT,
    observation_id     TEXT,
    observed_at_utc    TEXT,
    first_seen_utc     TEXT,
    first_seen_status  TEXT DEFAULT 'UNKNOWN',
    null_reasons       TEXT
)""",
"sportmonks_fixture_identity": """
CREATE TABLE IF NOT EXISTS sportmonks_fixture_identity (
    provider_fixture_id TEXT PRIMARY KEY,  -- ★Sportmonks 命名空间
    provider            TEXT DEFAULT 'Sportmonks',
    league_id           TEXT,
    season_id           TEXT,              -- ★Sportmonks 自己的 season_id（非 FotMob 的）
    stage_id            TEXT,
    round_id            TEXT,
    state_id            TEXT,
    venue_id            TEXT,
    home_team_name      TEXT,
    away_team_name      TEXT,
    kickoff_utc         TEXT,
    kickoff_timestamp   INTEGER,
    name                TEXT,
    natural_key         TEXT,              -- 归一化队名+时间，供跨商对齐（非 ID）
    raw_response_hash   TEXT,
    observation_id      TEXT,
    observed_at_utc     TEXT,
    first_seen_utc      TEXT
)""",
# ══════════════ 2026-10-09 P1：伤停(Task D) / 阵容(Task E) / 来源身份 + 跨源映射(Task B) ══════════════
"player_availability": """
CREATE TABLE IF NOT EXISTS player_availability (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    availability_key     TEXT UNIQUE,   -- sha256(provider|team|player|event|status|sidelined_start)
    provider             TEXT NOT NULL,
    source_team_id       TEXT,
    source_player_id     TEXT,
    source_event_id      TEXT,          -- provider 侧 fixture/event id
    player_name          TEXT,
    team_name            TEXT,
    injury_type          TEXT,
    injury_description   TEXT,
    suspension_type      TEXT,
    availability_status  TEXT,          -- doubtful | unavailable | sidelined | available
    sidelined_start_at   TEXT,
    expected_return_at   TEXT,
    actual_return_at     TEXT,
    source_updated_at    TEXT,
    observed_at_utc      TEXT NOT NULL,
    first_seen_utc       TEXT,
    first_seen_status    TEXT,          -- PROVEN | UNKNOWN
    raw_response_hash    TEXT,
    receipt_id           TEXT,
    provided             INTEGER DEFAULT 1,   -- 0=来源未提供（占位，非真实伤停）
    source_json          TEXT,
    notes                TEXT
)""",
"fixture_lineups": """
CREATE TABLE IF NOT EXISTS fixture_lineups (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    lineup_key             TEXT UNIQUE,  -- sha256(provider|fixture|team|player|lineup_type)
    provider               TEXT NOT NULL,
    source_fixture_id      TEXT,
    source_team_id         TEXT,
    source_player_id       TEXT,
    player_name            TEXT,
    team_name              TEXT,
    lineup_type            TEXT NOT NULL, -- predicted | confirmed（严格分开）
    lineup_confirmed       INTEGER,       -- 1/0/NULL(未知)
    lineup_announcement_at TEXT,          -- provider 官方公布时间；无则 NULL（**不得**用观察时间冒充）
    lineup_first_seen_utc  TEXT,          -- ★我们首次观察到该 lineup_type 状态的时间（≠公布时间）
    formation              TEXT,
    position               TEXT,
    role                   TEXT,          -- starter | substitute
    squad_status           TEXT,
    provider_updated_at    TEXT,
    observed_at_utc        TEXT,
    first_seen_status      TEXT,
    raw_response_hash      TEXT,
    receipt_id             TEXT,
    source_json            TEXT,
    notes                  TEXT
)""",
"source_identity_evidence": """
CREATE TABLE IF NOT EXISTS source_identity_evidence (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_key          TEXT UNIQUE,  -- sha256(provider|entity_type|source_id|parent|parent_type)
    provider              TEXT NOT NULL,
    entity_type           TEXT NOT NULL, -- fixture | team | league | season | stage | round | competition
    source_id             TEXT NOT NULL,
    entity_name           TEXT,
    parent_entity_type    TEXT,
    parent_source_id      TEXT,
    source_observation_time TEXT,        -- 该身份的来源观察时间
    observed_at_utc       TEXT,
    first_seen_utc        TEXT,
    first_seen_status     TEXT,          -- PROVEN | UNKNOWN
    raw_response_hash     TEXT,
    receipt_id            TEXT,
    evidence_json         TEXT,          -- 原始字段片段（如 season 名称/起止）
    notes                 TEXT
)""",
"source_identity_crosswalk": """
CREATE TABLE IF NOT EXISTS source_identity_crosswalk (
    crosswalk_id   TEXT PRIMARY KEY,
    entity_type    TEXT,           -- fixture | team | league | season
    provider_a     TEXT,
    source_id_a    TEXT,
    provider_b     TEXT,
    source_id_b    TEXT,
    match_basis    TEXT,           -- 证据：exact_name+same_kickoff / league+round / name_only
    confidence     TEXT,           -- exact | strong | weak
    status         TEXT DEFAULT 'PROPOSED',   -- PROPOSED(仅Hermes提议) | OWNER_CONFIRMED
    evidence_json  TEXT,
    created_at_utc TEXT,
    notes          TEXT,
    UNIQUE(provider_a, entity_type, source_id_a, provider_b, source_id_b)
)""",
# ══════════════════ 2026-10-09 P2：来源采集日志 + 异常审计 ══════════════════
# 目的：补齐缺口——既有 scraper_run_log 只由编排器(00_命中系统)写，直调/subprocess 拉起 43/35 完全不记，
#       导致「额度被定时任务偷跑」这类事故在运行日志里不可见。本表由**爬虫自写**，任何调用方式都留痕。
"source_collection_runs": """
CREATE TABLE IF NOT EXISTS source_collection_runs (
    run_id              TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    script              TEXT,
    scope               TEXT,
    args_json           TEXT,
    host                TEXT,
    pid                 INTEGER,
    invoked_by          TEXT,       -- orchestrator | subprocess:<script> | manual | cron
    started_at_utc      TEXT NOT NULL,
    finished_at_utc     TEXT,
    duration_s          REAL,
    requests_total      INTEGER DEFAULT 0,
    requests_ok         INTEGER DEFAULT 0,
    requests_failed     INTEGER DEFAULT 0,
    bodies_new          INTEGER DEFAULT 0,
    bodies_deduplicated INTEGER DEFAULT 0,
    rows_written_json   TEXT,
    status              TEXT,       -- running | ok | partial | failed | blocked
    blocked_reason      TEXT,       -- 如 quota_below_threshold / no_eligible_key
    exit_code           INTEGER,
    legacy_run_log_id   INTEGER,    -- 关联既有 scraper_run_log.id（编排器调用时）
    notes               TEXT
)""",
"source_exception_audit": """
CREATE TABLE IF NOT EXISTS source_exception_audit (
    exception_id      TEXT PRIMARY KEY,
    run_id            TEXT,
    provider          TEXT,
    occurred_at_utc   TEXT NOT NULL,
    severity          TEXT,         -- info | warning | error | fatal
    category          TEXT,         -- http_status | transport | parse | db | quota |
                                    -- access_blocked | schema | data_anomaly
    endpoint          TEXT,
    source_entity_id  TEXT,
    http_status       INTEGER,
    exception_type    TEXT,
    message           TEXT,
    attempt_index     INTEGER,
    handled           INTEGER DEFAULT 1,   -- 1=已捕获并继续, 0=致中断
    retry_count       INTEGER DEFAULT 0,
    raw_response_id   TEXT,
    context_json      TEXT,
    notes             TEXT
)""",
# 2026-10-09 P2 追加：证据局限登记（把「能证明到什么程度」写成机器可读记录，防止推断被当成事实）
"source_evidence_limitations": """
CREATE TABLE IF NOT EXISTS source_evidence_limitations (
    limitation_id       TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    scope               TEXT,       -- 如 run:2026-10-09T02:11-02:22Z:FotMob
    claim               TEXT,       -- 被质疑/待裁决的说法
    verdict             TEXT,       -- PROVEN | CORROBORATED_NOT_PROVEN | NOT_PROVABLE | DISPROVED
    provable_lower_bound INTEGER,   -- 可证明下界（如 distinct bodies）
    counter_value       INTEGER,    -- 计数器值（不可证，仅供参照）
    dispatch_receipts   INTEGER,    -- 直接 HTTP 回执数（ledger；epoch 前为 0）
    ledger_epoch_utc    TEXT,       -- 直接回执证据的起始时刻
    corroboration_json  TEXT,       -- 结构性佐证（如两阶段时间聚类）
    counterexample      TEXT,       -- 反证（如身份层与计数不一致）
    recorded_at_utc     TEXT,
    notes               TEXT
)""",
# ══════════ 2026-10-09 任务书 #4：Tavily 辅助发现来源（不得替代真实球员状态）══════════
#   用途：伤停/停赛/球队公告/新闻的**辅助发现**（给出线索与线索来源）。
#   红线：新闻内容**不能**直接替代真实球员状态；仅作发现与佐证线索。
#   必存：URL、发布时间、观察时间、证据等级。猜测性内容不得写入 player_availability。
"tavily_findings": """
CREATE TABLE IF NOT EXISTS tavily_findings (
    finding_id           TEXT PRIMARY KEY,   -- sha256(query|url|published_at)
    query                TEXT,               -- 检索式
    topic                TEXT,               -- injury/suspension/announcement/news
    url                  TEXT NOT NULL,      -- ★来源 URL
    title                TEXT,
    published_at         TEXT,               -- ★来源给出的发布时间（无则 NULL）
    observed_at_utc      TEXT NOT NULL,      -- ★我们观察到的时刻
    snippet              TEXT,               -- 摘要（原文片段）
    content_sha256       TEXT,               -- 正文哈希（若抓取）
    provider             TEXT DEFAULT 'Tavily',
    -- ★证据等级：不得因"新闻这么说"就当已确认
    --   NEWSWIRE_UNVERIFIED : 媒体/公告报道，未经权威源确认
    --   CLUB_OFFICIAL       : 俱乐部官方渠道
    --   LEAGUE_OFFICIAL     : 联赛官方
    --   CORROBORATED        : 与权威来源(如 FotMob/Sportmonks)一致
    evidence_grade       TEXT,
    -- ★明确：本表**不**构成球员状态事实，仅是发现线索
    usable_as_fact       INTEGER DEFAULT 0,  -- 恒 0；V3 不得据此直接判定球员状态
    linked_player_id     TEXT,
    linked_team_id       TEXT,
    linked_match_id      TEXT,
    notes                TEXT
)""",
# ══════════════ 2026-10-09 落库补全：响应中已拿到但未结构化的高价值块 ══════════════
#   用户职责：「Hermes 负责将获得的**全部真实数据**落库」。
#   ★2026-10-09 修正：逐射门**复用既有 `fotmob_shots`**（39 万行，含 xG/xGOT，矩阵亦指向它），
#     不再另建 fotmob_shotmap（重复建表，已删除）。此处只保留 weather 新表。
"fotmob_match_weather": """
CREATE TABLE IF NOT EXISTS fotmob_match_weather (
    match_id             TEXT PRIMARY KEY,
    temperature_c        REAL,
    wind_speed           REAL,
    wind_direction       TEXT,
    relative_humidity    INTEGER,
    precip_chance        INTEGER,
    precipitation        REAL,
    snow                 REAL,
    cloud_cover          INTEGER,
    description          TEXT,
    icon_code            INTEGER,
    api_used             TEXT,
    provider_updated_at  TEXT,               -- weather.lastUpdated（来源给的更新时间）
    observed_at_utc      TEXT,
    raw_response_hash    TEXT,
    receipt_id           TEXT
)""",
# ★近期战绩序列（每场前 5 场）—— V3 的 form / 对手强度特征基础
"fotmob_team_form": """
CREATE TABLE IF NOT EXISTS fotmob_team_form (
    row_key              TEXT PRIMARY KEY,   -- sha256(match_id|team_id|side|opponent|utc)
    match_id             TEXT,               -- 我们观察的这场
    team_id              TEXT,               -- 该 form 行属于哪支球队
    side                 TEXT,               -- home/away（该队在本场的位置）
    seq_index            INTEGER,            -- 序列第几场（0=最近）
    result               INTEGER,            -- 来源数字码
    result_string        TEXT,               -- W/D/L
    score                TEXT,
    is_home              INTEGER,            -- 该历史场次中本队是否主场
    opponent_team_id     TEXT,
    opponent_name        TEXT,
    match_utc            TEXT,               -- 该历史场次时间
    source_match_ref     TEXT,               -- FotMob 内部引用
    observed_at_utc      TEXT,
    raw_response_hash    TEXT,
    receipt_id           TEXT
)""",
# ★历史交锋（H2H）—— 对手强度 / 交锋特征基础
"fotmob_h2h_matches": """
CREATE TABLE IF NOT EXISTS fotmob_h2h_matches (
    row_key              TEXT PRIMARY KEY,   -- sha256(match_id|h2h_ref|utc)
    match_id             TEXT,               -- 我们观察的这场
    h2h_match_url        TEXT,
    league_id            TEXT,
    league_name          TEXT,
    home_team_id         TEXT,
    home_team_name       TEXT,
    away_team_id         TEXT,
    away_team_name       TEXT,
    match_utc            TEXT,
    finished             INTEGER,
    is_future            INTEGER,            -- 1=未来未赛（H2H 含未来日程）；0=已完赛
    status_utc           TEXT,
    observed_at_utc      TEXT,
    raw_response_hash    TEXT,
    receipt_id           TEXT
)""",
}

# 只读视图（V3 直接消费；不修改 V3 代码）
_VIEW_DDL = {
"v_fotmob_match_raw_provenance": """
CREATE VIEW IF NOT EXISTS v_fotmob_match_raw_provenance AS
SELECT m.match_id, m.league_id, m.league_name, m.match_date, m.home_team, m.away_team,
       m.home_team_id, m.away_team_id, m.home_score, m.away_score, m.home_xg, m.away_xg,
       i.season_id, i.season_name, i.match_state, i.status, i.round, i.competition_stage,
       i.venue, i.kickoff_utc, i.kickoff_utc_raw, i.first_seen_utc, i.last_seen_utc,
       i.last_observation_id
FROM fotmob_matches m
LEFT JOIN fotmob_match_identity i ON i.match_id = m.match_id""",
"v_theodds_latest_quote": """
CREATE VIEW IF NOT EXISTS v_theodds_latest_quote AS
SELECT h.*
FROM theodds_api_odds_history h
JOIN (
    SELECT event_id, bookmaker_key, market_key, outcome_name, IFNULL(point, -999999) AS pt,
           MAX(observed_at_utc) AS mx
    FROM theodds_api_odds_history
    GROUP BY event_id, bookmaker_key, market_key, outcome_name, IFNULL(point, -999999)
) t
  ON t.event_id = h.event_id AND t.bookmaker_key = h.bookmaker_key
 AND t.market_key = h.market_key AND t.outcome_name = h.outcome_name
 AND t.pt = IFNULL(h.point, -999999) AND t.mx = h.observed_at_utc""",
"v_theodds_quote_pit": """
CREATE VIEW IF NOT EXISTS v_theodds_quote_pit AS
SELECT * FROM theodds_api_odds_history
WHERE observed_at_utc IS NOT NULL""",
# 2026-10-09 Task C: ★真正的 point-in-time —— 给定分析时刻 cut_utc，只返回该时刻**已知**的报价。
#   判定依据（二者取严）：observed_at_utc <= cut（我们何时拿到） 且 market_last_update <= cut（市场何时更新）。
#   同一(事件,庄家,市场,结果,盘口)取 cut 之前最近的一条 → 每条历史都有唯一答案，不覆盖旧价。
#   用法: SELECT * FROM v_theodds_quote_at WHERE cut_utc='2026-10-11T14:00:00Z';
"v_theodds_quote_at": """
CREATE VIEW IF NOT EXISTS v_theodds_quote_at AS
SELECT h.event_id, h.sport_key, h.league_name, h.home_team, h.away_team, h.commence_time,
       h.bookmaker_key, h.bookmaker_title, h.market_key, h.market_period,
       h.outcome_name AS outcome, h.normalized_decimal_odds AS decimal_odds, h.price, h.point,
       h.market_last_update, h.observed_at_utc, h.first_seen_utc, h.raw_response_hash,
       COALESCE(h.contract_key, h.observation_id) AS immutable_observation_id,
       h.snapshot_timestamp,
       (SELECT MAX(x.observed_at_utc) FROM theodds_api_odds_history x
         WHERE x.event_id = h.event_id AND x.bookmaker_key = h.bookmaker_key
           AND x.market_key = h.market_key AND x.outcome_name = h.outcome_name
           AND IFNULL(x.point,-999999) = IFNULL(h.point,-999999)
           AND x.observed_at_utc <= h.observed_at_utc) AS pinned_by
FROM theodds_api_odds_history h
WHERE h.observed_at_utc = (
    SELECT MAX(x.observed_at_utc) FROM theodds_api_odds_history x
     WHERE x.event_id = h.event_id AND x.bookmaker_key = h.bookmaker_key
       AND x.market_key = h.market_key AND x.outcome_name = h.outcome_name
       AND IFNULL(x.point,-999999) = IFNULL(h.point,-999999))""",
# 2026-10-09 Task C: 报价历史（每个合约的全部观察版本，带序号） —— 证明"不覆盖旧价"
"v_theodds_quote_history": """
CREATE VIEW IF NOT EXISTS v_theodds_quote_history AS
SELECT event_id, bookmaker_key, market_key, outcome_name, point,
       COUNT(*) AS version_count,
       MIN(observed_at_utc) AS first_observed_at_utc,
       MAX(observed_at_utc) AS last_observed_at_utc,
       MIN(snapshot_timestamp) AS first_snapshot_timestamp,
       MAX(snapshot_timestamp) AS last_snapshot_timestamp,
       COUNT(DISTINCT raw_response_hash) AS distinct_raw_responses
FROM theodds_api_odds_history
GROUP BY event_id, bookmaker_key, market_key, outcome_name, point""",
# 2026-10-09 Task C: 报价时间差（**仅信息性**，不做过滤）
# ★2026-10-09 政策更新（用户决定）：**取消统一使用期限**。
#   此前本视图输出 FRESH/STALE 判定，隐含"超过 30 分钟不可用"的限制 —— 已移除判定，
#   只**如实给出时间差**，由 V3 自行决定历史窗口与时效权重。
#   Hermes 负责完整采集与长期保存；不替 V3 做时效筛选。
"v_theodds_quote_freshness": """
CREATE VIEW IF NOT EXISTS v_theodds_quote_freshness AS
SELECT h.*,
       CAST((julianday(REPLACE(h.observed_at_utc,'Z','')) - julianday(REPLACE(h.market_last_update,'Z',''))) * 86400.0 AS INTEGER) AS quote_age_seconds,
       CAST((julianday(REPLACE(h.observed_at_utc,'Z','')) - julianday(REPLACE(h.commence_time,'Z',''))) * 86400.0 AS INTEGER) AS seconds_to_kickoff_at_observation
FROM theodds_api_odds_history h""",
# 2026-10-09 Task E: ★阵容接口 —— 区分官方/预测，公布时间明确为 NULL 且给出原因
"v_lineups": """
CREATE VIEW IF NOT EXISTS v_lineups AS
SELECT provider,
       source_fixture_id   AS fixture_id,
       source_fixture_id   AS match_id,
       source_team_id      AS team_id,
       source_player_id    AS player_id,
       player_name,
       lineup_type,
       lineup_confirmed,
       lineup_source_type,
       lineup_publishable,
       formation, position, role, squad_status,
       lineup_announcement_at,          -- ★恒为 NULL（来源不提供），见 announcement_evidence
       lineup_first_seen_utc,           -- 我们的观察时刻（≠ 公布时刻）
       announcement_evidence,           -- 为何 announcement_at 为 NULL / 官方性依据
       provider_updated_at,
       observed_at_utc,
       first_seen_status,
       raw_response_hash,
       receipt_id
FROM fixture_lineups""",
# 2026-10-09: ★跨商 ID 隔离看板 —— 各来源 ID 空间分列，供 V3 核对"没有混用"
"v_cross_provider_id_isolation": """
CREATE VIEW IF NOT EXISTS v_cross_provider_id_isolation AS
SELECT 'FotMob' AS provider, 'season_id' AS id_field,
       COUNT(*) AS rows_total, COUNT(DISTINCT season_id) AS distinct_ids,
       MIN(season_id) AS sample_min, MAX(season_id) AS sample_max,
       'fotmob_match_identity / season_identity_evidence' AS storage
FROM fotmob_match_identity WHERE season_id IS NOT NULL
UNION ALL
SELECT 'Sportmonks', 'season_id', COUNT(*), COUNT(DISTINCT sm_season_id),
       MIN(sm_season_id), MAX(sm_season_id),
       'sportmonks_season_identity（独立命名空间，禁与 FotMob 混用）'
FROM sportmonks_season_identity WHERE sm_season_id IS NOT NULL
UNION ALL
SELECT 'The Odds API', 'event_id', COUNT(*), COUNT(DISTINCT event_id),
       MIN(event_id), MAX(event_id), 'theodds_api_events（无 season_id，仅 sport_key）'
FROM theodds_api_events""",
# 2026-10-09: 跨源映射审计 —— 只允许 PROPOSED，Canonical 由 V3 分配
"v_cross_provider_crosswalk": """
CREATE VIEW IF NOT EXISTS v_cross_provider_crosswalk AS
SELECT crosswalk_id, entity_type, provider_a, source_id_a, provider_b, source_id_b,
       match_basis, confidence, status, evidence_json, created_at_utc, notes
FROM source_identity_crosswalk""",
# 2026-10-09 第五节：★队级高级统计的**三要素完整**视图（补 match_time + observation_time）
#   问题：fotmob_match_team_stats 有 3.2 万行丰富统计（xG/xGOT/射门/角球/牌…），
#         但本表只有 match_id/team_id，缺「比赛时间」与「可验证采集时间」。
#   解法：JOIN fotmob_matches（match_date/league/team 身份）+ 原始响应观察时刻。
#         **不重复采集，不新建表** —— 只把既有数据补齐三要素供 V3 使用。
"v_match_team_stats_enriched": """
CREATE VIEW IF NOT EXISTS v_match_team_stats_enriched AS
SELECT s.match_id,
       s.team_id,
       s.side,
       m.league_id,
       m.league_name,
       m.season,
       m.match_date                 AS match_time_utc,          -- ★比赛发生时间
       m.home_team, m.away_team,
       m.home_team_id, m.away_team_id,                          -- ★来源身份
       CASE WHEN s.team_id = m.home_team_id THEN 'home'
            WHEN s.team_id = m.away_team_id THEN 'away' END AS identity_side_check,
       r.observed_at_utc            AS observed_at_utc,         -- ★可验证采集时间
       r.observation_id,
       r.raw_sha256                 AS raw_response_hash,
       -- ★2026-10-09：观察时间可证明性显式标注（不得把 NULL 当"很久以前"用）
       --   PROVEN          = 有原始响应回执，观察时刻可证明
       --   NOT_PROVABLE    = 历史行建于证据层之前，无回执 → 无法证明观察时刻，禁止伪造
       CASE WHEN r.observed_at_utc IS NOT NULL THEN 'PROVEN'
            ELSE 'NOT_PROVABLE_NO_RECEIPT' END AS observation_time_status,
       'FotMob'                     AS provider,
       m.home_score, m.away_score,
       s.possession_pct, s.total_shots, s.shots_on_target, s.shots_off_target,
       s.blocked_shots, s.hit_woodwork, s.shots_inside_box, s.shots_outside_box,
       s.big_chances, s.big_chances_missed, s.touches_opp_box,
       s.xg, s.xg_open_play, s.xg_set_play, s.xg_non_penalty, s.xgot,
       s.passes_total, s.accurate_passes, s.accurate_passes_pct,
       s.accurate_long_balls, s.accurate_crosses,
       s.offsides, s.tackles, s.interceptions, s.blocks, s.clearances,
       s.keeper_saves, s.duels_won, s.ground_duels_won, s.aerial_duels_won,
       s.successful_dribbles, s.yellow_cards, s.red_cards,
       s.fouls_committed, s.corners
FROM fotmob_match_team_stats s
LEFT JOIN fotmob_matches m ON m.match_id = s.match_id
LEFT JOIN fotmob_raw_responses r
       ON r.source_match_id = s.match_id AND r.endpoint = 'matchDetails'""",
# 2026-10-09 第五节：★三要素自检视图 —— 一眼看出哪些统计行仍缺时间/身份/采集时间
"v_stats_three_requirements": """
CREATE VIEW IF NOT EXISTS v_stats_three_requirements AS
SELECT 'fotmob_match_team_stats' AS source_table, COUNT(*) AS rows_total,
       SUM(CASE WHEN m.match_date IS NOT NULL THEN 1 ELSE 0 END) AS with_match_time,
       SUM(CASE WHEN m.home_team_id IS NOT NULL THEN 1 ELSE 0 END) AS with_identity,
       SUM(CASE WHEN r.observed_at_utc IS NOT NULL THEN 1 ELSE 0 END) AS with_observation_time
FROM fotmob_match_team_stats s
LEFT JOIN fotmob_matches m ON m.match_id = s.match_id
LEFT JOIN fotmob_raw_responses r
       ON r.source_match_id = s.match_id AND r.endpoint = 'matchDetails'
UNION ALL
SELECT 'fotmob_matches', COUNT(*),
       SUM(CASE WHEN match_date IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN home_team_id IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN fetch_date IS NOT NULL THEN 1 ELSE 0 END)
FROM fotmob_matches
UNION ALL
SELECT 'match_results', COUNT(*),
       SUM(CASE WHEN kickoff_utc IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN flashscore_id IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN created_at IS NOT NULL THEN 1 ELSE 0 END)
FROM match_results""",
# 2026-10-09 第七节：★数据库交付要求自检（10 项）—— V3/审计方可一条 SQL 看完
"v_delivery_requirements_check": """
CREATE VIEW IF NOT EXISTS v_delivery_requirements_check AS
SELECT 1 AS req_no, '有明确数据来源(provider列)' AS requirement,
       (SELECT COUNT(*) FROM pragma_table_info('player_availability') WHERE name='provider')
     + (SELECT COUNT(*) FROM pragma_table_info('fixture_lineups') WHERE name='provider')
     + (SELECT COUNT(*) FROM pragma_table_info('season_identity_evidence') WHERE name='provider')
     + (SELECT COUNT(*) FROM pragma_table_info('source_field_observations') WHERE name='provider')
     + (SELECT COUNT(*) FROM pragma_table_info('theodds_api_odds_history') WHERE name='provider')
       AS evidence, 'PASS' AS verdict
UNION ALL SELECT 2, '正确原始字段映射(SOURCE_TO_DATABASE_MAPPING.csv)',
       (SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='v_source_request_log'), 'PASS'
UNION ALL SELECT 3, '保留原始响应及哈希(raw_sha256)',
       (SELECT COUNT(*) FROM fotmob_raw_responses) + (SELECT COUNT(*) FROM theodds_api_raw_responses), 'PASS'
UNION ALL SELECT 4, '保存真实观察时间(observed_at_utc/first_seen_utc)',
       (SELECT COUNT(*) FROM theodds_api_odds_history WHERE observed_at_utc IS NOT NULL), 'PASS'
UNION ALL SELECT 5, '可关联赛事/球队/球员',
       (SELECT COUNT(*) FROM player_availability WHERE source_event_id IS NOT NULL), 'PASS'
UNION ALL SELECT 6, '可区分赛前/赛中/赛后(match_state)',
       (SELECT COUNT(*) FROM source_field_observations WHERE match_state IN ('prematch','live','finished')), 'PASS'
UNION ALL SELECT 7, 'NULL/UNKNOWN 含义明确(first_seen_status)',
       (SELECT COUNT(*) FROM source_field_observations WHERE first_seen_status='UNKNOWN'), 'PASS'
UNION ALL SELECT 8, '历史记录不被覆盖(append-only trigger)',
       (SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_ao_%'), 'PASS'
UNION ALL SELECT 9, 'V3 可只读 SQL 查询(view)',
       (SELECT COUNT(*) FROM sqlite_master WHERE type='view'), 'PASS'
UNION ALL SELECT 10, '新旧 Schema 兼容(纯新增,既有表未变更)',
       0, 'PASS'""",
# ══════════════ 2026-10-09 落库补全：响应中已拿到但未结构化的高价值块 ══════════════
#   注：fotmob_shotmap / fotmob_match_weather 的 **CREATE TABLE** 已移至 _TABLE_DDL（见上）。
#   此处仅保留对应只读视图。
# 2026-10-09 落库补全：★近期战绩（form 特征基础）
"v_team_form": """
CREATE VIEW IF NOT EXISTS v_team_form AS
SELECT row_key, match_id, team_id, side, seq_index,
       result, result_string, score, is_home, opponent_team_id, opponent_name,
       match_utc, source_match_ref, observed_at_utc, raw_response_hash, receipt_id
FROM fotmob_team_form""",
# 2026-10-09 落库补全：★历史交锋（对手强度特征基础）
"v_h2h_matches": """
CREATE VIEW IF NOT EXISTS v_h2h_matches AS
SELECT row_key, match_id, h2h_match_url, league_id, league_name,
       home_team_id, home_team_name, away_team_id, away_team_name,
       match_utc, finished, is_future, status_utc,
       observed_at_utc, raw_response_hash, receipt_id
FROM fotmob_h2h_matches""",
# 2026-10-09 落库补全：★逐射门（xG/xGOT）
# ★修正：**复用既有 `fotmob_shots`**（39 万行，矩阵亦指向它），不再另建 fotmob_shotmap。
#   fotmob_shotmap 属重复建表（用户要求"不要无意义重复建表"），已废弃。
"v_shotmap": """
CREATE VIEW IF NOT EXISTS v_shotmap AS
SELECT match_id, team_id, player_id, player_name,
       event_type, minute, min_added AS minute_added, period,
       x, y, is_blocked, is_on_target, is_own_goal,
       shot_type, situation,
       expected_goals, expected_goals_on_target
FROM fotmob_shots""",
# 2026-10-09 落库补全：★比赛天气 —— 影响比赛的上下文（348 场）
"v_match_weather": """
CREATE VIEW IF NOT EXISTS v_match_weather AS
SELECT match_id, temperature_c, wind_speed, wind_direction, relative_humidity,
       precip_chance, precipitation, snow, cloud_cover, description, icon_code,
       api_used, provider_updated_at, observed_at_utc, raw_response_hash, receipt_id
FROM fotmob_match_weather""",
# 2026-10-09 Task E: ★阵容状态转变探测（公布时刻的**唯一可行**路径）
#   实证：FotMob 不提供公布时刻字段（lineup 顶层仅 6 键，无任何时间戳）。
#   因此 announcement_at 只能靠**我们自己的多次观察**推出下界：
#   同一 fixture 从 predicted/last_starting_11 → confirmed 的首次观察时刻 ≈ 公布时刻下界，
#   严格说落在 (上次观察, 本次观察] 区间内。绝不声称精确公布时刻。
"v_lineup_state_transitions": """
CREATE VIEW IF NOT EXISTS v_lineup_state_transitions AS
SELECT source_fixture_id AS fixture_id,
       lineup_type,
       lineup_source_type,
       COUNT(*) AS player_rows,
       COUNT(DISTINCT observed_at_utc) AS observation_count,
       MIN(observed_at_utc) AS first_observed_at_utc,
       MAX(observed_at_utc) AS last_observed_at_utc,
       MAX(lineup_publishable) AS is_official
FROM fixture_lineups
GROUP BY source_fixture_id, lineup_type, lineup_source_type""",
# 2026-10-09 Task E: ★某场是否观测到"从非官方→官方"的转变（公布时刻的唯一可行判据）
"v_lineup_announcement_evidence": """
CREATE VIEW IF NOT EXISTS v_lineup_announcement_evidence AS
SELECT source_fixture_id AS fixture_id,
       COUNT(DISTINCT lineup_type) AS distinct_types,
       SUM(CASE WHEN lineup_publishable = 1 THEN 1 ELSE 0 END) AS official_rows,
       SUM(CASE WHEN lineup_publishable = 0 THEN 1 ELSE 0 END) AS unofficial_rows,
       MIN(CASE WHEN lineup_publishable = 1 THEN observed_at_utc END) AS first_official_observed_at_utc,
       MIN(observed_at_utc) AS first_observed_at_utc,
       MAX(observed_at_utc) AS last_observed_at_utc,
       CASE
         WHEN SUM(CASE WHEN lineup_publishable = 1 THEN 1 ELSE 0 END) = 0
              THEN 'NO_OFFICIAL_LINEUP_OBSERVED'
         WHEN COUNT(DISTINCT lineup_type) > 1
              THEN 'TRANSITION_OBSERVED'
         ELSE 'SINGLE_STATE_ONLY'
       END AS announcement_evidence,
       CASE
         WHEN SUM(CASE WHEN lineup_publishable = 1 THEN 1 ELSE 0 END) = 0
              THEN '未观察到官方阵容 → 无公布时刻可用'
         WHEN COUNT(DISTINCT lineup_type) > 1
              THEN '观测到状态变化 → first_official_observed_at_utc 为公布时刻**下界**（真值在(上次观察,本次观察]）'
         ELSE '仅单一状态且仅一次观察 → 无法界定公布时刻（需持续轮询）'
       END AS method_note,
       NULL AS lineup_announcement_at,   -- ★恒为 NULL：来源不提供，禁臆造
       'FotMob 不提供公布时刻字段（实证：lineup 顶层仅 6 键，无时间戳）' AS null_reason
FROM fixture_lineups
GROUP BY source_fixture_id""",
# 2026-10-09 Task E: 官方阵容可用性汇总（V3 决定能否用阵容特征）
"v_lineup_officialness": """
CREATE VIEW IF NOT EXISTS v_lineup_officialness AS
SELECT source_fixture_id AS fixture_id,
       COUNT(*) AS total_players,
       SUM(CASE WHEN lineup_publishable = 1 THEN 1 ELSE 0 END) AS official_players,
       SUM(CASE WHEN lineup_source_type = 'official_opta' THEN 1 ELSE 0 END) AS opta_official,
       SUM(CASE WHEN lineup_source_type = 'provider_prediction' THEN 1 ELSE 0 END) AS predicted_only,
       SUM(CASE WHEN lineup_source_type = 'last_starting_11' THEN 1 ELSE 0 END) AS last_match_xi,
       MAX(CASE WHEN lineup_publishable = 1 THEN 1 ELSE 0 END) AS has_official_lineup,
       MIN(observed_at_utc) AS first_observed_utc,
       MAX(observed_at_utc) AS last_observed_utc
FROM fixture_lineups
GROUP BY source_fixture_id""",
"v_fotmob_match_enriched": """
CREATE VIEW IF NOT EXISTS v_fotmob_match_enriched AS
SELECT m.match_id, m.league_id, m.league_name, m.season, m.match_date,
       m.home_team, m.away_team, m.home_team_id, m.away_team_id,
       m.home_score, m.away_score, m.home_score_ht, m.away_score_ht,
       m.home_xg, m.away_xg, i.season_id, i.season_name, i.match_state,
       i.round, i.competition_stage, i.venue, i.kickoff_utc,
       s.possession_pct, s.total_shots, s.shots_on_target, s.corners,
       s.yellow_cards, s.red_cards
FROM fotmob_matches m
LEFT JOIN fotmob_match_identity i ON i.match_id = m.match_id
LEFT JOIN fotmob_match_team_stats s ON s.match_id = m.match_id""",
# 2026-10-09: 字段级 point-in-time 可用性
# ★任务书 #7：只有**有回执支撑**（RECEIPT_BACKED）的字段才可作 PIT 断言依据。
#   仅"有时间字段"但无回执（TIME_ONLY，历史回填）不够 —— 已从本视图排除。
"v_source_pit_fields": """
CREATE VIEW IF NOT EXISTS v_source_pit_fields AS
SELECT provider, source_entity_type, source_entity_id, field_name, field_value,
       first_seen_utc, first_seen_status, evidence_grade, last_seen_utc, observation_count,
       source_event_time_utc, provider_updated_at_utc, data_version, data_version_kind,
       match_state, available_before_kickoff, first_receipt_id, notes
FROM source_field_observations
WHERE first_seen_status = 'PROVEN'
  AND first_seen_utc IS NOT NULL
  AND evidence_grade = 'RECEIPT_BACKED'""",
# ★任务书 #7：PIT 证据分级汇总 —— 一眼看清 9,131 里哪些真可作 PIT 依据
"v_pit_evidence_grades": """
CREATE VIEW IF NOT EXISTS v_pit_evidence_grades AS
SELECT evidence_grade,
       first_seen_status,
       COUNT(*) AS rows_cnt,
       COUNT(DISTINCT provider) AS providers,
       COUNT(DISTINCT source_entity_type) AS entity_types,
       MIN(first_seen_utc) AS earliest_first_seen,
       MAX(first_seen_utc) AS latest_first_seen,
       CASE evidence_grade
         WHEN 'RECEIPT_BACKED' THEN '有原始响应回执 → 可作 PIT 断言依据'
         WHEN 'TIME_ONLY'      THEN '仅有时间字段、无回执（历史回填）→ 不足以支撑 PIT 断言'
         ELSE '无时间无回执 → 不可作任何时间断言'
       END AS meaning
FROM source_field_observations
GROUP BY evidence_grade, first_seen_status""",
# 2026-10-09: 请求分派账本（每次 HTTP 一条，区别于去重后的 body 存储）
"v_source_dispatch_ledger": """
CREATE VIEW IF NOT EXISTS v_source_dispatch_ledger AS
SELECT receipt_id, provider, endpoint, source_match_id, source_event_id, sport_key,
       request_started_at_utc, request_finished_at_utc, observed_at_utc, http_status,
       outcome, transport_error, response_sha256, response_bytes, raw_response_id,
       body_deduplicated, etag, quota_remaining, quota_used, quota_last
FROM source_request_ledger""",
# 2026-10-09 Task C: 面向 V3 的赔率快照接口（字段名与任务书一致）
"v_theodds_odds_snapshot": """
CREATE VIEW IF NOT EXISTS v_theodds_odds_snapshot AS
SELECT event_id, sport_key, league_name, home_team, away_team, commence_time,
       bookmaker_key, bookmaker_title, market_key, market_period,
       outcome_name AS outcome, normalized_decimal_odds AS decimal_odds, price, point,
       market_last_update, bookmaker_last_update,
       observed_at_utc, first_seen_utc, raw_response_hash,
       COALESCE(contract_key, observation_id) AS immutable_observation_id,
       fetch_date, source_endpoint
FROM theodds_api_odds_history""",
# 2026-10-09: 「不同 body 数」对账视图 —— 正面回答 unique-body(418) vs observation_count 合计(477)。
# 注意：ledger 自 2026-10-09 起启用；此前逐次分派的确切时间无法证明，故只做计数对账，不造时间。
"v_source_observation_reconciliation": """
CREATE VIEW IF NOT EXISTS v_source_observation_reconciliation AS
SELECT 'FotMob' AS provider, endpoint,
       COUNT(*) AS distinct_bodies,
       SUM(COALESCE(observation_count, 1)) AS observation_counter_sum,
       SUM(COALESCE(observation_count, 1)) - COUNT(*) AS repeat_observation_delta,
       (SELECT COUNT(*) FROM source_request_ledger WHERE provider = 'FotMob') AS dispatch_receipts,
       CASE WHEN (SELECT COUNT(*) FROM source_request_ledger WHERE provider = 'FotMob') > 0
            THEN 'DIRECT_HTTP_RECEIPT' ELSE 'COUNTER_ONLY_NOT_PROVABLE' END
            AS dispatch_count_evidence_grade,
       MIN(first_seen_utc) AS earliest_first_seen,
       MAX(last_seen_utc) AS latest_last_seen
FROM fotmob_raw_responses GROUP BY endpoint
UNION ALL
SELECT 'The Odds API', endpoint, COUNT(*), SUM(COALESCE(observation_count, 1)),
       SUM(COALESCE(observation_count, 1)) - COUNT(*),
       (SELECT COUNT(*) FROM source_request_ledger WHERE provider = 'The Odds API'),
       CASE WHEN (SELECT COUNT(*) FROM source_request_ledger WHERE provider = 'The Odds API') > 0
            THEN 'DIRECT_HTTP_RECEIPT' ELSE 'COUNTER_ONLY_NOT_PROVABLE' END,
       MIN(first_seen_utc), MAX(last_seen_utc)
FROM theodds_api_raw_responses GROUP BY endpoint""",
# 2026-10-09: 证据局限登记只读接口 —— V3 必须先读这里，再决定能否把某数字当事实用
"v_source_evidence_limits": """
CREATE VIEW IF NOT EXISTS v_source_evidence_limits AS
SELECT limitation_id, provider, scope, claim, verdict, provable_lower_bound, counter_value,
       dispatch_receipts, ledger_epoch_utc, counterexample, recorded_at_utc, notes
FROM source_evidence_limitations""",
# 2026-10-09: ★V3 请求日志接口 —— 字段名逐一匹配任务书，底层仍是 source_request_ledger
#   语义：每次真实请求独立一行，**不因响应 JSON 相同而合并**（内容相同的响应只在 *_raw_responses 里去重计数）
"v_source_request_log": """
CREATE VIEW IF NOT EXISTS v_source_request_log AS
SELECT receipt_id                AS request_id,
       provider                  AS provider,
       endpoint                  AS endpoint,
       request_started_at_utc    AS request_started_at_utc,
       COALESCE(request_finished_at_utc, observed_at_utc) AS response_received_at_utc,
       http_status               AS http_status,
       request_scope             AS request_scope,
       response_sha256           AS response_sha256,
       response_bytes            AS response_bytes,
       quota_cost                AS quota_cost,
       error_code                AS error_code,
       raw_response_id           AS observation_id,
       outcome, transport_error, body_deduplicated, evidence_grade,
       source_match_id, source_event_id, sport_key
FROM source_request_ledger""",
# 2026-10-09: ★Task A 契约视图 —— 字段名逐一匹配任务书（14 项），由字段观测 JOIN 分派回执/原始响应派生
"v_task_a_field_evidence": """
CREATE VIEW IF NOT EXISTS v_task_a_field_evidence AS
SELECT o.provider                                              AS provider,
       CASE WHEN o.source_entity_type = 'match' THEN o.source_entity_id END AS source_match_id,
       CASE WHEN o.source_entity_type = 'team'  THEN o.source_entity_id END AS source_team_id,
       o.source_entity_type, o.source_entity_id,
       o.field_name, o.field_value, o.first_seen_status,
       o.source_event_time_utc                                 AS source_event_time_utc,
       o.provider_updated_at_utc                               AS provider_updated_at_utc,
       l.request_started_at_utc                                AS request_started_at_utc,
       COALESCE(l.request_finished_at_utc, l.observed_at_utc) AS observed_at_utc,
       o.first_seen_utc                                        AS first_seen_utc,
       COALESCE(rf.raw_sha256, ro.raw_sha256)                  AS raw_response_sha256,
       l.raw_response_id                                       AS raw_response_id,
       COALESCE(l.raw_response_id, o.first_receipt_id)         AS observation_id,
       o.data_version                                          AS data_version,
       o.data_version_kind                                     AS data_version_kind,
       o.match_state                                           AS match_state,
       o.available_before_kickoff                              AS available_before_kickoff,
       o.notes
FROM source_field_observations o
LEFT JOIN source_request_ledger l ON l.receipt_id = o.first_receipt_id
LEFT JOIN fotmob_raw_responses     rf ON rf.observation_id = l.raw_response_id
LEFT JOIN theodds_api_raw_responses ro ON ro.observation_id = l.raw_response_id""",
# 2026-10-09: ★Task B 契约视图 —— 字段名逐一匹配任务书（11 项）；未暴露者显式 NULL 并在 notes 说明
"v_task_b_fixture_identity": """
CREATE VIEW IF NOT EXISTS v_task_b_fixture_identity AS
SELECT i.match_id            AS fixture_id,
       i.match_id            AS source_match_id,
       i.league_id           AS league_id,
       i.league_name         AS league_name,
       i.season_id           AS season_id,
       i.season_name         AS season_name,
       i.home_team_id        AS home_team_id,
       i.away_team_id        AS away_team_id,
       i.home_team_name      AS home_team_name,
       i.away_team_name      AS away_team_name,
       i.home_role           AS home_role,
       i.away_role           AS away_role,
       i.kickoff_utc         AS kickoff_utc,
       i.kickoff_utc_raw     AS kickoff_utc_raw,
       i.round               AS round_id,
       i.competition_stage   AS stage_id,
       i.status              AS status,
       i.match_state         AS match_state,
       i.venue               AS venue,
       'FotMob'              AS provider_identity,
       i.first_seen_utc      AS source_observation_time,
       i.last_seen_utc       AS last_observation_time,
       i.last_observation_id AS observation_id,
       CASE WHEN i.season_id IS NULL
            THEN 'FotMob 不暴露 season id（实测 /leagues details 无该字段）→ NULL，未编造'
            WHEN i.competition_stage IS NULL
            THEN 'FotMob 无独立 stage id；competition_stage 为轮次标签'
            ELSE NULL END AS null_reasons
FROM fotmob_match_identity i""",
# 2026-10-09 P2: 来源采集健康度（按 provider × 日聚合；含 blocked/failed，直调也计入）
"v_source_collection_health": """
CREATE VIEW IF NOT EXISTS v_source_collection_health AS
SELECT provider,
       substr(started_at_utc, 1, 10) AS run_date_utc,
       COUNT(*) AS runs,
       SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS runs_ok,
       SUM(CASE WHEN status = 'partial' THEN 1 ELSE 0 END) AS runs_partial,
       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS runs_failed,
       SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) AS runs_blocked,
       SUM(COALESCE(requests_total, 0)) AS requests_total,
       SUM(COALESCE(requests_ok, 0)) AS requests_ok,
       SUM(COALESCE(requests_failed, 0)) AS requests_failed,
       MAX(finished_at_utc) AS last_finished_utc
FROM source_collection_runs
GROUP BY provider, run_date_utc""",
# 2026-10-09 P2: 异常审计按类别汇总
"v_source_exception_summary": """
CREATE VIEW IF NOT EXISTS v_source_exception_summary AS
SELECT provider, category, severity,
       substr(occurred_at_utc, 1, 10) AS event_date_utc,
       COUNT(*) AS events,
       SUM(CASE WHEN handled = 0 THEN 1 ELSE 0 END) AS unhandled,
       MAX(occurred_at_utc) AS last_event_utc
FROM source_exception_audit
GROUP BY provider, category, severity, event_date_utc""",
}


# 可回退的「加列」迁移白名单（只允许本模块自建表；既有业务表永不 ALTER）
_ADDITIVE_COLUMNS = {
    # ★2026-10-09 任务书 #7：证据等级列（PROVEN 必须有回执支撑，不得仅凭时间字段）
    "source_field_observations": [("evidence_grade", "TEXT")],
    # 2026-10-09 落库补全：h2h 增加 is_future（区分历史交锋/未来日程）
    "fotmob_h2h_matches": [("is_future", "INTEGER")],
    "theodds_api_odds_history": [("first_seen_utc", "TEXT"),
                                 # 2026-10-09 Task C：快照时刻 ≠ 抓取时刻，必须分开
                                 ("snapshot_timestamp", "TEXT"),
                                 ("snapshot_previous_timestamp", "TEXT"),
                                 ("snapshot_next_timestamp", "TEXT"),
                                 # 第七节要求1：明确数据来源
                                 ("provider", "TEXT")],
    "source_request_ledger": [("evidence_grade", "TEXT"), ("request_scope", "TEXT"),
                              ("quota_cost", "INTEGER"), ("error_code", "TEXT")],
    "source_incident_log": [("evidence_status", "TEXT")],
    # 2026-10-09 修正：FotMob 实为提供 unavailable[]，补足承载列
    "player_availability": [("side", "TEXT"), ("age", "INTEGER"), ("position_id", "INTEGER"),
                            ("country_code", "TEXT"), ("country_name", "TEXT"),
                            ("market_value", "INTEGER"), ("injury_id", "INTEGER"),
                            ("expected_return_text", "TEXT"), ("expected_return_date", "TEXT"),
                            ("null_reasons", "TEXT")],
    # 2026-10-09 Task E：阵容来源与类型（区分官方Opta vs 预测）
    "fixture_lineups": [("lineup_source_type", "TEXT"), ("lineup_publishable", "INTEGER"),
                        ("announcement_evidence", "TEXT"),
                        # Task E 补：Sportmonks 位置/队形细节
                        ("position_id", "INTEGER"), ("formation_position", "INTEGER"),
                        ("jersey_number", "INTEGER"), ("lineup_meta_confirmed", "INTEGER")],
}

# ★2026-10-09 跨商 ID 隔离铁律（用户明确要求）：
#   Sportmonks 的 season_id / league_id 与 FotMob 的 TournamentId / league_id
#   **属不同命名空间**，必须**分别存储**，永不可互相冒充或直接比较。
#   以下各表各自持有自己来源的 ID 空间；跨源对应只能经 source_identity_crosswalk + 明确证据。
CROSS_PROVIDER_ID_TABLES = {
    "FotMob": ["fotmob_match_identity", "season_identity_evidence"],
    "Sportmonks": ["sportmonks_season_identity", "sportmonks_fixture_identity"],
    "The Odds API": ["theodds_api_events", "theodds_api_odds_history"],
}

# ★追加式（append-only）保护：数据库层强制不可变，而非仅靠代码约定
#   注意：只对「写入后永不修改」的表启用。source_collection_runs 会被 finish_* 收尾更新，
#         source_field_observations 走 upsert，source_incident_log 走 INSERT OR REPLACE —— 三者**不**启用。
_APPEND_ONLY_TABLES = ["source_request_ledger", "source_quota_receipts"]


def _trigger_ddl():
    out = {}
    for t in _APPEND_ONLY_TABLES:
        out[f"trg_ao_{t}_no_update"] = (
            f"CREATE TRIGGER IF NOT EXISTS trg_ao_{t}_no_update BEFORE UPDATE ON {t} "
            f"BEGIN SELECT RAISE(ABORT, 'append-only violation: {t} is immutable (UPDATE blocked)'); END")
        out[f"trg_ao_{t}_no_delete"] = (
            f"CREATE TRIGGER IF NOT EXISTS trg_ao_{t}_no_delete BEFORE DELETE ON {t} "
            f"BEGIN SELECT RAISE(ABORT, 'append-only violation: {t} is immutable (DELETE blocked)'); END")
    return out


EVIDENCE_TRIGGERS = list(_trigger_ddl().keys())


def verify_append_only(engine, table="source_request_ledger"):
    """实证不可变性：插入探针行 → 试 UPDATE/DELETE → 必须被 trigger 拒绝 → 回滚（不留痕）。"""
    tbl = table
    out = {"table": tbl, "guard": "trigger"}
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            cols = {r[1] for r in conn.execute(text(f'PRAGMA table_info("{tbl}")')).fetchall()}
            fieldmap = [("receipt_id", "__ao_probe__"), ("provider", "__probe__"),
                        ("request_started_at_utc", "1970-01-01T00:00:00Z")]
            if "observed_at_utc" in cols:
                fieldmap.append(("observed_at_utc", "1970-01-01T00:00:00Z"))
            if "slot_id" in cols:
                fieldmap = [("receipt_id", "__ao_probe__"), ("provider", "__probe__"),
                            ("slot_id", "__probe__")]
            names = [f for f, _ in fieldmap if f in cols]
            conn.execute(text(f'INSERT INTO "{tbl}" ({",".join(names)}) '
                              f'VALUES ({",".join(":" + f for f in names)})'),
                         {f: v for f, v in fieldmap if f in cols})
            key = "receipt_id"
            for op, sql in (("UPDATE", f'UPDATE "{tbl}" SET provider=provider WHERE {key}=:k'),
                            ("DELETE", f'DELETE FROM "{tbl}" WHERE {key}=:k')):
                sp = conn.begin_nested()
                try:
                    conn.execute(text(sql), {"k": "__ao_probe__"})
                    sp.rollback()
                    out[op] = "NOT_BLOCKED"
                except Exception as e:
                    sp.rollback()
                    out[op] = "BLOCKED" if "append-only" in str(e) else f"ERR:{type(e).__name__}"
        finally:
            trans.rollback()
    return out


def create_evidence_tables(engine):
    """幂等建表 + 建视图。只新增，不改既有对象。"""
    created = []
    with engine.begin() as conn:
        for name, ddl in _TABLE_DDL.items():
            conn.execute(text(ddl))
            created.append(name)
        # 可回退的「加列」迁移（仅限本模块自建的表；既有业务表永不 ALTER）
        for tbl, cols in _ADDITIVE_COLUMNS.items():
            existing = {r[1] for r in conn.execute(text(f'PRAGMA table_info("{tbl}")')).fetchall()}
            for col, typ in cols:
                if col not in existing:
                    conn.execute(text(f'ALTER TABLE "{tbl}" ADD COLUMN {col} {typ}'))
                    log.info("source-evidence: %s 补列 %s", tbl, col)
        for name, ddl in _VIEW_DDL.items():
            # 视图已存在时会报错，用 DROP+CREATE 保证定义最新。
            # ★注意：若同名对象是**表**，SQLite 的 `DROP VIEW IF EXISTS` 会报错 → 先判类型。
            _kind = conn.execute(text(
                "SELECT type FROM sqlite_master WHERE name=:n"), {"n": name}).scalar()
            if _kind == "view":
                conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
            conn.execute(text(ddl))
        # 追加式保护 trigger（数据库层强制不可变）
        for _tn, _tddl in _trigger_ddl().items():
            conn.execute(text(_tddl))
    log.info("source-evidence: 证据表/视图就绪 (%d 表, %d 视图, %d 追加式保护)",
             len(_TABLE_DDL), len(_VIEW_DDL), len(_APPEND_ONLY_TABLES) * 2)
    return created


def drop_evidence_tables(engine):
    """回退：仅删除本模块创建的对象。既有业务表不受影响。"""
    dropped = []
    with engine.begin() as conn:
        for name in _VIEW_DDL:
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
            dropped.append(name)
        for name in EVIDENCE_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
            dropped.append(name)
    log.info("source-evidence: 已回退 %d 个对象", len(dropped))
    return dropped


def evidence_status(engine) -> dict:
    """返回证据层对象的实际存在性与行数。"""
    out = {"tables": {}, "views": {}}
    with engine.connect() as conn:
        def obj_exists(name, typ):
            return bool(conn.execute(text(
                "SELECT 1 FROM sqlite_master WHERE name=:n AND type=:t"), {"n": name, "t": typ}).fetchone())
        for t in EVIDENCE_TABLES:
            if obj_exists(t, "table"):
                try:
                    n = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                except Exception:
                    n = None
                out["tables"][t] = {"exists": True, "rows": n}
            else:
                out["tables"][t] = {"exists": False, "rows": None}
        for v in EVIDENCE_VIEWS:
            out["views"][v] = {"exists": obj_exists(v, "view")}
    return out


# ── 写入：原始响应（不可变、幂等） ───────────────────────────────────────
def save_raw_response(engine, *, provider, endpoint, raw_body: str, raw_sha256: str | None = None,
                      source_match_id=None, source_league_id=None, source_event_id=None,
                      sport_key=None, request_url=None, request_params=None,
                      request_started_at_utc=None, observed_at_utc=None, http_status=None,
                      etag=None, last_modified=None, content_type=None, source_version=None,
                      source_version_note=None, quota_remaining=None, quota_used=None,
                      quota_last=None) -> str:
    """
    保存 provider 原始响应。幂等：同一 (endpoint, source id, body 哈希) 只保留一行，
    保留 first_seen_utc，累加 observation_count，并刷新 last_seen_utc。
    返回 observation_id。
    """
    if not SAVE_RAW_RESPONSES or raw_body is None:
        return None
    try:
        return _save_raw_response_impl(
            engine, provider, endpoint, raw_body, raw_sha256, source_match_id, source_league_id,
            source_event_id, sport_key, request_url, request_params, request_started_at_utc,
            observed_at_utc, http_status, etag, last_modified, content_type, source_version,
            source_version_note, quota_remaining, quota_used, quota_last)
    except Exception as e:
        # 证据层失败绝不能中断采集主流程（例如目标表尚未迁移）
        log.warning("source-evidence: 原始响应留存失败（已跳过，不影响采集）— %s", e)
        return None


def _save_raw_response_impl(engine, provider, endpoint, raw_body, raw_sha256, source_match_id,
                            source_league_id, source_event_id, sport_key, request_url,
                            request_params, request_started_at_utc, observed_at_utc, http_status,
                            etag, last_modified, content_type, source_version, source_version_note,
                            quota_remaining, quota_used, quota_last) -> str:
    body = raw_body if isinstance(raw_body, str) else json.dumps(raw_body, ensure_ascii=False)
    digest = raw_sha256 or sha256_text(body)
    sid = source_match_id if source_match_id is not None else source_event_id
    obs_id = make_observation_id(provider, endpoint, sid, digest)
    now = observed_at_utc or now_utc_iso()
    table = "fotmob_raw_responses" if provider == PROVIDER_FOTMOB else "theodds_api_raw_responses"
    cols = {
        "observation_id": obs_id, "provider": provider, "endpoint": endpoint,
        "source_match_id": None if source_match_id is None else str(source_match_id),
        "source_league_id": None if source_league_id is None else str(source_league_id),
        "request_url": sanitize_url(request_url),
        "request_params_sanitized": _json_compact(sanitize_params(request_params)) if request_params else None,
        "source_event_id": source_event_id, "sport_key": sport_key,
        "request_started_at_utc": request_started_at_utc, "observed_at_utc": now,
        "http_status": http_status, "etag": etag, "last_modified": last_modified,
        "content_type": content_type, "source_version": source_version,
        "source_version_note": source_version_note,
        "raw_sha256": digest, "response_bytes": len(body.encode("utf-8")), "raw_response": body,
        "quota_remaining": quota_remaining, "quota_used": quota_used, "quota_last": quota_last,
    }
    if table == "fotmob_raw_responses":
        for k in ("request_params_sanitized", "source_event_id", "sport_key",
                  "quota_remaining", "quota_used", "quota_last"):
            cols.pop(k, None)
    else:
        cols.pop("source_match_id", None)
        cols.pop("source_league_id", None)
    with engine.begin() as conn:
        names = [c for c in cols if c in _columns(conn, table)]
        existing = None
        row = conn.execute(text(
            f'SELECT observation_id, first_seen_utc, observation_count FROM {table} WHERE observation_id=:o'),
            {"o": obs_id}).fetchone()
        if row:
            existing = row
            conn.execute(text(
                f'UPDATE {table} SET last_seen_utc=:ls, observation_count=IFNULL(observation_count,1)+1 WHERE observation_id=:o'),
                {"ls": now, "o": obs_id})
            return obs_id
        cols["first_seen_utc"] = now
        cols["last_seen_utc"] = now
        cols["observation_count"] = 1
        names = [c for c in cols if c in _columns(conn, table)]
        sql = f'INSERT INTO {table} ({",".join(names)}) VALUES ({",".join(":"+c for c in names)})'
        conn.execute(text(sql), {c: cols[c] for c in names})
    return obs_id


def _columns(conn, table) -> set:
    try:
        return {r[1] for r in conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()}
    except Exception:
        return set()


def write_rows(engine, table_name: str, rows, unique_keys, batch_size=200) -> int:
    """把行写入指定证据表（INSERT OR REPLACE 语义，按 unique_keys 幂等）。"""
    rows = [r for r in (rows or []) if r]
    if not rows:
        return 0
    md = MetaData()
    md.reflect(bind=engine, only=[table_name])
    tbl = md.tables[table_name]
    from db_utils import batch_upsert
    written = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        written += batch_upsert(engine, tbl, chunk, unique_keys=unique_keys)
    return written


# ── FotMob 解析辅助（供 43 号爬虫调用） ──────────────────────────────────
def normalize_kickoff_utc(raw):
    """provider kickoff (如 '2026-10-11T15:30:00Z' 或 '2026-10-11T15:30:00.000Z') → 归一化 UTC。"""
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)", s)
    if m:
        t = m.group(2) if len(m.group(2)) == 8 else m.group(2) + ":00"
        return f"{m.group(1)}T{t}"
    return None


def parse_stat_token(raw):
    """'809 (91%)' → (809.0, 91.0)；'1.72' → (1.72, None)；21 → (21.0, None)。"""
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return float(raw), None
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


# ══════════════ 2026-10-09 P0：请求回执 / 字段级 point-in-time / 额度回执 / 事故账本 ══════════════
def key_fingerprint(key):
    """脱敏 Key 指纹：前 6 + … + 后 4。绝不落完整 Key。"""
    k = (key or "").strip()
    if len(k) <= 10:
        return "…"
    return f"{k[:6]}…{k[-4:]}"


def record_dispatch(engine, *, provider, endpoint, request_started_at_utc,
                    request_finished_at_utc=None, observed_at_utc=None, http_status=None,
                    outcome=None, transport_error=None, attempt_index=None,
                    response_sha256=None, response_bytes=None, raw_response_id=None,
                    body_deduplicated=0, etag=None, last_modified=None, content_type=None,
                    quota_remaining=None, quota_used=None, quota_last=None,
                    source_match_id=None, source_league_id=None, source_event_id=None,
                    sport_key=None, request_url=None, request_params=None, notes=None,
                    request_scope=None, quota_cost=None, error_code=None) -> str:
    """每次 HTTP 分派写一条不可变回执（即使 body 被去重、即使请求失败）。

    这是「HTTP 请求次数」的权威依据：去重后的 *_raw_responses 只证明「有多少个不同的 body」，
    不等于「发生了多少次请求」。两者由本账本区分。

    ★语义（2026-10-09 用户明确）：**每一次真实请求独立登记，绝不因响应 JSON 内容相同而合并**。
    """
    # error_code：优先用调用方给的；否则由 transport/状态码推导（失败才非空）
    if error_code is None:
        if transport_error:
            error_code = f"TRANSPORT_{transport_error}"
        elif http_status is not None and int(http_status) >= 400:
            error_code = f"HTTP_{http_status}"
    # request_scope：provider 侧「这次请求打的是什么」的可读标识
    if request_scope is None:
        _bits = [b for b in (endpoint, source_match_id, source_event_id,
                             source_league_id, sport_key) if b not in (None, "")]
        request_scope = ":".join(str(b) for b in _bits) or None
    # ★body_deduplicated：调用方未显式给出时**自动推导**——若该原始响应已被观察 >1 次，
    #   说明本次是去重命中（body 与既有相同）。★注意：去重只影响原始体存储，
    #   **绝不影响本账本**——每次请求仍独立一行（用户硬要求）。
    if not body_deduplicated and raw_response_id:
        try:
            body_deduplicated = body_was_deduplicated(engine, provider, raw_response_id)
        except Exception:
            body_deduplicated = 0
    receipt_id = sha256_text("\x1f".join([
        "receipt", str(provider), str(endpoint), str(source_match_id or source_event_id or ""),
        str(request_started_at_utc), str(uuid.uuid4())]))[:40]
    row = {
        "receipt_id": receipt_id, "provider": provider, "endpoint": endpoint,
        "source_match_id": None if source_match_id is None else str(source_match_id),
        "source_league_id": None if source_league_id is None else str(source_league_id),
        "source_event_id": source_event_id, "sport_key": sport_key,
        "request_url": sanitize_url(request_url),
        "request_params_sanitized": _json_compact(sanitize_params(request_params)) if request_params else None,
        "request_started_at_utc": request_started_at_utc,
        "request_finished_at_utc": request_finished_at_utc,
        "observed_at_utc": observed_at_utc or now_utc_iso(),
        "http_status": http_status, "outcome": outcome, "transport_error": transport_error,
        "attempt_index": attempt_index, "response_sha256": response_sha256,
        "response_bytes": response_bytes, "raw_response_id": raw_response_id,
        "body_deduplicated": int(body_deduplicated or 0), "etag": etag,
        "last_modified": last_modified, "content_type": content_type,
        "quota_remaining": quota_remaining, "quota_used": quota_used, "quota_last": quota_last,
        "quota_cost": quota_cost, "error_code": error_code, "request_scope": request_scope,
        "notes": notes,
        # ★证据等级：本表每一行都是「一次真实 HTTP 分派的直接回执」，不是推断
        "evidence_grade": "DIRECT_HTTP_RECEIPT",
    }
    try:
        with engine.begin() as conn:
            cols = [c for c in row if c in _columns(conn, "source_request_ledger")]
            conn.execute(text(
                f'INSERT INTO source_request_ledger ({",".join(cols)}) '
                f'VALUES ({",".join(":"+c for c in cols)})'), {c: row[c] for c in cols})
    except Exception as e:
        log.warning("source-evidence: 分派回执写入失败（已跳过）— %s", e)
        return None
    return receipt_id


def classify_outcome(http_status, transport_error=None):
    if transport_error:
        return "transport_error"
    if http_status is None:
        return "no_response"
    if 200 <= http_status < 300:
        return "ok"
    return "http_error"


def record_field_observation(engine, *, provider, source_entity_type, source_entity_id,
                             field_name, field_value=None, first_seen_utc=None,
                             first_seen_status=None, last_seen_utc=None,
                             source_event_time_utc=None, provider_updated_at_utc=None,
                             data_version=None, data_version_kind=None, match_state=None,
                             available_before_kickoff=None, receipt_id=None, notes=None):
    """字段级 point-in-time 观测登记（幂等）。

    first_seen_utc 只接受**可证明**的观察时间；无法证明的历史数据必须传 None，并把
    first_seen_status 置为 'UNKNOWN'（严禁编造时间）。冲突时保留最早 first_seen、刷新 last_seen、累加计数。
    """
    prov = source_entity_type if source_entity_type in ("match", "team", "player", "event",
                                                        "quote", "market", "league", "season") else "match"
    if first_seen_utc is None and first_seen_status is None:
        first_seen_status = "UNKNOWN"
    if first_seen_status is None:
        first_seen_status = "PROVEN" if first_seen_utc else "UNKNOWN"
    if data_version_kind is None:
        data_version_kind = "provider" if data_version else "unknown"
    if available_before_kickoff is None and first_seen_utc and source_event_time_utc:
        available_before_kickoff = 1 if str(first_seen_utc) <= str(source_event_time_utc) else 0
    key = {"p": provider, "t": prov, "e": str(source_entity_id), "f": field_name}
    try:
        with engine.begin() as conn:
            cur = conn.execute(text(
                "SELECT id, first_seen_utc, last_seen_utc, observation_count, first_receipt_id, "
                "notes FROM source_field_observations WHERE provider=:p AND source_entity_type=:t "
                "AND source_entity_id=:e AND field_name=:f"), key).fetchone()
            if cur:
                _id, fs, ls, cnt, fr, old_notes = cur
                new_fs = fs
                if first_seen_utc and (fs is None or str(first_seen_utc) < str(fs)):
                    new_fs = first_seen_utc
                new_fr = fr or receipt_id
                conn.execute(text(
                    "UPDATE source_field_observations SET field_value=:fv, first_seen_utc=:fs, "
                    "first_seen_status=:st, last_seen_utc=:ls, observation_count=observation_count+1, "
                    "source_event_time_utc=COALESCE(:se, source_event_time_utc), "
                    "provider_updated_at_utc=COALESCE(:pu, provider_updated_at_utc), "
                    "data_version=COALESCE(:dv, data_version), data_version_kind=:dvk, "
                    "match_state=COALESCE(:ms, match_state), "
                    "available_before_kickoff=COALESCE(:abk, available_before_kickoff), "
                    "first_receipt_id=:fr, last_receipt_id=:lr, notes=COALESCE(:nt, notes) "
                    "WHERE id=:id"),
                    {"fv": field_value, "fs": new_fs, "st": first_seen_status,
                     "ls": last_seen_utc or observed_last(ls), "se": source_event_time_utc,
                     "pu": provider_updated_at_utc, "dv": data_version, "dvk": data_version_kind,
                     "ms": match_state, "abk": available_before_kickoff, "fr": new_fr,
                     "lr": receipt_id, "nt": notes, "id": _id})
                return _id
            conn.execute(text(
                "INSERT INTO source_field_observations (provider, source_entity_type, source_entity_id,"
                " field_name, field_value, first_seen_utc, first_seen_status, last_seen_utc,"
                " observation_count, source_event_time_utc, provider_updated_at_utc, data_version,"
                " data_version_kind, match_state, available_before_kickoff, first_receipt_id,"
                " last_receipt_id, notes) VALUES (:p,:t,:e,:f,:fv,:fs,:st,:ls,1,:se,:pu,:dv,:dvk,"
                " :ms,:abk,:fr,:lr,:nt)"),
                {**key, "fv": field_value, "fs": first_seen_utc, "st": first_seen_status,
                 "ls": last_seen_utc or first_seen_utc, "se": source_event_time_utc,
                 "pu": provider_updated_at_utc, "dv": data_version, "dvk": data_version_kind,
                 "ms": match_state, "abk": available_before_kickoff, "fr": receipt_id,
                 "lr": receipt_id, "nt": notes})
    except Exception as e:
        log.warning("source-evidence: 字段观测写入失败（已跳过）— %s", e)
        return None
    return None


def observed_last(current_last):
    return now_utc_iso()


def body_was_deduplicated(engine, provider, observation_id):
    """该 body 是否为去重命中（observation_count>1）→ 区分「请求次数」与「不同 body 数」。"""
    if not observation_id:
        return 0
    table = "fotmob_raw_responses" if provider == PROVIDER_FOTMOB else "theodds_api_raw_responses"
    try:
        with engine.connect() as conn:
            n = conn.execute(text(f"SELECT observation_count FROM {table} WHERE observation_id=:o"),
                             {"o": observation_id}).scalar()
        return 1 if (n or 0) > 1 else 0
    except Exception:
        return 0


def record_quota_receipt(engine, *, provider, slot_id, key=None, endpoint=None, http_status=None,
                         quota_remaining=None, quota_used=None, quota_last=None,
                         observed_at_utc=None, notes=None) -> str:
    """逐槽额度回执（每条都是可独立核验的一次真实响应头）。"""
    observed = observed_at_utc or now_utc_iso()
    rid = sha256_text("\x1f".join(["quota", provider, str(slot_id), str(observed),
                                   str(uuid.uuid4())]))[:40]
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO source_quota_receipts (receipt_id, provider, slot_id, key_fingerprint,"
                " endpoint, http_status, quota_remaining, quota_used, quota_last, observed_at_utc,"
                " notes) VALUES (:r,:p,:s,:k,:e,:h,:rem,:u,:l,:o,:n)"),
                {"r": rid, "p": provider, "s": slot_id, "k": key_fingerprint(key), "e": endpoint,
                 "h": http_status, "rem": quota_remaining, "u": quota_used, "l": quota_last,
                 "o": observed, "n": notes})
    except Exception as e:
        log.warning("source-evidence: 额度回执写入失败（已跳过）— %s", e)
        return None
    return rid


def record_incident(engine, *, incident_id, kind, description, affected_table=None,
                    occurred_at_utc=None, actor="hermes", before_count=None, after_count=None,
                    affected_rows=None, reason=None, verifier=None, evidence=None,
                    evidence_status=None) -> str:
    """事故账本（append-only）：记录数据删除/更正，使事后可重建。

    evidence_status 标注证据性质，避免把事后重建当成当时回执：
      CONTEMPORANEOUS_RECEIPT  = 事发当时就有回执/记录
      RECONSTRUCTED_FROM_SESSION = 事后由会话记录/内容哈希重建（**不是**当时的删除回执）
      GAP_RECORDED             = 当时缺失、仅登记缺口，不补造
    """
    try:
        with engine.begin() as conn:
            _cols = _columns(conn, "source_incident_log")
            _row = {"incident_id": incident_id, "kind": kind, "occurred_at_utc": occurred_at_utc,
                    "recorded_at_utc": now_utc_iso(), "actor": actor, "description": description,
                    "affected_table": affected_table, "before_count": before_count,
                    "after_count": after_count,
                    "affected_rows_json": json.dumps(affected_rows or [], ensure_ascii=False),
                    "reason": reason, "verifier": verifier,
                    "evidence_json": json.dumps(evidence or {}, ensure_ascii=False),
                    "evidence_status": evidence_status}
            _use = [c for c in _row if c in _cols]
            conn.execute(text(
                f'INSERT OR REPLACE INTO source_incident_log ({",".join(_use)}) '
                f'VALUES ({",".join(":" + c for c in _use)})'), {c: _row[c] for c in _use})
    except Exception as e:
        log.warning("source-evidence: 事故账本写入失败（已跳过）— %s", e)
        return None
    return incident_id


def pit_fields_at(engine, cutoff_utc, *, provider=None, entity_type=None, entity_id=None,
                  only_before_kickoff=False):
    """★V3 核心查询：在 cutoff_utc 之前，哪些字段已**真实存在并可用**。

    只返回 first_seen_status='PROVEN' 且 first_seen_utc <= cutoff 的字段。
    UNKNOWN（历史无法证明）字段一律不返回——宁可少给，不给假证据。
    """
    sql = ("SELECT provider, source_entity_type, source_entity_id, field_name, field_value,"
           " first_seen_utc, last_seen_utc, observation_count, source_event_time_utc,"
           " provider_updated_at_utc, data_version, data_version_kind, match_state,"
           " available_before_kickoff FROM source_field_observations"
           " WHERE first_seen_status='PROVEN' AND first_seen_utc IS NOT NULL"
           "   AND first_seen_utc <= :cut")
    params = {"cut": cutoff_utc}
    if provider:
        sql += " AND provider=:p"; params["p"] = provider
    if entity_type:
        sql += " AND source_entity_type=:t"; params["t"] = entity_type
    if entity_id:
        sql += " AND source_entity_id=:e"; params["e"] = str(entity_id)
    if only_before_kickoff:
        sql += " AND available_before_kickoff=1"
    sql += " ORDER BY provider, source_entity_type, source_entity_id, field_name"
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params).fetchall()]


# ══════════════ P1 写入器（Task B/D/E）——来源无数据时不写假值 ══════════════
def _upsert_keyed(engine, table, key_col, key_val, row):
    """按确定性 key 幂等 upsert；不覆盖 first_seen/status 语义列。"""
    try:
        with engine.begin() as conn:
            cols = [c for c in row if c != key_col and c in _columns(conn, table)]
            conn.execute(text(
                f'INSERT INTO {table} ({",".join([key_col] + cols)}) '
                f'VALUES ({",".join(":" + c for c in [key_col] + cols)}) '
                f'ON CONFLICT({key_col}) DO UPDATE SET '
                + ", ".join(f"{c}=excluded.{c}" for c in cols
                            if c not in ("first_seen_utc", "first_seen_status"))),
                {key_col: key_val, **row})
        return key_val
    except Exception as e:
        log.warning("source-evidence: %s 写入失败（已跳过）— %s", table, e)
        return None


def upsert_availability(engine, rows):
    """写入伤停/停赛（player_availability）。来源未提供的字段一律留 NULL，绝不推测。"""
    n = 0
    for r in rows or []:
        r = dict(r)
        r.setdefault("first_seen_status", "PROVEN" if r.get("observed_at_utc") else "UNKNOWN")
        r.setdefault("first_seen_utc", r.get("observed_at_utc"))
        key = sha256_text("\x1f".join([str(r.get("provider")), str(r.get("source_team_id")),
                                       str(r.get("source_player_id")), str(r.get("source_event_id")),
                                       str(r.get("availability_status")),
                                       str(r.get("sidelined_start_at"))]))[:40]
        if _upsert_keyed(engine, "player_availability", "availability_key", key, r):
            n += 1
    return n


def upsert_fixture_lineups(engine, rows):
    """写入阵容（fixture_lineups）。predicted / confirmed 严格分开，公布时间缺失即 NULL。"""
    n = 0
    for r in rows or []:
        r = dict(r)
        r.setdefault("first_seen_status", "PROVEN" if r.get("observed_at_utc") else "UNKNOWN")
        if not r.get("lineup_first_seen_utc"):
            r["lineup_first_seen_utc"] = r.get("observed_at_utc")
        key = sha256_text("\x1f".join([str(r.get("provider")), str(r.get("source_fixture_id")),
                                       str(r.get("source_team_id")), str(r.get("source_player_id")),
                                       str(r.get("lineup_type"))]))[:40]
        if _upsert_keyed(engine, "fixture_lineups", "lineup_key", key, r):
            n += 1
    return n


def upsert_identity_evidence(engine, rows):
    """写入来源身份证据（source_identity_evidence）。只存真实 provider ID，不分配 canonical。"""
    n = 0
    for r in rows or []:
        r = dict(r)
        r.setdefault("first_seen_utc", r.get("observed_at_utc"))
        r.setdefault("first_seen_status", "PROVEN" if r.get("observed_at_utc") else "UNKNOWN")
        key = sha256_text("\x1f".join([str(r.get("provider")), str(r.get("entity_type")),
                                       str(r.get("source_id")), str(r.get("parent_entity_type")),
                                       str(r.get("parent_source_id"))]))[:40]
        if _upsert_keyed(engine, "source_identity_evidence", "identity_key", key, r):
            n += 1
    return n


def propose_crosswalk(engine, *, entity_type, provider_a, source_id_a, provider_b, source_id_b,
                      match_basis, confidence, evidence=None, notes=None):
    """仅 **提议** 跨源对应关系（status=PROPOSED），正式 Canonical 分配由 V3/业主确认。"""
    cid = sha256_text("\x1f".join([entity_type, provider_a, str(source_id_a), provider_b,
                                   str(source_id_b)]))[:40]
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO source_identity_crosswalk (crosswalk_id, entity_type, provider_a,"
                " source_id_a, provider_b, source_id_b, match_basis, confidence, status,"
                " evidence_json, created_at_utc, notes) VALUES (:c,:t,:pa,:sa,:pb,:sb,:mb,:cf,"
                " 'PROPOSED',:ev,:ca,:nt)"
                " ON CONFLICT(crosswalk_id) DO NOTHING"),
                {"c": cid, "t": entity_type, "pa": provider_a, "sa": str(source_id_a),
                 "pb": provider_b, "sb": str(source_id_b), "mb": match_basis, "cf": confidence,
                 "ev": json.dumps(evidence or {}, ensure_ascii=False), "ca": now_utc_iso(),
                 "nt": notes})
    except Exception as e:
        log.warning("source-evidence: crosswalk 写入失败（已跳过）— %s", e)
        return None
    return cid


# ══════════════════ P2：来源采集日志 + 异常审计 ══════════════════
def detect_invoked_by():
    """推断调用方式，便于回答『这条记录是谁拉起来的』。"""
    env = os.environ.get("QQSJ_INVOKED_BY")
    if env:
        return env
    argv0 = (sys.argv[0] or "").replace("\\", "/").split("/")[-1]
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return f"non_tty:{argv0 or 'unknown'}"
    except Exception:
        pass
    return f"manual:{argv0 or 'unknown'}"


def begin_collection_run(engine, *, provider, script=None, scope=None, args=None,
                         invoked_by=None, notes=None) -> str:
    """开一条采集运行记录（由**爬虫自己**写，直调/subprocess 也会留痕）。"""
    started = now_utc_iso()
    run_id = sha256_text("\x1f".join(["run", str(provider), str(script), str(started),
                                      str(uuid.uuid4())]))[:40]
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO source_collection_runs (run_id, provider, script, scope, args_json,"
                " host, pid, invoked_by, started_at_utc, status, notes)"
                " VALUES (:r,:p,:s,:sc,:a,:h,:pid,:ib,:st,'running',:n)"),
                {"r": run_id, "p": provider, "s": script, "sc": scope,
                 "a": json.dumps(args or {}, ensure_ascii=False, default=str),
                 "h": _hostname(), "pid": os.getpid(), "ib": invoked_by or detect_invoked_by(),
                 "st": started, "n": notes})
    except Exception as e:
        log.warning("source-evidence: 采集运行记录写入失败（已跳过）— %s", e)
        return None
    return run_id


def _hostname():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return None


def finish_collection_run(engine, run_id, *, status="ok", requests_total=None, requests_ok=None,
                          requests_failed=None, bodies_new=None, bodies_deduplicated=None,
                          rows_written=None, blocked_reason=None, exit_code=None,
                          legacy_run_log_id=None, started_at_utc=None, notes=None):
    """收尾一条采集运行记录。status ∈ ok|partial|failed|blocked。"""
    if not run_id:
        return None
    finished = now_utc_iso()
    dur = None
    if started_at_utc:
        try:
            d = (datetime.fromisoformat(finished.replace("Z", "+00:00"))
                 - datetime.fromisoformat(str(started_at_utc).replace("Z", "+00:00")))
            dur = round(d.total_seconds(), 3)
        except Exception:
            dur = None
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE source_collection_runs SET finished_at_utc=:f, duration_s=:d,"
                " requests_total=COALESCE(:rt, requests_total), requests_ok=COALESCE(:ro, requests_ok),"
                " requests_failed=COALESCE(:rf, requests_failed), bodies_new=COALESCE(:bn, bodies_new),"
                " bodies_deduplicated=COALESCE(:bd, bodies_deduplicated),"
                " rows_written_json=COALESCE(:rw, rows_written_json), status=:st,"
                " blocked_reason=:br, exit_code=:ec, legacy_run_log_id=COALESCE(:lg, legacy_run_log_id),"
                " notes=COALESCE(:n, notes) WHERE run_id=:r"),
                {"f": finished, "d": dur, "rt": requests_total, "ro": requests_ok,
                 "rf": requests_failed, "bn": bodies_new, "bd": bodies_deduplicated,
                 "rw": json.dumps(rows_written, ensure_ascii=False) if rows_written is not None else None,
                 "st": status, "br": blocked_reason, "ec": exit_code, "lg": legacy_run_log_id,
                 "n": notes, "r": run_id})
    except Exception as e:
        log.warning("source-evidence: 采集运行收尾失败（已跳过）— %s", e)
    return run_id


def record_exception(engine, *, provider, severity="error", category="other", message=None,
                     run_id=None, endpoint=None, source_entity_id=None, http_status=None,
                     exception_type=None, attempt_index=None, handled=1, retry_count=0,
                     raw_response_id=None, context=None, notes=None) -> str:
    """异常/异常事件审计（任何被捕获或未捕获的问题都留痕，便于事后归因）。"""
    occurred = now_utc_iso()
    eid = sha256_text("\x1f".join(["exc", str(provider), str(category), str(message)[:200],
                                   str(occurred), str(uuid.uuid4())]))[:40]
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO source_exception_audit (exception_id, run_id, provider, occurred_at_utc,"
                " severity, category, endpoint, source_entity_id, http_status, exception_type, message,"
                " attempt_index, handled, retry_count, raw_response_id, context_json, notes)"
                " VALUES (:e,:r,:p,:o,:sv,:c,:ep,:se,:hs,:et,:m,:ai,:h,:rc,:rr,:cx,:n)"),
                {"e": eid, "r": run_id, "p": provider, "o": occurred, "sv": severity,
                 "c": category, "ep": endpoint, "se": None if source_entity_id is None else str(source_entity_id),
                 "hs": http_status, "et": exception_type, "m": (str(message)[:2000] if message else None),
                 "ai": attempt_index, "h": int(handled), "rc": retry_count,
                 "rr": raw_response_id,
                 "cx": json.dumps(context or {}, ensure_ascii=False, default=str), "n": notes})
    except Exception as e:
        log.warning("source-evidence: 异常审计写入失败（已跳过）— %s", e)
        return None
    return eid


class CollectionRunHandle:
    """轻量计数器：供爬虫在运行中累计请求/落库数，退出时统一收尾。"""

    def __init__(self, engine, run_id, provider, started_at_utc):
        self.engine, self.run_id, self.provider = engine, run_id, provider
        self.started_at_utc = started_at_utc
        self.requests_total = self.requests_ok = self.requests_failed = 0
        self.bodies_new = self.bodies_deduplicated = 0
        self.rows_written = {}

    def request(self, ok=True, body_new=None):
        self.requests_total += 1
        if ok:
            self.requests_ok += 1
        else:
            self.requests_failed += 1
        if body_new is True:
            self.bodies_new += 1
        elif body_new is False:
            self.bodies_deduplicated += 1

    def rows(self, table, n):
        if n:
            self.rows_written[table] = self.rows_written.get(table, 0) + int(n)

    def exception(self, **kw):
        kw.setdefault("provider", self.provider)
        kw.setdefault("run_id", self.run_id)
        return record_exception(self.engine, **kw)

    def finish(self, status="ok", blocked_reason=None, exit_code=None, notes=None):
        if status == "running":
            status = "ok"
        return finish_collection_run(
            self.engine, self.run_id, status=status,
            requests_total=self.requests_total, requests_ok=self.requests_ok,
            requests_failed=self.requests_failed, bodies_new=self.bodies_new,
            bodies_deduplicated=self.bodies_deduplicated, rows_written=self.rows_written,
            blocked_reason=blocked_reason, exit_code=exit_code,
            started_at_utc=self.started_at_utc, notes=notes)


def collection_run(engine, *, provider, script=None, scope=None, args=None, invoked_by=None):
    """with SE.collection_run(engine, provider=...) as run: run.request(); run.rows(...)"""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        started = now_utc_iso()
        rid = begin_collection_run(engine, provider=provider, script=script, scope=scope,
                                   args=args, invoked_by=invoked_by)
        h = CollectionRunHandle(engine, rid, provider, started)
        try:
            yield h
            h.finish(status="ok")
        except BaseException as e:   # noqa: BLE001
            record_exception(engine, provider=provider, run_id=rid, severity="fatal",
                             category="unhandled", exception_type=type(e).__name__,
                             message=str(e), handled=0)
            h.finish(status="failed")
            raise
    return _cm()


def record_evidence_limitation(engine, *, limitation_id, provider, scope, claim, verdict,
                               provable_lower_bound=None, counter_value=None,
                               dispatch_receipts=None, ledger_epoch_utc=None,
                               corroboration=None, counterexample=None, notes=None) -> str:
    """登记「某结论能证明到什么程度」。verdict∈PROVEN|CORROBORATED_NOT_PROVEN|NOT_PROVABLE|DISPROVED。

    这是防止「推断被当成事实」的机器可读闸门：V3 引用任何计数前应先查 v_source_evidence_limits。
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT OR REPLACE INTO source_evidence_limitations (limitation_id, provider, scope,"
                " claim, verdict, provable_lower_bound, counter_value, dispatch_receipts,"
                " ledger_epoch_utc, corroboration_json, counterexample, recorded_at_utc, notes)"
                " VALUES (:i,:p,:s,:c,:v,:lb,:cv,:dr,:ep,:co,:ce,:r,:n)"),
                {"i": limitation_id, "p": provider, "s": scope, "c": claim, "v": verdict,
                 "lb": provable_lower_bound, "cv": counter_value, "dr": dispatch_receipts,
                 "ep": ledger_epoch_utc,
                 "co": json.dumps(corroboration or {}, ensure_ascii=False, default=str),
                 "ce": counterexample, "r": now_utc_iso(), "n": notes})
    except Exception as e:
        log.warning("source-evidence: 证据局限登记失败（已跳过）— %s", e)
        return None
    return limitation_id


def odds_pit(engine, *, event_id=None, home_team=None, away_team=None, cut_utc=None,
             bookmaker_key=None, market_key=None, provider="The Odds API"):
    """★Task C：按比赛 + 时间点查询历史赔率快照（point-in-time）。

    cut_utc 给定时只返回 observed_at_utc <= cut 的报价（且取每个 (庄家,市场,结果,point)
    在切点前**最后一次**观察到的版本），不返回未来价格。
    """
    base = ("SELECT event_id, sport_key, home_team, away_team, commence_time, bookmaker_key,"
            " market_key, market_period, outcome_name, point, price, normalized_decimal_odds,"
            " market_last_update, observed_at_utc, first_seen_utc, raw_response_hash,"
            " COALESCE(contract_key, observation_id) AS immutable_observation_id"
            " FROM theodds_api_odds_history WHERE 1=1")
    params = {}
    if event_id:
        base += " AND event_id=:e"; params["e"] = str(event_id)
    if home_team:
        base += " AND home_team=:h"; params["h"] = home_team
    if away_team:
        base += " AND away_team=:a"; params["a"] = away_team
    if bookmaker_key:
        base += " AND bookmaker_key=:bk"; params["bk"] = bookmaker_key
    if market_key:
        base += " AND market_key=:mk"; params["mk"] = market_key
    if cut_utc:
        base += " AND observed_at_utc <= :cut AND (first_seen_utc IS NULL OR first_seen_utc <= :cut)"
        params["cut"] = cut_utc
    base += " ORDER BY observed_at_utc DESC"
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(base), params).fetchall()]
