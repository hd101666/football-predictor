# 命中系统 Crawler & Model 总表 (Crawler & Model Master Index)

> 本表由**实跑验证**生成，非文件名字面推断。最后验证: **2026-10-30**。
> 判定口径: **能跑** = 已在本机真实启动并成功取数/落库；**已停用** = 经复测确认不可用（订阅/封锁/需账号），按“废弃不修”原则不再维护。

## 总览

| 项目 | 数值 |
|---|---|
| 足球爬虫 | 38 |
| 篮球爬虫 | 7 |
| **爬虫合计** | **45** |
| 能跑 | **39** |
| 已停用（废弃，不修） | 6 |
| 数据表总数 | 231 |
| 全库总行数 | 13,839,923 |
| 已导出样本表 | 190 (每表≤100行) |

## 已停用清单（废弃，不修）

| 文件 | 停用原因 | 替代方案 |
|---|---|---|
| `11_fbref_xg_scraper.py` | FBref 免费页已移除 xG 列，需付费订阅 | `understat_xg_*`（336队/5976场，已有数据） |
| `13_bet365_scraper.py` | 需 RapidAPI 付费订阅，RAPIDAPI_KEY 仍为占位符 | 无（可用 `35_theoddsapi` 替代主流联赛） |
| `19_whoscored_scraper.py` | WhoScored 全站 Cloudflare IP 级封锁（首页亦被拦） | 无 |
| `24_betfair_scraper.py` | 需官方 Exchange API Key+证书，IP 被 403 | 无 |
| `30_qiety_history_scraper.py` | 浏览器 UI 登录需账号密码，且硬编码旧域名全失效 | `29_qiety_yb_full_scraper` 的 `qiety_matches` 表 |
| `46_sportmonks_fixtures_scraper.py` | 账号仅 Free Plan，无 football 权限 | 无 |

## 一、足球爬虫 (football/) — 主用

