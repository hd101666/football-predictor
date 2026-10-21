# hit_system — 命中系统参考包（代码 + 已结算影子注单）

本目录是 `D:\cl\qqsj`（全球双体育量化系统 / 命中系统）的**只读快照**，导出给外部分析助手阅读与验证。

- 源项目：`D:\cl\qqsj`（导出时未修改、未删除任何源文件；数据库全部以 `mode=ro` 只读打开）
- 导出时间：2026-10-21
- 用途：让人能独立复核「命中分 / p融合 / 候选生成与过滤 / 转正判定 / 自动结算 / 凯利与投注计划 / 爬虫落表」这套逻辑，以及用真实已结算数据验算。

```
ref/hit_system/
├── README.md          ← 本文件
├── code/              ← 116 个 .py + requirements.txt + _param_overrides.json（已脱敏）
└── data/              ← 12 张已结算/推荐表的 .csv.gz（Git LFS）
```

---

## 0. 必读：脱敏改动的副作用

所有真实密钥的**默认值**已替换为 `"REDACTED"` 或空串（`os.environ.get("X", "…")` 形态保留，语义不变）。因此：

| 文件 | 原本 | 现在 | 影响 |
|---|---|---|---|
| `config.py` | `APISPORTS_KEY_1/2/3`、`TAVILY_API_KEY`、`SHARPAPI_KEY`、`PINNACLE_GUEST_KEY`、`RAPIDAPI_KEY`、`FEISHU_*` 等硬编码默认值 | 默认 `""` 或 `"REDACTED"` | 需自备 `.env` 才能真连 |
| `15_pinnacle_oddsportal_scraper.py` | `_OP_PBKDF2_PASSWORD` / `_OP_PBKDF2_SALT`（自 OddsPortal app-*.js 逆向的硬编码口令与盐） | 改为 `os.environ.get(..., "REDACTED")` | **OddsPortal 响应解密需自备口令/盐**，否则该源不可用；其余源不受影响 |
| `config.py` | `BETTING_MODE` 默认 `"paper"` | 提取为同文件常量 `PAPER_MODE = "paper"`，默认值行为完全一致 | 无（真钱通道仍需 `BETTING_MODE=live` + `ENABLE_LIVE_BETTING=1` 双开关） |

另外 3 处 `os.environ.get("X", "<非空默认值>")` 也被替换（`TMP`、`QQSJ_ODDS_API_BUDGET_CAP`、`QQSJ_ODDS_API_MIN_REMAINING`）——**注意 `QQSJ_ODDS_API_BUDGET_CAP` 现在是 `int(os.environ.get(..., "REDACTED"))`，直接跑会在 import 期抛 `ValueError`**，要跑 `35_theoddsapi_multi_scraper.py` 请先设该环境变量（原值见 `config` 注释语义：单次运行配额上限）。

脱敏后全部 116 个 `.py` 均通过 `ast.parse` 语法校验，但**只有语法可读性保证，没有跑通验证**（缺少真实密钥与 4.9 GB 数据库在同机环境）。

---

## 1. 代码文件作用

### 1.1 核心引擎（无网络、被主控 import）

| 文件 | 行数 | 作用 |
|---|---|---|
| `00_命中系统.py` | 9436 | **主控**。调度全部爬虫 → 跨源比赛匹配 → 共识赔率 → 调预测模型 → 候选生成/过滤 → hit_score → 投注计划/投注单落盘 → 影子桶写库。全部核心公式在这一个文件里。 |
| `config.py` | 1483 | 全局配置：融合权重、MARKET_BIAS、阈值、资金管理、联赛/球队中文映射、The Odds API 8 槽位配额池、`.env` 加载、`_param_overrides.json` 覆盖。 |
| `db_utils.py` | 220 | SQLite↔MySQL DDL 兼容层 + 批量写入。 |
| `env_setup.py` | 54 | `.env` 加载 + 日志 + stdout UTF-8（所有爬虫 `import env_setup` 完成初始化）。 |
| `promotion_gate.py` | 169 | **FIX-003 转正闸门**：预注册校验（`promotion_registry.json`）+ 每季度最多放行 1 个新转正桶（多重比较防护）。 |
| `freshness_check.py` | 91 | 跑批收尾数据新鲜度监控（核心表 1 天 / 辅助表 7 天），异常写 `data_quality_issue_log`。 |
| `http_utils.py` | 226 | `StealthSession`：TLS 指纹 + UA 轮换 + Cookie 热身 + 重试 + 429 处理。 |
| `leagues.py` | 77 | Flashscore 管道格式联赛路径映射。 |
| `source_evidence.py` | 2198 | 数据来源「证据层」（FotMob / The Odds API 共用）：请求台账、字段观测、配额回执、身份交叉表。 |
| `odds_extract.py` | 379 | The Odds API v4 响应纯解析层（无网络、无 DB）。 |
| `fotmob_extract.py` | 659 | FotMob matchDetails / leagues 响应纯解析层。 |
| `sportmonks_extract.py` | 458 | Sportmonks API v3 纯解析层。 |
| `sporttery_source.py` | 292 | 竞彩官网（sporttery.cn）数据源封装。 |
| `htft_settle.py` | 23 | 半全场结果判定（21_auto_settle 与 backtest_engine 共用）。 |
| `team_mapping.py` | 3345 | 中文↔英文队名映射（145 条主表 + 大量别名/联赛规则）。 |
| `team_zh.py` | 999 | 球队中文名映射表。 |

### 1.2 模型层

