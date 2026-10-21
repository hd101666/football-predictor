# -*- coding: utf-8 -*-
"""
篮球独立预测模型
================
引擎架构（优先级由高到低）：
  1. elo+pace    - ELO 与 Pace/ORtg/DRtg 融合（60% BRef + 40% ELO）
  2. pace_only   - 仅 Basketball-Reference 赛季效率数据
  3. elo         - 仅 ELO（双方均有历史记录）
  4. elo_partial - 仅 ELO（一方有历史记录）
  5. implied_odds - 赔率隐含概率
  6. default_home_adv - 主场基准（57%）

数据来源：basketball_matches（ELO）+ bballref_team_stats（ORtg/DRtg/Pace）
输出：写入 market_prediction_snapshot（moneyline + totals）
"""

import math
import os
import sys
import sqlite3
import unicodedata
import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from config import BBALL_SIGMA_BREF, BBALL_SIGMA_PACE, NBA_HOME_ADV_PTS
except ImportError:
    BBALL_SIGMA_BREF = 13.0
    BBALL_SIGMA_PACE = 14.0
    NBA_HOME_ADV_PTS = 2.5

DB_PATH       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sports_data.db")
RUN_TAG       = "bball_elo_v1"
ELO_K         = 20
ELO_HOME      = 100   # 篮球主场优势比足球更大
ELO_INIT      = 1500
HOME_WIN_BASE = 0.57  # 职业篮球主场胜率基准（无历史数据时用）
W_BREF        = 0.60  # Pace/ORtg/DRtg 融合权重（两模型均有时）
W_ELO         = 0.40  # ELO 融合权重


# ─── 工具 ─────────────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    for s in [" w", " women", " bc", " bk", " basketball"]:
        if name.endswith(s):
            name = name[: -len(s)]
    return re.sub(r"\s+", " ", name).strip()


class _NameIndex:
    def __init__(self, names: set):
        self._norm_map = {_norm(n): n for n in names}
        self._cache: dict = {}

    def match(self, query: str, threshold: float = 0.72) -> str | None:
        if not query:
            return None
        nq = _norm(query)
        if nq in self._norm_map:
            return self._norm_map[nq]
        if nq in self._cache:
            return self._cache[nq]
        best_score, best = 0.0, None
        for nc, orig in self._norm_map.items():
            s = SequenceMatcher(None, nq, nc).ratio()
            if s > best_score:
                best_score, best = s, orig
        result = best if best_score >= threshold else None
        self._cache[nq] = result
        return result


# ─── ELO 模型 ─────────────────────────────────────────────────────────────────

def _build_elo(matches: list) -> tuple[dict, _NameIndex]:
    ratings: dict = defaultdict(lambda: ELO_INIT)

    for m in sorted(matches, key=lambda x: x["date"]):
        h, a, hs, as_ = m["home"], m["away"], m["hs"], m["as"]
        rh = ratings[h] + ELO_HOME
        ra = ratings[a]
        exp_h = 1 / (1 + 10 ** ((ra - rh) / 400))
        sh = 1.0 if hs > as_ else 0.0
        sa = 1.0 - sh

        pt_diff = abs(hs - as_)
        km = 1.0 if pt_diff <= 5 else (1.2 if pt_diff <= 15 else 1.5)

        ratings[h] += ELO_K * km * (sh - exp_h)
        ratings[a] += ELO_K * km * (sa - (1 - exp_h))

    rd = dict(ratings)
    return rd, _NameIndex(set(rd.keys()))


def _elo_win_prob(home: str, away: str,
                  ratings: dict, idx: _NameIndex) -> tuple[float | None, str]:
    """返回 (p_home, engine) 或 (None, '') 当无任何 ELO 数据"""
    # 2026-07-29修复：_norm()对中文队名ascii-only编码会丢字符变空串，
    # 见00_命中系统.py get_fotmob_shots_probs()同一处说明
    try:
        from team_mapping import team_en
        home, away = team_en(home), team_en(away)
    except Exception:
        pass
    hk = idx.match(home)
    ak = idx.match(away)

    if hk and ak:
        rh = ratings[hk] + ELO_HOME
        ra = ratings[ak]
        ph = 1 / (1 + 10 ** ((ra - rh) / 400))
        return ph, "elo"

    if hk or ak:
        rh = (ratings.get(hk, ELO_INIT) if hk else ELO_INIT) + ELO_HOME
        ra = ratings.get(ak, ELO_INIT) if ak else ELO_INIT
        ph = 1 / (1 + 10 ** ((ra - rh) / 400))
        return ph, "elo_partial"

    return None, ""


