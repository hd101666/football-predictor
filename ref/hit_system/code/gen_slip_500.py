# -*- coding: utf-8 -*-
"""
500元实投投注单生成器 v2
- 只取 07-04 12:00 BJT 前未开赛的比赛（严格排除整点）
- 大小球 total/team_total over only (Qiety平台)
- 仅使用 formula_version=v1 推荐
- 按比赛去重（同一场最多下一注）
"""
import sqlite3, sys, os, re
from datetime import datetime, timezone, timedelta
sys.stdout.reconfigure(encoding='utf-8')

BJT = timezone(timedelta(hours=8))
NOW = datetime.now(timezone.utc).astimezone(BJT)
CUTOFF = datetime(2026, 7, 4, 12, 0, 0, tzinfo=BJT)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DB_ENGINE_URL
DB = DB_ENGINE_URL.replace('sqlite:///', '')

conn = sqlite3.connect(DB)
c = conn.cursor()

# ── 重置上次 in_slip 标记，重新选取 ──────────────────────────────────────────
c.execute("""UPDATE hit_recommendations SET status='pending'
             WHERE fetch_date IN ('2026-07-03','2026-07-04') AND status='in_slip'""")
conn.commit()

# ── 仅读取 v1 推荐 ────────────────────────────────────────────────────────────
c.execute("""
SELECT id, league_name, home_team, away_team, kickoff_utc, market, outcome,
       best_odds, model_prob, kelly_fraction, hit_score, handicap
FROM hit_recommendations
WHERE fetch_date IN ('2026-07-03','2026-07-04')
  AND is_filtered = 0
  AND status = 'pending'
  AND (formula_version = 'v1' OR formula_version IS NULL)
  AND best_source != 'qiety_yb'
  AND market IN ('total','team_total')
  AND outcome = 'over'
ORDER BY hit_score DESC
""")
raw = c.fetchall()

def normalize_team(name):
    if not name:
        return ''
    n = re.sub(r'\(女\)|\(W\)|\(男\)|\(M\)', '', name)
    return n.strip().lower()

# 时间过滤 + 按比赛去重（date+主客队规范化，取分最高）
seen = {}
for r in raw:
    rid, lg, hm, aw, kick, mkt, out, odds, prob, kelly, score, hcap = r
    try:
        dt = datetime.fromisoformat(str(kick).replace('Z', '+00:00'))
        dt_bjt = dt.astimezone(BJT)
        date_part = dt.strftime('%Y-%m-%d')
    except Exception:
        continue
    # 严格截止：未开赛 且 < 12:00（排除整点）
    if dt_bjt <= NOW or dt_bjt >= CUTOFF:
        continue
    key = (date_part, normalize_team(hm), normalize_team(aw))
    if key not in seen or score > seen[key][10]:
        seen[key] = r

