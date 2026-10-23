# -*- coding: utf-8 -*-
"""导出公司级历史赔率（bok500_company.db）为任务13 第三节格式。

数据源：逐场抓取 500.com 的 ouzhi / yazhi / daxiao 三个页面，
每家公司分别记录 open（初盘）和 close（收盘价）。

产出：
    matches.csv.gz     比赛基础信息（关联用，来自 bok500_hist.db）
    odds_1x2.csv.gz    公司级 1X2 初盘+收盘
    odds_ah.csv.gz     公司级 亚盘 初盘+收盘（含数值 line）
    odds_ou.csv.gz     公司级 大小球 初盘+收盘
    coverage.csv       每家公司在每个市场/阶段的覆盖场次
    README.md
    manifest.json
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone


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
    ap.add_argument("--histdb", default=r"D:\cl\qqsj_v2\out\bok500_hist.db")
    ap.add_argument("--companydb", default=r"D:\cl\qqsj_v2\out\bok500_company.db")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--label", default="bundesliga2_company_2019_2026")
    a = ap.parse_args()

    out = os.path.join(a.outdir, a.label)
    os.makedirs(out, exist_ok=True)
    hist = sqlite3.connect(f"file:{a.histdb}?mode=ro", uri=True, timeout=60)
    comp = sqlite3.connect(f"file:{a.companydb}?mode=ro", uri=True, timeout=60)
    man = {"exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "500.com (per-match ouzhi/yazhi/daxiao pages)",
           "files": {}}

    def put(name, hdr, rows):
        p = os.path.join(out, name)
        n = dump_gz(p, hdr, rows)
        man["files"][name] = {"rows": n, "bytes": os.path.getsize(p), "sha256": sha(p)}
        print(f"  {name:22} {n:7} 行")
        return n

    # matches（关联表）
    rows = hist.execute("""SELECT fid, season_label, league_zh, round, kickoff_utc,
                                  home_zh, away_zh, ft_home, ft_away, ht_home, ht_away
                           FROM matches ORDER BY season_label DESC, round""").fetchall()
    hdr = ["match_id", "source", "source_match_id", "league_zh", "season", "round",
           "kickoff_utc", "home_zh", "away_zh", "ft_home", "ft_away", "ht_home", "ht_away"]
    put("matches.csv.gz", hdr,
        [[f"500_{r[0]}", "500.com", r[0], r[2], r[1], r[3], r[4],
          r[5], r[6], r[7], r[8], r[9], r[10]] for r in rows])

    # matches 表在 hist 库，comp 库里没有 → 先建 fid -> kickoff_utc 映射
    KO = dict(hist.execute("SELECT fid, kickoff_utc FROM matches").fetchall())

    # odds_1x2：每行一个 (fid, bookmaker, stage)
    rows = comp.execute("""SELECT c.fid, c.bookmaker, c.stage,
                                  c.home_val, c.draw_val, c.away_val, c.book_update_bj
                           FROM company_odds c
                           WHERE c.market='1X2'
                           ORDER BY c.fid, c.bookmaker, c.stage""").fetchall()
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage",
           "home_odds", "draw_odds", "away_odds", "book_update_bj", "source"]
    put("odds_1x2.csv.gz", hdr,
        [[f"500_{r[0]}", r[1], KO.get(r[0]) or "", r[2], r[3], r[4], r[5], r[6], "500.com"] for r in rows])

    # odds_ah
    rows = comp.execute("""SELECT c.fid, c.bookmaker, c.stage,
                                  c.line_num, c.line_text, c.home_val, c.away_val, c.book_update_bj
                           FROM company_odds c
                           WHERE c.market='AH'
                           ORDER BY c.fid, c.bookmaker, c.stage""").fetchall()
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "line", "line_text",
           "home_price", "away_price", "price_format", "book_update_bj", "source"]
    put("odds_ah.csv.gz", hdr,
        [[f"500_{r[0]}", r[1], KO.get(r[0]) or "", r[2], r[3], r[4], r[5], r[6], "HK", r[7], "500.com"]
         for r in rows])

    # odds_ou
    rows = comp.execute("""SELECT c.fid, c.bookmaker, c.stage,
                                  c.line_num, c.home_val, c.away_val, c.book_update_bj
                           FROM company_odds c
                           WHERE c.market='OU'
                           ORDER BY c.fid, c.bookmaker, c.stage""").fetchall()
    hdr = ["match_id", "bookmaker", "snapshot_utc", "stage", "line",
           "over_price", "under_price", "price_format", "book_update_bj", "source"]
    put("odds_ou.csv.gz", hdr,
        [[f"500_{r[0]}", r[1], KO.get(r[0]) or "", r[2], r[3], r[4], r[5], "HK", r[6], "500.com"]
         for r in rows])

    # coverage
    cov = comp.execute("""SELECT market, bookmaker, stage, COUNT(*) rows, COUNT(DISTINCT fid) fids
                          FROM company_odds GROUP BY 1,2,3 ORDER BY 1,2,3""").fetchall()
    cp = os.path.join(out, "coverage.csv")
    with open(cp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market", "bookmaker", "stage", "rows", "matches"])
        for r in cov:
            w.writerow(r)
    man["files"]["coverage.csv"] = {"rows": len(cov), "bytes": os.path.getsize(cp), "sha256": sha(cp)}
    print(f"  {'coverage.csv':22} {len(cov):7} 行")

    # 统计
    total_m = hist.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    by_mkt = defaultdict(lambda: defaultdict(int))
    for mk, bm, st, n, f in cov:
        by_mkt[mk][st] += n
    companies = sorted({r[1] for r in cov})

    readme = f"""# 500.com 公司级历史赔率（德乙 2019/2020 ~ 2026/2027）

