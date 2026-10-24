# -*- coding: utf-8 -*-
"""加速版批量翻译：大批次 + 多线程并发。

改进：
  1. 批次 40 -> 80（JSON 输出上限 8000 tokens，够 80 条）
  2. 4 线程并发（智谱 glm-4-flash 免费额度无并发限制）
  3. 每批独立重试，单批失败不影响整体
  4. 断点续跑（读已有 CSV 跳过）
  5. 立即写盘（每批完成就 flush）

用法：
  python -X utf8 translate_teams_fast.py --workers 4 --batch 80
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
OUT_CSV = r"D:\cl\qqsj_v2\qiety_team_map_llm.csv"
BASE_MAP = r"D:\cl\qqsj_v2\qiety_team_map.csv"

PROMPT = """你是足球俱乐部名称专家。把中文足球队名翻译成英文俱乐部名。

严格要求：
1. 只输出 JSON 数组，每项 {{"zh":"中文名","en":"英文名","conf":"high|low"}}
2. en 必须是该俱乐部真实的官方英文名，不是城市名、不是意译
3. 完全不确定时 en 填 "?"，conf 填 "low"
4. 严禁把不同球队翻译成同一个英文名
5. 严禁中英混杂（如 "Donau弗里德"）
6. 含"女"→英文含 Women；含"U19/U21/U23"→保留；含"B队"→含 B 或 II
7. 参考联赛可判断，但不要因为同联赛就套用同城大俱乐部

待翻译（中文名 | 所属联赛）：
{items}

只输出 JSON 数组："""

_lock = threading.Lock()


def get_key():
    k = os.environ.get("ZHIPU_API_KEY")
    if not k:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as kh:
            k, _ = winreg.QueryValueEx(kh, "ZHIPU_API_KEY")
    if not k:
        raise SystemExit("未找到 ZHIPU_API_KEY")
    return k


def load_known():
    m = {}
    if os.path.exists(BASE_MAP):
        with open(BASE_MAP, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en:
                    m[zh] = en
    return m


def collect_missing(db, known):
    con = sqlite3.connect("file:" + db + "?mode=ro", uri=True, timeout=60)
    rows = con.execute("""
        SELECT home_team, away_team, league, COUNT(*) n
        FROM soft_odds_snapshots WHERE source='qiety'
        GROUP BY home_team, away_team, league ORDER BY n DESC
    """).fetchall()
    miss = {}
    for h, a, lg, n in rows:
        for t in (h, a):
            t = (t or "").strip()
            if t and t not in known and t not in miss:
                miss[t] = lg or ""
    return miss


def call_glm(key, prompt, model, retry=3):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 8000,
    })
    for i in range(retry):
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "120", "-X", "POST", API,
                                "-H", "Content-Type: application/json",
                                "-H", "Authorization: Bearer " + key,
                                "-d", payload], capture_output=True, text=True)
            d = json.loads((r.stdout or "").strip())
            if "choices" in d:
                return d["choices"][0]["message"]["content"]
            code = str(d.get("error", {}).get("code"))
            if code in ("1305", "4290", "429"):
                time.sleep(5 + i * 5)
                continue
            return None
        except Exception:
            time.sleep(2 + i * 2)
    return None


def parse_json(text):
    if not text:
        return {}
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    m = re.search(r"\[.*\]", t, re.S)
    if m:
        try:
            arr = json.loads(m.group(0))
            out = {}
            for it in arr:
                if isinstance(it, dict):
                    zh = str(it.get("zh") or "").strip()
                    en = str(it.get("en") or "").strip()
                    conf = str(it.get("conf") or "").strip().lower()
                    if zh:
                        out[zh] = (en, conf)
            if out:
                return out
        except json.JSONDecodeError:
            # 修复尾逗号
            try:
                fixed = re.sub(r",\s*\]", "]", m.group(0))
                arr = json.loads(fixed)
                out = {}
                for it in arr:
                    if isinstance(it, dict):
                        zh = str(it.get("zh") or "").strip()
                        en = str(it.get("en") or "").strip()
                        conf = str(it.get("conf") or "").strip().lower()
                        if zh:
                            out[zh] = (en, conf)
                return out
            except Exception:
                pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            return {str(k).strip(): (str(v).strip(), "unknown") for k, v in obj.items()}
        except json.JSONDecodeError:
            pass
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--out", default=OUT_CSV)
    ap.add_argument("--batch", type=int, default=80)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="glm-4-flash")
    a = ap.parse_args()

    key = get_key()
    known = load_known()
    miss = collect_missing(a.db, known)

    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("en_name") or "").strip() and (r.get("source") or "").startswith("glm"):
                    done.add(r["zh_name"])
    print(f"已有 {len(done)} 条翻译，缺失 {len(miss)} 个")

    todo = [(t, lg) for t, lg in miss.items() if t not in done]
    if a.limit:
        todo = todo[:a.limit]
    batches = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"待翻 {len(todo)} 个 -> {len(batches)} 批（{a.batch}/批，{a.workers} 并发）\n")

    newfile = not os.path.exists(a.out)
    fh = open(a.out, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if newfile:
        w.writerow(["zh_name", "en_name", "league", "source"])
        fh.flush()

    t0 = time.time()
    ok = fail = done_b = 0

    def work(batch):
        items = "\n".join(f"- {t} | {lg}" for t, lg in batch)
        resp = call_glm(key, PROMPT.format(items=items), a.model)
        return batch, parse_json(resp)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(work, b): b for b in batches}
        for fut in as_completed(futs):
            batch, got = fut.result()
            with _lock:
                for t, lg in batch:
                    item = got.get(t)
                    if isinstance(item, tuple):
                        en, conf = item
                    else:
                        en, conf = (str(item or "").strip(), "unknown")
                    bad = (not en or en == "?" or re.search("[\u4e00-\u9fff]", en))
                    if bad:
                        w.writerow([t, "", lg, "unresolved"])
                        fail += 1
                    else:
                        w.writerow([t, en, lg, f"{a.model}:{conf}"])
                        ok += 1
                fh.flush()
                done_b += 1
                el = time.time() - t0
                rate = (done_b * a.batch) / el if el else 0
                left = (len(batches) - done_b) * a.batch
                print(f"  批 {done_b}/{len(batches)}  成功{ok} 未解{fail}  "
                      f"{rate:.1f}个/秒  ETA {left/rate/60 if rate else 0:.0f}分")
    fh.close()
    print(f"\n完成: 成功 {ok} / 未解 {fail}  耗时 {(time.time()-t0)/60:.1f} 分")


if __name__ == "__main__":
    main()
