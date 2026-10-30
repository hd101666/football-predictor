# -*- coding: utf-8 -*-
"""
46_sportmonks_fixtures_scraper.py — Sportmonks Football API v3 采集器（Task B 第二来源）

用途：为 V3 提供**第二大来源**的赛事/赛季身份，与 FotMob 交叉验证。
依据：https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-all-fixtures

★授权状态：Sportmonks 需 token（实测无 token → HTTP 401）。
  本机当前无 SPORTMONKS_API_KEY / SPORTMONKS_TOKEN，因此**真实采集不能执行**。
  本脚本设计为「有 token 即插即用」：设置环境变量后无需改代码。

环境变量（任选其一）：
  SPORTMONKS_API_KEY  或  SPORTMONKS_TOKEN

用法：
  python -X utf8 46_sportmonks_fixtures_scraper.py --check                # 只检查凭证
  python -X utf8 46_sportmonks_fixtures_scraper.py --probe-league 8       # 探测联赛(8=英超)当前赛季
  python -X utf8 46_sportmonks_fixtures_scraper.py --date 2026-10-11      # 抓某日赛程
  python -X utf8 46_sportmonks_fixtures_scraper.py --season 23690 --apply # 抓某赛季并落库
  python -X utf8 46_sportmonks_fixtures_scraper.py --team 8 --apply       # 抓球队→赛季→身份

未提供 token 时：以 exit code 3 明确退出（而非静默失败或伪造数据）。
"""
import os
import sys
import json
import argparse
import hashlib
import urllib.request
import urllib.error
import datetime
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    import env_setup  # noqa
except Exception:
    pass

from sqlalchemy import create_engine, text
import sportmonks_extract as SM

BASE = "https://api.sportmonks.com/v3/football"
TOKEN_ENVS = ("SPORTMONKS_API_KEY", "SPORTMONKS_TOKEN")
RATE_SLEEP = 1.2          # 保守限速（免费档约 180 req/min → 远低于上限）
EXIT_NO_TOKEN = 3

engine = None


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_token():
    for k in TOKEN_ENVS:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return None


def _req(path, params=None, token=None):
    params = dict(params or {})
    params["api_token"] = token
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "qqsj-sportmonks/1.0",
                                               "Accept": "application/json"})
    started = now_utc()
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read()
        status = e.code
    except Exception as e:
        body = json.dumps({"transport_error": str(e)}).encode()
        status = 0
    return {"url": url.replace(token, "***"), "path": path, "params": {k: v for k, v in params.items()
                                                                       if k != "api_token"},
            "http_status": status, "body": body,
            "request_started_at_utc": started, "request_finished_at_utc": now_utc(),
            "elapsed_ms": int((time.time() - t0) * 1000)}


def _persist(engine, resp, rows, table, key_cols, *, request_scope, quota_cost=1):
    """写原始响应 + 分派回执 + 规范化行（复用证据层）。"""
    import source_evidence as SE
    sha = hashlib.sha256(resp["body"]).hexdigest()
    obs_id = SE.record_raw_response(
        engine, provider=SM.PROVIDER, endpoint=resp["path"], raw_bytes=resp["body"],
        http_status=resp["http_status"], request_url=resp["url"],
        request_params=resp["params"], observed_at_utc=resp["request_finished_at_utc"],
        request_started_at_utc=resp["request_started_at_utc"], quota_cost=quota_cost,
        request_scope=request_scope)
    for row in rows:
        row.setdefault("observation_id", obs_id)
        row.setdefault("raw_response_hash", sha)
        row.setdefault("observed_at_utc", resp["request_finished_at_utc"])
    if rows:
        SE.write_rows(engine, table, rows, key_cols)
    return obs_id, sha, len(rows)


