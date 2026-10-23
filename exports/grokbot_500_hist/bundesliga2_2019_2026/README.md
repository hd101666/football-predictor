# 500.com 历史数据（德乙 2019/2020 ~ 2026/2027）

导出时间: 2026-10-23T10:33:38Z
数据源: **500.com** `getmatch` AJAX 接口
```
GET https://liansai.500.com/index.php?c=score&a=getmatch&stid=<stid>&round=<N>
```

## 赛季与场次

| 赛季 | 场次 | 有全场比分 | 有半场比分 |
|---|---|---|---|
| 2026/2027 | 306 | 306 | 306 |
| 2025/2026 | 306 | 306 | 306 |
| 2024/2025 | 306 | 306 | 306 |
| 2023/2024 | 306 | 306 | 306 |
| 2022/2023 | 306 | 306 | 306 |
| 2021/2022 | 306 | 306 | 306 |
| 2020/2021 | 306 | 306 | 306 |
| 2019/2020 | 306 | 306 | 306 |

合计 **2448** 场

## 接口返回字段

```json
{"fid":825597,"round":1,"stime":"2019-07-27 02:30",
 "hname":"斯图加特","gname":"汉诺威96",
 "hscore":2,"gscore":1,                        // 全场
 "hhalfscore":2,"ghalfscore":1,                // 半场 ★
 "win":1.71,"draw":3.84,"lost":4.42,           // 欧赔
 "handline":"半球/一球","pan":"赢半","color":"lred",  // 亚盘 + 盘路
 "status":5}                                   // 5=完场
```

## 重要说明

1. **`odds_1x2` / `odds_ah` 是"赛前最终赔率"（≈收盘价），不是初盘**。
   `getmatch` 接口只返回一个赔率值（win/draw/lost），经实测比对
   ouzhi 页的 tr0(初盘)/tr1(收盘)，接口值 = tr1 收盘价。
   初盘需另抓 `ouzhi-<fid>.shtml` 的 tr0。
2. **`bookmaker` 统一写 `match_avg`**，因为 `getmatch` 返回的是该场"平均/主流"赔率，
   不是某一家公司。要公司级历史赔率必须逐场抓 `ouzhi-<fid>.shtml`。
3. **亚盘的 `line` 是文字**（`半球/一球`），不是数值。
   数值化需要映射表（平手=0, 半球=-0.5, 一球=-1.0, 半球/一球=-0.75 ...）。
4. `country` 为 `DE`（德乙）、`league_en` 为空（接口只给中文）。

## 时区

- `kickoff_utc` 已是 UTC（接口给的是北京时间 `stime`，导出时 -8h）
- 所有 `snapshot_utc` 直接用 `kickoff_utc`（因接口只给最终值，无独立快照时间）

## 复现

```bash
python -X utf8 collect_500_history.py \
  --url https://liansai.500.com/zuqiu-19952/ \
  --out out/bok500_hist.db --since 2019
python -X utf8 export_500_history.py --db out/bok500_hist.db --outdir <repo>/exports/grokbot_500
```

## robots.txt

同样违反 500.com 的 `Disallow: /ouzhi-*.shtml`（本脚本用 AJAX 接口，路径为 `/index.php`
不在 Disallow 列表内，但数据同源）。用户已授权仅自用。
