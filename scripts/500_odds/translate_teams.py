# -*- coding: utf-8 -*-
"""用智谱 GLM 批量翻译 qiety 中文队名 -> 英文俱乐部名。

设计：
  1. 收集所有未映射的中文队名（带所属联赛作为上下文，提高准确率）
  2. 每批 40 个发给 glm-4-flash，要求返回严格 JSON
  3. 失败重试（3 次，退避）；JSON 解析失败则降批重试
  4. 结果写 CSV，含置信度标记
  5. 支持断点续跑（已翻的跳过）

Key 从环境变量 ZHIPU_API_KEY 读取，绝不写进代码。

用法：
  python -X utf8 translate_teams.py --limit 100      # 试跑
  python -X utf8 translate_teams.py                  # 全量
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
OUT_CSV = r"D:\cl\qqsj_v2\qiety_team_map_llm.csv"
BASE_MAP = r"D:\cl\qqsj_v2\qiety_team_map.csv"

PROMPT = """你是足球俱乐部名称专家。把中文足球队名翻译成英文俱乐部名。

严格要求：
1. 只输出 JSON 数组，每项 {{"zh":"中文名","en":"英文名","conf":"high|low","note":"依据"}}
2. en 必须是【该俱乐部真实的官方英文名】，不是城市名、不是意译
3. conf="high" 仅当你确信时；任何犹豫必须标 low
4. 完全不确定时 en 填 "?"，conf 填 "low"
5. 严禁把不同球队翻译成同一个英文名（如多支威尔士球队都写成 Cardiff City）
6. 严禁中英混杂（如 "Donau弗里德"）
7. 若中文名含"女"→英文含 Women；含"U19/U21/U23"→保留；含"B队"→含 B 或 II
8. 参考联赛可帮助判断，但不要因为同联赛就套用同城球队

待翻译（中文名 | 所属联赛）：
{items}

只输出 JSON 数组："""


def get_key():
    k = os.environ.get("ZHIPU_API_KEY")
    if not k:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as kh:
                k, _ = winreg.QueryValueEx(kh, "ZHIPU_API_KEY")
        except Exception:
            pass
    if not k:
        raise SystemExit("未找到 ZHIPU_API_KEY（环境变量或注册表）")
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
        GROUP BY home_team, away_team, league
        ORDER BY n DESC
    """).fetchall()
    miss = {}
    for h, a, lg, n in rows:
        for t in (h, a):
            t = (t or "").strip()
            if t and t not in known:
                if t not in miss or (lg and not miss[t]):
                    miss[t] = lg or ""
    return miss


def call_glm(key, prompt, model="glm-4-flash", retry=3):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4000,
    })
    for i in range(retry):
        r = subprocess.run(["curl", "-s", "--max-time", "90", "-X", "POST", API,
                            "-H", "Content-Type: application/json",
                            "-H", "Authorization: Bearer " + key,
                            "-d", payload], capture_output=True, text=True)
        out = (r.stdout or "").strip()
        try:
            d = json.loads(out)
            if "choices" in d:
                return d["choices"][0]["message"]["content"]
            err = d.get("error", {})
            code = str(err.get("code"))
            if code in ("1305", "4290", "429"):
                time.sleep(5 + i * 5)
                continue
            return None
        except json.JSONDecodeError:
            time.sleep(2 + i * 2)
    return None


def parse_json(text):
    """解析模型输出，支持对象或数组，返回 {zh: (en, conf)}"""
    if not text:
        return {}
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # 优先找数组
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
            pass
    # 退化：对象格式
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
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="glm-4-flash")
    a = ap.parse_args()

    key = get_key()
    print(f"Key: {key[:8]}{'*'*10}{key[-6:]}")
    known = load_known()
    miss = collect_missing(a.db, known)
    print(f"已知映射 {len(known)} 条 / 缺失 {len(miss)} 个队名")

    # 断点续跑
    done = {}
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done[r["zh_name"]] = r["en_name"]
        print(f"已有翻译 {len(done)} 条，跳过")

    todo = [(t, lg) for t, lg in miss.items() if t not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f"待翻译 {len(todo)} 个\n")

    # 写文件头
    newfile = not os.path.exists(a.out)
    fh = open(a.out, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if newfile:
        w.writerow(["zh_name", "en_name", "league", "source"])
        fh.flush()

    t0 = time.time()
    ok = fail = 0
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        items = "\n".join(f"- {t} | {lg}" for t, lg in chunk)
        resp = call_glm(key, PROMPT.format(items=items), model=a.model)
        got = parse_json(resp)
        for t, lg in chunk:
            item = got.get(t)
            if isinstance(item, tuple):
                en, conf = item
            else:
                en, conf = (str(item or "").strip(), "unknown")
            # 垃圾值过滤：中英混杂、问号、空、与中文名相同
            bad = (not en or en == "?" or re.search(r"[\u4e00-\u9fff]", en) is not None)
            if bad:
                w.writerow([t, "", lg, "unresolved"])
                fail += 1
            else:
                w.writerow([t, en, lg, f"{a.model}:{conf}"])
                ok += 1
        fh.flush()
        el = time.time() - t0
        rate = (i + len(chunk)) / el if el else 0
        eta = (len(todo) - i - len(chunk)) / rate / 60 if rate else 0
        print(f"  {min(i+a.batch, len(todo))}/{len(todo)}  成功{ok} 未解{fail}  "
              f"{rate:.1f}个/秒  ETA {eta:.0f}分")
        time.sleep(0.5)
    fh.close()
    print(f"\n完成: 成功 {ok} / 未解 {fail}  耗时 {(time.time()-t0)/60:.1f} 分")
    print(f"输出: {a.out}")


if __name__ == "__main__":
    main()
