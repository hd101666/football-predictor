# -*- coding: utf-8 -*-
"""
_auto_calibrate.py — 参数自动校准（每积累100注新结算数据触发一次）

功能：
  1. 检查距上次校准新增的已结算注数
  2. 若 >= CALIBRATE_EVERY，运行复盘分析
  3. 自动计算并写入 _param_overrides.json（由 config.py 加载覆盖）
  4. 打印校准报告

用法：
  python _auto_calibrate.py               # 自动判断是否需要校准
  python _auto_calibrate.py --force       # 强制执行（忽略100注门槛）
  python _auto_calibrate.py --dry-run     # 只打印报告，不写入
"""
import os, sys, json, argparse, re
from datetime import datetime, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL, HIT_SCORE_GLOBAL_THRESHOLD

engine = create_engine(DB_ENGINE_URL, connect_args={'timeout': 30})

CALIBRATE_EVERY = 100       # 每积累多少注新结算数据触发一次
STATE_FILE = os.path.join(_SCRIPT_DIR, '_calibration_state.json')
OVERRIDE_FILE = os.path.join(_SCRIPT_DIR, '_param_overrides.json')


# ── 状态文件 I/O ──────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'last_settled_count': 0, 'last_calibration_date': None,
                'calibration_count': 0, 'HIT_SCORE_GLOBAL_THRESHOLD': HIT_SCORE_GLOBAL_THRESHOLD}


def _save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _load_overrides() -> dict:
    try:
        with open(OVERRIDE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_overrides(overrides: dict):
    with open(OVERRIDE_FILE, 'w', encoding='utf-8') as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)


# ── 读取已结算数量 ────────────────────────────────────────────────────

def _get_settled_count() -> int:
    # Bug修复(2026-07-22)：漏了formula_version过滤，把v2(价值边际驱动的并行实验
    # 公式，从不进real staking/_generate_bet_plan()，见generate_recommendations()
    # 文档)结算量也算进"距上次校准新增多少注"，导致v2结算得快时空耗触发校准门槛，
    # 且_analyze()同一个漏洞更严重——见下面说明。
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT COUNT(*) FROM hit_recommendations
            WHERE status IN ('win','lose','push')
              AND best_odds BETWEEN 1.20 AND 20.0
              AND (formula_version = 'v1' OR formula_version IS NULL)
        """)).fetchone()
    return row[0] if row else 0


# ── 核心分析（从 _review_report.py 内联提取） ────────────────────────

def _analyze(days: int = 90) -> dict:
    """返回分析数据字典"""
    # Bug修复(2026-07-22)：原查询没有formula_version过滤，把v1(HIT_SCORE_GLOBAL_
    # THRESHOLD门槛+MARKET_BIAS策略限制下的真实推荐，唯一会被这个脚本的
    # HIT_SCORE_GLOBAL_THRESHOLD校准结果影响的部分)和v2(用完全不同的
    # compute_hit_score_v2()公式、不受MARKET_BIAS约束、只用于对比复盘、从不
    # 进真实投注计划的并行实验数据)混在一起分析——两者的hit_score数值含义完全
    # 不同(v1是覆盖度+一致性+置信度+偏置+联赛加成的综合分，v2是纯edge/kelly/
    # 来源数driven)，混在同一个命中分分桶里比较毫无意义，且v2的spread/team_total
    # 实验数据(MARKET_BIAS对v1锁定只推大球，v2没有这个限制)会把market_roi的
    # 亏损市场判断带偏(实测team_total: v1单独+2.77pnl，v2单独-13.88pnl，混合后
    # 才会显示"持续亏损")。这个脚本的产出(HIT_SCORE_GLOBAL_THRESHOLD)只对v1
    # 生效，分析范围也必须只用v1数据。
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT market, outcome, best_odds, model_prob, hit_score, status, fetch_date
            FROM hit_recommendations
            WHERE status IN ('win','lose','push')
              AND fetch_date >= :cutoff
              AND best_odds BETWEEN 1.20 AND 20.0
              AND market != 'correct_score'
              AND (formula_version = 'v1' OR formula_version IS NULL)
            ORDER BY fetch_date
        """), {'cutoff': cutoff}).fetchall()

    if not rows:
        return {}

    total  = len(rows)
    wins   = sum(1 for r in rows if r[5] == 'win')
    pushes = sum(1 for r in rows if r[5] == 'push')
    eff    = total - pushes
    wr     = wins / eff * 100 if eff else 0
    pnl    = sum((r[2]-1) if r[5]=='win' else (0 if r[5]=='push' else -1) for r in rows)
    roi    = pnl / eff * 100 if eff else 0

    # 按市场分层 ROI
    markets = {}
    for r in rows:
        markets.setdefault(r[0], []).append(r)
    mkt_roi = {}
    for m, mrs in markets.items():
        meff = sum(1 for r in mrs if r[5] != 'push')
        mpnl = sum((r[2]-1) if r[5]=='win' else (0 if r[5]=='push' else -1) for r in mrs)
        mkt_roi[m] = mpnl / meff * 100 if meff else 0

    # 命中分区间实际胜率
    buckets = [(0.45,0.55),(0.55,0.65),(0.65,0.70),(0.70,0.75),(0.75,1.01)]
    score_calibration = []
    for lo, hi in buckets:
        brows = [r for r in rows if lo <= r[4] < hi]
        if len(brows) < 3:
            continue
        beff = sum(1 for r in brows if r[5] != 'push')
        bwin = sum(1 for r in brows if r[5] == 'win')
        bwr  = bwin / beff * 100 if beff else 0
        score_calibration.append({'lo': lo, 'hi': hi, 'n': len(brows),
                                   'win_rate': round(bwr, 1)})

    return {'total': total, 'win_rate': round(wr, 1), 'roi': round(roi, 2),
            'pnl': round(pnl, 2), 'market_roi': mkt_roi,
            'score_calibration': score_calibration, 'cutoff': cutoff,
            'days': days}


