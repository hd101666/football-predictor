# `endpoint_inventory.csv` 字段说明

数据行数：62（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| method | schema 中声明的 HTTP 方法 | 字符串 | 无 | GET | 未声明时留空 |
| endpoint | 平台接口路径/参数模板 | 字符串 | 无 | /api/open/all-odds/changes?isports_match_id={isports_match_id} | 未声明时留空 |
| description | 平台接口说明 | 字符串 | 无 | 获取 isports 全联赛赔率原始变动流。支持单场回放，或用 since 拉取全联赛增量；覆盖上游实际返回的全部公司（当前最多 19 家），不经过平台赛程匹配，仅保留近 3 个北京自然日 | 未提供时留空 |
| parameters | 接口参数清单 JSON 字符串 | JSON 字符串 | 按平台定义 | isports_match_id; since; league_id; company_ids; markets; order; limit | 未提供时留空 |
| response_field_definitions | schema 返回字段定义 JSON 字符串 | JSON 字符串 | 按平台定义 | 31 | 未提供时留空 |
| schema_file | 本地 schema 文件名（不含目录） | 字符串 | 无 | GET_all_odds_changes.json | 未提供时留空 |
| schema_captured_at_utc | schema 采集时间 | ISO 8601 | UTC | 2026-10-27T02:18:32.7000208Z | 未提供时留空 |
