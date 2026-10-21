# -*- coding: utf-8 -*-
# _backtest_team_total_shadow.py — 用历史真实盘口+真实赛果回测球队大小(team_total)，
# 把结果直接写入 shadow_recommendations(shadow_type='team_total')，加速积累样本
# 到 TEAM_TOTAL_VALIDATION_MIN_SAMPLES(30场)转正门槛，不用等未来比赛一天天攒。
#
# 复用生产环境同一套 get_model_probs() 融合公式(book50%+泊松30%+ELO20%)和
# 21_auto_settle.py 的 _settle_result() 判负逻辑，跟实盘走的是同一套代码，
# 不是另起一套简化算法。
#
# 数据口径说明：team_total_home/team_total_away(主客队归属明确)的数据只从
# 2026-07-19(Pinnacle归属拆分修复上线日)才开始有，历史比赛只有旧的裸"team_total"
# (主客队归属不明，_settle_result()按现有约定沿用"默认当主队算"简化处理)。
# 这批回测样本继承同样的口径，不是本脚本编的新规则。
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3, importlib
from datetime import datetime, timezone
import env_setup
from config import DB_ENGINE_URL, KELLY_FRACTION, KELLY_MAX_RATIO

_sys_mod = importlib.import_module('00_命中系统')
get_model_probs = _sys_mod.get_model_probs

_settle_mod = importlib.import_module('21_auto_settle')
_settle_result = _settle_mod._settle_result

DB_PATH = DB_ENGINE_URL.replace('sqlite:///', '')
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

# ── 1. 历史场次：有已结算比分 + 有team_total盘口(取该场最新一次抓到的快照) ──
cur.execute("""
    SELECT um.unified_id, um.sport_code, um.league_name, um.home_team_std, um.away_team_std,
           um.kickoff_utc, um.home_score, um.away_score
    FROM unified_matches um
    WHERE um.home_score IS NOT NULL AND um.away_score IS NOT NULL
      AND EXISTS (SELECT 1 FROM unified_odds uo WHERE uo.unified_id=um.unified_id AND uo.market='team_total')
""")
matches = cur.fetchall()
print(f"候选历史场次: {len(matches)}")

t0 = time.time()
written = {"win": 0, "lose": 0, "push": 0, "skipped_gate": 0, "no_line": 0}
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
_MIN_PROB_GATE = 0.50

for i, (uid, sport_raw, league, home, away, kickoff, hs, aws) in enumerate(matches):
    sport = "football" if sport_raw in ("soccer", "football") else sport_raw

    # 该场最新一次抓到的team_total odds快照(over/under各一条，同一handicap)
    cur.execute("""
        SELECT outcome, odds_value, handicap, fetch_date FROM unified_odds
        WHERE unified_id=? AND market='team_total'
        ORDER BY fetch_date DESC
    """, (uid,))
    odds_rows = cur.fetchall()
    if not odds_rows:
        continue
    latest_fd = odds_rows[0][3]
    latest = [r for r in odds_rows if r[3] == latest_fd]
    over_row  = next((r for r in latest if r[0] == "over"), None)
    under_row = next((r for r in latest if r[0] == "under"), None)
    if not over_row or not under_row or over_row[2] is None:
        written["no_line"] += 1
        continue
    line = over_row[2]
    bp = {"team_total_over": 1.0 / over_row[1], "team_total_under": 1.0 / under_row[1]}

    try:
        probs = get_model_probs(uid, home, away, league, sport, book_probs=bp,
                                 team_total_line=line)
    except Exception:
        continue

    for outcome, odds_row in (("over", over_row), ("under", under_row)):
        model_prob = probs.get(f"team_total_{outcome}")
        if model_prob is None:
            continue
        odds_val = odds_row[1]
        if model_prob < _MIN_PROB_GATE or odds_val <= 1:
            continue
        raw_k = (model_prob * odds_val - 1) / (odds_val - 1)
        raw_k = max(0.0, min(raw_k * KELLY_FRACTION, KELLY_MAX_RATIO))
        if raw_k <= 0:
            written["skipped_gate"] += 1
            continue

        result = _settle_result("team_total", outcome, line, hs, aws, odds_val)
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
                VALUES (?,?,?,?,?,?, 'team_total','team_total',?,?,?,?,?,?,?,?,?, ?,?)
            """, (uid, sport, league, home, away, kickoff,
                  outcome, line, round(odds_val, 4), round(model_prob, 4),
                  round(raw_k, 4), round(model_prob, 4), "-",
                  (kickoff or "")[:10], now_iso,
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
      f"未过滤门槛跳过={written['skipped_gate']}  无盘口线跳过={written['no_line']}")

# ── 汇总回测命中率/ROI（跟_team_total_validation_status()同一套算法） ──
for sp in ("football", "basketball"):
    cur.execute("""
        SELECT status, best_odds FROM shadow_recommendations
        WHERE shadow_type='team_total' AND status IN ('win','lose') AND sport_code=?
    """, (sp,))
    rows = cur.fetchall()
    n = len(rows)
    if n == 0:
        print(f"{sp}: 无已结算样本")
        continue
    pnl = sum((r[1] - 1.0) if r[0] == "win" else -1.0 for r in rows)
    roi = pnl / n
    win_rate = sum(1 for r in rows if r[0] == "win") / n
    print(f"{sp}: n={n} 胜率={win_rate:.1%} 平注ROI={roi:+.1%}")

conn.close()
