# -*- coding: utf-8 -*-
"""500.com 亚盘（yazhi）+ 大小球（daxiao）解析器。

实测结构（2026-10-23，fid=1430753）：
  <tr class="tr1" id="293">
    <td class="tb_plgs" row="1"> ... title="威***" ... </td>
    <td>  <table class="pl_table_data">        ← 初盘
            <tbody><tr>
              <td class="ying">1.000↑</td>          ← 主队水位（香港盘，0.7~1.0）
              <td ref="0.250">受平手/半球<font>降</font></td>   ← 盘口线，ref=数值
              <td>0.730</td>                        ← 客队水位
            </tr></tbody>
          </table>
          <time>10-23 11:48</time>              ← 初盘时间
    </td>
    <td>  <table class="pl_table_data">        ← 即时盘（同上结构）
          </table> <time>10-17 23:26</time>
    </td>

盘口 ref 语义（主队视角，任务要求 line 为主队视角如 -0.75）：
    500.com 的 ref 是"主队受让值"——正数表示主队受让（弱队），
    任务要求"主队视角 -0.75"，因此 line = -ref。
    示例 ref=0.250 → 受平手/半球 → line = -0.25
         ref=0.000 → 平手         → line = 0.00
         ref=-0.5  → 让半球       → line = +0.50

大小球 ref 语义：ref 为盘口线（如 2.5 球），无正负。
"""
import re
import subprocess
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

MIN_HTML = 120_000

COMP_BLOCK = re.compile(
    r'<tr[^>]*class="tr[12]"[^>]*id="(\d+)"[^>]*>(.*?)(?=<tr[^>]*class="tr[12]"[^>]*id=|\Z)',
    re.S)


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def _num(s):
    """从 '1.000↑' / '0.730' 提取浮点。"""
    m = re.search(r"(\d+\.\d+)", s or "")
    return float(m.group(1)) if m else None


def _ref_to_line(ref):
    """500.com 的 ref（主队受让值）→ 任务要求的 line（主队视角）。

    ref=0.25 表示主队受让平手/半球 → line = -0.25
    ref=0.00 平手                  → line = 0.00
    ref=-0.5 主队让半球            → line = +0.50
    """
    if ref is None:
        return None
    return round(-ref, 3)


def parse_yazhi(match_id, cache=None, resolve=True, drop_avg=True):
    """解析亚盘。返回 [{cid, bookmaker, open:{line,home,away}, live:{...}, times}]"""
    import sys
    sys.path.insert(0, r"D:\cl\qqsj_v2")
    from scraper_500_ouzhi import resolve_name, load_cache, AVG_CIDS, KNOWN as KNOWN_SAFE

    cache = cache if cache is not None else load_cache()
    url = f"https://odds.500.com/fenxi/yazhi-{match_id}.shtml"
    html = fetch(url)
    meta = {"url": url, "html_len": len(html)}
    if len(html) < MIN_HTML:
        return [], meta

    out = []
    for cid_s, body in COMP_BLOCK.findall(html):
        cid = int(cid_s)
        if drop_avg and cid in AVG_CIDS:
            continue
        tm = re.search(r'title="([^"]*)"', body)
        masked = tm.group(1) if tm else ""
        # cid 不在已知公司表里的，反查后若仍是"平均/均值"类，跳过
        if resolve and cid not in KNOWN_SAFE:
            nm = resolve_name(cid, cache)
            if "平均" in nm or "均值" in nm or not nm or nm.startswith("cid"):
                continue
        # 每个公司有 2 张 pl_table_data：初盘、即时盘
        blocks = re.findall(r'<table[^>]*class="pl_table_data"[^>]*>(.*?)</table>', body, re.S)
        if len(blocks) < 2:
            continue
        times = re.findall(r"<time>([^<]*)</time>", body)

        def one(block):
            ref = re.search(r'ref="(-?\d+\.\d+)"', block)
            vals = re.findall(r"<td[^>]*>\s*([\d.]+)(?:[↑↓])?\s*</td>", block)
            if not ref or len(vals) < 2:
                return None
            return {"line": _ref_to_line(float(ref.group(1))),
                    "home": float(vals[0]), "away": float(vals[-1])}

        o = one(blocks[0])
        l = one(blocks[1])
        if not o:
            continue
        name = resolve_name(cid, cache) if resolve else masked
        if "平均" in name or "均值" in name:
            continue                      # 平均类不是真公司
        out.append({"cid": cid, "bookmaker": name,
                    "open": o, "live": l or o,
                    "open_time": times[0] if len(times) > 0 else "",
                    "live_time": times[1] if len(times) > 1 else ""})
    meta["company_rows"] = len(out)
    return out, meta


