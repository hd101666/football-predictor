"""
xG features from Understat aggregated team data
"""

import pandas as pd
import numpy as np


# League name mapping
LEAGUE_MAP = {
    "E0": "EPL",
    "SP1": "La_liga",
    "I1": "Serie_A",
    "D1": "Bundesliga",
    "F1": "Ligue_1",
}


def load_understat_xg() -> pd.DataFrame:
    """Load pre-aggregated Understat team xG data"""
    url = "https://raw.githubusercontent.com/vibedatascience/understat_teams_aggregated/main/understat_teams_aggregated_2014_2024.csv"
    df = pd.read_csv(url)
    df["xG_per_match"] = df["xG"] / df["matches"]
    df["xGA_per_match"] = df["xGA"] / df["matches"]
    return df


def add_xg_features(matches: pd.DataFrame, xg_data: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Add pre-match xG strength features.
    Uses previous season xG as proxy for current strength (avoids lookahead).
    """
    if xg_data is None:
        xg_data = load_understat_xg()

    df = matches.copy()

    # Season alignment: use previous season xG to avoid lookahead
    # Football season year = year if month >= 8, else year - 1
    def get_season_year(date):
        if pd.isna(date):
            return None
        return date.year if date.month >= 8 else date.year - 1

    df["SeasonYear"] = df["Date"].apply(get_season_year)
    df["xG_Season"] = df["SeasonYear"] - 1  # previous season

    # Map league codes
    if "League" in df.columns:
        df["xg_league"] = df["League"].map(LEAGUE_MAP)
    else:
        df["xg_league"] = None

    # Extract year from date or season
    if "Date" in df.columns:
        df["year"] = pd.to_datetime(df["Date"]).dt.year
    else:
        df["year"] = 2023

    # Merge home team xG (previous season)
    home_xg = xg_data.rename(columns={
        "team_name": "HomeTeam",
        "xG_per_match": "Home_xG_pm",
        "xGA_per_match": "Home_xGA_pm",
        "npxG": "Home_npxG",
        "npxGA": "Home_npxGA",
    })[["HomeTeam", "league", "year", "Home_xG_pm", "Home_xGA_pm", "Home_npxG", "Home_npxGA"]]

    away_xg = xg_data.rename(columns={
        "team_name": "AwayTeam",
        "xG_per_match": "Away_xG_pm",
        "xGA_per_match": "Away_xGA_pm",
        "npxG": "Away_npxG",
        "npxGA": "Away_npxGA",
    })[["AwayTeam", "league", "year", "Away_xG_pm", "Away_xGA_pm", "Away_npxG", "Away_npxGA"]]

    # Use previous year to avoid leakage
    df["prev_year"] = df["year"] - 1

    df = df.merge(
        home_xg,
        left_on=["HomeTeam", "xg_league", "prev_year"],
        right_on=["HomeTeam", "league", "year"],
        how="left",
        suffixes=("", "_h"),
    )
    df = df.merge(
        away_xg,
        left_on=["AwayTeam", "xg_league", "prev_year"],
        right_on=["AwayTeam", "league", "year"],
        how="left",
        suffixes=("", "_a"),
    )

    # Derived features
    df["xG_Diff"] = df["Home_xG_pm"] - df["Away_xG_pm"]
    df["xGA_Diff"] = df["Away_xGA_pm"] - df["Home_xGA_pm"]
    df["xG_Total"] = df["Home_xG_pm"] + df["Away_xG_pm"]

    # Interaction features
    if "EloDiff" in df.columns:
        df["Elo_xG_Interact"] = df["EloDiff"] * df["xG_Diff"]
        df["Elo_xGA_Interact"] = df["EloDiff"] * df["xGA_Diff"]

    # Fill missing with league average
    for col in ["Home_xG_pm", "Away_xG_pm", "Home_xGA_pm", "Away_xGA_pm", "xG_Diff", "xGA_Diff", "xG_Total"]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    return df


def get_xg_feature_columns() -> list[str]:
    return [
        "Home_xG_pm", "Away_xG_pm", "xG_Diff",
        "Home_xGA_pm", "Away_xGA_pm", "xGA_Diff",
        "xG_Total",
    ]
