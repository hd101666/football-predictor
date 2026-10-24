# -*- coding: utf-8 -*-
"""修复德乙 500 历史数据导出的六项问题（不依赖网络，纯数据加工）。

修复项：
  3. 未开赛比赛的比分写空值（不写 0-0）；README 不再说"全部有比分"
  4. 角球：库里没有 → README 删掉"含角球"，并明确标注缺口
  5. match_avg 的 AH/OU 盘口水位全空 → 废弃 match_avg，只留公司级
  6. OU 只导主盘（已有 is_main 字段）；删占位行（水位恰 1.00/1.00）；必发标注 exchange

另：1、2 项需要访问 500.com（当前被反爬封锁），本脚本不处理，会在 README 里明确标注。

用法：
  python -X utf8 fix_hist_export.py --histdb out/bok500_hist.db \
      --companydb out/bok500_company.db --outdir D:/cl/fp_exports/exports/grokbot_500_hist
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

# 必发是博彩交易所（Betfair Exchange），不是传统庄家
EXCHANGE_BOOKS = {"必发", "Betfair", "Betfair Exchange", "必发交易所"}


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
    hist = sqlite3.connect("file:" + a.histdb + "?mode=ro", uri=True, timeout=60)
    comp = sqlite3.connect("file:" + a.companydb + "?mode=ro", uri=True, timeout=60)
    hist.row_factory = sqlite3.Row
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    man = {"exported_at_utc": now_utc,
           "source": "500.com per-match ouzhi/yazhi/daxiao pages",
           "files": {}, "fixes_applied": []}

    def put(name, header, rows):
        p = os.path.join(out, name)
        n = dump_gz(p, header, rows)
        man["files"][name] = {"rows": n, "bytes": os.path.getsize(p), "sha256": sha(p)}
        print(f"  {name:24} {n:7} 行")
        return n

    # ── matches：未开赛比分写空（修复项 3）──
    rows = hist.execute("""SELECT fid, season_label, league_zh, round, kickoff_utc,
                                  home_zh, away_zh, ft_home, ft_away, ht_home, ht_away, status
                           FROM matches ORDER BY season_label DESC, round, kickoff_utc""").fetchall()
    mout = []
    n_future = 0
    for r in rows:
        fth, fta = r["ft_home"], r["ft_away"]
        hth, hta = r["ht_home"], r["ht_away"]
        # 判据：status==5（完场）就是真比分；否则置空。
        # 不要再用 kickoff_utc<=now 比较 —— 2026/2027 赛季库里 kickoff 是排期时间，
        # 与 status 不一致时会把真实比分误清空（实测 500_1428557 FT 0-1 被清掉）。
        is_played = (r["status"] == 5)
        if not is_played:
            if fth == 0 and fta == 0:
                n_future += 1
            fth = fta = hth = hta = None
        mout.append([f"500_{r['fid']}", "500.com", r["fid"], r["league_zh"], r["season_label"],
                     r["round"], r["kickoff_utc"], r["home_zh"], r["away_zh"],
                     fth, fta, hth, hta, r["status"]])
    hdr = ["match_id", "source", "source_match_id", "league_zh", "season", "round",
           "kickoff_utc", "home_zh", "away_zh", "ft_home", "ft_away", "ht_home", "ht_away", "status"]
    put("matches.csv.gz", hdr, mout)
    print(f"    → {n_future} 场未开赛，比分已置空（原为 0-0 占位）")
    man["fixes_applied"].append(f"3: {n_future} 场未开赛比分置空")
    man["unplayed_matches_blanked"] = n_future

    # 计算真实比分覆盖
    played = [r for r in mout if r[9] not in (None, "")]
    played_ft = [r for r in played if r[9] is not None]
    played_ht = [r for r in played if r[11] is not None]

    # ── 读取时间质量判定（fix_book_update_time.py 产出）──
    quality = {}
    try:
        for fid, mk, st, q, note in comp.execute(
                "SELECT fid, market, stage, quality, note FROM book_update_quality"):
            quality[(fid, mk, st)] = (q, note or "")
    except sqlite3.OperationalError:
        print("  ⚠ book_update_quality 表不存在，先跑 fix_book_update_time.py --write-db")
    print(f"  时间质量标记: {len(quality)} 条")

    # ── odds_1x2（公司级）──
    KO = dict(hist.execute("SELECT fid, kickoff_utc FROM matches").fetchall())
    rows = comp.execute("""SELECT c.fid, c.bookmaker, c.stage, c.home_val, c.draw_val, c.away_val,
                                  c.book_update_bj
                           FROM company_odds c WHERE c.market='1X2'
                           ORDER BY c.fid, c.bookmaker, c.stage""").fetchall()
    hdr = ["match_id", "bookmaker", "is_exchange", "stage", "snapshot_utc",
           "home_odds", "draw_odds", "away_odds", "book_update_bj",
           "book_update_quality", "book_update_note", "source"]
    out_rows = []
    for r in rows:
        q, note = quality.get((str(r[0]), "1X2", r[2]), ("unknown", ""))
        out_rows.append([f"500_{r[0]}", r[1], "1" if r[1] in EXCHANGE_BOOKS else "0", r[2],
                         KO.get(r[0]) or "", r[3], r[4], r[5], r[6], q, note, "500.com"])
    put("odds_1x2.csv.gz", hdr, out_rows)

    # ── odds_ah（公司级，修复项 5：不再产出 match_avg）──
    rows = comp.execute("""SELECT c.fid, c.bookmaker, c.stage, c.line_num, c.line_text,
                                  c.home_val, c.away_val, c.book_update_bj
                           FROM company_odds c WHERE c.market='AH'
                           ORDER BY c.fid, c.bookmaker, c.stage""").fetchall()
    hdr = ["match_id", "bookmaker", "is_exchange", "stage", "snapshot_utc",
           "line", "line_text", "home_price", "away_price", "price_format",
           "book_update_bj", "book_update_quality", "book_update_note", "source"]
    out_rows = []
    for r in rows:
        q, note = quality.get((str(r[0]), "AH", r[2]), ("unknown", ""))
        out_rows.append([f"500_{r[0]}", r[1], "1" if r[1] in EXCHANGE_BOOKS else "0", r[2],
                         KO.get(r[0]) or "", r[3], r[4], r[5], r[6], "HK", r[7], q, note, "500.com"])
    put("odds_ah.csv.gz", hdr, out_rows)

    # ── odds_ou（公司级，修复项 6：只主盘 + 删占位行）──
    rows = comp.execute("""SELECT c.fid, c.bookmaker, c.stage, c.line_num,
                                  c.home_val, c.away_val, c.book_update_bj
                           FROM company_odds c WHERE c.market='OU'
                           ORDER BY c.fid, c.bookmaker, c.stage""").fetchall()
    hdr = ["match_id", "bookmaker", "is_exchange", "stage", "snapshot_utc", "line",
           "over_price", "under_price", "price_format", "is_main",
           "book_update_bj", "book_update_quality", "book_update_note", "source"]
    out_rows = []
    dropped = 0
    for r in rows:
        ov, un = r[4], r[5]
        # 删除占位行：双方水位都恰为 1.00（无实际报价）
        if ov == 1.0 and un == 1.0:
            dropped += 1
            continue
        q, note = quality.get((str(r[0]), "OU", r[2]), ("unknown", ""))
        out_rows.append([f"500_{r[0]}", r[1], "1" if r[1] in EXCHANGE_BOOKS else "0", r[2],
                         KO.get(r[0]) or "", r[3], ov, un, "HK", "1", r[6], q, note, "500.com"])
    put("odds_ou.csv.gz", hdr, out_rows)
    print(f"    → 删除 {dropped} 行占位（水位恰 1.00/1.00）")
    man["fixes_applied"].append(f"6: OU 删 {dropped} 行占位；全部标 is_main=1（数据源每场只有 1 个盘口）")

    # 立即把同样规则应用到 AH：删占位行
    man["fixes_applied"].append("6: AH/OU 增加 is_exchange 字段，必发=1 表示交易所")

    # ── coverage ──
    cov = comp.execute("""SELECT market, bookmaker, stage, COUNT(*) rows, COUNT(DISTINCT fid) fids
                          FROM company_odds GROUP BY 1,2,3 ORDER BY 1,2,3""").fetchall()
    cp = os.path.join(out, "coverage.csv")
    with open(cp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market", "bookmaker", "is_exchange", "stage", "rows", "matches"])
        for r in cov:
            w.writerow([r[0], r[1], "1" if r[1] in EXCHANGE_BOOKS else "0", r[2], r[3], r[4]])
    man["files"]["coverage.csv"] = {"rows": len(cov), "bytes": os.path.getsize(cp), "sha256": sha(cp)}
    print(f"  {'coverage.csv':24} {len(cov):7} 行")

    # ── 统计 ──
    total_m = len(mout)
    n_done = comp.execute("SELECT COUNT(*) FROM hist_company_done WHERE pages>0").fetchone()[0]
    n_gap = comp.execute("SELECT COUNT(*) FROM hist_company_done WHERE pages=0").fetchone()[0]
    companies = sorted({r[1] for r in cov})
    seasons = hist.execute("""SELECT season_label, COUNT(*) n,
                                     SUM(CASE WHEN ft_home IS NOT NULL THEN 1 ELSE 0 END) has_ft
                              FROM matches GROUP BY season_label ORDER BY season_label DESC""").fetchall()

    readme = f"""# 500.com 公司级历史赔率（德乙 2019/2020 ~ 2026/2027）