| 文件 | 作用 |
|---|---|
| `poisson_model_v2.py` | 高级泊松 λ：球队主/客场攻防 + 近况混合（长期 60/近期 40）+ 对手强度修正；**样本 < 5 场直接返回 None，不再回归联赛均值**（2026-08-24 规则）。 |
| `predict_football.py` | 足球预测 v2：Dixon-Coles 低比分修正（ρ 由 MLE 拟合，默认 −0.10）+ 泊松 + ELO（K=32, 主场 +60, 初始 1500）+ 形态指数衰减 0.06；产出 1x2 / 大小球 / 比分 / 半全场（HTFT 9 格联合）→ 写 `market_prediction_snapshot`、`football_score_predictions`、`dc_rho_state`。 |
| `predict_basketball.py` | 篮球独立预测（写 `market_prediction_snapshot`）。 |
| `basketball_normal_model.py` | 篮球正态分布模型（基于历史得分均值/标准差算大小球）。 |
| `corner_model.py` | 角球模型 v2：正态(≤10.5)/负二项(≥11.5) 混合分布，`MU_BIAS_CORRECTION = +0.25`，EV≥10%，`CORNER_KELLY_FRAC = 0.25`。 |
| `_fit_draw_calibration.py` | 足球 1x2 平局等渗回归校准曲线拟合（分位分桶每桶 ≥200 场再做 PAVA）→ 写 `draw_calibration_curve`。 |
| `04_1_LSTM_时序状态模型.py` | 「LSTM」实为纯 NumPy/SciPy 的 EMA + AR(1) 替代实现，写 `team_lstm_state`。 |
| `04_2_Football_xG_Module.py` | xG 三源融合特征，写 `football_xg_stats`。 |
| `05_泊松凯利预测模型.py` | 七层融合终极版（泊松/「LSTM」/Transformer/xG/GNN/RL/多模态权重见 §2.6），写 `basketball_prediction`。 |
| `05b_国家队预测适配层.py` | 国家队 ELO + StatsBomb 国家队 xG 适配层，写 `prediction_snapshot`。 |

### 1.3 结算 / 校准 / 回测 / 出单

| 文件 | 作用 |
|---|---|
| `21_auto_settle.py` | **自动结算**（2060 行）：`auto_settle`（正式单）、`auto_settle_under/over_shadow`、`settle_team_total_shadow_full`、`settle_legacy_team_total_under`、`settle_basketball_under/moneyline_fade`、`settle_moneyline_shadow_full`、`settle_shadow_recommendations`（多桶）、`settle_corner_recommendations`、`settle_fotmob_corner_shadow`；含 4 层比分匹配（精确统一ID → 模糊队名 → FotMob 兜底 → 188bifen 兜底）。 |
| `_auto_calibrate.py` | 每积累 100 注新结算触发阈值校准，写 `_param_overrides.json`。 |
| `_daily_settle.py` | 每日结算管道封装。 |
| `backtest_engine.py` | 回测闭环：`backtest_daily` 表 + 资金曲线。 |
| `_backtest_*.py`（10 个） | 因子回测：totals/team_total/fotmob 三市场/角球/平局门槛/深回测。 |
| `_k_value_*.py`（5 个） | K 值（凯利）推荐单历史迭代版本，v3/v4 为后期清洁版。 |
| `gen_slip*.py` / `export_*.py` / `_print_cn_bet_slip.py` / `gen_full_slip_tmp.py` | 投注单生成/导出/全中文排版。 |
| `predict_reasoning_xlsx.py` / `settle_match_detail_zh.py` / `_translate_slip_zh.py` | 逐场推荐理由 Excel、结算复盘明细、中文格式统一。 |
| `06_Web可视化看板.py` | Streamlit 看板（读 `HIT_SCORE_GLOBAL_THRESHOLD` 等）。 |
| `ren9_analysis.py` / `ren9_daily_review.py` / `gen_jingcai.py` | 胜负彩 14 场 / 任九 分析、复盘、竞彩出单。 |
| `_run_scrape_only.py` | 只跑爬虫阶段（「先爬→补爬→再分析」分步流程）。 |

### 1.4 爬虫（写哪些表）

| 文件 | 数据源 | 主要落表 |
|---|---|---|
| `43_fotmob_match_data_scraper.py` | FotMob | `fotmob_matches` / `fotmob_shots` / `fotmob_player_match_stats` / `fotmob_lineups` / `fotmob_match_team_stats` + 证据层表 |
| `15_pinnacle_oddsportal_scraper.py` | Pinnacle Guest API + OddsPortal(AES) | `theodds_fixtures` / `theodds_odds` / `theodds_odds_history` / `pinnacle_correct_score_odds` |
| `12_pinnacle_scraper.py` | Pinnacle guest public API | `pinnacle_fixtures` / `pinnacle_leagues` / `pinnacle_odds` / `pinnacle_odds_history` / `pinnacle_corner_odds` |
| `35_theoddsapi_multi_scraper.py` | The Odds API v4（Bet365/Betfair/Unibet…，8 槽位配额） | `theodds_api_odds` + `theodds_api_*` 证据表（经 `source_evidence.py`） |
| `07_sofascore_scraper.py` | SofaScore | `sofascore_matches/stats/form/h2h/odds/xg` |
| `08_flashscore_scraper.py` / `09_flashscore_schedule_scraper.py` | Flashscore 管道协议 | `flashscore_matches` / `flashscore_odds_history` / `soccerway_*`(历史命名) |
| `10_oddsportal_scraper.py` | OddsPortal（Playwright） | `oddsportal_matches/odds/odds_history` |
| `11_betexplorer_scraper.py` | BetExplorer | `betexplorer_matches/odds/avg_odds` + `match_results` |
| `13_bet365_scraper.py` | Bet365 | `bet365_fixtures/odds/inplay` |
| `16_flashscore_results_scraper.py` | Flashscore 赛果 | `match_results`（结算依赖） |
| `16_footballdata_scraper.py` / `23_football_data_scraper.py` | football-data.co.uk | `fd_matches` |
| `10_understat_xg_scraper.py` / `17_understat_scraper.py` | Understat | `understat_xg_matches/teams` / `understat_matches` / `understat_team_stats` |
| `11_fbref_xg_scraper.py` / `22_fbref_scraper.py` | FBref | `fbref_xg_teams` / `fbref_team_stats` / `fbref_match_stats` |
| `12_statsbomb_national_xg_scraper.py` | StatsBomb Open Data | `statsbomb_national_xg_*` |
| `18_espn_scores_scraper.py` | ESPN 公开 API | `espn_scores` |
| `19_whoscored_scraper.py` / `24_betfair_scraper.py` | WhoScored / Betfair（实验性） | `whoscored_*` / `betfair_exchange_odds` |
| `25_transfermarkt_scraper.py` | Transfermarkt | `transfermarkt_squad_values` / `transfermarkt_injuries` |
| `26_multi_bookmaker_scraper.py` | WH/DK/FD/Unibet/Bovada | `multi_bookie_odds` |
| `29_qiety_yb_full_scraper.py` / `28_..._v2` / `30_qiety_history` | 企鹅体育 YB（亚博） | `qiety_matches` / `qiety_odds_snapshots` / `multisource_odds` / `qiety_history` |
| `46_qiety_lineup_scraper.py` | 企鹅体育阵容 | `qiety_lineups/standings/h2h_history/lineup_scrape_log` |
| `38_qiety_correct_score_scraper.py` | 企鹅比分盘 | `yb_correct_score_odds` |
| `39/40/41/42_okooo_*` | 澳客网 | `okooo_ren9_matches/snapshots` / `okooo_injuries` / `okooo_bet_flow` / `okooo_football_odds` / `okooo_basketball_odds` |
| `33_corner_odds_scraper.py` / `37_corner_stats_scraper.py` / `48_qiumibao_corner_scraper.py` | 角球盘口/统计/188bifen | `corner_live_odds` / `corner_stats_final` / `corner_stats_pending` / `qiumibao_*` |
| `44_lottery_500com_*` / `45_titan007_*` / `47_sporttery_hafu_*` | 500彩票网 / 球探 / 竞彩官网 | `lottery_sfc_matches/prizes` / `titan007_match_history` / `sporttery_odds_*` |
| `46_sportmonks_fixtures_scraper.py` | Sportmonks v3 | `sportmonks_fixture_identity/season_identity` |
| `_elo_scraper.py` | clubelo.com + eloratings.net | `club_elo` / `national_team_elo` |
| `import_corner_stats.py` | 由 `fd_matches` 计算 | `corner_team_stats` / `corner_league_baseline` |
| 篮球系（`27/28/29/30/31/23_bball_ref`） | EuroLeague feeds / LiveScore / BetExplorer / FlashScore / NBA stats / BBR | `euroleague_*` / `ls_bball_*` / `be_bball_*` / `fs_bball_*` / `sofa_bball_*` / `nba_matches` / `bballref_*` |

