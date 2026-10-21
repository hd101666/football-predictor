# -*- coding: utf-8 -*-
"""
gen_jingcai.py — 竞彩足球胜平负 十四场/任选九场 预测分析 + 复式投注单生成
===========================================================================
功能：
  1. 抓取当前开售期14场竞彩足球比赛及赔率
  2. 调用融合预测模型（ELO + Poisson + xG）获取胜平负概率
  3. 竞彩返奖率修正（约70%，规范化implied概率）
  4. 64元复式自动优化（32注×2元）
     - 十四场复式：14场中选5场双覆盖 = 2^5=32注
     - 任选九场复式：top9场中5场双覆盖 = 2^5=32注
     - 自动对比EV，推荐更优方案
  5. 双格式输出：详细分析报告 + 彩票机输入代码

用法：
  python -X utf8 gen_jingcai.py
  python -X utf8 gen_jingcai.py --budget 32      # 16注×2元
  python -X utf8 gen_jingcai.py --mode 9         # 仅任选九场
  python -X utf8 gen_jingcai.py --mode 14        # 仅十四场
  python -X utf8 gen_jingcai.py --date 2026-06-26
"""

import sys, os, math, argparse, logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from itertools import product as iproduct

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL

engine = create_engine(DB_ENGINE_URL, connect_args={'timeout': 60})
log = logging.getLogger("gen_jingcai")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ─── 常量 ──────────────────────────────────────────────────────────────────────
TICKET_UNIT        = 2      # 每注2元
SPORTTERY_RETURN   = 0.70   # 竞彩返奖率约70%
WIN_CODE  = 3               # 主胜
DRAW_CODE = 1               # 平局
LOSS_CODE = 0               # 客胜

# 竞彩固定奖金参考（实际为彩池制，此为历史均值参考，仅用于EV估算）
PRIZE_14_JACKPOT  = 5_000_000   # 十四场一等奖约500万
PRIZE_14_2ND      = 50_000      # 十四场二等奖（13场）约5万
PRIZE_9_9         = 800_000     # 任选九场9中9约80万
PRIZE_9_8         = 60_000      # 任选九场8中9约6万
PRIZE_9_7         = 3_000       # 任选九场7中9约3000元

# ─── 工具函数 ──────────────────────────────────────────────────────────────────
def _fair_probs(odds_h, odds_d, odds_a):
    """竞彩赔率 → 去除税率后的公平概率"""
    raw = [1/o if o else 0 for o in (odds_h, odds_d, odds_a)]
    total = sum(raw) or 1.0
    return tuple(r / total for r in raw)


def _normalize(name: str) -> str:
    import re, unicodedata
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', n.lower())


