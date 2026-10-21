# -*- coding: utf-8 -*-
"""
_daily_settle.py — 每日自动结算管道

执行顺序：
  1. 运行 16_flashscore_results_scraper.py（下载最新赛果 → match_results）
  2. 运行 37_corner_stats_scraper.py（抓 corner-stats.com 角球终值 → corner_stats_final，
     角球结算的主数据源，明确区分已结束/未结束比赛）
  3. 运行 33_corner_odds_scraper.py（刷新角球实时快照 → corner_live_odds，角球结算的
     兜底数据源；scoremer 目前被 403 封锁，仅 500.com 可用）
  4. 运行 21_auto_settle.py（用赛果+角球数结算 pending 推荐，内部会自动跑复盘报告并存档）
  5. 检查是否满足参数校准门槛，满足则运行 _auto_calibrate.py

用法：
  python _daily_settle.py                    # 标准模式
  python _daily_settle.py --date 2026-06-27  # 结算指定日期
  python _daily_settle.py --skip-scrape      # 跳过爬取，只做结算+校准
  python _daily_settle.py --force-calibrate  # 强制执行校准（不管注数是否达门槛）
"""
import os, sys, subprocess, time, argparse
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PYTHON = sys.executable


def _run(script: str, args: list[str], timeout: int = 900) -> bool:
    path = os.path.join(_SCRIPT_DIR, script)
    cmd  = [PYTHON, '-X', 'utf8', path] + args
    label = script + (' ' + ' '.join(args) if args else '')
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ▶ {label}")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, timeout=timeout, text=True, encoding='utf-8',
                           errors='replace', capture_output=False)
        elapsed = round(time.time() - t0, 1)
        ok = r.returncode == 0
        status = 'OK' if ok else f'FAIL(rc={r.returncode})'
        print(f"  [{status}] 耗时 {elapsed}s")
        return ok
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] 超过 {timeout}s")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def run_pipeline(date: str = None, skip_scrape: bool = False,
                 force_calibrate: bool = False):
    print("=" * 60)
    print(f"  每日结算管道  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if date:
        print(f"  目标日期: {date}")
    print("=" * 60)

    # ── Step 1: 下载赛果 ──────────────────────────────────
    if not skip_scrape:
        ok = _run('16_flashscore_results_scraper.py', [], timeout=900)
        if not ok:
            print("  ⚠ 赛果爬取失败，继续尝试结算（使用已有数据）")
    else:
        print("\n[skip] 跳过赛果爬取")

    # ── Step 2: 抓角球终值（主数据源，明确区分已结束/未结束）──────────────
    if not skip_scrape:
        ok = _run('37_corner_stats_scraper.py', ['--max', '150'], timeout=600)
        if not ok:
            print("  ⚠ 角球终值抓取失败，角球结算将只能用兜底快照")
    else:
        print("\n[skip] 跳过角球终值抓取")

    # ── Step 3: 刷新角球实时快照（兜底数据源）─────────────────────────────
    if not skip_scrape:
        ok = _run('33_corner_odds_scraper.py', [], timeout=300)
        if not ok:
            print("  ⚠ 角球快照刷新失败，角球结算将只能用已有快照（可能匹配不到）")
    else:
        print("\n[skip] 跳过角球快照刷新")

    # ── Step 4: 自动结算（含角球，内部会跑复盘报告并存档到桌面）────────────
    # Bug修复(2026-08-14)：原 timeout=120 远小于 21_auto_settle.py 自身的真实
    # 耗时——它的 __main__ 入口（非 --shadow 模式）每次都会先串行跑两个角球
    # 补抓子进程(37_corner_stats_scraper.py + 33_corner_odds_scraper.py)，各自
    # 内部超时300s，最坏情况600s就烧完了，还没轮到真正的 auto_settle() 等结算
    # 函数执行。而 _run() 把子进程超时当普通失败处理（只打印警告，不 sys.exit），
    # 导致 Windows 计划任务(qqsj_daily_settle_2230，每天22:30)看到的永远是
    # exit 0"成功"，实际上结算函数常年在被杀之前就已经出局——这正是发现
    # hit_recommendations/under_shadow_bets等表pending从5月底一路堆积到8月中
    # 的根因。改成1800s，覆盖600s角球预抓取+积压较多时的实际结算耗时。
    settle_args = ['--date', date] if date else []
    _run('21_auto_settle.py', settle_args, timeout=1800)

    # ── Step 5: 参数校准检查 ──────────────────────────────
    calibrate_args = ['--force'] if force_calibrate else []
    _run('_auto_calibrate.py', calibrate_args, timeout=60)

    print("\n" + "=" * 60)
    print(f"  管道完成  {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='每日自动结算管道')
    parser.add_argument('--date',            help='结算指定日期 YYYY-MM-DD')
    parser.add_argument('--skip-scrape',     action='store_true', help='跳过赛果爬取')
    parser.add_argument('--force-calibrate', action='store_true', help='强制执行参数校准')
    args = parser.parse_args()
    run_pipeline(date=args.date, skip_scrape=args.skip_scrape,
                 force_calibrate=args.force_calibrate)
