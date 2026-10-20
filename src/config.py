"""
Configuration for the Football Prediction System
"""

# Big 5 European leagues codes on football-data.co.uk
LEAGUES = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
}

# Seasons to download (format used by football-data.co.uk: YYZZ e.g. 2324 for 2023/24)
# Start from recent seasons for faster prototype; expand later
SEASONS = [
    "1920", "2021", "2122", "2223", "2324", "2425", "2526"
]

# Current season for fixtures
CURRENT_SEASON = "2526"

# Base URL pattern for CSV files
DATA_URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"

# Feature engineering parameters
ELO_K = 20
ELO_HOME_ADVANTAGE = 60  # points
FORM_WINDOW = 5  # last N matches for form features

# Model parameters
TRAIN_TEST_SPLIT_DATE = "2024-01-01"  # for time-based validation
RANDOM_STATE = 42

# Recommendation thresholds (stricter)
MIN_PROBABILITY = 0.62          # raised from 0.58
MIN_EDGE = 0.10                 # raised from 0.08
MIN_VALUE = 0.06                # raised from 0.05
CONFIDENCE_LEVELS = {
    "high": 0.72,
    "medium": 0.66,
    "low": 0.62,
}

# Output paths
DATA_DIR = "data"
MODELS_DIR = "models"
REPORTS_DIR = "reports"
