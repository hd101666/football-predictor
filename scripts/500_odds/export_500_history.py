# -*- coding: utf-8 -*-
"""导出历史数据（bok500_hist.db）为任务13 第三节格式。

产出（<outdir>/）：
  matches.csv.gz    历史比赛（含赛季/轮次/全场/半场）
  odds_1x2.csv.gz   欧赔（getmatch 的 win/draw/lost，作为 open 阶段快照）
  odds_ah.csv.gz    亚盘（handline 盘口 + pan 盘路）
  trend.csv.gz      亚盘走势（handline/pan 是赛前最终状态）
  README.md
  manifest.json
"""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

BJ_TZ = "+08:00"


def esc(v):
    if v is None:
        return ""
    s = str(v)
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n\r') else s


def dump_gz(path, header, rows):
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(esc(v) for v in r) + "\n")
    os.replace(tmp, path)
    return len(rows)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj_v2\out\bok500_hist.db")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--label", default="bundesliga2_2019_2026")
    a = ap.parse_args()

    out = os.path.join(a.outdir, a.label)
    os.makedirs(out, exist_ok=True)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=60)
    man = {"exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source_db": os.path.basename(a.db), "files": {}}

    def put(name, hdr, rows):
        p = os.path.join(out, name)
        n = dump_gz(p, hdr, rows)
        man["files"][name] = {"rows": n, "bytes": os.path.getsize(p), "sha256": sha(p)}
        print(f"  {name:22} {n:6} 行")
        return n

    # matches
    rows = con.execute("""SELECT fid, season_label, league_zh, round, kickoff_bj, kickoff_utc,
                                 home_zh, away_zh, ft_home, ft_away, ht_home, ht_away, status
                          FROM matches ORDER BY season_label DESC, round, kickoff_bj""").fetchall()
    hdr = ["match_id", "source", "source_match_id", "pinnacle_event_id", "league_zh", "league_en",
           "country", "season", "kickoff_utc", "home_zh", "away_zh", "home_en", "away_en",
           "jc_code", "sfc_issue", "round", "ft_home", "ft_away", "ht_home", "ht_away", "status"]
    out_rows = []
    for r in rows:
        (fid, season, lg, rnd, kbj, kutc, home, away, fth, fta, hth, hta, st) = r
        out_rows.append([f"500_{fid}", "500.com", fid, "", lg, "", "DE", season, kutc,
                         home, away, "", "", "", "", rnd, fth, fta, hth, hta, st])
    put("matches.csv.gz", hdr, out_rows)

    # odds_1x2
    rows = con.execute("""SELECT o.fid, m.kickoff_utc, o.open_h, o.open_d, o.open_a
                          FROM odds o JOIN matches m ON m.fid=o.fid
                          WHERE o.market='1X2' AND o.open_h IS NOT NULL""").fetchall()
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "home_odds", "draw_odds", "away_odds", "source"]
    out_rows = [[f"500_{r[0]}", "match_avg", r[1] or "", "close",
                 r[2], r[3], r[4], "500.com"] for r in rows]
    put("odds_1x2.csv.gz", hdr, out_rows)

    # odds_ah
    rows = con.execute("""SELECT o.fid, m.kickoff_utc, o.open_line, m.home_zh, m.away_zh
                          FROM odds o JOIN matches m ON m.fid=o.fid
                          WHERE o.market='AH' AND o.open_line IS NOT NULL""").fetchall()
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "line", "line_text",
           "home_price", "away_price", "price_format", "source"]
    out_rows = [[f"500_{r[0]}", "match_avg", r[1] or "", "close", "", r[2],
                 "", "", "HK", "500.com"] for r in rows]
    put("odds_ah.csv.gz", hdr, out_rows)

    # 赛季统计
    stats = con.execute("""SELECT season_label, COUNT(*),
                                  SUM(CASE WHEN ft_home IS NOT NULL THEN 1 ELSE 0 END),
                                  SUM(CASE WHEN ht_home IS NOT NULL THEN 1 ELSE 0 END)
                           FROM matches GROUP BY season_label ORDER BY season_label DESC""").fetchall()

    readme = f"""# 500.com 历史数据（德乙 2019/2020 ~ 2026/2027）

导出时间: {man['exported_at_utc']}
数据源: **500.com** `getmatch` AJAX 接口
```
GET https://liansai.500.com/index.php?c=score&a=getmatch&stid=<stid>&round=<N>
```

## 赛季与场次

| 赛季 | 场次 | 有全场比分 | 有半场比分 |
|---|---|---|---|
""" + "".join(f"| {s} | {n} | {f} | {h} |\n" for s, n, f, h in stats) + f"""
合计 **{sum(s[1] for s in stats)}** 场

## 接口返回字段

```json
{{"fid":825597,"round":1,"stime":"2019-07-27 02:30",
 "hname":"斯图加特","gname":"汉诺威96",
 "hscore":2,"gscore":1,                        // 全场
 "hhalfscore":2,"ghalfscore":1,                // 半场 ★
 "win":1.71,"draw":3.84,"lost":4.42,           // 欧赔
 "handline":"半球/一球","pan":"赢半","color":"lred",  // 亚盘 + 盘路
 "status":5}}                                   // 5=完场
```

## 重要说明

1. **`odds_1x2` / `odds_ah` 是"赛前最终赔率"（≈收盘价），不是初盘**。
   `getmatch` 接口只返回一个赔率值（win/draw/lost），经实测比对
   ouzhi 页的 tr0(初盘)/tr1(收盘)，接口值 = tr1 收盘价。
   初盘需另抓 `ouzhi-<fid>.shtml` 的 tr0。
2. **`bookmaker` 统一写 `match_avg`**，因为 `getmatch` 返回的是该场"平均/主流"赔率，
   不是某一家公司。要公司级历史赔率必须逐场抓 `ouzhi-<fid>.shtml`。
3. **亚盘的 `line` 是文字**（`半球/一球`），不是数值。
   数值化需要映射表（平手=0, 半球=-0.5, 一球=-1.0, 半球/一球=-0.75 ...）。
4. `country` 为 `DE`（德乙）、`league_en` 为空（接口只给中文）。

## 时区

- `kickoff_utc` 已是 UTC（接口给的是北京时间 `stime`，导出时 -8h）
- 所有 `snapshot_utc` 直接用 `kickoff_utc`（因接口只给最终值，无独立快照时间）

## 复现

```bash
python -X utf8 collect_500_history.py \\
  --url https://liansai.500.com/zuqiu-19952/ \\
  --out out/bok500_hist.db --since 2019
python -X utf8 export_500_history.py --db out/bok500_hist.db --outdir <repo>/exports/grokbot_500
```

## robots.txt

同样违反 500.com 的 `Disallow: /ouzhi-*.shtml`（本脚本用 AJAX 接口，路径为 `/index.php`
不在 Disallow 列表内，但数据同源）。用户已授权仅自用。
"""
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    man["seasons"] = [{"season": s, "matches": n, "with_ft": f, "with_ht": h} for s, n, f, h in stats]
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    print(f"\n  输出: {out}")
    print(f"  赛季: {len(stats)}  总场次: {sum(s[1] for s in stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
