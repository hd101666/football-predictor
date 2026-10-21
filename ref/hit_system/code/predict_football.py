"""
足球独立预测模型 v2
===================
双引擎架构：
  1. 泊松进球模型  - 有≥10场历史数据时使用
  2. ELO 评分模型  - 数据不足时降级使用

优化：批量写入、预构建名称索引、缓存模糊匹配结果
"""

import math
import os
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from scipy.stats import poisson as scipy_poisson
from scipy.stats import skellam as scipy_skellam
from scipy.optimize import brentq

DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sports_data.db")
RUN_TAG  = "poisson_elo_v1"
N_GOALS  = 8
ELO_K    = 32
ELO_HOME = 60
ELO_INIT = 1500
MIN_POISSON_GAMES        = 5   # 降低至5场支持亚洲/南美稀疏联赛
MIN_POISSON_GAMES_SPARSE = 3   # 极稀疏兜底（仅用于新兴联赛）
FORM_DECAY               = 0.06  # 指数衰减系数（每场递减6%，约10场后权重减半）

# Dixon-Coles 低比分相关性修正
DC_RHO_DEFAULT = -0.10   # 文献典型值，MLE拟合失败/数据不足时的兜底
DC_RHO_BOUNDS  = (-0.30, 0.30)
DC_FIT_SAMPLE  = 8000    # 拟合rho用的历史比赛采样上限（速度考虑，不影响准确性——rho只由低比分格贡献似然）
DC_FIT_MIN_N   = 200     # 采样有效样本低于此数就放弃拟合，用默认值
DC_RHO         = DC_RHO_DEFAULT  # 运行时由 _fit_dc_rho() 覆盖（run_predictions 入口处）

# league_name 关键词 → Poisson league_key 映射（按优先级排列，长词在前防止短词覆盖）
LEAGUE_NAME_MAP = {
    # 英格兰
    "premier league":     "premier_league",
    "championship":       "championship",
    "league one":         "league_one",
    "league two":         "league_two",
    "national league":    "national_league_eng",
    # 西班牙
    "la liga 2":          "laliga_2",
    "laliga":             "laliga",
    "la liga":            "laliga",
    # 德国
    "bundesliga 2":       "bundesliga_2",
    "2. bundesliga":      "bundesliga_2",
    "bundesliga":         "bundesliga",
    # 意大利
    "serie b":            "serie_b",
    "serie a br":         "serie_a_br",
    "serie a":            "serie_a",
    # 法国
    "ligue 2":            "ligue_2",
    "ligue 1":            "ligue_1",
    # 荷兰
    "eredivisie":         "eredivisie",
    # 葡萄牙
    "liga portugal":      "liga_portugal",
    "primeira liga":      "liga_portugal",
    "portugal":           "liga_portugal",
    # 比利时
    "pro league":         "pro_league_be",
    "first division a":   "pro_league_be",
    # 土耳其
    "super lig":          "super_lig",
    # 苏格兰
    "scottish premiership": "spfl_premiership",
    "spfl":               "spfl_premiership",
    "scotland":           "spfl_premiership",
    "scottish championship": "spfl_championship",
    "scottish league one": "spfl_league_one",
    "scottish league two": "spfl_league_two",
    # 希腊
    "super league":       "super_league_gr",
    # 北欧
    "eliteserien":        "eliteserien",
    "allsvenskan":        "allsvenskan",
    "superliga":          "superliga",
    # 俄罗斯 / 东欧
    "rpl":                "rpl",
    "russia":             "rpl",
    # 亚洲
    "csl":                "csl",
    "china - super":      "csl",
    "j1":                 "j1",
    "j league":           "j1",
    "k league 1":         "k_league_1",
    # 南美
    "liga argentina":     "liga_argentina",
    "argentina - primera division": "liga_argentina",
    "brazil - serie a":   "serie_a_br",
    "brazil - serie b":   "serie_b_br",
    "brazil - serie":     "serie_a_br",
    # 北美
    "mls":                "mls",
    # 世界杯
    "world cup":          "world_cup",
    "fifa world cup":     "world_cup",
    "copa america":       "copa_america",
    "euro":               "euro",
    # 欧洲联赛杯
    "champions league":   "ucl",
    "europa league":      "uel",
    "conference league":  "uecl",
}

# football-data.co.uk 短码 → Poisson league_key（与 LEAGUE_NAME_MAP 值对齐）
FD_CODE_MAP = {
    "E0":  "premier_league",
    "E1":  "championship",
    "E2":  "league_one",
    "E3":  "league_two",
    "EC":  "national_league_eng",
    "SP1": "laliga",
    "SP2": "laliga_2",
    "D1":  "bundesliga",
    "D2":  "bundesliga_2",
    "I1":  "serie_a",
    "I2":  "serie_b",
    "F1":  "ligue_1",
    "F2":  "ligue_2",
    "N1":  "eredivisie",
    "P1":  "liga_portugal",
    "B1":  "pro_league_be",
    "SC0": "spfl_premiership",
    "SC1": "spfl_championship",
    "SC2": "spfl_league_one",
    "SC3": "spfl_league_two",
    "T1":  "super_lig",
    "G1":  "super_league_gr",
}

# Understat / FBref league_slug → Poisson league_key
SLUG_CODE_MAP = {
    "premier_league":   "premier_league",
    "bundesliga":       "bundesliga",
    "serie_a":          "serie_a",
    "ligue_1":          "ligue_1",
    "laliga":           "laliga",
    "rfpl":             "rpl",
    "england":          "premier_league",
    "germany":          "bundesliga",
    "italy":            "serie_a",
    "france":           "ligue_1",
    "spain":            "laliga",
}


def _map_league(league_name: str) -> str:
    """从 league_name 推断 football_matches 里对应的 league code"""
    ln = league_name.lower()
    for keyword, code in LEAGUE_NAME_MAP.items():
        if keyword in ln:
            return code
    return ""


# ─── 工具 ─────────────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    for s in [" fc", " sc", " cf", " ac", " bk", " sk", " fk", " if",
              " city", " united", " town", " sporting", " athletic",
              " corners", " cards", " bookings"]:
        if name.endswith(s):
            name = name[: -len(s)]
    return re.sub(r"\s+", " ", name).strip()


class _NameIndex:
    """预构建归一化名称索引，支持 O(1) 精确匹配 + 缓存模糊匹配"""

    def __init__(self, names: set):
        self._orig = list(names)
        self._norm_map = {_norm(n): n for n in names}   # norm → orig
        self._cache: dict[str, str | None] = {}

    def match(self, query: str, threshold: float = 0.70) -> str | None:
        if not query:
            return None
        nq = _norm(query)
        # 精确归一化匹配
        if nq in self._norm_map:
            return self._norm_map[nq]
        # 缓存命中
        if nq in self._cache:
            return self._cache[nq]
        # 模糊匹配
        best_score, best = 0.0, None
        for nc, orig in self._norm_map.items():
            s = SequenceMatcher(None, nq, nc).ratio()
            if s > best_score:
                best_score, best = s, orig
        result = best if best_score >= threshold else None
        self._cache[nq] = result
        return result


# ─── 泊松模型 ─────────────────────────────────────────────────────────────────

