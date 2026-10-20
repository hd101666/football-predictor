"""
Hybrid injury module: panel data + Bot real-time check.
"""

import pandas as pd
import requests
from datetime import datetime
from pathlib import Path


PANEL_URL = "https://raw.githubusercontent.com/withqwerty/availability-data/main/cleaned/panel.csv"
CACHE_PATH = Path("data/injury_panel.csv")


def load_injury_panel(force_refresh: bool = False) -> pd.DataFrame:
    """Load season-level injury burden from GitHub panel."""
    if CACHE_PATH.exists() and not force_refresh:
        return pd.read_csv(CACHE_PATH)
    print("Downloading injury panel...")
    resp = requests.get(PANEL_URL, timeout=30)
    resp.raise_for_status()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(resp.text)
    return pd.read_csv(CACHE_PATH)


def get_team_burden(df: pd.DataFrame, team: str, season: int | None = None) -> dict:
    """Get injury burden for a team from panel."""
    team_df = df[df["club"].str.contains(team, case=False, na=False)]
    if season:
        team_df = team_df[team_df["season"] == season]
    if team_df.empty:
        return {"team": team, "injury_burden": None, "source": "panel"}
    latest = team_df.sort_values("season").iloc[-1]
    return {
        "team": team,
        "season": int(latest["season"]),
        "injury_burden": round(latest["injury_burden"], 3),
        "injured_matchdays": int(latest["injured_matchdays"]),
        "source": "panel",
    }


def build_bot_injury_prompt(home: str, away: str) -> str:
    """Build prompt for Bot to check real-time injuries."""
    return f"""
请查询以下比赛的最新伤停信息（只基于可查证来源），输出 JSON。

比赛：{home} vs {away}

输出格式：
{{
  "home_injuries": [{{"player": "姓名", "reason": "原因", "status": "out/doubtful"}}],
  "away_injuries": [{{"player": "姓名", "reason": "原因", "status": "out/doubtful"}}],
  "confidence": 0.7,
  "source": "来源简述"
}}

如果没有找到确定伤停，返回空列表。
"""


def merge_injury_signals(panel_data: dict, bot_data: dict | None) -> dict:
    """
    Merge panel (season-level) and Bot (real-time) signals.
    Bot data takes priority for current absences.
    """
    result = {
        "panel_burden": panel_data.get("injury_burden"),
        "realtime_absences": [],
        "combined_risk": "low",
    }
    if bot_data:
        home_inj = bot_data.get("home_injuries", [])
        away_inj = bot_data.get("away_injuries", [])
        result["realtime_absences"] = home_inj + away_inj
        total = len(result["realtime_absences"])
        if total >= 3:
            result["combined_risk"] = "high"
        elif total >= 1:
            result["combined_risk"] = "medium"
    return result


def injury_feature_for_match(home: str, away: str, panel_df: pd.DataFrame, bot_result: dict | None = None) -> dict:
    """Generate injury features for one match."""
    home_panel = get_team_burden(panel_df, home)
    away_panel = get_team_burden(panel_df, away)
    merged = merge_injury_signals(
        {"injury_burden": home_panel.get("injury_burden")},
        bot_result,
    )
    return {
        "home_burden": home_panel.get("injury_burden"),
        "away_burden": away_panel.get("injury_burden"),
        "burden_diff": (home_panel.get("injury_burden") or 0) - (away_panel.get("injury_burden") or 0),
        "realtime_count": len(merged["realtime_absences"]),
        "combined_risk": merged["combined_risk"],
    }


if __name__ == "__main__":
    df = load_injury_panel()
    print(f"Panel loaded: {len(df)} rows")
    print(get_team_burden(df, "Arsenal"))
    print(build_bot_injury_prompt("Arsenal", "Chelsea"))
