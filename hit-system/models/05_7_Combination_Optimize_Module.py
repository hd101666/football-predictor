# 05_7_Combination_Optimize_Module.py — 串关优化（2~3 串）
import pandas as pd
from itertools import combinations
from sqlalchemy import create_engine
from db_utils import exec_ddl
from config import DB_ENGINE_URL, DB_DIR, KELLY_MIN_VALUE

engine  = create_engine(DB_ENGINE_URL)
MAX_LEN = 3


def load_high_value(threshold: float = KELLY_MIN_VALUE) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT league, home_team, away_team, sport_type, "
        "home_win_prob, away_win_prob, draw_prob, "
        "home_kelly, away_kelly, draw_kelly FROM basketball_prediction",
        engine,
    )
    mask = (df["home_kelly"] > threshold) | (df["away_kelly"] > threshold) | (df["draw_kelly"].fillna(0) > threshold)
    return df[mask].reset_index(drop=True)


# 庄家固定赔率（现实近似值，独立于模型概率）
BOOK_ODDS_BASKETBALL = {"home": 1.84, "away": 1.84}
BOOK_ODDS_FOOTBALL   = {"home": 2.10, "draw": 3.30, "away": 3.60}


def calc_comb(comb: pd.DataFrame):
    """返回 (模型联合概率, 庄家联串赔率)"""
    joint_prob  = 1.0
    parlay_odds = 1.0
    for _, row in comb.iterrows():
        stype = row.get("sport_type", "football")
        if stype == "football":
            probs    = {"home": row["home_win_prob"],
                        "draw": row.get("draw_prob") or 0,
                        "away": row["away_win_prob"]}
            best_sel = max(probs, key=probs.get)
            joint_prob  *= max(probs[best_sel], 1e-6)
            parlay_odds *= BOOK_ODDS_FOOTBALL.get(best_sel, 2.10)
        else:
            if row["home_win_prob"] >= row["away_win_prob"]:
                joint_prob  *= max(row["home_win_prob"], 1e-6)
                parlay_odds *= BOOK_ODDS_BASKETBALL["home"]
            else:
                joint_prob  *= max(row["away_win_prob"], 1e-6)
                parlay_odds *= BOOK_ODDS_BASKETBALL["away"]
    return joint_prob, parlay_odds


def generate_best_combinations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for length in range(2, MAX_LEN + 1):
        for idx in combinations(df.index, length):
            comb = df.loc[list(idx)]
            joint_prob, parlay_odds = calc_comb(comb)
            if parlay_odds <= 1:
                continue
            comb_kelly = max(0.0, (joint_prob * parlay_odds - 1) / (parlay_odds - 1))
            if comb_kelly > KELLY_MIN_VALUE:
                rows.append({
                    "comb_len":   length,
                    "match_list": " | ".join(
                        f"{r['home_team']}vs{r['away_team']}" for _, r in comb.iterrows()
                    ),
                    "total_odds": round(parlay_odds, 2),
                    "total_prob": round(joint_prob, 4),
                    "comb_kelly": round(comb_kelly, 4),
                })
    if not rows:
        return pd.DataFrame(columns=["comb_len", "match_list", "total_odds", "total_prob", "comb_kelly"])
    return pd.DataFrame(rows).sort_values("comb_kelly", ascending=False)


def save_comb_result(df_comb: pd.DataFrame):
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS combination_result (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comb_len INTEGER, match_list TEXT,
        total_odds FLOAT, total_prob FLOAT, comb_kelly FLOAT,
        update_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    df_comb.to_sql("combination_result", engine, if_exists="replace", index=False)
    xlsx = rf"{DB_DIR}\combination_best_result.xlsx"
    df_comb.to_excel(xlsx, index=False)
    print(f"✅ 串关优化完成，导出 → {xlsx}")


if __name__ == "__main__":
    try:
        df = load_high_value()
        if df.empty:
            print("⚠️ 无高价值预测，请先运行 05_泊松凯利预测模型.py")
        else:
            df_comb = generate_best_combinations(df)
            save_comb_result(df_comb)
    except Exception as e:
        print(f"⚠️ 串关模块异常: {e}")