# 二次去重：同联赛前缀+同日期+同盘口+同市场 = 同一场，保留开赛时间较晚的记录
primary = sorted(seen.values(), key=lambda r: r[4])  # 按开赛时间升序
secondary_seen = {}
eligible_list = []
for r in primary:
    rid, lg, hm, aw, kick, mkt, out, odds, prob, kelly, score, hcap = r
    lg_prefix = (lg or '').split()[0]
    try:
        dp = datetime.fromisoformat(str(kick).replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except Exception:
        dp = str(kick)[:10]
    sec_key = (dp, lg_prefix, mkt, hcap)
    if sec_key in secondary_seen:
        eligible_list[secondary_seen[sec_key]] = r  # 替换为时间更晚的
    else:
        secondary_seen[sec_key] = len(eligible_list)
        eligible_list.append(r)

eligible = sorted(eligible_list, key=lambda r: r[10], reverse=True)[:12]

def bjt_str(kick):
    try:
        dt = datetime.fromisoformat(str(kick).replace('Z', '+00:00')).astimezone(BJT)
        return dt.strftime('%m月%d日%H:%M')
    except:
        return str(kick)[:16]

def play_cn(market, outcome, hcap):
    d = '大球' if outcome == 'over' else '小球'
    h = str(hcap) if hcap and hcap != 0 else ''
    if market == 'team_total':
        return f"球队大小/{d}{h}"
    return f"大小球/{d}{h}"

def single_sz(score):
    if score >= 0.95: return 40
    if score >= 0.88: return 35
    if score >= 0.82: return 30
    if score >= 0.80: return 25
    if score >= 0.79: return 20
    if score >= 0.77: return 20
    if score >= 0.75: return 15
    return 15

singles = eligible[:10]
top8 = [r for r in singles if r[9] > 0][:8]

W = 118
sep = '─' * W

lines = []
lines.append('')
lines.append('=' * W)
lines.append(f"  实投500元投注计划  [2026-07-03/04]  窗口: 07-04 12:00 BJT前未开赛")
lines.append(f"  平台: Qiety(YB)  市场: 大小球/球队大小  方向: 大球only  公式: v1")
lines.append(f"  K1/4 = (p融合*赔率-1)/(赔率-1)*0.25")
lines.append('=' * W)
lines.append('')

# ── 单注 ──────────────────────────────────────────────────────────────────────
lines.append(f"  +- 单注（共{len(singles)}注，阶梯投注）")
lines.append(f"  +-{sep}")
lines.append(f"  |   序  开赛时间        联赛             主队         客队         方向              赔率  p融合  K1/4   投注   命中分")
lines.append(f"  +-{sep}")
single_total = 0
for i, r in enumerate(singles):
    rid, lg, hm, aw, kick, mkt, out, odds, prob, kelly, score, hcap = r
    tbj  = bjt_str(kick)
    play = play_cn(mkt, out, hcap)
    sz   = single_sz(score)
    single_total += sz
    mark = '[热]' if score >= 0.85 else ('[推]' if score >= 0.75 else '[选]')
    lg_s  = (lg  or '')[:16]
    hm_s  = (hm  or '')[:11]
    aw_s  = (aw  or '')[:11]
    play_s= play[:18]
    lines.append(f"  |  {i+1:2d}. {tbj:<14} {lg_s:<17} {hm_s:<12} {aw_s:<12} {play_s:<19} {odds:.2f}  {prob:.3f} {kelly:.4f}  {mark}{sz}元  {score:.3f}")
lines.append(f"  +-{sep}")
lines.append(f"  >> 单注小计: {len(singles)}注 = {single_total}元")
lines.append('')

# ── 串关 ──────────────────────────────────────────────────────────────────────
s2, s3, s4, s5, s6, s7, s8 = 20, 15, 20, 25, 30, 20, 20

PARLAY_DEFS = [
    (2, "2串1 稳健",    s2, [([0,1],s2),([1,2],s2),([0,2],s2),([0,4],s2)]),
    (3, "3串1 进取",    s3, [([0,1,2],s3),([1,2,3],s3),([3,5,6],s3)]),
    (4, "4串1 博取",    s4, [([0,1,2,3],s4),([0,2,4,5],s4)]),
    (5, "5串1 高博",    s5, [([0,1,2,3,4],s5)]),
    (6, "6串1 以小博大",s6, [([0,1,2,3,4,5],s6)]),
    (7, "7串1 以小博大",s7, [([0,1,2,3,4,5,6],s7)]),
    (8, "8串1 以小博大",s8, [([0,1,2,3,4,5,6,7],s8)]),
]

def co(idxs):
    o = 1.0
    for i in idxs:
        if i < len(top8): o *= top8[i][7]
    return round(o, 1)

def win(idxs, stake):
    return round(co(idxs)*stake - stake, 1)

def _valid(combos):
    n = len(top8)
    return [(idxs, stake) for idxs, stake in combos if all(i < n for i in idxs)]

serial_n = 0
serial_t = 0
for min_top, label, stake, combos in PARLAY_DEFS:
    if len(top8) < min_top: continue
    valid = _valid(combos)
    if not valid: continue
    tot = sum(s for _, s in valid)
    serial_n += len(valid)
    serial_t += tot
    lines.append(f"  +- {label}（每单 {stake}元 x {len(valid)}单 = {tot}元）")
    lines.append(f"  +-{sep}")
    for k, (idxs, s) in enumerate(valid):
        prize = win(idxs, s)
        pz = f"[大奖]{prize}元" if prize >= 200 else f"{prize}元"
        lines.append(f"  |  [{k+1}] 组合赔率 {co(idxs)}  中奖可赢 {pz}")
        for i in idxs:
            if i < len(top8):
                t8 = top8[i]
                lines.append(f"  |      * {bjt_str(t8[4])} {(t8[2] or '')[:10]}vs{(t8[3] or '')[:10]} {play_cn(t8[5],t8[6],t8[11])} @{t8[7]:.2f}")
    lines.append(f"  +-{sep}")
    lines.append('')

grand = single_total + serial_t
pct   = round(grand / 500 * 100, 1)
lines.append(f"  +{'='*W}+")
lines.append(f"  |  资金汇总：单注{len(singles)}注({single_total}元) + 串关{serial_n}单({serial_t}元) = 总投注 {grand}元 / 500元（{pct}%）")
lines.append(f"  |  风控：日亏上限150元 | 连亏4注停手 | 本金<300元单注减半")
lines.append(f"  +{'='*W}+")
lines.append('')

# ── 明细表 ────────────────────────────────────────────────────────────────────
lines.append('=' * (W+10))
lines.append(f"  实投推荐明细  [2026-07-03/04 -> 07-04 12:00前]  本金500元  公式v1")
lines.append('=' * (W+10))
lines.append(f"  {'开赛时间':<14} {'联赛':<20} {'主队':<16} {'客队':<16} {'市场':<8} {'方向':<18} {'赔率':<6} {'p融合':<7} {'K1/4':<7} {'投注':>6} {'命中分':<6}")
lines.append('-' * (W+10))
for i, r in enumerate(singles):
    rid, lg, hm, aw, kick, mkt, out, odds, prob, kelly, score, hcap = r
    tbj   = bjt_str(kick)
    lg_s  = (lg or '')[:18]
    hm_s  = (hm or '')[:14]
    aw_s  = (aw or '')[:14]
    play  = play_cn(mkt, out, hcap)
    sz    = single_sz(score)
    mkt_s = '大小球' if mkt == 'total' else '球队大小'
    lines.append(f"  {tbj:<14} {lg_s:<20} {hm_s:<16} {aw_s:<16} {mkt_s:<8} {play:<18} {odds:.2f}   {prob:.3f}   {kelly:.4f}   {sz}元   {score:.3f}")
lines.append('=' * (W+10))
lines.append(f"  共 {len(singles)} 条推荐  截止: 2026-07-04 12:00 BJT(严格)  平台: Qiety(YB)  仅v1公式")
lines.append('')

out_text = '\n'.join(lines)
print(out_text)

# ── 保存文件 ──────────────────────────────────────────────────────────────────
desktop = r"D:\lucky"
os.makedirs(desktop, exist_ok=True)
ts = NOW.strftime('%H%M')
fname = f"投注单_2026-07-03_500元_{ts}.txt"
fpath = os.path.join(desktop, fname)
with open(fpath, 'w', encoding='utf-8') as f:
    f.write(out_text)
print(f"\n已保存: {fpath}", file=sys.stderr)

# ── 落库 ──────────────────────────────────────────────────────────────────────
try:
    c.execute("""CREATE TABLE IF NOT EXISTS betting_slips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slip_date TEXT, slip_time TEXT, file_name TEXT,
        total_invest REAL, single_count INTEGER, serial_count INTEGER,
        content TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""INSERT INTO betting_slips(slip_date,slip_time,file_name,total_invest,single_count,serial_count,content)
                 VALUES(?,?,?,?,?,?,?)""",
              ('2026-07-03', ts, fname, grand, len(singles), serial_n, out_text))
    ids = [r[0] for r in singles]
    c.executemany("UPDATE hit_recommendations SET status='in_slip' WHERE id=?", [(i,) for i in ids])
    conn.commit()
    print(f"落库完成: betting_slips + {len(ids)}条推荐标记in_slip", file=sys.stderr)
except Exception as e:
    print(f"落库异常: {e}", file=sys.stderr)
finally:
    conn.close()
