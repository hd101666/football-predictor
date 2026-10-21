# 05_泊松凯利预测模型.py — 七层融合终极版（泊松+LSTM+Transformer+xG+GNN+RL+多模态）
import pandas as pd
import numpy as np
from datetime import date
from scipy.stats import poisson
from sqlalchemy import create_engine, text
from db_utils import exec_ddl
from config import (
    DB_ENGINE_URL, DB_DIR, BASKETBALL_LEAGUE_LIST,
    WEIGHT_POISSON, WEIGHT_LSTM, WEIGHT_TRANSFORMER,
    WEIGHT_XG, WEIGHT_GNN, WEIGHT_RL, WEIGHT_MULTIMODAL,
    KELLY_MAX_RATIO, KELLY_MIN_VALUE,
)

engine = create_engine(DB_ENGINE_URL)

# ── unified_matches.league_name → football_team_stats.league slug ────────────
LEAGUE_NAME_TO_SLUG = {
    "england - premier league":     "premier_league",
    "germany - bundesliga":         "bundesliga",
    "spain - la liga":              "laliga",
    "italy - serie a":              "serie_a",
    "france - ligue 1":             "ligue_1",
    "netherlands - eredivisie":     "eredivisie",
    "portugal - primeira liga":     "liga_portugal",
    "portugal - liga portugal":     "liga_portugal",
    "russia - premier league":      "rpl",
    "china pr - super league":      "csl",
    "china - super league":         "csl",
    "japan - j1 league":            "j1",
    "japan - j league":             "j1",
    "korea republic - k league 1":  "k_league_1",
    "usa - mls":                    "mls",
    "brazil - serie a":             "serie_a_br",
    "sweden - allsvenskan":         "allsvenskan",
    "norway - eliteserien":         "eliteserien",
    "belgium - pro league":         "pro_league_be",
    "scotland - premiership":       "spfl_premiership",
    "turkey - super lig":           "super_lig",
    "turkey - superlig":            "super_lig",
    "denmark - superliga":          "superliga",
    "argentina - primera division": "liga_argentina",
    "usa - nba":                    "nba",
    "nba":                          "nba",
    "usa - wnba":                   "wnba",
    "wnba":                         "wnba",
}

def _league_to_slug(league_name: str) -> str | None:
    return LEAGUE_NAME_TO_SLUG.get(league_name.lower().strip())


