# -*- coding: utf-8 -*-
"""
命中系统投注推荐单 - 全中文输出版
基于 Kelly 分数分级分配，控制日总暴露风险
"""
import sqlite3
from datetime import datetime, timezone, timedelta
import sys
import pandas as pd
import os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BANKROLL = 200.0
BASE_PCT  = 0.02
MAX_DAILY_PCT = 0.25
DAILY_LIMIT = 10
MIN_HIT_SCORE = 0.45

TIERS = [
    ("S 稳胆", 0.75, 1.50, 0.030, "SSSSS"),
    ("A 高优", 0.65, 1.20, 0.024, "SSSS"),
    ("B 优选", 0.55, 1.00, 0.020, "SSS"),
    ("C 观察", 0.45, 0.75, 0.015, "SS"),
]

# ═══════════════════════════════════════════
# 全中文翻译映射表
# ═══════════════════════════════════════════

LEAGUE_CN = {
    # 足球
    "International - Friendlies": "国际友谊赛",
    "Brazil - Copa Do Nordeste": "巴西东北杯",
    "Italy - Serie C": "意大利丙级联赛",
    "Italy - Serie A": "意大利甲级联赛",
    "Italy - Serie B": "意大利乙级联赛",
    "England - Premier League": "英格兰超级联赛",
    "England - Championship": "英格兰冠军联赛",
    "Germany - Bundesliga": "德国甲级联赛",
    "Germany - 2. Bundesliga": "德国乙级联赛",
    "Spain - La Liga": "西班牙甲级联赛",
    "France - Ligue 1": "法国甲级联赛",
    "Netherlands - Eredivisie": "荷兰甲级联赛",
    "Portugal - Primeira Liga": "葡萄牙超级联赛",
    "Turkey - Super Lig": "土耳其超级联赛",
    "Denmark - Superliga": "丹麦超级联赛",
    "Sweden - Allsvenskan": "瑞典超级联赛",
    "Norway - Eliteserien": "挪威超级联赛",
    "Korea Republic - K League 1": "韩国K1联赛",
    "Japan - J1 League": "日本J1联赛",
    "Australia - A-League": "澳大利亚A联赛",
    "USA - MLS": "美国职业大联盟",
    "Argentina - Liga Profesional": "阿根廷职业联赛",
    "Mexico - Liga MX": "墨西哥超级联赛",
    "Poland - Ekstraklasa": "波兰超级联赛",
    "Austria - Bundesliga": "奥地利甲级联赛",
    "Switzerland - Super League": "瑞士超级联赛",
    "Belgium - Pro League": "比利时甲级联赛",
    "Scotland - Premiership": "苏格兰超级联赛",
    "Greece - Super League": "希腊超级联赛",
    "Czech Republic - First League": "捷克甲级联赛",
    "Croatia - HNL": "克罗地亚甲级联赛",
    "Serbia - Super Liga": "塞尔维亚超级联赛",
    "Romania - Liga I": "罗马尼亚甲级联赛",
    "Bulgaria - First League": "保加利亚甲级联赛",
    "UEFA - Nations League": "欧洲国家联赛",
    "UEFA - European Championship": "欧洲杯",
    "FIFA - World Cup": "世界杯",
    "England - FA Cup": "英格兰足总杯",
    "UEFA - Champions League": "欧洲冠军联赛",
    "UEFA - Europa League": "欧罗巴联赛",
    # 篮球
    "China - CBA": "中国 CBA",
    "Czech Republic - NBL": "捷克 NBL",
    "Turkey - Super League": "土耳其超级联赛",
    "Israel - Premier League": "以色列超级联赛",
    "Puerto Rico - Superior Nacional": "波多黎各 BSN",
    "Spain - Liga ACB": "西班牙 ACB 联赛",
    "Spain - ACB": "西班牙 ACB 联赛",
    "Australia - NBL": "澳大利亚 NBL",
    "France - LNB Pro A": "法国 LNB Pro A",
    "Germany - BBL": "德国 BBL",
    "Greece - A1 Ethniki": "希腊 A1 联赛",
    "Italy - Lega A": "意大利 Lega A",
    "Lithuania - LKL": "立陶宛 LKL",
    "NBA": "NBA",
    "WNBA": "WNBA",
    "Philippines - PBA": "菲律宾 PBA",
    "Japan - B.League": "日本 B 联赛",
    "Korea Republic - KBL": "韩国 KBL",
    "Euroleague": "欧洲篮球联赛",
    "Eurocup": "欧洲杯篮球",
}

