# -*- coding: utf-8 -*-
"""任务13 历史数据采集 v2 —— 用 getmatch AJAX 接口（最高效方案）。

接口（实测 2026-10-23，来自 stage.js 源码）：
    GET https://liansai.500.com/index.php?c=score&a=getmatch&stid=<stid>&round=<N>
    返回 JSON 数组，每场含：
      fid, round, stime("2019-07-27 02:30" 北京时间), status(5=完场)
      hname/gname(简体队名), hsxname/gsxname
      hscore/gscore(全场), hhalfscore/ghalfscore(半场)     ← 半场比分
      win/draw/lost(欧赔), handline(亚盘盘口), pan(盘路), color

赛季发现：
    https://liansai.500.com/zuqiu-<seasonId>/  页内含全部历史赛季链接
    <a href="/zuqiu-6018/" title="2020-2021 德乙">2020/2021赛季</a>

stid（阶段ID）：
    从赛季页 jifen-<stid>/ 的 id="match_stage" data-id="<stid>" 取，或用 URL 里的数字。

用法：
    python -X utf8 collect_500_history.py --url https://liansai.500.com/zuqiu-19952/ \
        --out out/bok500_hist.db --since 2019
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
CREATE TABLE IF NOT EXISTS seasons (
    season_id TEXT PRIMARY KEY, league_zh TEXT, season_label TEXT,
    stid TEXT, url TEXT, rounds INTEGER, discovered_utc TEXT
);
CREATE TABLE IF NOT EXISTS matches (
    fid        TEXT PRIMARY KEY,
    season_id  TEXT, league_zh TEXT, season_label TEXT, round INTEGER,
    kickoff_bj TEXT, kickoff_utc TEXT,
    home_zh    TEXT, away_zh TEXT,
    ft_home    INTEGER, ft_away INTEGER,
    ht_home    INTEGER, ht_away INTEGER,
    status     INTEGER, source TEXT DEFAULT '500.com'
);
CREATE TABLE IF NOT EXISTS odds (
    fid       TEXT NOT NULL,
    market    TEXT NOT NULL,       -- 1X2 / AH
    bookmaker TEXT NOT NULL,       -- 这里是 matchObj 里的"平均值/让球值"，非公司级
    open_h REAL, open_d REAL, open_a REAL,
    open_line TEXT,
    source    TEXT DEFAULT '500.com',
    PRIMARY KEY (fid, market, bookmaker)
);
"""