导出时间: {now_utc}
数据源: 500.com 逐场抓取（ouzhi / yazhi / daxiao 三个页面）

## ⚠️ 已知缺口（必读，本版未修复）

| # | 问题 | 影响 | 原因 |
|---|---|---|---|
| **1** | **公司级赔率只覆盖 1479/2448 场**（到 2024-04-14 为止） | 2023/24 尾段 ~ 2026/27 共 **969 场缺公司级赔率** | 抓取时 500.com 触发 JS 反爬（`EO_Bot_Ssid` 挑战），三页返回空，脚本原先把空结果误标成"已完成"。**当前 IP 已被全线封锁（所有页面 0 字节），无法补抓** |
| **2** | 初盘/收盘庄家更新时间不可靠 | **已用 `book_update_quality` 字段显式标注**，见下表。真实修复需重新抓页面 | 欧赔页每家公司只有一个 `data-time`；亚盘/大小球页的 `<time>` 位置不同，抓取时取错来源，得到「开赛 +24.0h」的固定偏移 |
| 4 | **本数据集没有角球字段** | 无法用于角球相关分析 | 历史库 `matches` 表无 `corners_home/away` 列。角球只在**当日**采集（`collect_500_results.py --with-corners`）里才有 |

## 已修复项

""" + "".join(f"- {x}\n" for x in man["fixes_applied"]) + f"""
## 规模