def main():
    global engine
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="仅检查凭证是否存在")
    ap.add_argument("--probe-league", type=int, help="探测该联赛的当前赛季（Sportmonks league id）")
    ap.add_argument("--team", type=int, help="按球队 ID 取赛季（/seasons/teams/{id}）")
    ap.add_argument("--date", help="抓某日赛程 YYYY-MM-DD")
    ap.add_argument("--season", type=int, help="抓某赛季 fixtures（filters=fixtureLeagues 或 seasons include）")
    ap.add_argument("--seasons-by-league", type=int, action="append", default=None,
                    help="抓某联赛的全部赛季（可重复；/v3/football/seasons?filters=seasonLeagues:{id}）")
    ap.add_argument("--seasons-all", action="store_true", help="抓全部赛季（订阅范围内的）")
    ap.add_argument("--sidelined-team", type=int, help="抓某球队伤停/停赛（task D；include=sidelined，全套餐免费）")
    ap.add_argument("--sidelined-history", action="store_true",
                    help="配合 --sidelined-team：用 sidelinedHistory 取完整伤停历史")
    ap.add_argument("--fixture-lineups", type=int, metavar="FIXTURE_ID",
                    help="抓某 fixture 阵容（Task E；官方阵容全套餐免费，约开赛前1小时公布）")
    ap.add_argument("--league-id", type=int, default=None, help="配合 --season：按联赛过滤")
    ap.add_argument("--apply", action="store_true", help="落库（否则仅 dry-run）")
    a = ap.parse_args()

    token = get_token()
    if not token:
        print(json.dumps({
            "provider": SM.PROVIDER,
            "status": "NO_CREDENTIALS",
            "checked_env_vars": list(TOKEN_ENVS),
            "http_probe_without_token": "401 No token provided",
            "action_required": "设置 SPORTMONKS_API_KEY（或 SPORTMONKS_TOKEN）后重跑",
            "note": "未伪造任何数据；真实采集未执行。",
        }, ensure_ascii=False, indent=1))
        return EXIT_NO_TOKEN

    if a.check:
        r = _req("leagues/8", {"include": ""}, token)
        print(json.dumps({"status": "TOKEN_PRESENT", "http_status": r["http_status"],
                          "body_head": r["body"][:300].decode("utf-8", "ignore")},
                         ensure_ascii=False, indent=1))
        return 0

    os.makedirs("data", exist_ok=True)
    from config import DB_ENGINE_URL
    engine = create_engine(DB_ENGINE_URL)
    import source_evidence as SE

    # 确保新表存在
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sportmonks_season_identity (
                sm_season_id TEXT PRIMARY KEY, league_id TEXT, season_name TEXT,
                is_current INTEGER, finished INTEGER, starting_at TEXT, ending_at TEXT,
                natural_key TEXT, source_endpoint TEXT, raw_response_hash TEXT,
                observation_id TEXT, observed_at_utc TEXT, first_seen_utc TEXT,
                first_seen_status TEXT, provider TEXT
            )"""))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sportmonks_fixture_identity (
                provider_fixture_id TEXT PRIMARY KEY, league_id TEXT, season_id TEXT,
                stage_id TEXT, round_id TEXT, state_id TEXT, venue_id TEXT,
                home_team_name TEXT, away_team_name TEXT, kickoff_utc TEXT,
                kickoff_timestamp INTEGER, name TEXT, natural_key TEXT,
                raw_response_hash TEXT, observation_id TEXT, observed_at_utc TEXT,
                first_seen_utc TEXT, provider TEXT
            )"""))

    out = {"provider": SM.PROVIDER, "requests": 0, "rows": {}, "api_calls": []}

    def fetch(path, params, scope):
        r = _req(path, params, token)
        out["requests"] += 1
        out["api_calls"].append({"path": path, "http_status": r["http_status"]})
        time.sleep(RATE_SLEEP)
        return r

    # 1) 球队 → 赛季身份（最省额度，最适合先建身份）
    if a.team:
        r = fetch(f"seasons/teams/{a.team}", {}, "identity")
        rows = []
        if r["http_status"] == 200:
            payload = json.loads(r["body"])
            for s in SM.extract_seasons(payload):
                s["natural_key"] = None
                rows.append(s)
            if a.apply and rows:
                n = _persist(engine, r, [dict(
                    sm_season_id=str(s["season_id"]), league_id=str(s.get("league_id") or ""),
                    season_name=s.get("season_name"), is_current=int(bool(s.get("is_current"))),
                    finished=int(bool(s.get("finished"))), starting_at=s.get("starting_at"),
                    ending_at=s.get("ending_at"), natural_key=None,
                    source_endpoint=s.get("source_endpoint"),
                    raw_response_hash=s.get("raw_response_hash"),
                    observation_id=s.get("observation_id"), observed_at_utc=s.get("observed_at_utc"),
                    first_seen_utc=s.get("observed_at_utc"), first_seen_status="PROVEN",
                    provider=SM.PROVIDER) for s in rows], "sportmonks_season_identity",
                ["sm_season_id"], request_scope="identity")
                out["rows"]["sportmonks_season_identity"] = n
        out["api_calls"][-1]["parsed_rows"] = len(rows)

    # 2) 某日赛程 → 赛事身份
    if a.date:
        r = fetch("fixtures/date/" + a.date, {"include": "participants;league;season"},
                  "fixture_identity")
        rows = []
        if r["http_status"] == 200:
            payload = json.loads(r["body"])
            for f in SM.extract_fixtures(payload, observed_at_utc=r["request_finished_at_utc"]):
                f["natural_key"] = SM.natural_key(f["home_team_name"], f["away_team_name"],
                                                  f["kickoff_utc"])
                rows.append(f)
            if a.apply and rows:
                n = _persist(engine, r, [dict(
                    provider_fixture_id=str(f["provider_fixture_id"]),
                    league_id=str(f.get("league_id") or ""), season_id=str(f.get("season_id") or ""),
                    stage_id=str(f.get("stage_id") or ""), round_id=str(f.get("round_id") or ""),
                    state_id=str(f.get("state_id") or ""), venue_id=str(f.get("venue_id") or ""),
                    home_team_name=f.get("home_team_name"), away_team_name=f.get("away_team_name"),
                    kickoff_utc=f.get("kickoff_utc"), kickoff_timestamp=f.get("kickoff_timestamp"),
                    name=f.get("name"), natural_key=f.get("natural_key"),
                    raw_response_hash=f.get("raw_response_hash"),
                    observation_id=f.get("observation_id"), observed_at_utc=f.get("observed_at_utc"),
                    first_seen_utc=f.get("observed_at_utc"), provider=SM.PROVIDER) for f in rows],
                "sportmonks_fixture_identity", ["provider_fixture_id"], request_scope="fixture_identity")
                out["rows"]["sportmonks_fixture_identity"] = n
        out["api_calls"][-1]["parsed_rows"] = len(rows)

    # 3) 探测联赛当前赛季
    if a.probe_league is not None:
        r = fetch(f"leagues/{a.probe_league}", {"include": "currentSeason"}, "identity")
        if r["http_status"] == 200:
            payload = json.loads(r["body"])
            out["league_probe"] = {"league": (payload.get("data") or {}).get("name"),
                                   "current_season": (payload.get("data") or {}).get("currentseason")}
        time.sleep(RATE_SLEEP)
        r2 = fetch(f"seasons/leagues/{a.probe_league}", {}, "identity")
        if r2["http_status"] == 200:
            seas = SM.extract_seasons(json.loads(r2["body"]))
            out["seasons_found"] = [{"season_id": s["season_id"], "name": s["season_name"],
                                     "is_current": s["is_current"]} for s in seas[:8]]
            if a.apply and seas:
                n = _persist(engine, r2, [dict(
                    sm_season_id=str(s["season_id"]), league_id=str(s.get("league_id") or ""),
                    season_name=s.get("season_name"), is_current=int(bool(s.get("is_current"))),
                    finished=int(bool(s.get("finished"))), starting_at=s.get("starting_at"),
                    ending_at=s.get("ending_at"), natural_key=None,
                    source_endpoint=s.get("source_endpoint"),
                    raw_response_hash=s.get("raw_response_hash"),
                    observation_id=s.get("observation_id"), observed_at_utc=s.get("observed_at_utc"),
                    first_seen_utc=s.get("observed_at_utc"), first_seen_status="PROVEN",
                    provider=SM.PROVIDER) for s in seas], "sportmonks_season_identity",
                    ["sm_season_id"], request_scope="identity")
                out["rows"]["sportmonks_season_identity"] = n

    # 4) 球队伤停/停赛（Task D；sidelined 全套餐免费）
    if a.sidelined_team:
        inc = (SM.SIDELINED_INCLUDES["from_team_full_history"] if a.sidelined_history
               else SM.SIDELINED_INCLUDES["from_team"])
        r = fetch(f"teams/{a.sidelined_team}", {"include": inc}, "injury_availability")
        rows = []
        if r["http_status"] == 200:
            payload = json.loads(r["body"])
            data = payload.get("data") or {}
            # sidelinedHistory 与 sidelined 字段形状一致，只是键名不同
            src = dict(data)
            if a.sidelined_history and not src.get("sidelined"):
                src["sidelined"] = data.get("sidelinedhistory") or data.get("sidelinedHistory") or []
            rows = SM.extract_sidelined(src, source_entity_type="team",
                                        observed_at_utc=r["request_finished_at_utc"])
            for x in rows:
                x["source_team_id"] = x.get("source_team_id") or str(a.sidelined_team)
            if a.apply and rows:
                n = SE.upsert_availability(engine, rows)
                out["rows"]["player_availability"] = n
        out["api_calls"][-1]["parsed_rows"] = len(rows)

    # 5) fixture 阵容（Task E；官方/预测由 metadata.lineup_confirmed 严格区分）
    if a.fixture_lineups:
        inc = "lineups;formations;lineups.detailedposition;sidelined.sideline;metadata"
        r = fetch(f"fixtures/{a.fixture_lineups}", {"include": inc}, "lineup_snapshot")
        rows = []
        if r["http_status"] == 200:
            payload = json.loads(r["body"])
            data = payload.get("data") or {}
            rows = SM.extract_lineups(data, observed_at_utc=r["request_finished_at_utc"])
            if a.apply and rows:
                # 阵容走通用写入（含位置/队形/官方性列）
                SE.write_rows(engine, "fixture_lineups", [dict(
                    lineup_key=__import__("hashlib").sha256(
                        f"Sportmonks|{x['source_fixture_id']}|{x['source_player_id']}".encode()
                    ).hexdigest(),
                    provider=x["provider"], source_fixture_id=x["source_fixture_id"],
                    source_team_id=x["source_team_id"], source_player_id=x["source_player_id"],
                    player_name=x["player_name"], lineup_type=x["lineup_type"],
                    lineup_confirmed=x["lineup_confirmed"],
                    lineup_announcement_at=None, lineup_first_seen_utc=x["lineup_first_seen_utc"],
                    formation=x["formation"], position=x["position"], role=x["squad_status"],
                    squad_status=x["squad_status"], observed_at_utc=x["observed_at_utc"],
                    first_seen_status=x["first_seen_status"],
                    raw_response_hash=x["raw_response_hash"], receipt_id=x["receipt_id"],
                    source_json=json.dumps({k: x.get(k) for k in
                                            ("position_id", "formation_position", "jersey_number")},
                                           ensure_ascii=False),
                    notes=x["notes"], lineup_source_type=x["lineup_source_type"],
                    lineup_publishable=x["lineup_publishable"],
                    announcement_evidence=x["announcement_evidence"],
                    position_id=x["position_id"], formation_position=x["formation_position"],
                    jersey_number=x["jersey_number"],
                    lineup_meta_confirmed=x["lineup_confirmed"],
                ) for x in rows], ["lineup_key"])
                out["rows"]["fixture_lineups"] = len(rows)
        out["api_calls"][-1]["parsed_rows"] = len(rows)
        if rows:
            out["lineup_type_detected"] = rows[0]["lineup_type"]

    out["dry_run"] = not a.apply
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa  (used in _req)
    sys.exit(main())
