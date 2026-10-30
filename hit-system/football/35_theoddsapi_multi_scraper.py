# -*- coding: utf-8 -*-
"""
35_theoddsapi_multi_scraper.py — The Odds API 多庄家赔率爬虫（付费商业API）

真实来源: api.the-odds-api.com（聚合 bet365 / Betfair Exchange / Unibet 等）
⚠️ 注意: 此文件是商业API，与 15_pinnacle_guest_api_scraper 的 Pinnacle Guest API 完全不同
市场: 独赢(h2h) / 让球(spreads) / 大小球(totals)（默认；可用 --markets 扩展，须合订阅范围）

2026-10-09 专项增强（用户授权范围内）：
  * 原始响应/哈希/精确观察时间留存（theodds_api_raw_responses）
  * 事件身份表（theodds_api_events）+ 庄家目录 + 市场目录（含文档列出的市场，verified 区分）
  * 赔率历史「追加而非覆盖」（theodds_api_odds_history），保留 market.last_update ★关键字段，
    支持 point-in-time 查询（视图 v_theodds_latest_quote / v_theodds_quote_pit）
  * 单场 event 模式（--event-id / --sport），使用 /sports/{key}/events/{id}/odds/
  * 七 Key 固定顺序轮换（config.py），失败不换 Key 重试，额度未知/过期即阻断
"""
import sys, os, time, json, logging, argparse
import requests
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, text

import env_setup
import config as _cfg
from config import (DB_ENGINE_URL, THE_ODDS_API_BASE, update_the_odds_api_quota)
from db_utils import batch_upsert, exec_ddl

import source_evidence as SE
import odds_extract as OX

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# 每枚 key 的轮换阈值固定为 1；未有近期 provider-confirmed 余量时阻断。
# 账户级最小余量闸保持独立，显式低额度参数不能绕过该闸。
QUOTA_ROTATE_BELOW = 1


def select_the_odds_api_slot(rotate_below=None):
    """★2026-10-24 用户决策 C：按余额倒序选槽（余量最高的先烧）。

    原策略是固定顺序 1→9（用户 2026-10-09 定的）。改为倒序的原因：
    The Odds API 在**额度不足时返回 401 而非 402**，Key1(剩0) 一调 /v4/odds 就被
    标 AUTH_FAILED，导致 `_quota_confirmation_is_current()=False`，
    fixed_order 的 `return None` 让**整池 9 个 key 全部不可用**（哪怕 Key9 剩 499）。
    倒序后天然先用到余额最多的 Key9，不会撞上已耗尽的槽。
    """
    rb = QUOTA_ROTATE_BELOW if rotate_below is None else rotate_below
    return _cfg.select_the_odds_api_slot_desc(rb)


# ── 额度预算闸（2026-10-09 额度事故后新增）─────────────────────────────
# 计费口径（官方）：cost = [返回的市场数] × [请求指定的区域数]；/sports 为 0 额度。
# 事故背景：_refresh_odds_snapshot 每 4h 全量跑一次本爬虫(≈200 额度)，3 天打空 3500 额度。
# 本闸门提供三层保护：
#   1) 预检：八槽合计剩余 < min_remaining → 直接拒绝派发（不发任何请求）；
#   2) 单次上限：本次运行累计估算消耗 ≥ budget_cap → 停止继续抓取剩余赛种；
#   3) 派发前打印预估、结束后打印实耗，便于审计。
# ★2026-10-24 重新启用：默认 0（停用）→ 20（单次运行上限）。
#   背景：新增 THE_ODDS_API_KEY_9（满额 500），9 槽总余量 815（原 313）。
#   20/次 × 每天最多 1 次 ≈ 20/天 → 815 次可支撑约 40 天。
#   如需彻底停用，设 THEODDS_DAILY_CREDIT_CAP=0。
DEFAULT_BUDGET_CAP = int(os.environ.get("THEODDS_DAILY_CREDIT_CAP", "20"))
ACCOUNT_QUOTA_RESERVE_MINIMUM = 50
DEFAULT_MIN_REMAINING = max(ACCOUNT_QUOTA_RESERVE_MINIMUM,
                            int(os.environ.get("QQSJ_ODDS_API_MIN_REMAINING", "50")))