# ─── Pace/ORtg/DRtg 模型 ──────────────────────────────────────────────────────

def _bref_ratings(team: str, conn) -> dict | None:
    """从 bballref_team_stats 查询球队赛季效率数据，模糊匹配"""
    # 2026-07-29修复：bballref_team_stats存英文NBA队名，qiety_yb/okooo_jingcai
    # 中文展示名直接LIKE匹配配不上，见00_命中系统.py get_fotmob_shots_probs()同一处说明
    try:
        from team_mapping import team_en
        team = team_en(team)
    except Exception:
        pass
    for chars in [5, 3]:
        try:
            row = conn.execute(
                "SELECT ortg, drtg, pace, nrtg FROM bballref_team_stats "
                "WHERE team LIKE ? ORDER BY season DESC LIMIT 1",
                (f"%{team[:chars]}%",)
            ).fetchone()
            if row and row[0]:
                return {
                    "ortg": float(row[0]),
                    "drtg": float(row[1]),
                    "pace": float(row[2]) if row[2] else 100.0,
                    "nrtg": float(row[3]) if row[3] else 0.0,
                }
        except Exception:
            pass
    return None


def _pace_predict(home: str, away: str, conn) -> tuple[float, float, float] | None:
    """
    ORtg/DRtg/Pace → (p_home, p_away, exp_total)
    公式：exp_pts = (ortg_attack + opp_drtg) / 2 × avg_pace / 100
    胜负：正态分布 CDF(margin / sigma)
    """
    hr = _bref_ratings(home, conn)
    ar = _bref_ratings(away, conn)
    if not hr or not ar:
        return None

    avg_pace = (hr["pace"] + ar["pace"]) / 2
    exp_home = (hr["ortg"] + ar["drtg"]) / 2 * avg_pace / 100
    exp_away = (ar["ortg"] + hr["drtg"]) / 2 * avg_pace / 100
    margin   = (exp_home - exp_away) + NBA_HOME_ADV_PTS

    z = margin / (BBALL_SIGMA_BREF * math.sqrt(2))
    ph = min(0.95, max(0.05, 0.5 * (1 + math.erf(z))))
    exp_total = round(exp_home + exp_away, 1)
    return round(ph, 4), round(1 - ph, 4), exp_total


def _get_implied_probs(cur, uid: str, fetch_date: str, frozen_market_input=None) -> tuple | None:
    """从赔率数据获取 moneyline 隐含概率：consensus_odds → unified_odds"""
    queries = [
        ("SELECT outcome, consensus_odds FROM consensus_odds "
         "WHERE unified_id=? AND fetch_date=? AND market='moneyline'",
         (uid, fetch_date)),
        ("SELECT outcome, AVG(odds_value) FROM unified_odds "
         "WHERE unified_id=? AND fetch_date=? AND market='moneyline' GROUP BY outcome",
         (uid, fetch_date)),
    ]
    for stage, (sql, params) in enumerate(queries):
        prob_map = {}
        try:
            if frozen_market_input is None:
                odds_rows = cur.execute(sql, params).fetchall()
            else:
                entry = frozen_market_input.get(uid, {})
                if entry.get("fetch_date") != fetch_date:
                    return None
                prefix = "consensus" if stage == 0 else "unified"
                if entry.get(prefix + "_status") != "SUCCESS":
                    continue
                rows = [r for r in entry[prefix + "_rows"]
                        if r["uid"] == uid and r["fd"] == fetch_date and r["market"] == "moneyline"]
                if stage == 0:
                    odds_rows = [(r["outcome"], r["consensus"]) for r in rows]
                else:
                    grouped = {}
                    for r in rows:
                        if r["val"] is not None:
                            grouped.setdefault(r["outcome"], []).append(r["val"])
                    odds_rows = [(outcome, sum(values) / len(values))
                                 for outcome, values in grouped.items()]
            for outcome, odds in odds_rows:
                if odds and odds > 1:
                    prob_map[outcome] = 1.0 / odds
        except Exception:
            continue
        if "home" in prob_map and "away" in prob_map:
            total = prob_map["home"] + prob_map["away"]
            ph = round(prob_map["home"] / total, 4)
            if 0.05 < ph < 0.95:
                return ph, round(1 - ph, 4)
    return None


# ─── 主入口 ───────────────────────────────────────────────────────────────────

