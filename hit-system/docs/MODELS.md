# 模型清单与回测 (Models)

> 全部数字来自本机真实运行与真实数据库，未做任何修饰。验证时间 **2026-10-30**。

## 一、模型清单

| 模型文件 | 名称 | 用途 | 算法 | 输入特征 | 输出 |
|---|---|---|---|---|---|
| `models/predict_football.py` | 足球独立预测模型 v2 | 足球 | 双引擎：泊松(≥10场历史) / ELO(数据不足降级) + Dixon-Coles 低比分修正 + 市场隐含λ融合 | 历史比赛(football_matches/fd_matches/betexplorer/fbref)、ELO评分、大小球与独赢赔率 | 1X2概率、比分矩阵、大小球概率、半全场9格 |
| `models/05_泊松凯利预测模型.py` | 泊松+Kelly 融合模型 | 足球 | 泊松分布 + 动态权重融合 + Kelly 仓位 | 多源融合数据、赔率 | 预测概率、Kelly 建议仓位 |
| `models/basketball_normal_model.py` | 篮球正态分布模型 | 篮球 | 正态分布 CDF（Abramowitz-Stegun 近似） | 历史得分均值/标准差、队均得失分 | 大小分概率、让分概率、公允赔率 |
| `models/04_1_LSTM_时序状态模型.py` | LSTM 时序状态模型 | 足球 | LSTM 序列建模 | 历史时序比赛数据 | 状态转移/趋势特征 |
| `models/04_2_Football_xG_Module.py` | xG 模块 | 足球 | xG→λ 转换 | understat/fbref xG | 期望进球λ |
| `models/corner_model.py` | 角球模型 | 足球 | 角球统计回归 | 角球历史、联赛基准 | 角球大小盘概率 |
| `models/poisson_model_v2.py` | 泊松模型 v2 | 足球 | 泊松/双泊松 | 队伍攻防强度 | 比分与总数概率 |
| `models/predict_basketball.py` | 篮球预测主流程 | 篮球 | 正态模型 + 赔率融合 | basketball_* 系列表 | 篮球推荐 |
| `models/promotion_gate.py` | 上架闸门 | 通用 | 分季度晋升校验 | 候选推荐、历史表现 | 是否允许对外推荐 |
| `models/05_8_Kelly_Capital_Allocation_Module.py` | Kelly 资金分配 | 通用 | 分数 Kelly | 概率、赔率、资金 | 单注仓位 |
| `models/05_7_Combination_Optimize_Module.py` | 串关优化 | 通用 | 组合枚举+期望价值 | 单场推荐 | 最优串关组合 |
| `models/backtest_engine.py` | 回测引擎 | 通用 | 逐场结算 | 历史预测+赛果 | 收益曲线、指标 |
| `models/05_9_Backtest_Module.py` | 回测模块(旧) | 通用 | — | — | ⚠ **文件已损坏，无法运行**（见下） |

## 二、特征说明（足球 `predict_football.py`）

| 特征 | 计算方式 | 数据表 | 时间窗口 | 是否只用赛前数据 |
|---|---|---|---|---|
| 泊松攻防强度 | 主客队进球率的联赛加权指数衰减（decay=0.06） | football_matches, fd_matches, betexplorer_matches, fbref_match_stats | 全历史，近期权重更高 | 是 |
| ELO 评分 | 逐场更新，K 值按分档 | 同上 | 全历史，**按 PIT 截断到预测日** | 是（截断已验证生效） |
| Dixon-Coles ρ | 极大似然拟合低比分联合分布 | fd_matches 等 | 近 3000~3100 场滚动 | 是 |
| 市场隐含λ | 由大小球+独赢赔率反解 λ | unified_odds | 当日赛前赔率 | 是 |
| HT/FT 状态系数 | 半场领先/平/落后三态下的攻防修正 | fd_matches(含半场) | 231,065 场训练样本 | 是 |
| xG | understat/fbref xG 归一化 | understat_xg_matches, fbref_match_stats | 当季 | 是 |

**防未来数据泄漏（PIT）**：`_earliest_kickoff_date()` 取今日赛事最早开赛日，ELO 训练集严格小于该日期。实测输出 `ELO截止=2026-10-23 用 274044/275339 场`，即主动剔除了 1,295 场未来数据。

## 三、回测结果（真实数字，含审慎提示）