def _dc_tau(x: int, y: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Dixon-Coles(1997) 低比分相关性修正因子，仅对 (0,0)/(0,1)/(1,0)/(1,1) 四格生效，其余恒为1。
    修正独立泊松假设下被系统性低估的 0-0/1-1 与被高估的 1-0/0-1。"""
    if x == 0 and y == 0:
        return 1.0 - lam_h * lam_a * rho
    if x == 0 and y == 1:
        return 1.0 + lam_h * rho
    if x == 1 and y == 0:
        return 1.0 + lam_a * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _dc_score_grid(lh: float, la: float, rho: float = None, n: int = N_GOALS):
    """返回 Dixon-Coles 修正后、归一化的联合比分概率矩阵 grid[i][j] = P(主队i球, 客队j球)"""
    if rho is None:
        rho = DC_RHO
    ph = [scipy_poisson.pmf(i, lh) for i in range(n + 1)]
    pa = [scipy_poisson.pmf(j, la) for j in range(n + 1)]
    grid = [[0.0] * (n + 1) for _ in range(n + 1)]
    total = 0.0
    for i in range(n + 1):
        for j in range(n + 1):
            p = max(ph[i] * pa[j] * _dc_tau(i, j, lh, la, rho), 0.0)
            grid[i][j] = p
            total += p
    total = total or 1.0
    for i in range(n + 1):
        for j in range(n + 1):
            grid[i][j] /= total
    return grid


def _fit_dc_rho(matches: list, poisson_params: dict, global_params: dict) -> float:
    """全局MLE拟合Dixon-Coles rho：team-strength(lam_h/lam_a)已由现有加权泊松参数固定，
    rho只出现在tau修正项里，泊松pmf本身与rho无关，因此似然函数只需对低比分格的tau求和最大化。"""
    import random as _random
    sample = matches if len(matches) <= DC_FIT_SAMPLE else _random.sample(matches, DC_FIT_SAMPLE)

    obs = []  # [(hs, as, lam_h, lam_a)]
    for m in sample:
        lp = poisson_params.get(m["league"]) or global_params
        if not lp:
            continue
        r = _poisson_predict(m["home"], m["away"], lp)
        if not r:
            continue
        obs.append((m["hs"], m["as"], r["lam_h"], r["lam_a"]))

    # Bug修复(2026-07-22)：tau修正只对(0,0)/(0,1)/(1,0)/(1,1)四格生效，其余恒为1
    # （见_dc_tau()文档字符串本身的说明），意味着比分不在这四格内的比赛对rho的
    # 似然贡献恒为log(1)=0，本不该参与MLE。但下面_neg_loglik()原来对全部obs都算
    # tau，用min(hs,1)/min(as_,1)把比分强行夹到0/1——等于把一场真实3-2的比赛当成
    # "1-1"去算tau，用一个假的(1,1)格观测污染了真正1-1比赛的似然贡献。实测这类
    # "至少一方进2+球"的比赛占样本63.4%(3645场里2311场)，意味着原来63%的"观测"
    # 其实是被误归类的假数据，会把rho拟合结果往两个方向都可能带偏(取决于当期
    # 数据里高比分/真1-1比分的比例)。改成只保留真正0/1比分的比赛参与MLE，
    # 其余比赛按理论直接跳过(它们对rho确实没有信息量，不是丢弃有效数据)。
    obs = [(hs, as_, lh, la) for hs, as_, lh, la in obs if hs <= 1 and as_ <= 1]

    if len(obs) < DC_FIT_MIN_N:
        log_msg = f"  ⚠ Dixon-Coles拟合样本不足({len(obs)}<{DC_FIT_MIN_N})，用默认 rho={DC_RHO_DEFAULT}"
        print(log_msg, flush=True)
        return DC_RHO_DEFAULT

    def _neg_loglik(rho: float) -> float:
        s = 0.0
        for hs, as_, lam_h, lam_a in obs:
            tau = _dc_tau(hs, as_, lam_h, lam_a, rho)
            s += math.log(max(tau, 1e-6))
        return -s

    try:
        from scipy.optimize import minimize_scalar
        res = minimize_scalar(_neg_loglik, bounds=DC_RHO_BOUNDS, method="bounded")
        if res.success:
            rho = float(res.x)
            print(f"  📐 Dixon-Coles rho MLE拟合: {rho:.4f}（样本{len(obs)}场）", flush=True)
            return rho
    except Exception as e:
        print(f"  ⚠ Dixon-Coles拟合异常: {e}，用默认 rho={DC_RHO_DEFAULT}", flush=True)
    return DC_RHO_DEFAULT


def _score_matrix(lh: float, la: float):
    grid = _dc_score_grid(lh, la)
    win = draw = loss = 0.0
    for i in range(N_GOALS + 1):
        for j in range(N_GOALS + 1):
            p = grid[i][j]
            if i > j:   win  += p
            elif i == j: draw += p
            else:        loss += p
    total = win + draw + loss or 1.0
    return win / total, draw / total, loss / total


def _build_poisson_params(matches: list, decay: float = FORM_DECAY) -> dict:
    """
    按联赛建立队伍攻防强度参数（指数衰减加权，近期状态权重更高）
    decay=0.06: 最近1场权重≈最近12场前的2倍，约10场后权重减半
    """
    # Group raw appearances per team per league, sorted newest-first
    by_lg_home: dict = defaultdict(lambda: defaultdict(list))  # lg→team→[(date,gf,ga)]
    by_lg_away: dict = defaultdict(lambda: defaultdict(list))
    lg_totals:  dict = defaultdict(lambda: [0.0, 0.0, 0])     # [home_g, away_g, games]

    for m in matches:
        lg, h, a = m["league"], m["home"], m["away"]
        hs, as_, dt = int(m["hs"]), int(m["as"]), (m.get("date") or "0000-00-00")
        by_lg_home[lg][h].append((dt, hs, as_))
        by_lg_away[lg][a].append((dt, as_, hs))
        lg_totals[lg][0] += hs; lg_totals[lg][1] += as_; lg_totals[lg][2] += 1

    def _weighted(appearances: list) -> tuple:
        """降序排列（最近=index 0），返回 (avg_gf, avg_ga, n_games)"""
        apps = sorted(appearances, key=lambda x: x[0], reverse=True)
        weights = [math.exp(-decay * i) for i in range(len(apps))]
        tw = sum(weights) or 1.0
        avg_gf = sum(w * gf for w, (_, gf, _) in zip(weights, apps)) / tw
        avg_ga = sum(w * ga for w, (_, _, ga) in zip(weights, apps)) / tw
        return avg_gf, avg_ga, len(apps)

    params: dict = {}
    all_lgs = set(by_lg_home.keys()) | set(by_lg_away.keys())
    for lg in all_lgs:
        lt = lg_totals[lg]
        g = lt[2] or 1
        home_avg = lt[0] / g or 1.35
        away_avg = lt[1] / g or 1.10

        all_teams = set(by_lg_home[lg].keys()) | set(by_lg_away[lg].keys())
        team_p = {}
        for team in all_teams:
            h_gf, h_ga, hg = _weighted(by_lg_home[lg].get(team, []))
            a_gf, a_ga, ag = _weighted(by_lg_away[lg].get(team, []))
            if hg == 0 and ag == 0:
                continue
            team_p[team] = {
                "ha": h_gf if hg else home_avg, "hd": h_ga if hg else away_avg, "hg": hg,
                "aa": a_gf if ag else away_avg, "ad": a_ga if ag else home_avg, "ag": ag,
            }
        params[lg] = {
            "home_avg": home_avg,
            "away_avg": away_avg,
            "teams": team_p,
            "index": _NameIndex(set(team_p.keys())),
        }
    return params


_OU_LINES = [1.5, 2.5, 3.0, 3.5, 4.5]


def _top_score_from_lambdas(lam_h: float, lam_a: float, n: int = N_GOALS) -> str:
    """计算 Dixon-Coles 修正后最可能比分，返回 'H-A' 格式字符串"""
    grid = _dc_score_grid(lam_h, lam_a, n=n)
    best_p, best_s = 0.0, "0-0"  # 初始值永不返回（循环必然覆盖），改为 0-0 避免与真实 1-1 混淆
    for i in range(n + 1):
        for j in range(n + 1):
            p = grid[i][j]
            if p > best_p:
                best_p, best_s = p, f"{i}-{j}"
    return best_s

def _ou_from_lambdas(lam_h: float, lam_a: float) -> dict:
    """Dixon-Coles 修正后的大小球概率，返回 {'over': p, 'under': p, 'over_2.5': p, ...}"""
    grid = _dc_score_grid(lam_h, lam_a)
    result = {}
    for line in _OU_LINES:
        over_p = 0.0
        for i in range(N_GOALS + 1):
            for j in range(N_GOALS + 1):
                if i + j > line:
                    over_p += grid[i][j]
        over_p = round(min(max(over_p, 0.01), 0.99), 6)
        key = str(line).replace(".0", "").replace(".", "_")
        result[f"over_{key}"]  = over_p
        result[f"under_{key}"] = round(1.0 - over_p, 6)
    # 默认键 'over'/'under' 对应 2.5 线
    result["over"]  = result["over_2_5"]
    result["under"] = result["under_2_5"]
    return result


def _poisson_predict(home: str, away: str, lp: dict):
    # 2026-07-29修复：见_elo_predict()同一处说明
    try:
        from team_mapping import team_en
        home, away = team_en(home), team_en(away)
    except Exception:
        pass
    idx: _NameIndex = lp["index"]
    teams = lp["teams"]
    hk = idx.match(home)
    ak = idx.match(away)
    if not hk or not ak:
        return None
    th, ta = teams[hk], teams[ak]
    # 亚洲/南美稀疏联赛允许低至3场，但置信度会低一些
    min_games = MIN_POISSON_GAMES_SPARSE if (th["hg"] + ta["ag"]) < 12 else MIN_POISSON_GAMES
    if th["hg"] < min_games or ta["ag"] < min_games:
        return None
    home_avg = lp["home_avg"] or 1.35
    away_avg = lp["away_avg"] or 1.10
    # Bug修复(2026-08-11)：两个归一化分母原先写反了。ta["ad"]是"客队在客场的
    # 场均失球"，它的联赛基准是"主队在主场的场均进球"=home_avg（不是away_avg）；
    # th["hd"]是"主队在主场的场均失球"，基准是away_avg（不是home_avg）。写反后
    # lam_h被放大 home_avg/away_avg≈1.27 倍、lam_a被压缩到 away_avg/home_avg≈0.79 倍，
    # 主客差被整体放大约3.06倍——实测1672场(对干净的match_results校准)：poisson引擎
    # 预测主客差0.811 vs 实际0.232(3.50x)、poisson_global 1.211 vs 0.422(2.87x)，
    # 且poisson_global预测总进球2.840与按错误公式推算的2.839几乎完全吻合，根因确认。
    lam_h = max(0.3, min(th["ha"] * (ta["ad"] / home_avg), 6.0))
    lam_a = max(0.3, min(ta["aa"] * (th["hd"] / away_avg), 6.0))
    w, d, l = _score_matrix(lam_h, lam_a)
    return {"win": w, "draw": d, "loss": l, "lam_h": lam_h, "lam_a": lam_a}


def _poisson_predict_shrunk(home: str, away: str, lp: dict, k: float = 8.0):
    """跟 _poisson_predict 逻辑一致，但不用"样本量够门槛就100%信任队伍参数、
    不够就整场跳过"的硬切换，改用经验贝叶斯收缩：队伍强度按自身样本量连续地往
    (联赛或全局)均值收缩，样本越少收缩越狠、越多越接近队伍自己的真实值，k是收缩
    强度(等效先验场次数，k场时队伍自己的观测值和均值各占一半权重)。
    2026-07-24半全场(HT/FT)模型回测发现：半场专属样本天然比全场薄，硬切换在这里
    产生的噪声明显（新模型Brier/logloss一度不如"无脑猜训练集最常见结果"的基线），
    换成收缩估计后同一批holdout重新验证过确实更好，因此只给HT/FT用，不改主引擎
    _poisson_predict()本身的行为（全场泊松/主推荐单不受影响）。"""
    # 2026-07-29修复：见_elo_predict()同一处说明
    try:
        from team_mapping import team_en
        home, away = team_en(home), team_en(away)
    except Exception:
        pass
    idx: _NameIndex = lp["index"]
    teams = lp["teams"]
    hk = idx.match(home)
    ak = idx.match(away)
    if not hk or not ak:
        return None
    th, ta = teams[hk], teams[ak]
    home_avg = lp["home_avg"] or 1.35
    away_avg = lp["away_avg"] or 1.10

    def _shrink(val, n, prior):
        return (n * val + k * prior) / (n + k) if (n + k) > 0 else prior

    ha = _shrink(th["ha"], th["hg"], home_avg)
    hd = _shrink(th["hd"], th["hg"], away_avg)
    aa = _shrink(ta["aa"], ta["ag"], away_avg)
    ad = _shrink(ta["ad"], ta["ag"], home_avg)

    # Bug修复(2026-08-11)：同 _poisson_predict，两个归一化分母写反了。注意上面
    # _shrink() 的先验用的恰恰是正确基准（hd收缩向away_avg、ad收缩向home_avg），
    # 说明原作者清楚语义，只是这两行除法写反了。
    lam_h = max(0.3, min(ha * (ad / home_avg), 6.0))
    lam_a = max(0.3, min(aa * (hd / away_avg), 6.0))
    w, d, l = _score_matrix(lam_h, lam_a)
    return {"win": w, "draw": d, "loss": l, "lam_h": lam_h, "lam_a": lam_a}


# ─── ELO 模型 ─────────────────────────────────────────────────────────────────

def _build_elo(matches: list) -> tuple[dict, _NameIndex]:
    ratings: dict = defaultdict(lambda: ELO_INIT)
    for m in sorted(matches, key=lambda x: x["date"]):
        h, a, hs, as_ = m["home"], m["away"], m["hs"], m["as"]
        rh = ratings[h] + ELO_HOME
        ra = ratings[a]
        exp_h = 1 / (1 + 10 ** ((ra - rh) / 400))
        sh = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        sa = 1.0 - sh
        km = 1.0 if abs(hs - as_) <= 1 else (1.5 if abs(hs - as_) == 2 else 1.75)
        ratings[h] += ELO_K * km * (sh - exp_h)
        ratings[a] += ELO_K * km * (sa - (1 - exp_h))
    rd = dict(ratings)
    return rd, _NameIndex(set(rd.keys()))


def _elo_predict(home: str, away: str,
                 ratings: dict, idx: _NameIndex):
    # 2026-07-29修复：_norm()对中文队名做ascii-only编码会直接丢字符变成空串，
    # qiety_yb/okooo_jingcai中文展示名永远匹配不上英文历史库，见00_命中系统.py
    # get_fotmob_shots_probs()同一处说明。团队索引idx本身是英文历史数据建的，
    # 转英文后再查才对得上。
    try:
        from team_mapping import team_en
        home, away = team_en(home), team_en(away)
    except Exception:
        pass
    hk = idx.match(home)
    ak = idx.match(away)
    rh = (ratings.get(hk, ELO_INIT) if hk else ELO_INIT) + ELO_HOME
    ra = ratings.get(ak, ELO_INIT) if ak else ELO_INIT
    p_win = 1 / (1 + 10 ** ((ra - rh) / 400))
    diff = abs(rh - ra - ELO_HOME)
    draw = max(0.08, min(0.27 * math.exp(-diff / 550), 0.34))
    ph = p_win * (1 - draw)
    pa = (1 - p_win) * (1 - draw)
    t = ph + draw + pa
    return ph / t, draw / t, pa / t


# ─── 全局合并参数（跨联赛泊松）────────────────────────────────────────────────

def _build_global_params(params: dict) -> dict:
    all_teams: dict = {}
    total_hg = total_ag = 0
    total_hgoals = total_agoals = 0
    for lp in params.values():
        for t, tp in lp["teams"].items():
            if t not in all_teams:
                all_teams[t] = tp.copy()
            total_hg      += tp["hg"]
            total_ag      += tp["ag"]
            total_hgoals  += tp["ha"] * tp["hg"]
            total_agoals  += tp["aa"] * tp["ag"]
    if not all_teams or total_hg == 0:
        return {}
    return {
        "home_avg": total_hgoals / total_hg,
        "away_avg": total_agoals / total_ag,
        "teams": all_teams,
        "index": _NameIndex(set(all_teams.keys())),
    }


# ─── 半全场(HT/FT)模型 ─────────────────────────────────────────────────────────
# 竞彩"半全场胜平负"：9个结果(半场胜/平/负 × 全场胜/平/负)，中奖须半场+全场同时猜中。
# 2026-07-24新增：此前唯一存在过的实现(run_today_prediction.py，已确认是废弃管线的
# 死代码)只算了9个结果里的5个，且用"半场概率×全场概率"边际相乘，隐含半场/全场彼此
# 独立的错误假设——真实比赛存在"半场领先方下半场收缩"这类状态效应。这里的实现：
# 1) 半场/下半场攻防强度分开估计(复用_build_poisson_params，只是喂进去的"进球"分别
#    换成半场进球、全场减半场进球，权重/回退逻辑完全和主引擎一致，不重新发明)；
# 2) 下半场λ按半场领先/平局/落后三态用fd_matches量出来的真实经验系数修正，
#    而不是当独立事件相乘；
# 3) 半场比分格 × 状态修正后的下半场比分格做卷积，得到完整9格联合分布(自然和为1)。

def _load_fd_htft_matches(conn) -> list:
    """fd_matches(football-data.co.uk)里同时有全场+半场真实比分的历史场次，
    是目前唯一大样本、可靠的半全场训练数据源(sofascore被墙、soccerway半场字段
    代号验证是猜错的，见 project_flashscore_09_ht_field_bug 记忆，本函数不碰这两个源)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT league_code, home_team, away_team, fthg, ftag, hthg, htag, match_date
        FROM fd_matches
        WHERE fthg IS NOT NULL AND ftag IS NOT NULL
          AND hthg IS NOT NULL AND htag IS NOT NULL
          AND match_date IS NOT NULL AND match_date != ''
    """)
    matches = []
    for r in cur.fetchall():
        lg_key = FD_CODE_MAP.get(r[0] or "", "")
        if not lg_key:
            continue
        try:
            fthg, ftag, hthg, htag = int(r[3]), int(r[4]), int(r[5]), int(r[6])
        except (TypeError, ValueError):
            continue
        # 半场进球不可能超过全场，防御一下（fd_matches本身没见过这个问题，但保险起见）
        if hthg > fthg or htag > ftag or hthg < 0 or htag < 0:
            continue
        matches.append({
            "league": lg_key, "home": r[1], "away": r[2],
            "fthg": fthg, "ftag": ftag, "hthg": hthg, "htag": htag,
            "date": (r[7] or "2000-01-01")[:10],
        })
    return matches


def _build_htft_state_coeffs(matches: list, min_state_n: int = 200) -> dict:
    """半场领先状态 → 下半场进球率经验修正系数，真实数据量出来的，不是拍脑袋。
    返回 {'home_lead': (home_mult, away_mult), 'draw': (...), 'away_lead': (...)}，
    home_mult = 该状态下主队下半场实际场均进球 / 主队下半场总体场均进球（away同理）。
    某状态样本量不足 min_state_n 时该状态系数退回 (1.0, 1.0)（不修正，等于承认这个
    状态下数据不够支撑经验系数，不能用不可靠估计冒充真实信号）。
    """
    tot_h = tot_a = tot_n = 0.0
    state_h = defaultdict(float)
    state_a = defaultdict(float)
    state_n = defaultdict(int)

    for m in matches:
        h2h = m["fthg"] - m["hthg"]
        a2h = m["ftag"] - m["htag"]
        state = "home_lead" if m["hthg"] > m["htag"] else ("away_lead" if m["hthg"] < m["htag"] else "draw")
        tot_h += h2h; tot_a += a2h; tot_n += 1
        state_h[state] += h2h
        state_a[state] += a2h
        state_n[state] += 1

    if tot_n == 0:
        return {}
    base_h = tot_h / tot_n
    base_a = tot_a / tot_n

    coeffs = {}
    for state in ("home_lead", "draw", "away_lead"):
        n = state_n.get(state, 0)
        if n < min_state_n or base_h <= 0 or base_a <= 0:
            coeffs[state] = (1.0, 1.0)
            continue
        coeffs[state] = (
            (state_h[state] / n) / base_h,
            (state_a[state] / n) / base_a,
        )
    return coeffs


def _league_avg_lambdas(league: str, poisson_params: dict, global_params: dict) -> dict | None:
    """半全场(HT/FT)半场/下半场λ取联赛场均值，不做球队级差异化。
    2026-07-24用fd_matches holdout(22606场，2025-01-01后)回测对比过：球队级差异化
    (含收缩估计，k=8/20/40均测过)虽然argmax命中率更高，但Brier/logloss(概率标定
    质量)反而不如"完全不做球队差异化、只用联赛均值+状态系数"这个更简单的版本——
    本系统用概率算EV/凯利仓位，标定质量比单纯选没选对更要紧，两者不能割裂着挑，
    因此正式采用这个更简单但标定更可靠的版本，不用_poisson_predict_shrunk。"""
    lp = poisson_params.get(league)
    if lp and lp.get("home_avg") and lp.get("away_avg"):
        return {"lam_h": lp["home_avg"], "lam_a": lp["away_avg"]}
    if global_params and global_params.get("home_avg"):
        return {"lam_h": global_params["home_avg"], "lam_a": global_params["away_avg"]}
    return None


def _htft_joint_grid(lh_ht: float, la_ht: float, lh_2h: float, la_2h: float,
                     state_coeffs: dict, n_ht: int = 6, n_2h: int = 6) -> dict:
    """给定半场/下半场λ，返回9格联合概率 {(ht_result, ft_result): prob}，
    ht_result/ft_result ∈ {'home','draw','away'}。半场用独立泊松；下半场λ先按
    半场结果对应的领先状态用经验系数修正，再和半场比分格做卷积得到全场比分分布，
    不是简单的"半场概率×全场概率"独立假设。"""
    ph = [scipy_poisson.pmf(i, lh_ht) for i in range(n_ht + 1)]
    pa = [scipy_poisson.pmf(j, la_ht) for j in range(n_ht + 1)]

    # 下半场λ只有3种可能取值(半场领先/平/落后三态)，不管半场格子(i,j)具体是几比几，
    # 同一态用的是同一套修正系数——之前在i,j双重循环内部按格子重算下半场分布，
    # 9x9=49个半场格子实际只对应3种状态，等于把下半场泊松pmf多算了十几倍，这里
    # 提到循环外按状态预计算一次，结果完全不变，只是不重复计算。
    p2h_by_state, p2a_by_state = {}, {}
    for state in ("home_lead", "draw", "away_lead"):
        h_mult, a_mult = state_coeffs.get(state, (1.0, 1.0))
        lh2 = max(0.05, lh_2h * h_mult)
        la2 = max(0.05, la_2h * a_mult)
        p2h_by_state[state] = [scipy_poisson.pmf(k, lh2) for k in range(n_2h + 1)]
        p2a_by_state[state] = [scipy_poisson.pmf(l, la2) for l in range(n_2h + 1)]

    joint = defaultdict(float)
    for i in range(n_ht + 1):
        for j in range(n_ht + 1):
            p_ht = ph[i] * pa[j]
            if p_ht < 1e-6:
                continue
            ht_r = "home" if i > j else ("away" if i < j else "draw")
            state = {"home": "home_lead", "away": "away_lead", "draw": "draw"}[ht_r]
            p2h, p2a = p2h_by_state[state], p2a_by_state[state]
            for k in range(n_2h + 1):
                for l in range(n_2h + 1):
                    p2 = p2h[k] * p2a[l]
                    if p2 < 1e-6:
                        continue
                    fh, fa = i + k, j + l
                    ft_r = "home" if fh > fa else ("away" if fh < fa else "draw")
                    joint[(ht_r, ft_r)] += p_ht * p2

    total = sum(joint.values()) or 1.0
    return {k: v / total for k, v in joint.items()}


# ─── 集成预测 ─────────────────────────────────────────────────────────────────

def _elo_lambdas(home: str, away: str, ratings: dict, idx: _NameIndex,
                 home_avg: float = 1.38, away_avg: float = 1.08) -> tuple:
    """ELO 差值 → 进球期望，供 OU/比分预测使用。
    两队均未在 ELO 索引中找到时返回 (None, None)，调用方应跳过比分写入。

    修复：原先用线性阻尼 scale=1+diff_norm*0.25 直接缩放 home_avg/away_avg，
    ELO 差距再大 scale 也几乎不动（400分差距=胜率91%级别时 scale 仅到 1.25），
    导致 lam_h/lam_a 长期贴近基线 1.38/1.08，泊松最可能比分几乎恒为 1-1/1-0，
    且与 _elo_predict() 算出的胜平负概率互相独立、可能自相矛盾。
    现改为反解：固定总进球期望 home_avg+away_avg 不变，只调整主客场分配比例 r，
    使 _score_matrix(total*r, total*(1-r)) 算出的主胜概率与 _elo_predict() 的
    胜率完全一致——比分预测与胜平负概率共用同一套 ELO 胜率，不再是两条互相矛盾的独立算法，
    ELO 差距越大，比分预测也能相应给出 2-0/3-1 等更悬殊的结果。
    """
    # 2026-07-29修复：见_elo_predict()同一处说明
    try:
        from team_mapping import team_en
        home, away = team_en(home), team_en(away)
    except Exception:
        pass
    hk = idx.match(home)
    ak = idx.match(away)
    # 两队均为默认 ELO_INIT → 无任何真实 ELO 信息，无预测价值
    if hk is None and ak is None:
        return None, None

    target_win_prob, _, _ = _elo_predict(home, away, ratings, idx)
    total_avg = home_avg + away_avg

    def _win_gap(r: float) -> float:
        w, _, _ = _score_matrix(total_avg * r, total_avg * (1 - r))
        return w - target_win_prob

    # 总进球期望固定不变时，泊松模型能达到的主胜概率存在数学上限
    # （即使 lam_a→0，home 也有 e^-lam_h 的概率踢成 0-0，胜率无法逼近 100%）。
    # ELO 差距极端、隐含胜率超出该上限时，用边界最悬殊的分配（而非退回 r=0.5 的对称兜底），
    # 这样至少给出模型能力范围内最接近真实实力差距的比分，而不是抹平差距
    R_LO, R_HI = 0.005, 0.995
    gap_lo, gap_hi = _win_gap(R_LO), _win_gap(R_HI)
    if gap_lo > 0:
        r = R_LO
    elif gap_hi < 0:
        r = R_HI
    else:
        r = brentq(_win_gap, R_LO, R_HI, xtol=1e-4)

    return max(0.3, total_avg * r), max(0.3, total_avg * (1 - r))


MARKET_LAMBDA_BLEND_WEIGHT = 0.5  # 市场隐含λ在融合里的权重(另一半是模型λ)，2026-09-06新增


def _devig_two_way(odds_a, odds_b):
    """两项市场(大小球/2way独赢)去水位，返回(p_a, p_b)，任一赔率缺失/非法返回None。"""
    if not odds_a or not odds_b or odds_a <= 1 or odds_b <= 1:
        return None
    ia, ib = 1.0 / odds_a, 1.0 / odds_b
    total = ia + ib
    if total <= 0:
        return None
    return ia / total, ib / total


def _devig_three_way(odds_a, odds_b, odds_c):
    """三项市场(胜平负)去水位，返回(p_a, p_b, p_c)。"""
    if not all([odds_a, odds_b, odds_c]) or min(odds_a, odds_b, odds_c) <= 1:
        return None
    ia, ib, ic = 1.0 / odds_a, 1.0 / odds_b, 1.0 / odds_c
    total = ia + ib + ic
    if total <= 0:
        return None
    return ia / total, ib / total, ic / total


def _implied_total_lambda(line, odds_over, odds_under):
    """从真实大小球盘口(线+赔率)反推市场隐含的总进球期望值(泊松lambda)。
    只处理.5整数线(2.5/3.5等)——整数线(2.0/3.0)存在"走盘"(push)可能，简化不处理，
    返回None，调用方原样退回纯模型λ，不强算。"""
    if line is None:
        return None
    try:
        line = float(line)
    except (TypeError, ValueError):
        return None
    if line == int(line):
        return None
    devig = _devig_two_way(odds_over, odds_under)
    if devig is None:
        return None
    p_over, _ = devig
    threshold = math.floor(line) + 1  # over 2.5 -> 总进球数>=3

    def f(lam):
        return (1.0 - scipy_poisson.cdf(threshold - 1, lam)) - p_over

    try:
        return brentq(f, 0.05, 8.0)
    except ValueError:
        return None


def _split_lambda_by_moneyline(total_lambda, p_home, p_away):
    """已知总进球期望值(total_lambda)，用独赢赔率反推的胜率比例拆分主客队各自的
    进球期望值——用Skellam分布(两个独立泊松分布之差)匹配P(主胜)/P(客胜)的相对比例，
    忽略平局的绝对占比(Skellam自己的P(diff=0)天然承担平局角色，不需要额外处理)。"""
    denom = p_home + p_away
    target = p_home / denom if denom > 0 else 0.5

    def f(r):
        lam_h = total_lambda * r
        lam_a = total_lambda * (1 - r)
        p_pos = 1.0 - scipy_skellam.cdf(0, lam_h, lam_a)   # P(主队净胜球>0)
        p_neg = scipy_skellam.cdf(-1, lam_h, lam_a)         # P(主队净胜球<0)
        cur_denom = p_pos + p_neg
        cur = p_pos / cur_denom if cur_denom > 0 else 0.5
        return cur - target

    try:
        r = brentq(f, 0.05, 0.95)
    except ValueError:
        r = 0.5
    return total_lambda * r, total_lambda * (1 - r)


def _market_implied_lambdas(line, odds_over, odds_under, odds_home, odds_draw, odds_away):
    """综合大小球+独赢真实赔率，反推市场对这场比赛主客队各自进球期望值的隐含判断。
    2026-09-06新增——历史统计模型(泊松/ELO/FotMob xG)完全基于历史数据，看不到伤停/
    状态/内部消息这类只有市场赔率才反映得出的实时信息(见907场真实样本复盘：模型λ
    跟实际进球数相关系数只有0.13~0.17，偏低)。任何一步反推失败(缺赔率/线是整数
    盘口/求解不收敛)都返回None，调用方原样退回纯模型λ，不强融合。"""
    total_lambda = _implied_total_lambda(line, odds_over, odds_under)
    if total_lambda is None:
        return None
    if odds_draw:
        devig = _devig_three_way(odds_home, odds_draw, odds_away)
        if devig is None:
            return None
        p_home, _, p_away = devig
    else:
        devig = _devig_two_way(odds_home, odds_away)
        if devig is None:
            return None
        p_home, p_away = devig
    return _split_lambda_by_moneyline(total_lambda, p_home, p_away)


def predict_match(home: str, away: str, league_code: str,
                  poisson_params: dict, global_params: dict,
                  elo_ratings: dict, elo_idx: _NameIndex,
                  league_name: str = "", fotmob_lambdas_fn=None,
                  market_odds: dict | None = None):
    result = None

    # 1. 同联赛泊松
    lp = poisson_params.get(league_code)
    if lp:
        r = _poisson_predict(home, away, lp)
        if r:
            result = {"home": r["win"], "draw": r["draw"], "away": r["loss"],
                      "lam_h": r["lam_h"], "lam_a": r["lam_a"], "engine": "poisson"}

    # 2. 全局泊松
    if result is None and global_params:
        r = _poisson_predict(home, away, global_params)
        if r:
            result = {"home": r["win"], "draw": r["draw"], "away": r["loss"],
                      "lam_h": r["lam_h"], "lam_a": r["lam_a"], "engine": "poisson_global"}

    # 2.5 FotMob λ（xG/射正，2026-07-21新增）：诊断发现1和2两级失败后直接摔到ELO反解λ，
    # 而LEAGUE_NAME_MAP只有53个联赛映射(泊松参数只对32个联赛建成)，绝大多数比赛(实测
    # 137场里126场)其实是"联赛没进53个映射表/球队名在历史数据里对不上"，不是真的
    # 没有精细数据——FotMob(00_命中系统.py的43号爬虫，覆盖58个联赛)刚好能补这一段：
    # ELO反解的λ只是从胜率数学倒推、不基于任何进球历史，FotMob好歹是真实xG/射正数据，
    # 精度介于"本联赛专属泊松"和"纯ELO"之间，放在ELO之前作为更优先的兜底。
    if result is None and fotmob_lambdas_fn:
        try:
            lam_h_fm, lam_a_fm = fotmob_lambdas_fn(home, away, league_name)
        except Exception:
            lam_h_fm = lam_a_fm = None
        if lam_h_fm is not None and lam_a_fm is not None:
            w, d, l = _score_matrix(lam_h_fm, lam_a_fm)
            result = {"home": w, "draw": d, "away": l,
                      "lam_h": lam_h_fm, "lam_a": lam_a_fm, "engine": "fotmob"}

    # 3. ELO 降级（附带 ELO 估算 lambda，供大小球预测）
    if result is None:
        ph, pd, pa = _elo_predict(home, away, elo_ratings, elo_idx)
        # Bug修复(2026-08-11)：原先调用不传联赛均值，_elo_lambdas 永远退回硬编码
        # 默认值 home_avg=1.38/away_avg=1.08（总和2.46）——实测ELO引擎898场预测总
        # 进球恰好是2.464，与该默认值完全吻合，而真实均值2.735，系统性低估约10%。
        # 而且总量被压低会连带压窄主客差（差值=总量×(2r-1)），实测预测主客差0.321
        # vs 实际0.437。这里改为按联赛取真实均值（_league_avg_lambdas 自带全局兜底）。
        _avg = _league_avg_lambdas(league_code, poisson_params, global_params)
        if _avg:
            lam_h, lam_a = _elo_lambdas(home, away, elo_ratings, elo_idx,
                                        home_avg=_avg["lam_h"], away_avg=_avg["lam_a"])
        else:
            lam_h, lam_a = _elo_lambdas(home, away, elo_ratings, elo_idx)
        result = {"home": ph, "draw": pd, "away": pa,
                  "lam_h": lam_h, "lam_a": lam_a, "engine": "elo"}

    # 4. 市场隐含λ融合（2026-09-06新增，见_market_implied_lambdas()说明）：不管
    # 上面走的是哪一级引擎，只要调用方传入了这场比赛的真实赔率，都在最后统一融合
    # 一次，不需要在4个分支里各自重复接线。融合失败(缺赔率/线是整数盘口/求解不
    # 收敛)时market_odds_result为None，原样保留纯模型结果，不强融合。
    # Bug修复(2026-09-06)：ELO兜底在两队均未知时返回lam_h/lam_a=(None,None)
    # （_elo_lambdas()文档明确"调用方应跳过比分写入"），但这里融合前漏检，
    # (1-w)*None直接抛TypeError，且此函数在批量循环里被无try/except调用，
    # 单场触发就会让run_predictions()整体崩溃、当天全部比赛的足球预测被跳过。
    if market_odds and result.get("lam_h") is not None and result.get("lam_a") is not None:
        mkt = _market_implied_lambdas(
            market_odds.get("ou_line"), market_odds.get("over"), market_odds.get("under"),
            market_odds.get("home"), market_odds.get("draw"), market_odds.get("away"),
        )
        if mkt is not None:
            mkt_lam_h, mkt_lam_a = mkt
            w = MARKET_LAMBDA_BLEND_WEIGHT
            blended_h = (1 - w) * result["lam_h"] + w * mkt_lam_h
            blended_a = (1 - w) * result["lam_a"] + w * mkt_lam_a
            bw, bd, bl = _score_matrix(blended_h, blended_a)
            result = {"home": bw, "draw": bd, "away": bl,
                      "lam_h": blended_h, "lam_a": blended_a,
                      "engine": result["engine"] + "+market"}

    return result


# ─── 主入口 ───────────────────────────────────────────────────────────────────

def _load_market_odds_map(cur, _uids, fetch_date, frozen_market_input=None):
    """Keep market aggregation unchanged; supplied run input never falls back to SQL."""
    market_odds_map: dict = {}
    if _uids:
        _CHUNK = 500
        for _i in range(0, len(_uids), _CHUNK):
            _chunk_uids = _uids[_i:_i + _CHUNK]
            _placeholders = ",".join("?" * len(_chunk_uids))
            if frozen_market_input is None:
                cur.execute(f"""
                    SELECT unified_id, market, outcome, handicap, odds_value
                    FROM unified_odds
                    WHERE unified_id IN ({_placeholders}) AND fetch_date=?
                      AND market IN ('moneyline','total','totals')
                      AND outcome IN ('home','draw','away','over','under')
                      AND odds_value BETWEEN 1.01 AND 15.0
                """, [*_chunk_uids, fetch_date])
                market_rows = cur.fetchall()
            else:
                market_rows = []
                for uid in _chunk_uids:
                    entry = frozen_market_input.get(uid, {})
                    if entry.get("fetch_date") != fetch_date or entry.get("unified_status") != "SUCCESS":
                        continue
                    for r in entry["unified_rows"]:
                        if (r["uid"] == uid and r["fd"] == fetch_date
                                and r["market"] in ("moneyline", "total", "totals")
                                and r["outcome"] in ("home", "draw", "away", "over", "under")
                                and r["val"] is not None and 1.01 <= r["val"] <= 15.0):
                            market_rows.append((uid, r["market"], r["outcome"], r["hc"], r["val"]))
            _ml_rows: dict = {}     # uid -> outcome -> [odds]
            _tot_rows: dict = {}    # uid -> (line, outcome) -> [odds]
            for _uid, _mkt, _oc, _hc, _val in market_rows:
                if _mkt == "moneyline":
                    _ml_rows.setdefault(_uid, defaultdict(list))[_oc].append(_val)
                else:
                    _tot_rows.setdefault(_uid, defaultdict(list))[(_hc, _oc)].append(_val)

            for _uid in _chunk_uids:
                _entry = {}
                _ml = _ml_rows.get(_uid)
                if _ml and _ml.get("home") and _ml.get("away"):
                    _entry["home"] = sum(_ml["home"]) / len(_ml["home"])
                    _entry["away"] = sum(_ml["away"]) / len(_ml["away"])
                    _entry["draw"] = (sum(_ml["draw"]) / len(_ml["draw"])) if _ml.get("draw") else None
                _tot = _tot_rows.get(_uid)
                if _tot:
                    # 同一场可能有多条盘口线，取有效来源最多(over+under条数最多)的主线
                    _lines = defaultdict(int)
                    for (_hc, _oc), _vals in _tot.items():
                        if _hc is not None:
                            _lines[_hc] += len(_vals)
                    if _lines:
                        _main_line = max(_lines, key=_lines.get)
                        _over_vals = _tot.get((_main_line, "over"))
                        _under_vals = _tot.get((_main_line, "under"))
                        if _over_vals and _under_vals:
                            _entry["ou_line"] = _main_line
                            _entry["over"] = sum(_over_vals) / len(_over_vals)
                            _entry["under"] = sum(_under_vals) / len(_under_vals)
                if "home" in _entry and "over" in _entry:
                    market_odds_map[_uid] = _entry
    return market_odds_map


def run_predictions(fetch_date: str | None = None, *, frozen_market_input=None) -> int:
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n🔮 足球预测模型启动  [{fetch_date}]", flush=True)

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur  = conn.cursor()

    # ── 加载历史比赛 ──
    cur.execute("""
        SELECT league, home_team, away_team, home_score, away_score, match_date
        FROM football_matches
        WHERE home_score IS NOT NULL AND status='Match Finished'
    """)
    matches = [{"league": r[0], "home": r[1], "away": r[2],
                "hs": int(r[3]), "as": int(r[4]), "date": r[5]}
               for r in cur.fetchall()]

    # Bug修复：betexplorer 历史数据原来硬编码 "2025-01-01"，导致形态衰减 exp(-decay*i) 失效
    # 改为使用 kickoff_utc[:10] 作为比赛日期，让近期比赛权重高于旧比赛
    cur.execute("""
        SELECT league_code, home_team, away_team, home_score, away_score,
               COALESCE(kickoff_utc, fetch_date, '2024-01-01') as match_date
        FROM betexplorer_matches
        WHERE home_score IS NOT NULL AND status='FT' AND sport_code='football'
    """)
    for r in cur.fetchall():
        date_str = (r[5] or "2024-01-01")[:10]
        matches.append({"league": r[0], "home": r[1], "away": r[2],
                        "hs": int(r[3]), "as": int(r[4]), "date": date_str})

    # ── 补充源1：football-data.co.uk (fd_matches) — 255k场，欧洲21联赛，最强历史覆盖 ──
    cur.execute("""
        SELECT league_code, home_team, away_team, fthg, ftag, match_date
        FROM fd_matches
        WHERE fthg IS NOT NULL AND ftag IS NOT NULL
          AND match_date IS NOT NULL AND match_date != ''
    """)
    _fd_added = 0
    for r in cur.fetchall():
        lg_key = FD_CODE_MAP.get(r[0] or "", "")
        if not lg_key:
            continue
        try:
            matches.append({"league": lg_key, "home": r[1], "away": r[2],
                            "hs": int(r[3]), "as": int(r[4]), "date": (r[5] or "2000-01-01")[:10]})
            _fd_added += 1
        except (TypeError, ValueError):
            pass
    print(f"  📚 fd_matches 补充: {_fd_added} 场", flush=True)

    # ── 补充源2：FBref 赛季统计 (fbref_match_stats) — 近2赛季顶级联赛 ──
    cur.execute("""
        SELECT league_name, home_team, away_team, home_score, away_score, match_date
        FROM fbref_match_stats
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
          AND match_date IS NOT NULL
    """)
    _fbref_added = 0
    for r in cur.fetchall():
        lg_key = _map_league(r[0] or "")
        if not lg_key:
            continue
        try:
            matches.append({"league": lg_key, "home": r[1], "away": r[2],
                            "hs": int(r[3]), "as": int(r[4]), "date": (r[5] or "2024-01-01")[:10]})
            _fbref_added += 1
        except (TypeError, ValueError):
            pass
    print(f"  📚 fbref_match_stats 补充: {_fbref_added} 场", flush=True)

    # ── 补充源3：Understat xG 数据 (understat_xg_matches) — 6大联赛含 xG ──
    cur.execute("""
        SELECT league_slug, home_team, away_team, home_goals, away_goals, match_date
        FROM understat_xg_matches
        WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
          AND match_date IS NOT NULL AND is_result = 1
    """)
    _ustat_added = 0
    for r in cur.fetchall():
        lg_key = SLUG_CODE_MAP.get((r[0] or "").lower(), "")
        if not lg_key:
            continue
        try:
            matches.append({"league": lg_key, "home": r[1], "away": r[2],
                            "hs": int(r[3]), "as": int(r[4]), "date": (r[5] or "2024-01-01")[:10]})
            _ustat_added += 1
        except (TypeError, ValueError):
            pass
    print(f"  📚 understat_xg_matches 补充: {_ustat_added} 场", flush=True)

    print(f"  📚 历史比赛合计: {len(matches)} 场", flush=True)

    # ── 建模 ──
    poisson_params = _build_poisson_params(matches)
    global_params  = _build_global_params(poisson_params)
    elo_ratings, elo_idx = _build_elo(matches)
    print(f"  🏆 ELO: {len(elo_ratings)} 队  |  泊松: {len(poisson_params)} 联赛", flush=True)

    # FotMob λ 兜底函数（2026-07-21新增，见predict_match()里"2.5 FotMob λ"说明）：
    # 用importlib延迟导入00_命中系统.py，避免模块级循环导入(00_命中系统.py只在函数内部
    # 局部import本文件的_dc_score_grid，不是模块级，这里对称处理)。取不到就退回None，
    # predict_match()会正常跳过这一级直接摔到ELO，不影响原有行为。
    _fotmob_lambdas_fn = None
    try:
        import importlib
        _hit_sys_mod = importlib.import_module("00_命中系统")
        _hit_sys_mod.preload_xg_caches()
        _fotmob_lambdas_fn = _hit_sys_mod._fotmob_lambdas
    except Exception as e:
        print(f"  ⚠ FotMob λ兜底加载失败(不影响其他引擎): {e}", flush=True)

    global DC_RHO
    DC_RHO = _fit_dc_rho(matches, poisson_params, global_params)
    # 持久化 rho：00_命中系统.py 跑在独立子进程里，读不到这里的模块内存值，
    # 需要落库让比分玩法接入推荐引擎时能拿到同一个拟合值
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS dc_rho_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rho REAL, fetch_date TEXT, created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.execute("INSERT INTO dc_rho_state (rho, fetch_date) VALUES (?, ?)", (DC_RHO, fetch_date))
        conn.commit()
    except Exception as e:
        print(f"  ⚠ DC_RHO 落库失败: {e}", flush=True)

    # ── 半全场(HT/FT) 模型：球队半场/下半场攻防强度 + 状态修正系数（训练一次，本轮复用）──
    htft_matches = _load_fd_htft_matches(conn)
    ht_matches = [{**m, "hs": m["hthg"], "as": m["htag"]} for m in htft_matches]
    sh_matches = [{**m, "hs": m["fthg"] - m["hthg"], "as": m["ftag"] - m["htag"]} for m in htft_matches]
    ht_poisson_params = _build_poisson_params(ht_matches)
    ht_global_params  = _build_global_params(ht_poisson_params)
    sh_poisson_params = _build_poisson_params(sh_matches)
    sh_global_params  = _build_global_params(sh_poisson_params)
    htft_state_coeffs = _build_htft_state_coeffs(htft_matches)
    print(f"  ⏱ HT/FT: {len(htft_matches)} 场训练样本  |  状态系数: {htft_state_coeffs}", flush=True)

    # ── 今日赛事 ──
    cur.execute("""
        SELECT unified_id, league_name, league_code, home_team_std, away_team_std,
               kickoff_utc
        FROM unified_matches
        WHERE fetch_date=? AND sport_code IN ('football','soccer','Soccer')
          AND status IN ('pending','scheduled','NS')
          AND home_team_std != '' AND away_team_std != ''
    """, (fetch_date,))
    fixtures = cur.fetchall()
    print(f"  ⚽ 今日待预测: {len(fixtures)} 场", flush=True)

    market_odds_map = _load_market_odds_map(
        cur, [f[0] for f in fixtures], fetch_date, frozen_market_input)
    print(f"  📐 市场隐含λ融合：{len(market_odds_map)}/{len(fixtures)} 场有完整大小球+独赢真实赔率", flush=True)

    # ── 批量生成预测 ──
    rows_1x2   = []
    rows_ou    = []
    rows_score = []   # 新增: (uid, home, away, kickoff, top_score, lam_h, lam_a, engine, fetch_date, now)
    rows_htft  = []   # 半全场(HT/FT): 9格联合概率，market_group='HTFT'
    stats    = defaultdict(int)
    now      = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    skip_tags = {"(Corners)", "(Cards)", "(Bookings)"}

    for uid, league_name, league_code, home, away, kickoff in fixtures:
        if any(t in (home + away) for t in skip_tags):
            continue
        mapped_league = league_code or _map_league(league_name)
        probs = predict_match(home, away, mapped_league,
                              poisson_params, global_params,
                              elo_ratings, elo_idx,
                              league_name=league_name, fotmob_lambdas_fn=_fotmob_lambdas_fn,
                              market_odds=market_odds_map.get(uid))
        stats[probs["engine"]] += 1

        # 1X2 行
        for outcome, prob in [("home", probs["home"]),
                               ("draw", probs["draw"]),
                               ("away", probs["away"])]:
            if prob <= 0:
                continue
            rows_1x2.append((
                uid, "football", league_code or "", fetch_date, kickoff or "",
                home, away, "1X2", "full_time", "fulltime",
                outcome, None, round(prob, 6), round(1 / prob, 4),
                None, None, None,
                "高" if prob > 0.50 else ("中" if prob > 0.35 else "低"),
                probs["engine"], RUN_TAG, now,
            ))

        # OU 行 + 比分行：用泊松 lambda 计算
        lam_h = probs.get("lam_h")
        lam_a = probs.get("lam_a")
        if lam_h and lam_a:
            ou = _ou_from_lambdas(lam_h, lam_a)
            for sel, prob in ou.items():
                if prob <= 0:
                    continue
                line_val = None
                if "_" in sel:
                    parts = sel.split("_")
                    try:
                        line_val = float(".".join(parts[1:]).replace("_", "."))
                    except ValueError:
                        pass
                rows_ou.append((
                    uid, "football", league_code or "", fetch_date, kickoff or "",
                    home, away, "OU", "total", "fulltime",
                    sel, line_val, round(prob, 6), round(1 / prob, 4) if prob > 0 else None,
                    None, None, None,
                    "高" if prob > 0.55 else ("中" if prob > 0.45 else "低"),
                    probs["engine"], RUN_TAG, now,
                ))
            # 比分预测：ELO 双队未知时 _elo_lambdas 返回 (None,None)，lam_h/lam_a 为 None
            # 外层 if lam_h and lam_a 已拦截，到达此处 lam 一定有效，直接写入
            top_score = _top_score_from_lambdas(lam_h, lam_a)
            rows_score.append((
                uid, home, away, league_name, kickoff or "",
                top_score, round(lam_h, 3), round(lam_a, 3),
                probs["engine"], fetch_date, now,
            ))

        # 半全场(HT/FT) 行：联赛场均值(不做球队级差异化，2026-07-24回测验证过这样
        # 概率标定质量更好，见_league_avg_lambdas()说明)，league→global两级回退。
        # 两级都没有真实半场/下半场训练数据就跳过这场比赛，不接ELO兜底——ELO只建模
        # 整场胜率，没有半场维度，硬凑等于制造假信号，违反"推荐单数据支撑规则"。
        ht_r = _league_avg_lambdas(mapped_league, ht_poisson_params, ht_global_params)
        sh_r = _league_avg_lambdas(mapped_league, sh_poisson_params, sh_global_params)
        if ht_r and sh_r and htft_state_coeffs:
            joint = _htft_joint_grid(ht_r["lam_h"], ht_r["lam_a"], sh_r["lam_h"], sh_r["lam_a"], htft_state_coeffs)
            for (htres, ftres), prob in joint.items():
                if prob <= 0:
                    continue
                rows_htft.append((
                    uid, "football", league_code or "", fetch_date, kickoff or "",
                    home, away, "HTFT", "ht_ft", "fulltime",
                    f"{htres}-{ftres}", None, round(prob, 6), round(1 / prob, 4) if prob > 0 else None,
                    None, None, None,
                    "高" if prob > 0.30 else ("中" if prob > 0.12 else "低"),
                    "poisson_htft_joint", RUN_TAG, now,
                ))

    # ── 批量写入（单事务）──
    cur.execute(
        "DELETE FROM market_prediction_snapshot WHERE match_date=? AND run_tag=? AND market_group='1X2'",
        (fetch_date, RUN_TAG)
    )
    cur.execute(
        "DELETE FROM market_prediction_snapshot WHERE match_date=? AND run_tag=? AND market_group='OU'",
        (fetch_date, RUN_TAG)
    )
    cur.execute(
        "DELETE FROM market_prediction_snapshot WHERE match_date=? AND run_tag=? AND market_group='HTFT'",
        (fetch_date, RUN_TAG)
    )
    insert_sql = """
        INSERT INTO market_prediction_snapshot
        (match_id_internal, sport_code, league_code, match_date, kickoff_local,
         home_team_name_std, away_team_name_std, market_group, market_type, period,
         selection_name, line_value, model_prob, fair_odds,
         offered_odds, expected_value, kelly_ratio, confidence_grade,
         result_source, run_tag, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    cur.executemany(insert_sql, rows_1x2)
    cur.executemany(insert_sql, rows_ou)
    cur.executemany(insert_sql, rows_htft)
    print(f"  ⏱ HT/FT: {len(rows_htft)} 行写入影子桶（{len(rows_htft)//9 if rows_htft else 0} 场有完整9格）", flush=True)

    # 写入比分预测表
    if rows_score:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS football_score_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unified_id TEXT,
                home_team TEXT,
                away_team TEXT,
                league_name TEXT,
                kickoff_utc TEXT,
                top_score TEXT,
                lambda_home REAL,
                lambda_away REAL,
                engine TEXT,
                fetch_date TEXT,
                created_at TEXT,
                UNIQUE(unified_id, fetch_date)
            )
        """)
        cur.execute("DELETE FROM football_score_predictions WHERE fetch_date=?", (fetch_date,))
        cur.executemany("""
            INSERT OR REPLACE INTO football_score_predictions
            (unified_id, home_team, away_team, league_name, kickoff_utc,
             top_score, lambda_home, lambda_away, engine, fetch_date, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, rows_score)

    conn.commit()
    conn.close()

    n = len(rows_1x2) // 3
    print(f"  ✅ 预测完成: {n} 场  比分: {len(rows_score)} 条  引擎分布: {dict(stats)}  OU行: {len(rows_ou)}", flush=True)
    return n


if __name__ == "__main__":
    import argparse as _ap
    _p = _ap.ArgumentParser()
    _p.add_argument("--date", default=None)
    _p.add_argument("--latest", action="store_true")
    _args = _p.parse_args()
    run_predictions(_args.date)
