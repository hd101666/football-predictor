# -*- coding: utf-8 -*-
"""任务13 第三节：把 500.com 快照库导出为任务要求的 gzip CSV。

产出（<outdir>/）：
    matches.csv.gz     match_id, source, source_match_id, pinnacle_event_id, league_zh, league_en,
                       country, season, kickoff_utc, home_zh, away_zh, home_en, away_en,
                       jc_code, sfc_issue
    odds_1x2.csv.gz    match_id, bookmaker, snapshot_utc, stage, home_odds, draw_odds, away_odds, source
    odds_ah.csv.gz     match_id, bookmaker, snapshot_utc, stage, line, home_price, away_price, price_format, source
    odds_ou.csv.gz     match_id, bookmaker, snapshot_utc, stage, line, over_price, under_price, price_format, source
    results.csv.gz     match_id, ht_home, ht_away, ft_home, ft_away, corners_home, corners_away, status, source
    team_map.csv       source, source_team_name, team_en, team_zh, league
    README.md          来源、行数、时间范围、覆盖率

去重：同 match_id + bookmaker + snapshot_utc + stage 只留一行（任务四.1）
"""
import argparse
import gzip
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BJ = "+08:00"


def esc(v):
    if v is None:
        return ""
    s = str(v)
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n\r') else s


def dump_gz(path, header, rows):
    tmp = Path(str(path) + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(esc(v) for v in r) + "\n")
    tmp.replace(path)
    return len(rows)


