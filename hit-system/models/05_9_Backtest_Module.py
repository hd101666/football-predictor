# 05_9_Backtest_Module.py — 历史回测（凯利策略）
# 覆盖足球+篮球，使用真实赔率，支持日期过滤
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from db_utils import exec_ddl
from config import DB_ENGINE_URL, DB_DIR, KELLY_MAX_RATIO

engine       = create_engine(DB_ENGINE_URL)
INIT_CAPITAL = 10_000
ODDS_MARGIN  = 0.92


def load_backtest_data(lookback_days: int = 30) -> pd.DataFrame:
    \"\"\"从 prediction_snapshot 加载有赛果的预测记录。\"\"\"
    since = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    sql = """
    SELECT
        ps.sport_code,
        ps.league_code,
        ps.match_date,
        ps.home_team_name_std AS home_team,
        ps.away_team_name_std AS away_team,
        ps.best_pick,
        ps.best_prob,
        ps.best_odds,
        ps.best_kelly,
        ps.home_win_prob,
        ps.draw_prob,
        ps.away_win_prob,
        ps.is_hit,
        ps.actual_result,
        ps.actual_home_score,
        ps.actual_away_score,
        ps.confidence_grade
    FROM prediction_snapshot ps
    WHERE ps.is_hit IS NOT NULL
      AND ps.match_date >= :since
    ORDER BY ps.match_date ASC
    """
    return pd.read_sql(text(sql), engine, params={"since": since})


def calc_backtest_metrics(df: pd.DataFrame):
    capital      = float(INIT_CAPITAL)
    capital_list = [capital]
    win_count    = total_count = 0
    profits      = []
    details      = []

    for _, row in df.iterrows():
        hs = pd.to_numeric(row.get("actual_home_score"), errors="coerce")
        as_ = pd.to_numeric(row.get("actual_away_score"), errors="coerce")
        if pd.isna(hs) or pd.isna(as_):
            continue

        # 确认实际结果
        if hs > as_:
            actual = "主胜"
        elif hs < as_:
            actual = "客胜"
        else:
            actual = "平局"

        best_pick = str(row.get("best_pick", ""))
        if not best_pick:
            continue

        probs = {
            "主胜": float(row.get("home_win_prob", 0) or 0),
            "客胜": float(row.get("away_win_prob", 0) or 0),
        }
        if row.get("draw_prob") is not None:
            probs["平局"] = float(row.get("draw_prob", 0) or 0)

        # 真实赔率优先，fallback 用默认值
        best_odds = float(row.get("best_odds", 0) or 0)
        if best_odds <= 1:
            # 从 pick 推断赔率
            sport_code = str(row.get("sport_code", "football"))
            if best_pick == "主胜":
                best_odds = 2.10 if sport_code == "football" else 1.90
            elif best_pick == "客胜":
                best_odds = 3.60 if sport_code == "football" else 1.90
            else:
                best_odds = 3.30

        p_pred = probs.get(best_pick, 0)
        used_real_odds = float(row.get("best_odds", 0) or 0) > 1

        # 凯利
        kelly_f = max(0.0, min((p_pred * best_odds - 1) / (best_odds - 1), KELLY_MAX_RATIO))
        stake   = capital * kelly_f if kelly_f > 0 else 0
        is_win = best_pick == actual
        profit = stake * (best_odds - 1) if is_win else -stake
        capital += profit
        capital_list.append(capital)
        profits.append(profit)
        if is_win:
            win_count += 1
        total_count += 1

        details.append({
            "match_date": row.get("match_date"),
            "sport": str(row.get("sport_code", "")),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "pick": best_pick,
            "prob": p_pred,
            "odds": best_odds,
            "actual": actual,
            "is_win": is_win,
            "profit": round(profit, 2),
            "used_real_odds": used_real_odds,
        })

    if total_count == 0:
        print("⚠️ 无可回测数据（prediction_snapshot 中无已回写命中记录）")
        print("   ➜ 请先运行 run_today_prediction.py 产生预测并等待命中回写")
        return pd.DataFrame(), pd.DataFrame()

    win_rate     = win_count / max(total_count, 1)
    cap_arr      = np.array(capital_list)
    peak         = np.maximum.accumulate(cap_arr)
    max_drawdown = float(((cap_arr - peak) / (peak + 1e-9)).min()) if len(cap_arr) > 1 else 0.0
    returns      = np.diff(cap_arr) / (np.abs(cap_arr[:-1]) + 1e-9)
    sharpe       = float(np.mean(returns) / (np.std(returns) + 1e-9)) if len(returns) > 0 else 0.0

    summary = pd.DataFrame([{
        "total_match":      total_count,
        "win_count":        win_count,
        "win_rate":         round(win_rate, 4),
        "sports":           f"足球{df[df['sport_code']=='football'].shape[0]}场/篮球{df[df['sport_code']=='basketball'].shape[0]}场",
        "real_odds_count":  sum(1 for d in details if d["used_real_odds"]),
        "initial_capital":  INIT_CAPITAL,
        "final_capital":    round(capital, 2),
        "total_profit":     round(capital - INIT_CAPITAL, 2),
        "max_drawdown":     round(max_drawdown, 4),
        "sharpe_ratio":     round(sharpe, 4),
    }])
    curve = pd.DataFrame({"capital_curve": capital_list})
    detail_df = pd.DataFrame(details)
    return summary, curve, detail_df


def save_backtest_result(summary: pd.DataFrame, curve: pd.DataFrame, detail_df: pd.DataFrame):
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS backtest_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_match INTEGER, win_count INTEGER, win_rate FLOAT,
        sports TEXT, real_odds_count INTEGER,
        initial_capital FLOAT, final_capital FLOAT,
        total_profit FLOAT, max_drawdown FLOAT, sharpe_ratio FLOAT,
        update_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS backtest_curve (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        capital_curve FLOAT
    )""")
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS backtest_detail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_date TEXT, sport TEXT, home_team TEXT, away_team TEXT,
        pick TEXT, prob FLOAT, odds FLOAT, actual TEXT,
        is_win INTEGER, profit FLOAT, used_real_odds INTEGER
    )""")
    # 追加而非覆盖，保留历史
    summary.to_sql("backtest_summary", engine, if_exists="append", index=False)
    curve.to_sql("backtest_curve", engine, if_exists="append", index=False)
    if not detail_df.empty:
        detail_df.to_sql("backtest_detail", engine, if_exists="append", index=False)
    xlsx = rf"{DB_DIR}\backtest_report.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="回测摘要", index=False)
        curve.to_excel(w, sheet_name="资金曲线", index=False)
        if not detail_df.empty:
            detail_df.to_excel(w, sheet_name="明细", index=False)
    print(f"✅ 历史回测完成，导出 → {xlsx}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    import sys
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    try:
        df = load_backtest_data(lookback)
        if df.empty:
            print("⚠️ 无法匹配比赛结果与预测数据，请确认 prediction_snapshot 中有命中回写记录")
        else:
            summary, curve, detail_df = calc_backtest_metrics(df)
            if not summary.empty:
                save_backtest_result(summary, curve, detail_df)
    except Exception as e:
        print(f"⚠️ 回测模块异常: {e}")
        import traceback; traceback.print_exc()
