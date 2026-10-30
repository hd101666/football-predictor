# -*- coding: utf-8 -*-
"""
odds_extract.py — The Odds API v4 响应的纯解析层（无网络、无 DB）。

要点：
  * 市场时段（period）由真实 market key + provider 定义推定，绝不「所有 h2h 都当同一时段」。
  * 保留 market.last_update（★关键）、bookmaker.title/region、outcome.description、
    SID/link/bet limit/rotation number 等来源可选字段。
  * 报价按「内容签名」幂等：同一报价不重复，价格/市场更新时间变化即追加新版本 → 支持 point-in-time。
  * American / Decimal 只做单向：请求 oddsFormat=decimal，标准化字段直接取原值，绝不二次换算。

被 35_theoddsapi_multi_scraper.py 调用；单元测试直接喂 mock JSON。
"""
import re
import json

from source_evidence import make_observation_id, sha256_text

# provider 文档列出的足球市场目录（仅文档证据；verified 由真实响应决定）
DOCUMENTED_SOCCER_MARKETS = [
    "h2h", "h2h_lay", "spreads", "totals", "btts",
    "draw_no_bet", "h2h_h1", "h2h_h2", "spreads_h1", "spreads_h2",
    "totals_h1", "totals_h2", "btts_h1", "btts_h2",
    "alternate_spreads", "alternate_totals",
    "alternate_team_totals", "team_totals", "team_totals_h1", "team_totals_h2",
    "team_totals_over", "team_totals_under",
    "totals_corners", "alternate_totals_corners", "team_totals_corners",
    "totals_cards", "alternate_totals_cards", "team_totals_cards",
    "double_chance", "correct_score", "correct_score_h1",
    "half_time_full_time", "htft_double",
    "odd_even", "odd_even_h1", "odd_even_h2",
    "draw_no_bet_h1", "draw_no_bet_h2",
    "first_half_winner", "second_half_winner",
    "alternate_h2h_h1", "alternate_h2h_h2",
    "spreads_corners", "spreads_cards",
    "player_goal_scorer_anytime", "player_goal_scorer_first", "player_goal_scorer_last",
    "player_shots", "player_shots_on_target", "player_assists",
    "player_cards", "player_to_score_or_assist",
    "player_goalkeeper_saves", "player_anytime_assist",
    "player_to_receive_card", "player_passes",
]

_DOC_MARKET_SET = set(DOCUMENTED_SOCCER_MARKETS)


def market_period(market_key):
    """由真实 market key 推定比赛时段（full / first_half / second_half / quarter_N / extra）。"""
    k = (market_key or "").lower()
    if re.search(r"(_|^)h1(_|$)|_1h(_|$)|first_half|_1st_half", k):
        return "first_half"
    if re.search(r"(_|^)h2(_|$)|_2h(_|$)|second_half|_2nd_half", k):
        return "second_half"
    m = re.search(r"(_|^)q([1-4])(_|$)", k)
    if m:
        return f"quarter_{m.group(2)}"
    if "extra" in k:
        return "extra_time"
    if "penalt" in k:
        return "penalty"
    return "full"


def market_category(market_key):
    k = (market_key or "").lower()
    for cat, pat in (
        ("h2h", r"^h2h"), ("spreads", r"spreads"), ("totals", r"totals"),
        ("btts", r"btts|both_teams"), ("draw_no_bet", r"draw_no_bet"),
        ("team_totals", r"team_totals"), ("corners", r"corner"),
        ("cards", r"card"), ("player_props", r"^player_|_player"),
        ("correct_score", r"correct_score"), ("double_chance", r"double_chance"),
        ("half_time_full_time", r"half_time_full_time|htft"),
        ("odd_even", r"odd_even"),
    ):
        if re.search(pat, k):
            return cat
    return "other"


def market_weekends_ok(market_key):
    return market_key in _DOC_MARKET_SET


def _normalize_outcome(oc_name, home_team, away_team, market_key):
    """把结果名归一化到 home/away/draw/over/under/<raw>。"""
    lo = (oc_name or "").lower()
    if market_key == "totals" or lo in ("over", "under") or "total" in (market_key or "").lower():
        if lo in ("over", "under"):
            return lo
    if lo in ("draw", "tie"):
        return "draw"
    if home_team and oc_name == home_team:
        return "home"
    if away_team and oc_name == away_team:
        return "away"
    if home_team and home_team[:8].lower() in lo:
        return "home"
    if away_team and away_team[:8].lower() in lo:
        return "away"
    return lo


