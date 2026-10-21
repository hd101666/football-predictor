# -*- coding: utf-8 -*-
# _backtest_fotmob_corner_shadow.py — 用历史真实角球盘口(pinnacle_corner_odds)+真实角球
# 终值(corner_stats_final/corner_live_odds兜底)回测FotMob角球信号，写入
# shadow_recommendations(shadow_type='fotmob_corner')，加速积累样本。
#
# 跟_backtest_fotmob_shadow.py同一套模式：复用现有corner_model.predict_corners()当"现有
# model_prob"，跟FotMob角球信号(get_fotmob_corner_probs())按0.85/0.15融合，结算逻辑
# 复用21_auto_settle.py的_fuzzy_match()+settle_fotmob_corner_shadow()同一套ground truth
# 匹配规则(先corner_stats_final，缺失兜底corner_live_odds历史最大值)。
#
# 数据现实：corner_stats_final目前只有14场终值记录，corner_live_odds有1085场兜底记录，
# 均远少于fotmob_1x2/totals/team_total那批(unified_matches全量历史比分)——角球终值本身
# 是这个项目最新、覆盖最薄的数据源(37_corner_stats_scraper.py 2026-07-15才接入调度)，
# 回测样本量上限天然更低，不是本脚本的bug。
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3, importlib
from datetime import datetime, timezone
import env_setup
from config import DB_ENGINE_URL, KELLY_FRACTION, KELLY_MAX_RATIO

_sys_mod = importlib.import_module('00_命中系统')
get_fotmob_corner_probs = _sys_mod.get_fotmob_corner_probs
preload_xg_caches       = _sys_mod.preload_xg_caches

_corner_mod = importlib.import_module('corner_model')
predict_corners = _corner_mod.predict_corners

_settle_mod = importlib.import_module('21_auto_settle')
_fuzzy_match = _settle_mod._fuzzy_match

DB_PATH = DB_ENGINE_URL.replace('sqlite:///', '')
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

print("预加载xG/射正/角球缓存...")
preload_xg_caches()

# ── 1. 加载ground truth(角球终值) ──────────────────────────────────────────
cur.execute("SELECT home_team, away_team, total_corners, match_date FROM corner_stats_final")
final_rows = cur.fetchall()
cur.execute("""
    SELECT home_team, away_team, total_corners, fetch_date FROM corner_live_odds
    -- Bug修复(2026-08-11)：0 会漏过 IS NOT NULL。500.com 对没有技术统计的比赛
    -- 照样渲染成 "0 角球 0"，历史上写进730条假0(占该来源83%)，当ground truth
    -- 用会把回测结论整体推向"小球该赢"。足球全场零角球实际不存在。
    WHERE total_corners IS NOT NULL AND total_corners > 0
    -- Bug修复(2026-08-11)：排除 scoremer 来源。33号解析器里 heh/haa/rcn
    -- 三个字段的含义是注释自认的"文档推断"，从未验证，实测全错：
    --   * status 其实是比赛分钟数(1-121)，不是状态码，原 status_map 映射错误
    --   * 1691行里 701 行是 NS(比赛根本没开踢)却存着角球数
    --   * heh+haa != rcn 占 1679/1691 = 99.3%，rcn 不是两队角球之和
    --   * 571 行 total_corners > 30(最高937)，单场不可能
    -- 无法区分哪些值碰巧是对的，且该源已被403封锁不再更新，整体排除。
    AND source <> 'scoremer'
""")
live_rows = cur.fetchall()
print(f"ground truth: corner_stats_final={len(final_rows)}场  corner_live_odds兜底={len(live_rows)}场")


def _ground_truth(home, away, fd):
    for lh, la, total_c, match_date in final_rows:
        if fd and match_date:
            try:
                if abs((datetime.strptime(match_date, "%Y-%m-%d") - datetime.strptime(fd, "%Y-%m-%d")).days) > 1:
                    continue
            except ValueError:
                pass
        if _fuzzy_match(home, away, lh, la):
            return total_c, "corner_stats_final"
    best = None
    for lh, la, total_c, live_fd in live_rows:
        if fd and live_fd:
            try:
                if abs((datetime.strptime(live_fd, "%Y-%m-%d") - datetime.strptime(fd, "%Y-%m-%d")).days) > 1:
                    continue
            except ValueError:
                pass
        if not _fuzzy_match(home, away, lh, la):
            continue
        if best is None or total_c > best:
            best = total_c
    if best is not None:
        return best, "corner_live_odds"
    return None, None