def _total_remaining():
    """八槽近期 provider-confirmed 余量合计；忽略初始化计划值和过期回执。"""
    return _cfg.sum_current_verified_quota_remaining(
        _cfg.get_the_odds_api_pool_metadata())


# P2：本次运行的请求计数（供采集运行日志收尾使用）
_RUN_STATS = {"requests": 0, "requests_ok": 0, "requests_failed": 0,
              "bodies_new": 0, "bodies_deduplicated": 0}


def preflight_budget(min_remaining=None, allow_low_quota=False):
    """预检额度。返回 (是否放行, 合计剩余)；低于账户级保留量时始终阻断。"""
    requested = DEFAULT_MIN_REMAINING if min_remaining is None else int(min_remaining)
    mr = max(ACCOUNT_QUOTA_RESERVE_MINIMUM, requested)
    tot = _total_remaining()
    if allow_low_quota:
        log.warning("忽略 allow_low_quota：账户级最小余量闸不能被绕过")
    if tot < mr:
        log.error(
            "额度闸拦截：八槽合计剩余 %s < 下限 %s → 拒绝派发（未发送任何请求）。", tot, mr)
        return False, tot
    return True, tot


def response_cost(payload, regions):
    """本次响应的实际计费 = 返回的不同市场数 × 区域数。"""
    n_regions = len([r for r in (regions or "").split(",") if r.strip()]) or 1
    markets = set()
    for ev in (payload if isinstance(payload, list) else []) or []:
        if not isinstance(ev, dict):
            continue
        for bk in ev.get("bookmakers", []) or []:
            for m in bk.get("markets", []) or []:
                if isinstance(m, dict) and m.get("key"):
                    markets.add(m["key"])
    return len(markets) * n_regions

engine = create_engine(DB_ENGINE_URL)

TARGET_BOOKMAKERS = ['bet365', 'betfair_ex_eu', 'betfair_ex_uk', 'unibet_eu', 'unibet']
MARKETS  = 'h2h,spreads,totals'
REGIONS  = 'uk,eu'
SPORT_GROUPS = {'Soccer', 'Basketball'}

FALLBACK_SPORT_KEYS = [
    'soccer_epl', 'soccer_spain_la_liga', 'soccer_germany_bundesliga',
    'soccer_italy_serie_a', 'soccer_france_ligue_one',
    'soccer_netherlands_eredivisie', 'soccer_portugal_primeira_liga',
    'soccer_turkey_super_league', 'soccer_usa_mls',
    'soccer_uefa_champs_league', 'soccer_uefa_europa_league',
    'basketball_nba', 'basketball_euroleague',
]