### 1.5 主入口与依赖

```bash
python -X utf8 00_命中系统.py                 # 全量：爬虫 → 匹配 → 共识 → 模型 → 推荐单 → 投注计划
python -X utf8 00_命中系统.py --date 2026-09-20
python -X utf8 00_命中系统.py --no-scrape     # 跳过爬虫只做整合
python -X utf8 00_命中系统.py --fast          # 跳过慢速爬虫（is_slow=True 档）
python -X utf8 21_auto_settle.py --date 2026-09-20 [--shadow]
```

`requirements.txt`（项目原样）：requests / pandas / numpy / sqlalchemy / openpyxl / beautifulsoup4 / lxml / scipy / scikit-learn / tensorflow / torch / streamlit / tavily-python / pycryptodome。
实际代码另隐式依赖：`curl_cffi`（Flashscore/FotMob/Pinnacle-OddsPortal 的 TLS 指纹）、`playwright`（OddsPortal/qiety 历史）、`nodriver`+真实 Chrome（FBref/WhoScored）、`python-dotenv`（config）。

`_param_overrides.json` 是**运行时参数覆盖**，目前只有 `HIT_SCORE_GLOBAL_THRESHOLD = 0.70` 及校准说明（含 2026-07-20 自动校准误改成 0.55、7-22 手动改回 0.70 的完整来龙去脉，值得读）。优先级：`_param_overrides.json` > `config.py`。

---

## 2. 命中分（hit score）完整公式

### 2.1 v1 公式（`00_命中系统.py: compute_hit_score`，主用）

```
coverage_score   = 0.5 + min(source_count / 2.0, 1.0) * 0.5      # 数据覆盖度
odds_consistency = 0.5 + min(source_count_odds / 2.0, 1.0) * 0.5 # 赔率一致性
confidence_score = clamp(model_prob, 0, 1)                       # 模型置信度

base = 0.30*coverage_score + 0.30*odds_consistency + 0.40*confidence_score
```

> 注意：分母是 **2**，不是 4——代码注释解释「系统最多 2 个实时赔率源，单源 Pinnacle 即视为 2 档可信度」。

接着 5 道依次相乘的修正（顺序不能换，代码就是这个顺序）：

```
① 热门惩罚：若 model_prob > 0.55
   calib_penalty = min(0.25, (model_prob - 0.55) * 1.0)
   hs *= (1 - calib_penalty)                       # 隐含"庄家高估热门"，最高砍 25%

② 市场偏置：bias_mult, market_min_threshold = get_market_bias(sport, market, outcome)
   hs *= bias_mult                                 # 不在白名单 → bias=0.0 → hs=0 → 自动出局
   例外（运行时转正后自动把 0 改 1.00）：
     - outcome=under 且 market∈{total, team_total, team_total_*}：_under_validation_status 通过
     - market=moneyline：_moneyline_validation_status(sport, outcome) 通过（按 sport×outcome 分开判）

③ 联赛 Tier 加成：hs *= LEAGUE_TIER_BOOST[tier]
     wc_boost 1.10 / tier1 1.00 / tier2 1.03 / tier3 0.88 / tier4 0.60
     tier 由 _get_league_tier() 关键词判定；杯赛/预备队/青年队/女足邀请赛关键词先排除

④ 截断 hs = round(clamp(hs, 0, 1), 4)

⑤ Kelly=0 折减：若 kelly <= 0 → hs = round(hs * 0.70, 4)   # "高覆盖但无价值边际"惩罚
```

返回：`hit_score / value_edge / kelly_fraction / confidence(高≥0.75、中≥0.60、低) / market_min_threshold`。

配套计算（同函数内）：
```
fair_odds  = 1 / model_prob
value_edge = consensus_odds / fair_odds - 1
kelly      = (model_prob*odds - 1)/(odds - 1) * KELLY_FRACTION(0.25)，clamp[0, KELLY_MAX_RATIO=0.25]
```

