"""
Per-league model training with probability calibration
"""

import os
import joblib
import pandas as pd
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, log_loss
from .config import MODELS_DIR, TRAIN_TEST_SPLIT_DATE, RANDOM_STATE, LEAGUES
from .features import get_feature_columns
from .xg_features import get_xg_feature_columns
from .injury_features import get_injury_features


def get_all_features() -> list[str]:
    base = [
        "EloDiff", "HomeElo", "AwayElo",
        "FormDiff", "AttackDiff", "DefenseDiff",
        "HomeFormGF", "AwayFormGF",
        "HomeFormGA", "AwayFormGA",
    ]
    derived = ["Elo_Form_Interact", "Attack_Defense_Ratio"]
    xg = get_xg_feature_columns()
    interactions = ["Elo_xG_Interact", "Elo_xGA_Interact"]
    injury = get_injury_features()
    # Local DB features (optional)
    local_xg = ["Home_xG_local", "Away_xG_local", "xG_Diff_local"]
    local_inj = ["Home_Inj", "Away_Inj", "InjuryDiff"]
    return base + derived + xg + interactions + injury + local_xg + local_inj


def _base_model(num_class: int = 2) -> XGBClassifier:
    """Optimized XGBoost with better regularization."""
    common = dict(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.75,
        colsample_bytree=0.75,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    if num_class == 2:
        return XGBClassifier(**common, eval_metric="logloss")
    return XGBClassifier(
        **common,
        objective="multi:softprob",
        num_class=num_class,
        eval_metric="mlogloss",
    )


def train_per_league(df: pd.DataFrame) -> dict:
    """
    Train calibrated models separately for each league.
    Returns dict of league -> model
    """
    features = get_all_features()
    available = [f for f in features if f in df.columns]
    split_date = pd.to_datetime(TRAIN_TEST_SPLIT_DATE)

    models = {}
    results = {}

    for league_code, league_name in LEAGUES.items():
        league_df = df[df["League"] == league_code].copy()
        if len(league_df) < 200:
            print(f"Skipping {league_name}: only {len(league_df)} matches")
            continue

        train_mask = league_df["Date"] < split_date
        test_mask = league_df["Date"] >= split_date

        if train_mask.sum() < 100 or test_mask.sum() < 30:
            print(f"Skipping {league_name}: insufficient split")
            continue

        print(f"Training {league_name} ({len(league_df)} matches)...")

        # 1X2 with calibration
        base = _base_model(num_class=3)
        calibrated = CalibratedClassifierCV(base, method="isotonic", cv=3)
        calibrated.fit(
            league_df.loc[train_mask, available],
            league_df.loc[train_mask, "Result"],
        )

        # Evaluate
        proba = calibrated.predict_proba(league_df.loc[test_mask, available])
        pred = proba.argmax(axis=1)
        acc = accuracy_score(league_df.loc[test_mask, "Result"], pred)
        ll = log_loss(league_df.loc[test_mask, "Result"], proba)
        results[league_code] = {"acc": round(acc, 4), "logloss": round(ll, 4)}
        models[league_code] = calibrated
        print(f"  {league_name}: acc={acc:.4f}, logloss={ll:.4f}")

    # Save
    os.makedirs(MODELS_DIR, exist_ok=True)
    path = os.path.join(MODELS_DIR, "per_league_models.joblib")
    joblib.dump({"models": models, "features": available, "results": results}, path)
    print(f"\nPer-league models saved to {path}")
    print("Results:", results)
    return models


def load_per_league_models() -> dict:
    path = os.path.join(MODELS_DIR, "per_league_models.joblib")
    return joblib.load(path)


def predict_per_league(models_data: dict, matches: pd.DataFrame) -> pd.DataFrame:
    """Predict using the appropriate league model"""
    models = models_data["models"]
    features = models_data["features"]
    df = matches.copy()

    df["Prob_Home"] = np.nan
    df["Prob_Draw"] = np.nan
    df["Prob_Away"] = np.nan

    for league_code, model in models.items():
        mask = df["League"] == league_code
        if mask.sum() == 0:
            continue
        proba = model.predict_proba(df.loc[mask, features])
        df.loc[mask, "Prob_Home"] = proba[:, 0]
        df.loc[mask, "Prob_Draw"] = proba[:, 1]
        df.loc[mask, "Prob_Away"] = proba[:, 2]

    df["MaxProb"] = df[["Prob_Home", "Prob_Draw", "Prob_Away"]].max(axis=1)
    return df