# ── 2. 历史角球盘口候选(主盘口only) ──────────────────────────────────────────
cur.execute("""
    SELECT league_name, home_team, away_team, kickoff_utc, fetch_date, line,
           MAX(CASE WHEN side='over' THEN price_dec END) as over_price,
           MAX(CASE WHEN side='under' THEN price_dec END) as under_price
    FROM pinnacle_corner_odds
    WHERE market_type='total' AND period=0 AND is_alternate=0
    GROUP BY league_name, home_team, away_team, kickoff_utc, fetch_date, line
    HAVING over_price IS NOT NULL AND under_price IS NOT NULL
""")
candidates = cur.fetchall()
print(f"候选历史角球盘口: {len(candidates)} 条(联赛+对阵+盘口线唯一)")

now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
written = {"win": 0, "lose": 0, "push": 0, "skipped_gate": 0, "no_ground_truth": 0}
t0 = time.time()
_gt_cache: dict = {}

for i, (league, home, away, kickoff, fd, line, over_p, under_p) in enumerate(candidates):
    gt_key = (home, away, fd)
    if gt_key not in _gt_cache:
        _gt_cache[gt_key] = _ground_truth(home, away, fd)
    total_corners, gt_src = _gt_cache[gt_key]
    if total_corners is None:
        written["no_ground_truth"] += 1
        continue

    try:
        pc = predict_corners(home, away, league_name=league)
    except Exception:
        pc = None
    # predict_corners()只固定输出[8.5,9.5,10.5,11.5,12.5]这5条线的over_X_Y概率，不支持
    # 任意线。真实历史盘口line不精确落在这5条线上时，不拿别的线兜底凑数(混用不同线的
    # 概率去settle这一行的真实赔率，会重演"P_book/P_poisson对不上真实线"那个bug)，
    # 直接跳过existing-model分量对比，只让FotMob信号本身(line-aware)参与，不融合。
    p_model_over = pc.get(f"over_{str(line).replace('.', '_')}") if isinstance(pc, dict) else None
    if p_model_over is None:
        continue

    fm_p = get_fotmob_corner_probs(home, away, league, line=line)
    if not fm_p:
        continue

    for direction, odds_val, p_over_side in (("over", over_p, p_model_over),
                                              ("under", under_p, 1 - p_model_over)):
        fm_side_p = fm_p.get(direction)
        if fm_side_p is None or not odds_val or odds_val <= 1:
            continue
        blended = 0.85 * p_over_side + 0.15 * fm_side_p
        if blended < 0.50:
            continue
        raw_k = (blended * odds_val - 1) / (odds_val - 1)
        raw_k = max(0.0, min(raw_k * KELLY_FRACTION, KELLY_MAX_RATIO))
        if raw_k <= 0:
            written["skipped_gate"] += 1
            continue
        if direction == "over":
            result = "win" if total_corners > line else ("lose" if total_corners < line else "push")
        else:
            result = "win" if total_corners < line else ("lose" if total_corners > line else "push")
        profit = (odds_val - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
        try:
            uid_synth = f"corner_bt_{league}_{home}_{away}_{line}"
            cur.execute("""
                INSERT OR IGNORE INTO shadow_recommendations
                (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                 shadow_type, market, outcome, handicap, best_odds, model_prob,
                 kelly_fraction, hit_score, predicted_score, fetch_date, created_at,
                 status, profit_loss)
                VALUES (?,'football',?,?,?,?, 'fotmob_corner','corner_ou',?,?,?,?,?,?,?,?,?, ?,?)
            """, (uid_synth, league, home, away, kickoff,
                  f"corner_{direction}", line, round(odds_val, 4), round(blended, 4),
                  round(raw_k, 4), round(blended, 4), "-", fd, now_iso,
                  result, round(profit, 4)))
            written[result] += 1
        except Exception as e:
            print(f"  写入异常 {home}/{away}/{direction}: {e}")

    if (i + 1) % 200 == 0:
        conn.commit()
        print(f"  进度 {i+1}/{len(candidates)}  耗时{time.time()-t0:.0f}s")

conn.commit()
print(f"\n完成，总耗时 {time.time()-t0:.0f}s")
print(f"写入: win={written['win']} lose={written['lose']} push={written['push']}  "
      f"未过滤门槛跳过={written['skipped_gate']}  无角球终值跳过={written['no_ground_truth']}")

cur.execute("""
    SELECT status, best_odds FROM shadow_recommendations
    WHERE shadow_type='fotmob_corner' AND status IN ('win','lose')
""")
rows = cur.fetchall()
n = len(rows)
if n == 0:
    print("fotmob_corner: 无已结算样本")
else:
    pnl = sum((r[1] - 1.0) if r[0] == 'win' else -1.0 for r in rows)
    print(f"【fotmob_corner 累计回测结果】 n={n}  胜率={sum(1 for r in rows if r[0]=='win')/n:.1%}  "
          f"平注ROI={pnl/n:+.1%}")

conn.close()
