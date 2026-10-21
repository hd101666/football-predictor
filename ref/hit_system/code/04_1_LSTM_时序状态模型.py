# -*- coding: utf-8 -*-
# 04_1_LSTM_时序状态模型.py
# 纯 NumPy/SciPy 实现：EMA + AR(1) 自回归模型替代 LSTM
# 保持相同的 team_lstm_state 表结构和 import 接口
import sys
import numpy as np
from scipy import linalg

try:
    from config import DB_ENGINE_URL, LSTM_SEQ_LENGTH
except ImportError:
    DB_ENGINE_URL = "sqlite:///data/sports_data.db"
    LSTM_SEQ_LENGTH = 10

# STATE_LEVEL 可能在 config.py 中缺失，提供内置 fallback
try:
    from config import STATE_LEVEL
except ImportError:
    STATE_LEVEL = {0: "低谷", 1: "回暖", 2: "稳定", 3: "强势", 4: "巅峰"}

try:
    from db_utils import exec_ddl
except ImportError:
    def exec_ddl(engine, sql: str):
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text(sql))

from sqlalchemy import create_engine
import pandas as pd

engine = create_engine(DB_ENGINE_URL)

# ── EMA 平滑参数 ──
EMA_ALPHA = 0.3          # 近期权重（越大越重近期表现）
EMA_WARMUP = 3           # 至少需要几场才启用 EMA，否则用简单均值


# ═══════════════════════════════════════════════════════════════
# 1. 数据加载 —— 篮球 + 足球统一
# ═══════════════════════════════════════════════════════════════
def _melt_matches(table: str) -> pd.DataFrame:
    """从一张 matches 表中读取并 melt 为 (league, team, date, diff) 长格式"""
    try:
        df = pd.read_sql(
            f"SELECT league, home_team, away_team, home_score, away_score, match_date "
            f"FROM {table}",
            engine,
        )
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    df["home_diff"] = df["home_score"] - df["away_score"]
    df["away_diff"] = df["away_score"] - df["home_score"]

    rows = []
    for _, r in df.iterrows():
        rows.append({"league": r["league"], "team": r["home_team"],
                      "date": r["match_date"], "diff": r["home_diff"]})
        rows.append({"league": r["league"], "team": r["away_team"],
                      "date": r["match_date"], "diff": r["away_diff"]})
    return pd.DataFrame(rows)


def load_team_match_data() -> pd.DataFrame:
    """加载篮球 + 足球全部比赛数据，返回按 (league, team, date) 排序的长表"""
    parts = []
    for tbl in ("basketball_matches", "football_matches"):
        part = _melt_matches(tbl)
        if not part.empty:
            parts.append(part)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    return df.sort_values(["league", "team", "date"]).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════
# 2. EMA 计算 —— 指数加权移动平均
# ═══════════════════════════════════════════════════════════════
def _ema(series: np.ndarray, alpha: float = EMA_ALPHA) -> np.ndarray:
    """向前递推 EMA，返回与输入等长的数组"""
    if len(series) == 0:
        return series
    out = np.empty_like(series, dtype=float)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = alpha * series[i] + (1 - alpha) * out[i - 1]
    return out


# ═══════════════════════════════════════════════════════════════
# 3. AR(1) 模型 —— 最小二乘拟合 + 一步预测
# ═══════════════════════════════════════════════════════════════
def _fit_ar1(y: np.ndarray):
    """
    拟合 AR(1):  y_t = c + phi * y_{t-1} + eps
    返回 (c, phi) 或 None（数据不足时）
    """
    if len(y) < 3:
        return None
    y_prev = y[:-1]
    y_curr = y[1:]
    # 最小二乘: [c, phi] = (X'X)^{-1} X'y
    X = np.column_stack([np.ones_like(y_prev), y_prev])
    try:
        beta, _, _, _ = linalg.lstsq(X, y_curr)
    except linalg.LinAlgError:
        return None
    c, phi = beta
    # 稳定性约束：|phi| 不超过 1（避免发散）
    phi = np.clip(phi, -0.99, 0.99)
    return c, phi


def _ar1_forecast(c: float, phi: float, last_val: float) -> float:
    """AR(1) 一步向前预测"""
    return c + phi * last_val


# ═══════════════════════════════════════════════════════════════
# 4. 核心：计算每队时序状态分
# ═══════════════════════════════════════════════════════════════
def calc_team_state_score(df_seq: pd.DataFrame = None) -> pd.DataFrame:
    """
    对每个 (league, team) 计算 EMA + AR(1) 状态分。
    - 先对 diff 序列做 EMA 平滑
    - 再对 EMA 序列拟合 AR(1)，做一步预测
    - 将预测值映射到 0-4 状态空间
    """
    if df_seq is None:
        df_seq = load_team_match_data()

    if df_seq.empty:
        return pd.DataFrame(columns=["league", "team", "state_score"])

    state_result = []
    for (lg, team), group in df_seq.groupby(["league", "team"]):
        diffs = group["diff"].values.astype(float)

        # ---- 至少有少量比赛才计算 ----
        if len(diffs) < EMA_WARMUP:
            raw_score = 2.0  # 数据不足 → 中性
        else:
            # ① EMA 平滑
            ema_vals = _ema(diffs)

            # ② 取最近 LSTM_SEQ_LENGTH 个平滑值用于 AR(1) 建模
            window = ema_vals[-LSTM_SEQ_LENGTH:]

            # ③ 拟合 AR(1)
            ar_params = _fit_ar1(window)

            if ar_params is None:
                # AR(1) 拟合失败，退回 EMA 末值
                raw_score = float(ema_vals[-1])
            else:
                c, phi = ar_params
                raw_score = _ar1_forecast(c, phi, float(ema_vals[-1]))

        # ---- 映射到 0-4 状态空间（与原版 LSTM 相同公式）----
        # 原: state_norm = clip((pred_diff + 10) / 5, 0, 4)
        # diff=0 → 2.0 (稳定), diff=+10 → 4.0 (巅峰), diff=-10 → 0.0 (低谷)
        state_norm = float(np.clip((raw_score + 10) / 5, 0, 4))
        if np.isnan(state_norm):
            state_norm = 2.0

        level_key = int(np.clip(round(state_norm), 0, 4))
        state_result.append({
            "league":      lg,
            "team":        team,
            "state_score": round(state_norm, 2),
            "state_level": STATE_LEVEL.get(level_key, "稳定"),
        })

    return pd.DataFrame(state_result)


# ═══════════════════════════════════════════════════════════════
# 5. 入库
# ═══════════════════════════════════════════════════════════════
def save_state_to_db(df_state: pd.DataFrame):
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS team_lstm_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league VARCHAR(50), team VARCHAR(100),
        state_score FLOAT, state_level VARCHAR(20),
        update_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    df_state.to_sql("team_lstm_state", engine, if_exists="replace", index=False)
    print("✅ EMA+AR(1) 时序状态分计算完成并入库")


# ═══════════════════════════════════════════════════════════════
# 6. 主入口（保持与原版兼容）
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Windows 终端 UTF-8 输出
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    df_seq = load_team_match_data()
    if df_seq.empty:
        print("⚠️ 暂无比赛数据，跳过时序状态计算")
    else:
        n_teams = df_seq.groupby(["league", "team"]).ngroups
        print(f"📊 加载完成：{len(df_seq)} 条记录，{n_teams} 支球队")
        df_state = calc_team_state_score(df_seq)
        if df_state.empty:
            print("⚠️ 计算结果为空")
        else:
            save_state_to_db(df_state)