def contract_key(event_id, bookmaker_key, market_key, outcome_name, point, price, market_last_update):
    """报价内容签名：内容同 → 同一条（幂等）；任一变化 → 新版本（追加）。"""
    return make_observation_id(
        "odds", event_id, bookmaker_key, market_key, outcome_name,
        "" if point is None else repr(float(point)),
        "" if price is None else repr(float(price)),
        market_last_update or "")


def extract_event_rows(payload, sport_key, observed_at_utc, raw_hash, source_endpoint=None):
    rows = []
    for ev in payload or []:
        if not isinstance(ev, dict) or not ev.get("id"):
            continue
        title = ev.get("sport_title") or sport_key
        rows.append({
            "event_id": str(ev.get("id")),
            "sport_key": sport_key,
            "sport_title": title,
            "league_name": title,
            "commence_time": ev.get("commence_time"),
            "home_team": ev.get("home_team"),
            "away_team": ev.get("away_team"),
            "source_event_identity": "provider_event_id",
            "first_seen_utc": observed_at_utc,
            "last_seen_utc": observed_at_utc,
            "last_observation_id": None,
            "raw_response_hash": raw_hash,
        })
    return rows


def extract_quote_rows(payload, sport_key, observed_at_utc, raw_response_hash,
                       fetch_date, source_endpoint=None, include_extended=True):
    """解析 /sports/{key}/odds 响应。

    返回 dict：
      legacy   — 兼容 theodds_api_odds 的 13 列行（仅 h2h/spreads/totals）
      history  — theodds_api_odds_history 追加行（全部市场）
      bookmakers / markets / events — 目录与事件行
    """
    legacy, history = [], []
    bkmap, mkmap = {}, {}
    sp = "football" if "soccer" in (sport_key or "") else (
        "basketball" if "basketball" in (sport_key or "") else "other")

    for ev in payload or []:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "")
        if not eid:
            continue
        home = ev.get("home_team", "") or ""
        away = ev.get("away_team", "") or ""
        ct = ev.get("commence_time", "")
        lgn = ev.get("sport_title") or sport_key
        for bk in ev.get("bookmakers", []) or []:
            if not isinstance(bk, dict):
                continue
            bkkey = bk.get("key", "") or ""
            bktitle = bk.get("title")
            bk_lu = bk.get("last_update")
            bkm = bkmap.setdefault(bkkey, {"key": bkkey, "title": bktitle, "regions": set(),
                                           "markets": set(), "count": 0,
                                           "first": observed_at_utc, "last": observed_at_utc})
            if bktitle:
                bkm["title"] = bktitle
            if bk.get("region") or bk.get("regions"):
                r = bk.get("region") or bk.get("regions")
                for rr in ([r] if isinstance(r, str) else r):
                    bkm["regions"].add(rr)
            for mkt in bk.get("markets", []) or []:
                if not isinstance(mkt, dict):
                    continue
                mk = mkt.get("key", "") or ""
                mlu = mkt.get("last_update")
                period = market_period(mk)
                bkm["markets"].add(mk)
                mm = mkmap.setdefault(mk, {"market_key": mk, "category": market_category(mk),
                                           "period_scope": period, "verified": 1,
                                           "first": observed_at_utc, "last": observed_at_utc,
                                           "description": mkt.get("description")})
                mm["verified"] = 1
                for oc in mkt.get("outcomes", []) or []:
                    if not isinstance(oc, dict):
                        continue
                    price = oc.get("price")
                    if price is None:
                        continue
                    try:
                        price_f = float(price)
                    except (TypeError, ValueError):
                        continue
                    point = oc.get("point")
                    try:
                        point_f = float(point) if point is not None else None
                    except (TypeError, ValueError):
                        point_f = None
                    if point_f is None and isinstance(point, str) and point.strip():
                        point_f = None
                    sid = mkt.get("sid") or oc.get("sid")
                    link = mkt.get("link") or oc.get("link")
                    bet_limit = mkt.get("bet_limit", oc.get("bet_limit"))
                    rot = mkt.get("rotation_number", oc.get("rotation_number"))
                    ck = contract_key(eid, bkkey, mk, oc.get("name", ""), point_f, price_f, mlu)
                    if include_extended:
                        history.append({
                            "observation_id": ck,
                            "contract_key": ck,
                            "event_id": eid, "sport_key": sport_key, "sport_title": lgn,
                            "league_name": lgn, "home_team": home, "away_team": away,
                            "commence_time": ct,
                            "bookmaker_key": bkkey, "bookmaker_title": bktitle,
                            "bookmaker_region": bk.get("region"),
                            "market_key": mk, "market_period": period,
                            "market_last_update": mlu, "bookmaker_last_update": bk_lu,
                            "outcome_name": oc.get("name"), "outcome_description": oc.get("description"),
                            "point": point_f, "price": price_f,
                            "raw_odds_format": "decimal", "normalized_decimal_odds": price_f,
                            "source_sid": None if sid is None else str(sid),
                            "source_link": link,
                            "source_bet_limit": (float(bet_limit) if isinstance(bet_limit, (int, float))
                                                 else None),
                            "rotation_number": None if rot is None else str(rot),
                            "observed_at_utc": observed_at_utc, "fetch_date": fetch_date,
                            "first_seen_utc": observed_at_utc,
                            "raw_response_hash": raw_response_hash, "source_endpoint": source_endpoint,
                        })
                    if mk in ("h2h", "spreads", "totals") and price_f > 1.0:
                        legacy.append({
                            "event_id": eid, "sport": sp, "sport_key": sport_key,
                            "league_name": lgn, "home_team": home, "away_team": away,
                            "commence_time": ct, "bookmaker": bkkey,
                            "market": {"h2h": "moneyline", "spreads": "spread", "totals": "total"}[mk],
                            "outcome": _normalize_outcome(oc.get("name", ""), home, away, mk),
                            "odds": price_f, "point": point_f, "fetch_date": fetch_date,
                        })
                    bkm["count"] += 1
    bookmakers = [{
        "bookmaker_key": v["key"], "bookmaker_title": v["title"],
        "regions_seen": ",".join(sorted(v["regions"])) or None,
        "markets_seen": ",".join(sorted(v["markets"])) or None,
        "market_count": v["count"], "first_seen_utc": v["first"], "last_seen_utc": v["last"],
    } for v in bkmap.values() if v["key"]]
    markets = [{
        "market_key": v["market_key"], "description": v.get("description"),
        "category": v["category"], "period_scope": v["period_scope"],
        "source": "observed_response", "verified": 1, "notes": None,
        "first_seen_utc": v["first"], "last_seen_utc": v["last"],
    } for v in mkmap.values() if v["market_key"]]
    return {"legacy": legacy, "history": history, "bookmakers": bookmakers, "markets": markets}


