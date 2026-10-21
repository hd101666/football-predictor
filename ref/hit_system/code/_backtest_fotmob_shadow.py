# -*- coding: utf-8 -*-
# _backtest_fotmob_shadow.py — 用历史真实盘口+真实赛果回测FotMob三个市场信号
# (独赢moneyline / 整场大小球totals / 球队大小team_total)，直接写入
# shadow_recommendations(shadow_type='fotmob_1x2'/'fotmob_totals'/'fotmob_team_total')，
# 加速积累样本到转正门槛，不用等未来比赛一天天攒。
#
# 跟 _backtest_team_total_shadow.py 同一套模式：复用生产环境同一套 get_model_probs()
# 融合公式(book50%+泊松30%+ELO20%)和 21_auto_settle.py 的 _settle_result() 判负逻辑，
# FotMob信号跟现有model_prob按0.85/0.15融合(跟00_命中系统.py里fotmob_1x2实盘桶
# 同一个blend比例)，不是另起一套简化算法。
#
# 大小球/球队大小用 get_fotmob_totals_probs()/get_fotmob_team_total_probs()，在真实
# 盘口线上算(不是硬编码2.5线)，见这两个函数定义处的说明。
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3, importlib
from datetime import datetime, timezone
import env_setup
from config import DB_ENGINE_URL, KELLY_FRACTION, KELLY_MAX_RATIO

_sys_mod = importlib.import_module('00_命中系统')
get_model_probs             = _sys_mod.get_model_probs
get_fotmob_shots_probs      = _sys_mod.get_fotmob_shots_probs
get_fotmob_xg_probs         = _sys_mod.get_fotmob_xg_probs
get_fotmob_totals_probs     = _sys_mod.get_fotmob_totals_probs
get_fotmob_team_total_probs = _sys_mod.get_fotmob_team_total_probs
preload_xg_caches           = _sys_mod.preload_xg_caches

_settle_mod = importlib.import_module('21_auto_settle')
_settle_result = _settle_mod._settle_result

DB_PATH = DB_ENGINE_URL.replace('sqlite:///', '')
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

print("预加载xG/射正缓存（preload_xg_caches，内存查找代替逐场DB查询）...")
t_pre = time.time()
preload_xg_caches()
print(f"  完成，耗时{time.time()-t_pre:.0f}s\n")

