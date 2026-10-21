# 05b_国家队预测适配层.py
"""
国家队预测适配层 — 衔接 national_team_elo + statsbomb_national_xg 到预测模型。
在 05_泊松凯利预测模型.py 的七层融合架构基础上，专门处理国家队/世界杯赛事。

对接表：
  - national_team_elo          → Elo 评分（替代 LSTM/Transformer 状态）
  - statsbomb_national_xg_teams → xG 数据
  - statsbomb_national_xg_matches → 历史比赛 xG
  - theodds_odds / pinnacle_odds → 赔率

输出写入 prediction_snapshot 表，与俱乐部模型同一格式。
"""

import pandas as pd
import numpy as np
from datetime import date, datetime, timezone
from scipy.stats import poisson
from sqlalchemy import create_engine, text
from db_utils import exec_ddl
from config import (
    DB_ENGINE_URL, DB_DIR,
    WEIGHT_POISSON, WEIGHT_LSTM, WEIGHT_TRANSFORMER,
    WEIGHT_XG, WEIGHT_GNN, WEIGHT_RL, WEIGHT_MULTIMODAL,
    KELLY_FRACTION, KELLY_MAX_RATIO, KELLY_MIN_VALUE,
)

engine = create_engine(DB_ENGINE_URL)

# ── 本期世界杯比赛（第26085期，暂存已知比赛列表）──────────────
# 后续可改为从 unified_matches 自动读取
WORLD_CUP_MATCHES_26085 = [
    # (序号, home, away, utc_time)
    # 注意：下面用系统 unified_id 和标准球队名
    # 实际运行时会从 unified_matches 自动拉取
]