TEAM_CN = {
    # 足球 - 国际
    "Croatia": "克罗地亚",
    "Belgium": "比利时",
    "Wales": "威尔士",
    "Ghana": "加纳",
    "Georgia": "格鲁吉亚",
    "Romania": "罗马尼亚",
    "Fortaleza": "福塔雷萨",
    "Vitoria": "维多利亚",
    "Brescia": "布雷西亚",
    "Ascoli": "阿斯科利",
    # 篮球
    "Basketball Nymburk": "宁布尔克",
    "BK Pardubice": "帕尔杜比采",
    "Mets de Guaynabo": "瓜伊纳沃大都会",
    "Leones de Ponce": "庞塞狮子",
    "Besiktas JK": "贝西克塔斯",
    "Bahcesehir Koleji": "巴赫切希尔学院",
    "Zhejiang Guangsha Lions": "浙江广厦猛狮",
    "Shanghai Sharks": "上海大鲨鱼",
    "Ironi Ness Ziona": "内斯锡安纳",
    "Maccabi Raanana": "马卡比拉阿纳纳",
    "Real Madrid": "皇家马德里",
    "Barcelona": "巴塞罗那",
    "Murcia": "穆尔西亚天主大学",
    "Tenerife": "特内里费",
}

MARKET_CN = {
    "h2h": "胜平负",
    "spread": "让分",
    "totals": "大小球",
    "total": "大小球",
}

OUTCOME_CN = {
    "home": {"h2h": "主胜", "spread": "主队", "totals": "大球", "total": "大球"},
    "away": {"h2h": "客胜", "spread": "客队", "totals": "小球", "total": "小球"},
    "over": {"total": "大球", "totals": "大球", "h2h": "大球", "spread": "大球"},
    "under": {"total": "小球", "totals": "小球", "h2h": "小球", "spread": "小球"},
    "draw": {"h2h": "平局", "spread": "平局"},
    "home -8.5": "主队 -8.5",
}

def translate_outcome(market, outcome, handicap, sport):
    """翻译投注方向为中文"""
    mkt_cn = MARKET_CN.get(market, market)
    
    # 带让分的组合方向
    if outcome == "home":
        if handicap is not None and handicap != 0:
            h_str = f"{handicap:+.1f}" if isinstance(handicap, float) else f"{handicap}"
            return f"主队 {h_str}"
        return OUTCOME_CN.get(outcome, {}).get(market, "主队")
    elif outcome == "away":
        if handicap is not None and handicap != 0:
            h_str = f"{handicap:+.1f}" if isinstance(handicap, float) else f"{handicap}"
            return f"客队 {h_str}"
        return OUTCOME_CN.get(outcome, {}).get(market, "客队")
    elif outcome == "over":
        h_str = ""
        if handicap is not None and handicap != 0:
            h_str = f" {handicap}"
        if sport == "basketball":
            return f"大分{h_str}"
        return f"大球{h_str}"
    elif outcome == "under":
        h_str = ""
        if handicap is not None and handicap != 0:
            h_str = f" {handicap}"
        if sport == "basketball":
            return f"小分{h_str}"
        return f"小球{h_str}"
    else:
        return str(outcome)

def get_tier(hit_score):
    if hit_score is None:
        return TIERS[-1]
    for name, threshold, kelly_mult, pct, stars in TIERS:
        if hit_score >= threshold:
            return (name, threshold, kelly_mult, pct, stars)
    return TIERS[-1]

def calc_allocation(hit_score, kelly_fraction):
    tier_name, _, kelly_mult, base_pct, stars = get_tier(hit_score)
    kf = kelly_fraction if kelly_fraction and kelly_fraction > 0 else 1.0
    if kf >= 1.0:
        adj = 1.2
    elif kf >= 0.5:
        adj = 0.8 + (kf - 0.5) * 0.8
    else:
        adj = 0.8
    actual_pct = round(base_pct * adj, 4)
    actual_pct = min(actual_pct, 0.05)
    amount = round(BANKROLL * actual_pct, 1)
    amount = max(amount, 2)
    return tier_name, stars, actual_pct, amount

# ── 查询数据 ──
conn = sqlite3.connect(r'F:\qqsj\data\sports_data.db')
c = conn.cursor()

bjtz = timezone(timedelta(hours=8))
bj_now = datetime.now(bjtz)
today_str = bj_now.strftime("%Y-%m-%d")
weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
weekday = weekday_names[bj_now.weekday()]