**推荐门槛**（`generate_recommendations`，全部是 AND）：
```
effective_threshold = max(market_min_threshold, HIT_SCORE_GLOBAL_THRESHOLD=0.70)
hit_score >= effective_threshold
kelly_fraction   > 0
model_prob       >= _min_prob_gate        # 0.50；足球 1x2 平局为 0.20（且先过等渗校准）
（under）handicap >= UNDER_MIN_HANDICAP=2.5
（spread）必须存在"打赢盘口"口径的概率，不许用独赢概率冒充
每场最多 MAX_RECS_PER_MATCH = 1 条，每日 MAX_DAILY_RECOMMENDATIONS = 7 条
```

**MARKET_BIAS 白名单**（`config.py`，`(倍率, 该市场专属最低门槛)`）：

| sport | (market, outcome) | 倍率 | 门槛 |
|---|---|---|---|
| football | (total, over) | 1.05 | 0.65 |
| football | (team_total, over) | 1.10 | 0.65 |
| football | (moneyline, home/away) | 1.10 | 0.65 |
| basketball | (total, over) | 1.20 | 0.65 |
| basketball | (team_total, over) | 1.10 | 0.65 |
| basketball | (total_flip, under) | 0.90 | 0.70 |
| basketball | (moneyline, away) | 1.15 | 0.65 |
| 兜底/未知 | (total, over) 1.10 / (team_total, over) 1.05 | | 0.65 |

不在表内 = 倍率 `0.0` → 命中分归零 → 绝不进正式推荐（只进影子桶追踪）。这就是「只推大球/不推小球」的实现方式，不是靠 if 语句，而是靠偏置表。

### 2.2 v2 公式（并行跑，用于对比复盘）

```
edge_score    = min(max(0, model_prob - implied_prob)/0.20, 1.0)
kelly_score   = min(kelly_fraction/0.05, 1.0)
quality_score = min(source_count/2.0, 1.0)
hs_v2 = 0.50*edge + 0.30*kelly + 0.20*quality
```
门槛 `HIT_SCORE_V2_THRESHOLD = 0.55`，且额外要求 `kelly>0` 且 `model_prob>=0.50`、非"让球无口径概率"。
v2 不受 v1 的 MARKET_BIAS 门控影响（所以 v2 会出现在 `shadow_recommendations` 的 `gated_v2` 桶）。

### 2.3 角球自己的命中分（`corner_model._hit_score`，另一套）

```
hs_corner = min(0.999, 0.5 + edge*2.5 + p_model*0.10)
```
国家队赛事另有「强弱悬殊惩罚」：|ELO 差| ≥350/250/150 → μ 减 1.5/1.0/0.5，over 方向命中分再乘 0.65/0.75/0.88；任一方场均角球 < 3.8 → μ−0.4 且再乘 0.92。

### 2.4 关于「+0.25 偏差修正」

任务书提到的「偏差修正 +0.25」**不是命中分的一部分**，它只出现在**角球模型**：`corner_model.MU_BIAS_CORRECTION = 0.25`（回测发现模型系统性低估角球，μ 加 +0.25）；投注单标题里打印的「偏差修正+0.25」就是它。
足球侧没有「+0.25 命中分修正」——足球的校准是另一条线：平局概率走等渗回归校准 `_apply_draw_calibration()`（`_fit_draw_calibration.py` + `draw_calibration_curve` 表，>30 天自动重拟合），热门惩罚是「model_prob>0.55 递减扣分最高 −25%」。

---

## 3. p融合（p_fusion）

`00_命中系统.py: get_model_probs()`

```
p_fusion = 0.50 × P_book + 0.30 × P_poisson + 0.20 × P_elo
```
权重在 `config.py`：`FUSION_W_BOOK=0.50 / FUSION_W_POISSON=0.30 / FUSION_W_ELO=0.20`。
注释里明确写了：这组权重是**初始设定（首个 commit 起从未做过权重扫描/回测）**，改它属于「模型调优」被项目宪章禁止，除非绑定新信息源 + 预注册 + 独立 CLV 纸面验收。

缺失降级（代码原文口径）：
- 缺 P_book：(W_POISSON+W_ELO) 按比例重分给 P_poisson / P_elo
- 缺 P_elo：全给 P_poisson；缺 P_poisson：全给 P_elo；三者全缺 → 返回空 dict，该候选无概率

### 3.1 P_book：庄家概率取自谁、怎么去水

- 现货价 = `consensus_odds`：由 `compute_consensus_odds()` 按 `(market, outcome, 盘口线)` 分组、**同一规范化来源只留权重最高的一条**，然后做**加权算术平均**（不是中位数、不是最优价）。多个盘口线时只保留「来源数最多」的那条作为主盘口。
- 来源权重 `SOURCE_WEIGHTS`：pinnacle 1.00、theodds 1.00（`SOURCE_CANONICAL` 映射到 pinnacle，去重后算 1 个源）、betfair 0.95、bet365 0.90、oddsportal 0.85、betexplorer 0.80、qiety_yb 0.80、sofascore 0.75、flashscore 0.70、okooo_jingcai 0.55 …
- **主力是 Pinnacle**：`15_pinnacle_oddsportal_scraper.py` 实际爬的是 Pinnacle Guest API（旧名 theodds），`sharp_odds` 取权重最大来源的那条原始价。
- **P_book = 1 / consensus_odds 的裸隐含概率（单一 outcome 口径），没有对该场三个方向做归一化去水**。也就是说 `P_book` 内含庄家水位（overround），并未 devig。这是本系统的一个重要口径特点：水位被当作真实概率的一部分吸收，可通过比较 `model_prob`（融合后）与 `implied_prob` 看出系统性偏差（例如正式单里 model_prob 0.82 vs implied 0.41）。
- 反面参照：`corner_model._implied_fair()` 与 `prediction_football` 的 `_devig_two_way/_devig_three_way` **是**做了归一化去水的（两路 `ro/(ro+ru)`、三路同理），且 `_generate_correct_score_recs()` 对比分市场按全部已捕获比分隐含概率之和归一化。所以「去水」在系统内**并存两种口径**：主池（consensus/1x2/大小球）不去水，比分/角球/预测模型的 odds 口径去水。

### 3.2 P_poisson / P_elo 怎么来、用了哪些特征