def _safe_load(sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(sql, engine)
    except Exception:
        return pd.DataFrame()


def load_national_data():
    """加载国家队相关数据"""
    elo = _safe_load("SELECT * FROM national_team_elo")
    
    xg_teams = _safe_load("""
        SELECT team_name, competition_name, season_name,
               avg_xg, avg_xga, matches_played
        FROM statsbomb_national_xg_teams
    """)
    
    xg_matches = _safe_load("""
        SELECT match_date, home_team, away_team,
               home_xg, away_xg, home_score, away_score,
               competition_name
        FROM statsbomb_national_xg_matches
        WHERE match_date >= '2022-01-01'
        ORDER BY match_date DESC
    """)
    
    print(f"  Elo: {len(elo)} 支国家队")
    print(f"  xG球队: {len(xg_teams)} 条记录")
    print(f"  历史xG比赛: {len(xg_matches)} 场")
    return elo, xg_teams, xg_matches


def load_worldcup_fixtures():
    """从 unified_matches 加载世界杯 pending 场次（赔率用体彩官方数据）"""
    today = date.today().isoformat()
    
    # 读3天内的世界杯比赛
    fixtures = _safe_load("""
        SELECT CAST(um.id AS TEXT) AS unified_id, um.home_team_std, um.away_team_std,
               um.kickoff_utc, um.status,
               um.sources_json
        FROM unified_matches um
        WHERE um.league_name = 'FIFA - World Cup'
          AND um.kickoff_utc >= datetime('now', '-1 day')
          AND um.kickoff_utc < datetime('now', '+7 days')
          AND home_team_std != ''
          AND away_team_std != ''
          AND home_team_std NOT LIKE '%(Bookings)%'  -- 去掉牌的赔率
        ORDER BY um.kickoff_utc
    """)
    
    if fixtures.empty:
        print("  未找到世界杯比赛")
        return fixtures
    
    # 使用体彩官方赔率（用户提供的第26085期数据）
    # (home_team, away_team, home_odds, draw_odds, away_odds)
    official_odds = {
        ("Mexico", "South Africa"): (1.43, 4.37, 8.07),
        ("South Korea", "Czechia"): (2.67, 3.07, 2.82),
        ("Canada", "Bosnia and Herzegovina"): (1.84, 3.49, 4.45),
        ("USA", "Paraguay"): (1.94, 3.40, 4.03),
        ("Qatar", "Switzerland"): (12.30, 6.16, 1.23),
        ("Brazil", "Morocco"): (1.63, 3.80, 5.46),
        ("Haiti", "Scotland"): (6.21, 4.32, 1.50),
        ("Australia", "Turkiye"): (5.01, 3.70, 1.71),
        ("Netherlands", "Japan"): (2.00, 3.51, 3.63),
        ("Ivory Coast", "Ecuador"): (3.46, 2.86, 2.37),
        ("Sweden", "Tunisia"): (1.90, 3.36, 4.23),
        ("Spain", "Cape Verde"): (1.09, 10.58, 25.22),
        ("Belgium", "Egypt"): (1.63, 3.87, 5.31),
        ("Saudi Arabia", "Uruguay"): (7.20, 4.28, 1.46),
    }
    
    for idx, fix in fixtures.iterrows():
        home = fix["home_team_std"]
        away = fix["away_team_std"]
        
        # 去掉 (Bookings) 后缀
        home_clean = home.replace(" (Bookings)", "")
        away_clean = away.replace(" (Bookings)", "")
        
        # 匹配
        key = (home_clean, away_clean)
        key_rev = (away_clean, home_clean)
        
        odds = official_odds.get(key) or official_odds.get(key_rev)
        if odds:
            fixtures.at[idx, "home_odds"] = odds[0]
            fixtures.at[idx, "draw_odds"] = odds[1]
            fixtures.at[idx, "away_odds"] = odds[2]
        else:
            # 尝试模糊匹配
            for (h, a), o in official_odds.items():
                if (home_clean.lower() in h.lower() or h.lower() in home_clean.lower()) and \
                   (away_clean.lower() in a.lower() or a.lower() in away_clean.lower()):
                    fixtures.at[idx, "home_odds"] = o[0]
                    fixtures.at[idx, "draw_odds"] = o[1]
                    fixtures.at[idx, "away_odds"] = o[2]
                    break
    
    has_odds = fixtures["home_odds"].notna().sum()
    print(f"  世界杯赛程: {len(fixtures)} 场 (有赔率: {has_odds})")
    return fixtures


def get_team_xg(team_name: str, xg_teams: pd.DataFrame) -> dict:
    """获取球队的 xG 数据，从多个赛事中取最新/最相关的"""
    if xg_teams.empty:
        return {"avg_xg": None, "avg_xga": None, "matches": 0, "source": None}
    
    team_lower = team_name.lower().strip()
    
    # 优先匹配 exact name
    row = xg_teams[xg_teams["team_name"].str.lower() == team_lower]
    
    # 模糊匹配
    if row.empty:
        mask = xg_teams["team_name"].str.lower().str.contains(team_lower, na=False)
        if mask.any():
            row = xg_teams[mask]
    
    if not row.empty:
        # 如果有多个赛事，按优先级取：FIFA World Cup > UEFA Euro > Copa America
        priority = {"FIFA World Cup": 0, "UEFA Euro": 1, "Copa America": 2}
        row = row.copy()
        row["_priority"] = row["competition_name"].map(priority).fillna(5)
        row = row.sort_values("_priority")
        best = row.iloc[0]
        return {
            "avg_xg": float(best["avg_xg"]),
            "avg_xga": float(best["avg_xga"]),
            "matches": int(best["matches_played"]),
            "source": best["competition_name"],
        }
    
    return {"avg_xg": None, "avg_xga": None, "matches": 0, "source": None}


def get_team_elo(team_name: str, elo: pd.DataFrame) -> float:
    """获取球队 Elo 评分"""
    if elo.empty:
        return 1500.0  # 默认中位数
    
    team_lower = team_name.lower().strip()
    row = elo[elo["team_name"].str.lower() == team_lower]
    
    if row.empty:
        # 模糊匹配（处理 Turkey vs Turkiye 等差异）
        mask = elo["team_name"].str.lower().str.contains(team_lower, na=False)
        if mask.any():
            row = elo[mask]
    
    if not row.empty:
        return float(row.iloc[0]["elo_rating"])
    
    return 1500.0  # 默认


def elo_to_exp_goals(home_elo: float, away_elo: float, base_avg: float = 2.5) -> tuple:
    """
    Elo 评分 → 预期进球
    使用经典 Elo 足球模型：
      expected_home = base_avg/2 * home_elo / (home_elo + away_elo) * 2
      即按 Elo 力量比分配预期进球
    """
    total = home_elo + away_elo
    if total <= 0:
        return base_avg / 2, base_avg / 2
    
    # Elo 强度比
    home_strength = home_elo / total
    away_strength = away_elo / total
    
    # 主场优势系数（世界杯无真实主场，但系统有主客标识）
    home_advantage = 1.10
    
    # 分配预期进球
    home_exp = base_avg * home_strength * home_advantage
    away_exp = base_avg * away_strength / home_advantage
    
    return home_exp, away_exp


def adjust_with_xg(home_exp: float, away_exp: float,
                   home_xg: dict, away_xg: dict,
                   xg_weight: float = 0.30) -> tuple:
    """
    用 xG 数据微调 Elo 预期进球
    xg_weight: xG 的权重（剩下1-xg_weight给 Elo）
    """
    if home_xg["avg_xg"] is None or away_xg["avg_xg"] is None:
        return home_exp, away_exp
    
    # 将 xG 转换为标准化比率（相对于联赛均值）
    # 用两队 xG/xGA 比率调整预期进球
    # 简单的做法：用 xG 差值修正
    
    # 按每队 xG 能力调整
    # 保守调整：最多修正 ±20%
    xg_home_adj = (home_xg["avg_xg"] - away_xg["avg_xga"]) / 2.5  # 相对2.5基准
    xg_away_adj = (away_xg["avg_xg"] - home_xg["avg_xga"]) / 2.5
    
    # 限制调整幅度
    xg_home_adj = max(-0.20, min(0.20, xg_home_adj))
    xg_away_adj = max(-0.20, min(0.20, xg_away_adj))
    
    home_adj = home_exp * (1 + xg_home_adj * xg_weight)
    away_adj = away_exp * (1 + xg_away_adj * xg_weight)
    
    return home_adj, away_adj


def poisson_probs(home_exp: float, away_exp: float, max_goals: int = 8) -> dict:
    """泊松分布计算胜平负概率"""
    hp = [poisson.pmf(i, home_exp) for i in range(max_goals + 1)]
    ap = [poisson.pmf(i, away_exp) for i in range(max_goals + 1)]
    
    home_win = draw = away_win = 0.0
    score_probs = {}
    
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = hp[h] * ap[a]
            score_probs[f"{h}-{a}"] = p
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
    
    total = home_win + draw + away_win
    if total > 0:
        home_win /= total
        draw /= total
        away_win /= total
    
    return {
        "home_win_prob": round(home_win, 4),
        "draw_prob": round(draw, 4),
        "away_win_prob": round(away_win, 4),
        "home_exp": round(home_exp, 2),
        "away_exp": round(away_exp, 2),
        "total_exp": round(home_exp + away_exp, 2),
    }


def calc_kelly(prob: float, odds: float) -> dict:
    """
    13命中13场 K值标准公式

    K = (p × o - 1) / (o - 1)
    K_1/4 = K × 0.25

    返回:
      k: 基础 Kelly（仓位比例，0~1）
      k_quarter: 1/4 Kelly
      ev: 期望值 (p×o - 1)
    """
    if odds <= 1 or prob <= 0:
        return {"k": 0.0, "k_quarter": 0.0, "ev": 0.0}

    ev = prob * odds - 1
    if ev <= 0:
        return {"k": 0.0, "k_quarter": 0.0, "ev": round(ev, 4)}

    k = max(0, (prob * odds - 1) / (odds - 1))
    k_quarter = k * 0.25

    # 硬上限：单注仓位不超过本金的25%
    k = min(k, 0.25)
    k_quarter = min(k_quarter, 0.25)

    return {
        "k": round(k, 4),
        "k_quarter": round(k_quarter, 4),
        "ev": round(ev, 4),
    }


def fusion_prob(book_prob: float, poisson_prob: float, elo_adjustment: float = 0.0) -> float:
    """
    13命中13场标准融合概率口径

    p_fusion = 0.50 × P_book + 0.30 × P_poisson + 0.20 × P_elo

    其中：
      P_book   = 庄家隐含概率（1/赔率，含抽水修正）
      P_poisson = 泊松模型概率
      P_elo    = Elo 模型概率（当前简化为泊松基础上的 Elo 调整偏移）
    """
    p = 0.50 * book_prob + 0.30 * poisson_prob + 0.20 * elo_adjustment
    return min(max(p, 0.01), 0.99)


def predict_match(home_team: str, away_team: str,
                  home_odds: float, draw_odds: float, away_odds: float,
                  elo: pd.DataFrame, xg_teams: pd.DataFrame) -> dict:
    """预测一场国家队比赛（13命中13场 K值标准）"""

    # 1. 庄家隐含概率（含抽水修正）
    total_implied = 0
    implied = {"home": 0, "draw": 0, "away": 0}
    for label, o in [("home", home_odds), ("draw", draw_odds), ("away", away_odds)]:
        if o and o > 1:
            implied[label] = 1.0 / o
            total_implied += 1.0 / o

    # 抽水修正：归一化使概率之和=1
    if total_implied > 0:
        for label in implied:
            implied[label] = implied[label] / total_implied

    # 2. Poisson 概率（基于 Elo 预期进球）
    home_elo = get_team_elo(home_team, elo)
    away_elo = get_team_elo(away_team, elo)
    home_exp, away_exp = elo_to_exp_goals(home_elo, away_elo)

    # xG 微调预期进球
    home_xg = get_team_xg(home_team, xg_teams)
    away_xg = get_team_xg(away_team, xg_teams)
    home_exp, away_exp = adjust_with_xg(home_exp, away_exp, home_xg, away_xg)

    poisson_probs_result = poisson_probs(home_exp, away_exp)
    p_poisson = {
        "home": poisson_probs_result["home_win_prob"],
        "draw": poisson_probs_result["draw_prob"],
        "away": poisson_probs_result["away_win_prob"],
    }

    # 3. Elo 调整概率（作为 P_elo 的输入）
    # 将 Elo 差值映射为概率调整：Elo 差每100分 ≈ 5% 概率偏移
    elo_diff = home_elo - away_elo
    elo_shift = max(-0.15, min(0.15, elo_diff / 2000))

    p_elo = {
        "home": max(0.01, min(0.99, p_poisson["home"] + elo_shift)),
        "draw": p_poisson["draw"],  # 平局不受 Elo 方向偏移影响
        "away": max(0.01, min(0.99, p_poisson["away"] - elo_shift)),
    }

    # 4. 融合概率 p_fusion = 0.50×P_book + 0.30×P_poisson + 0.20×P_elo
    p_fusion = {}
    for label in ["home", "draw", "away"]:
        p_fusion[label] = fusion_prob(implied[label], p_poisson[label], p_elo[label])

    # 归一化确保和为1
    total_p = sum(p_fusion.values())
    if total_p > 0:
        for label in p_fusion:
            p_fusion[label] = p_fusion[label] / total_p

    # 5. 标准 Kelly 计算（使用融合概率）
    odds_map = {"home": home_odds, "draw": draw_odds, "away": away_odds}
    kelly_results = {}
    for label in ["home", "draw", "away"]:
        o = odds_map[label]
        if o and o > 1:
            kelly_results[label] = calc_kelly(p_fusion[label], o)
        else:
            kelly_results[label] = {"k": 0.0, "k_quarter": 0.0, "ev": 0.0}

    # 6. 最佳方向（按1/4 Kelly排序）
    best_dir = max(kelly_results, key=lambda d: kelly_results[d]["k_quarter"])
    best_k = kelly_results[best_dir]["k"]
    best_k_quarter = kelly_results[best_dir]["k_quarter"]
    best_ev = kelly_results[best_dir]["ev"]

    # 最可能方向（融合概率最大方向，供足彩参考）
    likeliest_dir = max(p_fusion, key=lambda d: p_fusion[d])
    likeliest_prob = p_fusion[likeliest_dir]

    # 7. 信心等级（按1/4 Kelly）
    if best_k_quarter >= 0.05:
        confidence = "A级 (强信心)"
    elif best_k_quarter >= 0.02:
        confidence = "B级 (中等信心)"
    elif best_k_quarter > 0:
        confidence = "C级 (弱信心)"
    else:
        confidence = "D级 (无价值)"

    pick_label_map = {"home": "主胜", "draw": "平局", "away": "客胜"}

    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_elo": home_elo,
        "away_elo": away_elo,
        "home_xg": home_xg,
        "away_xg": away_xg,
        "home_exp": poisson_probs_result["home_exp"],
        "away_exp": poisson_probs_result["away_exp"],
        "total_exp": poisson_probs_result["total_exp"],
        # 三种概率口径
        "p_book_home": implied["home"],
        "p_book_draw": implied["draw"],
        "p_book_away": implied["away"],
        "p_poisson_home": p_poisson["home"],
        "p_poisson_draw": p_poisson["draw"],
        "p_poisson_away": p_poisson["away"],
        "p_elo_home": p_elo["home"],
        "p_elo_draw": p_elo["draw"],
        "p_elo_away": p_elo["away"],
        # 融合概率 p_fusion
        "home_win_prob": round(p_fusion["home"], 4),
        "draw_prob": round(p_fusion["draw"], 4),
        "away_win_prob": round(p_fusion["away"], 4),
        # Kelly 结果
        "home_kelly": kelly_results["home"]["k"],
        "home_kelly_quarter": kelly_results["home"]["k_quarter"],
        "home_ev": kelly_results["home"]["ev"],
        "draw_kelly": kelly_results["draw"]["k"],
        "draw_kelly_quarter": kelly_results["draw"]["k_quarter"],
        "draw_ev": kelly_results["draw"]["ev"],
        "away_kelly": kelly_results["away"]["k"],
        "away_kelly_quarter": kelly_results["away"]["k_quarter"],
        "away_ev": kelly_results["away"]["ev"],
        # 最佳方向（按1/4 Kelly）
        "best_pick": best_dir,
        "best_pick_label": pick_label_map.get(best_dir, best_dir),
        "best_prob": p_fusion[best_dir],
        "best_odds": odds_map[best_dir] or 2.0,
        "best_kelly": best_k,
        "best_kelly_quarter": best_k_quarter,
        "best_ev": best_ev,
        # 最可能方向（供足彩参考）
        "likeliest_pick": likeliest_dir,
        "likeliest_pick_label": pick_label_map.get(likeliest_dir, likeliest_dir),
        "likeliest_prob": likeliest_prob,
        # 信心
        "confidence": confidence,
        # 标注
        "prob_formula": "p_fusion = 0.50*P_book + 0.30*P_poisson + 0.20*P_elo",
        "kelly_formula": "K = (p*o-1)/(o-1), K_1/4 = K*0.25",
        "odds_source": "13场体彩官方数据",
    }


