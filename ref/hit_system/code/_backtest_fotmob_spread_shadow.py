# -*- coding: utf-8 -*-
# _backtest_fotmob_spread_shadow.py — 用历史真实让球盘口+真实赛果回测FotMob让球(spread)信号，
# 写入shadow_recommendations(shadow_type='fotmob_spread')，加速积累样本。
#
# 跟_backtest_fotmob_shadow.py同一套模式：复用生产环境同一套get_model_probs()融合公式和
# 21_auto_settle.py的_settle_result()判负逻辑，FotMob让球信号(get_fotmob_spread_probs()，
# 联合泊松矩阵积分覆盖概率)跟现有model_prob按0.85/0.15融合，同一口径。
#
# 让球市场目前没有独立的P_poisson分量(足球侧只有LSTM margin~Normal校准法，
# 见_lstm_spread_cover_prob())，FotMob是这个市场第一个基于真实进球分布的信号。
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3, importlib
from datetime import datetime, timezone
import env_setup
from config import DB_ENGINE_URL, KELLY_FRACTION, KELLY_MAX_RATIO

_sys_mod = importlib.import_module('00_命中系统')
get_model_probs         = _sys_mod.get_model_probs
get_fotmob_spread_probs = _sys_mod.get_fotmob_spread_probs
preload_xg_caches       = _sys_mod.preload_xg_caches

_settle_mod = importlib.import_module('21_auto_settle')
_settle_result = _settle_mod._settle_result

DB_PATH = DB_ENGINE_URL.replace('sqlite:///', '')
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

print("预加载xG/射正缓存...")
preload_xg_caches()

_MIN_PROB_GATE = 0.50
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

cur.execute("""
    SELECT um.unified_id, um.sport_code, um.league_name, um.home_team_std, um.away_team_std,
           um.kickoff_utc, um.home_score, um.away_score
    FROM unified_matches um
    WHERE um.sport_code IN ('soccer','football')
      AND um.home_score IS NOT NULL AND um.away_score IS NOT NULL
      AND EXISTS (SELECT 1 FROM unified_odds uo WHERE uo.unified_id=um.unified_id AND uo.market='spread')
""")
matches = cur.fetchall()
print(f"候选历史场次: {len(matches)}")

written = {"win": 0, "lose": 0, "push": 0, "skipped_gate": 0, "no_line": 0}
t0 = time.time()

for i, (uid, sport_raw, league, home, away, kickoff, hs, aws) in enumerate(matches):
    sport = "football"
    cur.execute("""
        SELECT outcome, odds_value, handicap, fetch_date FROM unified_odds
        WHERE unified_id=? AND market='spread' ORDER BY fetch_date DESC
    """, (uid,))
    rows = cur.fetchall()
    if not rows:
        written["no_line"] += 1
        continue
    latest_fd = rows[0][3]
    latest = [r for r in rows if r[3] == latest_fd]
    home_row = next((r for r in latest if r[0] == 'home'), None)
    away_row = next((r for r in latest if r[0] == 'away'), None)
    if not home_row or not away_row or home_row[2] is None:
        written["no_line"] += 1
        continue
    bp = {"home": 1.0 / home_row[1], "away": 1.0 / away_row[1]} if home_row[1] > 1 and away_row[1] > 1 else {}
    if not bp:
        written["no_line"] += 1
        continue

    try:
        probs = get_model_probs(uid, home, away, league, sport, book_probs=bp)
    except Exception:
        continue

    for outcome, odds_row in (("home", home_row), ("away", away_row)):
        line = odds_row[2]
        if line is None:
            continue
        model_prob = probs.get(outcome)
        if model_prob is None:
            continue
        fm_p_raw = get_fotmob_spread_probs(home, away, league, outcome, line)
        fm_p = fm_p_raw.get(outcome) if fm_p_raw else None
        if fm_p is None:
            continue
        odds_val = odds_row[1]
        if not odds_val or odds_val <= 1:
            continue
        blended = 0.85 * model_prob + 0.15 * fm_p
        if blended < _MIN_PROB_GATE:
            continue
        raw_k = (blended * odds_val - 1) / (odds_val - 1)
        raw_k = max(0.0, min(raw_k * KELLY_FRACTION, KELLY_MAX_RATIO))
        if raw_k <= 0:
            written["skipped_gate"] += 1
            continue
        result = _settle_result("spread", outcome, line, hs, aws, odds_val)
        if result not in ("win", "lose", "push"):
            continue
        profit = (odds_val - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
        try:
            cur.execute("""
                INSERT OR IGNORE INTO shadow_recommendations
                (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                 shadow_type, market, outcome, handicap, best_odds, model_prob,
                 kelly_fraction, hit_score, predicted_score, fetch_date, created_at,
                 status, profit_loss)
                VALUES (?,?,?,?,?,?, 'fotmob_spread','spread',?,?,?,?,?,?,?,?,?, ?,?)
            """, (uid, sport, league, home, away, kickoff,
                  outcome, line, round(odds_val, 4), round(blended, 4),
                  round(raw_k, 4), round(blended, 4), "-", (kickoff or "")[:10], now_iso,
                  result, round(profit, 4)))
            written[result] += 1
        except Exception as e:
            print(f"  写入异常 {uid}/{outcome}: {e}")

    if (i + 1) % 30 == 0:
        conn.commit()
        print(f"  进度 {i+1}/{len(matches)}  耗时{time.time()-t0:.0f}s")

conn.commit()
print(f"\n完成，总耗时 {time.time()-t0:.0f}s")
print(f"写入: win={written['win']} lose={written['lose']} push={written['push']}  "
      f"未过滤门槛跳过={written['skipped_gate']}  无盘口跳过={written['no_line']}")

cur.execute("""
    SELECT status, best_odds FROM shadow_recommendations
    WHERE shadow_type='fotmob_spread' AND status IN ('win','lose')
""")
rows = cur.fetchall()
n = len(rows)
if n == 0:
    print("fotmob_spread: 无已结算样本")
else:
    pnl = sum((r[1] - 1.0) if r[0] == 'win' else -1.0 for r in rows)
    print(f"【fotmob_spread 累计回测结果】 n={n}  胜率={sum(1 for r in rows if r[0]=='win')/n:.1%}  "
          f"平注ROI={pnl/n:+.1%}")

conn.close()