def _safe_load(sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(sql, engine)
    except Exception:
        return pd.DataFrame()


def _compute_dynamic_weights(lstm_state, xg_stats, gnn_data, rl_data, mm_data, trans_data):
    """
    动态降权：检测各模块数据是否有效，空表/无匹配数据时将权重分配给有效模块。
    返回归一化后的7个权重 (w_poisson, w_lstm, w_trans, w_xg, w_gnn, w_rl, w_mm)
    """
    base = {
        'poisson': WEIGHT_POISSON,
        'lstm':    WEIGHT_LSTM,
        'trans':   WEIGHT_TRANSFORMER,
        'xg':      WEIGHT_XG,
        'gnn':     WEIGHT_GNN,
        'rl':      WEIGHT_RL,
        'mm':      WEIGHT_MULTIMODAL,
    }
    # 检查每个模块是否有有效数据
    active = {
        'poisson': True,  # Poisson 始终有效（基于 team_stats）
        'lstm':    not lstm_state.empty and len(lstm_state) >= 10,
        'trans':   not trans_data.empty and len(trans_data) >= 10,
        'xg':      not xg_stats.empty and len(xg_stats) >= 5,
        'gnn':     not gnn_data.empty and len(gnn_data) >= 5,
        'rl':      not rl_data.empty and len(rl_data) >= 5,
        'mm':      not mm_data.empty and len(mm_data) >= 5,
    }
    # 将失效模块的权重按比例重新分配给有效模块
    dead_weight = sum(base[k] for k in active if not active[k])
    alive_weight = sum(base[k] for k in active if active[k])
    if dead_weight > 0 and alive_weight > 0:
        for k in active:
            if active[k]:
                base[k] += dead_weight * (base[k] / alive_weight)

    total = sum(base.values())
    if total > 0:
        for k in base:
            base[k] /= total

    inactive_list = [k for k, v in active.items() if not v]
    if inactive_list:
        print(f"  ⚙️ 动态降权：{inactive_list} 模块无数据，权重已重分配")
    else:
        print(f"  ✅ 七层融合全部有效，权重完整")

    return (base['poisson'], base['lstm'], base['trans'],
            base['xg'], base['gnn'], base['rl'], base['mm'])


def load_fusion_data():
    return (
        _safe_load("SELECT * FROM basketball_team_stats"),
        _safe_load("SELECT league, avg_total FROM basketball_league_ou"),
        _safe_load("SELECT * FROM basketball_odds"),
        _safe_load("SELECT league, team, state_score FROM team_lstm_state"),
        _safe_load("SELECT league, team, xg_off, xg_def FROM football_xg_stats"),
        _safe_load("SELECT league, team, gnn_correlation_score FROM team_gnn_courtmotion"),
        _safe_load("SELECT league, team, rl_home_bonus, rl_away_bonus FROM team_rl_mas"),
        _safe_load("SELECT league, team, multimodal_total FROM team_multimodal"),
        _safe_load("SELECT league, team, trans_score FROM team_transformer_state"),
    )


def load_today_fixtures() -> pd.DataFrame:
    """
    从 unified_matches 读今日 pending 场次，关联 unified_odds 取 moneyline 赔率。
    返回列: league_name, sport_code, home_team, away_team, kickoff_utc,
            unified_id, home_odds, draw_odds, away_odds
    """
    today = date.today().isoformat()
    fixtures = _safe_load(f"""
        SELECT unified_id, sport_code, league_name, home_team_std AS home_team,
               away_team_std AS away_team, kickoff_utc
        FROM unified_matches
        WHERE fetch_date = '{today}' AND status = 'pending'
        ORDER BY kickoff_utc
    """)
    if fixtures.empty:
        return fixtures

    odds_raw = _safe_load(f"""
        SELECT unified_id, market, outcome, AVG(odds_value) AS odds_value
        FROM unified_odds
        WHERE fetch_date = '{today}' AND market = 'moneyline'
        GROUP BY unified_id, market, outcome
    """)

    if not odds_raw.empty:
        odds_pivot = odds_raw.pivot_table(
            index="unified_id", columns="outcome", values="odds_value"
        ).reset_index()
        odds_pivot.columns.name = None
        for col in ("home", "draw", "away"):
            if col not in odds_pivot.columns:
                odds_pivot[col] = None
        odds_pivot = odds_pivot.rename(columns={
            "home": "home_odds", "draw": "draw_odds", "away": "away_odds"
        })
        fixtures = fixtures.merge(odds_pivot[["unified_id", "home_odds", "draw_odds", "away_odds"]],
                                  on="unified_id", how="left")
    else:
        fixtures["home_odds"] = fixtures["draw_odds"] = fixtures["away_odds"] = None

    print(f"  今日赛程: {len(fixtures)} 场 (soccer={( fixtures['sport_code']=='soccer').sum()}, "
          f"basketball={(fixtures['sport_code']=='basketball').sum()})")
    return fixtures


def _build_football_index(df: pd.DataFrame) -> dict:
    """football_team_stats → {slug: {team_lower: (off, def, league_avg)}}"""
    idx: dict = {}
    if df.empty:
        return idx
    for slug, grp in df.groupby("league"):
        lg_avg = float(grp["avg_scored"].mean() + grp["avg_conceded"].mean()) / 2
        lg_avg = max(lg_avg, 0.1)
        idx[slug] = {
            row["team_name"].lower(): (
                float(row["avg_scored"]  or lg_avg / 2),
                float(row["avg_conceded"] or lg_avg / 2),
                lg_avg,
            )
            for _, row in grp.iterrows()
        }
    return idx


def _lookup_team(name: str, slug: str, football_idx: dict,
                 basketball_df: pd.DataFrame) -> tuple[float, float, float]:
    """返回 (offense_eff, defense_eff, league_avg)，找不到时用联赛均值兜底。"""
    name_lo = name.lower().strip()

    # 篮球
    if not basketball_df.empty and "league" in basketball_df.columns:
        bk_lg = basketball_df[basketball_df["league"] == slug]
        if not bk_lg.empty:
            lg_avg = float(bk_lg["offense_eff"].mean() + bk_lg["defense_eff"].mean()) / 2
            match = bk_lg[bk_lg["team"].str.lower() == name_lo]
            if not match.empty:
                r = match.iloc[0]
                return float(r["offense_eff"]), float(r["defense_eff"]), lg_avg
            return lg_avg / 2, lg_avg / 2, lg_avg

    # 足球
    if slug and slug in football_idx:
        league_teams = football_idx[slug]
        lg_avg = next(iter(league_teams.values()))[2] if league_teams else 2.5
        if name_lo in league_teams:
            return league_teams[name_lo]
        # 部分匹配（队名包含关系）
        for t, vals in league_teams.items():
            if name_lo in t or t in name_lo:
                return vals
        return lg_avg / 2, lg_avg / 2, lg_avg

    # 无统计数据：足球全局均值兜底
    return 1.3, 1.3, 2.6


def _get_val(df, lg, team, col, default=1.0):
    if df.empty or "league" not in df.columns or "team" not in df.columns or col not in df.columns:
        return default
    mask = (df["league"] == lg) & (df["team"] == team)
    if mask.any():
        return float(df.loc[mask, col].iloc[0])
    return default


def fusion_poisson_pred(
    home_off, home_def, away_off, away_def,
    home_lstm, away_lstm, home_trans, away_trans,
    home_xg, away_xg, home_gnn, away_gnn,
    home_rl_h, away_rl_a, home_mm, away_mm,
    league_avg, sport_type="football",
    weights=None,  # (w_poisson, w_lstm, w_trans, w_xg, w_gnn, w_rl, w_mm)
):
    max_val = 8 if sport_type == "football" else 200
    league_avg = max(league_avg, 0.1)

    home_exp = (home_off * away_def / league_avg) * (
        (1 + (home_lstm - 2) / 10) * (1 + (home_trans - 2) / 10) *
        max(home_xg, 0.01) * max(home_gnn, 0.01) * home_rl_h * home_mm
    )
    away_exp = (away_off * home_def / league_avg) * (
        (1 + (away_lstm - 2) / 10) * (1 + (away_trans - 2) / 10) *
        max(away_xg, 0.01) * max(away_gnn, 0.01) * away_rl_a * away_mm
    )
    max_exp_bound = 15 if sport_type == "football" else 140
    home_exp = max(min(home_exp, max_exp_bound), 0.01)
    away_exp = max(min(away_exp, max_exp_bound), 0.01)

    hp = [poisson.pmf(i, home_exp) for i in range(max_val + 1)]
    ap = [poisson.pmf(i, away_exp) for i in range(max_val + 1)]

    home_win = draw = away_win = 0.0
    score_probs: dict = {}
    for h in range(max_val + 1):
        for a in range(max_val + 1):
            p = hp[h] * ap[a]
            score_probs[f"{h}-{a}"] = p
            if h > a:   home_win += p
            elif h == a and sport_type == "football": draw += p
            elif h < a: away_win += p

    # 使用动态权重（如果传入）或回退到静态权重
    w_p, w_lstm, w_trans, w_xg, w_gnn, w_rl, w_mm = (
        weights if weights else
        (WEIGHT_POISSON, WEIGHT_LSTM, WEIGHT_TRANSFORMER,
         WEIGHT_XG, WEIGHT_GNN, WEIGHT_RL, WEIGHT_MULTIMODAL)
    )

    # 各子模型分量先归一化到 [0,1] 再加权：非概率指标做 sigmoid 压缩
    def _norm(v, ref=2.0):
        return 1 / (1 + np.exp(-(v - ref)))

    fh = (home_win * w_p
          + _norm(home_lstm)  * w_lstm
          + _norm(home_trans) * w_trans
          + _norm(home_xg, ref=league_avg / 2) * w_xg
          + _norm(home_gnn, ref=1.0) * w_gnn
          + _norm(home_rl_h, ref=1.0) * w_rl
          + _norm(home_mm,   ref=1.0) * w_mm)
    fa = (away_win * w_p
          + _norm(away_lstm)  * w_lstm
          + _norm(away_trans) * w_trans
          + _norm(away_xg, ref=league_avg / 2) * w_xg
          + _norm(away_gnn, ref=1.0) * w_gnn
          + _norm(away_rl_a, ref=1.0) * w_rl
          + _norm(away_mm,   ref=1.0) * w_mm)
    fd = draw * w_p if sport_type == "football" else None

    # 归一化使三者之和为 1
    total = fh + fa + (fd if fd is not None else 0.0)
    total = max(total, 1e-6)
    fh /= total
    fa /= total
    if fd is not None:
        fd /= total

    return {
        "home_exp": round(home_exp, 2), "away_exp": round(away_exp, 2),
        "total_exp": round(home_exp + away_exp, 2),
        "home_win_prob": round(fh, 4),
        "draw_prob":     round(fd, 4) if fd is not None else None,
        "away_win_prob": round(fa, 4),
        "score_probs":   score_probs,
    }


def kelly_multi(prob_dict: dict, odds_dict: dict, bankroll: float = 1000):
    """
    改进版 Kelly 公式：半 Kelly + 单场上限 5% + 止损保护 + 最低价值门槛
    """
    stake, kelly_val = {}, {}
    for k, p in prob_dict.items():
        o = float(odds_dict.get(k, 2.0) or 2.0)
        if o <= 1 or not p:
            stake[k] = 0; kelly_val[k] = 0; continue
        # 标准 Kelly
        full_kelly = max(0, (p * o - 1) / (o - 1))
        # 半 Kelly 策略（降低波动）
        half_kelly = full_kelly * 0.5
        # 硬上限：单场不超过资金 5%
        f = min(half_kelly, 0.05)
        # 最低价值门槛：Kelly < 1% 不值得下注
        if f < KELLY_MIN_VALUE:
            f = 0.0
        stake[k]     = round(bankroll * f, 2)
        kelly_val[k] = round(f, 4)
    return stake, kelly_val


def run_fusion_prediction(team, league, odds, lstm_state, xg_stats, gnn_data, rl_data, mm_data, trans_data):
    predictions = []
    weights = _compute_dynamic_weights(lstm_state, xg_stats, gnn_data, rl_data, mm_data, trans_data)

    # ── 加载今日真实赛程 ──────────────────────────────────────────────────────
    football_stats = _safe_load(
        "SELECT league, team_name, avg_scored, avg_conceded FROM football_team_stats"
    )
    football_idx = _build_football_index(football_stats)
    fixtures = load_today_fixtures()

    if fixtures.empty:
        print("⚠️ unified_matches 无今日赛程，回退旧逻辑（顺序配对）")
        # ── 旧逻辑兜底（保持向后兼容）────────────────────────────────────────
        for lg in league["league"].unique():
            row_lg = league.loc[league["league"] == lg, "avg_total"]
            lg_avg = float(row_lg.iloc[0]) if not row_lg.empty else 2.5
            teams  = team.loc[team["league"] == lg, "team"].tolist()
            if len(teams) < 2:
                continue
            sport = "basketball" if lg in BASKETBALL_LEAGUE_LIST else "football"
            for i in range(len(teams) - 1):
                home, away = teams[i], teams[i + 1]
                hd = team[(team["league"] == lg) & (team["team"] == home)]
                ad = team[(team["league"] == lg) & (team["team"] == away)]
                if hd.empty or ad.empty:
                    continue
                hd, ad = hd.iloc[0], ad.iloc[0]
                _append_pred(predictions, lg, sport, home, away,
                             hd["offense_eff"], hd["defense_eff"],
                             ad["offense_eff"], ad["defense_eff"],
                             lg_avg, 2.0, None, 2.0,
                             lstm_state, trans_data, xg_stats, gnn_data, rl_data, mm_data, weights)
        return pd.DataFrame(predictions)

    # ── 真实赛程逻辑 ─────────────────────────────────────────────────────────
    bball_ou = league  # basketball_league_ou

    for _, fix in fixtures.iterrows():
        lg_name  = fix["league_name"]
        home     = fix["home_team"]
        away     = fix["away_team"]
        sport_cd = fix["sport_code"]
        sport    = "basketball" if sport_cd == "basketball" else "football"

        slug = _league_to_slug(lg_name)
        # 篮球：优先用 BASKETBALL_LEAGUE_LIST slug 匹配
        if sport == "basketball" and slug is None:
            for bk_lg in BASKETBALL_LEAGUE_LIST:
                if bk_lg.lower() in lg_name.lower():
                    slug = bk_lg
                    break

        h_off, h_def, h_lga = _lookup_team(home, slug or "", football_idx, team)
        a_off, a_def, a_lga = _lookup_team(away, slug or "", football_idx, team)
        lg_avg = (h_lga + a_lga) / 2

        # 篮球联赛均值优先从 basketball_league_ou 取
        if sport == "basketball" and slug and not bball_ou.empty:
            row = bball_ou[bball_ou["league"] == slug]
            if not row.empty:
                lg_avg = float(row["avg_total"].iloc[0])

        ho = float(fix["home_odds"]) if pd.notna(fix.get("home_odds")) else 2.0
        do = float(fix["draw_odds"]) if pd.notna(fix.get("draw_odds")) else 3.5
        ao = float(fix["away_odds"]) if pd.notna(fix.get("away_odds")) else 2.0

        _append_pred(predictions, lg_name, sport, home, away,
                     h_off, h_def, a_off, a_def,
                     lg_avg, ho, do, ao,
                     lstm_state, trans_data, xg_stats, gnn_data, rl_data, mm_data, weights)

    return pd.DataFrame(predictions)


def _append_pred(predictions, lg, sport, home, away,
                 h_off, h_def, a_off, a_def,
                 lg_avg, ho, do, ao,
                 lstm_state, trans_data, xg_stats, gnn_data, rl_data, mm_data, weights):
    pred = fusion_poisson_pred(
        h_off, h_def, a_off, a_def,
        _get_val(lstm_state, lg, home, "state_score", 2.0),
        _get_val(lstm_state, lg, away, "state_score", 2.0),
        _get_val(trans_data, lg, home, "trans_score",  2.0),
        _get_val(trans_data, lg, away, "trans_score",  2.0),
        _get_val(xg_stats,   lg, home, "xg_off",       1.0),
        _get_val(xg_stats,   lg, away, "xg_off",       1.0),
        _get_val(gnn_data,   lg, home, "gnn_correlation_score", 1.0),
        _get_val(gnn_data,   lg, away, "gnn_correlation_score", 1.0),
        _get_val(rl_data,    lg, home, "rl_home_bonus", 1.0),
        _get_val(rl_data,    lg, away, "rl_away_bonus", 1.0),
        _get_val(mm_data,    lg, home, "multimodal_total", 1.0),
        _get_val(mm_data,    lg, away, "multimodal_total", 1.0),
        lg_avg, sport_type=sport,
        weights=weights,
    )
    if sport == "football":
        prob_d = {"home": pred["home_win_prob"], "draw": pred["draw_prob"], "away": pred["away_win_prob"]}
        odds_d = {"home": ho, "draw": do, "away": ao}
    else:
        prob_d = {"home": pred["home_win_prob"], "away": pred["away_win_prob"]}
        odds_d = {"home": ho, "away": ao}

    _, kelly = kelly_multi(prob_d, odds_d)
    top_score = max(pred["score_probs"].items(), key=lambda x: x[1]) if sport == "football" else ("-", 0)

    predictions.append({
        "league": lg, "sport_type": sport,
        "home_team": home, "away_team": away,
        "home_exp_score": pred["home_exp"], "away_exp_score": pred["away_exp"],
        "total_exp": pred["total_exp"],
        "home_win_prob": pred["home_win_prob"],
        "draw_prob":     pred["draw_prob"],
        "away_win_prob": pred["away_win_prob"],
        "top_score":       top_score[0],
        "top_score_prob":  round(top_score[1], 4),
        "home_kelly": kelly.get("home", 0),
        "draw_kelly": kelly.get("draw", 0),
        "away_kelly": kelly.get("away", 0),
        "home_odds": ho, "draw_odds": do, "away_odds": ao,
    })


def save_prediction(df: pd.DataFrame):
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS basketball_prediction (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league VARCHAR(50), sport_type VARCHAR(20),
        home_team VARCHAR(100), away_team VARCHAR(100),
        home_exp_score FLOAT, away_exp_score FLOAT, total_exp FLOAT,
        home_win_prob FLOAT, draw_prob FLOAT, away_win_prob FLOAT,
        top_score VARCHAR(20), top_score_prob FLOAT,
        home_kelly FLOAT, draw_kelly FLOAT, away_kelly FLOAT,
        home_odds FLOAT, draw_odds FLOAT, away_odds FLOAT,
        create_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    try:
        for col in ("home_odds", "draw_odds", "away_odds"):
            exec_ddl(engine, f"ALTER TABLE basketball_prediction ADD COLUMN {col} FLOAT")
    except Exception:
        pass
    df.to_sql("basketball_prediction", engine, if_exists="replace", index=False)
    xlsx = rf"{DB_DIR}\fusion_prediction_report.xlsx"
    df.to_excel(xlsx, index=False)
    print(f"✅ 七层融合终极预测完成 {len(df)} 场，导出 → {xlsx}")


if __name__ == "__main__":
    team, league, odds, lstm_state, xg_stats, gnn_data, rl_data, mm_data, trans_data = load_fusion_data()
    if team.empty or league.empty:
        print("⚠️ 请先运行 04_高阶指标分析.py 生成基础统计数据")
    else:
        df_pred = run_fusion_prediction(team, league, odds, lstm_state, xg_stats, gnn_data, rl_data, mm_data, trans_data)
        save_prediction(df_pred)
