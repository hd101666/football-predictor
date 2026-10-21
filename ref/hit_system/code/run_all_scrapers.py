# run_all_scrapers.py — 按优先级组并行执行爬虫（P1全部并行→P2全部并行→P3全部并行）
# WAL 模式支持并发写入，同组内爬虫同时启动，组间串行等待
import sys, subprocess, time, json, os, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

PYTHON = sys.executable

# ── 优先级分组 ────────────────────────────────────────────────────────────
# P1: 实时赔率（最关键，先跑）
# P2: 赛事数据（赛果/统计）
# P3: 历史数据（可延后）
SCRIPTS = [
    # ── P1: 实时赔率 ──────────────────────────────────
    ("03", "03_实时赔率抓取.py",              600,  "p1"),
    ("15", "15_pinnacle_oddsportal_scraper.py", 1800, "p1"),
    ("12", "12_pinnacle_scraper.py",          900,  "p1"),
    ("13", "13_bet365_scraper.py",            900,  "p1"),
    ("10", "10_oddsportal_scraper.py",        900,  "p1"),
    ("11", "11_betexplorer_scraper.py",       900,  "p1"),
    ("24", "24_betfair_scraper.py",           600,  "p1"),
    ("26", "26_multi_bookmaker_scraper.py",   900,  "p1"),
    ("29", "29_qiety_yb_full_scraper.py",    900,  "p1"),
    ("35", "35_theoddsapi_multi_scraper.py", 600,  "p1"),
    # ── P2: 赛果/统计 ────────────────────────────────
    ("07", "07_sofascore_scraper.py",         900,  "p2"),
    ("08", "08_flashscore_scraper.py",        900,  "p2"),
    ("16a","16_flashscore_results_scraper.py",900,  "p2"),
    ("18", "18_espn_scores_scraper.py",       900,  "p2"),
    # ── P3: 高级统计/历史 ────────────────────────────
    ("01", "01_初始化全量数据.py",             600,  "p3"),
    ("02", "02_每日增量更新.py",               600,  "p3"),
    ("09", "09_flashscore_schedule_scraper.py", 900,  "p3"),
    ("16b","16_footballdata_scraper.py",       600,  "p3"),
    ("fdh","23_football_data_scraper.py",     1800,  "p3"),
    ("17", "17_understat_scraper.py",          900,  "p3"),
    ("19", "19_whoscored_scraper.py",          600,  "p3"),
    ("22", "22_fbref_scraper.py",              900,  "p3"),
    ("23", "23_bball_ref_scraper.py",          900,  "p3"),
    ("25", "25_transfermarkt_scraper.py",      900,  "p3"),
]

# ── 进度记录 ──────────────────────────────────────────────────────────────
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "scraper_progress.json")
_progress_lock = threading.Lock()

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def run_one(label, script, timeout, priority, progress):
    log_path = f"logs/{label}.log"
    pri_icon = {"p1": "🔴", "p2": "🟡", "p3": "🟢"}.get(priority, "⚪")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {pri_icon} 开始 {label}: {script} (超时{timeout}s)", flush=True)
    t0 = time.time()
    try:
        result = subprocess.run(
            [PYTHON, "-X", "utf8", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1"}
        )
        elapsed = round(time.time() - t0, 1)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(result.stderr)
        lines = (result.stdout + result.stderr).strip().splitlines()
        tail = lines[-1] if lines else "(无输出)"
        status = "OK" if result.returncode == 0 else f"FAILED(rc={result.returncode})"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{status}] {label} 耗时{elapsed}s | {tail}", flush=True)
    except subprocess.TimeoutExpired:
        elapsed = timeout
        status = "TIMEOUT"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [TIMEOUT] {label} 超时{timeout}s", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        status = "ERROR"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] {label}: {e}", flush=True)

    with _progress_lock:
        progress[label] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "elapsed": elapsed,
            "script": script,
        }
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    return label, status, elapsed


def run_group(group, progress, max_workers=None):
    """并行执行同一优先级组内的所有爬虫，返回 {label: status}"""
    if not group:
        return {}
    workers = max_workers or len(group)
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_one, label, script, timeout, priority, progress): label
            for label, script, timeout, priority in group
        }
        for fut in as_completed(futures):
            label, status, elapsed = fut.result()
            results[label] = status
    return results


