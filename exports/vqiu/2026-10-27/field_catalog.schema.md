# `field_catalog.csv` 字段说明

数据行数：6168（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| field_source | 字段定义来源：schema 或实际响应 | 字符串 | 无 | schema | 缺失时留空 |
| newly_observed | 是否为 schema 未列出、但实际响应新发现的字段 | 布尔字符串 | 无 | false | 缺失时按 false |
| method | 接口 HTTP 方法 | 字符串 | 无 | GET | 缺失时留空 |
| endpoint | 字段所属接口路径 | URL 路径/模板 | 无 | /api/open/all-odds/changes?isports_match_id={isports_match_id} | 缺失时留空 |
| field_path | 字段在响应 JSON 中的路径 | 字符串 | 无 | data | 缺失时留空 |
| type | 平台 schema 类型或样本推断类型 | 字符串 | 无 | object | 未提供时留空 |
| description | 平台字段说明（若提供） | 字符串 | 无 | isports 全联赛原始赔率变动流（当前最多 19 家公司） | 未提供时留空 |
| unit | 字段单位；来源未统一给出时明确标注 | 字符串 | 无/源字段单位 | 未在字段目录中统一标注；详见字段描述与接口 semantics | 未提供时标注未注明 |
| example | 字段取值示例（敏感字段样例已清空） | 字符串 | 与源字段一致 | 602349 | 未提供或过滤时留空 |
| availability_status | 样本中字段可用性状态 | 字符串 | 无 | available_value | 未采样时为 not_sampled |
| sample_requests | 纳入统计的样本请求数 | 整数 | 次 | 1 | 未统计时留空 |
| successful_responses | 该接口成功响应数 | 整数 | 次 | 1 | 未统计时留空 |
| responses_with_field | 含该字段的响应数 | 整数 | 次 | 1 | 未统计时留空 |
| responses_missing_field | 未返回该字段的响应数 | 整数 | 次 | 0 | 未统计时留空 |
| nonnull_values | 非空值计数 | 整数 | 个 | 1 | 未统计时留空 |
| null_values | 显式 null 值计数 | 整数 | 个 | 0 | 未统计时留空 |
| empty_arrays | 空数组计数 | 整数 | 个 | 0 | 未统计时留空 |
| empty_strings | 空字符串计数 | 整数 | 个 | 0 | 未统计时留空 |

`newly_observed=true` 表示实际响应中发现、但 V 球 schema 未列出的字段；字段逐项列在该 CSV 中。
