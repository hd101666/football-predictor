"""
Injury scraper module.
Fetches current injury lists from Transfermarkt team pages.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.transfermarkt.com/",
    "Connection": "keep-alive",
}

# Transfermarkt team URLs (Big 5 sample)
TEAM_URLS = {
    "Arsenal": "https://www.transfermarkt.com/arsenal-fc/verletzungen/verein/11",
    "Chelsea": "https://www.transfermarkt.com/chelsea-fc/verletzungen/verein/631",
    "Liverpool": "https://www.transfermarkt.com/fc-liverpool/verletzungen/verein/31",
    "Man City": "https://www.transfermarkt.com/manchester-city/verletzungen/verein/281",
    "Man United": "https://www.transfermarkt.com/manchester-united/verletzungen/verein/985",
    "Tottenham": "https://www.transfermarkt.com/tottenham-hotspur/verletzungen/verein/148",
    "Real Madrid": "https://www.transfermarkt.com/real-madrid/verletzungen/verein/418",
    "Barcelona": "https://www.transfermarkt.com/fc-barcelona/verletzungen/verein/131",
    "Bayern Munich": "https://www.transfermarkt.com/fc-bayern-munchen/verletzungen/verein/27",
    "Dortmund": "https://www.transfermarkt.com/borussia-dortmund/verletzungen/verein/16",
    "Inter": "https://www.transfermarkt.com/inter-mailand/verletzungen/verein/46",
    "Milan": "https://www.transfermarkt.com/ac-mailand/verletzungen/verein/5",
    "Juventus": "https://www.transfermarkt.com/juventus-turin/verletzungen/verein/506",
    "Napoli": "https://www.transfermarkt.com/ssc-neapel/verletzungen/verein/6195",
    "Paris SG": "https://www.transfermarkt.com/paris-saint-germain/verletzungen/verein/583",
}


def scrape_team_injuries(team_name: str, url: str) -> list[dict]:
    """Scrape injury table for one team."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        injuries = []
        table = soup.select_one("table.items")
        if not table:
            return []
        for row in table.select("tbody tr"):
            cells = row.select("td")
            if len(cells) < 4:
                continue
            player = cells[0].get_text(strip=True)
            # Clean player name
            player = re.sub(r"\s+", " ", player)
            reason = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            since = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            until = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            if player and player != "Player":
                injuries.append({
                    "team": team_name,
                    "player": player,
                    "reason": reason,
                    "since": since,
                    "until": until,
                    "scraped_at": datetime.now().isoformat(),
                })
        return injuries
    except Exception as e:
        print(f"Error scraping {team_name}: {e}")
        return []


def scrape_all_injuries(teams: dict | None = None, delay: float = 1.5) -> pd.DataFrame:
    """Scrape injuries for all teams in TEAM_URLS or custom dict."""
    targets = teams or TEAM_URLS
    all_injuries = []
    for name, url in targets.items():
        print(f"Scraping {name}...")
        injuries = scrape_team_injuries(name, url)
        all_injuries.extend(injuries)
        time.sleep(delay)
    df = pd.DataFrame(all_injuries)
    return df


def save_injuries(df: pd.DataFrame, path: str = "data/injuries_live.csv"):
    """Save scraped injuries to CSV."""
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} injury records to {path}")
    return path


def get_team_injury_burden(df: pd.DataFrame, team: str) -> dict:
    """Summarize injury burden for one team."""
    team_df = df[df["team"] == team]
    return {
        "team": team,
        "injured_count": len(team_df),
        "players": team_df["player"].tolist(),
        "reasons": team_df["reason"].tolist(),
    }


if __name__ == "__main__":
    print("Starting injury scrape...")
    df = scrape_all_injuries()
    if not df.empty:
        save_injuries(df)
        print(df.groupby("team").size())
    else:
        print("No data scraped.")
