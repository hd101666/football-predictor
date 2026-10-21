# -*- coding: utf-8 -*-
# _backtest_draw_threshold.py — 用fd_matches历史真实盘口+真实赛果回测足球1x2平局门槛
# 复用生产环境同一套 get_model_probs() 融合公式(book50%+泊松30%+ELO20%)，
# 对近2个赛季约2万场真实比赛扫描不同(概率门槛×价值边际门槛)组合的命中率/ROI，
# 用真实数据校准 00_命中系统.py 里 _min_prob_gate / value_edge 阈值，而非人工猜测。
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import env_setup
from config import DB_ENGINE_URL

import importlib
_sys_mod = importlib.import_module('00_命中系统')
get_model_probs = _sys_mod.get_model_probs

DB_PATH = DB_ENGINE_URL.replace('sqlite:///', '')

conn = sqlite3.connect(DB_PATH, timeout=5)
cur = conn.cursor()
cur.execute("""
    SELECT home_team, away_team, league_name, psh, psd, psa, ftr, match_date
    FROM fd_matches
    WHERE psd IS NOT NULL AND psh IS NOT NULL AND psa IS NOT NULL
      AND ftr IS NOT NULL AND match_date >= '2024-07-01'
    ORDER BY match_date
""")
all_rows = cur.fetchall()
# 实测 get_model_probs() 单次约0.7s（team lookup无法进一步缓存），2万场要4小时不现实，
# 按固定步长抽样~3000场，保留时间/联赛分布代表性，牺牲部分精度换可行的运行时间
STRIDE = max(1, len(all_rows) // 3000)
rows = all_rows[::STRIDE]
print(f"样本总数: {len(all_rows)}  抽样步长: {STRIDE}  实际回测样本: {len(rows)}")

t0 = time.time()
results = []  # (fused_draw_prob, value_edge, odds, hit)
for i, (home, away, league, psh, psd, psa, ftr, mdate) in enumerate(rows):
    try:
        bp = {'home': 1.0 / psh, 'draw': 1.0 / psd, 'away': 1.0 / psa}
        probs = get_model_probs('bt', home, away, league, 'football', book_probs=bp)
        fused = probs.get('draw')
        if fused is None:
            continue
        implied = bp['draw']
        # value_edge 定义对齐 compute_hit_score 里常见口径：model_prob*odds - 1
        edge = fused * psd - 1.0
        hit = (ftr == 'D')
        results.append((fused, edge, psd, hit))
    except Exception:
        continue
    if (i + 1) % 300 == 0:
        elapsed = time.time() - t0
        print(f"  进度 {i+1}/{len(rows)}  耗时{elapsed:.0f}s")

print(f"\n有效样本: {len(results)}  总耗时 {time.time()-t0:.0f}s\n")

# ── 阈值扫描 ──────────────────────────────────────────────────────────────
prob_grid = [0.20, 0.22, 0.25, 0.28, 0.30, 0.33]
edge_grid = [-0.05, 0.0, 0.03, 0.05, 0.08, 0.10]

print(f"{'prob>=':<8}{'edge>=':<8}{'样本数':<8}{'命中率':<10}{'平注ROI':<10}")
print("-" * 50)
for pth in prob_grid:
    for eth in edge_grid:
        sub = [r for r in results if r[0] >= pth and r[1] >= eth]
        n = len(sub)
        if n < 30:
            continue
        hits = sum(1 for r in sub if r[3])
        hit_rate = hits / n
        # 平注ROI：每注1单位，赢了净赚(odds-1)，输了净亏1
        pnl = sum((r[2] - 1.0) if r[3] else -1.0 for r in sub)
        roi = pnl / n
        print(f"{pth:<8.2f}{eth:<8.2f}{n:<8}{hit_rate*100:<9.1f}%{roi*100:>+9.1f}%")

conn.close()
