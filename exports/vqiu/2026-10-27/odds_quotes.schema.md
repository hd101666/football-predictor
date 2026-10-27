# `odds_quotes.csv` 字段说明

数据行数：7385（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| capture_id | 采集记录编号 | 字符串 | 无 | VQ0056 | 缺失时留空 |
| source_url | 数据来源接口 URL | URL | 无 | https://vfootball.cn/api/open/matches/odds | 缺失时留空 |
| captured_at_utc | 接口响应采集时间 | ISO 8601 | UTC | 2026-10-27T02:24:19.159000Z | 缺失时留空 |
| captured_at_beijing | 接口响应采集时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-27T10:24:19.159000+08:00 | 缺失时留空 |
| match_unique_id | 包含 ID 命名空间的比赛键 | 字符串 | 无 | vfootball:602349 | 缺失时留空 |
| match_id | 源平台比赛编号 | 字符串/整数 | 无 | 602349 | 缺失时留空 |
| league_id | 联赛编号 | 字符串/整数 | 无 | 43 | 缺失时留空 |
| league_name | 联赛名称 | 字符串 | 无 | DFB Pokal | 缺失时留空 |
| home_team | 主队名称 | 字符串 | 无 | VfL Bochum 1848 | 缺失时留空 |
| away_team | 客队名称 | 字符串 | 无 | 1. FSV Mainz 05 | 缺失时留空 |
| market_key | 赔率市场编码 | 字符串 | 无 | eur | 缺失时留空 |
| market_label | 赔率市场名称 | 字符串 | 无 | 欧赔 1X2（胜平负） | 缺失时留空 |
| market_unit | 赔率/盘口单位 | 字符串 | 由平台返回 | decimal | 缺失时留空 |
| company_code | 赔率公司编码 | 字符串 | 无 | crown | 缺失时留空 |
| company_name | 赔率公司名称 | 字符串 | 无 | 皇* | 缺失时留空 |
| phase | 赛前/赛中阶段 | 字符串 | 无 | prematch | 缺失时留空 |
| quote_kind | 本行赔率记录阶段或原始路径末段 | 字符串 | 无 | current | 缺失时留空 |
| line | 盘口线 | 字符串/数值 | 市场单位由平台定义 | -0.5 | 缺失时留空 |
| quote_at_utc | 本条报价或变化时间 | ISO 8601 | UTC | 2026-10-26T12:27:28Z | 未返回时间戳时留空 |
| quote_at_beijing | 本条报价或变化时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-26T20:27:28+08:00 | 未返回时间戳时留空 |
| opening_at_utc | 初盘时间 | ISO 8601 | UTC | 2026-10-26T12:27:28Z | 未返回时留空 |
| opening_at_beijing | 初盘时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-26T20:27:28+08:00 | 未返回时留空 |
| current_at_utc | 即时盘时间 | ISO 8601 | UTC | 2026-10-26T12:27:28Z | 未返回时留空 |
| current_at_beijing | 即时盘时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-26T20:27:28+08:00 | 未返回时留空 |
| opening_home | 初盘主胜/主队赔率值 | 数值/字符串 | 由 market_unit 定义 | 4.2 | 未返回时留空 |
| opening_draw | 初盘平局赔率值 | 数值/字符串 | 由 market_unit 定义 | 4.1 | 未返回时留空 |
| opening_away | 初盘客胜/客队赔率值 | 数值/字符串 | 由 market_unit 定义 | 1.62 | 未返回时留空 |
| current_home | 即时盘主胜/主队赔率值 | 数值/字符串 | 由 market_unit 定义 | 4.2 | 未返回时留空 |
| current_draw | 即时盘平局赔率值 | 数值/字符串 | 由 market_unit 定义 | 3.80 | 未返回时留空 |
| current_away | 即时盘客胜/客队赔率值 | 数值/字符串 | 由 market_unit 定义 | 1.62 | 未返回时留空 |
| quote_home | 本行记录主队赔率字段 | 数值/字符串 | 由 market_unit 定义 | 4.2 | 未返回时留空 |
| quote_draw | 本行记录平局赔率字段 | 数值/字符串 | 由 market_unit 定义 | 3.80 | 未返回时留空 |
| quote_away | 本行记录客队赔率字段 | 数值/字符串 | 由 market_unit 定义 | 1.62 | 未返回时留空 |
| quote_over | 本行记录大球赔率字段 | 数值/字符串 | 由 market_unit 定义 | 1.90 | 未返回时留空 |
| quote_under | 本行记录小球赔率字段 | 数值/字符串 | 由 market_unit 定义 | 1.90 | 未返回时留空 |
| field_path | 报价对象在接口响应中的路径 | 字符串 | 无 | data.markets[].companies[].current | 缺失时留空 |

所有原始赔率和盘口细分字段都在 `api_response_values.csv` 中逐路径保留；本表提供可读的报价节点视图。报价时间来自平台时间戳并转换为 UTC 与 Asia/Shanghai。
