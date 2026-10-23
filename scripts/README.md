# 500.com 多公司赔率采集 + qiety 赛前赔率导出

任务 13（桌面「新建文本文档 (13).txt」）的实现代码。**仅个人研究使用，不对外分发。**

## ⚠️ 合规声明

500.com 的 `robots.txt` 明确包含：

```
Disallow: /ouzhi-*.shtml
Disallow: /yazhi-*.shtml
Disallow: /daxiao-*.shtml
```

本目录下的 `scraper_500_*.py` / `collect_500_*.py` 抓取的正是这些路径，**违反该声明**。
用户已明确授权（仅自用、不公开分发）。抓取间隔 0.5~0.6 秒/请求，单轮 49 场约 200 秒。

若你复用这些代码，请自行评估合规风险。

---

## 一、脚本清单

### 解析器（纯 HTML 解析，不写库）

| 文件 | 作用 | 关键点 |
|---|---|---|
| `scraper_500_ouzhi.py` | 欧赔（1X2）解析 | 公司行 class 是 `tr1`/`tr2` **交替**；公司名被掩码成 `威***`，需用 cid 反查真名 |
| `scraper_500_ah_ou.py` | 亚盘 + 大小球解析 | 亚盘页用 `dt=` 属性而非 `data-time=`；`ref` 已是主队视角 |
| `scraper_500_results.py` | 赛果解析 | 完场列表 `class="red"` 是全场比分；`<div class="pk">` 是**亚盘盘口不是半场** |

### 采集器（写 SQLite）

| 文件 | 作用 | 输出表 |
|---|---|---|
| `collect_500_live.py` | 当日全部赛程的 1X2+AH+OU 快照 | `matches`, `odds_1x2`, `odds_ah`, `odds_ou` |
| `collect_500_results.py` | 完场赛果 + 角球 | `results` |
| `collect_500_close.py` | 收盘价（close） | `odds_close` |
| `collect_500_history.py` | 历史赛季比分/欧赔/亚盘 | `matches`, `odds`（getmatch 接口） |
| `collect_500_hist_company.py` | 历史赛季**公司级**初盘+收盘 | `company_odds` |

### 导出器（生成 gzip CSV）

| 文件 | 作用 |
|---|---|
| `export_500_snapshot.py` | 当日快照 → 任务第三节格式（含 close 追加） |
| `export_500_history.py` | 历史数据 → 任务第三节格式 |
| `export_soft_snapshots.py` | qiety 赛前赔率 → GitHub `exports/grokbot/<日期>/soft_snapshots/` |

### 辅助

| 文件 | 作用 |
|---|---|
| `ah_line_map.py` | 亚盘文字 → 数值映射（`半球/一球` → `-0.75`） |
| `build_team_map.py` | 用 Pinnacle 赛程共现反推中文→英文队名 |
| `backfill_ht.py` | 用 getmatch 接口回填半场比分 |
| `push_soft_snapshots.bat` + `register_soft_push.ps1` | 每日 2 次推送的定时任务 |

---

## 二、500.com 页面结构（实测 2026-10-23）

### 欧赔 ouzhi 页

```
https://odds.500.com/fenxi/ouzhi-<fid>.shtml

<tr class="tr1" id="293" ttl="zy" data-time="2026-10-23 14:38:08">
  <td class="tb_plgs" title="威***">
    <a href=".../ouzhi.php?cid=293">          ← cid 反查真名
  <td><table class="pl_table_data">
    <tr>  初盘  1.67 / 3.30 / 4.60
    <tr class="bg-a">  收盘（赛后固化）  2.05 / 3.10 / 3.10
```

**关键发现**：已完赛比赛的 tr1 是**最终收盘价**，不需要赛前抢抓，赛后补抓即可。

### 亚盘 yazhi 页

```
<tr class="tr1" xls="row" id="3" dt="2026-10-22 09:59:45">   ← 注意是 dt= 不是 data-time=
  <table class="pl_table_data">  块0 = 初盘（1 个 tr）
  <table class="pl_table_data">  块1 = 收盘（1 个 tr）
    <td class="ying">0.970↑</td>          ← 主水位（带箭头）
    <td ref="-0.250">平手/半球</td>        ← 盘口，ref 已是主队视角
    <td class="ping">0.820↓</td>          ← 客水位
```

**两个坑**：
1. 亚盘/大小球页只有 60~70KB（欧赔页 280KB），长度阈值不能一刀切
2. 大小球页的盘口线在 `<td class="tb_tdul_pan">` 里，取值时必须排除这个 td

### 历史数据 getmatch 接口（最高效）