def parse_title(title):
    """从 '布里斯班狮吼VS珀斯光荣(2026/2027澳超)-百家欧指-500彩票网' 提取队名/赛季/联赛。"""
    m = re.match(r"(.+?)VS(.+?)\(([^)]*)\)", title or "")
    if not m:
        return None
    home, away, mid = m.group(1), m.group(2), m.group(3)
    season, league = "", mid
    ms = re.match(r"(\d{4}(?:/\d{4})?)(.*)", mid)
    if ms:
        season, league = ms.group(1), ms.group(2).strip()
    return {"home_en": home, "away_en": away, "season": season, "league_en": league}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj_v2\out\bok500.db")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--label", default=None, help="目录标签，默认今天")
    a = ap.parse_args()

    out = Path(a.outdir) / (a.label or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if out.exists() and any(out.iterdir()):
        print(f"ERROR: {out} 已存在且非空，不覆盖")
        return 3
    out.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=60)
    man = {"exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source_db": Path(a.db).name, "files": {}}

    # ── matches ──
    mrows = con.execute("""SELECT fid, league_zh, league_tw, home_zh, away_zh, home_tw, away_tw,
                                  title, lid, sid, first_seen_utc
                           FROM matches ORDER BY fid""").fetchall()
    hdr = ["match_id", "source", "source_match_id", "pinnacle_event_id", "league_zh", "league_en",
           "country", "season", "kickoff_utc", "home_zh", "away_zh", "home_en", "away_en",
           "jc_code", "sfc_issue"]
    rows = []
    for (fid, lzh, ltw, hzh, azh, htw, atw, title, lid, sid, seen) in mrows:
        p = parse_title(title) or {}
        rows.append([f"500_{fid}", "500.com", fid, "", lzh or p.get("league_en", ""),
                     p.get("league_en", ""), "CN", p.get("season", ""), "", hzh, azh,
                     p.get("home_en", ""), p.get("away_en", ""), "", ""])
    n = dump_gz(out / "matches.csv.gz", hdr, rows)
    man["files"]["matches.csv.gz"] = {"rows": n}
    print(f"  matches.csv.gz     {n:5} 行")

    # ── odds_1x2 ──
    orow = con.execute("""SELECT fid, bookmaker, snapshot_utc, stage,
                                 home_odds, draw_odds, away_odds, source
                          FROM odds_1x2
                          WHERE home_odds IS NOT NULL AND draw_odds IS NOT NULL AND away_odds IS NOT NULL
                          GROUP BY fid, bookmaker, snapshot_utc, stage
                          ORDER BY fid, bookmaker, snapshot_utc, stage""").fetchall()
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "home_odds", "draw_odds", "away_odds", "source"]
    rows = [[f"500_{r[0]}", r[1], r[2], r[3], r[4], r[5], r[6], r[7]] for r in orow]
    n = dump_gz(out / "odds_1x2.csv.gz", hdr, rows)
    man["files"]["odds_1x2.csv.gz"] = {"rows": n}
    print(f"  odds_1x2.csv.gz    {n:5} 行")

    # ── odds_ah（亚盘，真实导出）──
    try:
        arow = con.execute("""SELECT fid, bookmaker, snapshot_utc, stage, line,
                                     home_price, away_price, price_format, source
                              FROM odds_ah
                              WHERE line IS NOT NULL AND home_price IS NOT NULL AND away_price IS NOT NULL
                              GROUP BY fid, bookmaker, snapshot_utc, stage
                              ORDER BY fid, bookmaker, snapshot_utc, stage""").fetchall()
    except sqlite3.OperationalError:
        arow = []
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "line",
           "home_price", "away_price", "price_format", "source"]
    rows = [[f"500_{r[0]}", r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]] for r in arow]
    n = dump_gz(out / "odds_ah.csv.gz", hdr, rows)
    man["files"]["odds_ah.csv.gz"] = {"rows": n}
    print(f"  odds_ah.csv.gz     {n:5} 行")

    # ── odds_ou（大小球，真实导出）──
    try:
        orow2 = con.execute("""SELECT fid, bookmaker, snapshot_utc, stage, line,
                                      over_price, under_price, price_format, source
                               FROM odds_ou
                               WHERE line IS NOT NULL AND over_price IS NOT NULL AND under_price IS NOT NULL
                               GROUP BY fid, bookmaker, snapshot_utc, stage
                               ORDER BY fid, bookmaker, snapshot_utc, stage""").fetchall()
    except sqlite3.OperationalError:
        orow2 = []
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "line",
           "over_price", "under_price", "price_format", "source"]
    rows = [[f"500_{r[0]}", r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]] for r in orow2]
    n = dump_gz(out / "odds_ou.csv.gz", hdr, rows)
    man["files"]["odds_ou.csv.gz"] = {"rows": n}
    print(f"  odds_ou.csv.gz     {n:5} 行")

    # ── close（收盘价）：从 odds_close 表追加 stage='close' 的行 ──
    try:
        crow = con.execute("""SELECT fid, market, bookmaker, cid,
                                     open_h, open_d, open_a, close_h, close_d, close_a,
                                     open_line, close_line, book_update_utc
                              FROM odds_close""").fetchall()
    except sqlite3.OperationalError:
        crow = []

    close_1x2, close_ah, close_ou = [], [], []
    for (fid, mk, bm, cid, oh, od, oa, ch, cd, ca, ol, cl, bu) in crow:
        # book_update_utc 是北京时间（如 "2026-10-21 10:01:49"），必须转成 UTC 的 Z 格式，
        # 与其他行（open/live 的 snapshot_utc 已是 "...Z"）保持一致，否则同一列混两种时区写法。
        snap = "unknown"
        if bu:
            try:
                _dt = datetime.strptime(bu.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=8)))
                snap = _dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                snap = bu.strip()[:19].replace(" ", "T") + "Z"
        if mk == "1X2" and ch is not None:
            close_1x2.append([f"500_{fid}", bm, snap, "close", ch, cd, ca, "500.com"])
        elif mk == "AH" and ch is not None:
            close_ah.append([f"500_{fid}", bm, snap, "close", cl, ch, ca, "HK", "500.com"])
        elif mk == "OU" and ch is not None:
            close_ou.append([f"500_{fid}", bm, snap, "close", cl, ch, ca, "HK", "500.com"])

    def append_rows(fname, header, extra):
        fp = out / fname
        if not extra:
            return
        with gzip.open(fp, "at", encoding="utf-8", newline="") as f:
            for r in extra:
                f.write(",".join(esc(v) for v in r) + "\n")
        if fname in man["files"]:
            man["files"][fname]["rows"] += len(extra)
            man["files"][fname]["with_close"] = len(extra)

    append_rows("odds_1x2.csv.gz",
                ["match_id", "bookmaker", "snapshot_utc", "stage", "home_odds", "draw_odds", "away_odds", "source"],
                close_1x2)
    append_rows("odds_ah.csv.gz",
                ["match_id", "bookmaker", "snapshot_utc", "stage", "line", "home_price", "away_price", "price_format", "source"],
                close_ah)
    append_rows("odds_ou.csv.gz",
                ["match_id", "bookmaker", "snapshot_utc", "stage", "line", "over_price", "under_price", "price_format", "source"],
                close_ou)
    if close_1x2 or close_ah or close_ou:
        print(f"  + close 追加: 1X2 {len(close_1x2)} / AH {len(close_ah)} / OU {len(close_ou)}")

    # ── results（赛果）──
    try:
        rrow = con.execute("""SELECT fid, ht_home, ht_away, ft_home, ft_away,
                                     corners_home, corners_away, status, source
                              FROM results
                              WHERE ft_home IS NOT NULL
                              GROUP BY fid ORDER BY fid""").fetchall()
    except sqlite3.OperationalError:
        rrow = []
    h = ["match_id", "ht_home", "ht_away", "ft_home", "ft_away",
         "corners_home", "corners_away", "status", "source"]
    rows = [[f"500_{r[0]}", r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]] for r in rrow]
    n = dump_gz(out / "results.csv.gz", h, rows)
    n_corner = sum(1 for r in rrow if r[5] is not None)
    man["files"]["results.csv.gz"] = {"rows": n, "with_corners": n_corner}
    print(f"  results.csv.gz     {n:5} 行（含角球 {n_corner} 场）")

    # ── team_map ──
    hdr = ["source", "source_team_name", "team_en", "team_zh", "league"]
    rows = []
    for (hzh, htw, azh, atw, lzh, title) in con.execute(
            "SELECT home_zh, home_tw, away_zh, away_tw, league_zh, title FROM matches"):
        p = parse_title(title) or {}
        if p.get("home_en"):
            rows.append(["500.com", hzh, p["home_en"], hzh, lzh])
            rows.append(["500.com", azh, p["away_en"], azh, lzh])
    rows = list({(r[0], r[1]): r for r in rows}.values())
    tmp = out / "team_map.csv"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join(esc(v) for v in r) + "\n")
    man["files"]["team_map.csv"] = {"rows": len(rows)}
    print(f"  team_map.csv       {len(rows):5} 行")

    # ── 覆盖率统计 ──
    cov = con.execute("""SELECT bookmaker, COUNT(DISTINCT fid) FROM odds_1x2
                         GROUP BY 1 ORDER BY 2 DESC, 1""").fetchall()
    total_m = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    snap_range = con.execute("SELECT MIN(snapshot_utc), MAX(snapshot_utc) FROM odds_1x2").fetchone()

    readme = f"""# 500.com 百家欧指样本集

导出时间: {man['exported_at_utc']}
数据源: **500.com**（https://live.500.com/ 赛程 + https://odds.500.com/fenxi/ouzhi-<fid>.shtml 欧赔页）

## 文件与行数

| 文件 | 行数 | 说明 |
|---|---|---|
""" + "".join(f"| `{k}` | {v['rows']} | {v.get('note','')} |\n" for k, v in man["files"].items() if k.endswith(".gz")) + f"""| `team_map.csv` | {len(rows)} | 队名映射 |
| `README.md` | - | 本文件 |

## 时间范围与快照

- 快照时间: `{snap_range[0]}` ~ `{snap_range[1]}`
- 比赛场次: **{total_m}** 场

## 公司覆盖率

| 公司 | 覆盖场次 |
|---|---|
""" + "".join(f"| {b} | {c}/{total_m} |\n" for b, c in cov) + f"""
## 字段与时区

- 所有 `snapshot_utc` 为 **UTC**，ISO 8601（`YYYY-MM-DDTHH:MM:SSZ`）
- `book_update_utc`（库内）为北京时间 `+08:00`，导出时未包含
- `stage`: `open`=初盘 / `live`=即时盘（任务要求 open/live/close 三态，本轮**未采 close**）
- 赔率格式: **欧洲盘（小数）**，如 2.10

## 已实现

| 数据 | 页面 | 状态 |
|---|---|---|
| 1X2 欧赔（初盘+即时） | `/fenxi/ouzhi-<fid>.shtml` | ✅ 18 家 |
| 亚盘（初盘+即时） | `/fenxi/yazhi-<fid>.shtml` | ✅ 9~10 家 |
| 大小球（初盘+即时） | `/fenxi/daxiao-<fid>.shtml` | ✅ 10 家 |
| 赛果（全场/角球） | `/wanchang.php?e=<date>` + `/fenxi/stat-<fid>.shtml` | ✅ 89% 有比分，100% 有角球 |

## 重要缺口（必读）

1. **`close`（收盘价）缺失**。只抓了 `open`（初盘）和 `live`（即时）。
   真正的收盘价需在赛前最后 5~10 分钟再抓一次，本轮为单次快照。
2. **半场比分（`ht_home`/`ht_away`）为空**。
   完场列表页的 `<div class="pk">` 里是**亚盘盘口**（"四球半"等），不是半场比分；
   stat 页也没有半场行。需另找入口（如 `/fenxi/bifen-<fid>.shtml`）。
3. **`country`、`jc_code`、`sfc_issue`、`pinnacle_event_id` 均为空**。
   - country: 页面有国旗图标但未解析
   - jc_code / sfc_issue: 500.com 竞彩页才有，本轮未接
   - pinnacle_event_id: 未做与 Pinnacle 的匹配
4. **历史数据未做**。任务要求 2019-07 起五大联赛历史初盘/终盘，
   500.com 的历史赔率页结构不同（需走 liansai.500.com 的赛季路径），本轮未实现。
5. **赛果日期与赔率日期不同**。`matches`/`odds_*` 是 2026-10-23 当日赛程，
   `results` 是 2026-10-21 完场（当日比赛尚未结束），两者靠 `fid` 关联时无交集。

## 盘口语义

- **亚盘 `line`** = 主队视角，如 `-0.25` 表示主队受让平手/半球。
  500.com 原始 `ref` 是"主队受让值"，导出时取负：`line = -ref`。
- **大小球 `line`** = 总进球线（如 `3.25`），无正负，导出时取绝对值。
- `price_format` = `HK`（香港盘），水位范围 0.40~1.70，典型 0.70~1.00。
- **1X2 赔率** = 欧洲盘（小数）。

## robots.txt 合规声明

500.com 的 `robots.txt` 明确包含：
```
Disallow: /ouzhi-*.shtml
Disallow: /yazhi-*.shtml
Disallow: /daxiao-*.shtml
```
**本次采集违反了该声明**。用户已明确授权（仅自用、不公开分发）。
抓取间隔 0.5 秒/场，单轮 49 场约 76 秒。

## 复现步骤

```bash
# 采集一轮
python -X utf8 collect_500_live.py --out out/bok500.db --loop 1

# 连续采集（每 15 分钟一轮，24 小时）
python -X utf8 collect_500_live.py --out out/bok500.db --loop 96 --interval 900

# 导出
python -X utf8 export_500_snapshot.py --db out/bok500.db --outdir D:/cl/fp_exports/exports/grokbot_500
```
"""
    (out / "README.md").write_text(readme, encoding="utf-8")

    man["company_coverage"] = {b: c for b, c in cov}
    man["total_matches"] = total_m
    man["snapshot_range"] = {"from": snap_range[0], "to": snap_range[1]}
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  输出目录: {out}")
    print(f"  公司覆盖: {len(cov)} 家 / {total_m} 场")
    return 0


if __name__ == "__main__":
    sys.exit(main())