_QUOTA_HEADERS = ('x-requests-remaining', 'x-requests-used', 'x-requests-last')


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS theodds_api_odds (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id      TEXT,
            sport         TEXT,
            sport_key     TEXT,
            league_name   TEXT,
            home_team     TEXT,
            away_team     TEXT,
            commence_time TEXT,
            bookmaker     TEXT,
            market        TEXT,
            outcome       TEXT,
            odds          REAL,
            point         REAL,
            fetch_date    TEXT,
            UNIQUE(event_id, bookmaker, market, outcome, fetch_date)
        )
    """)
    # 来源证据层表/视图（幂等新增，不动既有表）
    SE.create_evidence_tables(engine)


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _api_get_ev(endpoint, params=None, *, timeout=20):
    """单次选取 slot、单次发送请求、不换 Key 重试；返回 (payload, evidence)。

    evidence 含：raw body / sha256 / 观察时间 / HTTP 状态 / 额度头 / ETag 等。
    """
    selected = select_the_odds_api_slot()
    if not selected:
        log.warning("The Odds API: no eligible configured quota slot (unknown/stale → BLOCK)")
        return None, {"error": "NO_ELIGIBLE_SLOT"}
    res = _authoritative_api_get(endpoint, params=params, selected=selected, timeout=timeout)
    resp = res.get("response")
    if resp is None:
        return None, {"error": res.get("error"), "selected_slot_id": res.get("selected_slot_id"),
                      "request_started_at_utc": res.get("request_started_at_utc"),
                      "observed_at_utc": res.get("observed_at_utc")}
    hdrs = resp.headers
    ev = {
        "selected_slot_id": res.get("selected_slot_id"),
        "request_url": f"{THE_ODDS_API_BASE}{endpoint}",
        "request_params": params,
        "request_started_at_utc": res.get("request_started_at_utc"),
        "observed_at_utc": res.get("observed_at_utc") or SE.now_utc_iso(),
        "http_status": resp.status_code,
        "raw_body": resp.text,
        "etag": hdrs.get("ETag"),
        "last_modified": hdrs.get("Last-Modified"),
        "content_type": hdrs.get("Content-Type"),
        "quota_remaining": _int_or_none(hdrs.get("x-requests-remaining")),
        "quota_used": _int_or_none(hdrs.get("x-requests-used")),
        "quota_last": _int_or_none(hdrs.get("x-requests-last")),
    }
    # 原始响应无条件留存（含非 200，作为失败证据；绝不含 API Key）
    ev["observation_id"] = SE.save_raw_response(
        engine, provider=SE.PROVIDER_ODDS, endpoint=endpoint, raw_body=res_ev_body(resp),
        source_event_id=(params or {}).get("event_id"), sport_key=_sport_key_from_endpoint(endpoint),
        request_url=ev["request_url"], request_params=params,
        request_started_at_utc=ev["request_started_at_utc"], observed_at_utc=ev["observed_at_utc"],
        http_status=resp.status_code, etag=ev["etag"], last_modified=ev["last_modified"],
        content_type=ev["content_type"], source_version=None,
        source_version_note="The Odds API 未提供官方报价版本号；本地 sha256 为内容哈希，非官方版本",
        quota_remaining=ev["quota_remaining"], quota_used=ev["quota_used"], quota_last=ev["quota_last"])
    # ── 分派回执（每次 HTTP 一条，与去重后的 body 存储区分开）──
    _body = ev.get("raw_body")
    SE.record_dispatch(
        engine, provider=SE.PROVIDER_ODDS, endpoint=endpoint,
        request_started_at_utc=ev["request_started_at_utc"],
        request_finished_at_utc=ev["observed_at_utc"], observed_at_utc=ev["observed_at_utc"],
        http_status=resp.status_code, outcome=SE.classify_outcome(resp.status_code),
        response_sha256=SE.sha256_text(_body or ""),
        response_bytes=len((_body or "").encode("utf-8")),
        raw_response_id=ev["observation_id"],
        body_deduplicated=SE.body_was_deduplicated(engine, SE.PROVIDER_ODDS, ev["observation_id"]),
        etag=ev["etag"], last_modified=ev["last_modified"], content_type=ev["content_type"],
        quota_remaining=ev["quota_remaining"], quota_used=ev["quota_used"],
        quota_last=ev["quota_last"], source_event_id=(params or {}).get("event_id"),
        sport_key=_sport_key_from_endpoint(endpoint), request_url=ev["request_url"],
        request_params=params,
        # 任务书字段：quota_cost = 本次请求实际消耗（The Odds API 用 x-requests-last 报告）
        quota_cost=ev.get("quota_last"),
        request_scope=f"odds:{_sport_key_from_endpoint(endpoint)}:"
                      f"{(params or {}).get('markets', 'h2h')}:{(params or {}).get('regions', '-')}")
    # ── 逐槽额度回执（脱敏指纹，绝不含完整 Key）──
    SE.record_quota_receipt(
        engine, provider=SE.PROVIDER_ODDS, slot_id=selected.get("slot_id"),
        key=selected.get("key"), endpoint=endpoint, http_status=resp.status_code,
        quota_remaining=ev["quota_remaining"], quota_used=ev["quota_used"],
        quota_last=ev["quota_last"], observed_at_utc=ev["observed_at_utc"])
    # ── P2 运行计数 ──
    _RUN_STATS["requests"] += 1
    if resp.status_code == 200:
        _RUN_STATS["requests_ok"] += 1
    else:
        _RUN_STATS["requests_failed"] += 1
    if SE.body_was_deduplicated(engine, SE.PROVIDER_ODDS, ev["observation_id"]):
        _RUN_STATS["bodies_deduplicated"] += 1
    else:
        _RUN_STATS["bodies_new"] += 1
    if resp.status_code == 200:
        try:
            return resp.json(), ev
        except ValueError:
            log.warning("The Odds API: invalid JSON response")
            return None, ev
    if resp.status_code == 422:
        return None, ev
    if resp.status_code in (401, 403):
        log.warning("The Odds API: selected credential slot rejected")
    elif resp.status_code == 429:
        log.warning("The Odds API: rate limited; no same-call credential failover")
    else:
        log.debug("HTTP %s: %s", resp.status_code, endpoint)
    return None, ev


def res_ev_body(resp):
    """原始 body：优先 resp.text，退化为 str(content)。"""
    try:
        return resp.text
    except Exception:
        try:
            return resp.content.decode("utf-8", "replace")
        except Exception:
            return None


def _sport_key_from_endpoint(endpoint):
    # /sports/{sport_key}/odds/ 或 /sports/{sport_key}/events/{id}/odds/
    parts = [p for p in (endpoint or "").split("/") if p]
    if len(parts) >= 2 and parts[0] == "sports" and parts[1] not in ("",):
        return parts[1]
    return None


def _api_get(endpoint, params=None):
    """兼容旧调用：只返回 payload。"""
    payload, _ev = _api_get_ev(endpoint, params=params)
    return payload


def _authoritative_api_get(endpoint, params=None, *, selected=None, timeout=20):
    """预选一次、发送至多一次、绝不换 Key 重试。"""
    selected = selected or select_the_odds_api_slot()
    if not selected:
        return {"selected_slot_id": None, "response": None, "error": "NO_ELIGIBLE_SLOT",
                "request_started_at_utc": SE.now_utc_iso(), "observed_at_utc": SE.now_utc_iso()}
    api_key = selected["key"]
    url = f"{THE_ODDS_API_BASE}{endpoint}"
    request_params = {"apiKey": api_key, **(params or {})}
    request_started = SE.now_utc_iso()
    response = None
    transport_error = None
    try:
        response = requests.get(url, params=request_params, timeout=timeout)
    except requests.exceptions.Timeout:
        transport_error = "TIMEOUT"
    except requests.exceptions.ConnectionError:
        transport_error = "CONNECTION_ERROR"
    except requests.exceptions.RequestException:
        transport_error = "NETWORK_ERROR"
    finally:
        status = response.status_code if response is not None else None
        headers = response.headers if response is not None else None
        update_the_odds_api_quota(
            selected["slot_id"], http_status=status, headers=headers,
            transport_error=transport_error,
        )
    return {"selected_slot_id": selected["slot_id"], "response": response, "error": transport_error,
            "request_started_at_utc": request_started, "observed_at_utc": SE.now_utc_iso()}


def list_sports():
    data, _ev = _api_get_ev('/sports/')
    if not data:
        return FALLBACK_SPORT_KEYS
    return [
        s['key'] for s in data
        if s.get('active') and s.get('group', '') in SPORT_GROUPS
        and not s.get('has_outrights', False)
    ]


def fetch_sport_odds(sport_key, markets=None, regions=None, bookmakers=None):
    """广播式多赛事抓取（原有行为）。返回 (payload, evidence)。"""
    return _api_get_ev(f'/sports/{sport_key}/odds/', {
        'regions':     regions or REGIONS,
        'markets':     markets or MARKETS,
        'bookmakers':  ','.join(bookmakers or TARGET_BOOKMAKERS),
        'dateFormat':  'iso',
        'oddsFormat':  'decimal',
    })


def fetch_event_odds(sport_key, event_id, markets=None, regions=None, bookmakers=None):
    """单场 event 模式：/sports/{sport_key}/events/{event_id}/odds/。返回 (payload, evidence)。"""
    return _api_get_ev(f'/sports/{sport_key}/events/{event_id}/odds/', {
        'regions':     regions or REGIONS,
        'markets':     markets or MARKETS,
        'bookmakers':  ','.join(bookmakers or TARGET_BOOKMAKERS),
        'dateFormat':  'iso',
        'oddsFormat':  'decimal',
    })


def _sport(sport_key):
    if 'soccer' in sport_key:
        return 'football'
    if 'basketball' in sport_key:
        return 'basketball'
    return 'other'


def _outcome(oc_name, home_team, away_team, market_key):
    return OX._normalize_outcome(oc_name, home_team, away_team, market_key)


_VALID_MARKETS = {'h2h', 'spreads', 'totals'}


def _market(market_key):
    return {'h2h': 'moneyline', 'spreads': 'spread', 'totals': 'total'}.get(market_key)


def parse_events(events, sport_key, fetch_date):
    """兼容入口：返回 theodds_api_odds 的 13 列行。"""
    rows, _ = _parse_and_split(events, sport_key, fetch_date,
                               observed_at_utc=SE.now_utc_iso(),
                               raw_response_hash=OX.payload_hash(events),
                               source_endpoint=f"/sports/{sport_key}/odds/")
    return rows


def _parse_and_split(payload, sport_key, fetch_date, observed_at_utc, raw_response_hash,
                     source_endpoint):
    r = OX.extract_quote_rows(payload if isinstance(payload, list) else payload.get("events", payload),
                              sport_key, observed_at_utc, raw_response_hash, fetch_date,
                              source_endpoint=source_endpoint)
    return r["legacy"], r


def _persist_evidence(sport_key, payload, ev, fetch_date):
    """把一次响应的扩展解析结果写入证据层（事件/历史/庄家/市场）。"""
    observed_at = ev.get("observed_at_utc") or SE.now_utc_iso()
    raw_hash = SE.sha256_text(ev.get("raw_body") or "")
    if isinstance(payload, dict) and "events" in payload and isinstance(payload["events"], list):
        events_payload = payload["events"]
    else:
        events_payload = payload if isinstance(payload, list) else []
    parsed = OX.extract_quote_rows(events_payload, sport_key, observed_at, raw_hash, fetch_date,
                                   source_endpoint=ev.get("request_url"))
    evrows = OX.extract_event_rows(events_payload, sport_key, observed_at, raw_hash)
    for e in evrows:
        e["last_observation_id"] = ev.get("observation_id")
    n_hist = SE.write_rows(engine, "theodds_api_odds_history", parsed["history"],
                           ["contract_key"])
    n_ev = SE.write_rows(engine, "theodds_api_events", evrows, ["event_id"])
    n_bk = SE.write_rows(engine, "theodds_api_bookmakers", parsed["bookmakers"], ["bookmaker_key"])
    # 先写「文档目录」再写「真实观察」：保证 verified=1 的实测市场不被 verified=0 的文档行覆盖
    doc_rows = OX.documented_market_rows(observed_at)
    n_mk = SE.write_rows(engine, "theodds_api_market_catalog",
                         doc_rows + parsed["markets"], ["market_key"])
    return {"history": n_hist, "events": n_ev, "bookmakers": n_bk, "markets": n_mk,
            "legacy": len(parsed["legacy"])}


def run(fetch_date=None, markets=None, regions=None, bookmakers=None,
        sport_keys=None, event_id=None, sport=None,
        budget_cap=None, min_remaining=None, allow_low_quota=False):
    if not fetch_date:
        fetch_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # 2026-10-21 停用（第 3 阶段 3.4）：The Odds API key 与 football-predictor 共用，额度只剩约 380。
    # ★2026-10-24 重新启用：新增 KEY_9（满额 500），总余量 815。
    # 早退闸门改为引用 DEFAULT_BUDGET_CAP（默认 20），避免此处默认值与模块常量不一致。
    _early_cap = int(os.environ.get("THEODDS_DAILY_CREDIT_CAP", str(DEFAULT_BUDGET_CAP)))
    if _early_cap <= 0:
        print('35 disabled: THEODDS_DAILY_CREDIT_CAP=0')
        return 0

    cap = DEFAULT_BUDGET_CAP if budget_cap is None else int(budget_cap)

    init_tables()
    log.info('=' * 60)
    log.info(f'The Odds API 多庄家  [{fetch_date}]')
    log.info(f'目标庄家: {", ".join(bookmakers or TARGET_BOOKMAKERS)}  市场: {markets or MARKETS}')
    log.info(f'区域: {regions or REGIONS}   单次额度上限: {cap}'
             f'（预估: 每次赛种 ≤ {len((markets or MARKETS).split(",")) * len((regions or REGIONS).split(","))} 额度）')
    log.info('=' * 60)

    # ── P2 采集运行日志：由爬虫自写，直调/subprocess 也留痕 ──
    _run_id = SE.begin_collection_run(
        engine, provider=SE.PROVIDER_ODDS, script="35_theoddsapi_multi_scraper.py",
        scope=(f"event:{event_id}" if event_id else (f"sport:{sport}" if sport else
               (f"keys:{len(sport_keys)}" if sport_keys else "all_sports"))),
        args={"fetch_date": fetch_date, "markets": markets, "regions": regions,
              "bookmakers": bookmakers, "event_id": event_id, "sport": sport,
              "budget_cap": cap, "min_remaining": min_remaining,
              "allow_low_quota": allow_low_quota})
    _run_started = SE.now_utc_iso()
    for _k in _RUN_STATS:
        _RUN_STATS[_k] = 0

    # ── 额度预算闸：预检（不放行则一个请求都不发）──
    ok, total_rem = preflight_budget(min_remaining, allow_low_quota)
    if not ok:
        SE.record_exception(engine, provider=SE.PROVIDER_ODDS, run_id=_run_id, severity="warning",
                            category="quota", message=f"额度闸拦截：八槽合计 {total_rem} < 下限 "
                            f"{max(ACCOUNT_QUOTA_RESERVE_MINIMUM, DEFAULT_MIN_REMAINING if min_remaining is None else int(min_remaining))}；未发送任何请求",
                            handled=1, context={"total_remaining": total_rem})
        SE.finish_collection_run(engine, _run_id, status="blocked",
                                 blocked_reason="quota_below_threshold", exit_code=0,
                                 started_at_utc=_run_started, notes=f"total_remaining={total_rem}")
        return 0
    log.info(f'额度预检通过：八槽合计剩余 {total_rem}')

    all_rows = []
    summary = []
    spent = 0

    if event_id:
        sk = sport or 'soccer_epl'
        payload, ev = fetch_event_odds(sk, event_id, markets=markets, regions=regions,
                                       bookmakers=bookmakers)
        if payload:
            rows, _ = _parse_and_split(payload if isinstance(payload, list) else payload.get("events", payload),
                                       sk, fetch_date,
                                       observed_at_utc=ev.get("observed_at_utc"),
                                       raw_response_hash=SE.sha256_text(ev.get("raw_body") or ""),
                                       source_endpoint=ev.get("request_url"))
            all_rows.extend(rows)
            stats = _persist_evidence(sk, payload, ev, fetch_date)
            summary.append((sk, stats))
            spent += response_cost(payload if isinstance(payload, list) else payload.get("events", []),
                                   regions or REGIONS)
            log.info(f"  [event {event_id}] {sk}: legacy={len(rows)} evidence={stats}")
        else:
            log.warning(f"  [event {event_id}] {sk}: 无数据（额度/凭证/网络受限，未重试）")
        log.info(f"本次实耗 ≈ {spent} 额度（预检时八槽合计剩余 {total_rem}）")
        return _write_legacy(all_rows, ["event_id", "bookmaker", "market", "outcome", "fetch_date"])

    sport_keys = sport_keys or list_sports()
    log.info(f"活跃赛种: {len(sport_keys)} 个（单次上限 {cap} 额度）")
    n_seen = 0
    for sk in sport_keys:
        if spent >= cap:
            log.warning(f"额度闸：本次已用 {spent} ≥ 单次上限 {cap}，停止继续抓取"
                        f"（{len(sport_keys) - n_seen} 个赛种未取）")
            break
        n_seen += 1
        payload, ev = fetch_sport_odds(sk, markets=markets, regions=regions, bookmakers=bookmakers)
        if not payload:
            continue
        rows, _ = _parse_and_split(payload, sk, fetch_date,
                                   observed_at_utc=ev.get("observed_at_utc"),
                                   raw_response_hash=SE.sha256_text(ev.get("raw_body") or ""),
                                   source_endpoint=ev.get("request_url"))
        all_rows.extend(rows)
        spent += response_cost(payload, regions or REGIONS)
        stats = _persist_evidence(sk, payload, ev, fetch_date)
        summary.append((sk, stats))
        bk_cnt = {}
        for r in rows:
            bk_cnt[r['bookmaker']] = bk_cnt.get(r['bookmaker'], 0) + 1
        bk_str = ', '.join(f"{k}={v}" for k, v in sorted(bk_cnt.items()))
        log.info(f"  {sk}: {len(payload)} 场  {bk_str}  evidence={stats}")
        time.sleep(0.5)

    if not all_rows:
        log.warning("未获取到任何赔率数据（检查API key余量 / 额度未知即阻断）")
        log.info(f"本次实耗 ≈ {spent} 额度（预检时八槽合计剩余 {total_rem}）")
        SE.finish_collection_run(engine, _run_id, status="partial",
                                 blocked_reason="no_rows_returned", exit_code=0,
                                 started_at_utc=_run_started,
                                 requests_total=_RUN_STATS["requests"],
                                 requests_ok=_RUN_STATS["requests_ok"],
                                 requests_failed=_RUN_STATS["requests_failed"],
                                 bodies_new=_RUN_STATS["bodies_new"],
                                 bodies_deduplicated=_RUN_STATS["bodies_deduplicated"],
                                 notes=f"est_credits_spent={spent}")
        return _write_legacy(all_rows, ["event_id", "bookmaker", "market", "outcome", "fetch_date"])
    SE.finish_collection_run(engine, _run_id, status="ok", exit_code=0,
                             started_at_utc=_run_started,
                             requests_total=_RUN_STATS["requests"],
                             requests_ok=_RUN_STATS["requests_ok"],
                             requests_failed=_RUN_STATS["requests_failed"],
                             bodies_new=_RUN_STATS["bodies_new"],
                             bodies_deduplicated=_RUN_STATS["bodies_deduplicated"],
                             notes=f"est_credits_spent={spent}")
    log.info(f"本次实耗 ≈ {spent} 额度（预检时八槽合计剩余 {total_rem}；"
             f"单次上限 {cap}；请用 _refresh_odds_quota.py 复核真实余量）")
    return _write_legacy(all_rows, ["event_id", "bookmaker", "market", "outcome", "fetch_date"])


def _write_legacy(all_rows, unique_keys):
    md = MetaData()
    md.reflect(bind=engine, only=['theodds_api_odds'])
    tbl = md.tables['theodds_api_odds']
    written = 0
    for i in range(0, len(all_rows), 500):
        chunk = all_rows[i:i+500]
        try:
            batch_upsert(engine, tbl, chunk, unique_keys=unique_keys)
            written += len(chunk)
        except Exception as e:
            log.warning(f"写库失败 (chunk {i}): {e}")
    if all_rows:
        bk_total = {}
        for r in all_rows:
            bk_total[r['bookmaker']] = bk_total.get(r['bookmaker'], 0) + 1
        log.info(f"完成: 写入 {written} 条")
        for bk, cnt in sorted(bk_total.items(), key=lambda x: -x[1]):
            log.info(f"  {bk}: {cnt} 条")
    return written


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    p.add_argument('--markets', default=None, help='逗号分隔市场，默认 h2h,spreads,totals')
    p.add_argument('--regions', default=None, help='默认 uk,eu')
    p.add_argument('--bookmakers', default=None, help='逗号分隔，默认内置 5 家')
    p.add_argument('--sport', default=None, help='仅抓单个 sport_key（如 soccer_epl）')
    p.add_argument('--event-id', default=None, help='单场 event 模式（需配合 --sport）')
    p.add_argument('--allow-low-quota', action='store_true',
                   help='兼容旧参数；不绕过账户级最小余量闸或每槽已验证轮换规则')
    p.add_argument('--budget-cap', type=int, default=None,
                   help=f'单次运行额度上限（默认 {DEFAULT_BUDGET_CAP}，可用环境变量 '
                        f'QQSJ_ODDS_API_BUDGET_CAP 覆盖）；达到即停止继续抓取')
    p.add_argument('--min-remaining', type=int, default=None,
                   help=f'预检下限：八槽合计剩余低于账户保留量直接拒绝派发（最低 {ACCOUNT_QUOTA_RESERVE_MINIMUM}；默认 {DEFAULT_MIN_REMAINING}）')
    args = p.parse_args()
    if args.allow_low_quota:
        log.warning('已忽略兼容参数 --allow-low-quota；账户级最小余量闸仍生效')
    bks = args.bookmakers.split(',') if args.bookmakers else None
    sks = [args.sport] if (args.sport and not args.event_id) else None
    written = run(fetch_date=args.date, markets=args.markets, regions=args.regions,
                  bookmakers=bks, sport_keys=sks, event_id=args.event_id, sport=args.sport,
                  budget_cap=args.budget_cap, min_remaining=args.min_remaining,
                  allow_low_quota=args.allow_low_quota)
    sys.exit(0 if written >= 0 else 1)
