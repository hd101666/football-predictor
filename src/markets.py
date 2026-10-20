"""
Multi-market prediction models
Supports: 1X2, Over/Under 2.5, BTTS, Corners O/U, Half-time/Full-time
"""

import os
import joblib
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, log_loss
from .config import MODELS_DIR, TRAIN_TEST_SPLIT_DATE, RANDOM_STATE
from .features import get_feature_columns


def _make_binary_model() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=250,
        max_depth=4,
        learning_rate=0.06,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        eval_metric="logloss",
    )


def _make_multiclass_model(num_class: int) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multi:softprob",
        num_class=num_class,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        eval_metric="mlogloss",
    )


def train_market_models(df: pd.DataFrame) -> dict:
    """Train models for all supported markets"""
    features = get_feature_columns()
    split_date = pd.to_datetime(TRAIN_TEST_SPLIT_DATE)
    train_mask = df["Date"] < split_date
    test_mask = df["Date"] >= split_date

    models = {}
    results = {}

    # 1X2 (already handled in model.py, but included here for completeness)
    print("Training 1X2 model...")
    m_1x2 = _make_multiclass_model(3)
    m_1x2.fit(df.loc[train_mask, features], df.loc[train_mask, "Result"])
    models["1x2"] = m_1x2
    proba = m_1x2.predict_proba(df.loc[test_mask, features])
    results["1x2_acc"] = accuracy_score(df.loc[test_mask, "Result"], proba.argmax(1))

    # Over/Under 2.5
    if "OU25" in df.columns:
        print("Training Over/Under 2.5 model...")
        m_ou = _make_binary_model()
        valid = df["OU25"].notna()
        m_ou.fit(df.loc[train_mask & valid, features], df.loc[train_mask & valid, "OU25"])
        models["ou25"] = m_ou
        if (test_mask & valid).any():
            pred = m_ou.predict(df.loc[test_mask & valid, features])
            results["ou25_acc"] = accuracy_score(df.loc[test_mask & valid, "OU25"], pred)

    # BTTS
    if "BTTS" in df.columns:
        print("Training BTTS model...")
        m_btts = _make_binary_model()
        valid = df["BTTS"].notna()
        m_btts.fit(df.loc[train_mask & valid, features], df.loc[train_mask & valid, "BTTS"])
        models["btts"] = m_btts
        if (test_mask & valid).any():
            pred = m_btts.predict(df.loc[test_mask & valid, features])
            results["btts_acc"] = accuracy_score(df.loc[test_mask & valid, "BTTS"], pred)

    # Corners O/U 9.5
    if "CornersOU95" in df.columns:
        print("Training Corners O/U 9.5 model...")
        m_corners = _make_binary_model()
        valid = df["CornersOU95"].notna()
        m_corners.fit(df.loc[train_mask & valid, features], df.loc[train_mask & valid, "CornersOU95"])
        models["corners"] = m_corners
        if (test_mask & valid).any():
            pred = m_corners.predict(df.loc[test_mask & valid, features])
            results["corners_acc"] = accuracy_score(df.loc[test_mask & valid, "CornersOU95"], pred)

    # Asian Handicap (home covers)
    if "AH_HomeCover" in df.columns:
        print("Training Asian Handicap model...")
        valid = df["AH_HomeCover"].notna() & df["AH_Line"].notna()
        m_ah = _make_binary_model()
        m_ah.fit(df.loc[train_mask & valid, features], df.loc[train_mask & valid, "AH_HomeCover"])
        models["ah"] = m_ah
        if (test_mask & valid).any():
            pred = m_ah.predict(df.loc[test_mask & valid, features])
            results["ah_acc"] = accuracy_score(df.loc[test_mask & valid, "AH_HomeCover"], pred)
        print("Training HT/FT model...")
        valid = df["HTFT"] >= 0
        m_htft = _make_multiclass_model(9)
        m_htft.fit(df.loc[train_mask & valid, features], df.loc[train_mask & valid, "HTFT"])
        models["htft"] = m_htft
        if (test_mask & valid).any():
            pred = m_htft.predict(df.loc[test_mask & valid, features])
            results["htft_acc"] = accuracy_score(df.loc[test_mask & valid, "HTFT"], pred)

    # Save all models
    os.makedirs(MODELS_DIR, exist_ok=True)
    save_path = os.path.join(MODELS_DIR, "market_models.joblib")
    joblib.dump(models, save_path)
    print(f"\nAll market models saved to {save_path}")
    print("Test accuracies:", results)
    return models


def load_market_models() -> dict:
    path = os.path.join(MODELS_DIR, "market_models.joblib")
    return joblib.load(path)


def predict_all_markets(models: dict, matches: pd.DataFrame) -> pd.DataFrame:
    """Add predictions for all available markets"""
    features = get_feature_columns()
    df = matches.copy()

    # 1X2
    if "1x2" in models:
        proba = models["1x2"].predict_proba(df[features])
        df["Prob_Home"] = proba[:, 0]
        df["Prob_Draw"] = proba[:, 1]
        df["Prob_Away"] = proba[:, 2]
        df["MaxProb_1x2"] = proba.max(axis=1)

    # O/U 2.5
    if "ou25" in models:
        proba = models["ou25"].predict_proba(df[features])
        df["Prob_Over25"] = proba[:, 1]
        df["Prob_Under25"] = proba[:, 0]

    # BTTS
    if "btts" in models:
        proba = models["btts"].predict_proba(df[features])
        df["Prob_BTTS_Yes"] = proba[:, 1]
        df["Prob_BTTS_No"] = proba[:, 0]

    # Corners
    if "corners" in models:
        proba = models["corners"].predict_proba(df[features])
        df["Prob_CornersOver"] = proba[:, 1]
        df["Prob_CornersUnder"] = proba[:, 0]

    # Asian Handicap
    if "ah" in models and "AH_Line" in df.columns:
        proba = models["ah"].predict_proba(df[features])
        df["Prob_AH_HomeCover"] = proba[:, 1]
        df["Prob_AH_AwayCover"] = proba[:, 0]
        proba = models["htft"].predict_proba(df[features])
        htft_labels = [
            "H/H", "H/D", "H/A",
            "D/H", "D/D", "D/A",
            "A/H", "A/D", "A/A",
        ]
        for i, label in enumerate(htft_labels):
            df[f"Prob_HTFT_{label}"] = proba[:, i]
        df["Pred_HTFT"] = [htft_labels[i] for i in proba.argmax(axis=1)]
        df["MaxProb_HTFT"] = proba.max(axis=1)

    return df