def fetch(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("gb18030", "replace")


def discover_seasons(entry_url):
    """从赛季页发现历史赛季 {season_id: (label, league)}"""
    html = fetch(entry_url)
    league = ""
    t = re.search(r"<title>【([^】]*)】", html)
    if t:
        parts = t.group(1).split("_")
        league = parts[1] if len(parts) > 1 else parts[0]

    out = {}
    for m in re.finditer(r'href="/zuqiu-(\d+)/"[^>]*title="([^"]*)"', html):
        sid, title = m.group(1), m.group(2)
        mm = re.match(r"(\d{4})[-/](\d{4})\s*(.*)", title)
        label = f"{mm.group(1)}/{mm.group(2)}" if mm else title
        lg = mm.group(3).strip() if mm and mm.group(3) else league
        out[sid] = (label, lg)
    # 当前赛季
    ms = re.search(r"seasonId\s*=\s*(\d+)", html)
    if ms:
        sm = re.search(r"【(\d{4}[/-]\d{4})", html)
        out.setdefault(ms.group(1), (sm.group(1).replace("-", "/") if sm else "", league))
    return out


def find_stid(season_url):
    """从赛季页找 jifen-<stid> 的 stid"""
    html = fetch(season_url)
    m = re.search(r"/zuqiu-\d+/jifen-(\d+)/", html)
    if m:
        return m.group(1)
    m2 = re.search(r'id="match_stage"[^>]*>(.*?)</div>', html, re.S)
    if m2:
        m3 = re.search(r'data-id="(\d+)"', m2.group(1))
        if m3:
            return m3.group(1)
    return None


def fetch_round(stid, rnd, retry=3):
    """取某一轮的全部比赛 JSON。"""
    for i in range(retry):
        raw = fetch(API.format(stid=stid, rnd=rnd))
        s = raw.strip()
        if s.startswith("["):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                pass
        if i < retry - 1:
            time.sleep(2 + i * 3)
    return []


def bj_to_utc(bj_str):
    try:
        dt = datetime.strptime(bj_str, "%Y-%m-%d %H:%M")
        return (dt - __import__("datetime").timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\out\bok500_hist.db")
    ap.add_argument("--since", type=int, default=2019, help="起始年份，默认 2019")
    ap.add_argument("--max-seasons", type=int, default=None)
    ap.add_argument("--max-rounds", type=int, default=None, help="测试：每季最多抓 N 轮")
    a = ap.parse_args()

    con = sqlite3.connect(a.out, timeout=60)
    con.executescript(DDL)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    seasons = discover_seasons(a.url)
    # 过滤起始年份
    sel = []
    for sid, (label, lg) in seasons.items():
        try:
            y = int(label.split("/")[0])
        except (ValueError, IndexError):
            continue
        if y >= a.since:
            sel.append((sid, label, lg))
    sel.sort(key=lambda x: x[1], reverse=True)
    if a.max_seasons:
        sel = sel[:a.max_seasons]
    print(f"发现 {len(seasons)} 个赛季，筛选({a.since}+) {len(sel)} 个")

    total_m = 0
    for sid, label, lg in sel:
        surl = f"https://liansai.500.com/zuqiu-{sid}/"
        stid = find_stid(surl)
        if not stid:
            print(f"  [{label}] 无 stid，跳过")
            continue
        # 先探轮数
        r1 = fetch_round(stid, 1)
        if not r1:
            print(f"  [{label}] 第1轮无数据，跳过")
            continue
        max_round = 46
        rounds = 0
        got_m = 0
        for rnd in range(1, max_round + 1):
            if a.max_rounds and rnd > a.max_rounds:
                break
            data = fetch_round(stid, rnd)
            if not data:
                break
            rounds += 1
            for d in data:
                fid = str(d.get("fid") or "")
                if not fid:
                    continue
                con.execute("""INSERT OR REPLACE INTO matches
                    (fid,season_id,league_zh,season_label,round,kickoff_bj,kickoff_utc,
                     home_zh,away_zh,ft_home,ft_away,ht_home,ht_away,status,source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (fid, sid, lg, label, d.get("round"), d.get("stime"),
                             bj_to_utc(d.get("stime") or ""),
                             d.get("hname"), d.get("gname"),
                             d.get("hscore"), d.get("gscore"),
                             d.get("hhalfscore"), d.get("ghalfscore"),
                             d.get("status"), "500.com"))
                if d.get("win") is not None:
                    con.execute("""INSERT OR REPLACE INTO odds
                        (fid,market,bookmaker,open_h,open_d,open_a,open_line,source)
                        VALUES (?,?,?,?,?,?,?,?)""",
                                (fid, "1X2", "match_avg", d.get("win"), d.get("draw"),
                                 d.get("lost"), None, "500.com"))
                if d.get("handline"):
                    con.execute("""INSERT OR REPLACE INTO odds
                        (fid,market,bookmaker,open_h,open_d,open_a,open_line,source)
                        VALUES (?,?,?,?,?,?,?,?)""",
                                (fid, "AH", "match_avg", None, None, None,
                                 d.get("handline"), "500.com"))
                got_m += 1
            time.sleep(0.5)
        con.execute("INSERT OR REPLACE INTO seasons VALUES (?,?,?,?,?,?,?)",
                    (sid, lg, label, stid, surl, rounds, now))
        con.commit()
        total_m += got_m
        print(f"  [{label}] stid={stid} {rounds} 轮 {got_m} 场")

    print(f"\n完成: 共 {total_m} 场")
    con.close()


if __name__ == "__main__":
    main()
