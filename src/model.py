"""
XGBoost model training and prediction for match outcomes (1X2)
"""

import os
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, log_loss, classification_report
from .config import MODELS_DIR, TRAIN_TEST_SPLIT_DATE, RANDOM_STATE
from .features import get_feature_columns


def train_model(df: pd.DataFrame, save_path: str | None = None) -> XGBClassifier:
    """
    Train multiclass XGBoost for Home/Draw/Away.
    Uses time-based split for realistic evaluation.
    """
    features = get_feature_columns()
    X = df[features]
    y = df["Result"]

    # Time-based split
    split_date = pd.to_datetime(TRAIN_TEST_SPLIT_DATE)
    train_mask = df["Date"] < split_date
    test_mask = df["Date"] >= split_date

    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]

    print(f"Training samples: {len(X_train)}, Test samples: {len(X_test)}")

    model = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multi:softprob",
        num_class=3,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        eval_metric="mlogloss",
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # Evaluation
    proba = model.predict_proba(X_test)
    pred = model.predict(X_test)
    print(f"Test Accuracy: {accuracy_score(y_test, pred):.4f}")
    print(f"Test LogLoss: {log_loss(y_test, proba):.4f}")
    print(classification_report(y_test, pred, target_names=["Home", "Draw", "Away"]))

    if save_path is None:
        os.makedirs(MODELS_DIR, exist_ok=True)
        save_path = os.path.join(MODELS_DIR, "xgb_1x2.joblib")
    joblib.dump(model, save_path)
    print(f"Model saved to {save_path}")
    return model


def load_model(path: str | None = None) -> XGBClassifier:
    if path is None:
        path = os.path.join(MODELS_DIR, "xgb_1x2.joblib")
    return joblib.load(path)


def predict_matches(model: XGBClassifier, matches: pd.DataFrame) -> pd.DataFrame:
    """Add probability columns for Home/Draw/Away"""
    features = get_feature_columns()
    proba = model.predict_proba(matches[features])
    matches = matches.copy()
    matches["Prob_Home"] = proba[:, 0]
    matches["Prob_Draw"] = proba[:, 1]
    matches["Prob_Away"] = proba[:, 2]
    matches["Pred"] = proba.argmax(axis=1)
    matches["PredLabel"] = matches["Pred"].map({0: "H", 1: "D", 2: "A"})
    matches["MaxProb"] = proba.max(axis=1)
    return matches