if __name__ == "__main__":
    print("=" * 60)
    print(f"全量爬虫并行执行 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
    print(f"共 {len(SCRIPTS)} 个脚本  |  同优先级组内并行，组间串行")
    print("优先级: 🔴P1(实时赔率) → 🟡P2(赛果) → 🟢P3(历史)")
    print("=" * 60)

    os.makedirs("logs", exist_ok=True)
    progress = load_progress()

    # ── 命令行参数 ────────────────────────────────────────────────────────
    args = sys.argv[1:]
    run_labels = None
    mode = "full"

    if args:
        parsed = []
        for a in args:
            if a in ("--incremental", "-i"):
                mode = "incremental"
            elif a in ("--priority", "-p"):
                mode = "priority"
            elif a in ("--help", "-h"):
                print("用法: python run_all_scrapers.py [选项] [标签...]")
                print("  --incremental, -i  只运行上次失败的爬虫")
                print("  --priority, -p     只运行 P1 实时赔率爬虫")
                print("  07 08 15           只运行指定标签的爬虫")
                sys.exit(0)
            else:
                parsed.append(a)
        if parsed:
            run_labels = set(parsed)

    # ── 筛选要运行的脚本 ──────────────────────────────────────────────────
    to_run = []
    for label, script, timeout, priority in SCRIPTS:
        if not os.path.isfile(script):
            print(f"[跳过] {label}: {script} (文件不存在)")
            continue
        if run_labels and label not in run_labels:
            continue
        if mode == "priority" and priority != "p1":
            continue
        if mode == "incremental":
            last = progress.get(label, {})
            if last.get("status") == "OK":
                print(f"[跳过] {label}: {script} (上次成功 {last.get('timestamp','')})")
                continue
        to_run.append((label, script, timeout, priority))

    if not to_run:
        print("没有需要运行的爬虫。")
        sys.exit(0)

    # ── 按优先级分组 ──────────────────────────────────────────────────────
    from itertools import groupby
    priority_order = ["p1", "p2", "p3"]
    grouped = {p: [] for p in priority_order}
    for item in to_run:
        grouped[item[3]].append(item)

    print(f"\n本次将运行 {len(to_run)} 个爬虫（组内并行）:\n")
    for p in priority_order:
        if grouped[p]:
            icon = {"p1":"🔴","p2":"🟡","p3":"🟢"}[p]
            print(f"  {icon} {p.upper()} ({len(grouped[p])}个并行): " +
                  ", ".join(l for l,_,_,_ in grouped[p]))

    # ── 按组并行执行 ──────────────────────────────────────────────────────
    summary = {}
    for p in priority_order:
        group = grouped[p]
        if not group:
            continue
        icon = {"p1":"🔴","p2":"🟡","p3":"🟢"}[p]
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} 启动 {p.upper()} 组 ({len(group)}个并行)")
        print(f"{'='*60}")
        group_results = run_group(group, progress)
        summary.update(group_results)
        ok = sum(1 for v in group_results.values() if v == "OK")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {p.upper()} 组完成: {ok}/{len(group)} 成功")

    # ── 每日结算管道（P2 完成后自动执行）────────────────────────────────
    if mode != "priority" and (run_labels is None or "settle" in run_labels):
        if grouped.get("p2") and os.path.isfile("_daily_settle.py"):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 启动每日结算管道...")
            try:
                result = subprocess.run(
                    [PYTHON, "-X", "utf8", "_daily_settle.py", "--skip-scrape"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=300,
                    env={**os.environ, "PYTHONUTF8": "1"}
                )
                lines = (result.stdout + result.stderr).strip().splitlines()
                for line in lines[-15:]:
                    print(f"  {line}")
                summary["settle"] = "OK" if result.returncode == 0 else f"FAIL(rc={result.returncode})"
            except Exception as e:
                print(f"  [settle ERROR] {e}")
                summary["settle"] = "ERROR"

    # ── 汇总 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    ok_count  = sum(1 for v in summary.values() if v == "OK")
    fail_count = sum(1 for v in summary.values() if v != "OK")
    print(f"汇总: ✅ {ok_count} 成功  ❌ {fail_count} 失败/超时")
    for k, v in summary.items():
        print(f"  [{'✓' if v=='OK' else '✗'}] {k}: {v}")
    print("=" * 60)
