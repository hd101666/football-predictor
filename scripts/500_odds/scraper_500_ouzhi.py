# -*- coding: utf-8 -*-
"""500.com 百家欧指解析器 v2（修正 tr1/tr2 交替 + 公司名反查）。

关键修正：
  1. 公司行 class 是 tr1 / tr2 交替（不是只有 tr1）——v1 只匹配 tr1，漏掉一半公司
  2. 公司名在页面里被掩码成 "威***" / "立*" / "P*********"，必须用 cid 反查真名
  3. cid -> 名 的映射里，一批 cid 的标题就是"平均指数"（不同口径均值），要排除
"""

import re, subprocess, time, json, os

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CACHE = r"D:\cl\qqsj_v2\out\bok_500_cid_names.json"

# 已确认为"平均"类（非公司）的 cid，直接排除
AVG_CIDS = {1, 7, 10, 13, 14, 17, 19, 20, 21, 22, 23, 24, 25,
            67, 103, 127, 132, 140, 291, 322, 348, 453, 502, 651, 772, 863, 1259, 1320}

# 已知公司 cid（实测反查结果，避免重复请求）
KNOWN = {
    2: "立博", 3: "bet365", 4: "Interwetten", 5: "澳门彩票", 6: "伟德",
    8: "snai", 9: "易胜博", 11: "Bwin", 12: "Oddset", 15: "Eurobet",
    16: "10bet", 18: "必发", 275: "博天堂", 280: "皇冠",
    293: "威廉希尔", 1055: "Pinnacle平博", 1487: "888sport",
}


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def load_cache():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(m):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(m, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def resolve_name(cid, cache, allow_net=True):
    """cid -> 公司名。优先本地 KNOWN，其次缓存，最后联网反查。"""
    if cid in KNOWN:
        return KNOWN[cid]
    k = str(cid)
    if k in cache:
        return cache[k]
    if not allow_net:
        return f"cid{cid}"
    html = fetch(f"https://odds.500.com/ouzhi.php?cid={cid}", timeout=15)
    m = re.search(r"<title>([^<]*)</title>", html)
    name = m.group(1).split("-")[0].replace("指数", "").strip() if m else f"cid{cid}"
    cache[k] = name
    save_cache(cache)
    time.sleep(0.3)
    return name


# tr1/tr2 交替，两者都是公司行
COMP_BLOCK = re.compile(
    r'<tr[^>]*class="tr[12]"[^>]*id="(\d+)"[^>]*data-time="([^"]*)"[^>]*>(.*?)(?=<tr[^>]*class="tr[12]"[^>]*id=|\Z)',
    re.S)


def parse_ouzhi(match_id, cache=None, resolve=True, drop_avg=True):
    """解析一场比赛的百家欧指。

    返回 (rows, meta)
      rows: [{cid, bookmaker, open:[h,d,a], live:[h,d,a], data_time}]
      meta: {url, html_len}
    """
    cache = cache if cache is not None else load_cache()
    url = f"https://odds.500.com/fenxi/ouzhi-{match_id}.shtml"
    html = fetch(url)
    meta = {"url": url, "html_len": len(html), "company_rows": 0}
    if len(html) < 5000:
        return [], meta

    out = []
    for cid, dtime, body in COMP_BLOCK.findall(html):
        cid = int(cid)
        if drop_avg and cid in AVG_CIDS:
            continue
        tm = re.search(r'class="tb_plgs"\s+title="([^"]*)"', body)
        masked = tm.group(1) if tm else ""
        blocks = re.findall(r'<table[^>]*class="pl_table_data"[^>]*>(.*?)</table>', body, re.S)
        if not blocks:
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", blocks[0], re.S)
        parsed = []
        for row in rows[:2]:
            vals = re.findall(r">\s*(\d+\.\d{1,3})\s*<", row)
            if len(vals) >= 3:
                parsed.append([float(v) for v in vals[:3]])
        if len(parsed) < 2:
            continue
        name = resolve_name(cid, cache) if resolve else masked
        out.append({"cid": cid, "bookmaker": name, "masked": masked,
                    "open": parsed[0], "live": parsed[1], "data_time": dtime})
    meta["company_rows"] = len(out)
    return out, meta


if __name__ == "__main__":
    t0 = time.time()
    rows, meta = parse_ouzhi("1234567")
    print(f"公司数 {meta['company_rows']}  耗时 {time.time()-t0:.1f}s  html={meta['html_len']}\n")
    print(f"{'cid':>6} {'公司':14} {'初盘':24} {'即时':24} 数据时间")
    print("-" * 96)
    for r in rows:
        o = "/".join(f"{x:.2f}" for x in r["open"])
        l = "/".join(f"{x:.2f}" for x in r["live"])
        print(f"{r['cid']:>6} {r['bookmaker']:14} {o:24} {l:24} {r['data_time']}")

    print("\n=== 重点公司 ===")
    for w in ["澳门", "威廉希尔", "立博", "bet365", "Pinnacle", "伟德", "易胜博", "Interwetten", "皇冠", "Bwin"]:
        hit = [r for r in rows if w.lower() in r["bookmaker"].lower()]
        print(f"  {w:12} {'✅ ' + str([h['cid'] for h in hit]) if hit else '❌ 本场无'}")
