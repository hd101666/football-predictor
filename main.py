"""
Main entry point for the Football Prediction System
"""

import argparse
import os
import sys
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data_loader import load_all_data
from src.features import build_features
from src.model import train_model
from src.markets import train_market_models
from src.per_league import train_per_league, load_per_league_models
from src.xg_features import add_xg_features
from src.injury_features import add_injury_features
from src.hybrid_predictor import HybridPredictor
from src.local_db_adapter import load_local_db
from src.fixtures import load_fixtures, filter_upcoming
from src.config import REPORTS_DIR, MIN_PROBABILITY, MIN_EDGE


def train():
    print("Loading data...")
    df = load_all_data()
    df = build_features(df)
    print(f"Ready: {len(df)} matches")
    train_model(df)
    print("Done.")


def train_markets():
    print("Loading data...")
    df = load_all_data()
    df = build_features(df)
    train_market_models(df)
    print("Done.")


def train_per_league_cmd(use_local_db: bool = True):
    print("Loading data...")
    df = load_all_data()
    df = build_features(df)
    df = add_xg_features(df)
    df = add_injury_features(df)

    # Enrich with local DB xG/injury if available
    if use_local_db:
        local_db = load_local_db()
        if local_db:
            print("Enriching with local DB xG and injury features...")
            try:
                df = local_db.enrich_matches(df)
                print(f"  Local features added. xG coverage: {df['Home_xG_local'].notna().mean():.1%}")
            except Exception as e:
                print(f"  Local DB enrich failed: {e}")
            finally:
                local_db.close()
        else:
            print("Local DB not found, using default features only.")

    print(f"Ready: {len(df)} matches")
    train_per_league(df)
    print("Done.")


def predict(output_path: str | None = None, use_hybrid: bool = True, use_fixtures: bool = True, days: int = 7):
    """Generate predictions with local DB features."""
    print("Loading models...")
    try:
        models_data = load_per_league_models()
    except FileNotFoundError:
        print("No models. Run: python main.py train_per_league")
        return

    # Load candidates
    candidates = None
    hist = None
    if use_fixtures:
        try:
            fixtures = load_fixtures()
            candidates = filter_upcoming(fixtures, days=days)
            print(f"Fixtures: {len(candidates)}")
            if not candidates.empty:
                hist = load_all_data()
                hist = build_features(hist)
                hist = add_xg_features(hist)
                hist = add_injury_features(hist)
        except Exception as e:
            print(f"Fixtures failed: {e}")

    if candidates is None or candidates.empty:
        print("Using recent matches")
        df = load_all_data()
        df = build_features(df)
        df = add_xg_features(df)
        df = add_injury_features(df)
        candidates = df.tail(30).copy()

    if candidates.empty:
        print("No candidates.")
        return

    # Ensure feature columns exist
    for col in models_data["features"]:
        if col not in candidates.columns:
            candidates[col] = 0.0

    print(f"Hybrid: min_prob={MIN_PROBABILITY}, min_edge={MIN_EDGE}")
    results = []

    for _, row in candidates.iterrows():
        league = row.get("League", "E0")
        model = models_data["models"].get(league)
        if model is None:
            continue

        features = models_data["features"]
        predictor = HybridPredictor(model, features, min_edge=MIN_EDGE, min_prob=MIN_PROBABILITY)
        feats = {c: row.get(c, 0.0) for c in features}
        odds = {
            "H": row.get("B365H", row.get("PSH", 2.0)),
            "D": row.get("B365D", row.get("PSD", 3.5)),
            "A": row.get("B365A", row.get("PSA", 3.5)),
        }
        home = str(row.get("HomeTeam", ""))
        away = str(row.get("AwayTeam", ""))

        # Local DB enrichment
        local_db = load_local_db()
        ctx = None
        inj_risk = "unknown"
        if local_db:
            try:
                best = local_db.get_best_odds(home, away)
                for k in ["H", "D", "A"]:
                    if best.get(k):
                        odds[k] = max(odds.get(k, 0) or 0, best[k])
                xg = local_db.get_match_xg(home, away)
                if xg["home_xg"] and xg["away_xg"]:
                    feats["xG_Diff"] = xg["home_xg"] - xg["away_xg"]
                if hist is not None:
                    for k, v in local_db.get_team_latest_features(home, hist).items():
                        if k in feats and pd.notna(v):
                            feats[k] = v
                inj = local_db.get_injury_features(home, away)
                inj_risk = inj["combined_risk"]
                if inj_risk == "high":
                    ctx = {"adjust": "downgrade"}
                elif inj_risk == "medium":
                    ctx = {"adjust": "mild_downgrade"}
            except Exception as e:
                print(f"DB error for {home}: {e}")
            finally:
                local_db.close()

        res = predictor.predict_match(feats, odds, ctx)
        if res["bet"]:
            results.append({
                "Date": row.get("Date"),
                "League": league,
                "Home": home,
                "Away": away,
                "Pick": res["bet"]["pick"],
                "Prob": res["bet"]["prob"],
                "Odds": res["bet"]["odds"],
                "Edge": res["bet"]["edge"],
                "EV": res["bet"]["ev"],
                "Confidence": res.get("confidence", "low"),
                "InjuryRisk": inj_risk,
            })

    os.makedirs(REPORTS_DIR, exist_ok=True)
    if results:
        out = pd.DataFrame(results)
        print(f"\nRecommendations ({len(out)}):")
        print(out.to_string(index=False))
        path = output_path or f"{REPORTS_DIR}/predict_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        out.to_csv(path, index=False)
        print(f"Saved: {path}")
    else:
        print("No recommendations.")


def main():
    parser = argparse.ArgumentParser(description="Football Prediction System")
    parser.add_argument("command", choices=["train", "train_markets", "train_per_league", "predict"])
    parser.add_argument("--no-hybrid", action="store_true")
    args = parser.parse_args()

    if args.command == "train":
        train()
    elif args.command == "train_markets":
        train_markets()
    elif args.command == "train_per_league":
        train_per_league_cmd()
    elif args.command == "predict":
        predict(use_hybrid=not args.no_hybrid)


if __name__ == "__main__":
    main()