来源：库内表 `backtest_summary`（1 行）、`backtest_curve`（181 点）、`backtest_daily`。

| 指标 | 数值 |
|---|---|
| 回测场次 | 180 |
| 命中数 / 胜率 | 88 / **48.89%** |
| 使用真实赔率场次 | 0（`real_odds_used=0`，180 场全部走 fallback 赔率） |
| 初始资金 → 终值 | 10,000 → 966,481.92 |
| 总盈利 | +956,481.92 |
| **最大回撤** | **-95.39%** |
| Sharpe | 0.2095 |

### ⚠ 必须诚实说明的三点

1. **这组数字不能当作模型盈利能力证明。** 180 场样本量过小，且 `real_odds_used=0` 说明全部用的是回退赔率而非真实历史收盘赔率，收益曲线不具参考性。
2. **最大回撤 -95.39%** 意味着任何实盘资金在这种资金曲线下都会先爆仓，终值 96 万在现实中不可达。
3. `backtest_daily` 表 3 行记录的 `matched/hit_count/roi` 全为 0，日期值出现 `'all'` 这种非法值，说明该回测落库逻辑本身有缺陷，尚未产出可用日度统计。

**结论：回测链路可用（能跑通并出数），但回测结论不可采信。** 真实有效的策略验证请参考各策略专项回测脚本，其数字需单独按样本量核对。

## 四、预测输出格式

每场比赛输出：
- `1X2 概率`：主胜 / 平 / 客胜（归一化后）
- `比分矩阵`：Dixon-Coles 修正后的各比分联合概率，取 argmax 为推荐比分
- `大小球概率`：按主线盘口的 Over/Under 概率
- `半全场 9 格`：HT/FT 联合概率
- `engine` 字段：标明本次由哪个引擎产出（elo / poisson / poisson_global / fotmob / 各 +market 融合）

**最优解选择逻辑**：一场比赛只给**一个**最优解——按期望价值（概率 × 赔率 − 1）最大者选取；若无正期望则不输出推荐。盘口线以实际核对到的赔率为准，不臆造盘口。

## 五、运行示例（真实输出）

### 足球（实测 2026-10-30 执行）

```bash
"C:/Users/Lucky/AppData/Local/Programs/Python/Python311/python.exe" predict_football.py --date 2026-10-23
```

真实输出：

```
  📐 Dixon-Coles rho MLE拟合: -0.0433（样本3052场）
  ⏱ HT/FT: 231065 场训练样本  |  状态系数: {'home_lead': (1.052, 0.998), 'draw': (0.955, 0.950), 'away_lead': (1.006, 1.093)}
  ⚽ 今日待预测: 533 场
  🏆 ELO: 1574 队  |  泊松: 32 联赛  |  ELO截止=2026-10-23  用 274044/275339 场
  📐 市场隐含λ融合：447/533 场有完整大小球+独赢真实赔率
  ⏱ HT/FT: 4716 行写入影子桶（524 场有完整9格）
  ✅ 预测完成: 524 场  比分: 209 条
     引擎分布: {'elo': 373, 'poisson_global+market': 23, 'elo+market': 69,
                'poisson+market': 25, 'fotmob+market': 12, 'poisson': 6,
                'poisson_global': 10, 'fotmob': 6}  OU行: 2508
```

### 篮球（实测真实输出）

```python
import basketball_normal_model as m
m.basketball_total_probs(220.5, 18.0, [215.5, 220.5, 225.5])
```
```
over  {215.5: 0.6094, 220.5: 0.5, 225.5: 0.3906}
under {215.5: 0.3906, 220.5: 0.5, 225.5: 0.6094}
fair_odds {215.5: (1.64, 2.56), 220.5: (2.0, 2.0), 225.5: (2.56, 1.64)}
```

## 六、已知问题

| 问题 | 状态 | 说明 |
|---|---|---|
| `unified_matches` 赛程断更 | **影响使用** | 实测最新 fetch_date = 2026-10-23，距今 7 天。跑 `--latest` 会得到「今日待预测 0 场」。需先跑赛程类爬虫补齐 `unified_matches` |
| `05_9_Backtest_Module.py` | **文件损坏** | 第 16 行三引号被误转义为 `\"\"\"`，`SyntaxError: unexpected character after line continuation character`，无法导入 |
| 回测结论不可采信 | 待重做 | 见第三节 |
