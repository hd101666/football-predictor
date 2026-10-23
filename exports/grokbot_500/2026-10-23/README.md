# 500.com 百家欧指样本集

导出时间: 2026-10-23T09:11:35Z
数据源: **500.com**（https://live.500.com/ 赛程 + https://odds.500.com/fenxi/ouzhi-<fid>.shtml 欧赔页）

## 文件与行数

| 文件 | 行数 | 说明 |
|---|---|---|
| `matches.csv.gz` | 49 |  |
| `odds_1x2.csv.gz` | 1752 |  |
| `odds_ah.csv.gz` | 706 |  |
| `odds_ou.csv.gz` | 880 |  |
| `results.csv.gz` | 238 |  |
| `team_map.csv` | 98 | 队名映射 |
| `README.md` | - | 本文件 |

## 时间范围与快照

- 快照时间: `2026-10-23T08:52:45Z` ~ `2026-10-23T08:52:45Z`
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
