# `api_response_values.csv` 字段说明

数据行数：195609（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| capture_id | 采集记录编号 | 字符串 | 无 | VQ0001 | 缺失时留空 |
| source_url | 数据来源接口 URL | URL | 无 | https://vfootball.cn/api/open/zc/matches | 缺失时留空 |
| captured_at_utc | 接口响应采集时间 | ISO 8601 | UTC | 2026-10-27T02:19:40.464000Z | 缺失时留空 |
| captured_at_beijing | 接口响应采集时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-27T10:19:40.464000+08:00 | 缺失时留空 |
| match_id | 可从当前记录提取的比赛编号 | 字符串/整数 | 无 | 602349 | 无法关联时留空 |
| vfootball_match_id | V 球比赛编号 | 字符串/整数 | 无 | 602349 | 无法关联时留空 |
| zc_match_id | 竞彩足球比赛编号 | 字符串/整数 | 无 | 周二001 | 无法关联时留空 |
| league_id | 联赛编号 | 字符串/整数 | 无 | 43 | 无法关联时留空 |
| league_name | 联赛名称 | 字符串 | 无 | DFB Pokal | 无法关联时留空 |
| home_team | 主队名称 | 字符串 | 无 | VfL Bochum 1848 | 无法关联时留空 |
| away_team | 客队名称 | 字符串 | 无 | 1. FSV Mainz 05 | 无法关联时留空 |
| kickoff_at_utc | 记录关联的开赛时间 | ISO 8601 | UTC | 2026-10-27T17:00:00Z | 无法关联时留空 |
| kickoff_at_beijing | 记录关联的开赛时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-28T01:00:00+08:00 | 无法关联时留空 |
| record_path | JSON 中包含当前实体编号的记录位置 | 字符串 | 无 | data | 缺失时留空 |
| field_path | 接口字段结构路径，数组以 [] 表示 | 字符串 | 无 | data.updatedAt | 无路径时留空 |
| value_type | 源值类型 | 字符串 | 无 | string | 缺失字段不会生成行 |
| value | 字段值；可解析的日期时间字符串规范化为 UTC，epoch 数值仍保留源数值 | 字符串化值 | 源接口单位 | 2026-10-26T18:14:04Z | null 为空；空数组/对象保留 []/{} |
| value_time_utc | 可解析时间字段的标准化 UTC 时间；非时间字段留空 | ISO 8601 | UTC | 2026-10-26T18:14:04Z | 不可解析/非时间字段留空 |
| value_time_beijing | 可解析时间字段的标准化北京时间；非时间字段留空 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-27T02:14:04+08:00 | 不可解析/非时间字段留空 |

数组路径使用 `[]` 代表数组元素，具体元素位置记录在 `record_path`。可解析的时间字符串在 `value` 中规范化为 UTC，并同时提供 UTC 与 Asia/Shanghai 两列；Unix epoch 数值保留原值并附标准化时区列。空数组与空对象分别以 `value_type=empty_array/empty_object`、`value=[]/{}` 保存。
