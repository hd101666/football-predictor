# `league_inventory.csv` 字段说明

数据行数：257（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| league_id | 平台联赛唯一编号 | 字符串/整数 | 无 | 12912 | 缺失时留空 |
| league_name_en | 联赛英文名称 | 字符串 | 无 | AFC Champions League Elite | 缺失时留空 |
| league_name_zh | 联赛中文名称 | 字符串 | 无 | 亚足联冠军联赛精英赛 | 缺失时留空 |
| match_count | 查询窗口内比赛数量 | 整数 | 场 | 12 | 缺失时留空 |
| first_kickoff_at_utc | 查询窗口最早开赛时间 | ISO 8601 | UTC | 2026-10-26T13:45:00Z | 缺失时留空 |
| first_kickoff_at_beijing | 查询窗口最早开赛时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-26T21:45:00+08:00 | 缺失时留空 |
| last_kickoff_at_utc | 查询窗口最晚开赛时间 | ISO 8601 | UTC | 2026-10-27T12:15:00Z | 缺失时留空 |
| last_kickoff_at_beijing | 查询窗口最晚开赛时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-27T20:15:00+08:00 | 缺失时留空 |
| capture_id | 采集记录编号 | 字符串 | 无 | VQ0198 | 缺失时留空 |
| source_url | 数据来源接口 URL | URL | 无 | https://vfootball.cn/api/open/all-odds/leagues?date_from=2026-10-25&date_to=2026-10-27&limit=100&off | 缺失时留空 |