def run_predictions(fetch_date: str | None = None, *, frozen_market_input=None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n🏀 篮球预测模型启动  [{fetch_date}]", flush=True)

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur  = conn.cursor()

    # ── 加载历史比赛（NBA/WNBA）──
    cur.execute("""
        SELECT league, home_team, away_team, home_score, away_score, match_date
        FROM basketball_matches
        WHERE home_score IS NOT NULL AND status IN ('Game Finished', 'After Over Time')
    """)
    matches = [{"league": r[0], "home": r[1], "away": r[2],
                "hs": int(r[3]), "as": int(r[4]), "date": r[5]}
               for r in cur.fetchall()]
    print(f"  📚 历史比赛: {len(matches)} 场 (NBA/WNBA)", flush=True)

    elo_ratings, elo_idx = _build_elo(matches)
    print(f"  🏆 ELO: {len(elo_ratings)} 队", flush=True)

    # ── 今日篮球赛事 ──
    cur.execute("""
        SELECT unified_id, league_name, league_code, home_team_std, away_team_std,
               kickoff_utc
        FROM unified_matches
        WHERE fetch_date=? AND sport_code='basketball'
          AND status IN ('pending','scheduled','NS')
          AND home_team_std != '' AND away_team_std != ''
    """, (fetch_date,))
    fixtures = cur.fetchall()
    print(f"  🏀 今日待预测: {len(fixtures)} 场", flush=True)

    # ── 批量预测 ──
    rows  = []
    stats = defaultdict(int)
    now   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for uid, league_name, league_code, home, away, kickoff in fixtures:

        # 1. Pace/ORtg/DRtg 模型
        pace_result = _pace_predict(home, away, cur)

        # 2. ELO 模型
        elo_ph, elo_engine = _elo_win_prob(home, away, elo_ratings, elo_idx)

        # ── 融合 ──
        if pace_result and elo_ph is not None:
            bp, ba, exp_total = pace_result
            ph = round(W_BREF * bp + W_ELO * elo_ph, 4)
            engine = f"elo+pace({elo_engine.split('_')[-1]})"
        elif pace_result:
            ph, _, exp_total = pace_result
            engine = "pace_only"
        elif elo_ph is not None:
            ph, exp_total = elo_ph, None
            engine = elo_engine
        else:
            # 赔率隐含概率
            implied = _get_implied_probs(cur, uid, fetch_date, frozen_market_input)
            if implied:
                ph, exp_total = implied[0], None
                engine = "implied_odds"
            else:
                ph, exp_total = HOME_WIN_BASE, None
                engine = "default_home_adv"

        pa = round(1 - ph, 4)
        stats[engine] += 1

        conf = lambda p: "高" if p > 0.65 else ("中" if p > 0.45 else "低")

        # moneyline 行
        for outcome, prob in [("home", ph), ("away", pa)]:
            rows.append((
                uid, "basketball", league_code or "", fetch_date, kickoff or "",
                home, away, "moneyline", "full_time", "fullgame",
                outcome, None, round(prob, 6), round(1 / prob, 4),
                None, None, None, conf(prob), engine, RUN_TAG, now,
            ))

        # totals 行（有 exp_total 时写入大小球预测）
        if exp_total and exp_total > 0:
            sigma = BBALL_SIGMA_PACE * math.sqrt(2)
            for line in [210.5, 215.5, 220.5, 225.5, 230.5]:
                z = (line - exp_total) / sigma
                p_under = round(min(0.95, max(0.05, 0.5 * (1 + math.erf(z)))), 4)
                p_over  = round(1 - p_under, 4)
                for outcome, prob in [("over", p_over), ("under", p_under)]:
                    rows.append((
                        uid, "basketball", league_code or "", fetch_date, kickoff or "",
                        home, away, "totals", "over_under", "fullgame",
                        outcome, line, round(prob, 6), round(1 / prob, 4),
                        None, None, None, conf(prob), engine, RUN_TAG, now,
                    ))

    # ── 批量写入 ──
    cur.execute(
        "DELETE FROM market_prediction_snapshot "
        "WHERE match_date=? AND run_tag=? AND sport_code='basketball'",
        (fetch_date, RUN_TAG)
    )
    cur.executemany("""
        INSERT INTO market_prediction_snapshot
        (match_id_internal, sport_code, league_code, match_date, kickoff_local,
         home_team_name_std, away_team_name_std, market_group, market_type, period,
         selection_name, line_value, model_prob, fair_odds,
         offered_odds, expected_value, kelly_ratio, confidence_grade,
         result_source, run_tag, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()

    n = len([r for r in rows if r[7] == "moneyline"]) // 2
    print(f"  ✅ 预测完成: {n} 场  引擎: {dict(stats)}", flush=True)
    return n


if __name__ == "__main__":
    run_predictions(sys.argv[1] if len(sys.argv) > 1 else None)