- **P_poisson**：`poisson_model_v2.compute_advanced_poisson()` + `predict_football` 的 DC 修正。
  λ 来源分层：FotMob(`_FM_CACHE`) / Understat(`_US_CACHE`) / football-data(`_FD_CACHE` 射正) / FBref（已废弃）等 xG 缓存 → 球队主客场进攻率、防守率、近期形态（长期 60% + 近期 40%，指数衰减 0.06/场）、联赛基线（`league_baseline` 的 home_attack/away_attack）、主场优势系数 `POISSON_HOME_ADV_XG=1.08` / `POISSON_HOME_ADV_SOT=1.06`；样本 < 5 场（稀疏联赛 3 场）无 λ。比分用 Dixon-Coles τ 修正 ρ（MLE 拟合，边界 ±0.30，默认 −0.10），联合网格 N_GOALS=8。
  `total_prob_at_line(p_total, line)` 把分布折算到**真实盘口线**（历史 bug：固定用 2.5 线导致 P_book 与 P_poisson 错位，65% 的场次盘口不是 2.5）。
- **P_elo**：读 `market_prediction_snapshot`（`predict_football` 写入）里的 ELO 快照概率；`_build_elo`：K=32、主场 +60、初始 1500，来源 `fd_matches` 历史结果（另有 `club_elo`/`national_team_elo` 爬虫表与 `_NAT_ELO` 缓存）。
- **七层融合权重**（`05_泊松凯利预测模型.py`，另一条更远的实验线，**未进 p_fusion**）：泊松 0.40 / LSTM 0.15 / Transformer 0.15 / xG 0.10 / GNN 0.08 / RL 0.07 / 多模态 0.05。

---

## 4. 各市场候选生成与过滤

主池（`generate_recommendations()`，遍历 `unified_matches` × `unified_odds`/`consensus_odds`，窗口 = 当前时刻 → 次日 12:00 北京时间）：

| 市场 | 生成/过滤要点 |
|---|---|
| 大小球 total | 走 MARKET_BIAS 白名单；**under 先被 bias=0 归零**（除非 `_under_validation_status` 转正），并单独写 `under_shadow_bets` 追踪；under 还需 `handicap>=2.5`；`BBALL_TOTAL_CAP` 系列做篮球总分上限；盘口线用真实线重算概率 |
| 让球 spread | 必须有"打赢盘口"的概率口径，否则排除（2026 修 Bug：曾用独赢概率冒充让球概率）；无 handicap 一律 pending 不结算 |
| 胜平负 moneyline | 足球 = 3 选 1（home/draw/away，平局为独立 outcome，打平不退本金）；平局先过等渗校准，门槛 prob>=0.20 & edge>=0.03；篮球按 outcome 分开转正（客胜曾 +74.6% ROI、主胜 −24.9%） |
| 球队大小 team_total / _home / _away | 主客队各自独立盘口线（2026 修「主客队身份」bug），共用 team_total 同一档 bias；已换成 `compute_team_total_probs()` 单队自己近 40 场得分均值/标准差建模 |
| 角球 corner | `corner_model.generate_corner_slip()`；EV≥10%；混合分布（正态≤10.5 / 负二项≥11.5）；转正门槛 `CORNER_VALIDATION_MIN_SAMPLES=30 / MIN_ROI=0`；未转正时只出「观察单」格式，不写 `corner_recommendations` |
| 半全场 HT/FT | `precomputed_htft_shadow`（predict_football 写 `market_prediction_snapshot(market_group='HTFT')`）；9 格联合概率；**两版并行**：`htft`（过 `_HTFT_LEAGUE_WHITELIST` 联赛白名单）与 `htft_nofilter`（不过滤），用于验证白名单到底有没有用 |
| 比分 correct_score | `_generate_correct_score_recs()`：DC 联合概率 vs 真实盘口去水隐含概率 → edge/Kelly/命中分；**长期不盈利**（全历史 n=128/ROI−30.6%，07-16 重校准后 n=14/ROI−100%）；未转正时只在比分预测单展示+写库统计，不占单注名额 |
| FotMob 系列 | `fotmob_1x2` / `fotmob_totals` / `fotmob_spread` / `fotmob_team_total` / `fotmob_corner` 都是**影子桶**（`shadow_recommendations` 表 `shadow_type` 字段），各自有 `_fotmob_*_validation_status()` 转正判定；`fotmob_corner` 需从 `pinnacle_corner_odds` 单独算，不能在主池现算 |
| LSTM 系列 | `lstm_1x2` / `lstm_moneyline` / `lstm_spread` 影子桶，来源 `team_lstm_state`（实为 EMA+AR(1)） |
| V2 替换公式 | `compute_hit_score_v2`，阈值 0.55，不受 v1 bias 门控；未过的进 `gated_v2` 桶 |
| 反着买 fade | `_generate_basketball_under_fade`（`basketball_under_fade_recs`）/ `_generate_basketball_moneyline_fade`（`basketball_moneyline_fade_recs`）/ `_generate_and_display_fade_manual`（人工批准转正，`formula_version='fade_manual'`：篮球小球最小赔率 `BASKETBALL_MONEYLINE_FADE_MIN_ODDS`） |
| league_ah_edge | `_generate_league_ah_edge()`：**不是模型信号**，是纯市场结构性错价规律（联赛级亚盘 edge），走人工批准转正 `formula_version='league_ah_edge'`，写 `league_ah_edge_recs` |
| 其他影子桶 | `injury_impact`（伤停，`okooo_injuries`）、`qiety_h2h`、`gated`（被 `_in_scope()` 拦下的反事实记录） |

**去重与截断**：影子桶按 `UNIQUE(unified_id, shadow_type, market, outcome, fetch_date)`；每桶每日有 top-N 截断（历史上有 top-10/每日截断，导致影子桶 population 不等于全部候选）。正式单 `hit_recommendations` 不受此截断。

---

## 5. 转正判定（_in_scope 等）

`_in_scope(r)` 是正式推荐的最后一道闸，只放行四个市场：

```python
total/over            → _total_over_validation_status(sport)["validated"]
team_total*/over      → _team_total_validation_status(football|sport, "over")["validated"]
moneyline             → _moneyline_validation_status(sport, outcome)["validated"]
correct_score         → _correct_score_validation_status()["validated"]
其余（含 corner, spread 影子, htft …） → False
```
被拦下的不进正式单，但会被写入 `shadow_recommendations.shadow_type='gated'`（反事实观察，仍照常结算），保证「如果当初放行会怎样」可回溯。

