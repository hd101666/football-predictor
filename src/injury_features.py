"""
Injury / availability features from Transfermarkt-derived panel data
"""

import pandas as pd
import numpy as np

LEAGUE_MAP = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
}


def load_injury_panel() -> pd.DataFrame:
    """Load club-season injury burden data"""
    url = "https://raw.githubusercontent.com/withqwerty/availability-data/main/cleaned/panel.csv"
    df = pd.read_csv(url)
    return df


def add_injury_features(matches: pd.DataFrame, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Add pre-match injury burden features.
    Uses previous season injury_burden to avoid lookahead.
    """
    if panel is None:
        panel = load_injury_panel()

    df = matches.copy()
    if "Date" in df.columns:
        df["year"] = pd.to_datetime(df["Date"]).dt.year
    else:
        df["year"] = 2023

    df["inj_league"] = df.get("League", pd.Series(dtype=str)).map(LEAGUE_MAP)
    df["prev_season"] = df["year"] - 1

    # Prepare panel
    panel = panel.rename(columns={
        "club": "team",
        "injury_burden": "inj_burden",
        "injured_matchdays": "inj_days",
    })

    home_inj = panel.rename(columns={
        "team": "HomeTeam",
        "inj_burden": "Home_InjBurden",
        "inj_days": "Home_InjDays",
    })[["HomeTeam", "league_name", "season", "Home_InjBurden", "Home_InjDays"]]

    away_inj = panel.rename(columns={
        "team": "AwayTeam",
        "inj_burden": "Away_InjBurden",
        "inj_days": "Away_InjDays",
    })[["AwayTeam", "league_name", "season", "Away_InjBurden", "Away_InjDays"]]

    df = df.merge(
        home_inj,
        left_on=["HomeTeam", "inj_league", "prev_season"],
        right_on=["HomeTeam", "league_name", "season"],
        how="left",
    )
    df = df.merge(
        away_inj,
        left_on=["AwayTeam", "inj_league", "prev_season"],
        right_on=["AwayTeam", "league_name", "season"],
        how="left",
        suffixes=("", "_a"),
    )

    # Derived
    df["InjBurden_Diff"] = df["Home_InjBurden"] - df["Away_InjBurden"]

    # Fill missing
    for col in ["Home_InjBurden", "Away_InjBurden", "InjBurden_Diff"]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    print(f"Injury feature coverage: {df['Home_InjBurden'].notna().mean():.1%}")
    return df


def get_injury_features() -> list[str]:
    return ["Home_InjBurden", "Away_InjBurden", "InjBurden_Diff"]
