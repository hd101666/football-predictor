# Football Prediction System

基于机器学习的足球比赛预测与推荐系统。优先支持欧洲五大联赛，使用免费数据源，XGBoost 模型，支持价值投注筛选与历史回测。

## 功能概览

- 数据下载与清洗（五大联赛历史数据）
- 特征工程：Elo 评分、近期状态、xG、伤病负担、交互特征
- 分联赛校准模型（XGBoost + Isotonic Calibration）
- 多盘口支持：1X2、让球、大小球、BTTS、角球、半全场
- 价值投注筛选（高信心、少而精）
- 信号一致性检查（Elo vs xG 冲突降级 / 强一致提升）
- 历史回测

## 快速开始

```bash
cd football_predictor
pip install -r requirements.txt

# 训练分联赛模型（推荐）
python main.py train_per_league

# 生成预测与推荐
python main.py predict
```

## 推荐阈值（当前严格标准）

| 条件 | 阈值 |
|------|------|
| 模型概率 | ≥ 0.62 |
| Edge | ≥ 0.10 |
| EV | ≥ 0.06 |
| 高信心 | ≥ 0.72 |
| 中信心 | ≥ 0.66 |

只有同时满足概率、Edge、EV 的比赛才会进入推荐。

## 信号逻辑

- **有意义冲突**：Elo 与 xG 方向相反且 `|xG_Diff| > 0.1` → 降一级信心
- **严重冲突**：Elo 看好客队但 xG 看好主队 → 再降一级
- **强一致**：同向且 `|EloDiff| > 50` 且 `|xG_Diff| > 0.15` → 提升一级信心

## 项目结构

```
football_predictor/
├── main.py                    # 入口脚本
├── requirements.txt
├── README.md
├── src/
│   ├── config.py              # 配置与阈值
│   ├── data_loader.py         # 数据下载与清洗
│   ├── features.py            # Elo + 状态特征
│   ├── xg_features.py         # 赛季级 xG
│   ├── xg_match.py            # 单场级 xG（Understat）
│   ├── injury_features.py     # 伤病负担特征
│   ├── model.py               # 基础 1X2 模型
│   ├── markets.py             # 多盘口模型
│   ├── per_league.py          # 分联赛校准模型
│   ├── recommendations.py     # 推荐逻辑
│   └── backtest.py            # 回测
├── data/                      # 缓存数据
├── models/                    # 训练好的模型
└── reports/                   # 预测报告
```

## 常用命令

```bash
# 训练基础 1X2 模型
python main.py train

# 训练所有盘口模型
python main.py train_markets

# 训练分联赛校准模型（含 xG + 伤病）
python main.py train_per_league

# 生成预测与推荐
python main.py predict
```

## 核心特征

| 类别 | 特征 | 说明 |
|------|------|------|
| Elo | EloDiff, HomeElo, AwayElo | 长期实力 |
| xG | xG_Diff, xGA_Diff, Home_xG_pm 等 | 进攻质量 |
| 交互 | Elo_xG_Interact | Elo × xG |
| 伤病 | Home_InjBurden, InjBurden_Diff | 上赛季伤病负担 |
| 状态 | FormDiff, AttackDiff | 近期表现 |

## 数据来源

- 比赛结果与赔率：football-data.co.uk
- xG：Understat（赛季聚合 + 单场）
- 伤病：Transfermarkt 衍生 panel（withqwerty/availability-data）

## 注意事项

- 首次运行需下载数据，请保持网络畅通
- 预测结果仅供参考，不构成投注建议
- 严格阈值下推荐数量较少，这是预期行为
- 追求正 ROI 需要持续回测验证

## 后续扩展方向

- 实时赛程接入
- 更多联赛支持
- 网页界面（Streamlit）
- 定时自动运行（Grok Bot）
