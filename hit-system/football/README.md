# 足球爬虫 (football/) — 38 个

> 当前主用。所有脚本均为可直接运行的完整版本（含 CLI 参数）。

| 文件 | 源站 | 输出表 | 状态 | 说明 |
|---|---|---|---|---|
| `07_sofascore_scraper.py` | api.sofascore.com, www.sofascore.com | `sofascore_form`, `sofascore_h2h`, `sofascore_matches` | 能跑 | 实测抓取中；sofascore 对高频请求返回403，脚本内置指纹轮换，可降速使用；该表历史为空说明尚未长期跑 |
| `08_flashscore_scraper.py` | d.flashscore.com, m.flashscore.com | `flashscore_matches`, `flashscore_odds_history`, `flashscore_scrape_log` | 能跑 | log表 7,948 行在库 |
| `09_flashscore_schedule_scraper.py` | www.flashscore.com | `soccerway_form`, `soccerway_h2h`, `soccerway_matches` | 能跑 | 实测可运行 |
| `10_understat_xg_scraper.py` | understat.com | `understat_xg_matches`, `understat_xg_teams` | 能跑 | 实测可运行 |
| `11_betexplorer_scraper.py` | www.betexplorer.com | `betexplorer_avg_odds`, `betexplorer_matches`, `betexplorer_odds` | 能跑 | 实测可运行 |
| `11_fbref_xg_scraper.py` | fbref.com | `fbref_xg_teams` | 需修复 | 实测绕过Cloudflare成功(页面221万字符)但解析0行: FBref已改版,列名变为 "Unnamed:0_level_0_Squad", 代码找 squad/xG 列失败 |
| `12_statsbomb_national_xg_scraper.py` | 内置/环境变量 | `statsbomb_national_xg_matches`, `statsbomb_national_xg_teams` | 能跑 | 实测可运行 |
| `13_bet365_scraper.py` | bet365-api-inplay.p.rapidapi.com, in-play.bet365.com | `bet365_fixtures`, `bet365_inplay`, `bet365_odds` | 需修复 | 依赖 RapidAPI bet365-api-inplay 订阅, 表为空 |
| `15_pinnacle_oddsportal_scraper.py` | guest.api.arcadia.pinnacle.com, www.oddsportal.com | `pinnacle_correct_score_odds`, `theodds_fixtures`, `theodds_odds` | 能跑 | 库内 2,640,925 行 |
| `16_footballdata_scraper.py` | www.football-data.co.uk | `fd_matches` | 能跑 | 309,641 行 |
| `16_flashscore_results_scraper.py` | www.flashscore.com | `match_results` | 能跑 | 22,086 行 |
| `17_understat_scraper.py` | understat.com | `understat_matches`, `understat_team_stats` | 能跑 | 实测可运行 |
| `19_whoscored_scraper.py` | www.whoscored.com | `whoscored_match_stats`, `whoscored_team_stats` | 需修复 | 实测报错: Playwright Sync API inside asyncio loop —— 需改 async API 或移出事件循环 |
| `22_fbref_scraper.py` | fbref.com | `fbref_match_stats`, `fbref_team_stats` | 能跑 | 9,069 行(注: 与11同为fbref但本脚本解析路径可用) |
| `23_football_data_scraper.py` | www.football-data.co.uk | `fd_matches` | 能跑 | 与16同源 football-data.co.uk |
| `25_transfermarkt_scraper.py` | www.transfermarkt.com | `transfermarkt_injuries`, `transfermarkt_squad_values` | 能跑 | 实测可运行 |
| `26_multi_bookmaker_scraper.py` | eu-offering-api.kambicdn.com, sbapi.ny.sportsbook.fanduel.com | `multi_bookie_odds` | 能跑 | 50,794 行 |
| `28_qiety_yb_scraper_v2.py` | api.bvl8bs5.com, user-pc-new.lvjida8.com | `multisource_odds`, `qiety_matches` | 能跑 | 读 QIETY_CUID/QIETY_TOKEN 环境变量 |
| `29_qiety_yb_full_scraper.py` | api.fgqinxg.com, user-pc-new.lvjida8.com | `multisource_odds`, `qiety_matches`, `qiety_odds_snapshots` | 能跑 | ★2026-10-30实测: 足球103场全部成功 |
| `30_qiety_history_scraper.py` | api.fgqinxg.com, h5.qiety.vip | `qiety_history` | 需修复 | 实测: 账号密码登录流程, 硬编码旧域名 qiety1692/1726/1748.vip 全部失效; 建议改用 29 的 token 方式 |
| `33_corner_odds_scraper.py` | live.500.com, lv.scoremer.com | `corner_live_odds` | 能跑 | 500.com 授权范围, 遇验证码需人工 |
| `35_theoddsapi_multi_scraper.py` | 内置/环境变量 | `theodds_api_odds` | 能跑 | 180,505 行; 需 THE_ODDS_API_KEY_* |
| `37_corner_stats_scraper.py` | corner-stats.com | `corner_stats_final`, `corner_stats_pending` | 能跑 | 实测可运行 |
| `38_qiety_correct_score_scraper.py` | api.fgqinxg.com, user-pc-new.lvjida8.com | `yb_correct_score_odds` | 能跑 | 369,031 行 |
| `39_okooo_ren9_scraper.py` | m.okooo.com | `okooo_ren9_matches`, `okooo_ren9_snapshots` | 能跑 | 实测可运行 |
| `40_okooo_injury_scraper.py` | www.okooo.com | `okooo_injuries` | 能跑 | 实测可运行 |
| `41_okooo_betflow_scraper.py` | www.okooo.com | `okooo_bet_flow` | 能跑 | 实测可运行 |
| `42_okooo_jingcai_scraper.py` | m.okooo.com, www.okooo.com | `okooo_basketball_odds`, `okooo_football_odds` | 能跑 | 实测可运行 |
| `43_fotmob_match_data_scraper.py` | www.fotmob.com | `fotmob_lineups`, `fotmob_match_team_stats`, `fotmob_matches` | 能跑 | 1,218,311 行(全库最大足球源之一) |
| `44_lottery_500com_sfc_history_scraper.py` | kaijiang.500.com | `lottery_sfc_matches`, `lottery_sfc_prizes` | 能跑 | 56,329 行 |
| `45_titan007_history_scraper.py` | bf.titan007.com | `titan007_match_history` | 能跑 | 1,645,374 行 |
| `46_qiety_lineup_scraper.py` | api.fgqinxg.com, user-pc-new.lvjida8.com | `qiety_h2h_history`, `qiety_lineup_scrape_log`, `qiety_lineups` | 能跑 | 494,222 行 |
| `46_sportmonks_fixtures_scraper.py` | api.sportmonks.com | `sportmonks_fixture_identity`, `sportmonks_season_identity` | 已停用 | 实测 --check: HTTP200 但 "don't have access via current subscription", 仅 Free Plan 无 football 权限 |
| `47_sporttery_hafu_scraper.py` | 内置/环境变量 | — | 能跑 | ★2026-10-30实测: 写入73条(足球55场含半全场+篮球18场) |
| `48_qiumibao_corner_scraper.py` | matchs.qiumibao.com, www.188bifen.com | `qiumibao_match_results`, `qiumibao_odds_snapshot` | 能跑 | 32,913 行 |
| `10_oddsportal_scraper.py` | www.oddsportal.com | `oddsportal_matches`, `oddsportal_odds`, `oddsportal_odds_history` | 能跑 | Playwright 渲染, 13,111 行 |
| `12_pinnacle_scraper.py` | guest.api.arcadia.pinnacle.com, www.pinnacle.com | `pinnacle_corner_odds`, `pinnacle_fixtures`, `pinnacle_leagues` | 能跑 | 545,651 行 |
| `24_betfair_scraper.py` | api.betfair.com, developer.betfair.com | `betfair_exchange_odds` | 需修复 | 实测: 未配置 BETFAIR_API_KEY + IP被403封锁; 需注册官方Exchange API Key |

运行方式见各脚本 `--help`；依赖安装见上级 `requirements.txt`。
