# `captures.csv` 字段说明

数据行数：200（不含表头）。编码：UTF-8。缺失值按本表字段说明处理；CSV 中的空单元格表示缺失或源值为 null，`api_response_values.csv` 用 `value_type` 区分。

| 字段名 | 中文含义 | 数据类型 | 单位 | 取值示例 | 缺失值写法 |
|---|---|---|---|---|---|
| capture_id | 本次采集记录的本地编号 | 字符串 | 无 | VQ0001 | 缺失时留空 |
| source_url | 去除敏感查询参数后的 V 球接口 URL | URL | 无 | https://vfootball.cn/api/open/zc/matches | 未解析时留空 |
| captured_at_utc | 响应采集时间 | ISO 8601 | UTC | 2026-10-27T02:19:40.464000Z | 无法取得时留空 |
| captured_at_beijing | 响应采集时间 | ISO 8601 | Asia/Shanghai, UTC+08:00 | 2026-10-27T10:19:40.464000+08:00 | 无法取得时留空 |
| method | HTTP 方法 | 字符串 | 无 | GET | 缺失时留空 |
| http_status | HTTP 状态码 | 整数/字符串 | 无 | 200 | 缺失时留空 |
| success | 采集与解析成功标记 | 布尔字符串 | 无 | true | 缺失时为 false |
| response_sha256 | 原始响应文件 SHA-256 摘要 | 十六进制字符串 | 无 | d320573419475ec55768279b6b915c1db944d6ec4be2af374f0dba9d20e538d3 | 失败或无文件时留空 |
| response_bytes | 本地响应文件字节数 | 整数 | byte | 7025 | 失败或无文件时留空 |
| manifest | 来源采集清单文件名 | 字符串 | 无 | data_capture_manifest_20261027.json | 缺失时留空 |
| data_count | 采集清单记录的返回条数（若提供） | 整数/字符串 | 条 | 14 | 源清单未提供时留空 |