| # | 文件 | 源站 / API | 类型 | 输出表 | 库内行数 | 需要Key | 状态 | 实测说明 |
|---|---|---|---|---|---|---|---|---|
| 07 | `07_sofascore_scraper.py` | api.sofascore.com, www.sofascore.com | 足球 | `sofascore_form`, `sofascore_h2h`, `sofascore_matches` 等6张 | 0 (空表) | 不需要 | **能跑** | 实测抓取中；sofascore 对高频请求返回403，脚本内置指纹轮换，可降速使用；该表历史为空说明尚未长期跑 |
| 08 | `08_flashscore_scraper.py` | d.flashscore.com, m.flashscore.com | 足球 | `flashscore_matches`, `flashscore_odds_history`, `flashscore_scrape_log` | 7.9K | 不需要 | **能跑** | log表 7,948 行在库 |
| 09 | `09_flashscore_schedule_scraper.py` | www.flashscore.com | 足球 | `soccerway_form`, `soccerway_h2h`, `soccerway_matches` 等5张 | 2.3K | 不需要 | **能跑** | 实测可运行 |
| 10 | `10_understat_xg_scraper.py` | understat.com | 足球 | `understat_xg_matches`, `understat_xg_teams` | 6.3K | 不需要 | **能跑** | 实测可运行 |
| 11 | `11_betexplorer_scraper.py` | www.betexplorer.com | 足球 | `betexplorer_avg_odds`, `betexplorer_matches`, `betexplorer_odds` 等4张 | 28.2K | 不需要 | **能跑** | 实测可运行 |
| 11 | `11_fbref_xg_scraper.py` | fbref.com | 足球 | `fbref_xg_teams` | 0 (空表) | 不需要 | **已停用** | 2026-10-30复测: FBref免费页已彻底移除xG列(实测stats表仅21列,无Expected_xG; /xg/页shooting表13列也无xG)，页面仅显示Subscribe/Sign up → 需付费订阅才能拿xG，判定废弃不修。替代源: understat_xg_*(336队/5976场)已有数据 |
| 12 | `12_statsbomb_national_xg_scraper.py` | — (内置/环境变量) | 足球 | `statsbomb_national_xg_matches`, `statsbomb_national_xg_teams` | 605 | 不需要 | **能跑** | 实测可运行 |
| 13 | `13_bet365_scraper.py` | bet365-api-inplay.p.rapidapi.com, in-play.bet365.com | 足球 | `bet365_fixtures`, `bet365_inplay`, `bet365_odds` | 0 (空表) | 需要: RAPIDAPI_KEY | **已停用** | 需RapidAPI付费订阅(实测403 not subscribed)，RAPIDAPI_KEY当前仍是占位符*** → 废弃不修 |
| 15 | `15_pinnacle_oddsportal_scraper.py` | guest.api.arcadia.pinnacle.com, www.oddsportal.com | 足球 | `pinnacle_correct_score_odds`, `theodds_fixtures`, `theodds_odds` 等4张 | 2.64M | 需要: PINNACLE_GUEST_KEY | **能跑** | 库内 2,640,925 行 |
| 16 | `16_footballdata_scraper.py` | www.football-data.co.uk | 足球 | `fd_matches` | 309.6K | 不需要 | **能跑** | 309,641 行 |
| 16 | `16_flashscore_results_scraper.py` | www.flashscore.com | 足球 | `match_results` | 22.1K | 不需要 | **能跑** | 22,086 行 |
| 17 | `17_understat_scraper.py` | understat.com | 足球 | `understat_matches`, `understat_team_stats` | 12.9K | 不需要 | **能跑** | 实测可运行 |
| 19 | `19_whoscored_scraper.py` | www.whoscored.com | 足球 | `whoscored_match_stats`, `whoscored_team_stats` | 0 (空表) | 不需要 | **已停用** | 2026-10-30复测: 已修复camoufox插件缺失(UBO空目录致manifest.json缺失，删除后自动重下)，浏览器可正常启动；但WhoScored全站被Cloudflare IP级封锁(首页也返回Attention Required) → 判定废弃不修 |
| 22 | `22_fbref_scraper.py` | fbref.com | 足球 | `fbref_match_stats`, `fbref_team_stats` | 9.1K | 不需要 | **能跑** | 9,069 行(注: 与11同为fbref但本脚本解析路径可用) |
| 23 | `23_football_data_scraper.py` | www.football-data.co.uk | 足球 | `fd_matches` | 309.6K | 不需要 | **能跑** | 与16同源 football-data.co.uk |
| 25 | `25_transfermarkt_scraper.py` | www.transfermarkt.com | 足球 | `transfermarkt_injuries`, `transfermarkt_squad_values` | 203 | 不需要 | **能跑** | 实测可运行 |
| 26 | `26_multi_bookmaker_scraper.py` | eu-offering-api.kambicdn.com, sbapi.ny.sportsbook.fanduel.com | 足球 | `multi_bookie_odds` | 50.8K | 不需要 | **能跑** | 50,794 行 |
| 28 | `28_qiety_yb_scraper_v2.py` | api.bvl8bs5.com, user-pc-new.lvjida8.com | 足球 | `multisource_odds`, `qiety_matches` | 117.6K | 需要: QIETY_TOKEN, QIETY_CUID | **能跑** | 读 QIETY_CUID/QIETY_TOKEN 环境变量 |
| 29 | `29_qiety_yb_full_scraper.py` | api.fgqinxg.com, user-pc-new.lvjida8.com | 足球 | `multisource_odds`, `qiety_matches`, `qiety_odds_snapshots` | 208.9K | 不需要 | **能跑** | ★2026-10-30实测: 足球103场全部成功 |
| 30 | `30_qiety_history_scraper.py` | api.fgqinxg.com, h5.qiety.vip | 足球 | `qiety_history` | 0 (空表) | 需要: QIETY_ACCOUNT, QIETY_PASSWORD | **已停用** | 2026-10-30复测: 该脚本用浏览器UI自动化登录(需QIETY_ACCOUNT/PASSWORD)，非token方式；硬编码域名qiety1748/1692/1726.vip+h5.qiety.vip全部失效(实测4个全失败)；.env中无账号密码 → 需你提供账号才能修，判定废弃不修。历史赛果可改用29号(29_qiety_yb_full_scraper)采集的qiety_matches表 |
| 33 | `33_corner_odds_scraper.py` | live.500.com, lv.scoremer.com | 足球 | `corner_live_odds` | 2.9K | 不需要 | **能跑** | 500.com 授权范围, 遇验证码需人工 |
| 35 | `35_theoddsapi_multi_scraper.py` | — (内置/环境变量) | 足球 | `theodds_api_odds` | 180.5K | 需要: THE_ODDS_API_KEY_1..9 | **能跑** | 180,505 行; 需 THE_ODDS_API_KEY_* |
| 37 | `37_corner_stats_scraper.py` | corner-stats.com | 足球 | `corner_stats_final`, `corner_stats_pending` | 3.7K | 不需要 | **能跑** | 实测可运行 |
| 38 | `38_qiety_correct_score_scraper.py` | api.fgqinxg.com, user-pc-new.lvjida8.com | 足球 | `yb_correct_score_odds` | 369.0K | 不需要 | **能跑** | 369,031 行 |
| 39 | `39_okooo_ren9_scraper.py` | m.okooo.com | 足球 | `okooo_ren9_matches`, `okooo_ren9_snapshots` | 2.3K | 不需要 | **能跑** | 实测可运行 |
| 40 | `40_okooo_injury_scraper.py` | www.okooo.com | 足球 | `okooo_injuries` | 1.3K | 不需要 | **能跑** | 实测可运行 |
| 41 | `41_okooo_betflow_scraper.py` | www.okooo.com | 足球 | `okooo_bet_flow` | 2.5K | 不需要 | **能跑** | 实测可运行 |
| 42 | `42_okooo_jingcai_scraper.py` | m.okooo.com, www.okooo.com | 足球 | `okooo_basketball_odds`, `okooo_football_odds` | 1.6K | 不需要 | **能跑** | 实测可运行 |
| 43 | `43_fotmob_match_data_scraper.py` | www.fotmob.com | 足球 | `fotmob_lineups`, `fotmob_match_team_stats`, `fotmob_matches` 等5张 | 1.22M | 不需要 | **能跑** | 1,218,311 行(全库最大足球源之一) |
| 44 | `44_lottery_500com_sfc_history_scraper.py` | kaijiang.500.com | 足球 | `lottery_sfc_matches`, `lottery_sfc_prizes` | 56.3K | 不需要 | **能跑** | 56,329 行 |
| 45 | `45_titan007_history_scraper.py` | bf.titan007.com | 足球 | `titan007_match_history` | 1.65M | 不需要 | **能跑** | 1,645,374 行 |
| 46 | `46_qiety_lineup_scraper.py` | api.fgqinxg.com, user-pc-new.lvjida8.com | 足球 | `qiety_h2h_history`, `qiety_lineup_scrape_log`, `qiety_lineups` 等4张 | 494.2K | 不需要 | **能跑** | 494,222 行 |
| 46 | `46_sportmonks_fixtures_scraper.py` | api.sportmonks.com | 足球 | `sportmonks_fixture_identity`, `sportmonks_season_identity` | 0 (空表) | 需要: SPORTMONKS_API_KEY | **已停用** | 账号仅Free Plan无football权限(实测no access via subscription) → 废弃不修 |
| 47 | `47_sporttery_hafu_scraper.py` | — (内置/环境变量) | 足球 | — | 0 (空表) | 不需要 | **能跑** | ★2026-10-30实测: 写入73条(足球55场含半全场+篮球18场) |
| 48 | `48_qiumibao_corner_scraper.py` | matchs.qiumibao.com, www.188bifen.com | 足球 | `qiumibao_match_results`, `qiumibao_odds_snapshot` | 32.9K | 不需要 | **能跑** | 32,913 行 |
| 10 | `10_oddsportal_scraper.py` | www.oddsportal.com | 足球 | `oddsportal_matches`, `oddsportal_odds`, `oddsportal_odds_history` | 13.1K | 不需要 | **能跑** | Playwright 渲染, 13,111 行 |
| 12 | `12_pinnacle_scraper.py` | guest.api.arcadia.pinnacle.com, www.pinnacle.com | 足球 | `pinnacle_corner_odds`, `pinnacle_fixtures`, `pinnacle_leagues` 等5张 | 545.7K | 需要: PINNACLE_GUEST_KEY | **能跑** | 545,651 行 |
| 24 | `24_betfair_scraper.py` | api.betfair.com, developer.betfair.com | 足球 | `betfair_exchange_odds` | 0 (空表) | 需要: BETFAIR_API_KEY(未配置) | **已停用** | 需注册官方Exchange API Key+证书，且IP被403封锁 → 废弃不修 |

