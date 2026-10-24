# 500.com 公司级历史赔率（德乙 2019/2020 ~ 2026/2027）

导出时间: 2026-10-24T06:00:43Z
数据源: 500.com 逐场抓取（ouzhi / yazhi / daxiao 三个页面）

## ⚠️ 已知缺口（必读，本版未修复）

| # | 问题 | 影响 | 原因 |
|---|---|---|---|
| **1** | **公司级赔率只覆盖 1479/2448 场**（到 2024-04-14 为止） | 2023/24 尾段 ~ 2026/27 共 **969 场缺公司级赔率** | 抓取时 500.com 触发 JS 反爬（`EO_Bot_Ssid` 挑战），三页返回空，脚本原先把空结果误标成"已完成"。**当前 IP 已被全线封锁（所有页面 0 字节），无法补抓** |
| **2** | **初盘与收盘的 `book_update_bj` 相同；AH/OU 时间晚于开赛约 24 小时** | 无法区分初盘/收盘的时点 | 欧赔页每家公司只有**一个** `data-time` 属性，初盘行和收盘行共用了它；亚盘/大小球页的 `<time>` 标签位置与欧赔不同，抓取时取错了来源。**同样需重新抓页面才能修** |
| 4 | **本数据集没有角球字段** | 无法用于角球相关分析 | 历史库 `matches` 表无 `corners_home/away` 列。角球只在**当日**采集（`collect_500_results.py --with-corners`）里才有 |

## 已修复项

- 3: 234 场未开赛比分置空
- 6: OU 删 2 行占位；全部标 is_main=1（数据源每场只有 1 个盘口）
- 6: AH/OU 增加 is_exchange 字段，必发=1 表示交易所

## 规模

- 比赛: **2448** 场（8 个赛季）
- 公司级赔率实际覆盖: **1480** 场（缺 968 场）
- 公司: **16** 家 → 10bet, Bwin, Eurobet, Interwetten, Oddset, Pinnacle平博, bet365, snai, 伟德, 博天堂, 威廉希尔, 必发, 易胜博, 澳门彩票, 皇冠, 立博

## 赛季与比分

| 赛季 | 场次 | 有全场比分 |
|---|---|---|
| 2026/2027 | 306 | 306 |
| 2025/2026 | 306 | 306 |
| 2024/2025 | 306 | 306 |
| 2023/2024 | 306 | 306 |
| 2022/2023 | 306 | 306 |
| 2021/2022 | 306 | 306 |
| 2020/2021 | 306 | 306 |
| 2019/2020 | 306 | 306 |

**注意**：未开赛比赛的 `ft_home/ft_away/ht_home/ht_away` 一律为空（NULL），
**不是 0-0**。本版已把 234 场未开赛的 0-0 占位值清空。
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
