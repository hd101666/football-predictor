"""
Feature engineering for football match prediction
Includes Elo ratings, recent form, home/away stats, etc.
"""

import pandas as pd
import numpy as np
from .config import ELO_K, ELO_HOME_ADVANTAGE, FORM_WINDOW


def calculate_elo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate pre-match Elo ratings for home and away teams.
    Simple Elo with home advantage.
    """
    teams = set(df["HomeTeam"].unique()) | set(df["AwayTeam"].unique())
    elo = {team: 1500.0 for team in teams}

    home_elos = []
    away_elos = []

    for _, row in df.iterrows():
        h = row["HomeTeam"]
        a = row["AwayTeam"]
        home_elos.append(elo[h])
        away_elos.append(elo[a])

        # Expected result
        eh = 1 / (1 + 10 ** ((elo[a] - (elo[h] + ELO_HOME_ADVANTAGE)) / 400))
        ea = 1 - eh

        # Actual result (1=home win, 0.5=draw, 0=away win)
        if row["FTR"] == "H":
            actual_h, actual_a = 1.0, 0.0
        elif row["FTR"] == "D":
            actual_h, actual_a = 0.5, 0.5
        else:
            actual_h, actual_a = 0.0, 1.0

        # Update
        elo[h] += ELO_K * (actual_h - eh)
        elo[a] += ELO_K * (actual_a - ea)

    df = df.copy()
    df["HomeElo"] = home_elos
    df["AwayElo"] = away_elos
    df["EloDiff"] = df["HomeElo"] - df["AwayElo"]
    return df


def add_form_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add rolling form features: points, goals for/against over last FORM_WINDOW matches.
    Calculated separately for home and away contexts where useful.
    """
    df = df.sort_values("Date").reset_index(drop=True)
    df["HomePoints"] = df["FTR"].map({"H": 3, "D": 1, "A": 0})
    df["AwayPoints"] = df["FTR"].map({"A": 3, "D": 1, "H": 0})

    # Team-level rolling stats
    def team_rolling(group):
        group = group.sort_values("Date").copy()
        # Points last N
        group["Points_lastN"] = group["Points"].shift(1).rolling(FORM_WINDOW, min_periods=1).mean()
        group["GF_lastN"] = group["GF"].shift(1).rolling(FORM_WINDOW, min_periods=1).mean()
        group["GA_lastN"] = group["GA"].shift(1).rolling(FORM_WINDOW, min_periods=1).mean()
        return group

    # Build long format for rolling
    home = df[["Date", "HomeTeam", "HomePoints", "FTHG", "FTAG"]].copy()
    home.columns = ["Date", "Team", "Points", "GF", "GA"]
    away = df[["Date", "AwayTeam", "AwayPoints", "FTAG", "FTHG"]].copy()
    away.columns = ["Date", "Team", "Points", "GF", "GA"]
    long = pd.concat([home, away], ignore_index=True)

    # Apply rolling - keep Team column
    long = long.groupby("Team", group_keys=False).apply(team_rolling, include_groups=True)
    if "Team" not in long.columns:
        long = long.reset_index()

    # Merge back
    home_form = long.rename(columns={
        "Points_lastN": "HomeFormPoints",
        "GF_lastN": "HomeFormGF",
        "GA_lastN": "HomeFormGA",
    })[["Date", "Team", "HomeFormPoints", "HomeFormGF", "HomeFormGA"]]

    away_form = long.rename(columns={
        "Points_lastN": "AwayFormPoints",
        "GF_lastN": "AwayFormGF",
        "GA_lastN": "AwayFormGA",
    })[["Date", "Team", "AwayFormPoints", "AwayFormGF", "AwayFormGA"]]

    df = df.merge(home_form, left_on=["Date", "HomeTeam"], right_on=["Date", "Team"], how="left")
    df = df.drop(columns=["Team"])
    df = df.merge(away_form, left_on=["Date", "AwayTeam"], right_on=["Date", "Team"], how="left")
    df = df.drop(columns=["Team"], errors="ignore")

    # Derived features
    df["FormDiff"] = df["HomeFormPoints"] - df["AwayFormPoints"]
    df["AttackDiff"] = df["HomeFormGF"] - df["AwayFormGF"]
    df["DefenseDiff"] = df["AwayFormGA"] - df["HomeFormGA"]
    # New interaction features
    df["Elo_Form_Interact"] = df["EloDiff"] * df["FormDiff"]
    df["Attack_Defense_Ratio"] = df["HomeFormGF"] / (df["HomeFormGA"] + 0.1)

    return df


