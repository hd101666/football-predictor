# -*- coding: utf-8 -*-
"""
_backtest_totals_over.py — 大小球(total/team_total)"大球"推荐命中率/ROI回测

直接用 hit_recommendations 里已经过 21_auto_settle.py 结算好的真实 status/best_odds，
不重新模拟赔率或概率（那些是生产时real-time算好的，本身没有look-ahead问题——
look-ahead风险只发生在"重新计算历史概率"时，这里不重算，只统计结算结果）。

已知数据质量问题（审查代码时发现，本脚本会分别报告，不悄悄纳入干净统计）：
1. status 词表不统一：21_auto_settle.py/16_flashscore_results_scraper.py 写 'lose'，
   但库里还存在 'loss' 拼法（来源未定位，疑似人工/一次性脚本），20_clv_roi_monitor.py
   只认 'loss' 从未统计到真正的'lose'。本脚本统一把 'lose'+'loss' 都算输。
2. 21_auto_settle.py 的 _settle_result() 对 market=='total' handicap为NULL时默认按2.5线
   （market=='team_total' 默认1.5线），这两个默认值只对足球合理，篮球用这个默认线结算
   出来的win/lose是噪声（几乎恒定"大球=赢/小球=输"，与真实比分无关）。本脚本单独标出
   这批"handicap IS NULL"的行，干净统计里剔除。

用法: python -X utf8 _backtest_totals_over.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL

engine = create_engine(DB_ENGINE_URL, connect_args={"timeout": 60})

_FOOTBALL = ("football", "soccer")
_BASKETBALL = ("basketball", "basket")

LOSE_STATUSES = ("lose", "loss")
WIN_STATUSES = ("win",)


def _sport_bucket(sport_code: str) -> str:
    sc = (sport_code or "").lower()
    if sc in _FOOTBALL:
        return "football"
    if sc in _BASKETBALL:
        return "basketball"
    return sc or "unknown"


def _stats(rows, label):
    """rows: list of (status, best_odds, handicap)"""
    n_win = sum(1 for st, _, _ in rows if st in WIN_STATUSES)
    n_lose = sum(1 for st, _, _ in rows if st in LOSE_STATUSES)
    n_push = sum(1 for st, _, _ in rows if st in ("push", "void"))
    n_pending = sum(1 for st, _, _ in rows if st not in WIN_STATUSES
                     and st not in LOSE_STATUSES and st not in ("push", "void"))
    n_settled = n_win + n_lose
    profit = sum((o - 1.0) for st, o, _ in rows if st in WIN_STATUSES and o) \
             - n_lose
    win_rate = n_win / n_settled * 100 if n_settled else 0.0
    roi = profit / n_settled * 100 if n_settled else 0.0
    avg_odds = (sum(o for st, o, _ in rows if st in WIN_STATUSES and o) / n_win) if n_win else 0.0
    print(f"  {label:<28} n_settled={n_settled:>4} (win={n_win:>3} lose={n_lose:>3}) "
          f"win_rate={win_rate:>5.1f}%  flat_ROI={roi:>+7.1f}%  avg_win_odds={avg_odds:.2f}  "
          f"push/void={n_push}  pending={n_pending}")
    return {"n_settled": n_settled, "win_rate": win_rate, "roi": roi, "n_win": n_win, "n_lose": n_lose}


def main():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT market, outcome, sport_code, status, best_odds, handicap, fetch_date
            FROM hit_recommendations
            WHERE market IN ('total', 'team_total')
        """)).fetchall()

    print("=" * 100)
    print(f"  大小球(total/team_total)推荐回测 — 样本总数: {len(rows)}")
    print("=" * 100)

    for outcome in ("over", "under"):
        print(f"\n── outcome = {outcome} ──")
        for market in ("total", "team_total"):
            sub = [r for r in rows if r[0] == market and r[1] == outcome]
            if not sub:
                continue
            clean = [(st, o, hc) for _, _, sp, st, o, hc, fd in sub if hc is not None]
            dirty = [(st, o, hc) for _, _, sp, st, o, hc, fd in sub if hc is None]
            for bucket in ("football", "basketball"):
                b_clean = [(st, o, hc) for mk, oc, sp, st, o, hc, fd in sub
                           if hc is not None and _sport_bucket(sp) == bucket]
                if b_clean:
                    _stats(b_clean, f"{market}/{outcome}/{bucket}(有盘口线)")
            if dirty:
                _stats(dirty, f"{market}/{outcome}/ALL(handicap=NULL,污染样本)")

    # 按修复节点分段：total_line/team_total_line 真实盘口线修复上线于 2026-07-06
    print("\n" + "=" * 100)
    print("  分段对比：P_book/P_poisson 盘口线错位修复前后（修复日 2026-07-06）")
    print("=" * 100)
    for market in ("total",):
        for bucket_sports, bucket_name in ((_FOOTBALL, "football"), (_BASKETBALL, "basketball")):
            before = [(st, o, hc) for mk, oc, sp, st, o, hc, fd in rows
                      if mk == market and oc == "over" and hc is not None
                      and (sp or "").lower() in bucket_sports and fd < "2026-07-06"]
            after = [(st, o, hc) for mk, oc, sp, st, o, hc, fd in rows
                     if mk == market and oc == "over" and hc is not None
                     and (sp or "").lower() in bucket_sports and fd >= "2026-07-06"]
            if before:
                _stats(before, f"{market}/over/{bucket_name}/fetch_date<0706")
            if after:
                _stats(after, f"{market}/over/{bucket_name}/fetch_date>=0706")

    # market='totals'（复数，fd_b365补充源，因MARKET_BIAS key不匹配几乎全被拦截）——
    # 单独看它在 consensus_odds 阶段的潜在样本量 vs 实际进入 hit_recommendations 的样本量
    print("\n" + "=" * 100)
    print("  market='totals'(拼写不一致导致MARKET_BIAS匹配不到，几乎全部丢失)覆盖损失")
    print("=" * 100)
    with engine.connect() as conn:
        co_totals = conn.execute(text("""
            SELECT COUNT(*) FROM consensus_odds WHERE market = 'totals'
        """)).fetchone()[0]
        hr_totals = conn.execute(text("""
            SELECT COUNT(*) FROM hit_recommendations WHERE market = 'totals'
        """)).fetchone()[0]
    print(f"  consensus_odds 候选行数(market='totals'): {co_totals}")
    print(f"  实际进入 hit_recommendations 的行数:        {hr_totals}")
    print(f"  → {co_totals - hr_totals} 行候选因 market 拼写跟 MARKET_BIAS 表 key 不一致，"
          f"hit_score 被强制归零，从未有机会成为推荐（不代表这些都是好单，只是完全没有被打分评估过）")


if __name__ == "__main__":
    main()