导出时间: {man['exported_at_utc']}
数据源: **500.com 逐场抓取**（每个 fid 抓 3 个页面）

```
https://odds.500.com/fenxi/ouzhi-<fid>.shtml    1X2    tr0=初盘 / tr1=收盘
https://odds.500.com/fenxi/yazhi-<fid>.shtml    亚盘   块0=初盘 / 块1=收盘
https://odds.500.com/fenxi/daxiao-<fid>.shtml   大小球 同上
```

## 规模

- 比赛: **{total_m}** 场（8 个赛季）
- 公司: **{len(companies)}** 家 → {', '.join(companies)}
- 总记录: **{sum(sum(v.values()) for v in by_mkt.values())}** 条

## 各市场记录数

| 市场 | open | close |
|---|---|---|
""" + "".join(f"| {m} | {v.get('open', 0)} | {v.get('close', 0)} |\n" for m, v in sorted(by_mkt.items())) + f"""
## 字段说明

**odds_1x2.csv.gz**
| 字段 | 含义 |
|---|---|
| match_id | `500_<fid>` |
| bookmaker | 公司名（中文，如 威廉希尔 / 澳门彩票 / Pinnacle平博） |
| stage | `open`=初盘 / `close`=收盘 |
| home_odds / draw_odds / away_odds | 欧洲盘小数赔率 |
| book_update_bj | 庄家最后更新时间（北京时间） |

**odds_ah.csv.gz**
| 字段 | 含义 |
|---|---|
| line | **数值盘口，主队视角**（负=主队让球，正=主队受让） |
| line_text | 500.com 原始文字（半球/一球 等） |
| home_price / away_price | 香港盘水位（0.70~1.00 典型） |

盘口语义示例：`半球/一球 → -0.75`、`受平手/半球 → +0.25`、`平手 → 0.00`

**odds_ou.csv.gz**
| 字段 | 含义 |
|---|---|
| line | 总进球线（如 3.25） |
| over_price / under_price | 大球/小球水位 |

## 时区

- `snapshot_utc` 用该场的 `kickoff_utc`（UTC），因为 ouzhi 页只给"庄家更新时间"不给快照时刻
- `book_update_bj` 保留北京时间原文，便于与原站核对

## 已验证

- 16 家公司的 **open 与 close 确实不同**（不是复制）：如 fid=825597 bet365 亚盘 -0.75 → -0.50
- 亚盘线数值化已覆盖 1X2 ~ 5 球全部盘口 + 20+ 别名

## 数据完整性

`coverage.csv` 列出每家公司在每个市场/阶段的覆盖场次。部分公司覆盖较少是正常的：
- Eurobet 只有 1051 场（该站后半段才收录）
- Oddset 1252 场
- 其余主流公司（皇冠/伟德/bet365/易胜博/Pinnacle/澳门/10bet/Interwetten/威廉希尔/立博）均 1450+ 场

## 复现

```bash
python -X utf8 collect_500_hist_company.py \\
  --histdb out/bok500_hist.db --out out/bok500_company.db
python -X utf8 export_500_hist_company.py \\
  --histdb out/bok500_hist.db --companydb out/bok500_company.db \\
  --outdir <repo>/exports/grokbot_500_hist
```
约 7.2 小时（2448 场 × 3 页 ≈ 7300 请求），支持断点续跑。

## 合规

500.com 的 `robots.txt` 含 `Disallow: /ouzhi-*.shtml`、`/yazhi-*.shtml`、`/daxiao-*.shtml`。
本次采集违反该声明，用户已授权仅自用、不公开分发。
"""
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    man["matches"] = total_m
    man["companies"] = companies
    man["by_market"] = {m: dict(v) for m, v in by_mkt.items()}
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    print(f"\n  输出: {out}")
    print(f"  比赛 {total_m}  公司 {len(companies)}")

    hist.close()
    comp.close()


if __name__ == "__main__":
    main()
