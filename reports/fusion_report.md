# 融合预测报告

生成时间：2026-10-19

## 概述

使用 ML + LLM 混合系统，对 11 场比赛进行融合预测。
- ML 模型：分联赛 XGBoost（含 Elo、xG、伤病特征）
- LLM 研究：Grok Bot 提供伤停、近况、信心
- 融合规则：根据信心和伤停动态调整概率与阈值

## 结果汇总

| 比赛 | 调整类型 | 主胜概率 | 主胜赔率 | 推荐 |
|------|----------|----------|----------|------|
| Arsenal vs Chelsea | neutral | 51.0% | 1.60 | — |
| 拜仁 vs 多特 | mild_downgrade | 58.9% | 1.33 | — |
| **皇马 vs 巴萨** | neutral | 52.7% | 1.95 | **H (Edge 4.3%)** |
| **国米 vs 米兰** | neutral | 31.1% | 1.90 | **A (Edge 24.5%)** |
| 利物浦 vs 曼城 | neutral | 41.9% | 2.38 | — |
| 巴黎 vs 马赛 | neutral | 41.0% | 1.42 | — |
| 曼联 vs 热刺 | neutral | 59.2% | 1.57 | — |
| 马竞 vs 塞维利亚 | slight_upgrade | 65.2% | 1.33 | — |
| 尤文 vs 那不勒斯 | downgrade | 30.4% | 2.05 | — |
| 莱比锡 vs 勒沃库森 | neutral | 39.0% | 2.10 | — |
| 摩纳哥 vs 里昂 | neutral | 38.1% | 2.00 | — |

## 推荐详情

### 1. 皇马 vs 巴萨 — 主胜
- Edge: 4.3%
- EV: 2.7%
- 说明：模型略看好主队，市场赔率有小幅价值

### 2. 国米 vs 米兰 — 客胜
- Edge: 24.5%
- EV: 92.3%
- 说明：模型认为客队被显著低估，但高 Edge 需谨慎验证

## 融合规则效果

| 调整类型 | 场次 | 说明 |
|----------|------|------|
| slight_upgrade | 1 | 马竞 vs 塞维利亚（信心 0.70） |
| mild_downgrade | 1 | 拜仁 vs 多特（有伤停） |
| downgrade | 1 | 尤文 vs 那不勒斯（多伤停 + 低信心） |
| neutral | 8 | 无强信号 |

## 文件

- CSV：`reports/fusion_report_20261019_1520.csv`
- 队名映射：`src/team_mapping.py`
- 融合逻辑：`src/hybrid_predictor.py`
