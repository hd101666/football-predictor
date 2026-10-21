# -*- coding: utf-8 -*-
"""
sportmonks_extract.py — Sportmonks Football API v3 纯解析层（证据层架构的解析端）

依据：https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-all-fixtures
（契约快照见 research/.../sportmonks_spec/）

★本模块**不发请求**（与 fotmob_extract / odds_extract 同构：证据层共享 + 纯解析）。
  抓取由 46_sportmonks_fixtures_scraper.py 负责；本模块只把 JSON 变成行。

契约要点（实测文档，非推测）：
  GET https://api.sportmonks.com/v3/football/fixtures?api_token=TOKEN
  Base entity 字段：id, sport_id, league_id, season_id, stage_id, group_id, aggregate_id,
                    round_id, state_id, venue_id, name, starting_at, starting_at_timestamp,
                    result_info, leg, details, length, placeholder, has_odds, has_premium_odds
  分页：per_page(max 50) / page / order；用 meta.has_more 翻页
  常用 include：participants / league / season / stage / round / state / venue / lineups /
                sidelined / statistics / events / scores / xGFixture
  ★跨商可用性：season_id / league_id 是**原生整数 ID**（与 FotMob 的 36781 不是同一命名空间，
     必须用自然键[队名+时间]或人工映射对齐，不能直接相等比较）

授权状态：**401 无 token 即拒绝** —— 本机当前无 SPORTMONKS 凭证，故真实采集未执行。
"""
import json
import hashlib
from typing import Any, Dict, List, Optional

PROVIDER = "Sportmonks"


