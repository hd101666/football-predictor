# 500.com 百家欧指样本集

导出时间: 2026-10-23T08:42:52Z
数据源: **500.com**（https://live.500.com/ 赛程 + https://odds.500.com/fenxi/ouzhi-<fid>.shtml 欧赔页）

## 文件与行数

| 文件 | 行数 | 说明 |
|---|---|---|
| `matches.csv.gz` | 49 |  |
| `odds_1x2.csv.gz` | 1752 |  |
| `odds_ah.csv.gz` | 0 | 本轮未采集（见 README 缺口说明） |
| `odds_ou.csv.gz` | 0 | 本轮未采集（见 README 缺口说明） |
| `results.csv.gz` | 0 | 本轮未采集（见 README 缺口说明） |
| `team_map.csv` | 98 | 队名映射 |
| `README.md` | - | 本文件 |

## 时间范围与快照

- 快照时间: `2026-10-23T08:35:14Z` ~ `2026-10-23T08:35:14Z`
- 比赛场次: **49** 场

## 公司覆盖率

| 公司 | 覆盖场次 |
|---|---|
| 10bet | 49/49 |
| Bwin | 49/49 |
| Interwetten | 49/49 |
| Pinnacle平博 | 49/49 |
| bet365 | 49/49 |
| snai | 49/49 |
| 伟德 | 49/49 |
| 博天堂 | 49/49 |
| 威廉希尔 | 49/49 |
| 平均 | 49/49 |
| 必发 | 49/49 |
| 易胜博 | 49/49 |
| 澳门彩票 | 49/49 |
| 皇冠 | 49/49 |
| 立博 | 49/49 |
| Eurobet | 48/49 |
| Oddset | 47/49 |
| 888sport | 46/49 |

## 字段与时区

- 所有 `snapshot_utc` 为 **UTC**，ISO 8601（`YYYY-MM-DDTHH:MM:SSZ`）
- `book_update_utc`（库内）为北京时间 `+08:00`，导出时未包含
- `stage`: `open`=初盘 / `live`=即时盘（任务要求 open/live/close 三态，本轮**未采 close**）
- 赔率格式: **欧洲盘（小数）**，如 2.10

## 重要缺口（必读）

1. **`odds_ah.csv.gz`（亚盘）和 `odds_ou.csv.gz`（大小球）为空**。
   500.com 的亚盘/大小球在另外的页面（`/yazhi-*.shtml`、`/daxiao-*.shtml`），
   本轮只实现了欧赔（1X2）解析。需另写解析器。
2. **`results.csv.gz` 为空**。赛果在 `https://odds.500.com/fenxi/stat-<fid>.shtml`，
   本轮未实现。
3. **`close` stage 缺失**。收盘价需要赛前最后时刻抓取，本轮为单次快照。
4. **`country`、`jc_code`、`sfc_issue`、`pinnacle_event_id` 均为空**。
   - country: 500.com 页面有国旗但未解析
   - jc_code / sfc_issue: 500.com 竞彩页才有，本轮未接
   - pinnacle_event_id: 未做与 Pinnacle 的匹配
5. **历史数据未做**。任务要求 2019-07 起五大联赛历史初盘/终盘，
   500.com 的历史赔率页结构不同，需单独实现。

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
