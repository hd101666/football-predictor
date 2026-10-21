#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日推荐/观察单·逐场推荐理由+冷门原因（Excel版，2026-09-03按用户要求新建）
================================================================
跟 settle_match_detail_xlsx.py 同一套翻译/格式化基础设施（_translate_slip_zh.py的
Translator + settle_match_detail_zh.py的direction_zh/market_label_zh/bucket_stats），
但这份表针对的是"今日尚未开赛"的推荐/观察候选（没有实际赛果可比对），核心新增两列：
  - 推荐理由：赔率隐含概率 vs 模型融合概率(p_fusion)的edge + 该市场历史累计命中率/ROI
  - 冷门原因：仅当推荐方向是市场相对不看好的一侧(隐含概率<45%)时才标注，说明edge幅度；
    不编造伤停/状态等无法从当前字段验证的具体causal叙事

用法：
  python -X utf8 predict_reasoning_xlsx.py --date 2026-09-03 [--out D:\\lucky\\xxx.xlsx]
"""
import sys, os, sqlite3, argparse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE_DIR)
DB_PATH = os.path.join(_BASE_DIR, "data", "sports_data.db")

import _translate_slip_zh as tsz
from settle_match_detail_zh import direction_zh, market_label_zh, bucket_stats, bj_time

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
FORMAL_FILL = PatternFill("solid", fgColor="C6E0B4")  # 正式推荐单用绿色区分
HEADER_FONT = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top", horizontal="left")

HEADERS = ["开赛时间", "联赛", "主队VS客队", "推荐玩法", "推荐方向", "赔率",
           "隐含概率", "模型p融合", "Edge", "命中分", "推荐理由", "冷门原因", "该市场历史表现"]

UNDERDOG_IMPLIED_THRESHOLD = 0.45  # 隐含概率低于此值才可能被标"冷门"


def safe_sheet_name(name: str) -> str:
    for ch in '[]:*?/\\':
        name = name.replace(ch, "")
    return name[:31] if len(name) > 31 else name


def build_reason(odds, model_prob, hit_score, hist_n, hist_hit_rate, hist_roi, is_formal, src=None):
    if odds is None or model_prob is None:
        return "字段缺失，无法计算edge"
    implied = 1.0 / odds if odds else None
    edge = (model_prob - implied) if implied is not None else None
    parts = []
    if implied is not None and edge is not None:
        parts.append(f"赔率{odds:.2f}隐含概率{implied:.1%}，模型融合概率{model_prob:.1%}，"
                      f"{'正' if edge >= 0 else '负'}edge{edge:+.1%}")
    if hit_score is not None:
        parts.append(f"命中分{hit_score:.3f}")
    if src:
        parts.append(f"数据源:{src}")
    if hist_n:
        parts.append(f"该市场历史已结算{hist_n}场，平注ROI{hist_roi}，命中率{hist_hit_rate}")
    else:
        parts.append("该市场历史结算样本为0，暂无累计表现可参考")
    if is_formal:
        parts.append("已过EV≥10%门槛，正式推荐(真钱)")
    else:
        parts.append("尚未通过转正门槛(显著性+近期窗口双重检验)，仅数据追踪/观察，非真钱推荐")
    return "；".join(parts)


def build_underdog_reason(odds, model_prob, outcome, handicap, home_zh, away_zh, market):
    """只有推荐方向是市场相对不看好一侧(隐含概率<45%)时才生成冷门说明；
    大小球/角球大小等不涉及胜负预期的玩法不适用冷门概念。"""
    if odds is None or model_prob is None:
        return ""
    if market in ("corner_total",) or outcome in ("over", "under", "corner_over", "corner_under"):
        return ""
    implied = 1.0 / odds if odds else None
    if implied is None or implied >= UNDERDOG_IMPLIED_THRESHOLD:
        return ""
    edge = model_prob - implied
    side_desc = ""
    if outcome == "away":
        side_desc = f"客场作战的{away_zh}"
    elif outcome == "home":
        side_desc = f"主场{home_zh}"
    elif outcome == "draw":
        side_desc = "平局"
    return (f"市场赔率{odds:.2f}隐含该方向仅{implied:.1%}获胜概率，属市场认定的相对冷门"
            f"（{side_desc or '该方向'}非市场热门）；模型融合概率{model_prob:.1%}高出隐含概率{edge:+.1%}，"
            f"edge来自赔率共识+泊松/ELO模型融合的统计偏差，不代表已核实具体伤停/状态等场外因素，"
            f"请结合该市场历史ROI自行判断是否跟注")


def historical_stats(conn, table, extra_where="", extra_params=()):
    cur = conn.execute(f"SELECT status, profit_loss FROM {table} WHERE 1=1 {extra_where}", extra_params)
    rows = cur.fetchall()
    n = sum(1 for s, _ in rows if s in ("win", "lose", "push"))
    hit_rate, roi = bucket_stats(rows)
    return n, hit_rate, roi


def write_sheet(wb, title, rows, is_formal=False):
    ws = wb.create_sheet(safe_sheet_name(title))
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = HEADER_FONT
        c.fill = FORMAL_FILL if is_formal else HEADER_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.border = BORDER
            c.alignment = WRAP
    widths = [14, 16, 24, 12, 20, 8, 9, 9, 8, 8, 46, 46, 24]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    fetch_date = args.date
    out_path = args.out or os.path.join("D:\\lucky", f"推荐理由逐场明细_{fetch_date}.xlsx")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    teams_dict, leagues_dict, outcomes_dict = tsz.load_dict()
    tr = tsz.Translator(teams_dict, leagues_dict, outcomes_dict)

    wb = Workbook()
    wb.remove(wb.active)
    index_rows = []  # (title, n, is_formal, note)

    # ── 一、正式推荐单（真钱）──────────────────────────────────────────
    seq = 1

    # 角球正式推荐
    cur.execute("""SELECT league_name, home_team, away_team, kickoff_utc, direction, line,
                          odds, p_fusion, kelly, hit_score, src
                   FROM corner_recommendations WHERE fetch_date=?""", (fetch_date,))
    corner_recs = cur.fetchall()
    if corner_recs:
        hist_n, hist_hr, hist_roi = historical_stats(conn, "corner_recommendations")
        rows = []
        for lg, hm, aw, ko, direction, line, odds, pf, kelly, hs, src in corner_recs:
            hm_zh, aw_zh = tr.team(hm), tr.team(aw)
            lg_zh = tr.league(lg) if lg else "-"
            dir_zh = direction_zh(tr, "corner_total", direction, line, hm_zh, aw_zh)
            implied = 1.0 / odds if odds else None
            edge = (pf - implied) if implied is not None else None
            reason = build_reason(odds, pf, hs, hist_n, hist_hr, hist_roi, is_formal=True, src=src)
            rows.append([bj_time(ko), lg_zh, f"{hm_zh} VS {aw_zh}", "角球大小", dir_zh,
                         round(odds, 2) if odds else None,
                         f"{implied:.1%}" if implied is not None else "-",
                         f"{pf:.3f}" if pf is not None else "-",
                         f"{edge:+.1%}" if edge is not None else "-",
                         round(hs, 3) if hs is not None else None,
                         reason, "不适用(大小球盘口，不涉及主客胜负预期)",
                         f"历史{hist_n}场 命中率{hist_hr} ROI{hist_roi}"])
        title = f"{seq:02d}_角球正式推荐单"
        write_sheet(wb, title, rows, is_formal=True)
        index_rows.append((title, len(rows), True, "真钱正式推荐"))
        seq += 1

    # 主推荐单（今天是0条，如果有数据也覆盖到）
    cur.execute("""SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
                          best_odds, model_prob, kelly_fraction, hit_score, formula_version, reason
                   FROM hit_recommendations WHERE fetch_date=?""", (fetch_date,))
    hit_recs = cur.fetchall()
    if hit_recs:
        rows = []
        for lg, hm, aw, ko, mkt, oc, hc, odds, mp, kf, hs, fver, db_reason in hit_recs:
            hist_n, hist_hr, hist_roi = historical_stats(
                conn, "hit_recommendations", "AND market=?", (mkt,))
            hm_zh, aw_zh = tr.team(hm), tr.team(aw)
            lg_zh = tr.league(lg) if lg else "-"
            mkt_zh = market_label_zh(tr, mkt)
            dir_zh = direction_zh(tr, mkt, oc, hc, hm_zh, aw_zh)
            implied = 1.0 / odds if odds else None
            if fver == "fade_manual":
                # "反着买"人工批准转正：下注方向是模型原判的反面，p_fusion这一列
                # 存的是"1-原始模型概率"的二元互补近似，不是重新拟合的模型输出，
                # 用它跟隐含概率算edge/判EV门槛没有意义(2026-09-04审查发现此前
                # 通用公式套在这类行上会算出"负edge却写着已过EV门槛"的自相矛盾
                # 文字)——直接展示DB里reason字段的真实依据(见project_fade_strategy_
                # promotion_0802记忆)，不重算edge。
                edge = None
                reason = (f"【反着买·人工批准转正，非算法验证】{db_reason}"
                          f"；命中分{hs:.3f}" if hs is not None else "")
                underdog = "不适用（反着买策略本身就是刻意反向下注模型原判的方向，"\
                           "冷门/热门框架不适用，依据见左侧推荐理由）"
            else:
                edge = (mp - implied) if implied is not None else None
                reason = build_reason(odds, mp, hs, hist_n, hist_hr, hist_roi, is_formal=True)
                underdog = build_underdog_reason(odds, mp, oc, hc, hm_zh, aw_zh, mkt) or "非冷门方向"
            rows.append([bj_time(ko), lg_zh, f"{hm_zh} VS {aw_zh}", mkt_zh, dir_zh,
                         round(odds, 2) if odds else None,
                         f"{implied:.1%}" if implied is not None else "-",
                         f"{mp:.3f}" if mp is not None else "-",
                         f"{edge:+.1%}" if edge is not None else "-",
                         round(hs, 3) if hs is not None else None,
                         reason, underdog,
                         f"历史{hist_n}场 命中率{hist_hr} ROI{hist_roi}"])
        title = f"{seq:02d}_主推荐单(独赢让球大小球)"
        write_sheet(wb, title, rows, is_formal=True)
        index_rows.append((title, len(rows), True, "真钱正式推荐"))
        seq += 1

    # ── 二、影子观察单（仅观察，非真钱）──────────────────────────────────
    for table, label, outcome_label in [("under_shadow_bets", "小球候选观察单", "under"),
                                          ("over_shadow_bets", "大球候选观察单", "over")]:
        cur.execute(f"""SELECT league_name, home_team, away_team, kickoff_utc, market, handicap,
                              best_odds, model_prob, kelly_fraction, hit_score
                       FROM {table} WHERE fetch_date=?""", (fetch_date,))
        recs = cur.fetchall()
        if not recs:
            continue
        hist_n, hist_hr, hist_roi = historical_stats(conn, table)
        rows = []
        for lg, hm, aw, ko, mkt, hc, odds, mp, kf, hs in recs:
            hm_zh, aw_zh = tr.team(hm), tr.team(aw)
            lg_zh = tr.league(lg) if lg else "-"
            mkt_zh = market_label_zh(tr, mkt)
            dir_zh = direction_zh(tr, mkt, outcome_label, hc, hm_zh, aw_zh)
            implied = 1.0 / odds if odds else None
            edge = (mp - implied) if implied is not None else None
            reason = build_reason(odds, mp, hs, hist_n, hist_hr, hist_roi, is_formal=False)
            rows.append([bj_time(ko), lg_zh, f"{hm_zh} VS {aw_zh}", mkt_zh, dir_zh,
                         round(odds, 2) if odds else None,
                         f"{implied:.1%}" if implied is not None else "-",
                         f"{mp:.3f}" if mp is not None else "-",
                         f"{edge:+.1%}" if edge is not None else "-",
                         round(hs, 3) if hs is not None else None,
                         reason, "不适用(大小球盘口，不涉及主客胜负预期)",
                         f"历史{hist_n}场 命中率{hist_hr} ROI{hist_roi}"])
        title = f"{seq:02d}_{label}"
        write_sheet(wb, title, rows)
        index_rows.append((title, len(rows), False, "影子观察，仅数据追踪"))
        seq += 1

    SHADOW_LABEL = {
        "1x2": "独赢影子观察单", "fotmob_1x2": "FotMob独赢观察单",
        "fotmob_corner": "FotMob角球观察单", "fotmob_spread": "FotMob让球观察单",
        "fotmob_team_total": "FotMob球队大小观察单", "fotmob_totals": "FotMob大小球观察单",
        "gated": "门槛拦截观察单(比分玩法等)", "htft": "半全场观察单",
        "htft_nofilter": "半全场(无联赛过滤)观察单",
        "lstm_1x2": "LSTM独赢观察单", "lstm_moneyline": "LSTM独赢(moneyline口径)观察单",
        "lstm_spread": "LSTM让球观察单", "moneyline": "独赢(moneyline口径)观察单",
        "qiety_h2h": "企鹅交锋观察单", "spread": "让球观察单", "team_total": "球队大小观察单",
    }
    cur.execute("SELECT DISTINCT shadow_type FROM shadow_recommendations WHERE fetch_date=?", (fetch_date,))
    types = sorted(r[0] for r in cur.fetchall())
    for stype in types:
        cur.execute("""SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
                              best_odds, model_prob, kelly_fraction, hit_score, unified_id
                       FROM shadow_recommendations WHERE fetch_date=? AND shadow_type=?
                       ORDER BY hit_score DESC""", (fetch_date, stype))
        recs = cur.fetchall()
        if not recs:
            continue
        hist_n, hist_hr, hist_roi = historical_stats(
            conn, "shadow_recommendations", "AND shadow_type=?", (stype,))
        rows = []
        for lg, hm, aw, ko, mkt, oc, hc, odds, mp, kf, hs, uid in recs:
            if not lg and uid:
                lg_row = cur.execute(
                    "SELECT league_name FROM unified_matches WHERE unified_id=?", (uid,)).fetchone()
                lg = lg_row[0] if lg_row else lg
            hm_zh, aw_zh = tr.team(hm), tr.team(aw)
            lg_zh = tr.league(lg) if lg else "-"
            is_corner = (stype == "fotmob_corner")
            mkt_zh = "角球大小" if is_corner else market_label_zh(tr, mkt)
            dir_zh = direction_zh(tr, "corner_total" if is_corner else mkt, oc, hc, hm_zh, aw_zh)
            implied = 1.0 / odds if odds else None
            edge = (mp - implied) if implied is not None else None
            reason = build_reason(odds, mp, hs, hist_n, hist_hr, hist_roi, is_formal=False)
            underdog = build_underdog_reason(odds, mp, oc, hc, hm_zh, aw_zh,
                                              "corner_total" if is_corner else mkt)
            rows.append([bj_time(ko), lg_zh, f"{hm_zh} VS {aw_zh}", mkt_zh, dir_zh,
                         round(odds, 2) if odds else None,
                         f"{implied:.1%}" if implied is not None else "-",
                         f"{mp:.3f}" if mp is not None else "-",
                         f"{edge:+.1%}" if edge is not None else "-",
                         round(hs, 3) if hs is not None else None,
                         reason, underdog or "非冷门方向/不适用",
                         f"历史{hist_n}场 命中率{hist_hr} ROI{hist_roi}"])
        title = f"{seq:02d}_{SHADOW_LABEL.get(stype, stype)}"
        write_sheet(wb, title, rows)
        index_rows.append((title, len(rows), False, "影子观察，仅数据追踪"))
        seq += 1

    # ── 目录汇总放最前面 ──────────────────────────────────────────────
    idx = wb.create_sheet("00_目录汇总", 0)
    idx.append(["工作表", "候选数", "是否正式推荐(真钱)", "说明"])
    for c in idx[1]:
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center")
    for title, n, is_formal, note in index_rows:
        idx.append([title, n, "是" if is_formal else "否", note])
    for row in idx.iter_rows(min_row=2, max_row=idx.max_row):
        for c in row:
            c.border = BORDER
    idx.column_dimensions["A"].width = 34
    idx.column_dimensions["B"].width = 10
    idx.column_dimensions["C"].width = 16
    idx.column_dimensions["D"].width = 26
    idx.freeze_panes = "A2"

    wb.save(out_path)
    print(f"已保存: {out_path}")
    print(f"共 {len(index_rows)} 个工作表，{sum(r[1] for r in index_rows)} 条候选")
    conn.close()


if __name__ == "__main__":
    main()