c.execute("""
    SELECT sport_code, league_name, home_team, away_team, 
           kickoff_utc, market, outcome, best_odds, best_source, 
           model_prob, implied_prob, value_edge, kelly_fraction, 
           hit_score, confidence, reason, handicap
    FROM hit_recommendations
    WHERE date(created_at) = date('now', '+8 hours')
      AND status = 'pending'
      AND (formula_version = 'v1' OR formula_version IS NULL)
      AND hit_score >= ?
    ORDER BY hit_score DESC
    LIMIT ?
""", (MIN_HIT_SCORE, DAILY_LIMIT))
rows = c.fetchall()

# ── D级过滤：读取prediction_snapshot，排除无真实赔率的比赛 ──
c.execute("""
    SELECT DISTINCT home_team_name_std, away_team_name_std
    FROM prediction_snapshot
    WHERE match_date = ?
      AND confidence_grade LIKE 'D%'
""", (today_str,))
d_grade_pairs = set((r[0].strip() if r[0] else '', r[1].strip() if r[1] else '') for r in c.fetchall())

# ── 生成投注单 ──
lines = []
lines.append("=" * 58)
lines.append("  🏆 命中系统投注推荐单")
lines.append("  日期: %s (%s)" % (today_str, weekday))
lines.append("  生成: %s 北京时间" % bj_now.strftime("%Y-%m-%d %H:%M:%S"))
lines.append("  本金: %.0f元 | 日限: %d注 | 门槛: 命中分≥%.2f" % (BANKROLL, DAILY_LIMIT, MIN_HIT_SCORE))
lines.append("  资金分配: S级3%% | A级2.4%% | B级2%% | C级1.5%% | 日总上限%.0f%%" % (MAX_DAILY_PCT * 100))
lines.append("=" * 58)
lines.append("")

if not rows:
    lines.append("  本期无推荐 (命中分未达门槛)")
    lines.append("")