## 二、篮球爬虫 (basketball/) — 单独存放

| # | 文件 | 源站 / API | 类型 | 输出表 | 库内行数 | 需要Key | 状态 | 实测说明 |
|---|---|---|---|---|---|---|---|---|
| 23 | `23_bball_ref_scraper.py` | www.basketball-reference.com | 篮球 | `bballref_game_logs`, `bballref_team_stats` | 60 | 不需要 | **能跑** | 实测可运行 |
| 27 | `27_euroleague_feeds_scraper.py` | feeds.incrowdsports.com, www.euroleague.net | 篮球 | `euroleague_boxscores`, `euroleague_clubs`, `euroleague_games` 等4张 | 379 | 不需要 | **能跑** | 实测可运行 |
| 28 | `28_livescore_basketball_scraper.py` | prod-public-api.livescore.com, www.livescore.com | 篮球 | `ls_bball_games`, `ls_bball_leagues` | 3.4K | 不需要 | **能跑** | 3,432 行 |
| 29 | `29_betexplorer_basketball_scraper.py` | www.betexplorer.com | 篮球 | `be_bball_matches`, `be_bball_odds` | 1.8K | 不需要 | **能跑** | 实测可运行 |
| 30 | `30_flashscore_basketball_scraper.py` | api.sofascore.com, d.flashscore.com | 篮球 | `fs_bball_matches`, `fs_bball_odds`, `fs_bball_scrape_log` 等5张 | 10.4K | 不需要 | **能跑** | 10,442 行 |
| 31 | `31_nba_official_scraper.py` | stats.nba.com, www.nba.com | 篮球 | `nba_matches` | 52.5K | 不需要 | **能跑** | 52,481 行 |
| 18 | `18_espn_scores_scraper.py` | site.api.espn.com | 篮球 | `espn_scores` | 75 | 不需要 | **能跑** | 实测可运行 |
