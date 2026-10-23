# -*- coding: utf-8 -*-
"""500.com 赛果解析器（任务13 二.3.c / 第三节 results）。

数据源：https://live.500.com/wanchang.php?e=YYYY-MM-DD  完场列表
        https://odds.500.com/fenxi/stat-<fid>.shtml     单场技术统计

完场列表行结构（实测 2026-10-21）：
  <tr id="a<fid>" ... gy="联赛,主,客" yy="繁体" ...>
      ... 比分 ... 半场 ...

stat 页含：全场比分、半场比分、角球、射门、控球率等技术统计。
"""
import re
import subprocess
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

WANCHANG = "https://live.500.com/wanchang.php?e={date}"
STAT = "https://odds.500.com/fenxi/stat-{fid}.shtml"


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def list_finished(date_str):
    """列出某日完场比赛。返回 [{fid, league, home, away, raw_row}]"""
    html = fetch(WANCHANG.format(date=date_str))
    out = []
    for m in re.finditer(r'<tr[^>]*id="a(\d+)"[^>]*>(.*?)(?=<tr[^>]*id="a\d+"|\Z)', html, re.S):
        fid, body = m.group(1), m.group(2)
        tag_m = re.search(r'<tr[^>]*id="a\d+"[^>]*>', m.group(0))
        tag = tag_m.group(0) if tag_m else ""

        def attr(n):
            mm = re.search(rf'\b{n}="([^"]*)"', tag)
            return mm.group(1) if mm else ""

        gy = attr("gy").split(",")
        out.append({
            "fid": fid,
            "league": gy[0] if gy else "",
            "home": gy[1] if len(gy) > 1 else "",
            "away": gy[2] if len(gy) > 2 else "",
            "lid": attr("lid"),
            "sid": attr("sid"),
            "raw_row": body[:1500],
        })
    return out


def _scores_from_row(body):
    """从完场列表行提取全场比分。

    实测结构（2026-10-21）：
      全场:  <td align="center" class="red">2 - 1</td>
      注意:  <div class="pk"> 里是【亚盘盘口】（如 "四球半"、"半球/一球"），不是半场比分，
             早期版本误当半场，导致 HT=(7,0) 这类不可能值。
             半场比分改从 stat 页的 "static_half" 行取（见 parse_stat）。
    """
    ft = None
    m = re.search(r'<td[^>]*class="red"[^>]*>\s*(\d+)\s*[-:]\s*(\d+)\s*</td>', body)
    if m:
        ft = (int(m.group(1)), int(m.group(2)))
    return ft


DETAIL = "https://live.500.com/detail.php?fid={fid}"


def parse_detail(fid):
    """从 live 详情页取全场+半场比分（实测结构）:

        <span class="score" style="color:red">2 - 1</span>
        <span class="score2">半场：2-1</span>
    """
    html = fetch(DETAIL.format(fid=fid))
    if len(html) < 5000:
        return None
    res = {"ft": None, "ht": None}

    m = re.search(r'<span class="score"[^>]*>\s*(\d+)\s*[-:]\s*(\d+)\s*</span>', html)
    if m:
        res["ft"] = (int(m.group(1)), int(m.group(2)))

    m2 = re.search(r'<span class="score2"[^>]*>\s*半场[：:]\s*(\d+)\s*[-:]\s*(\d+)\s*</span>', html)
    if m2:
        res["ht"] = (int(m2.group(1)), int(m2.group(2)))
    return res


def parse_stat(fid):
    """解析单场 stat 页：角球（static_corner）、射门等。返回 dict。

    实测结构：
      <tr def="static_corner">
          <td align="right">...</td><td>5</td><td>角球</td><td>2</td><td align="left">...</td>
      </tr>
      即：主队值在前，客队值在后，中间是项目名。
    """
    html = fetch(STAT.format(fid=fid))
    if len(html) < 30_000:
        return None
    res = {"corners_home": None, "corners_away": None, "ft": None}

    def stat_row(key):
        m = re.search(rf'<tr[^>]*def="{key}"[^>]*>(.*?)</tr>', html, re.S)
        if not m:
            return None
        vals = re.findall(r'<td[^>]*>\s*([\d.]+%?)\s*</td>', m.group(1))
        nums = [v for v in vals if not v.endswith("%")]
        if len(nums) >= 2:
            try:
                return int(float(nums[0])), int(float(nums[1]))
            except (ValueError, TypeError):
                return None
        return None

    c = stat_row("static_corner")
    if c:
        res["corners_home"], res["corners_away"] = c
    return res


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-10-21"
    rows = list_finished(date)
    print(f"{date} 完场 {len(rows)} 场\n")
    for r in rows[:8]:
        ft = _scores_from_row(r["raw_row"])
        print(f"  fid={r['fid']:9} {r['league']:6} {r['home'][:8]:8} vs {r['away'][:8]:8}  FT={ft}")

    if rows:
        print(f"\n=== stat 页（角球）测试 fid={rows[0]['fid']} ===")
        print(" ", parse_stat(rows[0]["fid"]))