def _txt(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def request_key(params: Dict[str, Any]) -> str:
    """规范化请求键（用于幂等/去重计数，不合并日志行）。"""
    items = sorted((k, "" if v is None else str(v)) for k, v in (params or {}).items()
                   if k != "api_token")
    return "&".join(f"{k}={v}" for k, v in items)


# ────────────────────────── Fixtures（核心：赛事+赛季身份） ──────────────────────────
def extract_fixtures(payload: Any, *, observed_at_utc=None, observation_id=None,
                     raw_response_hash=None) -> List[Dict[str, Any]]:
    """解析 /v3/football/fixtures 响应 → 规范化赛事身份行。

    返回的每行含：provider_fixture_id / league_id / season_id / stage_id / round_id /
    state_id / venue_id / name / kickoff_utc / kickoff_timestamp / + 观察与溯源字段。
    """
    rows: List[Dict[str, Any]] = []
    data = payload.get("data") if isinstance(payload, dict) else payload
    if data is None:
        return rows
    if isinstance(data, dict):
        data = [data]
    for fx in data:
        if not isinstance(fx, dict):
            continue
        name = _txt(fx.get("name"))
        home, away = None, None
        if name and " vs " in name:
            home, away = [p.strip() for p in name.split(" vs ", 1)]
        rows.append({
            "provider": PROVIDER,
            "provider_fixture_id": _int(fx.get("id")),
            "sport_id": _int(fx.get("sport_id")),
            "league_id": _int(fx.get("league_id")),
            "season_id": _int(fx.get("season_id")),
            "stage_id": _int(fx.get("stage_id")),
            "group_id": _int(fx.get("group_id")),
            "round_id": _int(fx.get("round_id")),
            "state_id": _int(fx.get("state_id")),
            "venue_id": _int(fx.get("venue_id")),
            "name": name,
            "home_team_name": home,
            "away_team_name": away,
            "kickoff_utc": _txt(fx.get("starting_at")),
            "kickoff_timestamp": _int(fx.get("starting_at_timestamp")),
            "result_info": _txt(fx.get("result_info")),
            "leg": _txt(fx.get("leg")),
            "has_odds": fx.get("has_odds"),
            "has_premium_odds": fx.get("has_premium_odds"),
            "observed_at_utc": observed_at_utc,
            "observation_id": observation_id,
            "raw_response_hash": raw_response_hash,
            "source_endpoint": "/v3/football/fixtures",
        })
    return rows


def extract_fixture_participants(fixture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从含 include=participants 的 fixture 中提取参赛方（home/away + team_id）。"""
    rows = []
    for p in (fixture.get("participants") or []):
        if not isinstance(p, dict):
            continue
        meta = p.get("meta") or {}
        rows.append({
            "provider": PROVIDER,
            "provider_fixture_id": _int(fixture.get("id")),
            "provider_team_id": _int(p.get("id")),
            "team_name": _txt(p.get("name")),
            "location": _txt(meta.get("location")) if isinstance(meta, dict) else None,
            "winner": meta.get("winner") if isinstance(meta, dict) else None,
        })
    return rows


# ────────────────────────── Seasons（赛季身份主表） ──────────────────────────
def extract_seasons(payload: Any, *, observed_at_utc=None, observation_id=None,
                    raw_response_hash=None) -> List[Dict[str, Any]]:
    """解析 /v3/football/seasons|seasons/teams/{id} → 赛季身份行。

    字段（文档实测）：id, sport_id, league_id, name, finished, pending, is_current,
                     starting_at, ending_at, tie_breaker_rule_id
    """
    rows = []
    data = payload.get("data") if isinstance(payload, dict) else payload
    if data is None:
        return rows
    if isinstance(data, dict):
        data = [data]
    for s in data:
        if not isinstance(s, dict):
            continue
        rows.append({
            "provider": PROVIDER,
            "season_id": _int(s.get("id")),           # ★赛季唯一 ID
            "league_id": _int(s.get("league_id")),
            "sport_id": _int(s.get("sport_id")),
            "season_name": _txt(s.get("name")),       # 如 "2026/2027"
            "finished": s.get("finished"),
            "pending": s.get("pending"),
            "is_current": s.get("is_current"),        # ★可据此外键定位当前赛季
            "starting_at": _txt(s.get("starting_at")),
            "ending_at": _txt(s.get("ending_at")),
            "observed_at_utc": observed_at_utc,
            "observation_id": observation_id,
            "raw_response_hash": raw_response_hash,
            "source_endpoint": "/v3/football/seasons",
        })
    return rows


# ────────────────────────── Leagues（联赛身份） ──────────────────────────
def extract_leagues(payload: Any, *, observed_at_utc=None, observation_id=None,
                    raw_response_hash=None) -> List[Dict[str, Any]]:
    """解析 /v3/football/leagues[/{id}] → 联赛身份行。

    字段：id, sport_id, country_id, name, active, short_code, image_path, type, sub_type, category
    """
    rows = []
    data = payload.get("data") if isinstance(payload, dict) else payload
    if data is None:
        return rows
    if isinstance(data, dict):
        data = [data]
    for l in data:
        if not isinstance(l, dict):
            continue
        rows.append({
            "provider": PROVIDER,
            "league_id": _int(l.get("id")),
            "sport_id": _int(l.get("sport_id")),
            "country_id": _int(l.get("country_id")),
            "league_name": _txt(l.get("name")),
            "active": l.get("active"),
            "short_code": _txt(l.get("short_code")),
            "league_type": _txt(l.get("type")),
            "sub_type": _txt(l.get("sub_type")),
            "category": _int(l.get("category")),
            "observed_at_utc": observed_at_utc,
            "observation_id": observation_id,
            "raw_response_hash": raw_response_hash,
            "source_endpoint": "/v3/football/leagues",
        })
    return rows


# ────────────────────────── 分页 ──────────────────────────
def pagination(payload: Dict[str, Any]) -> Dict[str, Any]:
    """读取分页元数据（has_more / current_page / next_page / total）。"""
    meta = (payload or {}).get("meta") or {}
    pag = meta.get("pagination") or {}
    return {
        "has_more": bool(pag.get("has_more")),
        "current_page": pag.get("current_page"),
        "next_page": pag.get("next_page"),
        "per_page": pag.get("per_page"),
        "total": pag.get("total"),
    }


# ────────────────────────── Seasons 端点族（5 个） ──────────────────────────
# 依据：docs.sportmonks.com/v3/.../seasons/*（快照见 sportmonks_spec/seasons_*.txt）
#   GET /v3/football/seasons                          → 全部赛季（可用 filters 过滤）
#   GET /v3/football/seasons/{ID}                     → 单个赛季
#   GET /v3/football/seasons/teams/{teamID}           → 某球队的赛季
#   GET /v3/football/seasons/search/{searchQuery}     → 按名称搜（如 "2024/2025"）
#   GET /v3/football/seasons/brackets/{seasonID}      → 赛季括号/对阵树
# 注意：不存在 /seasons/leagues/{id}（实测 404）；按联赛过滤要用 filters=seasonLeagues:{leagueIDs}
SEASON_ENDPOINTS = {
    "all": "/v3/football/seasons",
    "by_id": "/v3/football/seasons/{ID}",
    "by_team": "/v3/football/seasons/teams/{teamID}",
    "search": "/v3/football/seasons/search/{searchQuery}",
    "brackets": "/v3/football/seasons/brackets/{seasonID}",
}
# 全部 5 个 Seasons 端点实测均 401（无 token 不可访问）


def seasons_filter_by_league(league_ids) -> Dict[str, str]:
    """构造按联赛过滤赛季的 query（filters=seasonLeagues:{ids}）——替代不存在的 /seasons/leagues。"""
    if isinstance(league_ids, (int, str)):
        league_ids = [league_ids]
    return {"filters": "seasonLeagues:" + ",".join(str(i) for i in league_ids)}


def current_season(season_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """从赛季列表中取 is_current=True 的那条（来源原生标志，避免按名字猜测）。"""
    cur = [s for s in season_rows if s.get("is_current")]
    return cur[0] if cur else None


def resolve_season_id(season_rows: List[Dict[str, Any]], season_name: str) -> Optional[int]:
    """按名称（如 "2026/2027"）精确解析 season_id；找不到返回 None（不猜）。"""
    for s in season_rows:
        if (s.get("season_name") or "").strip() == season_name.strip():
            return s.get("season_id")
    return None


def season_payload_to_rows(payload: Any, *, league_id=None, observed_at_utc=None,
                           observation_id=None, raw_response_hash=None) -> List[Dict[str, Any]]:
    """extract_seasons 的别名 + 可附加 league_id 上下文（Seasons 端点族统一入口）。"""
    rows = extract_seasons(payload, observed_at_utc=observed_at_utc,
                           observation_id=observation_id, raw_response_hash=raw_response_hash)
    if league_id is not None:
        for r in rows:
            r.setdefault("league_id", _int(league_id))
    return rows


# ────────────────────────── Lineups / Formations（Task E） ──────────────────────────
# 依据：docs.sportmonks.com/v3/tutorials-and-guides/tutorials/lineups-and-formations
#   ★关键：官方阵容在**所有基础套餐免费**；**约开赛前 1 小时公布**。
#     预测阵容（Expected Lineups）需额外 add-on —— 即官方 vs 预测在本源天然可分。
#   ★`lineup_confirmed` 位于 **metadata include**：
#       false = 俱乐部尚未公布（此时是**预测**阵容，基于往绩/伤停）
#       true  = 俱乐部已正式公布（应反映赛时最终阵容）
#   ★来源**只给状态，不给公布时刻** → 按用户要求：保存"状态首次被采集观察的时间"，
#     并明确标注为观察时间，**不得当作官方发布时间**。
#   阵容对象字段：id, sport_id, fixture_id, player_id, team_id, position_id,
#                formation_field("2:2"), type_id(11=首发,12=替补), formation_position,
#                player_name, jersey_number
#   include：formations / lineups / lineups.detailedposition / lineups.xGLineup /
#            sidelined.sideline / metadata（取 lineup_confirmed）
LINEUP_TYPE_IDS = {11: "starter", 12: "substitute"}
LINEUP_FILTER = {"starter": "lineupTypes:11", "substitute": "lineupTypes:12"}
# 官方阵容公布时间的**行业参照**（仅供参考，非逐场事实）：约开赛前 1 小时
OFFICIAL_LINEUP_PUBLISH_LEAD_MINUTES = 60


def _metadata_lineup_confirmed(fixture_or_root: Dict[str, Any]):
    """从 metadata include 中提取 lineup_confirmed（bool/None）。

    API 3.0 的 metadata 形如 [{type:{code/name:'lineup_confirmed'}, values:{...}}]
    或 {'lineup_confirmed': true}；两种形态都兼容。
    """
    md = (fixture_or_root or {}).get("metadata")
    if isinstance(md, dict):
        v = md.get("lineup_confirmed")
        return v if isinstance(v, bool) else None
    if isinstance(md, list):
        for item in md:
            if not isinstance(item, dict):
                continue
            t = item.get("type") or {}
            code = (t.get("code") or t.get("name") or "") if isinstance(t, dict) else str(t)
            if "lineup_confirmed" in str(code).lower():
                vals = item.get("values")
                if isinstance(vals, dict):
                    for k in ("value", "boolean", "confirmed"):
                        if k in vals:
                            return bool(vals[k])
                if isinstance(vals, bool):
                    return vals
                if "value" in item:
                    return bool(item["value"])
    if isinstance(fixture_or_root.get("lineup_confirmed"), bool):
        return fixture_or_root["lineup_confirmed"]
    return None


def extract_lineups(fixture: Dict[str, Any], *, provider="Sportmonks",
                    observed_at_utc=None, observation_id=None,
                    raw_response_hash=None) -> List[Dict[str, Any]]:
    """解析 fixture 的 lineups[] → Task E 规范行。

    ★严格区分预测/官方：
      lineup_confirmed is True   → lineup_type='confirmed'（官方已公布）
      lineup_confirmed is False  → lineup_type='predicted'（来源给的预测）
      lineup_confirmed is None   → lineup_type='unknown'（**不猜**）
    ★来源不给公布时刻 → lineup_announcement_at 恒 None；
      只写 lineup_first_seen_utc=observed_at_utc，并注明"这是观察时间，非公布时间"。
    """
    rows = []
    confirmed = _metadata_lineup_confirmed(fixture)
    if confirmed is True:
        ltype = "confirmed"
    elif confirmed is False:
        ltype = "predicted"
    else:
        ltype = "unknown"

    # 队形：formations include（按 team 分）
    formation_by_team = {}
    for f in (fixture.get("formations") or []):
        if isinstance(f, dict) and f.get("participant_id") is not None:
            formation_by_team[str(f.get("participant_id"))] = _txt(f.get("formation"))

    for lu in (fixture.get("lineups") or []):
        if not isinstance(lu, dict):
            continue
        tid = lu.get("team_id")
        type_id = _int(lu.get("type_id"))
        rows.append({
            "provider": provider,
            "source_fixture_id": _txt(lu.get("fixture_id")),
            "source_team_id": _txt(tid),
            "source_player_id": _txt(lu.get("player_id")),
            "player_name": _txt(lu.get("player_name")),
            "lineup_type": ltype,                       # confirmed / predicted / unknown
            "lineup_confirmed": 1 if confirmed is True else (0 if confirmed is False else None),
            "lineup_source_type": "sportmonks_metadata_lineup_confirmed",
            "lineup_publishable": 1 if confirmed is True else 0,
            "squad_status": LINEUP_TYPE_IDS.get(type_id, f"type_{type_id}"),
            "position": _txt(lu.get("formation_field")),   # 如 "2:2"
            "position_id": _int(lu.get("position_id")),
            "formation_position": _int(lu.get("formation_position")),
            "formation": formation_by_team.get(str(tid)),
            "jersey_number": _int(lu.get("jersey_number")),
            # ★来源只给状态不给公布时刻
            "lineup_announcement_at": None,
            "lineup_first_seen_utc": observed_at_utc,
            "announcement_evidence": (
                "Sportmonks metadata.lineup_confirmed=true（官方已公布）；"
                "但**来源不提供公布时刻** → lineup_first_seen_utc 是**我们首次观察到该状态的时刻**，"
                "不是官方发布时间。行业参照：官方阵容约开赛前 1 小时公布。"
                if confirmed is True else
                "lineup_confirmed=false → 来源明确标注为**预测**阵容（非官方）。"
                if confirmed is False else
                "未取到 lineup_confirmed（缺 metadata include）→ 状态未知，**不推断**。"),
            "provider_updated_at": None,
            "observed_at_utc": observed_at_utc,
            "first_seen_status": "PROVEN" if observed_at_utc else "UNKNOWN",
            "raw_response_hash": raw_response_hash,
            "receipt_id": observation_id,
            "notes": json.dumps({
                "lineup_confirmed_missing": confirmed is None,
                "publish_time_not_provided_by_source": True,
                "official_publish_lead_ref_minutes": OFFICIAL_LINEUP_PUBLISH_LEAD_MINUTES,
            }, ensure_ascii=False),
        })
    return rows


# ────────────────────────── Sidelined（Task D 伤停/停赛） ──────────────────────────
# 依据：docs.sportmonks.com/v3/tutorials-and-guides/tutorials/includes/sidelined
#   ★sidelined include **所有套餐免费**（"Included in All Plans"），不是付费专属。
#   不是独立端点（/v3/football/sidelined → 404）；只能作为 include 挂在 fixtures / teams 上。
#   从 fixture：include=sidelined.sideline;sidelined.player;sidelined.type
#   从 team   ：include=sidelined.player;sidelined.type（可加 sidelined.team;sidelined.season）
#   历史记录  ：sidelinedHistory（**仅 teams 端点**）→ 每个球员的全部不可用期（含已结束）
#   ★字段：start date / end date / games missed / injury-or-suspension type
#          → 正好补齐 FotMob 缺的 sidelined_start_at 与 actual_return_at
SIDELINED_INCLUDES = {
    "from_fixture": "sidelined.sideline;sidelined.player;sidelined.type",
    "from_team": "sidelined.player;sidelined.type",
    "from_team_full_history": "sidelinedHistory.player;sidelinedHistory.type",
}
SIDELINED_AVAILABILITY = "all_plans_free"   # 实测文档：Included in All Plans


def extract_sidelined(fixture_or_team: Dict[str, Any], *, provider="Sportmonks",
                      source_entity_type="fixture", observed_at_utc=None,
                      observation_id=None, raw_response_hash=None) -> List[Dict[str, Any]]:
    """解析 fixture/team 响应中的 sidelined[] → Task D 规范行。

    每项（含 include 展开后）形如：
      {id, player_id, team_id, fixture_id?, type_id, start_date, end_date,
       games_missed, player:{...}, type:{name, ...}}
    """
    rows = []
    for s in (fixture_or_team.get("sidelined") or []):
        if not isinstance(s, dict):
            continue
        player = s.get("player") or {}
        styp = s.get("type") or {}
        start = _txt(s.get("start_date"))
        end = _txt(s.get("end_date"))
        type_name = _txt(styp.get("name") if isinstance(styp, dict) else styp)
        rows.append({
            "provider": provider,
            "source_player_id": _txt(s.get("player_id")) or _txt(player.get("id")),
            "player_name": _txt(player.get("display_name")) or _txt(player.get("name")),
            "source_team_id": _txt(s.get("team_id")),
            "source_event_id": _txt(s.get("fixture_id")) or _txt(fixture_or_team.get("id")),
            "injury_type": type_name,
            "injury_description": type_name,
            "suspension_type": type_name if (type_name and "suspens" in type_name.lower()) else None,
            "availability_status": "unavailable" if end is None else "resolved",
            "sidelined_start_at": start,          # ★FotMob 不给，这里给
            "expected_return_at": end,            # ★这里的 end_date 即预计/实际结束
            "actual_return_at": end if (end and start) else None,
            "source_updated_at": _txt(s.get("updated_at")),
            "games_missed": s.get("games_missed"),
            "observed_at_utc": observed_at_utc,
            "observation_id": observation_id,
            "raw_response_hash": raw_response_hash,
            "provided": 1,
            "source_json": json.dumps(s, ensure_ascii=False),
            "null_reasons": json.dumps({
                "actual_return_at": "仅当 start 与 end 均存在时判定为已结束；否则视为仍在伤停",
                "note": "Sportmonks sidelined（所有套餐免费）；需 token 才能真实采集",
            }, ensure_ascii=False),
        })
    return rows


# ────────────────────────── 跨商对齐（自然键，非 ID 相等） ──────────────────────────
def natural_key(team_home: Optional[str], team_away: Optional[str],
                kickoff_utc: Optional[str]) -> Optional[str]:
    """构造跨商对齐用的自然键：队名（归一化）+ 开球日期时刻。

    ★Sportmonks 的 season_id/league_id 与 FotMob/The Odds API 属不同命名空间，
      绝不可直接比较相等；跨商对应必须走本函数这类自然键，或人工映射表。
    """
    if not (team_home and team_away and kickoff_utc):
        return None
    norm = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
    k = str(kickoff_utc).replace("T", " ").replace("Z", "").strip()[:16]
    return f"{norm(team_home)}|{norm(team_away)}|{k}"
