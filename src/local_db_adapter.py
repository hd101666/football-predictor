"""
Local database adapter for sports_data.db.
Maps xG, odds, and injury data into prediction features.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from typing import Optional


class LocalDBAdapter:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> "LocalDBAdapter":
        self.conn = sqlite3.connect(self.db_path)
        return self

    def close(self):
        if self.conn:
            self.conn.close()

    # --- xG ---
    def get_match_xg(self, home: str, away: str, season: int | None = None) -> dict:
        """Get xG for a match from understat_matches."""
        query = """
            SELECT home_xg, away_xg, home_goals, away_goals
            FROM understat_matches
            WHERE home_team LIKE ? AND away_team LIKE ?
        """
        params = [f"%{home}%", f"%{away}%"]
        if season:
            query += " AND season = ?"
            params.append(season)
        query += " ORDER BY match_datetime DESC LIMIT 1"
        df = pd.read_sql(query, self.conn, params=params)
        if df.empty:
            return {"home_xg": None, "away_xg": None}
        return {
            "home_xg": float(df["home_xg"].iloc[0]) if pd.notna(df["home_xg"].iloc[0]) else None,
            "away_xg": float(df["away_xg"].iloc[0]) if pd.notna(df["away_xg"].iloc[0]) else None,
        }

    def get_team_avg_xg(self, team: str, n: int = 5) -> dict:
        """Get rolling average xG for a team."""
        query = """
            SELECT AVG(home_xg) as avg_xg, AVG(away_xg) as avg_xga
            FROM (
                SELECT home_xg, NULL as away_xg FROM understat_matches WHERE home_team LIKE ?
                UNION ALL
                SELECT NULL, away_xg FROM understat_matches WHERE away_team LIKE ?
                LIMIT ?
            )
        """
        df = pd.read_sql(query, self.conn, params=[f"%{team}%", f"%{team}%", n * 2])
        return {
            "avg_xg": float(df["avg_xg"].iloc[0]) if pd.notna(df["avg_xg"].iloc[0]) else None,
            "avg_xga": float(df["avg_xga"].iloc[0]) if pd.notna(df["avg_xga"].iloc[0]) else None,
        }

    # --- Odds ---
    def get_pinnacle_odds(self, unified_id: str) -> dict:
        """Get Pinnacle 1X2 odds for a match."""
        query = """
            SELECT outcome, odds_value
            FROM unified_odds
            WHERE unified_id = ? AND source = 'pinnacle' AND market = 'moneyline'
        """
        df = pd.read_sql(query, self.conn, params=(unified_id,))
        odds = {"H": None, "D": None, "A": None}
        for _, row in df.iterrows():
            if row["outcome"] == "home":
                odds["H"] = float(row["odds_value"])
            elif row["outcome"] == "draw":
                odds["D"] = float(row["odds_value"])
            elif row["outcome"] == "away":
                odds["A"] = float(row["odds_value"])
        return odds

    def get_latest_pinnacle_odds(self, limit: int = 10) -> pd.DataFrame:
        """Get latest Pinnacle odds snapshots."""
        query = """
            SELECT unified_id, outcome, odds_value, fetch_date
            FROM unified_odds
            WHERE source = 'pinnacle' AND market = 'moneyline'
            ORDER BY fetch_date DESC
            LIMIT ?
        """
        return pd.read_sql(query, self.conn, params=(limit,))

    # --- Injuries ---
    def get_match_injuries_okooo(self, match_id: str) -> pd.DataFrame:
        """Get injuries from okooo_injuries."""
        query = """
            SELECT player_name, side, team, reason, will_miss, position
            FROM okooo_injuries
            WHERE match_id = ?
        """
        return pd.read_sql(query, self.conn, params=(match_id,))

    def get_team_injury_risk(self, team: str) -> dict:
        """Get injury risk summary for a team from player_availability."""
        query = """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN availability_status IN ('unavailable', 'sidelined') THEN 1 ELSE 0 END) as out
            FROM player_availability
            WHERE team_name LIKE ? AND provided = 1
        """
        df = pd.read_sql(query, self.conn, params=(f"%{team}%",))
        total = int(df["total"].iloc[0])
        out = int(df["out"].iloc[0] or 0)
        risk = "low"
        if out >= 3:
            risk = "high"
        elif out >= 1:
            risk = "medium"
        return {"total": total, "unavailable": out, "risk": risk}

    def get_odds_by_teams(self, home: str, away: str) -> dict:
        """Get latest Pinnacle odds by team names via unified_matches."""
        query = """
            SELECT uo.outcome, uo.odds_value
            FROM unified_odds uo
            JOIN unified_matches um ON uo.unified_id = um.unified_id
            WHERE um.home_team LIKE ? AND um.away_team LIKE ?
              AND uo.source = 'pinnacle' AND uo.market = 'moneyline'
            ORDER BY uo.fetch_date DESC
            LIMIT 3
        """
        df = pd.read_sql(query, self.conn, params=(f"%{home}%", f"%{away}%"))
        odds = {"H": None, "D": None, "A": None}
        for _, row in df.iterrows():
            key = {"home": "H", "draw": "D", "away": "A"}.get(row["outcome"])
            if key and odds[key] is None:
                odds[key] = float(row["odds_value"])
        return odds

    def get_team_latest_features(self, team: str, hist_df: pd.DataFrame) -> dict:
        """Get latest rolling features for a team from historical data."""
        team_hist = hist_df[
            (hist_df["HomeTeam"].str.contains(team, case=False, na=False)) |
            (hist_df["AwayTeam"].str.contains(team, case=False, na=False))
        ].sort_values("Date").tail(1)
        if team_hist.empty:
            return {}
        row = team_hist.iloc[0]
        return {c: row[c] for c in row.index if c in [
            "EloDiff", "HomeElo", "AwayElo", "HomeForm", "AwayForm",
            "Home_xG_pm", "Away_xG_pm", "xG_Diff"
        ]}

    def export_xg_features(self) -> pd.DataFrame:
        """Export team-level xG averages from understat_matches for feature joining."""
        query = """
            SELECT 
                home_team AS team,
                league,
                season,
                AVG(home_xg) AS xg_for,
                AVG(away_xg) AS xg_against,
                COUNT(*) AS matches
            FROM understat_matches
            WHERE home_xg IS NOT NULL
            GROUP BY home_team, league, season
            UNION ALL
            SELECT 
                away_team AS team,
                league,
                season,
                AVG(away_xg) AS xg_for,
                AVG(home_xg) AS xg_against,
                COUNT(*) AS matches
            FROM understat_matches
            WHERE away_xg IS NOT NULL
            GROUP BY away_team, league, season
        """
        return pd.read_sql(query, self.conn)

    def export_injury_features(self) -> pd.DataFrame:
        """Export team-level injury burden from player_availability."""
        query = """
            SELECT 
                team_name AS team,
                COUNT(*) AS total_records,
                SUM(CASE WHEN availability_status IN ('unavailable', 'sidelined') THEN 1 ELSE 0 END) AS unavailable,
                SUM(CASE WHEN availability_status = 'doubtful' THEN 1 ELSE 0 END) AS doubtful
            FROM player_availability
            WHERE provided = 1 AND team_name IS NOT NULL
            GROUP BY team_name
        """
        return pd.read_sql(query, self.conn)

    def enrich_matches(self, matches: pd.DataFrame) -> pd.DataFrame:
        """
        Add local DB xG and injury features to a matches DataFrame.
        Expects columns: HomeTeam, AwayTeam, Date (or match_date).
        """
        df = matches.copy()
        xg = self.export_xg_features()
        inj = self.export_injury_features()

        if not xg.empty:
            # Average xG per team across seasons for simplicity
            team_xg = xg.groupby("team").agg({"xg_for": "mean", "xg_against": "mean"}).reset_index()
            df = df.merge(team_xg.rename(columns={"team": "HomeTeam", "xg_for": "Home_xG_local", "xg_against": "Home_xGA_local"}),
                          on="HomeTeam", how="left")
            df = df.merge(team_xg.rename(columns={"team": "AwayTeam", "xg_for": "Away_xG_local", "xg_against": "Away_xGA_local"}),
                          on="AwayTeam", how="left")
            df["xG_Diff_local"] = df["Home_xG_local"] - df["Away_xG_local"]

        if not inj.empty:
            df = df.merge(inj.rename(columns={"team": "HomeTeam", "unavailable": "Home_Inj", "doubtful": "Home_Doubt"}),
                          on="HomeTeam", how="left")
            df = df.merge(inj.rename(columns={"team": "AwayTeam", "unavailable": "Away_Inj", "doubtful": "Away_Doubt"}),
                          on="AwayTeam", how="left")
            df["InjuryDiff"] = df["Home_Inj"].fillna(0) - df["Away_Inj"].fillna(0)

        return df

    def get_injury_features(self, home: str, away: str) -> dict:
        """Generate injury features for a match."""
        h = self.get_team_injury_risk(home)
        a = self.get_team_injury_risk(away)
        return {
            "home_unavailable": h["unavailable"],
            "away_unavailable": a["unavailable"],
            "injury_diff": h["unavailable"] - a["unavailable"],
            "home_risk": h["risk"],
            "away_risk": a["risk"],
            "combined_risk": "high" if h["risk"] == "high" or a["risk"] == "high" else (
                "medium" if h["risk"] == "medium" or a["risk"] == "medium" else "low"
            ),
        }

    def get_best_odds(self, home: str, away: str) -> dict:
        """Get best available odds across bookmakers."""
        query = """
            SELECT uo.source, uo.outcome, uo.odds_value
            FROM unified_odds uo
            JOIN unified_matches um ON uo.unified_id = um.unified_id
            WHERE um.home_team LIKE ? AND um.away_team LIKE ?
              AND uo.market = 'moneyline'
            ORDER BY uo.fetch_date DESC
        """
        df = pd.read_sql(query, self.conn, params=(f"%{home}%", f"%{away}%"))
        if df.empty:
            return {"H": None, "D": None, "A": None}
        best = {"H": 0, "D": 0, "A": 0}
        mapping = {"home": "H", "draw": "D", "away": "A"}
        for _, row in df.iterrows():
            key = mapping.get(row["outcome"])
            if key and row["odds_value"] > best[key]:
                best[key] = float(row["odds_value"])
        return {k: v if v > 0 else None for k, v in best.items()}


def load_local_db(db_path: str = r"D:\cl\qqsj\data\sports_data.db") -> Optional[LocalDBAdapter]:
    """Load adapter if database exists."""
    if Path(db_path).exists():
        return LocalDBAdapter(db_path).connect()
    return None


if __name__ == "__main__":
    db = load_local_db()
    if db:
        print("xG sample:", db.get_match_xg("Arsenal", "Chelsea"))
        print("Injury sample:", db.get_injury_features("Arsenal", "Chelsea"))
        print("Pinnacle odds sample:")
        print(db.get_latest_pinnacle_odds(5))
        db.close()
    else:
        print("DB not found")