else:
    total_pct = 0.0
    total_amount = 0.0
    tier_counts = {"S 稳胆": 0, "A 高优": 0, "B 优选": 0, "C 观察": 0}

    for i, r in enumerate(rows, 1):
        sport, league, home, away, kickoff, market, outcome, odds, source, \
        model_prob, implied_prob, value_edge, kelly_frac, hit_score, confidence, reason, handicap = r

        # 跳过D级（无真实赔率）的比赛
        h_strip = home.strip() if home else ''
        a_strip = away.strip() if away else ''
        if (h_strip, a_strip) in d_grade_pairs:
            continue

        tier_name, stars, alloc_pct, alloc_amt = calc_allocation(hit_score, kelly_frac)
        total_pct += alloc_pct
        total_amount += alloc_amt

        if kickoff:
            try:
                dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                kickoff_bj = dt.astimezone(bjtz).strftime("%m/%d %H:%M")
            except:
                kickoff_bj = str(kickoff)
        else:
            kickoff_bj = "N/A"

        # ── 中文翻译 ──
        league_cn = LEAGUE_CN.get(league, league)
        home_cn = TEAM_CN.get(home, home)
        away_cn = TEAM_CN.get(away, away)
        market_cn = MARKET_CN.get(market, market)
        direction_cn = translate_outcome(market, outcome, handicap, sport)

        sport_icon = "⚽" if sport == "soccer" else "🏀"
        lines.append("  [%d] %s %s %s" % (i, stars, tier_name, sport_icon))
        lines.append("  联赛: %s" % league_cn)
        lines.append("  对阵: %s（主）vs %s（客）" % (home_cn, away_cn))
        lines.append("  开赛: %s 北京时间" % kickoff_bj)
        lines.append("  玩法: %s → %s" % (market_cn, direction_cn))
        lines.append("  赔率: %s (%s)" % (odds, source))
        if model_prob:
            lines.append("  模型概率: %.1f%%" % (model_prob * 100))
        if hit_score:
            lines.append("  命中分: %.3f" % hit_score)
        if value_edge:
            lines.append("  价值差: +%.1f%%" % (value_edge * 100))

        lines.append("  ─── 资金分配 ───")
        lines.append("  占本金: %.1f%% (%.0f元)" % (alloc_pct * 100, alloc_amt))
        if alloc_amt > 0 and odds:
            potential = round(alloc_amt * float(odds) - alloc_amt, 1)
            lines.append("  预期收益: +%.1f元 (赔率%.2f)" % (potential, float(odds)))

        if reason:
            lines.append("  分析: %s" % reason)
        lines.append("")

    # ── 串关推荐 ──
    parlay_path = r"F:\qqsj\data\parlay_best.xlsx"
    if os.path.exists(parlay_path):
        try:
            parlay_df = pd.read_excel(parlay_path)
            # 去重，只保留每个match_list的最优（最高combo_kelly）
            parlay_df = parlay_df.sort_values("combo_kelly", ascending=False)
            parlay_df = parlay_df.drop_duplicates(subset=["match_list"], keep="first")
            # 看2串1和3串1
            top_parlays = parlay_df[parlay_df["combo_len"].isin([2, 3])].head(5)

            if len(top_parlays) > 0:
                lines.append("=" * 58)
                lines.append("  🔗 串关推荐（2串1 / 3串1）")
                lines.append("=" * 58)
                lines.append("")
                for pi, pr in top_parlays.iterrows():
                    clen = int(pr["combo_len"])
                    match_list = str(pr["match_list"])
                    total_odds = pr["total_odds"]
                    total_prob = pr["total_prob"]
                    combo_kelly = pr["combo_kelly"]

                    # 拆分各场
                    legs = [m.strip() for m in match_list.split("+")]

                    # 星级
                    if combo_kelly >= 0.15:
                        pstars = "⭐⭐⭐⭐"
                        plevel = "高优"
                    elif combo_kelly >= 0.08:
                        pstars = "⭐⭐⭐"
                        plevel = "优选"
                    else:
                        pstars = "⭐⭐"
                        plevel = "观察"

                    # 串关资金=单场总和的50%（控制在安全范围）
                    parlay_bet = round(min(total_amount * 0.3, BANKROLL * 0.03))
                    parlay_bet = max(parlay_bet, 2)

                    lines.append(f"  [P{pi+1}] {pstars} {clen}串1 {plevel}")
                    for li, leg in enumerate(legs, 1):
                        lines.append(f"    第{li}场: {leg}")
                    lines.append(f"  综合赔率: {total_odds:.2f} | 联合概率: {total_prob*100:.1f}%")
                    lines.append(f"  凯利值: {combo_kelly:.4f}")
                    lines.append(f"  建议投注: {parlay_bet}元")
                    lines.append("")
        except Exception as e:
            lines.append(f"  ⚠️ 串关数据读取失败: {e}")
            lines.append("")

    # ── 汇总 ──
    lines.append("=" * 58)
    lines.append("  💰 资金分配汇总")
    lines.append("  " + "-" * 40)
    lines.append("  推荐数: %d 条" % len(rows))

    tier_stats = {}
    for r in rows:
        hs = r[13]
        kf = r[12]
        tn2, _, ap2, am2 = calc_allocation(hs, kf)
        if tn2 not in tier_stats:
            tier_stats[tn2] = {"count": 0, "pct": 0.0, "amt": 0.0}
        tier_stats[tn2]["count"] += 1
        tier_stats[tn2]["pct"] += ap2
        tier_stats[tn2]["amt"] += am2

    for tier_def in TIERS:
        tn = tier_def[0]
        if tn in tier_stats:
            s = tier_stats[tn]
            lines.append("  %s: %d条 | 占本金%.1f%% (%.0f元)" % (tn, s["count"], s["pct"]*100, s["amt"]))

    lines.append("  " + "-" * 40)
    lines.append("  日总分配: %.1f%% (%.0f元 / %.0f元本金)" % (total_pct*100, total_amount, BANKROLL))

    if total_pct > MAX_DAILY_PCT:
        lines.append("  ⚠️  超过日总上限%.0f%%！建议减注或跳过低级别推荐" % (MAX_DAILY_PCT * 100))
    else:
        lines.append("  ✅ 未超日总上限%.0f%%" % (MAX_DAILY_PCT * 100))

    remaining_pct = round(1.0 - total_pct, 4)
    lines.append("  剩余可用: %.1f%% (%.0f元)" % (max(remaining_pct, 0)*100, max(BANKROLL - total_amount, 0)))
    lines.append("=" * 58)
    lines.append("")
    lines.append("  ⚠️ 风险提示")
    lines.append("  • 以上为模型推荐，不构成投资建议")
    lines.append("  • 建议单注不超过本金3%，日总不超过25%")
    lines.append("  • Kelly公式: f* = (bp - q) / b，已按分级缩放")
    lines.append("=" * 58)

content = "\n".join(lines)

import os as _os_exp
_os_exp.makedirs(r"D:\lucky", exist_ok=True)
desktop = r"D:\lucky\bet_slip_%s.txt" % today_str
with open(desktop, "w", encoding="utf-8") as f:
    f.write(content)
print("OK -> %s" % desktop)
print("===CONTENT_START===")
print(content)
print("===CONTENT_END===")

conn.close()
