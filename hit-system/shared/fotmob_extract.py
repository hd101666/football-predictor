# -*- coding: utf-8 -*-
"""
fotmob_extract.py — FotMob matchDetails / leagues 响应的纯解析层（无网络、无 DB）。

设计原则：
  * 只读取 provider 真实提供的字段；未提供 → 返回 None 并在 provenance 中标注（不推造）。
  * 动态字段（统计分组、事件、阵容球员）逐条展开保存，绝不由映射表决定「丢弃」。
  * 赛前 / 进行中 / 已完赛 三种状态统一解析，缺射门/xG 属正常缺失，不算故障。

被 43_fotmob_match_data_scraper.py 调用；单元测试直接喂 mock JSON。
"""
import json
import re
import hashlib

from source_evidence import parse_stat_token, normalize_kickoff_utc, make_observation_id


def _dig(obj, *path, default=None):
    cur = obj
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def _txt(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ── 赛事与身份 ─────────────────────────────────────────────────────────
_IDENTITY_FIELDS = [
    "match_id", "league_id", "league_code", "league_name", "season_id", "season_name",
    "home_team_id", "away_team_id", "home_team_name", "away_team_name", "home_role",
    "away_role", "kickoff_utc_raw", "kickoff_utc", "status", "status_reason", "match_state",
    "started", "finished", "round", "competition_stage", "venue", "schedule_change_history",
]


def extract_identity(detail, *, league_id=None, league_code=None, league_name=None,
                     season_name=None, season_id=None, source_endpoint="matchDetails",
                     observed_at_utc=None, observation_id=None, first_seen_utc=None,
                     prev=None):
    """把 matchDetails 的 general/header/content 解析成 fotmob_match_identity 一行。"""
    general = _dig(detail, "general", default={}) or {}
    header = _dig(detail, "header", default={}) or {}
    content = _dig(detail, "content", default={}) or {}
    info_box = _dig(content, "matchFacts", "infoBox", default={}) or {}

    home = general.get("homeTeam") or {}
    away = general.get("awayTeam") or {}
    header_teams = header.get("teams") or []
    h_team = header_teams[0] if len(header_teams) > 0 else {}
    a_team = header_teams[1] if len(header_teams) > 1 else {}

    match_id = general.get("matchId") or h_team.get("id")
    try:
        match_id = int(match_id) if match_id is not None else None
    except (TypeError, ValueError):
        match_id = None

    lid = general.get("leagueId") or general.get("parentLeagueId") or league_id
    try:
        lid = int(lid) if lid is not None else None
    except (TypeError, ValueError):
        lid = None

    kickoff_raw = (general.get("matchTimeUTCDate") or general.get("matchTimeUTC")
                   or _dig(header, "status", "utcTime"))
    status_obj = general.get("status") if isinstance(general.get("status"), dict) else {}
    started = general.get("started")
    if started is None:
        started = status_obj.get("started")
    finished = general.get("finished")
    if finished is None:
        finished = status_obj.get("finished")
    cancelled = status_obj.get("cancelled") or general.get("cancelled")
    status_reason = status_obj.get("reason") or _txt(info_box.get("Match Status"))

    if finished:
        match_state = "finished"
    elif started:
        match_state = "live"
    elif kickoff_raw or status_obj or general:
        match_state = "prematch"
    else:
        match_state = "unknown"
    if cancelled:
        match_state = "cancelled"

    venue = (_txt(general.get("venue")) or _dig(info_box, "Stadium", "name")
             or _txt(info_box.get("Stadium")) or _dig(header, "venue", "name"))

    # 赛程变更历史：provider 未直接提供结构化字段；若 infoBox/事件流暴露延期信息则记录为证据字符串，
    # 否则 NULL + 原因（见 null_reasons）。绝不推造。
    sched = None
    info_notes = []
    for k, v in (info_box or {}).items():
        if isinstance(v, str) and re.search(r"(postpon|abandon|suspend|delay|rearrang|cancel)",
                                            v, re.I):
            info_notes.append(f"{k}: {v}")
    if info_notes:
        sched = json.dumps(info_notes, ensure_ascii=False)

    row = {
        "match_id": match_id,
        "source_match_id": str(match_id) if match_id is not None else None,
        "league_id": lid,
        "league_code": league_code,
        "league_name": _txt(general.get("leagueName")) or league_name,
        "season_id": (str(season_id) if season_id is not None
                      else _txt(general.get("seasonId") or general.get("selectedSeasonId"))),
        "season_name": season_name or _txt(general.get("season")) or _txt(general.get("seasonName")),
        "home_team_id": home.get("id") if home.get("id") is not None else h_team.get("id"),
        "away_team_id": away.get("id") if away.get("id") is not None else a_team.get("id"),
        "home_team_name": _txt(home.get("name")) or _txt(h_team.get("name")),
        "away_team_name": _txt(away.get("name")) or _txt(a_team.get("name")),
        "home_role": "home" if (home or h_team) else None,
        "away_role": "away" if (away or a_team) else None,
        "kickoff_utc_raw": _txt(kickoff_raw),
        "kickoff_utc": normalize_kickoff_utc(kickoff_raw),
        "status": _txt(status_obj) if isinstance(status_obj, str) else (
            ("FT" if finished else ("live" if started else "NS")) if (general or status_obj) else None),
        "status_reason": status_reason,
        "match_state": match_state,
        "started": 1 if started else (0 if started is False else None),
        "finished": 1 if finished else (0 if finished is False else None),
        "round": _txt(general.get("matchRound") or general.get("leagueRoundName")),
        "competition_stage": _txt(general.get("leagueRoundName") or general.get("parentLeagueName")
                                  or general.get("tournamentStage")),
        "venue": _txt(venue),
        "schedule_change_history": sched,
        "source_endpoint": source_endpoint,
        "first_seen_utc": first_seen_utc or observed_at_utc,
        "last_seen_utc": observed_at_utc,
        "last_observation_id": observation_id,
    }

    # 字段级证据：provided | derived | absent
    prov, reasons = {}, {}
    for f in _IDENTITY_FIELDS:
        val = row.get(f)
        if val is not None:
            prov[f] = "provided"
        else:
            prov[f] = "absent"
            reasons[f] = _absence_reason(f)
    row["field_provenance"] = json.dumps(prov, ensure_ascii=False, sort_keys=True)
    row["null_reasons"] = json.dumps({k: v for k, v in reasons.items() if v},
                                     ensure_ascii=False, sort_keys=True)

    # 赛程变更历史继承（若本次响应没有，但历史有过）
    if row["schedule_change_history"] is None and prev:
        row["schedule_change_history"] = prev.get("schedule_change_history")
    # ★2026-10-09 修复：赛季身份继承 —— matchDetails **从不**提供 season_id，
    #   它是由 /leagues(TournamentId) 单独解析后回填的。若本次抓取不带 season，
    #   必须保留既有值，否则重复抓取（如 lineup 轮询）会把已解析的赛季覆盖回 NULL。
    if not row.get("season_id") and prev and prev.get("season_id"):
        row["season_id"] = prev["season_id"]
    if not row.get("season_name") and prev and prev.get("season_name"):
        row["season_name"] = prev["season_name"]
    # 赛季已解析时，清掉"来源未提供"的缺席理由（避免误导 V3 以为从未解决）
    if row.get("season_id"):
        try:
            _nr = json.loads(row.get("null_reasons") or "{}")
            _nr.pop("season_id", None)
            _nr.pop("season_name", None)
            row["null_reasons"] = json.dumps(_nr, ensure_ascii=False, sort_keys=True) or None
            _fp = json.loads(row.get("field_provenance") or "{}")
            _fp["season_id"] = "resolved_from_leagues_TournamentId"
            _fp["season_name"] = "resolved_from_leagues_TournamentId"
            row["field_provenance"] = json.dumps(_fp, ensure_ascii=False, sort_keys=True)
        except Exception:
            pass
    return row


def _absence_reason(field):
    return {
        "season_id": "provider_did_not_supply_in_matchDetails",
        "season_name": "not_resolved_for_target",
        "round": "provider_did_not_supply",
        "competition_stage": "provider_did_not_supply",
        "venue": "provider_did_not_supply_or_empty",
        "schedule_change_history": "provider_has_no_structured_field",
        "status_reason": "no_status_reason_in_response",
        "league_code": "not_resolved_for_target",
    }.get(field, "provider_did_not_supply")


# ── 比赛统计（动态分组，全量保留） ──────────────────────────────────────
def extract_stats_raw(stats_content, match_id, home_id, away_id,
                      observed_at_utc=None, observation_id=None):
    """展开 content.stats.Periods.*.stats 的所有分组/所有周期/所有字段为逐条行。

    与 43 号爬虫既有的 42 列映射互补：本表不丢任何字段（含未映射标题、未映射 key）。
    """
    periods = _dig(stats_content, "Periods", default={}) or {}
    rows = []
    for period_name, pdata in periods.items():
        groups = (pdata or {}).get("stats", []) or []
        for g in groups:
            gkey = _txt(g.get("key"))
            gtitle = _txt(g.get("title"))
            for s in g.get("stats", []) or []:
                vals = s.get("stats")
                if not isinstance(vals, list) or len(vals) < 2:
                    continue
                if vals[0] is None and vals[1] is None:
                    continue
                skey = _txt(s.get("key"))
                stitle = _txt(s.get("title"))
                fmt = _txt(s.get("format"))
                for side, tid, raw in (("home", home_id, vals[0]), ("away", away_id, vals[1])):
                    num, pct = parse_stat_token(raw)
                    rows.append({
                        "match_id": match_id,
                        "team_id": tid,
                        "side": side,
                        "period": period_name,
                        "group_key": gkey,
                        "group_title": gtitle,
                        "stat_key": skey,
                        "stat_title": stitle,
                        "stat_format": fmt,
                        "raw_value": None if raw is None else str(raw),
                        "value_num": num,
                        "value_pct": pct,
                        "unit": _infer_unit(fmt, stitle),
                        "highlight": _txt(s.get("highlighted")),
                        "observed_at_utc": observed_at_utc,
                        "observation_id": observation_id,
                    })
    return rows


def _infer_unit(fmt, title):
    t = (title or "").lower()
    if "possession" in t or (fmt or "").lower().endswith("withpercentage"):
        return "%"
    if t.endswith("(xg)") or "xg" in t or "distance" in t:
        return "m/ratio"
    return None


# ── 比赛事件（进球/牌/换人） ────────────────────────────────────────────
_EVENT_ID_FIELDS = ("eventId", "id")


def extract_events(content, match_id, observed_at_utc=None, observation_id=None):
    events = _dig(content, "matchFacts", "events", "events")
    if not isinstance(events, list):
        return []
    rows = []
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            continue
        etype = _txt(e.get("type")) or _txt(e.get("eventType"))
        minute = e.get("time")
        min_added = e.get("minAdded")
        player = e.get("player") if isinstance(e.get("player"), dict) else {}
        assist = e.get("assistInput") if isinstance(e.get("assistInput"), dict) else {}
        if not assist and isinstance(e.get("assist"), dict):
            assist = e.get("assist")
        eid = None
        for f in _EVENT_ID_FIELDS:
            if e.get(f) is not None:
                eid = str(e[f])
                break
        pname = _txt(e.get("playerName")) or _txt(player.get("name"))
        pid = e.get("playerId") if e.get("playerId") is not None else player.get("id")
        key = eid or make_observation_id("event", match_id, etype, minute, min_added, pid, pname, i)
        rows.append({
            "match_id": match_id,
            "event_key": key,
            "event_id": eid,
            "event_type": etype,
            "minute": minute,
            "min_added": min_added,
            "period": _txt(_dig(e, "shotmapEvent", "period")) or _txt(e.get("period")),
            "is_home": 1 if e.get("isHome") else (0 if e.get("isHome") is False else None),
            "team_id": e.get("teamId"),
            "player_id": pid,
            "player_name": pname,
            "assist_player_id": assist.get("id") if assist else e.get("assistPlayerId"),
            "assist_player_name": _txt(assist.get("name")) if assist else _txt(e.get("assistPlayerName")),
            "card_type": _txt(e.get("card")) or _txt(e.get("cardType")),
            "is_own_goal": 1 if e.get("ownGoal") else 0,
            "is_penalty": 1 if (e.get("isPenalty") or _dig(e, "shotmapEvent", "situation") == "Penalty") else 0,
            "score_home": _dig(e, "score", "home") if isinstance(e.get("score"), dict) else e.get("scoreHome"),
            "score_away": _dig(e, "score", "away") if isinstance(e.get("score"), dict) else e.get("scoreAway"),
            "raw_event_json": json.dumps(e, ensure_ascii=False),
            "observed_at_utc": observed_at_utc,
            "observation_id": observation_id,
        })
    return rows


# ── 阵容球员（预测 vs 官方确认分开） ────────────────────────────────────
def _lineup_type(lineup_team, match_started=True, lineup_root=None):
    """判定该阵容的**真实状态**。

    ★2026-10-09 修正：FotMob 的 `lineupType` / `source` 位于 **lineup 顶层**，
    不在 homeTeam/awayTeam 内。此前只看 team 内层 → 永远取不到 → 全部退化成
    "未开赛即 predicted"，把 `lastStarting11`（上一场首发）也误记为 predicted。

    取值域（实测，来自 418 份真实响应）：
      lineupType ∈ {predicted, standard, lastStarting11, unavailable}
      source     ∈ {enetpulse, optaSdapi, lastStartingLinesups|lastStartingLineups}

    映射：
      predicted                  → predicted            （数据商预测，非官方）
      lastStarting11             → last_starting_11     （★上一场首发，既非预测也非本场官方）
      standard + optaSdapi       → confirmed            （Opta 官方）
      standard + 无/其它来源      → standard             （官方性未确证）
      unavailable / 无首发        → unavailable
    仅在完全取不到来源标记时，才退回 match_started 推断。
    """
    root = lineup_root if isinstance(lineup_root, dict) else {}
    t = (_txt(root.get("lineupType")) or _txt(root.get("type"))
         or _txt(lineup_team.get("lineupType")) or _txt(lineup_team.get("type")))
    src = (_txt(root.get("source")) or _txt(lineup_team.get("source")) or "").lower()
    tl = (t or "").lower()

    if tl == "laststarting11" or "laststarting" in src:
        return "last_starting_11"
    if tl == "unavailable":
        return "unavailable"
    if tl == "predicted" or src == "enetpulse" and tl == "predicted":
        return "predicted"
    if tl == "standard":
        return "confirmed" if "opta" in src else "standard"
    if tl:
        if "pred" in tl:
            return "predicted"
        if "confirm" in tl or "official" in tl:
            return "confirmed"
    conf = lineup_team.get("confirmed")
    if conf is True:
        return "confirmed"
    if conf is False:
        return "predicted"
    if not lineup_team.get("starters"):
        return "unavailable"
    # 唯有无来源标记时才用时间推断（赛前→predicted，防未来信息泄漏）
    return "confirmed" if match_started else "predicted"


def extract_shotmap(content, match_id, observed_at_utc=None, observation_id=None,
                    raw_response_hash=None):
    """解析 content.shotmap.shots[]（逐射门，含 xG/xGOT）——2026-10-09 落库补全。"""
    rows = []
    sm = _dig(content, "shotmap", default={}) or {}
    shots = sm.get("shots") if isinstance(sm, dict) else None
    for s in (shots or []):
        if not isinstance(s, dict):
            continue
        rows.append({
            "shot_key": hashlib.sha256(f"{match_id}|{s.get('id')}".encode()).hexdigest(),
            "match_id": str(match_id),
            "team_id": _txt(s.get("teamId")),
            "player_id": _txt(s.get("playerId")),
            "player_name": _txt(s.get("playerName")),
            "event_type": _txt(s.get("eventType")),
            "minute": s.get("min"),
            "minute_added": s.get("minAdded"),
            "period": _txt(s.get("period")),
            "x": s.get("x"), "y": s.get("y"),
            "goal_crossed_y": s.get("goalCrossedY"), "goal_crossed_z": s.get("goalCrossedZ"),
            "is_blocked": int(bool(s.get("isBlocked"))),
            "is_on_target": int(bool(s.get("isOnTarget"))),
            "is_own_goal": int(bool(s.get("isOwnGoal"))),
            "is_saved_off_line": int(bool(s.get("isSavedOffLine"))),
            "is_from_inside_box": int(bool(s.get("isFromInsideBox"))),
            "shot_type": _txt(s.get("shotType")),
            "situation": _txt(s.get("situation")),
            "expected_goals": s.get("expectedGoals"),
            "expected_goals_on_target": s.get("expectedGoalsOnTarget"),
            "keeper_id": _txt(s.get("keeperId")),
            "observed_at_utc": observed_at_utc,
            "raw_response_hash": raw_response_hash,
            "receipt_id": observation_id,
            "source_json": json.dumps(s, ensure_ascii=False),
        })
    return rows


def extract_weather(content, match_id, observed_at_utc=None, observation_id=None,
                    raw_response_hash=None):
    """解析 content.weather（比赛天气）——2026-10-09 落库补全。"""
    w = _dig(content, "weather", default={}) or {}
    if not isinstance(w, dict) or not w:
        return []
    return [{
        "match_id": str(match_id),
        "temperature_c": w.get("temperature"),
        "wind_speed": w.get("windSpeed"),
        "wind_direction": _txt(w.get("windDirectionCardinal")),
        "relative_humidity": w.get("relativeHumidity"),
        "precip_chance": w.get("precipChance"),
        "precipitation": w.get("precipitation"),
        "snow": w.get("snow"),
        "cloud_cover": w.get("cloudCover"),
        "description": _txt(w.get("description")),
        "icon_code": w.get("iconCode"),
        "api_used": _txt(w.get("apiUsed")),
        "provider_updated_at": _txt(w.get("lastUpdated")),
        "observed_at_utc": observed_at_utc,
        "raw_response_hash": raw_response_hash,
        "receipt_id": observation_id,
    }]


def extract_team_form(content, match_id, home_id=None, away_id=None,
                      observed_at_utc=None, observation_id=None, raw_response_hash=None):
    """解析 content.matchFacts.teamForm（每队近期战绩序列）—— 落库补全。

    形态：teamForm = [ [home 队的近期场次...], [away 队的近期场次...] ]
    """
    rows = []
    mf = _dig(content, "matchFacts", default={}) or {}
    tf = mf.get("teamForm") if isinstance(mf, dict) else None
    if not isinstance(tf, list):
        return rows
    for side_idx, side in ((0, "home"), (1, "away")):
        team_id = home_id if side == "home" else away_id
        block = tf[side_idx] if side_idx < len(tf) else None
        if not isinstance(block, list):
            continue
        for seq, item in enumerate(block):
            if not isinstance(item, dict):
                continue
            # ★真实结构：home/away 子对象含 id/name/isOurTeam；isOurTeam=true 即本队
            h_obj = item.get("home") if isinstance(item.get("home"), dict) else {}
            a_obj = item.get("away") if isinstance(item.get("away"), dict) else {}
            our = h_obj if h_obj.get("isOurTeam") else (a_obj if a_obj.get("isOurTeam") else None)
            opp = a_obj if our is h_obj else h_obj
            tt = item.get("tooltipText") if isinstance(item.get("tooltipText"), dict) else {}
            utc = _dig(item, "date", "utcTime")
            ref = _txt(item.get("linkToMatch"))
            rows.append({
                "row_key": hashlib.sha256(
                    f"{match_id}|{team_id}|{side}|{opp.get('id')}|{utc}".encode()
                ).hexdigest(),
                "match_id": str(match_id),
                "team_id": _txt(our.get("id")) or (None if team_id is None else str(team_id)),
                "side": side,
                "seq_index": seq,
                "result": item.get("result"),
                "result_string": _txt(item.get("resultString")),
                "score": _txt(item.get("score")),
                "is_home": (1 if our is h_obj else 0) if our else None,
                "opponent_team_id": _txt(opp.get("id")),
                "opponent_name": _txt(opp.get("name")),
                "match_utc": _txt(utc),
                "source_match_ref": ref,
                "observed_at_utc": observed_at_utc,
                "raw_response_hash": raw_response_hash,
                "receipt_id": observation_id,
            })
    return rows


def extract_h2h(content, match_id, observed_at_utc=None, observation_id=None,
                raw_response_hash=None):
    """解析 content.h2h.matches（历史交锋）—— 落库补全。"""
    rows = []
    h = _dig(content, "h2h", default={}) or {}
    ms = h.get("matches") if isinstance(h, dict) else None
    for m in (ms or []):
        if not isinstance(m, dict):
            continue
        home = m.get("home") or {}
        away = m.get("away") or {}
        lg = m.get("league") or {}
        utc = _dig(m, "time", "utcTime")
        url = _txt(m.get("matchUrl"))
        rows.append({
            "row_key": hashlib.sha256(f"{match_id}|{url}|{utc}".encode()).hexdigest(),
            "match_id": str(match_id),
            "h2h_match_url": url,
            "league_id": _txt(lg.get("id")) if isinstance(lg, dict) else None,
            "league_name": _txt(lg.get("name")) if isinstance(lg, dict) else None,
            "home_team_id": _txt(home.get("id")) if isinstance(home, dict) else None,
            "home_team_name": _txt(home.get("name")) if isinstance(home, dict) else None,
            "away_team_id": _txt(away.get("id")) if isinstance(away, dict) else None,
            "away_team_name": _txt(away.get("name")) if isinstance(away, dict) else None,
            "match_utc": _txt(utc),
            "finished": int(bool(m.get("finished"))) if m.get("finished") is not None else None,
            "status_utc": _txt(_dig(m, "status", "utcTime")),
            # ★H2H 同时含已完赛与未来未赛；显式标记，便于 V3 区分"历史交锋"与"未来日程"
            "is_future": (1 if (isinstance(m.get("status"), dict)
                                and m["status"].get("started") is False) else 0),
            "observed_at_utc": observed_at_utc,
            "raw_response_hash": raw_response_hash,
            "receipt_id": observation_id,
        })
    return rows


def extract_lineup_players(lineup, match_id, home_id, away_id,
                           observed_at_utc=None, observation_id=None, match_started=True):
    rows = []
    for side, tid in (("home", home_id), ("away", away_id)):
        team = (lineup or {}).get(f"{side}Team", {}) or {}
        if not team:
            continue
        ltype = _lineup_type(team, match_started, lineup_root=lineup)
        formation = _txt(team.get("formation"))
        coach = team.get("coach")
        coach_name = coach.get("name") if isinstance(coach, dict) else _txt(coach)
        announced = (_txt(team.get("lineupAnnouncedAt")) or _txt(team.get("announcedAt"))
                     or _txt(_dig(team, "lineupAnnouncement", "time")))
        for is_starter, players in ((1, team.get("starters") or []), (0, team.get("subs") or [])):
            for p in players:
                if not isinstance(p, dict):
                    continue
                rows.append({
                    "match_id": match_id,
                    "team_id": tid,
                    "side": side,
                    "lineup_type": ltype,
                    "player_id": p.get("id"),
                    "player_name": _txt(p.get("name")),
                    "first_name": _txt(p.get("firstName")),
                    "last_name": _txt(p.get("lastName")),
                    "shirt_number": None if p.get("shirtNumber") is None else str(p.get("shirtNumber")),
                    "position_id": p.get("positionId"),
                    "usual_position_id": p.get("usualPlayingPositionId"),
                    "nationality": _txt(p.get("countryName")),
                    "country_code": _txt(p.get("countryCode")),
                    "age": p.get("age"),
                    "is_starter": is_starter,
                    "market_value": p.get("marketValue"),
                    "rating": _dig(p, "performance", "rating"),
                    "formation": formation,
                    "coach_name": coach_name,
                    "lineup_announced_at_utc": announced,
                    "source_player_json": json.dumps(p, ensure_ascii=False),
                    "observed_at_utc": observed_at_utc,
                    "observation_id": observation_id,
                })
    return rows


# ── 伤停 / 停赛 / 可用性 ────────────────────────────────────────────────
# ★2026-10-09 修正：此前在 matchFacts 下找 injuries/suspensions/availability/missingPlayers——**这些键不存在**，
#   于是错误地判定「FotMob 不提供伤停」。真实路径为：
#     content.lineup.{homeTeam,awayTeam}.unavailable[] → 每项含 id/name/age/positionId/... 与
#     unavailability{injuryId, type(injury|suspension|internationalDuty), expectedReturn,
#                    expectedReturnDate, lastUpdated}
_AILMENT_MAP = {"injury": "injury", "suspension": "suspension",
                "internationalDuty": "international_duty"}
_DOUBTFUL_HINTS = ("doubtful", "day to day", "day-to-day", "late fitness", "minor")


def _availability_status(unav):
    """由 expectedReturn 文本推断 availability_status（来源无独立状态字段）。"""
    er = (_txt(unav.get("expectedReturn")) or "").lower()
    if any(h in er for h in _DOUBTFUL_HINTS):
        return "doubtful"
    if "out for season" in er:
        return "out_for_season"
    return "unavailable"


def extract_availability(content, match_id, home_id, away_id,
                         observed_at_utc=None, observation_id=None):
    """解析 FotMob 伤停/停赛（真实路径 content.lineup.*.unavailable[]）。

    返回 rows（每行 provided=1）。来源未提供的子字段一律留 None 并在 null_reasons 记账，绝不推测。
    """
    rows = []
    lineup = _dig(content, "lineup", default={}) or {}
    for side, tid in (("homeTeam", home_id), ("awayTeam", away_id)):
        block = lineup.get(side) or {}
        for item in (block.get("unavailable") or []):
            if not isinstance(item, dict):
                continue
            unav = item.get("unavailability") or {}
            if not isinstance(unav, dict):
                unav = {}
            _type = _txt(unav.get("type"))
            rows.append({
                "match_id": match_id,
                "team_id": tid,
                "side": side,
                "player_id": item.get("id"),
                "player_name": _txt(item.get("name")),
                "first_name": _txt(item.get("firstName")),
                "last_name": _txt(item.get("lastName")),
                "age": item.get("age"),
                "position_id": item.get("positionId"),
                "country_name": _txt(item.get("countryName")),
                "country_code": _txt(item.get("countryCode")),
                "market_value": item.get("marketValue"),
                "availability_type": _AILMENT_MAP.get(_type, _type) or "unavailable",
                "status": _availability_status(unav),
                "reason": None,
                "injury_id": unav.get("injuryId"),
                "injury_description": None,   # 来源只给 injuryId 数字码，无文字说明
                "suspension_type": _type if _type == "suspension" else None,
                "expected_return_text": _txt(unav.get("expectedReturn")),
                "expected_return_date": _txt(unav.get("expectedReturnDate")),
                "source_updated_at": _txt(unav.get("lastUpdated")),
                "provided": 1,
                "source_json": json.dumps(item, ensure_ascii=False),
                "observed_at_utc": observed_at_utc,
                "observation_id": observation_id,
                "null_reasons": json.dumps({
                    "injury_description": "FotMob 仅提供 injuryId 数字码，无文字伤情说明",
                    "sidelined_start_at": "FotMob 不提供起始时间",
                    "actual_return_at": "FotMob 不提供实际复出时间",
                    "expected_return_date": None if unav.get("expectedReturnDate") else
                        "部分记录仅有自由文本 expectedReturn，无 ISO 日期",
                }, ensure_ascii=False),
            })
    return rows


def extract_inmatch_injuries(content, match_id, observed_at_utc=None, observation_id=None):
    """比赛进行中的受伤事件（content.matchFacts.events.events[].injuredPlayerOut）——与赛前伤停分开。"""
    rows = []
    evs = _dig(content, "matchFacts", "events", "events", default=[]) or []
    for e in evs:
        if not isinstance(e, dict):
            continue
        who = e.get("injuredPlayerOut")
        if not who:
            continue
        rows.append({
            "match_id": match_id, "event_type": "injury_in_match",
            "player_name": _txt(who), "minute": e.get("time") or e.get("minute"),
            "observed_at_utc": observed_at_utc, "observation_id": observation_id,
            "source_json": json.dumps(e, ensure_ascii=False),
        })
    return rows


def availability_placeholder(match_id, home_id, away_id, observed_at_utc=None, observation_id=None):
    """★仅在**解析后确无伤停记录**时使用（provided=0），用于区分「无数据」与「无人伤停」。

    注意：FotMob matchDetails **确实提供** unavailable[]；因此本占位行只在
    content.lineup.*.unavailable 缺失/为空时写入，不再是「来源不支持」的意思。
    """
    return {
        "match_id": match_id, "team_id": -1, "side": None, "player_id": -1,
        "player_name": None, "availability_type": "no_availability_block",
        "status": "NOT_PRESENT_IN_RESPONSE",
        "reason": "content.lineup.{homeTeam,awayTeam}.unavailable 在该响应中缺失或为空",
        "provided": 0, "source_json": None,
        "observed_at_utc": observed_at_utc, "observation_id": observation_id,
    }
