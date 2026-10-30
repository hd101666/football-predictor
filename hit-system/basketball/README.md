# 篮球爬虫 (basketball/) — 7 个

> 篮球单独存放，与足球不混用。

**以下脚本同时覆盖足球与篮球，统一归入 `football/`，篮球调用时加 `--sport 2`：**

| 文件 | 说明 |
|---|---|
| `football/29_qiety_yb_full_scraper.py` | `--sport 1` 足球 / `--sport 2` 篮球 / `--all` 全部 |
| `football/46_qiety_lineup_scraper.py` | 阵容/伤病/积分榜/交锋，支持双运动 |
| `football/42_okooo_jingcai_scraper.py` | 澳客竞彩足球/篮球对阵+赔率 |
| `football/47_sporttery_hafu_scraper.py` | 竞彩官网半全场，足球篮球同时落库 |
| `football/48_qiumibao_corner_scraper.py` | 188bifen 半场/全场比分+角球 |
| `football/16_flashscore_results_scraper.py` | FlashScore 赛果，覆盖全球足球+篮球 |
| `football/15_pinnacle_oddsportal_scraper.py` | Pinnacle+OddsPortal 全量赔率，双运动 |
| `football/10_oddsportal_scraper.py` | OddsPortal 全量赔率，双运动 |
| `football/12_pinnacle_scraper.py` | Pinnacle 直爬，双运动 |
| `football/24_betfair_scraper.py` | Betfair 交易所赔率 |


| 文件 | 源站 | 输出表 | 状态 | 说明 |
|---|---|---|---|---|
| `23_bball_ref_scraper.py` | www.basketball-reference.com | `bballref_game_logs`, `bballref_team_stats` | 能跑 | 实测可运行 |
| `27_euroleague_feeds_scraper.py` | feeds.incrowdsports.com, www.euroleague.net | `euroleague_boxscores`, `euroleague_clubs`, `euroleague_games` | 能跑 | 实测可运行 |
| `28_livescore_basketball_scraper.py` | prod-public-api.livescore.com, www.livescore.com | `ls_bball_games`, `ls_bball_leagues` | 能跑 | 3,432 行 |
| `29_betexplorer_basketball_scraper.py` | www.betexplorer.com | `be_bball_matches`, `be_bball_odds` | 能跑 | 实测可运行 |
| `30_flashscore_basketball_scraper.py` | api.sofascore.com, d.flashscore.com | `fs_bball_matches`, `fs_bball_odds`, `fs_bball_scrape_log` | 能跑 | 10,442 行 |
| `31_nba_official_scraper.py` | stats.nba.com, www.nba.com | `nba_matches` | 能跑 | 52,481 行 |
| `18_espn_scores_scraper.py` | site.api.espn.com | `espn_scores` | 能跑 | 实测可运行 |

运行方式见各脚本 `--help`；依赖安装见上级 `requirements.txt`。