def documented_market_rows(observed_at_utc=None):
    """文档列出但本次未在真实响应中验证的市场（verified=0，明确标注并非当前可用承诺）。"""
    return [{
        "market_key": k, "description": None, "category": market_category(k),
        "period_scope": market_period(k), "source": "official_docs", "verified": 0,
        "notes": "documented in The Odds API v4 soccer market list; availability per event/bookmaker unverified",
        "first_seen_utc": observed_at_utc, "last_seen_utc": observed_at_utc,
    } for k in DOCUMENTED_SOCCER_MARKETS]


def sanitize_payload_for_hash(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(payload) -> str:
    return sha256_text(sanitize_payload_for_hash(payload))


# ══════════════════════ 历史快照支持（Task C） ══════════════════════
# 依据 docs.the-odds-api.com：
#   GET /v4/historical/sports/{sport}/odds?regions=&markets=&date={ISO8601}
#   响应为**信封**：{"timestamp":..., "previous_timestamp":..., "next_timestamp":..., "data":[...]}
#   timestamp = 该快照真实时间；previous/next = 可前后翻页的真实快照时间点
#   成本 = 10 × markets × regions（仅付费档）
# ★关键：快照时刻(timestamp)与抓取时刻(observed_at_utc)是**两个不同时间**，必须分别存。

SNAPSHOT_ENVELOPE_KEYS = ("timestamp", "previous_timestamp", "next_timestamp")


def is_snapshot_envelope(payload) -> bool:
    """判断是否为 historical 端点的信封响应（含 timestamp + data）。"""
    return (isinstance(payload, dict)
            and "timestamp" in payload
            and "data" in payload)


def unwrap_snapshot(payload):
    """拆信封 → (data, meta)。非信封时 meta 为 None（兼容普通 /odds 响应）。

    meta = {snapshot_timestamp, previous_timestamp, next_timestamp}
    """
    if is_snapshot_envelope(payload):
        return payload.get("data"), {
            "snapshot_timestamp": payload.get("timestamp"),
            "previous_timestamp": payload.get("previous_timestamp"),
            "next_timestamp": payload.get("next_timestamp"),
        }
    return payload, None


def extract_quote_rows_v4(payload, sport_key, observed_at_utc, raw_response_hash,
                          fetch_date, source_endpoint=None, include_extended=True):
    """兼容信封与非信封的统一入口。返回同 extract_quote_rows，另附 snapshot_meta。"""
    data, meta = unwrap_snapshot(payload)
    out = extract_quote_rows(data, sport_key, observed_at_utc, raw_response_hash,
                             fetch_date, source_endpoint=source_endpoint,
                             include_extended=include_extended)
    out["snapshot_meta"] = meta
    # ★把快照时刻写入每行（与 observed_at_utc 分开）
    if meta and meta.get("snapshot_timestamp"):
        for coll in ("legacy", "history"):
            for row in out.get(coll) or []:
                row["snapshot_timestamp"] = meta["snapshot_timestamp"]
                row["snapshot_previous_timestamp"] = meta.get("previous_timestamp")
                row["snapshot_next_timestamp"] = meta.get("next_timestamp")
    return out


# ── 报价时间信息（★仅信息性，**不做过滤 / 不设使用期限**） ──
# ★2026-10-09 政策更新（用户决定）：**取消所有统一使用期限**。
#   历史比赛 / xG / 球队统计 / 球员 / 阵容 / 伤停 / 赔率的全部合法数据长期保留，
#   不因超过任何固定天数（7/30/90 天）而清理或禁止读取；赔率快照永久保留并允许任意历史区间查询。
#   Hermes 只负责**如实提供时间戳与时间差**；历史窗口、时效权重、预测切点**由 V3 决定**。
#   下列函数仅供 V3 **可选参考**，绝不用于过滤数据，也不作为任何视图/合同的准入条件。
#   （保留常量与函数以兼容既有调用，但语义已从"闸门"降级为"信息"。）

# 参考值：若 V3 想用某个时效阈值，可参考此值；**数据库不强制**。
REFERENCE_FRESHNESS_SECONDS = 1800


def _parse_iso(ts):
    import datetime as _dt
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def quote_age_seconds(market_last_update, at_utc):
    """报价时间差（秒）= at_utc − market_last_update。None=不可判定。**仅信息，不过滤**。"""
    a, b = _parse_iso(market_last_update), _parse_iso(at_utc)
    if a is None or b is None:
        return None
    return (b - a).total_seconds()


def seconds_to_kickoff(commence_time, at_utc):
    """距开球时间差（秒）= commence_time − at_utc（正=赛前）。**仅信息，不过滤**。"""
    a, b = _parse_iso(commence_time), _parse_iso(at_utc)
    if a is None or b is None:
        return None
    return (a - b).total_seconds()


def time_context(market_last_update=None, at_utc=None, commence_time=None):
    """返回纯**信息性**时间上下文（供 V3 自行加权）。**不再给出任何可用/不可用判定**。

    ★旧版曾按固定阈值输出"过期/新鲜"判定 —— 已移除：
      V3 决定用多长的历史、用多旧的报价，Hermes 不设限、不筛选。
    """
    age = quote_age_seconds(market_last_update, at_utc)
    to_ko = seconds_to_kickoff(commence_time, at_utc)
    return {
        "quote_age_seconds": age,          # 报价距分析时刻的秒数（可为任意大小）
        "seconds_to_kickoff": to_ko,       # 距开球的秒数（正=赛前）
        "is_prematch_at_observation": (None if to_ko is None else to_ko > 0),
        "note": "仅供 V3 参考；Hermes 不设使用期限、不做时效过滤",
    }