def settle_over_under(total_goals: float, line: float) -> float:
    """
    Settle Over/Under for a given line.
    Returns result from the Over side perspective:
      1.0  = full win (Over)
      0.5  = half win
      0.0  = push
     -0.5  = half loss
     -1.0  = full loss
    """
    if pd.isna(line) or pd.isna(total_goals):
        return np.nan

    # Quarter lines: split into two half-lines
    if abs(line * 4) % 2 == 1:
        half1 = line - 0.25
        half2 = line + 0.25
        r1 = settle_over_under(total_goals, half1)
        r2 = settle_over_under(total_goals, half2)
        return (r1 + r2) / 2

    # Standard settlement
    if total_goals > line:
        return 1.0
    elif total_goals == line:
        return 0.0
    else:
        return -1.0


def classify_ah_outcome(result: float) -> str:
    """Map AH settlement result to category label"""
    if pd.isna(result):
        return "unknown"
    if result >= 0.99:
        return "full_win"
    elif result >= 0.4:
        return "half_win"
    elif abs(result) < 0.1:
        return "push"
    elif result <= -0.99:
        return "full_loss"
    else:
        return "half_loss"


def settle_asian_handicap(goal_diff: float, line: float) -> float:
    """
    Settle Asian Handicap for the home team.
    Convention (football-data.co.uk): line is applied to home team.
    Positive line = home receives; negative line = home gives.
    Returns:
      1.0  = full win
      0.5  = half win
      0.0  = push
     -0.5  = half loss
     -1.0  = full loss
    """
    if pd.isna(line) or pd.isna(goal_diff):
        return np.nan

    # Quarter lines: split into two half-lines
    if abs(line * 4) % 2 == 1:
        half1 = line - 0.25
        half2 = line + 0.25
        r1 = settle_asian_handicap(goal_diff, half1)
        r2 = settle_asian_handicap(goal_diff, half2)
        return (r1 + r2) / 2

    # Standard settlement: home covers if goal_diff + line > 0
    adjusted = goal_diff + line
    if adjusted > 0:
        return 1.0
    elif adjusted == 0:
        return 0.0
    else:
        return -1.0


def add_market_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Create target labels for additional markets"""
    df = df.copy()

    # Over/Under with proper settlement (default line 2.5)
    df["TotalGoals"] = df["FTHG"] + df["FTAG"]
    df["OU_Line"] = 2.5  # default; can be overridden later if line data available
    df["OU_Result"] = [
        settle_over_under(tg, line)
        for tg, line in zip(df["TotalGoals"], df["OU_Line"])
    ]
    df["OU25"] = (df["OU_Result"] > 0).astype(float)  # binary for classification

    # BTTS
    df["BTTS"] = ((df["FTHG"] > 0) & (df["FTAG"] > 0)).astype(int)

    # Corners
    if "HC" in df.columns and "AC" in df.columns:
        df["TotalCorners"] = df["HC"] + df["AC"]
        df["CornersOU95"] = (df["TotalCorners"] > 9.5).astype(int)

    # Asian Handicap with proper settlement
    if "AHh" in df.columns:
        df["AH_Line"] = pd.to_numeric(df["AHh"], errors="coerce")
        goal_diff = df["FTHG"] - df["FTAG"]
        df["AH_Result"] = [
            settle_asian_handicap(gd, line)
            for gd, line in zip(goal_diff, df["AH_Line"])
        ]
        df["AH_Outcome"] = df["AH_Result"].apply(classify_ah_outcome)
        df["AH_HomeCover"] = (df["AH_Result"] > 0).astype(float)
        df["AH_AbsLine"] = df["AH_Line"].abs()
    else:
        df["AH_AbsLine"] = 0.0

    # Half-time / Full-time
    if "HTR" in df.columns:
        htft_map = {
            ("H", "H"): 0, ("H", "D"): 1, ("H", "A"): 2,
            ("D", "H"): 3, ("D", "D"): 4, ("D", "A"): 5,
            ("A", "H"): 6, ("A", "D"): 7, ("A", "A"): 8,
        }
        df["HTFT"] = df.apply(
            lambda r: htft_map.get((r.get("HTR"), r.get("FTR")), -1), axis=1
        )

    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full feature pipeline including market targets"""
    print("Calculating Elo ratings...")
    df = calculate_elo(df)
    print("Adding form features...")
    df = add_form_features(df)
    print("Adding market targets...")
    df = add_market_targets(df)

    # Additional simple features
    df["HomeAdvantage"] = 1
    df["TotalGoalsAvg"] = (df["HomeFormGF"] + df["AwayFormGF"]) / 2

    # Drop rows with insufficient history
    feature_cols = get_feature_columns()
    required = feature_cols + ["Result"]
    df = df.dropna(subset=required).reset_index(drop=True)
    return df


def get_feature_columns() -> list[str]:
    return [
        "EloDiff", "HomeElo", "AwayElo",
        "HomeFormPoints", "AwayFormPoints", "FormDiff",
        "HomeFormGF", "AwayFormGF", "AttackDiff",
        "HomeFormGA", "AwayFormGA", "DefenseDiff",
        "TotalGoalsAvg",
    ]