def _fuzzy_score(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


# ─── 数据抓取 ──────────────────────────────────────────────────────────────────
def fetch_jingcai_matches(date_str: str = None, lookahead_days: int = 7) -> List[dict]:
    """
    从竞彩API抓取当前开售期足球胜平负比赛（最多14场）
    返回列表，按 match_num 排序
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=lookahead_days)).strftime("%Y-%m-%d")

    try:
        from sporttery_source import fetch_sporttery_fixtures
        fixtures = fetch_sporttery_fixtures("football", date_str, end_date)
        log.info(f"竞彩API: {len(fixtures)} 场")
        return fixtures
    except Exception as e:
        log.error(f"竞彩API失败: {e}")
        return []


def find_unified_id(home_en: str, away_en: str, league: str,
                    kickoff_date: str, home_cn: str = "", away_cn: str = "") -> Optional[str]:
    """
    在 unified_matches 中查找最匹配的 unified_id
    优先用英文队名，备用中文队名
    """
    search_names = [(home_en, away_en)]
    if home_cn:
        search_names.append((home_cn, away_cn))

    with engine.connect() as conn:
        for h_name, a_name in search_names:
            for chars in [6, 5, 4]:
                try:
                    rows = conn.execute(text("""
                        SELECT unified_id, home_team_std, away_team_std
                        FROM unified_matches
                        WHERE fetch_date BETWEEN :d0 AND :d1
                          AND home_team_std LIKE :h AND away_team_std LIKE :a
                          AND sport_code IN ('football','soccer','Soccer')
                        LIMIT 5
                    """), {
                        "d0": kickoff_date,
                        "d1": kickoff_date,
                        "h": f"%{h_name[:chars]}%",
                        "a": f"%{a_name[:chars]}%",
                    }).fetchall()
                    if rows:
                        # 返回最佳模糊匹配
                        best = max(rows, key=lambda r: (
                            _fuzzy_score(h_name, r[1]) + _fuzzy_score(a_name, r[2])
                        ))
                        if (_fuzzy_score(h_name, best[1]) + _fuzzy_score(a_name, best[2])) > 0.6:
                            return best[0]
                except Exception:
                    continue
    return None


# ─── 预测模型调用 ──────────────────────────────────────────────────────────────
def get_jingcai_probs(fixture: dict) -> dict:
    """
    获取单场竞彩比赛的融合概率
    返回: {
        'p_home': float, 'p_draw': float, 'p_away': float,
        'fair_home': float, 'fair_draw': float, 'fair_away': float,
        'edge_home': float, 'edge_draw': float, 'edge_away': float,
        'best_outcome': int, 'confidence': float,
        'engine': str, 'unified_id': str
    }
    """
    home_en  = fixture.get("home_team_en") or fixture.get("home_team", "")
    away_en  = fixture.get("away_team_en") or fixture.get("away_team", "")
    home_cn  = fixture.get("home_team_abbr", "")
    away_cn  = fixture.get("away_team_abbr", "")
    league   = fixture.get("league_name", "")
    match_dt = fixture.get("match_date", datetime.now().strftime("%Y-%m-%d"))

    odds_h = fixture.get("odds_1x2_home")
    odds_d = fixture.get("odds_1x2_draw")
    odds_a = fixture.get("odds_1x2_away")

    # 公平概率（竞彩返奖率归一化）
    if odds_h and odds_d and odds_a:
        fair_h, fair_d, fair_a = _fair_probs(odds_h, odds_d, odds_a)
    else:
        fair_h, fair_d, fair_a = 0.45, 0.28, 0.27

    # 尝试找 unified_id
    uid = find_unified_id(home_en, away_en, league, match_dt, home_cn, away_cn)

    # 构建 book_probs
    book_probs = {}
    if odds_h:
        book_probs["home"]  = fair_h
        book_probs["draw"]  = fair_d
        book_probs["away"]  = fair_a
        book_probs["over"]  = 0.50
        book_probs["under"] = 0.50

    # 调用融合模型
    p_fused = {}
    engine_used = "book_only"
    try:
        from 命中系统 import get_model_probs as _gmp
        p_fused = _gmp(uid or "", home_en, away_en,
                       league_name=league, sport_code="Soccer",
                       book_probs=book_probs)
        engine_used = "fusion"
    except Exception:
        pass

    if not p_fused:
        # 降级：直接用xG/ELO函数
        try:
            from 命中系统 import (get_xg_model_probs, get_fbref_xg_probs,
                                   get_football_xg_stats_probs, get_national_team_probs)
            for fn in [get_xg_model_probs, get_fbref_xg_probs, get_football_xg_stats_probs]:
                r = fn(home_en, away_en, league)
                if r and r.get("home"):
                    p_fused = r
                    engine_used = fn.__name__
                    break
        except Exception:
            pass

    if not p_fused:
        # 最后兜底：竞彩公平概率
        p_fused = {"home": fair_h, "draw": fair_d, "away": fair_a}
        engine_used = "sporttery_fair"

    p_h = p_fused.get("home", fair_h)
    p_d = p_fused.get("draw", fair_d)
    p_a = p_fused.get("away", fair_a)

    # 规范化（确保和=1）
    s = (p_h + p_d + p_a) or 1.0
    p_h, p_d, p_a = p_h/s, p_d/s, p_a/s

    # 价值边际
    edge_h = p_h - fair_h
    edge_d = p_d - fair_d
    edge_a = p_a - fair_a

    # 最优方向
    best_p = max(p_h, p_d, p_a)
    if p_h >= p_d and p_h >= p_a:
        best_outcome = WIN_CODE
    elif p_d >= p_h and p_d >= p_a:
        best_outcome = DRAW_CODE
    else:
        best_outcome = LOSS_CODE

    return {
        "p_home": round(p_h, 4), "p_draw": round(p_d, 4), "p_away": round(p_a, 4),
        "fair_home": round(fair_h, 4), "fair_draw": round(fair_d, 4), "fair_away": round(fair_a, 4),
        "edge_home": round(edge_h, 4), "edge_draw": round(edge_d, 4), "edge_away": round(edge_a, 4),
        "best_outcome": best_outcome, "confidence": round(best_p, 4),
        "engine": engine_used, "unified_id": uid or "",
        "odds_h": odds_h, "odds_d": odds_d, "odds_a": odds_a,
    }


# ─── 复式优化器 ────────────────────────────────────────────────────────────────
def _outcome_label(code: int) -> str:
    return {WIN_CODE: "主胜", DRAW_CODE: "平局", LOSS_CODE: "客胜"}.get(code, "?")


def _sorted_outcomes(probs: dict) -> List[Tuple[float, int]]:
    """返回 [(概率, 代码), ...] 降序排列"""
    return sorted([
        (probs["p_home"], WIN_CODE),
        (probs["p_draw"], DRAW_CODE),
        (probs["p_away"], LOSS_CODE),
    ], reverse=True)


def _p_correct_single(probs: dict, selections: List[int]) -> float:
    """选定方向组合的命中概率之和"""
    mapping = {WIN_CODE: probs["p_home"], DRAW_CODE: probs["p_draw"], LOSS_CODE: probs["p_away"]}
    return sum(mapping.get(s, 0) for s in selections)


def optimize_fuzhui(fixtures_with_probs: List[dict], budget: int = 64,
                    mode: str = "auto") -> dict:
    """
    复式票据优化器
    返回:
        {
          'sel_14':  {match_num: [codes...]},  # 十四场方案
          'combos_14': int,
          'sel_9':   {match_num: [codes...]},  # 任选九场方案
          'combos_9': int,
          'chosen_9': [match_nums],            # 任选九场选中的9场
          'recommended': '14场' | '9场',
          'ev_14': float, 'ev_9': float,
          'p_hit_14': float, 'p_hit_9': float,
        }
    """
    max_combos = budget // TICKET_UNIT  # 32注

    # 按置信度降序排列（置信度 = 最优方向概率）
    ranked = sorted(fixtures_with_probs, key=lambda x: x["probs"]["confidence"], reverse=True)
    ranked_nums = [x["match_num"] for x in ranked]

    # ── 构建十四场复式 ──
    sel_14, combos_14 = _build_selections(ranked, max_combos, n_matches=14)

    # ── 构建任选九场复式（选最有把握的9场） ──
    top9 = ranked[:9]
    sel_9, combos_9 = _build_selections(top9, max_combos, n_matches=9)
    chosen_9 = [x["match_num"] for x in top9]

    # ── EV 和命中率估算 ──
    p_hit_14 = _calc_p_hit_all(ranked, sel_14)
    p_hit_9  = _calc_p_hit_all(top9, sel_9)

    # 期望奖金（简化估算）
    ev_14 = (
        p_hit_14 * PRIZE_14_JACKPOT
        + _calc_p_hit_n(ranked, sel_14, 13) * PRIZE_14_2ND
    ) / max(combos_14, 1) / TICKET_UNIT - 1  # EV per 2元

    # 任选九场：9场全对 + 8场对 + 7场对
    p9_9 = p_hit_9
    p9_8 = _calc_p_hit_exactly_n(top9, sel_9, 8)
    p9_7 = _calc_p_hit_exactly_n(top9, sel_9, 7)
    ev_9 = (
        p9_9 * PRIZE_9_9 + p9_8 * PRIZE_9_8 + p9_7 * PRIZE_9_7
    ) / max(combos_9, 1) / TICKET_UNIT - 1

    recommended = "9场" if (mode == "9" or (mode != "14" and ev_9 >= ev_14)) else "14场"

    return {
        "sel_14": sel_14, "combos_14": combos_14,
        "sel_9": sel_9,   "combos_9": combos_9,
        "chosen_9": chosen_9,
        "recommended": recommended,
        "ev_14": round(ev_14, 4), "ev_9": round(ev_9, 4),
        "p_hit_14": round(p_hit_14, 8), "p_hit_9": round(p_hit_9, 6),
        "p9_9": round(p9_9, 6), "p9_8": round(p9_8, 6), "p9_7": round(p9_7, 6),
    }


def _build_selections(ranked: List[dict], max_combos: int, n_matches: int) -> Tuple[dict, int]:
    """
    从 ranked（按置信度降序） 中选 n_matches 场，
    以最低置信场次优先加第二方向，直到总注数 ≤ max_combos。
    返回 {match_num: [codes]}, actual_combos
    """
    # 只操作 n_matches 场
    pool = ranked[:n_matches]

    # 初始：每场只选最优方向（单注）
    selections = {x["match_num"]: [x["probs"]["best_outcome"]] for x in pool}
    combos = 1

    # 从置信度最低的场次开始扩展
    for m in reversed(pool):
        if combos >= max_combos:
            break
        mn = m["match_num"]
        sorted_oc = _sorted_outcomes(m["probs"])

        # 加第二方向（double）
        if len(selections[mn]) == 1 and combos * 2 <= max_combos:
            selections[mn].append(sorted_oc[1][1])
            combos *= 2
        # 加第三方向（triple，需满足3倍空间）
        elif len(selections[mn]) == 2 and combos * 3 // 2 <= max_combos:
            selections[mn].append(sorted_oc[2][1])
            combos = combos * 3 // 2

    return selections, combos


def _calc_p_hit_all(matches: List[dict], selections: dict) -> float:
    """所有场次全中概率"""
    p = 1.0
    for m in matches:
        mn = m["match_num"]
        sels = selections.get(mn, [m["probs"]["best_outcome"]])
        p *= _p_correct_single(m["probs"], sels)
    return p


def _calc_p_hit_n(matches: List[dict], selections: dict, n: int) -> float:
    """恰好命中 ≥ n 场的概率（简化：二项分布近似）"""
    probs = [_p_correct_single(m["probs"], selections.get(m["match_num"], [m["probs"]["best_outcome"]]))
             for m in matches]
    total = len(probs)
    # 递推
    dp = [0.0] * (total + 1)
    dp[0] = 1.0
    for p in probs:
        for k in range(total, 0, -1):
            dp[k] = dp[k] * (1 - p) + dp[k-1] * p
    return sum(dp[k] for k in range(n, total + 1))


def _calc_p_hit_exactly_n(matches: List[dict], selections: dict, n: int) -> float:
    """恰好命中 n 场的概率"""
    probs = [_p_correct_single(m["probs"], selections.get(m["match_num"], [m["probs"]["best_outcome"]]))
             for m in matches]
    total = len(probs)
    dp = [0.0] * (total + 1)
    dp[0] = 1.0
    for p in probs:
        new_dp = [0.0] * (total + 1)
        for k in range(total + 1):
            if dp[k] == 0:
                continue
            if k < total:
                new_dp[k+1] += dp[k] * p
            new_dp[k] += dp[k] * (1 - p)
        dp = new_dp
    return dp[n] if n <= total else 0.0


# ─── 输出格式 ──────────────────────────────────────────────────────────────────
def _tw(s: str, w: int) -> str:
    """中文截断+填充到显示宽度 w"""
    result, cur = "", 0
    for ch in str(s):
        cw = 2 if ord(ch) > 127 else 1
        if cur + cw > w:
            break
        result += ch; cur += cw
    return result + " " * (w - cur)


def format_analysis(fixtures_with_probs: List[dict], result: dict,
                    budget: int = 64) -> str:
    """生成详细分析报告"""
    lines = []
    W = 108
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    lines.append("=" * W)
    lines.append(f"  🎯  竞彩足球胜平负分析报告  [{now_bj} 北京时间]")
    lines.append("=" * W)
    lines.append(f"  {'序':>3}  {'开赛时间':<12} {'联赛':<8} {'主队':<12} {'客队':<12} "
                 f"{'主胜%':>6} {'平局%':>6} {'客胜%':>6} "
                 f"{'主赔':>5} {'平赔':>5} {'客赔':>5} "
                 f"{'推荐':>5} {'置信':>5} {'引擎':<12}")
    lines.append("-" * W)

    for item in fixtures_with_probs:
        f = item["fixture"]
        p = item["probs"]
        mn = item["match_num"]

        # 时间
        mt = f.get("match_time", "")
        md = f.get("match_date", "")
        if mt and md:
            try:
                dt = datetime.strptime(f"{md} {mt}", "%Y-%m-%d %H:%M")
                time_str = dt.strftime("%m/%d %H:%M")
            except Exception:
                time_str = f"{md[-5:]} {mt}"
        else:
            time_str = md[-5:] if md else "--/--"

        league   = _tw(f.get("league_name_cn") or f.get("league_name", ""), 8)
        home     = _tw(f.get("home_team_abbr") or f.get("home_team", "")[:8], 12)
        away     = _tw(f.get("away_team_abbr") or f.get("away_team", "")[:8], 12)
        rec_str  = _outcome_label(p["best_outcome"])

        # 在十四场方案中的选择
        sel_14 = result["sel_14"].get(mn, [p["best_outcome"]])
        sel14_str = "+".join(_outcome_label(s) for s in sorted(sel_14, reverse=True))

        lines.append(
            f"  [{mn}]  {time_str:<12} {league}{home}{away}"
            f"  {p['p_home']*100:>5.1f}% {p['p_draw']*100:>5.1f}% {p['p_away']*100:>5.1f}%"
            f"  {(p['odds_h'] or 0):>5.2f} {(p['odds_d'] or 0):>5.2f} {(p['odds_a'] or 0):>5.2f}"
            f"  {_tw(rec_str, 4)}{p['confidence']*100:>4.0f}%  {p['engine']}"
        )

    lines.append("-" * W)

    # 推荐方案
    rec  = result["recommended"]
    lines.append("")
    lines.append(f"  📊 推荐方案: {'任选九场' if rec=='9场' else '十四场'} 复式")
    lines.append(f"  预算: {budget}元 = {budget//TICKET_UNIT}注×{TICKET_UNIT}元")
    lines.append("")

    if rec == "9场" or True:  # 始终显示两个方案
        lines.append(f"  ── 方案A：任选九场复式（{result['combos_9']}注×{TICKET_UNIT}元"
                     f" = {result['combos_9']*TICKET_UNIT}元）──")
        lines.append(f"     选中场次: {', '.join(result['chosen_9'])}")
        for mn, sels in sorted(result['sel_9'].items()):
            if mn not in result["chosen_9"]:
                continue
            fp = next((x for x in fixtures_with_probs if x["match_num"] == mn), None)
            if fp:
                sel_str = " / ".join(_outcome_label(s) for s in sorted(sels, reverse=True))
                lines.append(f"     [{mn}] {_tw(fp['fixture'].get('home_team_abbr',''),8)}"
                             f"vs{_tw(fp['fixture'].get('away_team_abbr',''),8)}  → {sel_str}")
        lines.append(f"     全中概率: {result['p9_9']*100:.4f}%  EV/元: {result['ev_9']:+.3f}")
        lines.append("")

        lines.append(f"  ── 方案B：十四场复式（{result['combos_14']}注×{TICKET_UNIT}元"
                     f" = {result['combos_14']*TICKET_UNIT}元）──")
        for mn, sels in sorted(result['sel_14'].items()):
            fp = next((x for x in fixtures_with_probs if x["match_num"] == mn), None)
            if fp:
                sel_str = " / ".join(_outcome_label(s) for s in sorted(sels, reverse=True))
                marker = "*" if len(sels) > 1 else " "
                lines.append(f"  {marker}  [{mn}] {_tw(fp['fixture'].get('home_team_abbr',''),8)}"
                             f"vs{_tw(fp['fixture'].get('away_team_abbr',''),8)}  → {sel_str}")
        lines.append(f"     全中概率: {result['p_hit_14']*100:.6f}%  EV/元: {result['ev_14']:+.3f}")

    lines.append("")
    lines.append("=" * W)
    lines.append(f"  推荐: {'任选九场' if rec=='9场' else '十四场'}（EV更高）  "
                 f"  9场EV={result['ev_9']:+.3f}  14场EV={result['ev_14']:+.3f}")
    lines.append("=" * W)

    return "\n".join(lines)


def format_ticket_code(fixtures_with_probs: List[dict], result: dict) -> str:
    """
    生成彩票机可直接输入的格式
    十四场格式: 001→3  002→31  003→1 ...  (3=主胜, 1=平, 0=客胜)
    任选九场格式: 选中场次的编码
    """
    lines = []
    lines.append("\n" + "─" * 60)
    lines.append("  【彩票机输入代码】")
    lines.append("─" * 60)

    # 十四场
    lines.append("  ▶ 十四场复式（直接勾选）：")
    ticket_14 = []
    for mn in sorted(result["sel_14"].keys()):
        sels = result["sel_14"][mn]
        code_str = "".join(str(s) for s in sorted(sels, reverse=True))
        ticket_14.append(f"{mn}→{code_str}")
    lines.append("    " + "  ".join(ticket_14))
    lines.append(f"    注数: {result['combos_14']}注  金额: {result['combos_14']*TICKET_UNIT}元")

    # 任选九场
    lines.append("")
    lines.append("  ▶ 任选九场复式（选中场次）：")
    ticket_9 = []
    for mn in sorted(result["chosen_9"]):
        sels = result["sel_9"].get(mn, [])
        code_str = "".join(str(s) for s in sorted(sels, reverse=True))
        ticket_9.append(f"{mn}→{code_str}")
    lines.append("    " + "  ".join(ticket_9))
    lines.append(f"    注数: {result['combos_9']}注  金额: {result['combos_9']*TICKET_UNIT}元")
    lines.append("─" * 60)

    lines.append(f"\n  ★ 推荐方案: {'任选九场' if result['recommended']=='9场' else '十四场'}")
    return "\n".join(lines)


# ─── 写库 ──────────────────────────────────────────────────────────────────────
def save_to_db(fixtures_with_probs: List[dict], result: dict,
               fetch_date: str, issue: str = "") -> None:
    """将竞彩投注方案写入 jingcai_tickets 表"""
    import json as _json
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # 建表
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS jingcai_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_date TEXT,
                issue TEXT,
                mode TEXT,
                match_num TEXT,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                kickoff TEXT,
                selections TEXT,
                p_home REAL, p_draw REAL, p_away REAL,
                confidence REAL,
                recommended INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                actual_result TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("DELETE FROM jingcai_tickets WHERE fetch_date=:fd"), {"fd": fetch_date})

        recommended_mode = result["recommended"]
        sel_map = result["sel_9"] if recommended_mode == "9场" else result["sel_14"]
        chosen = result.get("chosen_9") if recommended_mode == "9场" else None

        for item in fixtures_with_probs:
            mn = item["match_num"]
            is_chosen = (chosen is None) or (mn in chosen)
            if not is_chosen:
                continue
            sels = sel_map.get(mn, [item["probs"]["best_outcome"]])
            f = item["fixture"]
            conn.execute(text("""
                INSERT INTO jingcai_tickets
                (fetch_date, issue, mode, match_num, league, home_team, away_team,
                 kickoff, selections, p_home, p_draw, p_away, confidence,
                 recommended, status, created_at)
                VALUES (:fd, :issue, :mode, :mn, :lg, :h, :a,
                        :ko, :sel, :ph, :pd, :pa, :conf, :rec, 'pending', :now)
            """), {
                "fd": fetch_date, "issue": issue, "mode": recommended_mode,
                "mn": mn, "lg": f.get("league_name", ""),
                "h": f.get("home_team_abbr", f.get("home_team", "")),
                "a": f.get("away_team_abbr", f.get("away_team", "")),
                "ko": f.get("match_datetime", ""),
                "sel": _json.dumps(sels),
                "ph": item["probs"]["p_home"], "pd": item["probs"]["p_draw"],
                "pa": item["probs"]["p_away"], "conf": item["probs"]["confidence"],
                "rec": 1 if is_chosen else 0,
                "now": now,
            })
    log.info(f"  ✅ 竞彩投注方案已写库: {fetch_date} ({recommended_mode})")


# ─── 主入口 ────────────────────────────────────────────────────────────────────
def run(date_str: str = None, budget: int = 64, mode: str = "auto",
        no_db: bool = False) -> None:
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print("=" * 72)
    print(f"  竞彩足球胜平负分析  [{date_str}]  预算={budget}元")
    print("=" * 72)

    # 1. 抓取当前开售期比赛
    fixtures = fetch_jingcai_matches(date_str)

    if not fixtures:
        print(f"\n  ⚠ 竞彩API无数据（API超时/无开售比赛）")
        print(f"  提示：竞彩API仅在中国大陆IP可访问，请确认网络环境")
        print(f"  如需手动录入比赛，请编辑 _jingcai_manual.json 后重新运行")
        _create_manual_template(date_str)
        return

    # 只取胜平负比赛（has odds_1x2）
    jc_matches = [f for f in fixtures if f.get("odds_1x2_home")]
    if len(jc_matches) > 14:
        jc_matches = jc_matches[:14]

    print(f"  共 {len(jc_matches)} 场竞彩足球胜平负比赛")

    if len(jc_matches) < 9:
        print(f"  ⚠ 有效比赛数 < 9，无法生成任选九场方案（需至少9场）")
        if len(jc_matches) < 1:
            return

    # 2. 为每场比赛获取融合概率
    fixtures_with_probs = []
    for idx, f in enumerate(jc_matches, 1):
        mn = f.get("match_num") or f"%03d" % idx
        probs = get_jingcai_probs(f)
        fixtures_with_probs.append({"match_num": mn, "fixture": f, "probs": probs})
        print(f"  [{mn}] {f.get('home_team_abbr','')} vs {f.get('away_team_abbr','')}  "
              f"主={probs['p_home']:.3f} 平={probs['p_draw']:.3f} 客={probs['p_away']:.3f}  "
              f"({probs['engine']})")

    # 3. 复式优化
    result = optimize_fuzhui(fixtures_with_probs, budget=budget, mode=mode)

    # 4. 输出
    analysis = format_analysis(fixtures_with_probs, result, budget)
    ticket   = format_ticket_code(fixtures_with_probs, result)
    print(analysis)
    print(ticket)

    # 5. 写库
    if not no_db:
        save_to_db(fixtures_with_probs, result, date_str)

    # 6. 保存到桌面
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        ts = datetime.now().strftime("%H%M")
        fp = os.path.join(desktop, f"竞彩_{date_str}_{ts}.txt")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(analysis + "\n" + ticket + "\n")
        print(f"\n  📄 分析报告已保存: {fp}")
    except Exception as e:
        log.warning(f"桌面保存失败: {e}")


def _create_manual_template(date_str: str) -> None:
    """创建手动录入模板文件"""
    import json as _json
    tmpl_path = os.path.join(_SCRIPT_DIR, "_jingcai_manual.json")
    if os.path.exists(tmpl_path):
        return
    template = {
        "_说明": "手动录入竞彩比赛，填好后重新运行 gen_jingcai.py",
        "date": date_str,
        "matches": [
            {
                "match_num": "001",
                "league_name": "England Premier League",
                "league_name_cn": "英超",
                "home_team": "Manchester City",
                "home_team_abbr": "曼城",
                "home_team_en": "Manchester City",
                "away_team": "Arsenal",
                "away_team_abbr": "阿森纳",
                "away_team_en": "Arsenal",
                "match_date": date_str,
                "match_time": "20:00",
                "match_datetime": f"{date_str} 20:00",
                "odds_1x2_home": 2.10,
                "odds_1x2_draw": 3.50,
                "odds_1x2_away": 3.20,
                "status": "NS"
            }
        ]
    }
    with open(tmpl_path, "w", encoding="utf-8") as f:
        _json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"  📝 手动录入模板已创建: {tmpl_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="竞彩足球胜平负 复式投注单生成")
    parser.add_argument("--date",   type=str, default=None, help="日期 YYYY-MM-DD")
    parser.add_argument("--budget", type=int, default=64,   help="预算（元，默认64）")
    parser.add_argument("--mode",   type=str, default="auto",
                        choices=["auto", "9", "14"], help="投注模式")
    parser.add_argument("--no-db",  action="store_true",    help="不写数据库")
    args = parser.parse_args()
    run(date_str=args.date, budget=args.budget, mode=args.mode, no_db=args.no_db)
