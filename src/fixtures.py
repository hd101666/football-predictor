"""
Upcoming fixtures loader from football-data.co.uk
"""

import pandas as pd
import requests
from io import StringIO
from datetime import datetime


FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"


def load_fixtures() -> pd.DataFrame:
    """Download upcoming fixtures with odds."""
    print("Downloading fixtures...")
    resp = requests.get(FIXTURES_URL, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text), encoding="utf-8-sig")
    # Clean BOM from column names
    df.columns = [c.replace("\ufeff", "").replace("ï»¿", "") for c in df.columns]
    if "Div" in df.columns:
        df = df.rename(columns={"Div": "League"})
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    # Filter to Big 5
    big5 = ["E0", "SP1", "I1", "D1", "F1"]
    df = df[df["League"].isin(big5)].copy()
    print(f"Loaded {len(df)} upcoming fixtures")
    return df


def filter_upcoming(df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    """Filter fixtures within next N days (including today)."""
    now = pd.Timestamp.now().normalize()
    end = now + pd.Timedelta(days=days)
    # Include today and future
    mask = (df["Date"] >= now) & (df["Date"] <= end)
    result = df[mask].copy()
    # If empty, return most recent fixtures as fallback
    if result.empty and not df.empty:
        result = df.sort_values("Date").tail(10)
    return result
    """Filter fixtures within next N days."""
    now = datetime.now()
    end = now + pd.Timedelta(days=days)
    mask = (df["Date"] >= now) & (df["Date"] <= end)
    return df[mask].copy()


if __name__ == "__main__":
    fixtures = load_fixtures()
    upcoming = filter_upcoming(fixtures, days=14)
    print(upcoming[["Date", "League", "HomeTeam", "AwayTeam"]].head(10))
