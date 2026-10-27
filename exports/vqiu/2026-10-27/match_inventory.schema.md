# `match_inventory.csv` 字段说明

数据行数：1203（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| match_unique_id | 包含 ID 命名空间的比赛唯一键 | 字符串 | 无 | isports:105612037 | 缺失时留空 |
| match_id | 源平台比赛编号 | 字符串/整数 | 无 | 105612037 | 缺失时留空 |
| id_namespace | 比赛编号所属命名空间 | 字符串 | 无 | ISports | 缺失时留空 |
| vfootball_match_id | V 球比赛编号（该接口未返回时为空） | 字符串/整数 | 无 | 602349 | 未返回时留空 |
| zc_match_id | 竞彩足球比赛编号（该接口未返回时为空） | 字符串/整数 | 无 | 周二001 | 未返回时留空 |
| league_id | 联赛唯一编号 | 字符串/整数 | 无 | 13351 | 缺失时留空 |
| league_name_en | 联赛英文名称 | 字符串 | 无 | Malta Premier League | 缺失时留空 |
| league_name_zh | 联赛中文名称 | 字符串 | 无 | 马耳他足球超级联赛 | 缺失时留空 |
| home_team_en | 主队英文名称 | 字符串 | 无 | Mosta FC | 缺失时留空 |
| home_team_zh | 主队中文名称 | 字符串 | 无 | 莫斯塔 | 缺失时留空 |
| away_team_en | 客队英文名称 | 字符串 | 无 | Hibernians FC | 缺失时留空 |
| away_team_zh | 客队中文名称 | 字符串 | 无 | 希伯尼安斯 | 缺失时留空 |
| kickoff_at_utc | 计划开赛时间 | ISO 8601 | UTC | 2026-10-24T16:00:00Z | 缺失时留空 |
| kickoff_at_beijing | 计划开赛时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-25T00:00:00+08:00 | 缺失时留空 |
| status | 平台返回的比赛状态 | 字符串 | 无 | finished | 缺失时留空 |
| home_score | 主队比分；比赛未完赛时不填 0 | 整数 | 球 | 0 | 未完赛/未返回时留空 |
| away_score | 客队比分；比赛未完赛时不填 0 | 整数 | 球 | 0 | 未完赛/未返回时留空 |
| mapping_status | 源平台对比赛映射状态 | 字符串 | 无 | complete | 缺失时留空 |
| updated_at_utc | 数据更新时间 | ISO 8601 | UTC | 2026-10-26T21:28:09.820000Z | 缺失时留空 |
| updated_at_beijing | 数据更新时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-27T05:28:09.820000+08:00 | 缺失时留空 |
| capture_id | 采集记录编号 | 字符串 | 无 | VQ0185 | 缺失时留空 |
| source_url | 数据来源接口 URL | URL | 无 | https://vfootball.cn/api/open/all-odds/matches?date_from=2026-10-25&date_to=2026-10-27&limit=100&off | 缺失时留空 |

比分仅在平台状态明确为完赛/终场时导出。未开赛或进行中的比分列留空；不会把 0-0 当成未完赛比分填入。