`_validation_result(rows, min_samples, min_roi)` 统计算法（所有市场共用）：

```
n = 已结算(win/lose) 条数（void/push/invalid/pending 不计）
roi        = mean(win: odds-1, lose: -1)                 # 平注 ROI
win_rate   = wins / n
单尾 95% CI 下界 > 0    （用 z=1.645 近似 t，等价于拒绝 H0: 真实ROI<=0）
近 recent_n=30 条（按 fetch_date 升序）平注 ROI 点估计 >= min_roi   ← 防"老样本摊薄近期衰减"
最大回撤 max_drawdown 仅展示，不参与判定
n < 2 时退化为只看点估计
→ 通过后再过 promotion_gate.check_promotion_gate(gate_key)：
   ① 预注册：promotion_registry.json 必须有该桶且 registered_at 早于样本窗口末端
   ② 多重比较：每自然季度最多 1 个新桶转正（QUARTERLY_PROMOTION_QUOTA=1）
   被拦 → validated=False 且 gate_blocked 记录原因
```
各市场阈值：`*_VALIDATION_MIN_SAMPLES = 30`，`*_VALIDATION_MIN_ROI = 0.0`（correct_score 为 +0.05 强制继续积累），`VALIDATION_RECENT_MAX_AGE_DAYS = 21`。

合理性吐槽点（供外部助手留意）：这里的"近 30 注"用的是 `fetch_date`（下注日），而 `VALIDATION_RECENT_MAX_AGE_DAYS` 是另一个独立的时间新鲜度参数，两者不是同一件事，代码里没有把「最近一次结算距今多少天」纳入判定。

---

## 6. 自动结算（21_auto_settle.py）

### 6.1 结果判定 `_settle_result(market, outcome, handicap, hs, as, odds, hs_ht, as_ht)`

| market | 判定 |
|---|---|
| `ht_ft` | 半场结果 + 全场结果必须**同时**猜中才算 win（无 push） |
| `moneyline` / `1x2` | home: hs>as；away: as>hs；draw: hs==as。**打平判 lose（不是 push）**——足球是 3 选 1 市场，平局是独立可下注结果，2026-09-05 修过这个把平局退款当正确行为的 bug |
| `spread` | handicap 为 None → pending（**不许按 pick'em 处理**）；否则 home: hs+spread>as，away: as+spread>hs，相等 push。2026-07-22 有 92 条历史 spread 因该 bug 被误判，已手动标 `status='invalid'` 排除（真实盘口线已不可考，只能排除不能重判） |
| `total` / `totals` / `ou` | 按 handicap 与 hs+as 比较，相等 push |
| `team_total` / `_home` / `_away` | 按对应单队得分与该队盘口线比较 |
| 其他/无比分 | pending |

`void` = 赛程取消/推迟（未开赛或状态异常），`invalid` = 历史脏数据，`inuse/push` = 走盘退款。

### 6.2 比分来源（4 层）

1. `unified_matches` 统一 ID 精确匹配
2. 模糊队名匹配 `_layer2_fuzzy_scores` / `_fuzzy_match`（标准化 + 相似度）
3. FotMob 兜底 `_apply_fotmob_goal_fallback` / `_match_fotmob_goal_score`（含角球 `_get_fotmob_corner_totals`）
4. 188bifen(`qiumibao`) 兜底 `_apply_qiumibao_goal_fallback`、角球 `_match_corner_from_qiumibao`
角球另有 `_corner_is_finished(status, minute, kickoff_utc)` 判断比赛是否真的踢完（防提前结算）。

### 6.3 盈亏口径（重要，两类混存）

- `under_shadow_bets` / `team_total_shadow_full` / `hit_recommendations`：`profit_loss` 是**元（¥，按 stake 折算）**，输的时候是 `-1.33/~-3.7` 这种非整数
- `shadow_recommendations` / `over_shadow_bets` / `moneyline_shadow_full` / `corner_recommendations`：`profit_loss` 是**平注单位（1u）**，输 = `-1.0`，赢 = `odds-1`
- `hit_recommendations` 只有 67/1705 行有 `stake` 非空，其余 profit_loss 为空 → 该表不能直接算 ROI，要自己按 `status` + `best_odds` 重建平注 ROI

---

## 7. 凯利与投注计划

- **K 值**：`K = max(0, min(p*odds-1, ...)/(odds-1) × KELLY_FRACTION)`，`KELLY_FRACTION = 0.25`（**K₁/₄**），上限 `KELLY_MAX_RATIO = 0.25`。投注单里打印的公式是 `K₁/₄ = (p融合×赔率-1)/(赔率-1)×0.25`。
- **按命中分调整注额**（`_generate_bet_plan` + `DYNAMIC_KELLY_SCALE`）：基准 `base_bet = BANKROLL(200) × SINGLE_BET_PCT(0.02) = 4 元`；本金 < `HALF_BANKROLL(120)` 时整体减半。
  | hit_score | 倍率 | 实际注额 |
  |---|---|---|
  | [0.90, 1.01) | 2.0 | 8 元 |
  | [0.80, 0.90) | 1.5 | 6 元 |
  | [0.70, 0.80) | 1.0 | 4 元 |
  | [0.60, 0.70) | 0.7 | 2.8 元 |
  | [0.00, 0.60) | 0.5 | 2 元 |
  （注释里写的「=12 元/9 元/6 元/4 元/3 元」是旧基准 6 元的遗留注释，与当前 4 元基准不一致，属于文档陈旧，以公式为准）
  单注最多 `SINGLE_BET_MAX = 10` 注；`correct_score` 未转正不占名额。
- **串关**（`PARLAY_CONFIG`，2~8 串 1）：`n: (本金百分比, 每日最多几单)` = 2:(2%,4单) 3:(1%,3) 4:(1%,2) 5~8:(1%,1)。
  只串 `PARLAY_ELIGIBLE_MARKETS = [(total,over),(team_total,over),(spread,home)]`，且 `kelly>0`、`kickoff` 未开赛、同一 `unified_id` 不得在同一注内重复（`_is_independent`）。池子取按 hit_score 排序的前 `min(n*3, len)`，`combinations` 穷举后**保留第一个最高分组合 + 随机采样其余**（所以每天的组合不完全可复现；单注额只按「单注」落库，串关额不写 `hit_recommendations`）。