# ── 校准逻辑 ─────────────────────────────────────────────────────────

def _compute_new_threshold(analysis: dict, current_threshold: float) -> float:
    """根据分析数据推算新门槛"""
    roi = analysis.get('roi', 0)
    cal = analysis.get('score_calibration', [])
    if not cal:
        return current_threshold

    # 找最低实际胜率 >= 50% 的分桶作为阈值下限
    new_thr = current_threshold
    if roi < -5:
        new_thr = min(current_threshold + 0.02, 0.80)
    elif roi > 15:
        new_thr = max(current_threshold - 0.02, 0.60)
    else:
        # 微调：找命中分最低档实际胜率是否 < 45%
        # Bug修复(2026-07-22)：原来lo_bucket只有上界(b['lo'] < current_threshold+0.05)，
        # 没有下界，导致会把current_threshold提高之前遗留的陈年历史数据（hit_score
        # 远低于当前门槛，早就被现行门槛挡在外面、跟"现在要不要调门槛"毫无关系）也
        # 算进来。实测2026-07-20这次校准就是这样触发的：90天窗口里混进497注hit_score
        # 0.45-0.65的陈年v1推荐（门槛提高到0.70/0.65之前生成的），其中[0.45,0.55)
        # 这一档胜率43.2%最差，被误判成"当前门槛附近表现差"，把new_thr直接下调到0.55，
        # 而实际当前门槛(0.70，或者MARKET_BIAS里total/team_total市场专属的0.65)真正
        # 附近的[0.65,0.75)两档胜率其实是53%+，完全正常，本不该调。
        # 加下界：只看current_threshold-0.10以上的分桶——0.10的余量是为了兼容
        # MARKET_BIAS表里"只推大球"策略下total/team_total市场专属的market_min_threshold
        # =0.65（比全局门槛低0.05，是当前确实在用的真实准入线，不是历史遗留），
        # 但排除掉更往下的、门槛提高后已经不可能再产生的陈年分桶。
        lo_bucket = [b for b in cal
                     if current_threshold - 0.10 <= b['lo'] < current_threshold + 0.05]
        if lo_bucket:
            worst = min(lo_bucket, key=lambda b: b['win_rate'])
            if worst['win_rate'] < 45.0 and worst['n'] >= 10:
                new_thr = min(worst['hi'], 0.80)

    return round(new_thr, 2)


