# -*- coding: utf-8 -*-
"""用 getmatch 接口回填「今日赛程」的半场比分。

背景：
  完场列表页的 <div class="pk"> 是亚盘盘口不是半场；
  stat 页无半场行；
  真正有半场的是 getmatch 接口的 hhalfscore/ghalfscore。

做法：
  1. 读 live.500.com 拿今日 fid（含 lid/sid）
  2. 对每个 fid 调 getmatch 接口（需要 stid，用 sid）
  3. 把 hhalfscore/ghalfscore/hscore/gscore 写入 independent 表 ht_backfill
  4. 结束后再并入 results（避免与 close 采集争锁）

用法：
  python -X utf8 backfill_ht.py --db out/bok500.db
"""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
API = "https://liansai.500.com/index.php?c=score&a=getmatch&stid={stid}&round={rnd}"

DDL = """
CREATE TABLE IF NOT EXISTS ht_backfill (
    fid TEXT PRIMARY KEY,
    round INTEGER,
    stime TEXT,
    home_zh TEXT, away_zh TEXT,
    ft_home INTEGER, ft_away INTEGER,
    ht_home INTEGER, ht_away INTEGER,
    status INTEGER,
    fetched_utc TEXT
);
"""


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def live_fids():
    """今日赛程 fid + lid/sid"""
    html = fetch("https://live.500.com/")
    out = []
    for m in re.finditer(r'<tr[^>]*\bfid="(\d+)"[^>]*>', html):
        tag = m.group(0)

        def attr(n):
            mm = re.search(rf'\b{n}="([^"]*)"', tag)
            return mm.group(1) if mm else ""

        out.append({"fid": m.group(1), "lid": attr("lid"), "sid": attr("sid")})
    return out


def getmatch(stid, rnd, retry=3):
    for i in range(retry):
        raw = fetch(API.format(stid=stid, rnd=rnd)).strip()
        if raw.startswith("["):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        if i < retry - 1:
            time.sleep(2 + i * 3)
    return []


def find_stid_for_fid(sid):
    """从赛季页找 stid（jifen-<stid>）"""
    for url in (f"https://liansai.500.com/zuqiu-{sid}/",):
        h = fetch(url)
        m = re.search(r"/zuqiu-\d+/jifen-(\d+)/", h)
        if m:
            return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj_v2\out\bok500.db")
    ap.add_argument("--rounds", default="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15",
                    help="要扫的轮次（今日赛程所在轮次）")
    a = ap.parse_args()

    con = sqlite3.connect(a.db, timeout=120)
    con.executescript(DDL)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 今日 fid 对应的 sid
    lf = live_fids()
    sids = {x["sid"] for x in lf if x["sid"]}
    print(f"今日 {len(lf)} 场，涉及 {len(sids)} 个 sid")

    # 今日 fid 集合，用于过滤
    want = {x["fid"] for x in lf}
    rounds = [int(x) for x in a.rounds.split(",")]

    found = 0
    stid_map = {}
    for sid in sids:
        stid = find_stid_for_fid(sid)
        if not stid:
            continue
        stid_map[sid] = stid
        print(f"  sid={sid} -> stid={stid}")
        for rnd in rounds:
            data = getmatch(stid, rnd)
            if not data:
                continue
            for d in data:
                fid = str(d.get("fid") or "")
                if fid not in want:
                    continue
                # status: 5=完场。未开赛/进行中的 0-0 是占位值，不能当比分存
                if d.get("status") != 5:
                    continue
                con.execute("""INSERT OR REPLACE INTO ht_backfill
                    (fid,round,stime,home_zh,away_zh,ft_home,ft_away,ht_home,ht_away,status,fetched_utc)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (fid, d.get("round"), d.get("stime"),
                             d.get("hname"), d.get("gname"),
                             d.get("hscore"), d.get("gscore"),
                             d.get("hhalfscore"), d.get("ghalfscore"),
                             d.get("status"), now))
                found += 1
            time.sleep(0.4)
    con.commit()
    print(f"回填 {found} 场半场数据")
    con.close()


if __name__ == "__main__":
    main()