- **风控**：日亏上限 30% 本金（60 元）、连亏 3 注停手、本金 < 120 元投注减半、`MAX_DAILY_RECOMMENDATIONS = 7`、`MAX_RECS_PER_MATCH = 1`、赔率区间 `MIN_RECOMMEND_ODDS 1.75 ~ MAX_RECOMMEND_ODDS 3.50`、`UNDER_MAX_DAILY = 3`（小球专项）。
- **真钱开关**：`BETTING_MODE` 默认 `paper`（写 `D:\lucky_paper` + 水印「[纸面模式-非真钱投注]」）；只有 `BETTING_MODE=live` **且** `ENABLE_LIVE_BETTING=1` 才写 `D:\lucky`。

---

## 8. 数据表：来源库、行数、日期范围、时区

**来源库：全部来自 `D:\cl\qqsj\data\sports_data.db`**（4.9 GB，229 张表）。
目录下另有 `data\sports_data_backup_fix_20260912.db`（4.0 GB，193 表），已核对为**主库的真子集**（同一批表行数更少，如 under_shadow 2964 < 3020），故未导出，避免重复数据误导。

导出方式（只读，官方脚本）：`python -X utf8 export_user_db.py --db D:\cl\qqsj\data\sports_data.db --out <dir> --tables …`

| 文件 | 表 | 行数 | 状态分布 | 日期范围（fetch_date / kickoff） |
|---|---|---|---|---|
| `under_shadow_bets.csv.gz` | under_shadow_bets | 3020 | win 699 / lose 842 / push 53 / void 1337 / pending 89 | 2026-06-25 → 2026-09-20 |
| `shadow_recommendations.csv.gz` | shadow_recommendations（多影子桶） | 3851 | lose 1894 / win 1407 / void 332 / push 54 / pending 164 | 2026-05-29 → 2026-09-20 |
| `hit_recommendations.csv.gz` | hit_recommendations（正式单 + 全部 formula_version） | 1705 | void 552 / lose 445 / win 329 / invalid 313 / push 26 / pending 20 / in_slip 20 | 2026-05-28 → 2026-09-20 |
| `team_total_shadow_full.csv.gz` | team_total_shadow_full | 632 | win 237 / lose 254 / void 128 / pending 13 | 2026-07-22 → 2026-09-20 |
| `moneyline_shadow_full.csv.gz` | moneyline_shadow_full | 446 | lose 225 / win 106 / void 94 / pending 21 | 2026-07-24 → 2026-09-20 |
| `over_shadow_bets.csv.gz` | over_shadow_bets | 326 | win 131 / lose 134 / void 30 / push 19 / pending 12 | 2026-08-02 → 2026-09-20 |
| `corner_recommendations.csv.gz` | corner_recommendations | 121 | lose 43 / win 40 / pending 25 / void 9 / push 4 | 2026-06-14 → 2026-09-05 |
| `legacy_team_total_under_recs.csv.gz` | legacy_team_total_under_recs | 52 | win 26 / lose 21 / pending 5 | 2026-07-25 → 2026-09-20 |
| `basketball_under_fade_recs.csv.gz` | basketball_under_fade_recs | 31 | win 14 / lose 16 / pending 1 | 2026-08-02 → 2026-09-18 |
| `basketball_moneyline_fade_recs.csv.gz` | basketball_moneyline_fade_recs | 31 | win 11 / lose 5 / pending 15 | 2026-08-01 → 2026-09-20 |
| `league_ah_edge_recs.csv.gz` | league_ah_edge_recs | 23 | pending 23（一条未结算） | 2026-08-28 → 2026-09-20 |
| `settle_summary.csv.gz` | settle_summary | 8 | 每日结算汇总（wins/losses/pushes/stake/pnl/roi/win_rate） | settle_date 只有 2026-07-01 |

`hit_recommendations` 细分：`formula_version` = v1 1315 / v2 311 / fade_manual 56 / league_ah_edge 23；`sport_code` = football 1083 / basketball 622；market 分布 total/over 412、moneyline/away 189、spread/away 184、moneyline/home 181、total/under 154、spread/home 151、team_total/under 142、team_total/over 99、moneyline/draw 50，其余为 correct_score 各比分。

`shadow_recommendations` 影子桶分布（`shadow_type`）：spread 492、htft 413、1x2 386、team_total 369、fotmob_totals 287、lstm_spread 245、gated 227、moneyline 224、fotmob_team_total 222、fotmob_spread 193、lstm_1x2 159、fotmob_1x2 156、fotmob_corner 141、htft_nofilter 119、qiety_h2h 103、gated_v2 75、lstm_moneyline 38、injury_impact 2。

### 时区（**务必注意，字段间不一致**）

| 字段 | 时区 | 依据 |
|---|---|---|
| `kickoff_utc` | **UTC**。但格式混乱：一部分是 `2026-07-24T22:00:00Z`，另一部分是 `2026-06-30 23:00:00`（无 Z、空格分隔，实际仍是 UTC） | 代码 `_run_one_date` 里显式声明 naive 当 UTC 再转 +8；注释 8090 行专门修过「本机时区恰是北京时间，naive UTC 被误当北京时间直接显示，差 8 小时」 |
| `created_at` / `fetch_date` | **北京时间（UTC+8），但无时区标记**（`datetime.now()`，本机 TZ 就是 Asia/Shanghai） | 全系统用 `datetime.now()` 不带 tzinfo |
| `settle_summary.created_at` | 部分行带 `+08:00`，部分行是微秒无时区 | 表内自身不一致 |
| 推荐窗口 | fetch_date 当天 00:00(北京) → 次日 12:00(北京) → 转 UTC | `generate_recommendations` 的 `win_end_bj` |

所以：**`kickoff_utc` 当 UTC 解析要 +8 才是北京时间；`created_at`/`fetch_date` 已经是北京时间，不要再 +8。**

### 直接用这批数据能算出的基准（我已验算，供你交叉核对）

`shadow_recommendations` 按 `shadow_type` 的平注 ROI（仅 win/lose，profit_loss 单位=注）：

