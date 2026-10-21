# -*- coding: utf-8 -*-
import sqlite3, sys, os
from datetime import datetime, timezone, timedelta
sys.stdout.reconfigure(encoding='utf-8')

BJT = timezone(timedelta(hours=8))
now_bjt = datetime.now(timezone.utc).astimezone(BJT)
date_str = now_bjt.strftime('%Y-%m-%d')
time_str = now_bjt.strftime('%H%M')

conn = sqlite3.connect('data/sports_data.db')
c = conn.cursor()
c.execute("""
SELECT league_name, home_team, away_team, kickoff_utc, market, outcome,
       best_odds, model_prob, kelly_fraction, hit_score, handicap
FROM hit_recommendations
WHERE fetch_date = '2026-06-10' AND is_filtered = 0
ORDER BY hit_score DESC
LIMIT 20
""")
recs = c.fetchall()
conn.close()

def utc_to_bjt(s):
    s = str(s).strip()
    try:
        if 'T' in s:
            dt = datetime.fromisoformat(s.replace('Z','+00:00'))
        else:
            dt = datetime.strptime(s[:16],'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        return dt.astimezone(BJT).strftime('%m月%d日%H:%M')
    except:
        return s

def fmt_play(market, outcome, handicap):
    h = '' if handicap is None else handicap
    if market == 'total':
        return f"大小球/{'大球' if outcome=='over' else '小球'}{h}"
    elif market == 'spread':
        if outcome == 'home':
            return f"让球/主胜{h}"
        else:
            return f"让球/客胜{h}"
    elif market == 'moneyline':
        if outcome == 'home': return '独赢/主胜'
        elif outcome == 'away': return '独赢/客胜'
        else: return '独赢/平局'
    return f"{market}/{outcome}"

def bet_size(hit_score, base=4):
    if hit_score >= 0.74: return base, '✅'
    elif hit_score >= 0.70: return base-1, '⬇'
    else: return base-1, '⬇'

# Top 10 for single bets
singles = recs[:10]
single_total = sum(bet_size(r[9])[0] for r in singles)

# Build lines
rows = []
for i, r in enumerate(singles):
    league, home, away, kick, market, outcome, odds, prob, kelly, score, hcap = r
    time_bjt = utc_to_bjt(kick)
    play = fmt_play(market, outcome, hcap)
    sz, mark = bet_size(score)
    rows.append((i+1, time_bjt, home, away, play, odds, prob, kelly, mark, sz, score))

# Parlay combinations using top 8（K₁/₄>0 才入串关池）
top = [(r[6], utc_to_bjt(r[3]), r[1], r[2], fmt_play(r[4],r[5],r[10])) for r in singles[:8] if r[8] > 0]
# odds, time, home, away, play

def combo_odds(idxs):
    o = 1.0
    for i in idxs: o *= top[i][0]
    return round(o, 1)

def win_amt(idxs, stake):
    return round(combo_odds(idxs)*stake - stake, 1)

# Build slip text
W = 108
sep = '─' * W
eq  = '=' * W
dbl = '═' * W

lines = []
lines.append('')
lines.append(eq)
lines.append(f"  💰 今日投注计划  [{date_str}]  本金 200元")
lines.append(f"  📐 K₁/₄ = (p融合×赔率-1)/(赔率-1)×0.25")
lines.append(eq)
lines.append('')

# Single bets
lines.append(f"  ┌─ 📌 单注（共{len(singles)}注，合计 {single_total}元）")
lines.append(f"  │  基准单注 4元，按命中分动态调整")
lines.append(f"  ├─{sep}")
lines.append(f"  │   序  开赛时间             主队     vs     客队      玩法/方向             赔率     p融合    K₁/₄     投注  命中分")
lines.append(f"  ├─{sep}")
for seq, tbj, home, away, play, odds, prob, kelly, mark, sz, score in rows:
    home_s = home[:8]
    away_s = away[:8]
    lines.append(f"  │  {seq:2d}. {tbj:<16}  {home_s:<10} vs  {away_s:<12}  {play:<20}  {odds:.2f}   {prob:.3f}  {kelly:.4f}  {mark}  {sz}元  {score:.3f}")
lines.append(f"  └─{sep}")
lines.append('')

# 2串1
parlay2 = [
    ([0,1], 4), ([1,3], 4), ([0,2], 4), ([0,5], 4)
]
lines.append(f"  ┌─ 🔗 2串1·稳健（每单 4元 × {len(parlay2)}单 = {len(parlay2)*4}元）")
lines.append(f"  ├─{sep}")
for idxs, stake in parlay2:
    co = combo_odds(idxs)
    wa = win_amt(idxs, stake)
    lines.append(f"  │  [{'ABCDEFGH'[parlay2.index((idxs,stake))]}] 组合赔率 {co}  中奖可赢 {wa}元")
    for i in idxs:
        lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

# 3串1
parlay3 = [
    ([0,1,2], 2), ([1,3,4], 2), ([4,6,7], 2)
]
lines.append(f"  ┌─ 🎰 3串1·进取（每单 2元 × {len(parlay3)}单 = {len(parlay3)*2}元）")
lines.append(f"  ├─{sep}")
for k, (idxs, stake) in enumerate(parlay3):
    co = combo_odds(idxs)
    wa = win_amt(idxs, stake)
    lines.append(f"  │  [{k+1}] 组合赔率 {co}  中奖可赢 {wa}元")
    for i in idxs:
        if i < len(top):
            lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

# 4串1
parlay4 = [
    ([0,1,2,3], 2), ([0,3,5,6], 2)
]
lines.append(f"  ┌─ 🎯 4串1·博取（每单 2元 × {len(parlay4)}单 = {len(parlay4)*2}元）")
lines.append(f"  ├─{sep}")
for k, (idxs, stake) in enumerate(parlay4):
    co = combo_odds(idxs)
    wa = win_amt(idxs, stake)
    lines.append(f"  │  [{k+1}] 组合赔率 {co}  中奖可赢 {wa}元")
    for i in idxs:
        if i < len(top):
            lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

# 5串1
p5_idxs = [0,1,2,3,4]
co5 = combo_odds(p5_idxs); wa5 = win_amt(p5_idxs, 2)
lines.append(f"  ┌─ 🚀 5串1·高博（每单 2元 × 1单 = 2元）")
lines.append(f"  ├─{sep}")
lines.append(f"  │  [1] 组合赔率 {co5}  中奖可赢 {wa5}元")
for i in p5_idxs:
    lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

# 6串1
p6_idxs = [0,1,2,3,4,5]
co6 = combo_odds(p6_idxs); wa6 = win_amt(p6_idxs, 2)
lines.append(f"  ┌─ 💫 6串1·以小博大（每单 2元 × 1单 = 2元）")
lines.append(f"  ├─{sep}")
lines.append(f"  │  [1] 组合赔率 {co6}  中奖可赢 {wa6}元")
for i in p6_idxs:
    lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

# 7串1
p7_idxs = [0,1,2,3,4,5,6]
co7 = combo_odds(p7_idxs); wa7 = win_amt(p7_idxs, 2)
lines.append(f"  ┌─ 🌟 7串1·以小博大（每单 2元 × 1单 = 2元）")
lines.append(f"  ├─{sep}")
lines.append(f"  │  [1] 组合赔率 {co7}  中奖可赢 💰{wa7}元")
for i in p7_idxs:
    lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

# 8串1
p8_idxs = [0,1,2,3,4,5,6,7]
co8 = combo_odds(p8_idxs); wa8 = win_amt(p8_idxs, 2)
lines.append(f"  ┌─ 💎 8串1·以小博大（每单 2元 × 1单 = 2元）")
lines.append(f"  ├─{sep}")
lines.append(f"  │  [1] 组合赔率 {co8}  中奖可赢 💰{wa8}元")
for i in p8_idxs:
    lines.append(f"  │      ✦ {top[i][1]} {top[i][2]}vs{top[i][3]} {top[i][4]} @{top[i][0]:.2f}")
lines.append(f"  └─{sep}")
lines.append('')

serial_total = len(parlay2)*4 + len(parlay3)*2 + len(parlay4)*2 + 2+2+2+2
serial_count = len(parlay2)+len(parlay3)+len(parlay4)+4
total_invest = single_total + serial_total
pct = round(total_invest/200*100, 1)

lines.append(f"  ╔{'═'*W}╗")
lines.append(f"  ║  📊 资金汇总：单注 {len(singles)}注（{single_total}元） + 串关 {serial_count}单（{serial_total}元） = 总投注 {total_invest}元 / 200元本金（占 {pct}%）")
lines.append(f"  ║  🛡 风控：日亏上限 60元 | 连亏3注停手 | 本金<120元减半")
lines.append(f"  ╚{'═'*W}╝")
lines.append('')

# Bottom detail table
lines.append('='*(W+10))
lines.append(f"  📋 今日投注推荐单  [{date_str}]  （北京时间）")
lines.append(f"  📐 概率口径：p融合 = 0.50×P庄家 + 0.30×P泊松 + 0.20×P_ELO  |  K值 = (p×赔率-1)/(赔率-1)×0.25（1/4 Kelly）")
lines.append('='*(W+10))
lines.append(f"  {'开赛时间':<16} {'联赛':<18} {'主队':<16} {'客队':<16} {'市场':<8} {'方向':<16} {'赔率':<7} {'p融合':<8} {'K₁/₄':<8} 命中分")
lines.append('-'*(W+10))
for r in recs:
    league, home, away, kick, market, outcome, odds, prob, kelly, score, hcap = r
    tbj = utc_to_bjt(kick)
    play_dir = fmt_play(market, outcome, hcap)
    mkt = '大小球' if market=='total' else ('让球' if market=='spread' else '独赢')
    dir_s = ('大球' if outcome=='over' else '小球') + (str(hcap) if market=='total' and hcap else '') if market=='total' else play_dir
    home_s = home[:14]; away_s = away[:14]; league_s = league[:16]
    lines.append(f"  {tbj:<16} {league_s:<18} [{'' if outcome!='home' else '主'}{'' if outcome!='away' else '客'}]{home_s:<14} [{'' if outcome!='away' else '客'}{'' if outcome!='home' else '主'}]{away_s:<14} {mkt:<8} {play_dir:<16} {odds:.2f}   {prob:.3f}   {kelly:.4f}  {score:.3f}")
lines.append('='*(W+10))
lines.append(f"  共 {len(recs)} 条推荐（门槛 ≥ 0.45，每场 ≤ 1 条，日限 20）")

out = '\n'.join(lines)
print(out)

# Save to D:\lucky
desktop = r"D:\lucky"
os.makedirs(desktop, exist_ok=True)
fname = f"投注单_{date_str}_{time_str}.txt"
fpath = os.path.join(desktop, fname)
with open(fpath, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"\n✅ 已保存到桌面: {fname}", file=sys.stderr)
