"""
Local database injury adapter.
Connects to user's sports_data.db and extracts injury features.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from typing import Optional


class LocalInjuryAdapter:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        return self

    def close(self):
        if self.conn:
            self.conn.close()

    def get_match_injuries(self, match_id: str, source: str = "okooo") -> pd.DataFrame:
        """Get injuries for a specific match."""
        if source == "okooo":
            query = """
                SELECT player_name, side, team, reason, will_miss, position
                FROM okooo_injuries
                WHERE match_id = ? AND will_miss = '1'
            """
        elif source == "fotmob":
            query = """
                SELECT player_name, side, reason, availability_type, status
                FROM fotmob_match_availability
                WHERE match_id = ? AND provided = 1
            """
        else:
            query = """
                SELECT player_name, team_name, injury_type, availability_status, expected_return_at
                FROM player_availability
                WHERE source_event_id = ? AND provided = 1
            """
        return pd.read_sql(query, self.conn, params=(match_id,))

    def get_team_injury_count(self, team: str, days: int = 7) -> dict:
        """Get recent injury count for a team from player_availability."""
        query = """
            SELECT COUNT(*) as cnt, 
                   SUM(CASE WHEN availability_status = 'unavailable' THEN 1 ELSE 0 END) as unavailable
            FROM player_availability
            WHERE team_name LIKE ? 
              AND observed_at_utc >= datetime('now', ?)
              AND provided = 1
        """
        df = pd.read_sql(query, self.conn, params=(f"%{team}%", f"-{days} days"))
        return {"total": int(df["cnt"].iloc[0]), "unavailable": int(df["unavailable"].iloc[0] or 0)}

    def get_injury_summary_for_match(self, home: str, away: str) -> dict:
        """Summarize injury risk for a match based on team names."""
        home_inj = self.get_team_injury_count(home)
        away_inj = self.get_team_injury_count(away)
        total = home_inj["unavailable"] + away_inj["unavailable"]
        risk = "low"
        if total >= 4:
            risk = "high"
        elif total >= 2:
            risk = "medium"
        return {
            "home_unavailable": home_inj["unavailable"],
            "away_unavailable": away_inj["unavailable"],
            "total_unavailable": total,
            "combined_risk": risk,
        }

    def list_recent_matches_with_injuries(self, limit: int = 20) -> pd.DataFrame:
        """List recent matches that have injury records."""
        query = """
            SELECT DISTINCT match_id, fetch_date, COUNT(*) as injury_count
            FROM okooo_injuries
            GROUP BY match_id
            ORDER BY fetch_date DESC
            LIMIT ?
        """
        return pd.read_sql(query, self.conn, params=(limit,))


def load_local_injury_adapter(db_path: str = r"D:\cl\qqsj\data\sports_data.db") -> Optional[LocalInjuryAdapter]:
    """Load adapter if database exists."""
    if Path(db_path).exists():
        return LocalInjuryAdapter(db_path).connect()
    return None


if __name__ == "__main__":
    # Test with sample path
    adapter = load_local_injury_adapter()
    if adapter:
        print("Connected to local database")
        print(adapter.list_recent_matches_with_injuries(5))
        adapter.close()
    else:
        print("Database not found at default path")