def _print_report(analysis: dict, current_thr: float, new_thr: float):
    W = 72
    print()
    print('=' * W)
    print(f"  自动校准报告  [{analysis.get('cutoff','')} 起 / {analysis.get('days',90)}天]")
    print('=' * W)
    print(f"  总结算: {analysis['total']} 注  |  胜率: {analysis['win_rate']}%  |  ROI: {analysis['roi']:+.1f}%")
    print()

    cal = analysis.get('score_calibration', [])
    if cal:
        print(f"  {'命中分区间':<14} {'注数':>5} {'实际胜率':>9}")
        print('  ' + '-' * 30)
        for b in cal:
            flag = '✅' if b['win_rate'] >= 50 else '⚠️ '
            print(f"  {flag} [{b['lo']:.2f},{b['hi']:.2f})   {b['n']:>5}  {b['win_rate']:>8.1f}%")

    print()
    if abs(new_thr - current_thr) < 0.001:
        print(f"  HIT_SCORE_GLOBAL_THRESHOLD: {current_thr} → 无需调整")
    else:
        direction = '上调' if new_thr > current_thr else '下调'
        print(f"  HIT_SCORE_GLOBAL_THRESHOLD: {current_thr} → {new_thr}  [{direction}]")

    losing_mkts = [m for m, r in analysis.get('market_roi', {}).items() if r < -10]
    if losing_mkts:
        print(f"  持续亏损市场: {losing_mkts}")
    print('=' * W)
    print()


def run_calibration(force: bool = False, dry_run: bool = False):
    state = _load_state()
    current_count = _get_settled_count()
    delta = current_count - state.get('last_settled_count', 0)

    print(f"[auto_calibrate] 已结算总量: {current_count}  "
          f"距上次校准新增: {delta}  触发门槛: {CALIBRATE_EVERY}")

    if not force and delta < CALIBRATE_EVERY:
        print(f"  → 不满足 {CALIBRATE_EVERY} 注门槛，跳过本次校准")
        return

    print("  → 开始校准分析...")
    analysis = _analyze(days=90)
    if not analysis:
        print("  → 无足够已结算数据，跳过")
        return

    overrides = _load_overrides()
    current_thr = overrides.get('HIT_SCORE_GLOBAL_THRESHOLD', HIT_SCORE_GLOBAL_THRESHOLD)
    new_thr = _compute_new_threshold(analysis, current_thr)

    _print_report(analysis, current_thr, new_thr)

    if dry_run:
        print("  [dry-run] 不写入文件")
        return

    # 写入 override 文件（config.py 在末尾加载此文件）
    overrides['HIT_SCORE_GLOBAL_THRESHOLD'] = new_thr
    overrides['_last_calibrated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    overrides['_calibration_roi'] = analysis['roi']
    overrides['_calibration_n']   = analysis['total']
    _save_overrides(overrides)
    print(f"  → 已写入 _param_overrides.json: HIT_SCORE_GLOBAL_THRESHOLD = {new_thr}")

    # 更新状态
    state['last_settled_count']      = current_count
    state['last_calibration_date']   = datetime.now().strftime('%Y-%m-%d %H:%M')
    state['calibration_count']       = state.get('calibration_count', 0) + 1
    state['HIT_SCORE_GLOBAL_THRESHOLD'] = new_thr
    _save_state(state)
    print(f"  → 校准 #{state['calibration_count']} 完成")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='参数自动校准')
    parser.add_argument('--force',   action='store_true', help='忽略注数门槛强制执行')
    parser.add_argument('--dry-run', action='store_true', help='只打印报告不写入')
    args = parser.parse_args()
    run_calibration(force=args.force, dry_run=args.dry_run)