_MIN_PROB_GATE = 0.50
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _blend_and_write(shadow_type, market, uid, sport, league, home, away, kickoff,
                      outcome, line, odds_val, model_prob_primary, fm_p, hs, aws, written):
    if fm_p is None or model_prob_primary is None or not odds_val or odds_val <= 1:
        return
    blended = 0.85 * model_prob_primary + 0.15 * fm_p
    if blended < _MIN_PROB_GATE:
        return
    raw_k = (blended * odds_val - 1) / (odds_val - 1)
    raw_k = max(0.0, min(raw_k * KELLY_FRACTION, KELLY_MAX_RATIO))
    if raw_k <= 0:
        written["skipped_gate"] += 1
        return
    result = _settle_result(market, outcome, line, hs, aws, odds_val)
    if result not in ("win", "lose", "push"):
        return
    profit = (odds_val - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
    try:
        cur.execute("""
            INSERT OR IGNORE INTO shadow_recommendations
            (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
             shadow_type, market, outcome, handicap, best_odds, model_prob,
             kelly_fraction, hit_score, predicted_score, fetch_date, created_at,
             status, profit_loss)
            VALUES (?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?,?, ?,?)
        """, (uid, sport, league, home, away, kickoff,
              shadow_type, market, outcome, line, round(odds_val, 4), round(blended, 4),
              round(raw_k, 4), round(blended, 4), "-", (kickoff or "")[:10], now_iso,
              result, round(profit, 4)))
        written[result] += 1
    except Exception as e:
        print(f"  写入异常 {uid}/{outcome}: {e}")


def _report(shadow_type, written, t0, n_candidates):
    print(f"  候选场次: {n_candidates}  耗时{time.time()-t0:.0f}s")
    print(f"  写入: win={written['win']} lose={written['lose']} push={written['push']}  "
          f"未过滤门槛跳过={written['skipped_gate']}  无盘口跳过={written['no_line']}")
    cur.execute("""
        SELECT status, best_odds FROM shadow_recommendations
        WHERE shadow_type=? AND status IN ('win','lose')
    """, (shadow_type,))
    rows = cur.fetchall()
    n = len(rows)
    if n == 0:
        print(f"  {shadow_type}: 无已结算样本（累计，含本次前已有的）\n")
        return
    pnl = sum((r[1] - 1.0) if r[0] == 'win' else -1.0 for r in rows)
    roi = pnl / n
    win_rate = sum(1 for r in rows if r[0] == 'win') / n
    print(f"  【{shadow_type} 累计回测结果】 n={n}  胜率={win_rate:.1%}  平注ROI={roi:+.1%}\n")


# ══════════════ 1. fotmob_1x2（独赢，home/away两个方向，跟实盘桶同口径）══════════════
print("=== fotmob_1x2 (独赢 home/away) ===")
cur.execute("""
    SELECT um.unified_id, um.sport_code, um.league_name, um.home_team_std, um.away_team_std,
           um.kickoff_utc, um.home_score, um.away_score
    FROM unified_matches um
    WHERE um.sport_code IN ('soccer','football')
      AND um.home_score IS NOT NULL AND um.away_score IS NOT NULL
      AND EXISTS (SELECT 1 FROM unified_odds uo WHERE uo.unified_id=um.unified_id AND uo.market='moneyline')
""")
matches_1x2 = cur.fetchall()
written_1x2 = {"win": 0, "lose": 0, "push": 0, "skipped_gate": 0, "no_line": 0}
t0 = time.time()
for i, (uid, sport_raw, league, home, away, kickoff, hs, aws) in enumerate(matches_1x2):
    sport = "football"
    cur.execute("""
        SELECT outcome, odds_value, fetch_date FROM unified_odds
        WHERE unified_id=? AND market='moneyline' ORDER BY fetch_date DESC
    """, (uid,))
    rows = cur.fetchall()
    if not rows:
        written_1x2["no_line"] += 1
        continue
    latest_fd = rows[0][2]
    latest = [r for r in rows if r[2] == latest_fd]
    bp = {outc: 1.0 / odds_v for outc, odds_v, _ in latest
          if outc in ('home', 'draw', 'away') and odds_v and odds_v > 1}
    if 'home' not in bp or 'away' not in bp:
        written_1x2["no_line"] += 1
        continue
    odds_map = {outc: odds_v for outc, odds_v, _ in latest}

    fm_probs = get_fotmob_shots_probs(home, away, league) or get_fotmob_xg_probs(home, away, league)
    if not fm_probs:
        continue
    try:
        probs = get_model_probs(uid, home, away, league, sport, book_probs=bp)
    except Exception:
        continue

    for outcome in ('home', 'away'):
        _blend_and_write("fotmob_1x2", "moneyline", uid, sport, league, home, away, kickoff,
                          outcome, None, odds_map.get(outcome), probs.get(outcome),
                          fm_probs.get(outcome), hs, aws, written_1x2)
    if (i + 1) % 50 == 0:
        conn.commit()
        print(f"  进度 {i+1}/{len(matches_1x2)}  耗时{time.time()-t0:.0f}s")
conn.commit()
_report("fotmob_1x2", written_1x2, t0, len(matches_1x2))


# ══════════════ 2. fotmob_totals（整场大小球 over/under，真实盘口线）══════════════
print("=== fotmob_totals (整场大小球 over/under) ===")
cur.execute("""
    SELECT um.unified_id, um.sport_code, um.league_name, um.home_team_std, um.away_team_std,
           um.kickoff_utc, um.home_score, um.away_score
    FROM unified_matches um
    WHERE um.sport_code IN ('soccer','football')
      AND um.home_score IS NOT NULL AND um.away_score IS NOT NULL
      AND EXISTS (SELECT 1 FROM unified_odds uo WHERE uo.unified_id=um.unified_id AND uo.market='total')
""")
matches_tot = cur.fetchall()
written_tot = {"win": 0, "lose": 0, "push": 0, "skipped_gate": 0, "no_line": 0}
t0 = time.time()
for i, (uid, sport_raw, league, home, away, kickoff, hs, aws) in enumerate(matches_tot):
    sport = "football"
    cur.execute("""
        SELECT outcome, odds_value, handicap, fetch_date FROM unified_odds
        WHERE unified_id=? AND market='total' ORDER BY fetch_date DESC
    """, (uid,))
    rows = cur.fetchall()
    if not rows:
        written_tot["no_line"] += 1
        continue
    latest_fd = rows[0][3]
    latest = [r for r in rows if r[3] == latest_fd]
    over_row = next((r for r in latest if r[0] == 'over'), None)
    under_row = next((r for r in latest if r[0] == 'under'), None)
    if not over_row or not under_row or over_row[2] is None:
        written_tot["no_line"] += 1
        continue
    line = over_row[2]
    bp = {"over": 1.0 / over_row[1], "under": 1.0 / under_row[1]}

    fm_probs = get_fotmob_totals_probs(home, away, league, line=line)
    if not fm_probs:
        continue
    try:
        probs = get_model_probs(uid, home, away, league, sport, book_probs=bp, total_line=line)
    except Exception:
        continue

    for outcome, odds_row in (("over", over_row), ("under", under_row)):
        _blend_and_write("fotmob_totals", "total", uid, sport, league, home, away, kickoff,
                          outcome, line, odds_row[1], probs.get(outcome),
                          fm_probs.get(outcome), hs, aws, written_tot)
    if (i + 1) % 50 == 0:
        conn.commit()
        print(f"  进度 {i+1}/{len(matches_tot)}  耗时{time.time()-t0:.0f}s")
conn.commit()
_report("fotmob_totals", written_tot, t0, len(matches_tot))


# ══════════════ 3. fotmob_team_total（球队大小 over/under，真实盘口线，含home/away变体）══════════════
print("=== fotmob_team_total (球队大小 over/under) ===")
cur.execute("""
    SELECT um.unified_id, um.sport_code, um.league_name, um.home_team_std, um.away_team_std,
           um.kickoff_utc, um.home_score, um.away_score
    FROM unified_matches um
    WHERE um.sport_code IN ('soccer','football')
      AND um.home_score IS NOT NULL AND um.away_score IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM unified_odds uo WHERE uo.unified_id=um.unified_id
            AND uo.market IN ('team_total','team_total_home','team_total_away')
      )
""")
matches_tt = cur.fetchall()
written_tt = {"win": 0, "lose": 0, "push": 0, "skipped_gate": 0, "no_line": 0}
t0 = time.time()
for i, (uid, sport_raw, league, home, away, kickoff, hs, aws) in enumerate(matches_tt):
    sport = "football"
    for market, side in (("team_total_home", "home"), ("team_total_away", "away"), ("team_total", "home")):
        cur.execute("""
            SELECT outcome, odds_value, handicap, fetch_date FROM unified_odds
            WHERE unified_id=? AND market=? ORDER BY fetch_date DESC
        """, (uid, market))
        rows = cur.fetchall()
        if not rows:
            continue
        latest_fd = rows[0][3]
        latest = [r for r in rows if r[3] == latest_fd]
        over_row = next((r for r in latest if r[0] == 'over'), None)
        under_row = next((r for r in latest if r[0] == 'under'), None)
        if not over_row or not under_row or over_row[2] is None:
            continue
        line = over_row[2]
        bp_key = f"{market}_over" if market != "team_total" else "team_total_over"
        bp_key_u = f"{market}_under" if market != "team_total" else "team_total_under"
        bp = {bp_key: 1.0 / over_row[1], bp_key_u: 1.0 / under_row[1]}
        kw = {}
        if market == "team_total_home":
            kw["team_total_home_line"] = line
        elif market == "team_total_away":
            kw["team_total_away_line"] = line
        else:
            kw["team_total_line"] = line

        fm_probs = get_fotmob_team_total_probs(home, away, league, side=side, line=line)
        if not fm_probs:
            continue
        try:
            probs = get_model_probs(uid, home, away, league, sport, book_probs=bp, **kw)
        except Exception:
            continue

        lookup_over = bp_key
        lookup_under = bp_key_u
        for outcome, odds_row, lk in (("over", over_row, lookup_over), ("under", under_row, lookup_under)):
            model_prob = probs.get(lk)
            if model_prob is None and market == "team_total":
                model_prob = probs.get(outcome)
            _blend_and_write("fotmob_team_total", market, uid, sport, league, home, away, kickoff,
                              outcome, line, odds_row[1], model_prob,
                              fm_probs.get(outcome), hs, aws, written_tt)
        break  # 一场比赛三种market变体按优先级只取第一个有数据的，避免重复计入
    if (i + 1) % 50 == 0:
        conn.commit()
        print(f"  进度 {i+1}/{len(matches_tt)}  耗时{time.time()-t0:.0f}s")
conn.commit()
_report("fotmob_team_total", written_tt, t0, len(matches_tt))

conn.close()
print("全部完成。")
