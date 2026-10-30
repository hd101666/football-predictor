# 命中系统 (Hit System) — 足球为主 / 篮球单独存放

> 全球足球与篮球分析预测系统的可复用部分。本目录为**独立可运行包**，不从属于仓库根目录已有的
> `crawlers/`、`src/`、`data/`、`models/`（那套是早期版本，本目录是完整版）。
>
> 全部状态与数字均由 **2026-10-30 实跑验证** 得出，不编造字段、不臆测状态。

---

## 📋 总表（先看这个）

完整爬虫总表见 **[`CRAWLER_INDEX.md`](CRAWLER_INDEX.md)** — 45 个爬虫逐行标注：
编号/文件、源站 API、覆盖范围、输出表、库内行数、是否需要 Key、**实测状态**、实测说明。

| 项目 | 数值 |
|---|---|
| 足球爬虫 | 38 |
| 篮球爬虫 | 7 |
| 爬虫合计 | **45** |
| 能跑 | **39** |
| 已停用（废弃，不修） | 6 |
| 数据表 | 231 张 |
| 全库行数 | 13,839,923 |
| 已导出样本 | 190 张表 × ≤100 行 |

模型清单与回测见 **[`docs/MODELS.md`](docs/MODELS.md)**。
字段字典（190 张表逐字段中文说明）见 **[`docs/FIELD_DICTIONARY.md`](docs/FIELD_DICTIONARY.md)**。

---

## 📁 目录结构

```
hit-system/
├── README.md                  ← 本文件
├── CRAWLER_INDEX.md           ← 45 个爬虫总表（必看）
├── requirements.txt
├── .env.example               ← 环境变量模板（只有变量名，无值）
├── football/                  ← 38 个足球爬虫
├── basketball/                ← 7 个篮球爬虫（与足球完全分开）
├── models/                    ← 预测模型 18 个
├── shared/                    ← 公共模块（config / db_utils / http_utils ...）
├── samples/                   ← 190 张表真实样本 CSV + manifest.json
└── docs/
    ├── MODELS.md              ← 模型清单、特征、回测、运行示例
    └── FIELD_DICTIONARY.md    ← 字段字典（空值语义）
```

**足球与篮球严格分开**：`football/` 与 `basketball/` 两个目录，无混用。
少数爬虫同时覆盖两种运动（如 `29_qiety_yb_full_scraper.py` 用 `--sport 1/2`），统一放在 `football/`，篮球侧在 `basketball/README.md` 中标注说明。

---

## 🚀 从零跑通

### 0. 环境

- Python **3.11**（实测 3.11.9 / Windows 10）
- 无需 GPU（LSTM 模型可选）

### 1. 安装依赖

```bash
cd hit-system
pip install -r requirements.txt
python -m playwright install chromium      # JS 渲染类爬虫必需
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你有的 Key。没有的留空即可，只影响对应爬虫
```

> 所有密钥一律走 `os.getenv()`，仓库内**不含任何真实 Key / Token / 密码 / Cookie**。

### 3. 准备数据库

数据库为 SQLite，默认路径 `./data/sports_data.db`（可通过 `DB_DIR` 修改）。

本包**不附带完整数据库**（5.27 GB），只附带 `samples/` 中每表最多 100 行样本。
两种起库方式：

```bash
# 方式 A：用你自己的库，把路径指过去
export DB_DIR=/path/to/your/data

# 方式 B：从样本表结构初始化空库（Python）
python - <<'PY'
import sqlite3, csv, glob, os
conn = sqlite3.connect("data/sports_data.db")
for f in glob.glob("samples/*.csv"):
    t = os.path.basename(f)[:-4]
    with open(f, encoding="utf-8-sig") as fh:
        hdr = next(csv.reader(fh))
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{t}" (' + ",".join(f'"{c}" TEXT' for c in hdr) + ")")
conn.commit(); print("表结构已建")
PY
```

### 4. 跑一个爬虫（真实命令）

```bash
# 企鹅体育全量赔率（需 QIETY_TOKEN）—— 实测 103 场全成功
python football/29_qiety_yb_full_scraper.py --sport 1 --force-refresh --within-hours 12

# 竞彩官网半全场 —— 实测写入 73 条（足球55场 + 篮球18场）
python football/47_sporttery_hafu_scraper.py

# football-data.co.uk 历史数据 —— 实测 309,641 行
python football/16_footballdata_scraper.py

# 篮球 NBA 官方 —— 实测 52,481 行
python basketball/31_nba_official_scraper.py
```

