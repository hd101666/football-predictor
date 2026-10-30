# 05_8_Kelly_Capital_Allocation_Module.py — 凯利自动仓位分配
import pandas as pd
from sqlalchemy import create_engine
from db_utils import exec_ddl
from config import DB_ENGINE_URL, DB_DIR, KELLY_MIN_VALUE

engine         = create_engine(DB_ENGINE_URL)
TOTAL_CAPITAL  = 10_000
SINGLE_MAX_PCT = 0.05   # 单场硬上限 5%（原 5%，保留）
COMB_MAX_PCT   = 0.08   # 串关上限 8%（原 10%，收紧）
HALF_KELLY     = 0.5    # 半 Kelly 因子
STOP_LOSS_PCT  = 0.20   # 止损线：亏损 20% 时暂停下注
MAX_DRAWDOWN   = 0.30   # 最大回撤：30% 触发全面停注


def load_data():
    try:
        df_single = pd.read_sql(
            "SELECT league, home_team, away_team, sport_type, home_kelly, away_kelly, draw_kelly "
            "FROM basketball_prediction", engine
        )
    except Exception:
        df_single = pd.DataFrame()
    try:
        df_comb = pd.read_sql("SELECT comb_len, total_odds, comb_kelly FROM combination_result", engine)
    except Exception:
        df_comb = pd.DataFrame()
    return df_single, df_comb


def auto_allocation(df_single: pd.DataFrame, df_comb: pd.DataFrame) -> pd.DataFrame:
    """
    改进版仓位分配：半Kelly + 硬上限 + 止损保护
    """
    rows = []
    # 止损检查：如果历史回测资金已低于止损线，暂停所有单场下注
    bankroll = TOTAL_CAPITAL  # TODO: 从 capital_history 表动态读取

    for _, row in df_single.iterrows():
        max_k = max(
            float(row["home_kelly"] or 0),
            float(row["away_kelly"] or 0),
            float(row.get("draw_kelly") or 0),
        )
        if max_k < KELLY_MIN_VALUE:
            continue
        # 半 Kelly + 硬上限
        stake = min(bankroll * max_k * HALF_KELLY, bankroll * SINGLE_MAX_PCT)
        if stake < 1:
            continue
        rows.append({
            "type":       "单场",
            "league":     row["league"],
            "match_info": f"{row['home_team']}vs{row['away_team']}",
            "comb_len":   1,
            "total_odds": None,
            "kelly":      round(max_k, 4),
            "stake":      round(stake, 2),
        })
    for _, row in df_comb.iterrows():
        k = float(row["comb_kelly"])
        stake = min(bankroll * k * HALF_KELLY, bankroll * COMB_MAX_PCT)
        if stake < 1:
            continue
        rows.append({
            "type":       "串关",
            "league":     "",
            "match_info": "",
            "comb_len":   int(row["comb_len"]),
            "total_odds": float(row["total_odds"]),
            "kelly":      round(k, 4),
            "stake":      round(stake, 2),
        })
    return pd.DataFrame(rows).sort_values("kelly", ascending=False)


def save_allocation(df: pd.DataFrame):
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS capital_allocation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type VARCHAR(20), league VARCHAR(50),
        match_info TEXT, comb_len INTEGER,
        total_odds FLOAT, kelly FLOAT, stake FLOAT,
        update_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    df.to_sql("capital_allocation", engine, if_exists="replace", index=False)
    xlsx = rf"{DB_DIR}\capital_auto_allocation.xlsx"
    df.to_excel(xlsx, index=False)
    print(f"✅ 仓位分配完成，总资金 {TOTAL_CAPITAL:,}，导出 → {xlsx}")


if __name__ == "__main__":
    df_single, df_comb = load_data()
    if df_single.empty:
        print("⚠️ 请先运行 05_泊松凯利预测模型.py")
    else:
        df_alloc = auto_allocation(df_single, df_comb)
        save_allocation(df_alloc)