| 桶 | n | 命中率 | 平注 ROI |
|---|---|---|---|
| fotmob_spread | 162 | 54.3% | **+8.1%** |
| fotmob_team_total | 212 | 53.3% | **+8.1%** |
| fotmob_totals | 260 | 54.2% | +4.2% |
| team_total | 331 | 51.1% | +4.0% |
| lstm_spread | 233 | 51.9% | +0.3% |
| moneyline | 160 | 43.8% | +0.6% |
| lstm_moneyline | 37 | 40.5% | +3.7% |
| gated_v2 | 40 | 37.5% | +4.3% |
| htft | 374 | 27.8% | −1.2% |
| fotmob_corner | 130 | 50.0% | −5.9% |
| spread | 425 | 48.2% | −6.9% |
| lstm_1x2 | 147 | 38.1% | −13.0% |
| fotmob_1x2 | 141 | 36.2% | −21.3% |
| qiety_h2h | 74 | 28.4% | −25.5% |
| 1x2 | 297 | 30.6% | −27.7% |
| **gated（被 _in_scope 拦下的反事实）** | 200 | 28.0% | **−42.1%** |

其它表合计（win/lose）：under_shadow_bets −326.37（元，n=1541）、over_shadow_bets −12.50（注，n=265）、moneyline_shadow_full −78.18（注，n=331）、team_total_shadow_full −2.98（注，n=491）、hit_recommendations +12.91（元，n=80 有 profit_loss 的行）。
这些数字说明：**目前只有 FotMob 三个市场和 team_total 是正 ROI 且样本还行；主池 1x2/spread 明显为负；`gated` 桶 −42% 说明"被拦下来是对的"。**

---

## 9. 没找到 / 不确定的地方（诚实清单）

1. **`03_实时赔率抓取.py` 依赖的 sportsbook-api2 / odds-feed 私有接口**：文件在包内，但它调用的第三方聚合服务（RapidAPI 系）真实 key 与订阅状态不明，无法确认可达性。
2. **`04_2_Football_xG_Module` / `05_泊松凯利预测模型` / `05b_国家队预测适配层` 是否真的每日在跑**：它们在 `_run_one_date` 的爬虫调度列表里（priority 3），但产出表（`football_xg_stats`/`basketball_prediction`/`prediction_snapshot`）没有随包导出，无法验证是否有新数据。
3. **「七层融合」（WEIGHT_POISSON…WEIGHT_MULTIMODAL）与 p_fusion 的关系**：注释说七层融合是另一条实验路线，代码里 p_fusion 只用 3 个分量；七层权重实际被哪些脚本消费无法从静态代码确定。
4. **`TEAM_TOTAL_VALIDATION_*` 与 `fotmob_team_total` 是否共用同一份结算样本**：两边分别有 `team_total_shadow_full` 表和 `shadow_recommendations` 桶，交叉去重逻辑不确定，统计时可能重复计数。
5. **`_in_scope()` 只放行 4 个市场，但 `hit_recommendations` 里存在 `spread`（335 条）与 `team_total/under`**：说明这批是历史遗留（v1 早期 `_in_scope` 不同，或走 `league_ah_edge`/`fade_manual` 独立通路），**当前代码不会再产生 spread 正式单**。做 ROI 统计时必须按 `formula_version` + `created_at` 分段，否则会把不同代际的规则混在一起。
6. **`gated` 桶的 top-N 截断**：影子桶每日有截断（历史上 top-10），所以桶内 ROI 不等于「全部候选」的 ROI，只等于「被留下那批」的 ROI。截断逻辑散在多个 `_generate_*` 里，我未能穷尽确认每个桶的 N。
7. **`corner_model` 里 `_fotmob_corner_probs_safe` 与 FotMob 角球影子桶（`shadow_type='fotmob_corner'`）的关系**：两者共用 `pinnacle_corner_odds`，但一条进 `corner_recommendations`（正式候选），一条进 `shadow_recommendations`（影子），是否同一批比赛有重叠未确认。
8. **`_param_overrides.json` 的生效范围**：`config.py` 只在 import 时读一次并覆盖模块级常量；已经 import 了旧的 `HIT_SCORE_GLOBAL_THRESHOLD` 的模块（`from config import …`）会拿到副本，运行中改 json **不会**热更新。多进程跑批时以子进程各自 import 的时刻为准。
9. **`MAX_DAILY_RECOMMENDATIONS = 7` / `MAX_RECS_PER_MATCH = 1` 的实际执行点**：`generate_recommendations` 里有 `_in_scope` + 截断，但"每场 1 条"是在 SQL 层用 `ROW_NUMBER()` 还是 Python 侧截断，我在 main 文件里只看到日志与解释性注释，未逐行确认实现位置。
10. **脱敏造成的功能缺口**：`15_pinnacle_oddsportal_scraper.py` 的 OddsPortal 解密口令/盐已改为 `REDACTED`；`35_theoddsapi_multi_scraper.py` 的 `QQSJ_ODDS_API_BUDGET_CAP` 默认值现在是 `"REDACTED"`（`int()` 会抛异常）。这两处在真跑前必须补环境变量。
11. **`settle_summary` 只有 2026-07-01 一天**：这张表的写入是历史一次性行为，不能当作「每日结算汇总」的完整序列。
12. **`moneyline_shadow_full` / `over_shadow_bets` / `under_shadow_bets` 三张表的 `void` 比例极高**（under 表 1337/3020 = 44% void）：`void` 的判定条件（未开赛/取消/比分缺失）在 `21_auto_settle` 里分散在多处，未逐一确认哪些情形会被误判为 void，建议外部助手先核 void 分布再算 ROI。

---

## 10. 复现命令

```bash
# 语法自检（不需要数据库/密钥）
python -c "import ast,glob;[ast.parse(open(f,encoding='utf-8-sig').read(),f) for f in glob.glob('code/*.py')];print('OK')"

# 读任意导出表
python -c "import gzip,csv;rows=list(csv.DictReader(gzip.open('data/under_shadow_bets.csv.gz','rt',encoding='utf-8')));print(len(rows),rows[0])"
```

Git LFS：`data/*.csv.gz` 由 `.gitattributes` 中的 `ref/hit_system/data/*.csv.gz filter=lfs` 规则追踪（`git lfs ls-files` 可验证）。
