# hit_system 数据集（供 GrokBot 复现分析）

导出时间: 2026-10-23T06:33:31Z
数据标签: `2026-10-23`

## 文件说明

| 文件 | 内容 | 关键字段 |
|---|---|---|
| `unified_matches.csv.gz` | 统一比赛表（多源去重后） | `unified_id`, `home_team_std`, `away_team_std`, `kickoff_utc`, `sources_json` |
| `hit_recommendations.csv.gz` | 正式推荐单 | `hit_score`(命中分), `model_prob`(p融合), `best_odds`, `formula_version`, `hs_over_obs` |
| `shadow_all.csv.gz` | 全部影子观察单合并 | `src_table`(来源表), `status`, `profit_loss` |
| `settled_results.csv.gz` | 已出结果的比赛 | `match_date`, 比分 |
| `soft_snapshots.csv.gz` | 软价快照（qiety） | `price_dec`, `captured_at_utc`, `qc_flag` |
| `pin_snapshots.csv.gz` | Pinnacle 快照 | `price_dec`(已转欧赔), `captured_at_utc` |
| `model_params.json` | 当前生效参数 | 阈值、权重、凯利分母 |

## 时区（重要）

- `created_at` / `created_at_bj` = **北京时间（UTC+8）**
- `created_at_utc` = 已减 8 小时，可直接与 `kickoff_utc` 比较
- 其余 `*_utc` 字段均为 UTC
- `kickoff_utc` 写法可能带 `Z`、带 `T`、或纯日期，比较前需归一化

## 复现要点

1. **过滤已开赛**：`created_at_utc < kickoff_utc`（注意归一化 `kickoff_utc`）
2. **命中分**：见 `hit_score` 列，门槛 0.70
3. **p融合** = 0.50×P庄家 + 0.30×P泊松 + 0.20×P_ELO
4. **凯利**：`kelly_fraction` = 全凯利 / 4
5. **HS-OVER-OBS**：`hs_over_obs=1` 表示足球大球、命中分≥0.70、赔率≥1.80、formula为v1
6. **v2 价值单**：`--full` 模式下无 v2 数据（v2 单独立存放，见 `exports/hit_system_v2/`）

## 已知缺口

- `soft_odds_snapshots.pinn_id` 恒为 NULL（qiety 侧无此 ID），需用 `home_team`+`away_team`+`kickoff_utc` 匹配
- 库里无 `bet_plan` 表，投注计划未持久化
