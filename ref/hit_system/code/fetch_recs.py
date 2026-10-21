# -*- coding: utf-8 -*-
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/sports_data.db')
c = conn.cursor()
c.execute("""
SELECT league_name, home_team, away_team, kickoff_utc, market, outcome,
       best_odds, model_prob, kelly_fraction, hit_score, handicap, reason
FROM hit_recommendations
WHERE fetch_date = '2026-06-09'
  AND is_filtered = 0
ORDER BY hit_score DESC
LIMIT 20
""")
rows = c.fetchall()
for r in rows:
    print('|'.join(str(x) if x is not None else '' for x in r))
conn.close()