def save_to_prediction_snapshot(results: list, run_tag: str = "national_prediction"):
    """将预测结果写入 prediction_snapshot 表"""
    if not results:
        print("  无预测结果可写入")
        return
    
    # 确保表结构
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS prediction_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id_internal TEXT,
            sport_code TEXT,
            league_code TEXT,
            source_name TEXT,
            home_team_id TEXT,
            away_team_id TEXT,
            home_team_name_std TEXT,
            away_team_name_std TEXT,
            best_pick TEXT,
            best_prob FLOAT,
            best_odds FLOAT,
            best_kelly FLOAT,
            home_win_prob FLOAT,
            draw_prob FLOAT,
            away_win_prob FLOAT,
            home_exp_score FLOAT,
            away_exp_score FLOAT,
            total_exp FLOAT,
            confidence_grade TEXT,
            odds_source TEXT,
            run_tag TEXT,
            actual_result TEXT,
            is_hit INTEGER DEFAULT 0,
            actual_home_score INTEGER,
            actual_away_score INTEGER,
            result_verified_at TEXT,
            match_date TEXT
        )
    """)
    
    rows = []
    for r in results:
        pick_label = r.get("best_pick_label", {"home": "主胜", "draw": "平局", "away": "客胜"}.get(r["best_pick"], r["best_pick"]))
        rows.append({
            "match_id_internal": r.get("unified_id", str(r["home_team"])),
            "sport_code": "football",
            "league_code": "fifa_world_cup",
            "source_name": "national_adaptation_layer",
            "home_team_name_std": r["home_team"],
            "away_team_name_std": r["away_team"],
            "best_pick": pick_label,
            "best_prob": r["best_prob"],
            "best_odds": r["best_odds"],
            "best_kelly": r["best_kelly_quarter"],  # 使用 1/4 Kelly
            "home_win_prob": r["home_win_prob"],
            "draw_prob": r["draw_prob"],
            "away_win_prob": r["away_win_prob"],
            "home_exp_score": r["home_exp"],
            "away_exp_score": r["away_exp"],
            "total_exp": r["total_exp"],
            "confidence_grade": f"{r['confidence']} (ev={r['best_ev']:.1%}, K_1/4={r['best_kelly_quarter']:.2%})",
            "odds_source": "13场体彩官方数据",
            "run_tag": run_tag,
            "match_date": date.today().isoformat(),
        })
    
    df = pd.DataFrame(rows)
    # 删除该 run_tag 的旧数据
    try:
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM prediction_snapshot WHERE run_tag = '{run_tag}'"))
            conn.commit()
    except Exception:
        pass
    
    df.to_sql("prediction_snapshot", engine, if_exists="append", index=False)
    print(f"  写入 prediction_snapshot: {len(rows)} 条 (run_tag={run_tag})")


def run_national_prediction(run_tag: str = "national_prediction"):
    """主入口：运行国家队预测流程"""
    print("=" * 60)
    print(f"国家队预测适配层 — {run_tag}")
    print("=" * 60)
    
    # 1. 加载数据
    print("\n加载数据...")
    elo, xg_teams, xg_matches = load_national_data()
    
    # 2. 加载赛程
    print("\n加载赛程...")
    fixtures = load_worldcup_fixtures()
    
    if fixtures.empty:
        print("  无赛程数据，退出")
        return
    
    # 3. 逐场预测
    print("\n预测中...")
    results = []
    for _, fix in fixtures.iterrows():
        home = fix["home_team_std"]
        away = fix["away_team_std"]
        ho = float(fix["home_odds"]) if pd.notna(fix.get("home_odds")) else None
        do = float(fix["draw_odds"]) if pd.notna(fix.get("draw_odds")) else None
        ao = float(fix["away_odds"]) if pd.notna(fix.get("away_odds")) else None
        
        print(f"  {home} vs {away}: ", end="")
        
        pred = predict_match(home, away, ho, do, ao, elo, xg_teams)
        pred["unified_id"] = str(fix["unified_id"])
        
        # 打印摘要
        ev_str = f"EV={pred['best_ev']:.1%}"
        print(f"{pred['best_pick_label']} @ {pred['best_odds']:.2f} "
              f"(p_fusion: H={pred['home_win_prob']:.1%} D={pred['draw_prob']:.1%} A={pred['away_win_prob']:.1%}) "
              f"| {pred['confidence']} | {ev_str} | K_1/4={pred['best_kelly_quarter']:.2%}")
        
        results.append(pred)
    
    # 4. 保存
    print(f"\n保存结果...")
    save_to_prediction_snapshot(results, run_tag)
    
    # 5. 汇总
    print(f"\n汇总:")
    ev_positive = sum(1 for r in results if r["best_ev"] > 0.03)
    print(f"  总场次: {len(results)}")
    print(f"  EV>=+3%: {ev_positive} 场")
    
    for r in results:
        if r["best_ev"] > 0.03:
            print(f"  VALUE {r['home_team']} vs {r['away_team']}: "
                  f"{r['best_pick_label']} @ {r['best_odds']:.2f} "
                  f"(p_fusion={r['best_prob']:.1%}, K_1/4={r['best_kelly_quarter']:.2%}, EV={r['best_ev']:.1%})")
    
    # 按 1/4 Kelly 排序输出
    sorted_results = sorted(results, key=lambda r: r["best_kelly_quarter"], reverse=True)
    print(f"\n按 K_1/4 排序:")
    for r in sorted_results:
        if r["best_kelly_quarter"] > 0:
            print(f"  {r['home_team']:25s} vs {r['away_team']:25s} | "
                  f"{r['best_pick_label']:4s} @ {r['best_odds']:.2f} | "
                  f"K_1/4={r['best_kelly_quarter']:.2%} | "
                  f"EV={r['best_ev']:.1%} | "
                  f"p_fusion={r['best_prob']:.1%} | "
                  f"{r['confidence']}")
    
    print("\n完成")


if __name__ == "__main__":
    run_national_prediction()