```
GET https://liansai.500.com/index.php?c=score&a=getmatch&stid=<stid>&round=<N>
```

返回 JSON，**一场的所有字段都在里面**：

```json
{"fid":825597,"round":1,"stime":"2019-07-27 02:30",
 "hname":"斯图加特","gname":"汉诺威96",
 "hscore":2,"gscore":1,                    // 全场
 "hhalfscore":2,"ghalfscore":1,            // 半场 ★ 这是唯一有半场的地方
 "win":1.71,"draw":3.84,"lost":4.42,       // 欧赔（≈收盘价）
 "handline":"半球/一球","pan":"赢半",       // 亚盘
 "status":5}                                // 5=完场
```

**34 轮只需 34 次请求**，而爬 HTML 要 306 次（9 倍效率差）。

赛季 ID 发现方式：`https://liansai.500.com/zuqiu-<seasonId>/` 页内含全部历史赛季链接。

---

## 三、快速开始

```bash
PY="C:/Users/Lucky/AppData/Local/Programs/Python/Python311/python.exe"

# 当日快照（49 场约 200 秒）
$PY -X utf8 collect_500_live.py --out out/bok500.db --loop 1

# 赛果 + 角球
$PY -X utf8 collect_500_results.py --db out/bok500.db --date 2026-10-21 --with-corners

# 收盘价（三市场）
$PY -X utf8 collect_500_close.py --db out/bok500.db --date 2026-10-21 --markets 1X2,AH,OU

# 历史（德乙 2019+，2448 场约 5 分钟）
$PY -X utf8 collect_500_history.py --url https://liansai.500.com/zuqiu-19952/ \
    --out out/bok500_hist.db --since 2019

# 公司级历史赔率（2448 场约 4.5 小时，支持断点续跑）
$PY -X utf8 collect_500_hist_company.py --histdb out/bok500_hist.db \
    --out out/bok500_company.db

# 导出
$PY -X utf8 export_500_snapshot.py --db out/bok500.db --outdir <repo>/exports/grokbot_500
$PY -X utf8 export_500_history.py --db out/bok500_hist.db --outdir <repo>/exports/grokbot_500_hist
$PY -X utf8 export_soft_snapshots.py --db D:\\cl\\qqsj\\data\\sports_data.db \
    --repo D:\\cl\\fp_exports --hours 24 --push
```

---

## 四、踩过的坑

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | AH/OU 全部 0 条 | `MIN_HTML=120000` 把 67KB 的亚盘页当坏页 | 按市场设阈值（1X2:150K / AH,OU:40K） |
| 2 | AH/OU 仍然 0 条 | 亚盘页用 `dt=` 不是 `data-time=` | 正则 `(?:data-time|dt)` |
| 3 | 客队水位 None | `(主,客)` 二元组硬套进 `(h,d,a)` 三字段 | 按市场分别映射 |
| 4 | 大小球客队水位显示 2.5 | 盘口线 td（`tb_tdul_pan`）被当水位 | 取值时排除该 class |
| 5 | 半场比分 7-0 > 全场 3-0 | `<div class="pk">` 是亚盘盘口不是半场 | 改用 getmatch 的 `hhalfscore` |
| 6 | 49 场里 15 场抓不到 | 500.com 偶发返回 HTTP 200 但 body 只有 38 字节 | 5 次重试，退避 3/8/20/40 秒 |
| 7 | 亚洲盘口符号反了 | `ref` 已是主队视角，不该再取负 | `line = ref`（不取反） |
| 8 | 列表页比分与 detail 页不符 | 列表页显示的可能是半场 | 以 getmatch / detail 为准 |

---

## 五、已知缺口

1. **半场比分只对已完赛比赛有效**（`status==5`）。未开赛返回的 0-0 是占位值，代码已过滤。
2. **`getmatch` 的赔率是收盘价不是初盘**。初盘必须抓 `ouzhi-<fid>.shtml` 的 tr0。
3. **`getmatch` 是平均赔率不是公司级**。公司级要逐场抓 HTML（2448 场 × 3 页 ≈ 7300 请求）。
4. **Pinnacle 匹配率约 38%**。未匹配的是奥丙、威尔士超、俄 U19 等冷门/青年联赛，Pinnacle 本身不提供。
5. **历史赛事范围**：当前只做了德乙（`zuqiu-19952`）。其他联赛换 `--url` 即可。

---

## 六、凭据

**所有脚本不含任何账号密码/token。** 采集 qiety 时从环境变量读取：

```
QIETY_ACCOUNT / QIETY_PASSWORD
```

`.gitignore` 已排除 `.env`、`.qiety_token.json`、`.qiety_account.json`、`*.db`。