def parse_daxiao(match_id, cache=None, resolve=True, drop_avg=True):
    """解析大小球。结构同亚盘，但 line 就是盘口线（如 2.5），无正负。"""
    import sys
    sys.path.insert(0, r"D:\cl\qqsj_v2")
    from scraper_500_ouzhi import resolve_name, load_cache, AVG_CIDS, KNOWN as KNOWN_SAFE

    cache = cache if cache is not None else load_cache()
    url = f"https://odds.500.com/fenxi/daxiao-{match_id}.shtml"
    html = fetch(url)
    meta = {"url": url, "html_len": len(html)}
    if len(html) < MIN_HTML:
        return [], meta

    out = []
    for cid_s, body in COMP_BLOCK.findall(html):
        cid = int(cid_s)
        if drop_avg and cid in AVG_CIDS:
            continue
        tm = re.search(r'title="([^"]*)"', body)
        masked = tm.group(1) if tm else ""
        blocks = re.findall(r'<table[^>]*class="pl_table_data"[^>]*>(.*?)</table>', body, re.S)
        if len(blocks) < 2:
            continue
        times = re.findall(r"<time>([^<]*)</time>", body)

        def one(block):
            ref = re.search(r'ref="(-?\d+\.\d+)"', block)
            vals = re.findall(r"<td[^>]*>\s*([\d.]+)(?:[↑↓])?\s*</td>", block)
            if not ref or len(vals) < 2:
                return None
            # 大小球没有主客让球概念，ref 就是盘口总进球线（如 3.25），不能取负
            return {"line": abs(round(float(ref.group(1)), 3)),
                    "over": float(vals[0]), "under": float(vals[-1])}

        o = one(blocks[0])
        l = one(blocks[1])
        if not o:
            continue
        name = resolve_name(cid, cache) if resolve else masked
        if "平均" in name or "均值" in name:
            continue                      # 平均类不是真公司，任务要求公司级赔率
        out.append({"cid": cid, "bookmaker": name,
                    "open": o, "live": l or o,
                    "open_time": times[0] if len(times) > 0 else "",
                    "live_time": times[1] if len(times) > 1 else ""})
    meta["company_rows"] = len(out)
    return out, meta


if __name__ == "__main__":
    import sys
    fid = sys.argv[1] if len(sys.argv) > 1 else "1430753"

    t0 = time.time()
    ya, m1 = parse_yazhi(fid)
    print(f"=== 亚盘 fid={fid}  {len(ya)} 家  {time.time()-t0:.1f}s ===")
    for r in ya:
        o, l = r["open"], r["live"]
        print(f"  {r['bookmaker']:12} 初 线{o['line']:+.2f} {o['home']:.3f}/{o['away']:.3f}  "
              f"即 线{l['line']:+.2f} {l['home']:.3f}/{l['away']:.3f}  {r['open_time']}")

    t0 = time.time()
    da, m2 = parse_daxiao(fid)
    print(f"\n=== 大小球 fid={fid}  {len(da)} 家  {time.time()-t0:.1f}s ===")
    for r in da:
        o, l = r["open"], r["live"]
        print(f"  {r['bookmaker']:12} 初 线{o['line']:.2f} 大{o['over']:.3f}/小{o['under']:.3f}  "
              f"即 线{l['line']:.2f} 大{l['over']:.3f}/小{l['under']:.3f}  {r['open_time']}")