### 5. 跑一次模型（真实命令与输出）

```bash
python models/predict_football.py --date 2026-10-23
```

```
  📐 Dixon-Coles rho MLE拟合: -0.0433（样本3052场）
  ⏱ HT/FT: 231065 场训练样本
  ⚽ 今日待预测: 533 场
  🏆 ELO: 1574 队  |  泊松: 32 联赛  |  ELO截止=2026-10-23  用 274044/275339 场
  📐 市场隐含λ融合：447/533 场有完整大小球+独赢真实赔率
  ✅ 预测完成: 524 场  比分: 209 条  OU行: 2508
```

篮球：

```python
import sys; sys.path.insert(0, "models")
import basketball_normal_model as m
m.basketball_total_probs(220.5, 18.0, [215.5, 220.5, 225.5])
```

---

## ⚠ 已知问题（诚实清单）

### 已修复（2026-10-30）

| 问题 | 处理结果 |
|---|---|
| `unified_matches` 赛程断更 7 天 | ✅ **已修复**。跑 `00_命中系统.py --no-scrape --date 2026-10-30` 重新聚合，今日 445 场已入库；`predict_football.py --latest` 现输出 436 场预测（原为 0 场） |

### 已停用爬虫（按"废弃不修"原则不再维护）

| 文件 | 停用原因 | 替代方案 |
|---|---|---|
| `11_fbref_xg_scraper.py` | 实测 FBref 免费页已彻底移除 xG 列（standard 表仅 21 列，`/xg/` 页 shooting 表 13 列均无 xG），页面只剩 Subscribe/Sign up | ✅ `understat_xg_teams`(336队) / `understat_xg_matches`(5,976场) 已有数据 |
| `13_bet365_scraper.py` | 需 RapidAPI 付费订阅；`RAPIDAPI_KEY` 当前仍是占位符 `***` | 用 `35_theoddsapi_multi_scraper.py` 覆盖主流联赛 |
| `19_whoscored_scraper.py` | 已修好 camoufox 插件（UBO 空目录导致 manifest.json 缺失），但 WhoScored 全站被 Cloudflare IP 级封锁，连首页都返回 `Attention Required` | 无 |
| `24_betfair_scraper.py` | 需官方 Exchange API Key + 应用证书，且 IP 已被 403 | 无 |
| `30_qiety_history_scraper.py` | 浏览器 UI 自动化登录需 `QIETY_ACCOUNT/PASSWORD`；硬编码 `qiety1748/1692/1726.vip`、`h5.qiety.vip` 全部失效 | 用 `29_qiety_yb_full_scraper.py` 的 `qiety_matches` 表 |
| `46_sportmonks_fixtures_scraper.py` | 账号仅 Free Plan，无 football 权限（HTTP 200 但返回 no access） | 无 |

### 仍未处理

| 问题 | 影响 | 说明 |
|---|---|---|
| `models/05_9_Backtest_Module.py` 文件损坏 | 无法导入 | 第 16 行三引号被误转义为 `\"\"\"`，SyntaxError |
| 现成回测结论不可采信 | 勿据此下注 | `backtest_summary` 仅 180 场且 `real_odds_used=0`，最大回撤 -95.39%，详见 MODELS.md |

## 📊 字段与空值约定

- **空值不等于 0**。未开赛比分、未确认首发、未覆盖联赛一律留空，不用 0 填充。
- 首发 vs 预测首发：`fixture_lineups` 有 `is_confirmed` 类字段区分，未确认为空。
- 赔率必须带来源与抓取时间：表内含 `bookmaker`/`snapshot_time` 列，详见字段字典。
- 时间语义：`kickoff_utc` 为 UTC；`fetch_date` 为源站日期；`created_at` 默认 `datetime('now')` 为**北京时间**，导出对时需 -8h。

---

## 🔒 安全声明

- 本包所有密钥均从环境变量读取，仓库内**零硬编码凭据**（已全量扫描验证）。
- 不包含任何私人账号、投注账号、Cookie、`.env` 真实值。
- `samples/` 已剔除 password/token/secret/cookie/session/account/phone/email 等敏感列。
- 样本中的球员姓名为**公开体育数据**，非私人信息。

---

## 免责

本系统为数据分析与预测工具，输出结果不构成投注建议。回测指标存在已知缺陷（见上），
请勿将任何预测结果直接当作最终推荐。使用方需自行核对盘口线与赔率的真实性。
