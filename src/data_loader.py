"""
Data loader for football-data.co.uk historical matches
"""

import os
import time
import pandas as pd
import requests
from io import StringIO
from tqdm import tqdm
from .config import LEAGUES, SEASONS, DATA_URL_TEMPLATE, DATA_DIR


def download_league_season(league_code: str, season: str) -> pd.DataFrame | None:
    """Download a single league-season CSV from football-data.co.uk"""
    url = DATA_URL_TEMPLATE.format(season=season, league=league_code)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        # Handle encoding
        content = resp.content.decode("utf-8-sig", errors="replace")
        df = pd.read_csv(StringIO(content))
        if df.empty:
            return None
        df["League"] = league_code
        df["LeagueName"] = LEAGUES.get(league_code, league_code)
        df["Season"] = f"20{season[:2]}-{season[2:]}"
        return df
    except Exception as e:
        print(f"Failed to download {league_code} {season}: {e}")
        return None


def load_all_data(force_download: bool = False) -> pd.DataFrame:
    """
    Download and concatenate all configured league-seasons.
    Caches to data/all_matches.parquet for speed.
    """
    cache_path = os.path.join(DATA_DIR, "all_matches.parquet")
    if os.path.exists(cache_path) and not force_download:
        print(f"Loading cached data from {cache_path}")
        return pd.read_parquet(cache_path)

    os.makedirs(DATA_DIR, exist_ok=True)
    all_dfs = []

    tasks = [(code, season) for code in LEAGUES for season in SEASONS]
    print(f"Downloading {len(tasks)} league-seasons...")

    for league_code, season in tqdm(tasks):
        df = download_league_season(league_code, season)
        if df is not None and not df.empty:
            all_dfs.append(df)
        time.sleep(0.5)  # be polite to the server

    if not all_dfs:
        raise RuntimeError("No data downloaded. Check network or league codes.")

    combined = pd.concat(all_dfs, ignore_index=True)

    # Clean and standardize
    combined = clean_matches(combined)
    combined.to_parquet(cache_path, index=False)
    print(f"Saved {len(combined)} matches to {cache_path}")
    return combined


def clean_matches(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names and types"""
    # Keep essential columns
    essential = [
        "Div", "Date", "HomeTeam", "AwayTeam",
        "FTHG", "FTAG", "FTR",
        "HTHG", "HTAG", "HTR",
        "HS", "AS", "HST", "AST",
        "HC", "AC",
        "HY", "AY", "HR", "AR",
        "B365H", "B365D", "B365A",
        "PSH", "PSD", "PSA",
        "AvgH", "AvgD", "AvgA",
        "League", "LeagueName", "Season",
    ]
    available = [c for c in essential if c in df.columns]
    df = df[available].copy()

    # Parse date
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])

    # Numeric
    for col in ["FTHG", "FTAG", "HTHG", "HTAG"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Result mapping
    result_map = {"H": 0, "D": 1, "A": 2}  # Home, Draw, Away
    df["Result"] = df["FTR"].map(result_map)

    # Odds to implied probabilities (for value calculation later)
    for prefix in ["B365", "PS", "Avg"]:
        for outcome in ["H", "D", "A"]:
            col = f"{prefix}{outcome}"
            if col in df.columns:
                df[f"{prefix}{outcome}_prob"] = 1 / pd.to_numeric(df[col], errors="coerce")

    # Ensure League column
    if "League" not in df.columns and "Div" in df.columns:
        df["League"] = df["Div"]

    df = df.sort_values("Date").reset_index(drop=True)
    return df


if __name__ == "__main__":
    data = load_all_data()
    print(data.head())
    print(f"\nTotal matches: {len(data)}")
    print(f"Leagues: {data['LeagueName'].unique()}")
    print(f"Date range: {data['Date'].min()} to {data['Date'].max()}")
