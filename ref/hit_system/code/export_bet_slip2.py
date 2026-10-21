# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone, timedelta
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect(r'F:\qqsj\data\sports_data.db')
c = conn.cursor()

c.execute("""
    SELECT sport_code, league_name, home_team, away_team, 
           kickoff_utc, market, outcome, best_odds, best_source, 
           model_prob, implied_prob, value_edge, kelly_fraction, 
           hit_score, confidence, reason, handicap
    FROM hit_recommendations
    WHERE created_at >= '2026-06-02T01:00' AND status='pending'
      AND (formula_version = 'v1' OR formula_version IS NULL)
    ORDER BY hit_score DESC
""")
rows = c.fetchall()

lines = []
lines.append("=" * 70)
lines.append("  命中系统投注推荐单")
lines.append("  日期: 2026-06-02 (周二)")
bj_now = datetime.now(timezone(timedelta(hours=8)))
lines.append("  生成: %s 北京时间" % bj_now.strftime("%Y-%m-%d %H:%M:%S"))
lines.append("  本金: 200元 | 单注基准: 2% | 日限10注")
lines.append("  门槛: hit_score >= 0.45")
lines.append("=" * 70)
lines.append("")

if not rows:
    lines.append("  本期无推荐")
    lines.append("")
    lines.append("  注: theodds数据源盘口线异常(抓到非主盘口),")
    lines.append("  需修复 isAlternate 过滤后再重新生成")
else:
    for i, r in enumerate(rows, 1):
        sport, league, home, away, kickoff, market, outcome, odds, source, \
        model_prob, implied_prob, value_edge, kelly_frac, hit_score, confidence, reason, handicap = r

        if kickoff:
            try:
                dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                kickoff_bj = dt.astimezone(timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")
            except:
                kickoff_bj = str(kickoff)
        else:
            kickoff_bj = "N/A"

        direction = str(outcome)
        if handicap:
            direction = direction + " " + str(handicap)

        lines.append("  [%d]" % i)
        lines.append("  开赛: %s 北京时间" % kickoff_bj)
        lines.append("  联赛: %s" % league)
        lines.append("  对阵: %s vs %s" % (home, away))
        lines.append("  玩法: %s" % market)
        lines.append("  方向: %s" % direction)
        lines.append("  赔率: %s (%s)" % (odds, source))
        if model_prob:
            lines.append("  模型概率: %.1f%%" % (model_prob * 100))
        if hit_score:
            lines.append("  命中分: %.3f" % hit_score)
        if value_edge:
            lines.append("  价值差: +%.1f%%" % (value_edge * 100))

        kf = kelly_frac if kelly_frac else 1
        amt = max(2, min(round(200 * 0.02 * kf, 1), 20))
        lines.append("  建议投注: %.0f元" % amt)

        # 标注盘口线问题
        if source == "theodds" and handicap and float(handicap) < 2.0 and market == "total":
            lines.append("  !! 警告: 盘口线异常(可能非主盘口), 待确认 !!")

        if reason:
            lines.append("  分析: %s" % reason)
        lines.append("")

lines.append("=" * 70)
lines.append("  汇总")
lines.append("  推荐数: %d 条" % len(rows))
lines.append("=" * 70)

content = "\n".join(lines)

import os as _os_exp2
_os_exp2.makedirs(r"D:\lucky", exist_ok=True)
desktop = r"D:\lucky\bet_slip_2026-06-02.txt"
with open(desktop, "w", encoding="utf-8") as f:
    f.write(content)
print("OK -> %s" % desktop)
print(content)

conn.close()
