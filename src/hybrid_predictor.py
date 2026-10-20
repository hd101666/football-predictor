"""
Hybrid ML + LLM style predictor with refined fusion rules.
"""

import pandas as pd
import numpy as np


class HybridPredictor:
    def __init__(self, ml_model, feature_cols, min_edge=0.05, min_prob=0.55):
        self.ml_model = ml_model
        self.feature_cols = feature_cols
        self.base_min_edge = min_edge
        self.base_min_prob = min_prob

    def predict_match(self, features: dict, market_odds: dict, llm_context: dict | None = None) -> dict:
        X = pd.DataFrame([features])[self.feature_cols]
        proba = self.ml_model.predict_proba(X)[0]
        ml_probs = {"H": float(proba[0]), "D": float(proba[1]), "A": float(proba[2])}

        # Apply probability adjustment
        min_prob = self.base_min_prob
        min_edge = self.base_min_edge
        if llm_context:
            adj_map = {
                "slight_upgrade": 1.05,
                "mild_downgrade": 0.96,
                "downgrade": 0.90,
            }
            adj = adj_map.get(llm_context.get("adjust"), 1.0)
            if adj != 1.0:
                fav = max(ml_probs, key=ml_probs.get)
                ml_probs[fav] *= adj
                s = sum(ml_probs.values())
                ml_probs = {k: v / s for k, v in ml_probs.items()}
            # Threshold adjustment
            if llm_context.get("adjust") == "slight_upgrade":
                min_prob = max(0.48, self.base_min_prob - 0.04)
                min_edge = max(0.02, self.base_min_edge - 0.015)
            elif llm_context.get("adjust") in ("downgrade", "mild_downgrade"):
                min_prob = self.base_min_prob + 0.04
                min_edge = self.base_min_edge + 0.015

        market_probs = {k: 1 / v for k, v in market_odds.items()}
        total = sum(market_probs.values())
        market_probs = {k: v / total for k, v in market_probs.items()}

        edges = {k: ml_probs[k] - market_probs[k] for k in ["H", "D", "A"]}
        best = max(edges, key=edges.get)
        best_edge = edges[best]
        best_prob = ml_probs[best]
        best_odds = market_odds[best]
        ev = best_prob * best_odds - 1

        bet = None
        if best_prob >= min_prob and best_edge >= min_edge and ev > 0:
            bet = {
                "pick": best,
                "prob": round(best_prob, 3),
                "odds": round(best_odds, 2),
                "edge": round(best_edge, 3),
                "ev": round(ev, 3),
            }

        # Confidence based on edge and probability
        confidence = "low"
        if best_edge >= 0.12 and best_prob >= 0.65:
            confidence = "high"
        elif best_edge >= 0.08 and best_prob >= 0.58:
            confidence = "medium"

        return {
            "ml_probs": {k: round(v, 3) for k, v in ml_probs.items()},
            "edges": {k: round(v, 3) for k, v in edges.items()},
            "bet": bet,
            "confidence": confidence,
            "llm_applied": bool(llm_context and llm_context.get("adjust") != "neutral"),
            "adjust": llm_context.get("adjust") if llm_context else None,
        }


def determine_adjust(raw: dict) -> dict:
    """
    Refined fusion rules:
    - slight_upgrade: confidence >= 0.70 AND no absences
    - downgrade: absences AND confidence < 0.55, OR news == high
    - mild_downgrade: absences AND confidence >= 0.55
    - neutral: otherwise
    """
    conf = raw.get("confidence", 0.5)
    absences = raw.get("key_absences", [])
    news = raw.get("news_impact", "none")

    flags = []
    if absences:
        flags.append("key_player_out")
    if news in ("medium", "high"):
        flags.append("news_risk")

    if conf >= 0.70 and not absences:
        adjust = "slight_upgrade"
    elif absences and conf < 0.55:
        adjust = "downgrade"
    elif absences and conf >= 0.55:
        adjust = "mild_downgrade"
    elif news == "high":
        adjust = "downgrade"
    else:
        adjust = "neutral"

    return {
        "adjust": adjust,
        "risk_flags": flags,
        "confidence": conf,
        "absence_count": len(absences),
    }


def llm_research_prompt(home: str, away: str, league: str) -> str:
    return f"""
你是足球研究助手。为以下比赛收集可查证信息，输出 JSON。

比赛：{home} vs {away}
联赛：{league}

输出格式：
{{
  "home_form": "近5场如 WWDLL",
  "away_form": "近5场",
  "key_absences": ["缺阵核心球员"],
  "news_impact": "none/low/medium/high",
  "suggested_result": "H/D/A",
  "confidence": 0.6,
  "reason": "简短理由"
}}
"""
