# 500.com 公司级历史赔率（德乙 2019/2020 ~ 2026/2027）

导出时间: 2026-10-23T17:58:57Z
数据源: **500.com 逐场抓取**（每个 fid 抓 3 个页面）

```
https://odds.500.com/fenxi/ouzhi-<fid>.shtml    1X2    tr0=初盘 / tr1=收盘
https://odds.500.com/fenxi/yazhi-<fid>.shtml    亚盘   块0=初盘 / 块1=收盘
https://odds.500.com/fenxi/daxiao-<fid>.shtml   大小球 同上
```

## 规模

- 比赛: **2448** 场（8 个赛季）
- 公司: **16** 家 → 10bet, Bwin, Eurobet, Interwetten, Oddset, Pinnacle平博, bet365, snai, 伟德, 博天堂, 威廉希尔, 必发, 易胜博, 澳门彩票, 皇冠, 立博
- 总记录: **107315** 条

## 各市场记录数

| 市场 | open | close |
|---|---|---|
| 1X2 | 22885 | 22885 |
| AH | 13377 | 13377 |
| OU | 17396 | 17395 |

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
python -X utf8 collect_500_hist_company.py \
  --histdb out/bok500_hist.db --out out/bok500_company.db
python -X utf8 export_500_hist_company.py \
  --histdb out/bok500_hist.db --companydb out/bok500_company.db \
  --outdir <repo>/exports/grokbot_500_hist
```
约 7.2 小时（2448 场 × 3 页 ≈ 7300 请求），支持断点续跑。

## 合规

500.com 的 `robots.txt` 含 `Disallow: /ouzhi-*.shtml`、`/yazhi-*.shtml`、`/daxiao-*.shtml`。
本次采集违反该声明，用户已授权仅自用、不公开分发。