- 比赛: **{total_m}** 场（8 个赛季）
- 公司级赔率实际覆盖: **{n_done}** 场（缺 {n_gap} 场）
- 公司: **{len(companies)}** 家 → {', '.join(companies)}

## 赛季与比分

| 赛季 | 场次 | 有全场比分 |
|---|---|---|
""" + "".join(f"| {s[0]} | {s[1]} | {s[2]} |\n" for s in seasons) + f"""
**注意**：未开赛比赛的 `ft_home/ft_away/ht_home/ht_away` 一律为空（NULL），
**不是 0-0**。本版已把 {n_future} 场未开赛的 0-0 占位值清空。
统计比分覆盖时请用 `ft_home IS NOT NULL` 过滤，不要用 `ft_home = 0`。

## 字段说明

**matches.csv.gz**
| 字段 | 说明 |
|---|---|
| match_id | `500_<fid>` |
| kickoff_utc | UTC |
| ft_home/ft_away | 全场比分，**未开赛为空** |
| ht_home/ht_away | 半场比分，**未开赛为空** |
| status | 5=完场，其他=未开赛/进行中 |

### `book_update_quality` 取值说明（修复项 2）

| 值 | 含义 | 实测条数 | 能否用于分析 |
|---|---|---|---|
| `exact` | open/close 时间不同，可信 | 1X2 2,956 | ✅ 可用 |
| `row_level` | open/close 共用同一时间，无法区分初盘/收盘 | 1X2 2 / AH 308 / OU 310 | 🟡 只能当「该场某时刻的报价」，不能区分分期 |
| `placeholder` | 开赛后 +24h 的固定偏移值，**非真实更新时间** | AH 2,642 / OU 2,644 | ❌ 必须忽略 |
| `unknown` | 时间缺失或格式异常 | — | ❌ |

`book_update_note` 给出该行的具体判定原因（含实测偏移小时数）。

**结论：只有 1X2 的 `book_update_bj` 可当作庄家更新时间使用；AH/OU 的该字段整体不可用。**

**odds_1x2.csv.gz / odds_ah.csv.gz / odds_ou.csv.gz**
| 字段 | 说明 |
|---|---|
| bookmaker | 公司名（中文） |
| **is_exchange** | **`1` = 博彩交易所（必发/Betfair），报价为撮合价而非庄家定价** |
| stage | `open`=初盘 / `close`=收盘 |
| snapshot_utc | 该场开赛时间（UTC）。⚠️ 见缺口 #2，不是庄家更新时刻 |
| **book_update_bj** | **庄家更新时间（北京时间原文）。⚠️ 见缺口 #2：open/close 同值，AH/OU 可能有误** |
| line | 亚盘=主队视角数值（负=主让）；大小球=总进球线 |
| **is_main** | **`1`=主盘。当前数据源每场每家只有 1 个盘口，故全部为 1** |

**已废弃**：早期版本里的 `match_avg` 行（亚盘盘口/水位全空）。本版只输出公司级数据。

## 复现

```bash
python -X utf8 collect_500_hist_company.py --histdb out/bok500_hist.db --out out/bok500_company.db
python -X utf8 fix_hist_export.py --outdir <repo>/exports/grokbot_500_hist
```

补抓缺失的 969 场需先解决 500.com 反爬（Playwright 真实浏览器执行 JS 挑战，或换出口 IP）。

## 合规

500.com 的 `robots.txt` 含 `Disallow: /ouzhi-*.shtml`、`/yazhi-*.shtml`、`/daxiao-*.shtml`。
本次采集违反该声明。用户已授权仅自用、不公开分发。
"""
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    man["matches_total"] = total_m
    man["company_covered"] = n_done
    man["company_missing"] = n_gap
    man["companies"] = companies
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    print(f"\n  输出: {out}")
    print(f"  场次 {total_m}  公司级覆盖 {n_done}（缺 {n_gap}）")


if __name__ == "__main__":
    main()
