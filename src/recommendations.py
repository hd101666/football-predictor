"""
Value betting and recommendation logic
"""

import pandas as pd
import numpy as np
from .config import MIN_PROBABILITY, MIN_EDGE, MIN_VALUE, CONFIDENCE_LEVELS


def add_ah_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate value metrics for Asian Handicap."""
    df = df.copy()
    for src, h_col, a_col in [
        ("PS", "PAHH", "PAHA"),
        ("B365", "B365AHH", "B365AHA"),
        ("Avg", "AvgAHH", "AvgAHA"),
    ]:
        if h_col in df.columns and df[h_col].notna().any():
            df["AH_Odds_Home"] = df[h_col]
            df["AH_Odds_Away"] = df[a_col]
            df["AH_MarketProb_Home"] = 1 / df[h_col]
            df["AH_MarketProb_Away"] = 1 / df[a_col]
            break

    if "Prob_AH_HomeCover" in df.columns and "AH_MarketProb_Home" in df.columns:
        df["AH_Edge_Home"] = df["Prob_AH_HomeCover"] - df["AH_MarketProb_Home"]
        df["AH_EV_Home"] = df["Prob_AH_HomeCover"] * df["AH_Odds_Home"] - 1
        df["AH_Edge_Away"] = df.get("Prob_AH_AwayCover", 1 - df["Prob_AH_HomeCover"]) - df["AH_MarketProb_Away"]
        df["AH_EV_Away"] = df.get("Prob_AH_AwayCover", 1 - df["Prob_AH_HomeCover"]) * df["AH_Odds_Away"] - 1
    return df


def add_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate edge and expected value for 1X2."""
    df = df.copy()
    for outcome, label in [("H", "Home"), ("D", "Draw"), ("A", "Away")]:
        for src in ["PS", "B365", "Avg"]:
            odds_col = f"{src}{outcome}"
            if odds_col in df.columns and df[odds_col].notna().any():
                df[f"MarketOdds_{label}"] = df[odds_col]
                df[f"MarketProb_{label}"] = 1 / df[odds_col]
                break

    for label, model_col in [("Home", "Prob_Home"), ("Draw", "Prob_Draw"), ("Away", "Prob_Away")]:
        market_col = f"MarketProb_{label}"
        if market_col in df.columns:
            df[f"Edge_{label}"] = df[model_col] - df[market_col]
            odds_col = f"MarketOdds_{label}"
            if odds_col in df.columns:
                df[f"EV_{label}"] = df[model_col] * df[odds_col] - 1
    return df


def generate_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter high-confidence value recommendations.
    Downgrades confidence only on meaningful signal conflicts:
    - Meaningful: opposite signs AND |xG_Diff| > 0.1
    - Severe: Elo favors away but xG favors home (extra downgrade)
    """
    recs = []
    for _, row in df.iterrows():
        elo_diff = row.get("EloDiff", 0)
        xg_diff = row.get("xG_Diff", 0)

        signals_conflict = (elo_diff * xg_diff < 0) and (abs(xg_diff) > 0.1)
        severe_conflict = signals_conflict and (elo_diff < 0) and (xg_diff > 0)
        # Strong agreement: same direction and both signals are meaningful
        strong_agree = (elo_diff * xg_diff > 0) and (abs(elo_diff) > 50) and (abs(xg_diff) > 0.15)

        for label, model_col in [("Home", "Prob_Home"), ("Draw", "Prob_Draw"), ("Away", "Prob_Away")]:
            prob = row.get(model_col, 0)
            edge = row.get(f"Edge_{label}", 0)
            ev = row.get(f"EV_{label}", 0)

            if prob >= MIN_PROBABILITY and edge >= MIN_EDGE and ev >= MIN_VALUE:
                confidence = "low"
                for lvl, thresh in sorted(CONFIDENCE_LEVELS.items(), key=lambda x: -x[1]):
                    if prob >= thresh:
                        confidence = lvl
                        break

                if signals_conflict:
                    if confidence == "high":
                        confidence = "medium"
                    elif confidence == "medium":
                        confidence = "low"

                if severe_conflict and confidence == "medium":
                    confidence = "low"

                # Boost on strong agreement
                if strong_agree and confidence == "medium":
                    confidence = "high"
                elif strong_agree and confidence == "low" and prob >= 0.60:
                    confidence = "medium"

                recs.append({
                    "Date": row["Date"],
                    "League": row.get("LeagueName", row.get("League")),
                    "HomeTeam": row["HomeTeam"],
                    "AwayTeam": row["AwayTeam"],
                    "Pick": label,
                    "ModelProb": round(prob, 3),
                    "MarketProb": round(row.get(f"MarketProb_{label}", 0), 3),
                    "Edge": round(edge, 3),
                    "EV": round(ev, 3),
                    "Odds": round(row.get(f"MarketOdds_{label}", 0), 2),
                    "Confidence": confidence,
                    "SignalConflict": signals_conflict,
                    "SevereConflict": severe_conflict,
                    "StrongAgree": strong_agree,
                    "MaxProb": round(row.get("MaxProb", prob), 3),
                })

    if not recs:
        return pd.DataFrame()
    rec_df = pd.DataFrame(recs)
    conf_order = {"high": 0, "medium": 1, "low": 2}
    rec_df["ConfRank"] = rec_df["Confidence"].map(conf_order)
    rec_df = rec_df.sort_values(["ConfRank", "Edge"], ascending=[True, False]).drop(columns=["ConfRank"])
    return rec_df
