# 字段字典 (Field Dictionary)

生成时间: 2026-10-30  |  数据源库: data/sports_data.db  |  样本: samples/  |  共 190 张表

统一约定: **空值不等于 0**。未开赛的比分、未确认的首发、未覆盖的联赛一律留空。

| 表名 | 总行数(全库) | 样本行数 | 字段数 | 敏感列已剔除 |
|---|---|---|---|---|
| backtest_curve | 181 | 100 | 1 | 0 |
| backtest_daily | 3 | 3 | 14 | 0 |
| backtest_summary | 1 | 1 | 10 | 0 |
| basketball_h2h | 2,353 | 100 | 6 | 0 |
| basketball_league_ou | 15 | 15 | 5 | 0 |
| basketball_matches | 52,923 | 100 | 11 | 0 |
| basketball_moneyline_fade_recs | 31 | 31 | 18 | 0 |
| basketball_prediction | 267 | 100 | 18 | 0 |
| basketball_team_stats | 379 | 100 | 7 | 0 |
| basketball_under_fade_recs | 31 | 31 | 18 | 0 |
| bballref_team_stats | 60 | 60 | 19 | 0 |
| be_bball_matches | 588 | 100 | 14 | 0 |
| be_bball_odds | 1,176 | 100 | 11 | 0 |
| betexplorer_matches | 6,145 | 100 | 15 | 0 |
| betting_slips | 16 | 16 | 9 | 0 |
| capital_allocation | 971 | 100 | 7 | 0 |
| club_elo | 21,496 | 100 | 6 | 0 |
| combination_result | 953 | 100 | 5 | 0 |
| consensus_odds | 495,835 | 100 | 12 | 0 |
| corner_league_baseline | 22 | 22 | 16 | 0 |
| corner_live_odds | 2,879 | 100 | 19 | 0 |
| corner_recommendations | 121 | 100 | 20 | 0 |
| corner_stats_final | 1,602 | 100 | 16 | 0 |
| corner_stats_pending | 2,138 | 100 | 8 | 0 |
| corner_team_stats | 601 | 100 | 24 | 0 |
| data_quality_issue_log | 17,178 | 100 | 7 | 0 |
| dc_rho_state | 252 | 100 | 4 | 0 |
| draw_calibration_curve | 3 | 3 | 6 | 0 |
| espn_scores | 75 | 75 | 24 | 0 |
| euroleague_boxscores | 202 | 100 | 23 | 0 |
| euroleague_clubs | 38 | 38 | 9 | 0 |
| euroleague_games | 101 | 100 | 16 | 0 |
| euroleague_standings | 38 | 38 | 14 | 0 |
| fbref_match_stats | 9,069 | 100 | 11 | 0 |
| fd_corner_stats | 155,213 | 100 | 47 | 0 |
| fd_elo_ratings | 1,298 | 100 | 5 | 0 |
| fd_matches | 309,641 | 100 | 81 | 0 |
| fd_matches_2627_fotmob | 234 | 100 | 14 | 0 |
| fd_matches_archive_fix004 | 22,358 | 100 | 83 | 0 |
| fdcouk_elo_ratings | 245,033 | 100 | 5 | 0 |
| fdcouk_matches | 230,557 | 100 | 49 | 0 |
| fixture_lineups | 29,103 | 100 | 30 | 0 |
| flashscore_matches | 4,522 | 100 | 17 | 0 |
| flashscore_scrape_log | 3,426 | 100 | 4 | 0 |
| football_matches | 8,202 | 100 | 9 | 0 |
| football_score_predictions | 17,273 | 100 | 12 | 0 |
| football_team_stats | 1,598 | 100 | 30 | 0 |
| football_xg_stats | 495 | 100 | 5 | 0 |
| fotmob_fixtures | 393 | 100 | 9 | 0 |
| fotmob_h2h_matches | 8,464 | 100 | 16 | 0 |
| fotmob_lineup_players | 25,427 | 100 | 24 | 0 |
| fotmob_lineups | 35,336 | 100 | 10 | 0 |
| fotmob_match_availability | 2,525 | 100 | 13 | 0 |
| fotmob_match_events | 3,116 | 100 | 22 | 0 |
| fotmob_match_identity | 440 | 100 | 30 | 0 |
| fotmob_match_stats_raw | 68,134 | 100 | 17 | 0 |
| fotmob_match_team_stats | 35,468 | 100 | 52 | 1 |
| fotmob_match_weather | 439 | 100 | 16 | 0 |
| fotmob_matches | 17,737 | 100 | 17 | 0 |
| fotmob_player_match_stats | 703,768 | 100 | 12 | 0 |
| fotmob_raw_responses | 2,844 | 100 | 20 | 0 |
| fotmob_shots | 426,002 | 100 | 19 | 0 |
| fotmob_team_form | 4,517 | 100 | 16 | 0 |
| fs_bball_matches | 1,298 | 100 | 21 | 0 |
| fs_bball_scrape_log | 4,557 | 100 | 4 | 0 |
| hit_recommendations | 1,709 | 100 | 36 | 0 |
| intl_basketball | 28,680 | 100 | 10 | 0 |
| jingcai_divergence_log | 1,163 | 100 | 22 | 0 |
| jingcai_history_bball_matches | 22,261 | 100 | 18 | 0 |
| jingcai_history_divergence | 81,744 | 100 | 23 | 0 |
| jingcai_history_matches | 81,744 | 100 | 22 | 0 |
| jingcai_history_odds | 402,668 | 100 | 9 | 0 |
| league_ah_edge_recs | 24 | 24 | 18 | 0 |
| league_master | 5 | 5 | 8 | 0 |
| league_preview_articles | 9 | 9 | 9 | 0 |
| legacy_team_total_under_recs | 55 | 55 | 18 | 0 |
| lottery_sfc_matches | 46,396 | 100 | 19 | 0 |
| lottery_sfc_prizes | 9,933 | 100 | 10 | 0 |
| ls_bball_games | 3,223 | 100 | 22 | 0 |
| ls_bball_leagues | 209 | 100 | 6 | 0 |
| market_prediction_snapshot | 795,559 | 100 | 22 | 0 |
| match_h2h | 15,414 | 100 | 11 | 0 |
| match_master | 91 | 91 | 15 | 0 |
| match_predictions | 74 | 74 | 17 | 0 |
| match_results | 22,086 | 100 | 15 | 0 |
| match_source_map | 91 | 91 | 11 | 0 |
| moneyline_shadow_full | 453 | 100 | 17 | 0 |
| multi_bookie_odds | 50,794 | 100 | 13 | 0 |
| multi_xg_team_stats | 59 | 59 | 8 | 0 |
| multisource_odds | 87,791 | 100 | 26 | 0 |
| national_team_elo | 13,420 | 100 | 5 | 0 |
| nba_matches | 52,481 | 100 | 37 | 0 |
| odds_snapshot | 1,780 | 100 | 17 | 0 |
| odds_snapshots | 1,760,299 | 100 | 8 | 0 |
| oddsportal_matches | 5,251 | 100 | 14 | 0 |
| oddsportal_odds | 7,860 | 100 | 8 | 0 |
| ofb_matches | 90,787 | 100 | 15 | 0 |
| okooo_basketball_odds | 212 | 100 | 14 | 0 |
| okooo_bet_flow | 2,547 | 100 | 19 | 0 |
| okooo_football_odds | 1,433 | 100 | 15 | 0 |
| okooo_injuries | 1,306 | 100 | 16 | 0 |
| okooo_ren9_matches | 1,412 | 100 | 16 | 0 |
| okooo_ren9_snapshots | 868 | 100 | 11 | 0 |
| over_shadow_bets | 333 | 100 | 17 | 0 |
| pin_arm_runs | 18 | 18 | 7 | 0 |
| pinnacle_corner_odds | 150,806 | 100 | 19 | 0 |
| pinnacle_corner_odds_tiers | 237,062 | 100 | 20 | 0 |
| pinnacle_correct_score_odds | 62,434 | 100 | 8 | 0 |
| pinnacle_fixtures | 8,167 | 100 | 13 | 0 |
| pinnacle_leagues | 503 | 100 | 7 | 0 |
| pinnacle_odds | 62,460 | 100 | 10 | 0 |
| pinnacle_odds_history | 323,715 | 100 | 9 | 0 |
| pipeline_run_log | 397 | 100 | 7 | 0 |
| player_availability | 2,475 | 100 | 34 | 0 |
| prediction_snapshot | 1,824 | 100 | 27 | 0 |
| qiety_h2h_history | 168,590 | 100 | 19 | 0 |
| qiety_lineup_scrape_log | 14,942 | 100 | 3 | 0 |
| qiety_lineups | 86,203 | 100 | 13 | 0 |
| qiety_matches | 29,800 | 100 | 11 | 0 |
| qiety_odds | 4,860 | 100 | 11 | 0 |
| qiety_odds_snapshots | 91,301 | 100 | 12 | 0 |
| qiety_standings | 224,487 | 100 | 20 | 0 |
| qiumibao_match_results | 31,565 | 100 | 18 | 0 |
| qiumibao_odds_snapshot | 1,348 | 100 | 13 | 0 |
| ren9_live_slips | 235 | 100 | 8 | 0 |
| ren9_rule_review | 69 | 69 | 25 | 0 |
| ren9_shadow_v2 | 2 | 2 | 12 | 0 |
| ren9_warning_signals | 476 | 100 | 19 | 0 |
| scraper_run_log | 4,212 | 100 | 7 | 0 |
| season_identity_evidence | 55 | 55 | 20 | 0 |
| settle_summary | 8 | 8 | 12 | 0 |
| shadow_recommendations | 3,930 | 100 | 20 | 0 |
| soccerway_matches | 2,259 | 100 | 19 | 0 |
| sofa_bball_matches | 837 | 100 | 12 | 0 |
| sofa_bball_stats | 3,750 | 100 | 7 | 0 |
| soft_odds_snapshots | 204,679 | 100 | 18 | 0 |
| soft_snap_seen | 1 | 1 | 3 | 0 |
| source_collection_runs | 9 | 9 | 22 | 0 |
| source_evidence_limitations | 12 | 12 | 13 | 0 |
| source_exception_audit | 3 | 3 | 17 | 0 |
| source_field_observations | 25,484 | 100 | 20 | 0 |
| source_identity_crosswalk | 1 | 1 | 12 | 0 |
| source_identity_evidence | 5 | 5 | 16 | 0 |
| source_incident_log | 3 | 3 | 14 | 0 |
| source_quota_receipts | 107 | 100 | 11 | 0 |
| source_request_ledger | 4,842 | 100 | 31 | 0 |
| sqlite_sequence | 137 | 100 | 2 | 0 |
| statsbomb_national_xg_matches | 377 | 100 | 13 | 0 |
| statsbomb_national_xg_teams | 228 | 100 | 12 | 0 |
| statsbomb_team_xg | 469 | 100 | 8 | 0 |
| team_form | 2,382 | 100 | 14 | 0 |
| team_gnn_courtmotion | 96 | 96 | 5 | 0 |
| team_lstm_state | 544 | 100 | 4 | 0 |
| team_master | 125 | 100 | 5 | 0 |
| team_multimodal | 48 | 48 | 6 | 0 |
| team_name_map | 746 | 100 | 7 | 0 |
| team_preview_notes | 112 | 100 | 13 | 0 |
| team_rl_mas | 48 | 48 | 4 | 0 |
| team_total_shadow_full | 639 | 100 | 18 | 0 |
| team_transformer_state | 496 | 100 | 3 | 0 |
| theodds_api_bookmakers | 3 | 3 | 7 | 0 |
| theodds_api_events | 895 | 100 | 12 | 0 |
| theodds_api_market_catalog | 56 | 56 | 9 | 0 |
| theodds_api_odds | 180,505 | 100 | 14 | 0 |
| theodds_api_odds_history | 10,960 | 100 | 35 | 0 |
| theodds_api_raw_responses | 88 | 88 | 24 | 0 |
| theodds_fixtures | 49,560 | 100 | 12 | 0 |
| theodds_odds | 426,530 | 100 | 12 | 0 |
| theodds_odds_history | 2,102,401 | 100 | 10 | 0 |
| titan007_1x2_odds | 21,546 | 100 | 15 | 0 |
| titan007_handicap_odds | 17,057 | 100 | 11 | 0 |
| titan007_match_history | 1,645,374 | 100 | 17 | 0 |
| titan007_totals_odds | 17,058 | 100 | 11 | 0 |
| transfermarkt_squad_values | 203 | 100 | 9 | 0 |
| under_shadow_bets | 3,027 | 100 | 17 | 0 |
| understat_matches | 12,174 | 100 | 15 | 0 |
| understat_team_stats | 678 | 100 | 18 | 0 |
| understat_xg_matches | 5,976 | 100 | 13 | 0 |
| understat_xg_teams | 336 | 100 | 10 | 0 |
| unified_matches | 74,621 | 100 | 17 | 0 |
| unified_odds | 560,846 | 100 | 9 | 0 |
| wc2026_group_standings | 48 | 48 | 15 | 0 |
| wc2026_groups | 12 | 12 | 5 | 0 |
| wc2026_h2h | 48 | 48 | 10 | 0 |
| wc2026_match_events | 258 | 100 | 9 | 0 |
| wc2026_match_team_stats | 88 | 88 | 19 | 1 |
| wc2026_matches | 70 | 70 | 14 | 0 |
| wc2026_teams | 48 | 48 | 9 | 0 |
| yb_corner_odds | 658 | 100 | 11 | 0 |
| yb_correct_score_odds | 369,031 | 100 | 6 | 0 |

---

## 各表字段明细

### backtest_curve

- 全库行数: 181   样本: 100 行 -> `samples/backtest_curve.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `capital_curve` | 源站原始字段(见同目录样本) | 10000.0 | 空=源站未提供 |

### backtest_daily

- 全库行数: 3   样本: 3 行 -> `samples/backtest_daily.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 3 | 不应为空 |
| `test_date` | 源站原始字段(见同目录样本) | 2026-07-20 | 空=源站未提供 |
| `total_recs` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `matched` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `hit_count` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `miss_count` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `hit_rate` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `total_profit` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `roi` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `by_league_json` | 源站原始字段(见同目录样本) | {} | 空=源站未提供 |
| `by_market_json` | 源站原始字段(见同目录样本) | {} | 空=源站未提供 |
| `by_score_band_json` | 源站原始字段(见同目录样本) | {} | 空=源站未提供 |
| `by_odds_band_json` | 源站原始字段(见同目录样本) | {} | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-07-24 03:53:11 | 空=历史回填无时间戳 |

### backtest_summary

- 全库行数: 1   样本: 1 行 -> `samples/backtest_summary.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `total_match` | 源站原始字段(见同目录样本) | 180 | 空=源站未提供 |
| `win_count` | 源站原始字段(见同目录样本) | 88 | 空=源站未提供 |
| `win_rate` | 源站原始字段(见同目录样本) | 0.4889 | 空=源站未提供 |
| `real_odds_used` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `fallback_odds_used` | 源站原始字段(见同目录样本) | 180 | 空=源站未提供 |
| `initial_capital` | 源站原始字段(见同目录样本) | 10000 | 空=源站未提供 |
| `final_capital` | 源站原始字段(见同目录样本) | 966481.92 | 空=源站未提供 |
| `total_profit` | 源站原始字段(见同目录样本) | 956481.92 | 空=源站未提供 |
| `max_drawdown` | 源站原始字段(见同目录样本) | -0.9539 | 空=源站未提供 |
| `sharpe_ratio` | 源站原始字段(见同目录样本) | 0.2095 | 空=源站未提供 |

### basketball_h2h

- 全库行数: 2,353   样本: 100 行 -> `samples/basketball_h2h.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `home_team` | 主队名称 | Miami Heat | 空=源站未覆盖 |
| `away_team` | 客队名称 | Washington Wizards | 空=源站未覆盖 |
| `h2h_count` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `home_h2h_win` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `away_h2h_win` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `home_h2h_win_rate` | 源站原始字段(见同目录样本) | 0.75 | 空=源站未提供 |

### basketball_league_ou

- 全库行数: 15   样本: 15 行 -> `samples/basketball_league_ou.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | nba | 空=源站未标注 |
| `match_count` | 源站原始字段(见同目录样本) | 2618 | 空=源站未提供 |
| `avg_total` | 源站原始字段(见同目录样本) | 228.631 | 空=源站未提供 |
| `median_total` | 源站原始字段(见同目录样本) | 228.0 | 空=源站未提供 |
| `std_total` | 源站原始字段(见同目录样本) | 20.0317 | 空=源站未提供 |

### basketball_matches

- 全库行数: 52,923   样本: 100 行 -> `samples/basketball_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 56568 | 不应为空 |
| `league` | 联赛/赛事名称 | eurocup | 空=源站未标注 |
| `league_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `season` | 赛季标识 | U2024 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2025-01-15 | 空=源站未提供 |
| `home_team` | 主队名称 | Aris Midea Thessaloniki | 空=源站未覆盖 |
| `away_team` | 客队名称 | Cosea JL Bourg-en-Bresse | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 51.0 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 92.0 | 空=未开赛或源站未覆盖，不是0 |
| `status` | 比赛状态 | Game Finished | 空=未知 |
| `create_time` | 源站原始字段(见同目录样本) | 2026-07-29 07:55:28 | 空=源站未提供 |

### basketball_moneyline_fade_recs

- 全库行数: 31   样本: 31 行 -> `samples/basketball_moneyline_fade_recs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 57 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | ae69649315ad | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | World - Club Friendlies | 空=源站未标注 |
| `home_team` | 主队名称 | National Formosa University | 空=源站未覆盖 |
| `away_team` | 客队名称 | Leeming Institute Of Technol… | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-09-20T09:10:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | moneyline | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 |  | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.7576 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.5577 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0189 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.5877 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-20 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-20T15:31:02 | 空=历史回填无时间戳 |

### basketball_prediction

- 全库行数: 267   样本: 100 行 -> `samples/basketball_prediction.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | Australia - NPL New South Wa… | 空=源站未标注 |
| `sport_type` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `home_team` | 主队名称 | Marconi Stallions | 空=源站未覆盖 |
| `away_team` | 客队名称 | Wollongong Wolves | 空=源站未覆盖 |
| `home_exp_score` | 源站原始字段(见同目录样本) | 0.65 | 空=源站未提供 |
| `away_exp_score` | 源站原始字段(见同目录样本) | 0.65 | 空=源站未提供 |
| `total_exp` | 源站原始字段(见同目录样本) | 1.3 | 空=源站未提供 |
| `home_win_prob` | 源站原始字段(见同目录样本) | 0.4187 | 空=源站未提供 |
| `draw_prob` | 源站原始字段(见同目录样本) | 0.1626 | 空=源站未提供 |
| `away_win_prob` | 源站原始字段(见同目录样本) | 0.4187 | 空=源站未提供 |
| `top_score` | 源站原始字段(见同目录样本) | 0-0 | 空=源站未提供 |
| `top_score_prob` | 源站原始字段(见同目录样本) | 0.2725 | 空=源站未提供 |
| `home_kelly` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `draw_kelly` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `away_kelly` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `home_odds` | 主胜赔率 | 2.0 | 空=该场无此盘口/未抓取，不是0 |
| `draw_odds` | 平局赔率 | 3.5 | 空=无平局盘口 |
| `away_odds` | 客胜赔率 | 2.0 | 空=该场无此盘口 |

### basketball_team_stats

- 全库行数: 379   样本: 100 行 -> `samples/basketball_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | nba | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | Miami Heat | 空=源站未提供 |
| `total_games` | 源站原始字段(见同目录样本) | 167.0 | 空=源站未提供 |
| `total_win` | 源站原始字段(见同目录样本) | 79.0 | 空=源站未提供 |
| `win_rate` | 源站原始字段(见同目录样本) | 0.4731 | 空=源站未提供 |
| `offense_eff` | 源站原始字段(见同目录样本) | 115.2335 | 空=源站未提供 |
| `defense_eff` | 源站原始字段(见同目录样本) | 114.6647 | 空=源站未提供 |

### basketball_under_fade_recs

- 全库行数: 31   样本: 31 行 -> `samples/basketball_under_fade_recs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 66 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 72150983abc2 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | WNBA | 空=源站未标注 |
| `home_team` | 主队名称 | Toronto Tempo | 空=源站未覆盖 |
| `away_team` | 客队名称 | Indiana Fever | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-09-18T23:30:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | over | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 187.5 | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.9229 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.5972 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.035 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.7993 | 空=源站未提供 |
| `status` | 比赛状态 | win | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) | 0.9229 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-18 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-18T21:52:51 | 空=历史回填无时间戳 |

### bballref_team_stats

- 全库行数: 60   样本: 60 行 -> `samples/bballref_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 90 | 不应为空 |
| `season` | 赛季标识 | 2024-25 | 空=源站未提供 |
| `team` | 源站原始字段(见同目录样本) | Washington Wizards | 空=源站未提供 |
| `games` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `wins` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `losses` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `pace` | 源站原始字段(见同目录样本) | 100.9 | 空=源站未提供 |
| `ortg` | 源站原始字段(见同目录样本) | 106.8 | 空=源站未提供 |
| `drtg` | 源站原始字段(见同目录样本) | 119.1 | 空=源站未提供 |
| `nrtg` | 源站原始字段(见同目录样本) | -12.299999999999997 | 空=源站未提供 |
| `efg_pct` | 源站原始字段(见同目录样本) | 0.512 | 空=源站未提供 |
| `tov_pct` | 源站原始字段(见同目录样本) | 13.6 | 空=源站未提供 |
| `orb_pct` | 源站原始字段(见同目录样本) | 22.7 | 空=源站未提供 |
| `ft_rate` | 源站原始字段(见同目录样本) | 0.178 | 空=源站未提供 |
| `opp_efg_pct` | 源站原始字段(见同目录样本) | 0.548 | 空=源站未提供 |
| `opp_tov_pct` | 源站原始字段(见同目录样本) | 11.4 | 空=源站未提供 |
| `drb_pct` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `opp_ft_rate` | 源站原始字段(见同目录样本) | 0.202 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-01 | 空=源站未提供 |

### be_bball_matches

- 全库行数: 588   样本: 100 行 -> `samples/be_bball_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 40473 | 不应为空 |
| `match_id` | 比赛ID(源站) | 10715839 | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | australia_nbl | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Australia - NBL | 空=源站未标注 |
| `season` | 赛季标识 | current | 空=源站未提供 |
| `home_team` | 主队名称 | Perth | 空=源站未覆盖 |
| `away_team` | 客队名称 | South East Melbourne | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 19.09. | 空=源站未提供 |
| `home_score` | 主队进球(全场) | 79 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 100 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `status` | 比赛状态 | finished | 空=未知 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### be_bball_odds

- 全库行数: 1,176   样本: 100 行 -> `samples/be_bball_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 80658 | 不应为空 |
| `match_id` | 比赛ID(源站) | 10715839 | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | ml | 空=源站未提供 |
| `bookmaker` | 赔率来源公司/源站 | betexplorer_avg | 空=未标注 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `odds_open` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds_close` | 源站原始字段(见同目录样本) | 2.13 | 空=源站未提供 |
| `odds_max` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds_min` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 |  | 空=无亚盘 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### betexplorer_matches

- 全库行数: 6,145   样本: 100 行 -> `samples/betexplorer_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 21644 | 不应为空 |
| `be_match_id` | 源站原始字段(见同目录样本) | x07NGFcM | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | africa_bal | 空=源站未提供 |
| `season` | 赛季标识 | current | 空=源站未提供 |
| `home_team` | 主队名称 | Ville de Dakar | 空=源站未覆盖 |
| `away_team` | 客队名称 | Al Ahly | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-05-22 | 空=源站未提供 |
| `status` | 比赛状态 | FT | 空=未知 |
| `home_score` | 主队进球(全场) | 93 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 90 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-12 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-12 02:44:20 | 空=历史回填无时间戳 |

### betting_slips

- 全库行数: 16   样本: 16 行 -> `samples/betting_slips.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 16 | 不应为空 |
| `slip_date` | 源站原始字段(见同目录样本) | 2026-07-03 | 空=源站未提供 |
| `slip_time` | 源站原始字段(见同目录样本) | 2145 | 空=源站未提供 |
| `file_name` | 源站原始字段(见同目录样本) | 投注单_2026-07-03_500元_2145.txt | 空=源站未提供 |
| `total_invest` | 源站原始字段(见同目录样本) | 285.0 | 空=源站未提供 |
| `single_count` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `serial_count` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `content` | 源站原始字段(见同目录样本) | 
===========================… | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-07-03 13:45:01 | 空=历史回填无时间戳 |

### capital_allocation

- 全库行数: 971   样本: 100 行 -> `samples/capital_allocation.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `type` | 源站原始字段(见同目录样本) | 串关 | 空=源站未提供 |
| `league` | 联赛/赛事名称 |  | 空=源站未标注 |
| `match_info` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `comb_len` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `total_odds` | 源站原始字段(见同目录样本) | 12.96 | 空=源站未提供 |
| `kelly` | 源站原始字段(见同目录样本) | 0.3056 | 空=源站未提供 |
| `stake` | 源站原始字段(见同目录样本) | 1000.0 | 空=源站未提供 |

### club_elo

- 全库行数: 21,496   样本: 100 行 -> `samples/club_elo.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 22112 | 不应为空 |
| `team_name` | 源站原始字段(见同目录样本) | La Fiorita | 空=源站未提供 |
| `country` | 源站原始字段(见同目录样本) | SMR | 空=源站未提供 |
| `elo_rating` | 源站原始字段(见同目录样本) | 716.190124512 | 空=源站未提供 |
| `level` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-31 | 空=源站未提供 |

### combination_result

- 全库行数: 953   样本: 100 行 -> `samples/combination_result.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `comb_len` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `match_list` | 源站原始字段(见同目录样本) | Qingdao Youth IslandvsSHANGH… | 空=源站未提供 |
| `total_odds` | 源站原始字段(见同目录样本) | 12.96 | 空=源站未提供 |
| `total_prob` | 源站原始字段(见同目录样本) | 0.3592 | 空=源站未提供 |
| `comb_kelly` | 源站原始字段(见同目录样本) | 0.3056 | 空=源站未提供 |

### consensus_odds

- 全库行数: 495,835   样本: 100 行 -> `samples/consensus_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1952202 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | a943acb3ae37 | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `consensus_odds` | 源站原始字段(见同目录样本) | 1.82 | 空=源站未提供 |
| `max_odds` | 源站原始字段(见同目录样本) | 1.82 | 空=源站未提供 |
| `min_odds` | 源站原始字段(见同目录样本) | 1.82 | 空=源站未提供 |
| `sharp_odds` | 源站原始字段(见同目录样本) | 1.82 | 空=源站未提供 |
| `implied_prob` | 源站原始字段(见同目录样本) | 0.5495 | 空=源站未提供 |
| `source_count` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 6.0 | 空=无亚盘 |

### corner_league_baseline

- 全库行数: 22   样本: 22 行 -> `samples/corner_league_baseline.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league_code` | 源站原始字段(见同目录样本) | E0 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 英格兰超级联赛 | 空=源站未标注 |
| `games` | 源站原始字段(见同目录样本) | 1193 | 空=源站未提供 |
| `avg_total` | 源站原始字段(见同目录样本) | 10.3311 | 空=源站未提供 |
| `median_total` | 源站原始字段(见同目录样本) | 10.0 | 空=源站未提供 |
| `std_total` | 源站原始字段(见同目录样本) | 3.4254 | 空=源站未提供 |
| `avg_home_crn` | 源站原始字段(见同目录样本) | 5.6136 | 空=源站未提供 |
| `avg_away_crn` | 源站原始字段(见同目录样本) | 4.7175 | 空=源站未提供 |
| `home_adv_crn` | 源站原始字段(见同目录样本) | 0.8961 | 空=源站未提供 |
| `over_8_5_pct` | 源站原始字段(见同目录样本) | 0.694 | 空=源站未提供 |
| `over_9_5_pct` | 源站原始字段(见同目录样本) | 0.5859 | 空=源站未提供 |
| `over_10_5_pct` | 源站原始字段(见同目录样本) | 0.4778 | 空=源站未提供 |
| `over_11_5_pct` | 源站原始字段(见同目录样本) | 0.342 | 空=源站未提供 |
| `over_12_5_pct` | 源站原始字段(见同目录样本) | 0.2615 | 空=源站未提供 |
| `seasons_used` | 源站原始字段(见同目录样本) | 2425,2324+FotMob当季 | 空=源站未提供 |
| `computed_at` | 源站原始字段(见同目录样本) | 2026-10-12T04:21:56.826759 | 空=源站未提供 |

### corner_live_odds

- 全库行数: 2,879   样本: 100 行 -> `samples/corner_live_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 10634 | 不应为空 |
| `source` | 源站原始字段(见同目录样本) | 500com | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 1495127 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 |  | 空=源站未标注 |
| `home_team` | 主队名称 | 巴布安特 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 霍森斯 | 空=源站未覆盖 |
| `match_status` | 比赛状态 | finished | 空=未知 |
| `match_minute` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_corners` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `total_corners` | 源站原始字段(见同目录样本) | 13 | 空=源站未提供 |
| `ft_corner_line` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ft_handicap` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ht_corner_line` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds_over` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds_under` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `raw_json` | 源站原始字段(见同目录样本) | {"fid": "1495127", "title": … | 空=源站未提供 |
| `fetched_at` | 源站原始字段(见同目录样本) | 2026-10-29 22:55:37 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-29 | 空=源站未提供 |

### corner_recommendations

- 全库行数: 121   样本: 100 行 -> `samples/corner_recommendations.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 241 | 不应为空 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-05 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Scotland - Premiership | 空=源站未标注 |
| `home_team` | 主队名称 | Dundee United | 空=源站未覆盖 |
| `away_team` | 客队名称 | Falkirk | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-09-05 14:00:00 | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | corner_total | 空=源站未提供 |
| `direction` | 源站原始字段(见同目录样本) | over | 空=源站未提供 |
| `line` | 源站原始字段(见同目录样本) | 10.0 | 空=源站未提供 |
| `odds` | 源站原始字段(见同目录样本) | 1.8929 | 空=源站未提供 |
| `p_model` | 源站原始字段(见同目录样本) | 0.6052 | 空=源站未提供 |
| `p_fusion` | 源站原始字段(见同目录样本) | 0.564 | 空=源站未提供 |
| `edge` | 源站原始字段(见同目录样本) | 0.103 | 空=源站未提供 |
| `kelly` | 源站原始字段(见同目录样本) | 0.0407 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.818 | 空=源站未提供 |
| `mu_predicted` | 源站原始字段(见同目录样本) | 10.94 | 空=源站未提供 |
| `src` | 源站原始字段(见同目录样本) | team_stats | 空=源站未提供 |
| `status` | 比赛状态 | win | 空=未知 |
| `created_at` | 抓取/写入时间 | 2026-09-05 13:03:09 | 空=历史回填无时间戳 |
| `profit_loss` | 源站原始字段(见同目录样本) | 0.8929 | 空=源站未提供 |

### corner_stats_final

- 全库行数: 1,602   样本: 100 行 -> `samples/corner_stats_final.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1671 | 不应为空 |
| `source` | 源站原始字段(见同目录样本) | corner-stats.com | 空=源站未提供 |
| `match_url_id` | 源站原始字段(见同目录样本) | 648909 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-10-19 | 空=源站未提供 |
| `home_team` | 主队名称 | FC Belshina Bobruisk | 空=源站未覆盖 |
| `away_team` | 客队名称 | FK Slavia-Mozyr | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 4 | 空=未开赛或源站未覆盖，不是0 |
| `home_corners` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `total_corners` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `home_corners_1h` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `away_corners_1h` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `fetched_at` | 源站原始字段(见同目录样本) | 2026-10-27 22:52:22 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-27 | 空=源站未提供 |
| `league_slug` | 源站原始字段(见同目录样本) | premier-league-belarus | 空=源站未提供 |

### corner_stats_pending

- 全库行数: 2,138   样本: 100 行 -> `samples/corner_stats_pending.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 9520 | 不应为空 |
| `source` | 源站原始字段(见同目录样本) | corner-stats.com | 空=源站未提供 |
| `match_url_id` | 源站原始字段(见同目录样本) | 650356 | 空=源站未提供 |
| `url_path` | 源站原始字段(见同目录样本) | /fc-inter-turku-helsingin-ja… | 空=源站未提供 |
| `first_seen` | 源站原始字段(见同目录样本) | 2026-10-29 22:45:11 | 空=源站未提供 |
| `last_try` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `attempts` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |

### corner_team_stats

- 全库行数: 601   样本: 100 行 -> `samples/corner_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league_code` | 源站原始字段(见同目录样本) | E0 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 英格兰超级联赛 | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | Man United | 空=源站未提供 |
| `games` | 源站原始字段(见同目录样本) | 76 | 空=源站未提供 |
| `games_home` | 源站原始字段(见同目录样本) | 38 | 空=源站未提供 |
| `games_away` | 源站原始字段(见同目录样本) | 38 | 空=源站未提供 |
| `avg_crn_for` | 源站原始字段(见同目录样本) | 5.6053 | 空=源站未提供 |
| `avg_crn_against` | 源站原始字段(见同目录样本) | 6.0526 | 空=源站未提供 |
| `std_crn_for` | 源站原始字段(见同目录样本) | 3.0944 | 空=源站未提供 |
| `avg_crn_for_home` | 源站原始字段(见同目录样本) | 6.7105 | 空=源站未提供 |
| `avg_crn_for_away` | 源站原始字段(见同目录样本) | 4.5 | 空=源站未提供 |
| `avg_crn_against_home` | 源站原始字段(见同目录样本) | 5.1053 | 空=源站未提供 |
| `avg_crn_against_away` | 源站原始字段(见同目录样本) | 7.0 | 空=源站未提供 |
| `avg_sot_for` | 源站原始字段(见同目录样本) | 4.8289 | 空=源站未提供 |
| `avg_sot_against` | 源站原始字段(见同目录样本) | 4.7632 | 空=源站未提供 |
| `over_8_5_pct` | 源站原始字段(见同目录样本) | 0.8026 | 空=源站未提供 |
| `over_9_5_pct` | 源站原始字段(见同目录样本) | 0.6579 | 空=源站未提供 |
| `over_10_5_pct` | 源站原始字段(见同目录样本) | 0.6184 | 空=源站未提供 |
| `over_11_5_pct` | 源站原始字段(见同目录样本) | 0.4737 | 空=源站未提供 |
| `over_12_5_pct` | 源站原始字段(见同目录样本) | 0.4211 | 空=源站未提供 |
| `attack_rating` | 源站原始字段(见同目录样本) | 0.9985 | 空=源站未提供 |
| `defense_rating` | 源站原始字段(见同目录样本) | 1.283 | 空=源站未提供 |
| `seasons_used` | 源站原始字段(见同目录样本) | 2425,2324+FotMob当季 | 空=源站未提供 |
| `computed_at` | 源站原始字段(见同目录样本) | 2026-10-12T04:21:56.826759 | 空=源站未提供 |

### data_quality_issue_log

- 全库行数: 17,178   样本: 100 行 -> `samples/data_quality_issue_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `entity_type` | 源站原始字段(见同目录样本) | team | 空=源站未提供 |
| `entity_key` | 源站原始字段(见同目录样本) | 西汉姆联U21 | 空=源站未提供 |
| `issue_code` | 源站原始字段(见同目录样本) | QIETY_CN_TEAM_UNMAPPED | 空=源站未提供 |
| `message` | 源站原始字段(见同目录样本) | 中文队名'西汉姆联U21'在TEAM_CN_TO_EN无… | 空=源站未提供 |
| `level` | 源站原始字段(见同目录样本) | warning | 空=源站未提供 |
| `source_name` | 源站原始字段(见同目录样本) | 00_命中系统/_model_team_en | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23 15:09:25 | 空=历史回填无时间戳 |

### dc_rho_state

- 全库行数: 252   样本: 100 行 -> `samples/dc_rho_state.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 252 | 不应为空 |
| `rho` | 源站原始字段(见同目录样本) | -0.048224219766666424 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23 06:47:27 | 空=历史回填无时间戳 |

### draw_calibration_curve

- 全库行数: 3   样本: 3 行 -> `samples/draw_calibration_curve.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 3 | 不应为空 |
| `fit_date` | 源站原始字段(见同目录样本) | 2026-08-08 | 空=源站未提供 |
| `breakpoints_json` | 源站原始字段(见同目录样本) | [0.17970362669881776, 0.1952… | 空=源站未提供 |
| `values_json` | 源站原始字段(见同目录样本) | [0.05, 0.08375, 0.1, 0.11666… | 空=源站未提供 |
| `train_samples` | 源站原始字段(见同目录样本) | 119457 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-08 10:17:57 | 空=历史回填无时间戳 |

### espn_scores

- 全库行数: 75   样本: 75 行 -> `samples/espn_scores.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 120 | 不应为空 |
| `espn_event_id` | 源站原始字段(见同目录样本) | 401856948 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_slug` | 源站原始字段(见同目录样本) | wnba | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | WNBA | 空=源站未标注 |
| `home_team` | 主队名称 | Portland Fire | 空=源站未覆盖 |
| `away_team` | 客队名称 | Atlanta Dream | 空=源站未覆盖 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-05-30 | 空=源站未提供 |
| `home_score` | 主队进球(全场) | 66 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 86 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `home_q1` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q1` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_q2` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q2` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_q3` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q3` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_q4` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q4` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_ot` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_ot` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `status` | 比赛状态 | Final | 空=未知 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-05-31 | 空=源站未提供 |

### euroleague_boxscores

- 全库行数: 202   样本: 100 行 -> `samples/euroleague_boxscores.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 202 | 不应为空 |
| `comp` | 源站原始字段(见同目录样本) | U | 空=源站未提供 |
| `season` | 赛季标识 | U2024 | 空=源站未提供 |
| `game_code` | 源站原始字段(见同目录样本) | 141 | 空=源站未提供 |
| `team_side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `club_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `club_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `score` | 源站原始字段(见同目录样本) | 81 | 空=源站未提供 |
| `fg_made` | 源站原始字段(见同目录样本) | 29 | 空=源站未提供 |
| `fg_attempted` | 源站原始字段(见同目录样本) | 61 | 空=源站未提供 |
| `fg2_made` | 源站原始字段(见同目录样本) | 23 | 空=源站未提供 |
| `fg3_made` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `ft_made` | 源站原始字段(见同目录样本) | 17 | 空=源站未提供 |
| `ft_attempted` | 源站原始字段(见同目录样本) | 18 | 空=源站未提供 |
| `assists` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `rebounds` | 源站原始字段(见同目录样本) | 35 | 空=源站未提供 |
| `off_rebounds` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `def_rebounds` | 源站原始字段(见同目录样本) | 27 | 空=源站未提供 |
| `steals` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `blocks` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `turnovers` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `fouls` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-12 | 空=源站未提供 |

### euroleague_clubs

- 全库行数: 38   样本: 38 行 -> `samples/euroleague_clubs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 4446 | 不应为空 |
| `comp` | 源站原始字段(见同目录样本) | U | 空=源站未提供 |
| `season` | 赛季标识 | U2024 | 空=源站未提供 |
| `club_code` | 源站原始字段(见同目录样本) | WOL | 空=源站未提供 |
| `club_name` | 源站原始字段(见同目录样本) | Wolves Twinsbet Vilnius | 空=源站未提供 |
| `country` | 源站原始字段(见同目录样本) | LTU | 空=源站未提供 |
| `arena` | 源站原始字段(见同目录样本) | Vilnius | 空=源站未提供 |
| `logo_url` | 源站原始字段(见同目录样本) | https://media-cdn.incrowdspo… | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### euroleague_games

- 全库行数: 101   样本: 100 行 -> `samples/euroleague_games.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 11650 | 不应为空 |
| `comp` | 源站原始字段(见同目录样本) | U | 空=源站未提供 |
| `season` | 赛季标识 | U2024 | 空=源站未提供 |
| `game_code` | 源站原始字段(见同目录样本) | 147 | 空=源站未提供 |
| `phase` | 源站原始字段(见同目录样本) | RS | 空=源站未提供 |
| `round` | 源站原始字段(见同目录样本) | 15 | 空=源站未提供 |
| `game_date` | 源站原始字段(见同目录样本) | 2025-01-15 | 空=源站未提供 |
| `home_code` | 源站原始字段(见同目录样本) | ARI | 空=源站未提供 |
| `home_name` | 主队名称 | Aris Midea Thessaloniki | 空=源站未覆盖 |
| `away_code` | 源站原始字段(见同目录样本) | BOU | 空=源站未提供 |
| `away_name` | 客队名称 | Cosea JL Bourg-en-Bresse | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 51 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 92 | 空=未开赛或源站未覆盖，不是0 |
| `played` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `arena` | 源站原始字段(见同目录样本) | PALAIS DE SPORTS | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### euroleague_standings

- 全库行数: 38   样本: 38 行 -> `samples/euroleague_standings.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 4502 | 不应为空 |
| `comp` | 源站原始字段(见同目录样本) | U | 空=源站未提供 |
| `season` | 赛季标识 | U2024 | 空=源站未提供 |
| `phase` | 源站原始字段(见同目录样本) | RS | 空=源站未提供 |
| `group_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `club_code` | 源站原始字段(见同目录样本) | ARI | 空=源站未提供 |
| `club_name` | 源站原始字段(见同目录样本) | Aris Midea Thessaloniki | 空=源站未提供 |
| `position` | 源站原始字段(见同目录样本) | 20 | 空=源站未提供 |
| `games_played` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `wins` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `losses` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `points_scored` | 源站原始字段(见同目录样本) | 278 | 空=源站未提供 |
| `points_against` | 源站原始字段(见同目录样本) | 377 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### fbref_match_stats

- 全库行数: 9,069   样本: 100 行 -> `samples/fbref_match_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 182296 | 不应为空 |
| `season` | 赛季标识 | 2026-27 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Belgium - Pro League | 空=源站未标注 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-08-09 | 空=源站未提供 |
| `home_team` | 主队名称 | Jagiellonia | 空=源站未覆盖 |
| `away_team` | 客队名称 | Widzew Łódź | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `home_xg` | 预期进球xG |  | 空=源站无xG |
| `away_xg` | 预期进球xG |  | 空=源站无xG |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-12 | 空=源站未提供 |

### fd_corner_stats

- 全库行数: 155,213   样本: 100 行 -> `samples/fd_corner_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 295666 | 不应为空 |
| `league_code` | 源站原始字段(见同目录样本) | D2 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 德国乙级联赛 | 空=源站未标注 |
| `season` | 赛季标识 | 2425 | 空=源站未提供 |
| `date` | 源站原始字段(见同目录样本) | 18/05/2025 | 空=源站未提供 |
| `home_team` | 主队名称 | Ulm | 空=源站未覆盖 |
| `away_team` | 客队名称 | Preußen Münster | 空=源站未覆盖 |
| `fthg` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `ftag` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `hc` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `ac` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `total_corners` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `hs` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `as_shots` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `hst` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `ast` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `hf` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `af` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `hy` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `ay` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `hr` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `ar` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `b365h` | 主胜赔率 | 3.7 | 空=该场无此盘口/未抓取，不是0 |
| `b365d` | 平局赔率 | 3.5 | 空=无平局盘口 |
| `b365a` | 客胜赔率 | 1.91 | 空=该场无此盘口 |
| `bwh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bwd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bwa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `psh` | 源站原始字段(见同目录样本) | 3.45 | 空=源站未提供 |
| `psd` | 源站原始字段(见同目录样本) | 3.77 | 空=源站未提供 |
| `psa` | 源站原始字段(见同目录样本) | 1.99 | 空=源站未提供 |
| `max_h` | 源站原始字段(见同目录样本) | 3.7 | 空=源站未提供 |
| `max_d` | 源站原始字段(见同目录样本) | 3.9 | 空=源站未提供 |
| `max_a` | 源站原始字段(见同目录样本) | 2.01 | 空=源站未提供 |
| `avg_h` | 主胜赔率 | 3.47 | 空=该场无此盘口/未抓取，不是0 |
| `avg_d` | 平局赔率 | 3.72 | 空=无平局盘口 |
| `avg_a` | 客胜赔率 | 1.96 | 空=该场无此盘口 |
| `b365_o25` | 源站原始字段(见同目录样本) | 1.67 | 空=源站未提供 |
| `b365_u25` | 源站原始字段(见同目录样本) | 2.15 | 空=源站未提供 |
| `avg_o25` | 源站原始字段(见同目录样本) | 1.65 | 空=源站未提供 |
| `avg_u25` | 源站原始字段(见同目录样本) | 2.17 | 空=源站未提供 |
| `ah_handicap` | 源站原始字段(见同目录样本) | 0.5 | 空=源站未提供 |
| `b365_ahh` | 源站原始字段(见同目录样本) | 1.83 | 空=源站未提供 |
| `b365_aha` | 源站原始字段(见同目录样本) | 1.98 | 空=源站未提供 |
| `avg_ahh` | 源站原始字段(见同目录样本) | 1.83 | 空=源站未提供 |
| `avg_aha` | 源站原始字段(见同目录样本) | 1.95 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | football-data.co.uk | 空=源站未提供 |

### fd_elo_ratings

- 全库行数: 1,298   样本: 100 行 -> `samples/fd_elo_ratings.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `team` | 源站原始字段(见同目录样本) | Nantes | 空=源站未提供 |
| `elo` | 源站原始字段(见同目录样本) | 1640.02 | 空=源站未提供 |
| `played` | 源站原始字段(见同目录样本) | 1169 | 空=源站未提供 |
| `last_match_date` | 源站原始字段(见同目录样本) | 2026-05-17 | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-09-13 15:25:05 | 空=历史回填无时间戳 |

### fd_matches

- 全库行数: 309,641   样本: 100 行 -> `samples/fd_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2899715 | 不应为空 |
| `season` | 赛季标识 | 2324 | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | G1 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Greece - Super League | 空=源站未标注 |
| `match_date` | 源站原始字段(见同目录样本) | 2024-05-19 | 空=源站未提供 |
| `match_time` | 开赛时间 | 18:00 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | Panathinaikos | 空=源站未覆盖 |
| `away_team` | 客队名称 | Olympiakos | 空=源站未覆盖 |
| `fthg` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `ftag` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `ftr` | 源站原始字段(见同目录样本) | D | 空=源站未提供 |
| `hthg` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `htag` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `htr` | 源站原始字段(见同目录样本) | H | 空=源站未提供 |
| `home_shots` | 源站原始字段(见同目录样本) | 11 | 空=源站未提供 |
| `away_shots` | 源站原始字段(见同目录样本) | 9 | 空=源站未提供 |
| `home_shots_target` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `away_shots_target` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `home_corners` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `home_yellow` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `away_yellow` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `home_red` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `away_red` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `b365h` | 主胜赔率 | 2.7 | 空=该场无此盘口/未抓取，不是0 |
| `b365d` | 平局赔率 | 3.3 | 空=无平局盘口 |
| `b365a` | 客胜赔率 | 2.55 | 空=该场无此盘口 |
| `psh` | 源站原始字段(见同目录样本) | 2.69 | 空=源站未提供 |
| `psd` | 源站原始字段(见同目录样本) | 3.48 | 空=源站未提供 |
| `psa` | 源站原始字段(见同目录样本) | 2.5 | 空=源站未提供 |
| `b365_over25` | 源站原始字段(见同目录样本) | 1.9 | 空=源站未提供 |
| `b365_under25` | 源站原始字段(见同目录样本) | 1.95 | 空=源站未提供 |
| `b365_ahh` | 源站原始字段(见同目录样本) | 2.0 | 空=源站未提供 |
| `b365_aha` | 源站原始字段(见同目录样本) | 1.85 | 空=源站未提供 |
| `ah_handicap` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `max_over25` | 源站原始字段(见同目录样本) | 1.92 | 空=源站未提供 |
| `max_under25` | 源站原始字段(见同目录样本) | 1.95 | 空=源站未提供 |
| `avg_over25` | 源站原始字段(见同目录样本) | 1.85 | 空=源站未提供 |
| `avg_under25` | 源站原始字段(见同目录样本) | 1.91 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `country` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hs` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `as_shots` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hst` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ast` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hc` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ac` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hf` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `af` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hy` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ay` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hr` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ar` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bwh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bwd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bwa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `iwh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `iwd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `iwa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `whh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `whd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `wha` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `vch` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `vcd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `vca` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbmxh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbavh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbmxd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbavd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbmxa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbava` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_fouls` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_fouls` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `p_over25` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `p_under25` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_elo` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_elo` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form3_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form5_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form3_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form5_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### fd_matches_2627_fotmob

- 全库行数: 234   样本: 100 行 -> `samples/fd_matches_2627_fotmob.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 234 | 不应为空 |
| `league_code` | 源站原始字段(见同目录样本) | N1 | 空=源站未提供 |
| `season` | 赛季标识 | 26-27 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-09-08 | 空=源站未提供 |
| `home_team` | 主队名称 | Nijmegen | 空=源站未覆盖 |
| `away_team` | 客队名称 | Excelsior | 空=源站未覆盖 |
| `fthg` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `ftag` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `home_corners` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `fotmob_match_id` | 源站原始字段(见同目录样本) | 5781720 | 空=源站未提供 |
| `fs_check` | 源站原始字段(见同目录样本) | verified | 空=源站未提供 |
| `name_mapped` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `fetched_at` | 源站原始字段(见同目录样本) | 2026-09-10 15:02:38 | 空=源站未提供 |

### fd_matches_archive_fix004

- 全库行数: 22,358   样本: 100 行 -> `samples/fd_matches_archive_fix004.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 430001 | 不应为空 |
| `season` | 赛季标识 | 25-26 | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | SC1 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Championship | 空=源站未标注 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-05-01 | 空=源站未提供 |
| `match_time` | 开赛时间 | 19:45 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | Raith Rvs | 空=源站未覆盖 |
| `away_team` | 客队名称 | Ross County | 空=源站未覆盖 |
| `fthg` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `ftag` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `ftr` | 源站原始字段(见同目录样本) | H | 空=源站未提供 |
| `hthg` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `htag` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `htr` | 源站原始字段(见同目录样本) | A | 空=源站未提供 |
| `home_shots` | 源站原始字段(见同目录样本) | 13 | 空=源站未提供 |
| `away_shots` | 源站原始字段(见同目录样本) | 11 | 空=源站未提供 |
| `home_shots_target` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `away_shots_target` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `home_corners` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `home_yellow` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `away_yellow` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `home_red` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `away_red` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `b365h` | 主胜赔率 | 2.7 | 空=该场无此盘口/未抓取，不是0 |
| `b365d` | 平局赔率 | 3.25 | 空=无平局盘口 |
| `b365a` | 客胜赔率 | 2.35 | 空=该场无此盘口 |
| `psh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `psd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `psa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `b365_over25` | 源站原始字段(见同目录样本) | 2.05 | 空=源站未提供 |
| `b365_under25` | 源站原始字段(见同目录样本) | 1.75 | 空=源站未提供 |
| `b365_ahh` | 源站原始字段(见同目录样本) | 2.05 | 空=源站未提供 |
| `b365_aha` | 源站原始字段(见同目录样本) | 1.75 | 空=源站未提供 |
| `ah_handicap` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `max_over25` | 源站原始字段(见同目录样本) | 2.05 | 空=源站未提供 |
| `max_under25` | 源站原始字段(见同目录样本) | 1.93 | 空=源站未提供 |
| `avg_over25` | 源站原始字段(见同目录样本) | 1.91 | 空=源站未提供 |
| `avg_under25` | 源站原始字段(见同目录样本) | 1.8 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-07 | 空=源站未提供 |
| `country` | 源站原始字段(见同目录样本) | Scotland | 空=源站未提供 |
| `hs` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `as_shots` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hst` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ast` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hc` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ac` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hf` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `af` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hy` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ay` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `hr` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `ar` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bwh` | 源站原始字段(见同目录样本) | 2.6 | 空=源站未提供 |
| `bwd` | 源站原始字段(见同目录样本) | 3.2 | 空=源站未提供 |
| `bwa` | 源站原始字段(见同目录样本) | 2.35 | 空=源站未提供 |
| `iwh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `iwd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `iwa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `whh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `whd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `wha` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `vch` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `vcd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `vca` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbmxh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbavh` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbmxd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbavd` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbmxa` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `bbava` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_fouls` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `away_fouls` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `p_over25` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `p_under25` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_elo` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_elo` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form3_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form5_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form3_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `form5_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `archived_at` | 源站原始字段(见同目录样本) | 2026-09-13 02:20:21 | 空=源站未提供 |
| `archive_reason` | 源站原始字段(见同目录样本) | dup_group_lower_completeness | 空=源站未提供 |

### fdcouk_elo_ratings

- 全库行数: 245,033   样本: 100 行 -> `samples/fdcouk_elo_ratings.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 245033 | 不应为空 |
| `date` | 源站原始字段(见同目录样本) | 2025-06-01 | 空=源站未提供 |
| `club` | 源站原始字段(见同目录样本) | Zwolle | 空=源站未提供 |
| `country` | 源站原始字段(见同目录样本) | NED | 空=源站未提供 |
| `elo` | 源站原始字段(见同目录样本) | 1462.81 | 空=源站未提供 |

### fdcouk_matches

- 全库行数: 230,557   样本: 100 行 -> `samples/fdcouk_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 230557 | 不应为空 |
| `division` | 源站原始字段(见同目录样本) | SP2 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2025-06-01 | 空=源站未提供 |
| `match_time` | 开赛时间 | 20:00:00 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | Cordoba | 空=源站未覆盖 |
| `away_team` | 客队名称 | Albacete | 空=源站未覆盖 |
| `home_elo` | 源站原始字段(见同目录样本) | 1468.4 | 空=源站未提供 |
| `away_elo` | 源站原始字段(见同目录样本) | 1495.25 | 空=源站未提供 |
| `form3_home` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `form5_home` | 源站原始字段(见同目录样本) | 4.0 | 空=源站未提供 |
| `form3_away` | 源站原始字段(见同目录样本) | 6.0 | 空=源站未提供 |
| `form5_away` | 源站原始字段(见同目录样本) | 9.0 | 空=源站未提供 |
| `ft_home` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `ft_away` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `ft_result` | 源站原始字段(见同目录样本) | D | 空=源站未提供 |
| `ht_home` | 主队半场进球 | 0.0 | 空=无半场数据 |
| `ht_away` | 客队半场进球 | 1.0 | 空=无半场数据 |
| `ht_result` | 源站原始字段(见同目录样本) | A | 空=源站未提供 |
| `home_shots` | 源站原始字段(见同目录样本) | 37.0 | 空=源站未提供 |
| `away_shots` | 源站原始字段(见同目录样本) | 7.0 | 空=源站未提供 |
| `home_target` | 源站原始字段(见同目录样本) | 9.0 | 空=源站未提供 |
| `away_target` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `home_fouls` | 源站原始字段(见同目录样本) | 13.0 | 空=源站未提供 |
| `away_fouls` | 源站原始字段(见同目录样本) | 11.0 | 空=源站未提供 |
| `home_corners` | 源站原始字段(见同目录样本) | 9.0 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 5.0 | 空=源站未提供 |
| `home_yellow` | 源站原始字段(见同目录样本) | 2.0 | 空=源站未提供 |
| `away_yellow` | 源站原始字段(见同目录样本) | 3.0 | 空=源站未提供 |
| `home_red` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `away_red` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `odd_home` | 源站原始字段(见同目录样本) | 1.6 | 空=源站未提供 |
| `odd_draw` | 源站原始字段(见同目录样本) | 4.01 | 空=源站未提供 |
| `odd_away` | 源站原始字段(见同目录样本) | 5.08 | 空=源站未提供 |
| `max_home` | 源站原始字段(见同目录样本) | 1.66 | 空=源站未提供 |
| `max_draw` | 源站原始字段(见同目录样本) | 4.5 | 空=源站未提供 |
| `max_away` | 源站原始字段(见同目录样本) | 5.6 | 空=源站未提供 |
| `over25` | 源站原始字段(见同目录样本) | 1.48 | 空=源站未提供 |
| `under25` | 源站原始字段(见同目录样本) | 2.51 | 空=源站未提供 |
| `max_over25` | 源站原始字段(见同目录样本) | 1.53 | 空=源站未提供 |
| `max_under25` | 源站原始字段(见同目录样本) | 2.7 | 空=源站未提供 |
| `handi_size` | 源站原始字段(见同目录样本) | -1.0 | 空=源站未提供 |
| `handi_home` | 源站原始字段(见同目录样本) | 2.0 | 空=源站未提供 |
| `handi_away` | 源站原始字段(见同目录样本) | 1.8 | 空=源站未提供 |
| `c_lth` | 源站原始字段(见同目录样本) | 0.0191 | 空=源站未提供 |
| `c_lta` | 源站原始字段(见同目录样本) | 0.0203 | 空=源站未提供 |
| `c_vhd` | 源站原始字段(见同目录样本) | 0.0937 | 空=源站未提供 |
| `c_vad` | 源站原始字段(见同目录样本) | 0.0164 | 空=源站未提供 |
| `c_htb` | 源站原始字段(见同目录样本) | 0.8251 | 空=源站未提供 |
| `c_phb` | 源站原始字段(见同目录样本) | 0.0254 | 空=源站未提供 |

### fixture_lineups

- 全库行数: 29,103   样本: 100 行 -> `samples/fixture_lineups.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 17289003 | 不应为空 |
| `lineup_key` | 源站原始字段(见同目录样本) | b99339053f5eb3f374b430f53923… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `source_fixture_id` | 源站原始字段(见同目录样本) | 5749722 | 空=源站未提供 |
| `source_team_id` | 源站原始字段(见同目录样本) | 8524 | 空=源站未提供 |
| `source_player_id` | 源站原始字段(见同目录样本) | 1130691 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | Kamaldeen Sulemana | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lineup_type` | 源站原始字段(见同目录样本) | standard | 空=源站未提供 |
| `lineup_confirmed` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lineup_announcement_at` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lineup_first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-29T19:37:13Z | 空=源站未提供 |
| `formation` | 源站原始字段(见同目录样本) | 4-2-3-1 | 空=源站未提供 |
| `position` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `role` | 源站原始字段(见同目录样本) | substitute | 空=源站未提供 |
| `squad_status` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `provider_updated_at` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-29T19:37:13Z | 空=源站未提供 |
| `first_seen_status` | 源站原始字段(见同目录样本) | PROVEN | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `receipt_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_json` | 源站原始字段(见同目录样本) | {"shirt_number": "7", "natio… | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | confirmed lineup; official a… | 空=源站未提供 |
| `lineup_source_type` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lineup_publishable` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `announcement_evidence` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `position_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `formation_position` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `jersey_number` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lineup_meta_confirmed` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### flashscore_matches

- 全库行数: 4,522   样本: 100 行 -> `samples/flashscore_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 225691 | 不应为空 |
| `flash_id` | 源站原始字段(见同目录样本) | GQEjF8fJ | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | africa_bal | 空=源站未提供 |
| `league_path` | 源站原始字段(见同目录样本) | /basketball/africa/bal/ | 空=源站未提供 |
| `home_team` | 主队名称 | Maktown Flyers (Nga) | 空=源站未覆盖 |
| `away_team` | 客队名称 | Ville de Dakar (Sen) | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-05-03T14:00:00 | 空=源站未提供 |
| `status` | 比赛状态 | FT | 空=未知 |
| `home_score` | 主队进球(全场) | 62 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 79 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-29 22:35:36 | 空=历史回填无时间戳 |
| `superseded` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `superseded_note` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### flashscore_scrape_log

- 全库行数: 3,426   样本: 100 行 -> `samples/flashscore_scrape_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league_code` | 源站原始字段(见同目录样本) | premier_league | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-07-31 | 空=源站未提供 |
| `scraped_at` | 源站原始字段(见同目录样本) | 2026-07-31 20:40:23 | 空=源站未提供 |

### football_matches

- 全库行数: 8,202   样本: 100 行 -> `samples/football_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | premier_league | 空=源站未标注 |
| `league_id` | 源站原始字段(见同目录样本) | 39 | 空=源站未提供 |
| `season` | 赛季标识 | 2024 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2024-08-16 | 空=源站未提供 |
| `home_team` | 主队名称 | Manchester United | 空=源站未覆盖 |
| `away_team` | 客队名称 | Fulham | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 1.0 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 0.0 | 空=未开赛或源站未覆盖，不是0 |
| `status` | 比赛状态 | Match Finished | 空=未知 |

### football_score_predictions

- 全库行数: 17,273   样本: 100 行 -> `samples/football_score_predictions.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 46980 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 7227975eff9b | 空=源站未提供 |
| `home_team` | 主队名称 | Deportes Iquique | 空=源站未覆盖 |
| `away_team` | 客队名称 | Magallanes | 空=源站未覆盖 |
| `league_name` | 联赛/赛事名称 | Chile - Primera B | 空=源站未标注 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T23:00:00Z | 空=源站未提供 |
| `top_score` | 源站原始字段(见同目录样本) | 1-1 | 空=源站未提供 |
| `lambda_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lambda_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `engine` | 源站原始字段(见同目录样本) | xG | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T15:02:01 | 空=历史回填无时间戳 |

### football_team_stats

- 全库行数: 1,598   样本: 100 行 -> `samples/football_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2399 | 不应为空 |
| `league` | 联赛/赛事名称 | morocco_botola | 空=源站未标注 |
| `team_name` | 源站原始字段(见同目录样本) | Ittihad Tanger | 空=源站未提供 |
| `season` | 赛季标识 | 2025 | 空=源站未提供 |
| `gp` | 源站原始字段(见同目录样本) | 25 | 空=源站未提供 |
| `wins` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `draws` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `losses` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `goals_for` | 源站原始字段(见同目录样本) | 29.0 | 空=源站未提供 |
| `goals_against` | 源站原始字段(见同目录样本) | 31.0 | 空=源站未提供 |
| `goals_for_home` | 源站原始字段(见同目录样本) | 17.0 | 空=源站未提供 |
| `goals_against_home` | 源站原始字段(见同目录样本) | 14.0 | 空=源站未提供 |
| `goals_for_away` | 源站原始字段(见同目录样本) | 12.0 | 空=源站未提供 |
| `goals_against_away` | 源站原始字段(见同目录样本) | 17.0 | 空=源站未提供 |
| `avg_total` | 源站原始字段(见同目录样本) | 2.4 | 空=源站未提供 |
| `avg_home_total` | 源站原始字段(见同目录样本) | 2.3846 | 空=源站未提供 |
| `avg_away_total` | 源站原始字段(见同目录样本) | 2.4167 | 空=源站未提供 |
| `over25_pct` | 源站原始字段(见同目录样本) | 0.36 | 空=源站未提供 |
| `under25_pct` | 源站原始字段(见同目录样本) | 0.64 | 空=源站未提供 |
| `avg_scored` | 源站原始字段(见同目录样本) | 1.16 | 空=源站未提供 |
| `avg_conceded` | 源站原始字段(见同目录样本) | 1.24 | 空=源站未提供 |
| `clean_sheets` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `clean_sheets_pct` | 源站原始字段(见同目录样本) | 0.24 | 空=源站未提供 |
| `failed_to_score` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `last6_wins` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `last6_draws` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `last6_losses` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `last6_gf` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `last6_ga` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `computed_at` | 源站原始字段(见同目录样本) | 2026-06-12T11:47:46.655394 | 空=源站未提供 |

### football_xg_stats

- 全库行数: 495   样本: 100 行 -> `samples/football_xg_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | Premier League | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | Aston Villa | 空=源站未提供 |
| `xg_off` | 源站原始字段(见同目录样本) | 1.138 | 空=源站未提供 |
| `xg_def` | 源站原始字段(见同目录样本) | 2.0229 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | understat | 空=源站未提供 |

### fotmob_fixtures

- 全库行数: 393   样本: 100 行 -> `samples/fotmob_fixtures.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | 5781786 | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 57 | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | N1 | 空=源站未提供 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-31T20:00:00 | 空=源站未提供 |
| `home_team` | 主队名称 | Ajax | 空=源站未覆盖 |
| `away_team` | 客队名称 | AZ Alkmaar | 空=源站未覆盖 |
| `status` | 比赛状态 | NS | 空=未知 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-30 06:40:02 | 空=历史回填无时间戳 |

### fotmob_h2h_matches

- 全库行数: 8,464   样本: 100 行 -> `samples/fotmob_h2h_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `row_key` | 源站原始字段(见同目录样本) | 378d02d478d4f98ed4ff451eb93c… | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 5103644 | 空=源站未提供 |
| `h2h_match_url` | 源站原始字段(见同目录样本) | /matches/coritiba-vs-flumine… | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 268 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Série A | 空=源站未标注 |
| `home_team_id` | 源站原始字段(见同目录样本) | 9767 | 空=源站未提供 |
| `home_team_name` | 源站原始字段(见同目录样本) | Coritiba | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | 9863 | 空=源站未提供 |
| `away_team_name` | 源站原始字段(见同目录样本) | Fluminense | 空=源站未提供 |
| `match_utc` | 开赛时间 | 2026-04-04T23:30:00.000Z | UTC或源站时区，需按README时区说明换算 |
| `finished` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `status_utc` | 源站原始字段(见同目录样本) | 2026-04-04T23:30:00.000Z | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:16:09Z | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) | 010b186edd610fd41e25018ead32… | 空=源站未提供 |
| `receipt_id` | 源站原始字段(见同目录样本) | 1caf4a61bff5ba804a310ef55003… | 空=源站未提供 |
| `is_future` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |

### fotmob_lineup_players

- 全库行数: 25,427   样本: 100 行 -> `samples/fotmob_lineup_players.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 85719 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5749722 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 8524 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `lineup_type` | 源站原始字段(见同目录样本) | standard | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) | 1113694 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | Jonathan Rowe | 空=源站未提供 |
| `first_name` | 源站原始字段(见同目录样本) | Jonathan | 空=源站未提供 |
| `last_name` | 源站原始字段(见同目录样本) | Rowe | 空=源站未提供 |
| `shirt_number` | 源站原始字段(见同目录样本) | 11 | 空=源站未提供 |
| `position_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `usual_position_id` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `nationality` | 源站原始字段(见同目录样本) | England | 空=源站未提供 |
| `country_code` | 源站原始字段(见同目录样本) | ENG | 空=源站未提供 |
| `age` | 源站原始字段(见同目录样本) | 23 | 空=源站未提供 |
| `is_starter` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `market_value` | 源站原始字段(见同目录样本) | 32148084.0 | 空=源站未提供 |
| `rating` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `formation` | 源站原始字段(见同目录样本) | 4-2-3-1 | 空=源站未提供 |
| `coach_name` | 源站原始字段(见同目录样本) | Maurizio Sarri | 空=源站未提供 |
| `lineup_announced_at_utc` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_player_json` | 源站原始字段(见同目录样本) | {"id": 1113694, "age": 23, "… | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-29T19:37:13Z | 空=源站未提供 |
| `observation_id` | 源站原始字段(见同目录样本) | 72b25bf916afa0b7baf50ccbbc98… | 空=源站未提供 |

### fotmob_lineups

- 全库行数: 35,336   样本: 100 行 -> `samples/fotmob_lineups.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 35936 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5107640 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 8127 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `formation` | 源站原始字段(见同目录样本) | 5-3-2 | 空=源站未提供 |
| `coach_name` | 源站原始字段(见同目录样本) | Andreas Brännström | 空=源站未提供 |
| `avg_starter_age` | 源站原始字段(见同目录样本) | 28.6 | 空=源站未提供 |
| `total_starter_mkt_value` | 源站原始字段(见同目录样本) | 7874137.0 | 空=源站未提供 |
| `starters_json` | 源站原始字段(见同目录样本) | [{"id": 213852, "age": 34, "… | 空=源站未提供 |
| `subs_json` | 源站原始字段(见同目录样本) | [{"id": 1155663, "age": 22, … | 空=源站未提供 |

### fotmob_match_availability

- 全库行数: 2,525   样本: 100 行 -> `samples/fotmob_match_availability.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 12415 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5749722 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 8524 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | awayTeam | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) | 721089 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | Gianluca Scamacca | 空=源站未提供 |
| `availability_type` | 源站原始字段(见同目录样本) | injury | 空=源站未提供 |
| `status` | 比赛状态 | unavailable | 空=未知 |
| `reason` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `provided` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `source_json` | 源站原始字段(见同目录样本) | {"id": 721089, "age": 27, "n… | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-29T19:37:13Z | 空=源站未提供 |
| `observation_id` | 源站原始字段(见同目录样本) | 72b25bf916afa0b7baf50ccbbc98… | 空=源站未提供 |

### fotmob_match_events

- 全库行数: 3,116   样本: 100 行 -> `samples/fotmob_match_events.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 3514 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5186620 | 空=源站未提供 |
| `event_key` | 源站原始字段(见同目录样本) | 7da93aa2f62c520a943d2a74e39b… | 空=源站未提供 |
| `event_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `event_type` | 源站原始字段(见同目录样本) | Half | 空=源站未提供 |
| `minute` | 源站原始字段(见同目录样本) | 90 | 空=源站未提供 |
| `min_added` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `is_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) |  | 空=源站未提供 |
| `assist_player_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `assist_player_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `card_type` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `is_own_goal` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `is_penalty` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `score_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `score_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `raw_event_json` | 源站原始字段(见同目录样本) | {"reactKey": "undefined90Hal… | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-12T04:19:53Z | 空=源站未提供 |
| `observation_id` | 源站原始字段(见同目录样本) | 209e24196ae95c4cbc7932914d79… | 空=源站未提供 |

### fotmob_match_identity

- 全库行数: 440   样本: 100 行 -> `samples/fotmob_match_identity.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | 5071396 | 空=源站未提供 |
| `source_match_id` | 源站原始字段(见同目录样本) | 5071396 | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 10000001 | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Major League Soccer | 空=源站未标注 |
| `season_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `season_name` | 源站原始字段(见同目录样本) | 2026 | 空=源站未提供 |
| `home_team_id` | 源站原始字段(见同目录样本) | 773958 | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | 722265 | 空=源站未提供 |
| `home_team_name` | 源站原始字段(见同目录样本) | Atlanta United | 空=源站未提供 |
| `away_team_name` | 源站原始字段(见同目录样本) | FC Cincinnati | 空=源站未提供 |
| `home_role` | 源站原始字段(见同目录样本) | home | 空=源站未提供 |
| `away_role` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `kickoff_utc_raw` | 源站原始字段(见同目录样本) | 2026-10-10T23:30:00.000Z | 空=源站未提供 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-10T23:30:00 | 空=源站未提供 |
| `status` | 比赛状态 | NS | 空=未知 |
| `status_reason` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `match_state` | 源站原始字段(见同目录样本) | prematch | 空=源站未提供 |
| `started` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `finished` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `round` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `competition_stage` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `venue` | 源站原始字段(见同目录样本) | Mercedes-Benz Stadium | 空=源站未提供 |
| `schedule_change_history` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_endpoint` | 源站原始字段(见同目录样本) | matchDetails | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-10T22:37:17Z | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-10T22:37:17Z | 空=源站未提供 |
| `last_observation_id` | 源站原始字段(见同目录样本) | 720a610155b8bb49dbcb8b10bf50… | 空=源站未提供 |
| `field_provenance` | 源站原始字段(见同目录样本) | {"away_role": "provided", "a… | 空=源站未提供 |
| `null_reasons` | 源站原始字段(见同目录样本) | {"competition_stage": "provi… | 空=源站未提供 |

### fotmob_match_stats_raw

- 全库行数: 68,134   样本: 100 行 -> `samples/fotmob_match_stats_raw.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 68282 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5186620 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 1029687 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | SecondHalf | 空=源站未提供 |
| `group_key` | 源站原始字段(见同目录样本) | discipline | 空=源站未提供 |
| `group_title` | 源站原始字段(见同目录样本) | Discipline | 空=源站未提供 |
| `stat_key` | 源站原始字段(见同目录样本) | fouls | 空=源站未提供 |
| `stat_title` | 源站原始字段(见同目录样本) | Fouls committed | 空=源站未提供 |
| `stat_format` | 源站原始字段(见同目录样本) | integer | 空=源站未提供 |
| `raw_value` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `value_num` | 源站原始字段(见同目录样本) | 8.0 | 空=源站未提供 |
| `value_pct` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `unit` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `highlight` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-12T04:19:53Z | 空=源站未提供 |
| `observation_id` | 源站原始字段(见同目录样本) | 209e24196ae95c4cbc7932914d79… | 空=源站未提供 |

### fotmob_match_team_stats

- 全库行数: 35,468   样本: 100 行 -> `samples/fotmob_match_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 36184 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5107640 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 8127 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `total_shots` | 源站原始字段(见同目录样本) | 13.0 | 空=源站未提供 |
| `shots_on_target` | 源站原始字段(见同目录样本) | 5.0 | 空=源站未提供 |
| `shots_off_target` | 源站原始字段(见同目录样本) | 8.0 | 空=源站未提供 |
| `blocked_shots` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `hit_woodwork` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `shots_inside_box` | 源站原始字段(见同目录样本) | 9.0 | 空=源站未提供 |
| `shots_outside_box` | 源站原始字段(见同目录样本) | 4.0 | 空=源站未提供 |
| `big_chances` | 源站原始字段(见同目录样本) | 3.0 | 空=源站未提供 |
| `big_chances_missed` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `touches_opp_box` | 源站原始字段(见同目录样本) | 20.0 | 空=源站未提供 |
| `xg` | 预期进球xG | 1.68 | 空=源站无xG |
| `xg_open_play` | 源站原始字段(见同目录样本) | 0.94 | 空=源站未提供 |
| `xg_set_play` | 源站原始字段(见同目录样本) | 0.74 | 空=源站未提供 |
| `xg_non_penalty` | 源站原始字段(见同目录样本) | 1.68 | 空=源站未提供 |
| `xgot` | 源站原始字段(见同目录样本) | 1.38 | 空=源站未提供 |
| `distance_covered` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `walking_distance` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `running_distance` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `sprint_distance` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `num_sprints` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `passes_total` | 源站原始字段(见同目录样本) | 569.0 | 空=源站未提供 |
| `accurate_passes` | 源站原始字段(见同目录样本) | 486.0 | 空=源站未提供 |
| `accurate_passes_pct` | 源站原始字段(见同目录样本) | 85.0 | 空=源站未提供 |
| `passes_own_half` | 源站原始字段(见同目录样本) | 193.0 | 空=源站未提供 |
| `passes_opp_half` | 源站原始字段(见同目录样本) | 293.0 | 空=源站未提供 |
| `accurate_long_balls` | 源站原始字段(见同目录样本) | 27.0 | 空=源站未提供 |
| `accurate_long_balls_pct` | 源站原始字段(见同目录样本) | 47.0 | 空=源站未提供 |
| `accurate_crosses` | 源站原始字段(见同目录样本) | 4.0 | 空=源站未提供 |
| `accurate_crosses_pct` | 源站原始字段(见同目录样本) | 19.0 | 空=源站未提供 |
| `throws` | 源站原始字段(见同目录样本) | 21.0 | 空=源站未提供 |
| `offsides` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `tackles` | 源站原始字段(见同目录样本) | 12.0 | 空=源站未提供 |
| `interceptions` | 源站原始字段(见同目录样本) | 8.0 | 空=源站未提供 |
| `blocks` | 源站原始字段(见同目录样本) | 5.0 | 空=源站未提供 |
| `clearances` | 源站原始字段(见同目录样本) | 29.0 | 空=源站未提供 |
| `keeper_saves` | 源站原始字段(见同目录样本) | 2.0 | 空=源站未提供 |
| `duels_won` | 源站原始字段(见同目录样本) | 40.0 | 空=源站未提供 |
| `ground_duels_won` | 源站原始字段(见同目录样本) | 25.0 | 空=源站未提供 |
| `ground_duels_won_pct` | 源站原始字段(见同目录样本) | 43.0 | 空=源站未提供 |
| `aerial_duels_won` | 源站原始字段(见同目录样本) | 15.0 | 空=源站未提供 |
| `aerial_duels_won_pct` | 源站原始字段(见同目录样本) | 45.0 | 空=源站未提供 |
| `successful_dribbles` | 源站原始字段(见同目录样本) | 4.0 | 空=源站未提供 |
| `successful_dribbles_pct` | 源站原始字段(见同目录样本) | 44.0 | 空=源站未提供 |
| `yellow_cards` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `red_cards` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `fouls_committed` | 源站原始字段(见同目录样本) | 10.0 | 空=源站未提供 |
| `corners` | 角球数 | 3.0 | 空=源站未覆盖角球 |
| `raw_stats_json` | 源站原始字段(见同目录样本) | [{"title": "Top stats", "key… | 空=源站未提供 |

### fotmob_match_weather

- 全库行数: 439   样本: 100 行 -> `samples/fotmob_match_weather.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | 5103644 | 空=源站未提供 |
| `temperature_c` | 源站原始字段(见同目录样本) | 23.0 | 空=源站未提供 |
| `wind_speed` | 源站原始字段(见同目录样本) | 3.0 | 空=源站未提供 |
| `wind_direction` | 源站原始字段(见同目录样本) | S | 空=源站未提供 |
| `relative_humidity` | 源站原始字段(见同目录样本) | 87 | 空=源站未提供 |
| `precip_chance` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `precipitation` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `snow` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `cloud_cover` | 源站原始字段(见同目录样本) | 59 | 空=源站未提供 |
| `description` | 源站原始字段(见同目录样本) | Cloudy | 空=源站未提供 |
| `icon_code` | 源站原始字段(见同目录样本) | 26 | 空=源站未提供 |
| `api_used` | 源站原始字段(见同目录样本) | current | 空=源站未提供 |
| `provider_updated_at` | 源站原始字段(见同目录样本) | 2026-10-09T02:15:00Z | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:16:09Z | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) | 010b186edd610fd41e25018ead32… | 空=源站未提供 |
| `receipt_id` | 源站原始字段(见同目录样本) | 1caf4a61bff5ba804a310ef55003… | 空=源站未提供 |

### fotmob_matches

- 全库行数: 17,737   样本: 100 行 -> `samples/fotmob_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 18093 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5107640 | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 67 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Sweden - Allsvenskan | 空=源站未标注 |
| `season` | 赛季标识 | 2026 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | Thu, Oct 29, 2026, 18:00 UTC | 空=源站未提供 |
| `home_team` | 主队名称 | Örgryte | 空=源站未覆盖 |
| `away_team` | 客队名称 | Mjällby | 空=源站未覆盖 |
| `home_team_id` | 源站原始字段(见同目录样本) | 10002 | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | 8127 | 空=源站未提供 |
| `home_score` | 主队进球(全场) | 1 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `home_xg` | 预期进球xG | 0.73 | 空=源站无xG |
| `away_xg` | 预期进球xG | 1.68 | 空=源站无xG |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |
| `home_score_ht` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |

### fotmob_player_match_stats

- 全库行数: 703,768   样本: 100 行 -> `samples/fotmob_player_match_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 705037 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5107640 | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) | 1801948 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | Marlon Ebietomere | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 10002 | 空=源站未提供 |
| `is_goalkeeper` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `usual_position` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `rating` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `minutes_played` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `goals` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `assists` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `stats_json` | 源站原始字段(见同目录样本) | [] | 空=源站未提供 |

### fotmob_raw_responses

- 全库行数: 2,844   样本: 100 行 -> `samples/fotmob_raw_responses.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `observation_id` | 源站原始字段(见同目录样本) | 5bca64947867dc09fc93bf3460d9… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `endpoint` | 源站原始字段(见同目录样本) | matchDetails | 空=源站未提供 |
| `source_match_id` | 源站原始字段(见同目录样本) | 5795472 | 空=源站未提供 |
| `source_league_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `request_url` | 源站原始字段(见同目录样本) | https://www.fotmob.com/api/d… | 空=源站未提供 |
| `request_started_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:11:20Z | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:11:22Z | 空=源站未提供 |
| `http_status` | 源站原始字段(见同目录样本) | 200 | 空=源站未提供 |
| `etag` | 源站原始字段(见同目录样本) | W/"t91ub22ga5191i" | 空=源站未提供 |
| `last_modified` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `content_type` | 源站原始字段(见同目录样本) | application/json; charset=ut… | 空=源站未提供 |
| `source_version` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_version_note` | 源站原始字段(见同目录样本) | FotMob 未提供官方数据版本号；本地 sha256 … | 空=源站未提供 |
| `raw_sha256` | 源站原始字段(见同目录样本) | bce1ad3fc56a76ab18b356844547… | 空=源站未提供 |
| `response_bytes` | 源站原始字段(见同目录样本) | 58571 | 空=源站未提供 |
| `raw_response` | 源站原始字段(见同目录样本) | {"general":{"matchId":"57954… | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:11:22Z | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:13:35Z | 空=源站未提供 |
| `observation_count` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |

### fotmob_shots

- 全库行数: 426,002   样本: 100 行 -> `samples/fotmob_shots.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 426748 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5107640 | 空=源站未提供 |
| `shot_id` | 源站原始字段(见同目录样本) | 2989860693 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 10002 | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) | 485914 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | Anton Andreasson | 空=源站未提供 |
| `minute` | 源站原始字段(见同目录样本) | 86 | 空=源站未提供 |
| `min_added` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `x` | 源站原始字段(见同目录样本) | 79.1063106808 | 空=源站未提供 |
| `y` | 源站原始字段(见同目录样本) | 27.278333333000003 | 空=源站未提供 |
| `expected_goals` | 源站原始字段(见同目录样本) | 0.028604671359062195 | 空=源站未提供 |
| `expected_goals_on_target` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `is_on_target` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `is_blocked` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `shot_type` | 源站原始字段(见同目录样本) | LeftFoot | 空=源站未提供 |
| `situation` | 源站原始字段(见同目录样本) | FromCorner | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | SecondHalf | 空=源站未提供 |
| `is_own_goal` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `event_type` | 源站原始字段(见同目录样本) | Miss | 空=源站未提供 |

### fotmob_team_form

- 全库行数: 4,517   样本: 100 行 -> `samples/fotmob_team_form.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `row_key` | 源站原始字段(见同目录样本) | 7772240eb687a6029e252d2fdb20… | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 5103644 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 9863 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | home | 空=源站未提供 |
| `seq_index` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `result` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `result_string` | 源站原始字段(见同目录样本) | W | 空=源站未提供 |
| `score` | 源站原始字段(见同目录样本) | 1 - 0 | 空=源站未提供 |
| `is_home` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `opponent_team_id` | 源站原始字段(见同目录样本) | 10276 | 空=源站未提供 |
| `opponent_name` | 源站原始字段(见同目录样本) | Vasco da Gama | 空=源站未提供 |
| `match_utc` | 开赛时间 | 2026-09-06T00:00:00.000Z | UTC或源站时区，需按README时区说明换算 |
| `source_match_ref` | 源站原始字段(见同目录样本) | /matches/fluminense-vs-vasco… | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:16:09Z | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) | 010b186edd610fd41e25018ead32… | 空=源站未提供 |
| `receipt_id` | 源站原始字段(见同目录样本) | 1caf4a61bff5ba804a310ef55003… | 空=源站未提供 |

### fs_bball_matches

- 全库行数: 1,298   样本: 100 行 -> `samples/fs_bball_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 87884 | 不应为空 |
| `flash_id` | 源站原始字段(见同目录样本) | GQEjF8fJ | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | africa_bal | 空=源站未提供 |
| `league_path` | 源站原始字段(见同目录样本) | /basketball/africa/bal/ | 空=源站未提供 |
| `home_team` | 主队名称 | Maktown Flyers (Nga) | 空=源站未覆盖 |
| `away_team` | 客队名称 | Ville de Dakar (Sen) | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-05-03T14:00:00 | 空=源站未提供 |
| `status` | 比赛状态 | FT | 空=未知 |
| `home_score` | 主队进球(全场) | 62 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 79 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_score_q1` | 源站原始字段(见同目录样本) | 15 | 空=源站未提供 |
| `home_score_q2` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `home_score_q3` | 源站原始字段(见同目录样本) | 23 | 空=源站未提供 |
| `home_score_q4` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `away_score_q1` | 源站原始字段(见同目录样本) | 18 | 空=源站未提供 |
| `away_score_q2` | 源站原始字段(见同目录样本) | 23 | 空=源站未提供 |
| `away_score_q3` | 源站原始字段(见同目录样本) | 19 | 空=源站未提供 |
| `away_score_q4` | 源站原始字段(见同目录样本) | 19 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### fs_bball_scrape_log

- 全库行数: 4,557   样本: 100 行 -> `samples/fs_bball_scrape_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `stage` | 源站原始字段(见同目录样本) | flash_league | 空=源站未提供 |
| `key` | 源站原始字段(见同目录样本) | nba | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-07-31 | 空=源站未提供 |
| `scraped_at` | 源站原始字段(见同目录样本) | 2026-07-31 20:51:56 | 空=源站未提供 |

### hit_recommendations

- 全库行数: 1,709   样本: 100 行 -> `samples/hit_recommendations.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 29287 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | d84e0c1a14a1 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Italy - Serie B | 空=源站未标注 |
| `home_team` | 主队名称 | Empoli | 空=源站未覆盖 |
| `away_team` | 客队名称 | Vicenza | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T18:30:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | spread | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.7937 | 空=源站未提供 |
| `best_source` | 源站原始字段(见同目录样本) | league_ah_edge | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.6055 | 空=源站未提供 |
| `implied_prob` | 源站原始字段(见同目录样本) | 0.5575 | 空=源站未提供 |
| `value_edge` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0271 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.4826 | 空=源站未提供 |
| `confidence` | 源站原始字段(见同目录样本) | 人工批准(联赛市场edge) | 空=源站未提供 |
| `reason` | 源站原始字段(见同目录样本) | 让球盘客队+方向联赛级市场edge——主胜赔率2.1-2… | 空=源站未提供 |
| `status` | 比赛状态 | win | 空=未知 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T15:02:08 | 空=历史回填无时间戳 |
| `quality_tier` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `is_filtered` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 0.25 | 空=无亚盘 |
| `closing_odds` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `clv` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `clv_status` | 源站原始字段(见同目录样本) | pending | 空=源站未提供 |
| `hit_score_v2` | 源站原始字段(见同目录样本) | 0.4826 | 空=源站未提供 |
| `formula_version` | 源站原始字段(见同目录样本) | league_ah_edge | 空=源站未提供 |
| `stake` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `clv_pin` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `clv_pin_fair` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `close_age_min` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `clv_pin_status` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `issued_at_utc` | 源站原始字段(见同目录样本) | 2026-10-23T15:02:08 | 空=源站未提供 |

### intl_basketball

- 全库行数: 28,680   样本: 100 行 -> `samples/intl_basketball.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 32672 | 不应为空 |
| `league_code` | 源站原始字段(见同目录样本) | mens-olympics | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 奥运男篮 | 空=源站未标注 |
| `season` | 赛季标识 | 1948 | 空=源站未提供 |
| `game_date` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_team` | 主队名称 | South Korea | 空=源站未覆盖 |
| `away_team` | 客队名称 | Czechoslovakia | 空=源站未覆盖 |
| `home_pts` | 源站原始字段(见同目录样本) | 38 | 空=源站未提供 |
| `away_pts` | 源站原始字段(见同目录样本) | 39 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | basketball-reference | 空=源站未提供 |

### jingcai_divergence_log

- 全库行数: 1,163   样本: 100 行 -> `samples/jingcai_divergence_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2179 | 不应为空 |
| `okooo_match_id` | 源站原始字段(见同目录样本) | 1348380 | 空=源站未提供 |
| `league_zh` | 源站原始字段(见同目录样本) | 亚运女足 | 空=源站未提供 |
| `home_team_zh` | 源站原始字段(见同目录样本) | 中国女足 | 空=源站未提供 |
| `away_team_zh` | 源站原始字段(见同目录样本) | 菲律宾女足 | 空=源站未提供 |
| `kickoff_bj` | 源站原始字段(见同目录样本) | 2026-09-21 15:00:00 | 空=源站未提供 |
| `jc_odds_home` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `jc_odds_draw` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `jc_odds_away` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `unified_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `matched_league_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `matched_home_team` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `matched_away_team` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_odds_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_odds_draw` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_odds_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_source_count` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `match_status` | 比赛状态 | unmatched_no_league_map | 空=未知 |
| `divergence_pct` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `favorite_agree` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-20 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-20 07:40:07 | 空=历史回填无时间戳 |

### jingcai_history_bball_matches

- 全库行数: 22,261   样本: 100 行 -> `samples/jingcai_history_bball_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | 62321 | 空=源站未提供 |
| `match_num` | 源站原始字段(见同目录样本) | 周三301 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2015-01-01 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 美国职业篮球联盟 | 空=源站未标注 |
| `home_team` | 主队名称 | 凯尔特人 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 国王 | 空=源站未覆盖 |
| `final_score` | 源站原始字段(见同目录样本) | 84-106 | 空=源站未提供 |
| `jc_mnl_close_home` | 源站原始字段(见同目录样本) | 1.56 | 空=源站未提供 |
| `jc_mnl_close_away` | 源站原始字段(见同目录样本) | 1.97 | 空=源站未提供 |
| `jc_hdc_close_line` | 源站原始字段(见同目录样本) | +1.5 | 空=源站未提供 |
| `jc_hdc_close_home` | 源站原始字段(见同目录样本) | 1.88 | 空=源站未提供 |
| `jc_hdc_close_away` | 源站原始字段(见同目录样本) | 1.62 | 空=源站未提供 |
| `jc_hilo_close_line` | 源站原始字段(见同目录样本) | 209.5 | 空=源站未提供 |
| `jc_hilo_close_over` | 源站原始字段(见同目录样本) | 1.76 | 空=源站未提供 |
| `jc_hilo_close_under` | 源站原始字段(见同目录样本) | 1.72 | 空=源站未提供 |
| `jc_close_time` | 源站原始字段(见同目录样本) | 2014-12-31 23:32:59 | 空=源站未提供 |
| `source_file` | 源站原始字段(见同目录样本) | jingcai_basketball_final.jso… | 空=源站未提供 |
| `imported_at` | 源站原始字段(见同目录样本) | 2026-08-07 04:03:13 | 空=源站未提供 |

### jingcai_history_divergence

- 全库行数: 81,744   样本: 100 行 -> `samples/jingcai_history_divergence.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 84222 | 不应为空 |
| `match_id` | 比赛ID(源站) | 2040723 | 空=源站未提供 |
| `league_zh` | 源站原始字段(见同目录样本) | 欧洲冠军联赛 | 空=源站未提供 |
| `home_team_zh` | 源站原始字段(见同目录样本) | 费内巴切 | 空=源站未提供 |
| `away_team_zh` | 源站原始字段(见同目录样本) | 格风暴 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-08-06 | 空=源站未提供 |
| `jc_odds_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `jc_odds_draw` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `jc_odds_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `unified_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `matched_league_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `matched_home_team` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `matched_away_team` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_odds_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_odds_draw` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_odds_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `consensus_source_count` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `match_status` | 比赛状态 | unmatched_ambiguous | 空=未知 |
| `divergence_pct` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `favorite_agree` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `win_flag` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `full_score` | 源站原始字段(见同目录样本) | 2:0 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-07 04:08:59 | 空=历史回填无时间戳 |

### jingcai_history_matches

- 全库行数: 81,744   样本: 100 行 -> `samples/jingcai_history_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | 78371 | 空=源站未提供 |
| `match_num` | 源站原始字段(见同目录样本) | 周六058 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2016-03-20 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 法国甲级联赛 | 空=源站未标注 |
| `home_team` | 主队名称 | 圣埃蒂安 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 蒙彼利埃 | 空=源站未覆盖 |
| `handicap` | 亚洲让球盘口线 | -1 | 空=无亚盘 |
| `half_score` | 源站原始字段(见同目录样本) | 0:0 | 空=源站未提供 |
| `full_score` | 源站原始字段(见同目录样本) | 3:0 | 空=源站未提供 |
| `win_flag` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_file` | 源站原始字段(见同目录样本) | jingcai_football_final.json | 空=源站未提供 |
| `imported_at` | 源站原始字段(见同目录样本) | 2026-08-07 04:05:15 | 空=源站未提供 |
| `jc_had_close_home` | 源站原始字段(见同目录样本) | 1.97 | 空=源站未提供 |
| `jc_had_close_draw` | 源站原始字段(见同目录样本) | 3.0 | 空=源站未提供 |
| `jc_had_close_away` | 源站原始字段(见同目录样本) | 3.55 | 空=源站未提供 |
| `jc_had_close_time` | 源站原始字段(见同目录样本) | 2016-03-19 22:36:40 | 空=源站未提供 |
| `match_time` | 开赛时间 |  | UTC或源站时区，需按README时区说明换算 |
| `jc_ttg_close_json` | 源站原始字段(见同目录样本) | {"s0": "6.75", "s1": "3.60",… | 空=源站未提供 |
| `jc_hhad_close_home` | 源站原始字段(见同目录样本) | 4.35 | 空=源站未提供 |
| `jc_hhad_close_draw` | 源站原始字段(见同目录样本) | 3.5 | 空=源站未提供 |
| `jc_hhad_close_away` | 源站原始字段(见同目录样本) | 1.63 | 空=源站未提供 |
| `jc_hhad_close_line` | 源站原始字段(见同目录样本) | -1 | 空=源站未提供 |

### jingcai_history_odds

- 全库行数: 402,668   样本: 100 行 -> `samples/jingcai_history_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 414720 | 不应为空 |
| `match_id` | 比赛ID(源站) | 2040717 | 空=源站未提供 |
| `code` | 源站原始字段(见同目录样本) | HAD | 空=源站未提供 |
| `combination` | 源站原始字段(见同目录样本) | A | 空=源站未提供 |
| `combination_desc` | 源站原始字段(见同目录样本) | 负 | 空=源站未提供 |
| `goal_line` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds` | 源站原始字段(见同目录样本) | 4.0 | 空=源站未提供 |
| `pool_id` | 源站原始字段(见同目录样本) | 2193778 | 空=源站未提供 |
| `odds_type` | 源站原始字段(见同目录样本) | F | 空=源站未提供 |

### league_ah_edge_recs

- 全库行数: 24   样本: 24 行 -> `samples/league_ah_edge_recs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 44 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | d84e0c1a14a1 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Italy - Serie B | 空=源站未标注 |
| `home_team` | 主队名称 | Empoli | 空=源站未覆盖 |
| `away_team` | 客队名称 | Vicenza | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T18:30:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | spread | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 0.25 | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.7937 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.6055 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0271 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.4826 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T15:02:08 | 空=历史回填无时间戳 |

### league_master

- 全库行数: 5   样本: 5 行 -> `samples/league_master.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league_id_internal` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `source_league_code` | 源站原始字段(见同目录样本) | sporttery_德篮联 | 空=源站未提供 |
| `source_league_id` | 源站原始字段(见同目录样本) | -1 | 空=源站未提供 |
| `league_name_std` | 源站原始字段(见同目录样本) | sporttery_德篮联 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-05-27 06:31:54 | 空=历史回填无时间戳 |
| `league_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `league_name_cn` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### league_preview_articles

- 全库行数: 9   样本: 9 行 -> `samples/league_preview_articles.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `article_id` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `season` | 赛季标识 | 2026-27 | 空=源站未提供 |
| `league_name_cn` | 源站原始字段(见同目录样本) | 德乙 | 空=源站未提供 |
| `title` | 源站原始字段(见同目录样本) | 一匹狼与17只哈士奇的故事？26-27赛季德乙联赛前瞻及… | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | 江湖论门 | 空=源站未提供 |
| `file_path` | 源站原始字段(见同目录样本) | D:\jiangshanlenmen\01_一匹狼与17… | 空=源站未提供 |
| `full_text` | 源站原始字段(见同目录样本) | 一匹狼与17只哈士奇的故事？26-27赛季德乙联赛前瞻及… | 空=源站未提供 |
| `char_count` | 源站原始字段(见同目录样本) | 8290 | 空=源站未提供 |
| `ingested_at` | 源站原始字段(见同目录样本) | 2026-08-23 03:28:05 | 空=源站未提供 |

### legacy_team_total_under_recs

- 全库行数: 55   样本: 55 行 -> `samples/legacy_team_total_under_recs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 115 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 39eb368cc9d1 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Germany - Bundesliga 2 | 空=源站未标注 |
| `home_team` | 主队名称 | 达姆施塔特 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 圣保利 | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T16:30:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | team_total_away | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 1.5 | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.9009 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.571 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0237 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.7376 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T15:02:08 | 空=历史回填无时间戳 |

### lottery_sfc_matches

- 全库行数: 46,396   样本: 100 行 -> `samples/lottery_sfc_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 49350 | 不应为空 |
| `period` | 源站原始字段(见同目录样本) | 26128 | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `home_team` | 主队名称 | 弗拉门戈 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 德尔瓦耶独立 | 空=源站未覆盖 |
| `result` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `draw_date` | 源站原始字段(见同目录样本) | 2026-09-18 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-16 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-16 00:03:18 | 空=历史回填无时间戳 |
| `pin_sfc_odds_h` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `pin_sfc_odds_d` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `pin_sfc_odds_a` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `pinnacle_odds_h` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `pinnacle_odds_d` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `pinnacle_odds_a` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `win_sp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `draw_sp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `lost_sp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `pin_score` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |

### lottery_sfc_prizes

- 全库行数: 9,933   样本: 100 行 -> `samples/lottery_sfc_prizes.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 10530 | 不应为空 |
| `period` | 源站原始字段(见同目录样本) | 26106 | 空=源站未提供 |
| `tier` | 源站原始字段(见同目录样本) | 任九 | 空=源站未提供 |
| `winning_count` | 源站原始字段(见同目录样本) | 2028 | 空=源站未提供 |
| `prize_amount` | 源站原始字段(见同目录样本) | 4347.0 | 空=源站未提供 |
| `sfc_sales` | 源站原始字段(见同目录样本) | 14070402.0 | 空=源站未提供 |
| `ren9_sales` | 源站原始字段(见同目录样本) | 13777502.0 | 空=源站未提供 |
| `jackpot_rollover` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-16 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-16 00:03:12 | 空=历史回填无时间戳 |

### ls_bball_games

- 全库行数: 3,223   样本: 100 行 -> `samples/ls_bball_games.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 52579 | 不应为空 |
| `event_id` | 源站原始字段(见同目录样本) | 1787711 | 空=源站未提供 |
| `league_country` | 源站原始字段(见同目录样本) | Mexico | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | LNBP | 空=源站未标注 |
| `stage_name` | 源站原始字段(见同目录样本) | lnbp | 空=源站未提供 |
| `home_team` | 主队名称 | Astros de Jalisco | 空=源站未覆盖 |
| `away_team` | 客队名称 | Soles de Mexicali | 空=源站未覆盖 |
| `home_team_id` | 源站原始字段(见同目录样本) | 87493 | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | 87430 | 空=源站未提供 |
| `kickoff_dt` | 源站原始字段(见同目录样本) | 2026-09-13T05:15:00 | 空=源站未提供 |
| `status` | 比赛状态 | FT | 空=未知 |
| `home_score` | 主队进球(全场) | 81 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 74 | 空=未开赛或源站未覆盖，不是0 |
| `home_q1` | 源站原始字段(见同目录样本) | 21 | 空=源站未提供 |
| `away_q1` | 源站原始字段(见同目录样本) | 18 | 空=源站未提供 |
| `home_q2` | 源站原始字段(见同目录样本) | 15 | 空=源站未提供 |
| `away_q2` | 源站原始字段(见同目录样本) | 25 | 空=源站未提供 |
| `home_q3` | 源站原始字段(见同目录样本) | 22 | 空=源站未提供 |
| `away_q3` | 源站原始字段(见同目录样本) | 19 | 空=源站未提供 |
| `home_q4` | 源站原始字段(见同目录样本) | 23 | 空=源站未提供 |
| `away_q4` | 源站原始字段(见同目录样本) | 12 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### ls_bball_leagues

- 全库行数: 209   样本: 100 行 -> `samples/ls_bball_leagues.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 27130 | 不应为空 |
| `league_country` | 源站原始字段(见同目录样本) | Mexico | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | LNBP | 空=源站未标注 |
| `stage_name` | 源站原始字段(见同目录样本) | lnbp | 空=源站未提供 |
| `first_seen` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `last_seen` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### market_prediction_snapshot

- 全库行数: 795,559   样本: 100 行 -> `samples/market_prediction_snapshot.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2050951 | 不应为空 |
| `match_id_internal` | 源站原始字段(见同目录样本) | a943acb3ae37 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `kickoff_local` | 源站原始字段(见同目录样本) | 2026-10-23T06:31:00 | 空=源站未提供 |
| `home_team_name_std` | 源站原始字段(见同目录样本) | 曼联 | 空=源站未提供 |
| `away_team_name_std` | 源站原始字段(见同目录样本) | 切尔西 | 空=源站未提供 |
| `market_group` | 源站原始字段(见同目录样本) | HTFT | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | ht_ft | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | fulltime | 空=源站未提供 |
| `selection_name` | 源站原始字段(见同目录样本) | home-away | 空=源站未提供 |
| `line_value` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.017642 | 空=源站未提供 |
| `fair_odds` | 源站原始字段(见同目录样本) | 56.6824 | 空=源站未提供 |
| `offered_odds` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `expected_value` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `kelly_ratio` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `confidence_grade` | 源站原始字段(见同目录样本) | 低 | 空=源站未提供 |
| `result_source` | 源站原始字段(见同目录样本) | poisson_htft_joint | 空=源站未提供 |
| `run_tag` | 源站原始字段(见同目录样本) | poisson_elo_v1 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T14:47:31 | 空=历史回填无时间戳 |

### match_h2h

- 全库行数: 15,414   样本: 100 行 -> `samples/match_h2h.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 23121 | 不应为空 |
| `home_team` | 主队名称 | Beerschot VA | 空=源站未覆盖 |
| `away_team` | 客队名称 | Eupen | 空=源站未覆盖 |
| `sport` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `meetings` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `home_wins` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `draws` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `away_wins` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `home_goals` | 主队进球(全场) | 0.0 | 空=未开赛或源站未覆盖，不是0 |
| `away_goals` | 客队进球(全场) | 4.0 | 空=未开赛或源站未覆盖，不是0 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-24 | 空=源站未提供 |

### match_master

- 全库行数: 91   样本: 91 行 -> `samples/match_master.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id_internal` | 源站原始字段(见同目录样本) | 87 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_id_internal` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `source_league_code` | 源站原始字段(见同目录样本) | sporttery_premier_league | 空=源站未提供 |
| `season` | 赛季标识 |  | 空=源站未提供 |
| `kickoff_time_utc` | 源站原始字段(见同目录样本) | 2026-06-08 02:45:00 | 空=源站未提供 |
| `home_team_id` | 源站原始字段(见同目录样本) | 91 | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | 105 | 空=源站未提供 |
| `home_team_name_std` | 源站原始字段(见同目录样本) | 克罗地亚 | 空=源站未提供 |
| `away_team_name_std` | 源站原始字段(见同目录样本) | 斯洛文尼亚 | 空=源站未提供 |
| `match_status` | 比赛状态 | NS | 空=未知 |
| `source_name` | 源站原始字段(见同目录样本) | fixtures_upcoming | 空=源站未提供 |
| `source_match_key` | 源站原始字段(见同目录样本) | football/sporttery_premier_l… | 空=源站未提供 |
| `is_neutral` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-07 10:40:46 | 空=历史回填无时间戳 |

### match_predictions

- 全库行数: 74   样本: 74 行 -> `samples/match_predictions.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 74 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 2bd3869b473b | 空=源站未提供 |
| `sport` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Australia - NPL Northern NSW | 空=源站未标注 |
| `home_team` | 主队名称 | Lambton Jaffas | 空=源站未覆盖 |
| `away_team` | 客队名称 | Adamstown Rosebud | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-06-20T04:00:00Z | 空=源站未提供 |
| `model` | 源站原始字段(见同目录样本) | fusion_v1 | 空=源站未提供 |
| `pred_home_prob` | 源站原始字段(见同目录样本) | 0.403 | 空=源站未提供 |
| `pred_draw_prob` | 源站原始字段(见同目录样本) | 0.2803 | 空=源站未提供 |
| `pred_away_prob` | 源站原始字段(见同目录样本) | 0.3166 | 空=源站未提供 |
| `pred_home_score` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `pred_away_score` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `confidence` | 源站原始字段(见同目录样本) | 0.5 | 空=源站未提供 |
| `raw_json` | 源站原始字段(见同目录样本) | {'under_1.5': 0.344, 'over_2… | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-19 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-19 15:05:03 | 空=历史回填无时间戳 |

### match_results

- 全库行数: 22,086   样本: 100 行 -> `samples/match_results.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1357765 | 不应为空 |
| `flashscore_id` | 源站原始字段(见同目录样本) | vVrYQrEk | 空=源站未提供 |
| `sport` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `country` | 源站原始字段(见同目录样本) | mexico | 空=源站未提供 |
| `league_slug` | 源站原始字段(见同目录样本) | lnbp | 空=源站未提供 |
| `league_cn` | 源站原始字段(见同目录样本) | 墨西哥职业篮 | 空=源站未提供 |
| `home_team` | 主队名称 | Abejas | 空=源站未覆盖 |
| `away_team` | 客队名称 | Gambusinos | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 83 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 87 | 空=未开赛或源站未覆盖，不是0 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-09-11 01:00:00+00:00 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-09-11 | 空=源站未提供 |
| `round_info` | 源站原始字段(见同目录样本) | Round 17 | 空=源站未提供 |
| `raw_data` | 源站原始字段(见同目录样本) | {"flashscore_id": "vVrYQrEk"… | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-27 14:43:23 | 空=历史回填无时间戳 |

### match_source_map

- 全库行数: 91   样本: 91 行 -> `samples/match_source_map.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 91 | 不应为空 |
| `match_id_internal` | 源站原始字段(见同目录样本) | 91 | 空=源站未提供 |
| `source_name` | 源站原始字段(见同目录样本) | fixtures_upcoming | 空=源站未提供 |
| `source_match_id` | 源站原始字段(见同目录样本) | basketball/sporttery_美职女篮/20… | 空=源站未提供 |
| `source_league_name` | 源站原始字段(见同目录样本) | sporttery_美职女篮 | 空=源站未提供 |
| `source_home_name` | 源站原始字段(见同目录样本) | 多伦多节奏 | 空=源站未提供 |
| `source_away_name` | 源站原始字段(见同目录样本) | 芝加哥天空 | 空=源站未提供 |
| `kickoff_time_source` | 源站原始字段(见同目录样本) | 2026-06-08 03:00:00 | 空=源站未提供 |
| `match_confidence_score` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `is_manual_locked` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-07 10:40:46 | 空=历史回填无时间戳 |

### moneyline_shadow_full

- 全库行数: 453   样本: 100 行 -> `samples/moneyline_shadow_full.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1044 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 93ec1bd22582 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Poland - 2nd Liga | 空=源站未标注 |
| `home_team` | 主队名称 | 索克尔克勒泽威 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 弗罗茨瓦夫B队 | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T12:30:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | moneyline | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `best_odds` | 源站原始字段(见同目录样本) | 2.38 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.5336 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0472 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.7158 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T07:01:50 | 空=历史回填无时间戳 |

### multi_bookie_odds

- 全库行数: 50,794   样本: 100 行 -> `samples/multi_bookie_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 121962 | 不应为空 |
| `source` | 源站原始字段(见同目录样本) | bovada | 空=源站未提供 |
| `event_id` | 源站原始字段(见同目录样本) | 29471768 | 空=源站未提供 |
| `sport` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `competition` | 源站原始字段(见同目录样本) | Denver Nuggets @ Golden Stat… | 空=源站未提供 |
| `home_team` | 主队名称 | Golden State Warriors | 空=源站未覆盖 |
| `away_team` | 客队名称 | Denver Nuggets | 空=源站未覆盖 |
| `match_time` | 开赛时间 | 1798255800000 | UTC或源站时区，需按README时区说明换算 |
| `market` | 源站原始字段(见同目录样本) | Game Lines | 空=源站未提供 |
| `selection` | 源站原始字段(见同目录样本) | Golden State Warriors | 空=源站未提供 |
| `odds` | 源站原始字段(见同目录样本) | 2.15 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 |  | 空=无亚盘 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### multi_xg_team_stats

- 全库行数: 59   样本: 59 行 -> `samples/multi_xg_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 59 | 不应为空 |
| `team_name` | 源站原始字段(见同目录样本) | Atlético Madrid | 空=源站未提供 |
| `league` | 联赛/赛事名称 | Champions League | 空=源站未标注 |
| `source` | 源站原始字段(见同目录样本) | statsbomb | 空=源站未提供 |
| `xg` | 预期进球xG | 1.0 | 空=源站无xG |
| `xga` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `matches` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-06 | 空=源站未提供 |

### multisource_odds

- 全库行数: 87,791   样本: 100 行 -> `samples/multisource_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 173220 | 不应为空 |
| `league` | 联赛/赛事名称 | 塞浦路斯甲级联赛 | 空=源站未标注 |
| `home_team` | 主队名称 | 卡米奥提萨 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 尼科西亚奥林匹亚科斯 | 空=源站未覆盖 |
| `odds_home` | 主胜赔率 | 1.77 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 |  | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 2.03 | 空=该场无此盘口 |
| `prob_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `prob_draw` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `prob_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `margin` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | qiety_yb | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-10-31 | 空=源站未提供 |
| `scraped_at` | 源站原始字段(见同目录样本) | 2026-10-30 13:18:52 | 空=源站未提供 |
| `jc_odds_home` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `jc_odds_draw` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `jc_odds_away` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `divergence` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `has_jingcai` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `odds_type` | 源站原始字段(见同目录样本) | over_under | 空=源站未提供 |
| `over_odds` | 大/小球赔率 | 1.77 | 空=无对应盘口 |
| `under_odds` | 大/小球赔率 | 2.03 | 空=无对应盘口 |
| `handicap_line` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `total_line` | 大小球盘口线 | 2.5 | 空=无大小球 |
| `sport` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 5735687 | 空=源站未提供 |

### national_team_elo

- 全库行数: 13,420   样本: 100 行 -> `samples/national_team_elo.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 14152 | 不应为空 |
| `team_name` | 源站原始字段(见同目录样本) | Eastern Samoa | 空=源站未提供 |
| `elo_rating` | 源站原始字段(见同目录样本) | 370.0 | 空=源站未提供 |
| `rank` | 源站原始字段(见同目录样本) | 244 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-20 | 空=源站未提供 |

### nba_matches

- 全库行数: 52,481   样本: 100 行 -> `samples/nba_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 52481 | 不应为空 |
| `game_id` | 源站原始字段(见同目录样本) | 0049700004 | 空=源站未提供 |
| `season` | 赛季标识 | 1997 | 空=源站未提供 |
| `season_type` | 源站原始字段(见同目录样本) | PO | 空=源站未提供 |
| `game_date` | 源站原始字段(见同目录样本) | 1998-04-23 | 空=源站未提供 |
| `home_team` | 主队名称 | Phoenix Suns | 空=源站未覆盖 |
| `home_abbr` | 源站原始字段(见同目录样本) | PHX | 空=源站未提供 |
| `away_team` | 客队名称 | San Antonio Spurs | 空=源站未覆盖 |
| `away_abbr` | 源站原始字段(见同目录样本) | SAS | 空=源站未提供 |
| `home_pts` | 源站原始字段(见同目录样本) | 96 | 空=源站未提供 |
| `away_pts` | 源站原始字段(见同目录样本) | 102 | 空=源站未提供 |
| `home_q1` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_q2` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_q3` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_q4` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q1` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q2` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q3` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_q4` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_fg_pct` | 源站原始字段(见同目录样本) | 0.471 | 空=源站未提供 |
| `home_3p_pct` | 源站原始字段(见同目录样本) | 0.273 | 空=源站未提供 |
| `home_ft_pct` | 源站原始字段(见同目录样本) | 0.611 | 空=源站未提供 |
| `away_fg_pct` | 源站原始字段(见同目录样本) | 0.529 | 空=源站未提供 |
| `away_3p_pct` | 源站原始字段(见同目录样本) | 0.25 | 空=源站未提供 |
| `away_ft_pct` | 源站原始字段(见同目录样本) | 0.628 | 空=源站未提供 |
| `home_reb` | 源站原始字段(见同目录样本) | 37 | 空=源站未提供 |
| `home_ast` | 源站原始字段(见同目录样本) | 24 | 空=源站未提供 |
| `home_stl` | 源站原始字段(见同目录样本) | 9 | 空=源站未提供 |
| `home_blk` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `home_tov` | 源站原始字段(见同目录样本) | 11 | 空=源站未提供 |
| `away_reb` | 源站原始字段(见同目录样本) | 37 | 空=源站未提供 |
| `away_ast` | 源站原始字段(见同目录样本) | 17 | 空=源站未提供 |
| `away_stl` | 源站原始字段(见同目录样本) | 9 | 空=源站未提供 |
| `away_blk` | 源站原始字段(见同目录样本) | 7 | 空=源站未提供 |
| `away_tov` | 源站原始字段(见同目录样本) | 13 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | nba_api | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-12 11:31:13 | 空=历史回填无时间戳 |

### odds_snapshot

- 全库行数: 1,780   样本: 100 行 -> `samples/odds_snapshot.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id_internal` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | wnba | 空=源站未提供 |
| `source_name` | 源站原始字段(见同目录样本) | 默认估值 | 空=源站未提供 |
| `bookmaker_name` | 源站原始字段(见同目录样本) | 默认估值 | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | h2h | 空=源站未提供 |
| `line_value` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds_home` | 主胜赔率 | 1.85 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 |  | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 1.85 | 空=该场无此盘口 |
| `over_odds` | 大/小球赔率 |  | 空=无对应盘口 |
| `under_odds` | 大/小球赔率 |  | 空=无对应盘口 |
| `source_timestamp_utc` | 源站原始字段(见同目录样本) | 2026-05-25 11:31:26.000000 | 空=源站未提供 |
| `collected_at_utc` | 源站原始字段(见同目录样本) | 2026-05-25 11:31:26.000000 | 空=源站未提供 |
| `is_live` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `raw_payload_json` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `raw_payload_hash` | 源站原始字段(见同目录样本) | 64d24406906d967a010f38c5e346… | 空=源站未提供 |

### odds_snapshots

- 全库行数: 1,760,299   样本: 100 行 -> `samples/odds_snapshots.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1760299 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | a943acb3ae37 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | consensus | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `odds_value` | 源站原始字段(见同目录样本) | 1.82 | 空=源站未提供 |
| `snapshot_time` | 抓取/写入时间 | 2026-10-23T07:02:09 | 空=历史回填无时间戳 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |

### oddsportal_matches

- 全库行数: 5,251   样本: 100 行 -> `samples/oddsportal_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 10250 | 不应为空 |
| `op_match_id` | 源站原始字段(见同目录样本) | CtnQOrYA | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 |  | 空=源站未标注 |
| `season` | 赛季标识 | current | 空=源站未提供 |
| `home_team` | 主队名称 | Seattle Storm W | 空=源站未覆盖 |
| `away_team` | 客队名称 | Chicago Sky W | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `status` | 比赛状态 | NS | 空=未知 |
| `home_score` | 主队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-10 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-10 07:26:57 | 空=历史回填无时间戳 |

### oddsportal_odds

- 全库行数: 7,860   样本: 100 行 -> `samples/oddsportal_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 14053 | 不应为空 |
| `op_match_id` | 源站原始字段(见同目录样本) | CtnQOrYA | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | 1X2 | 空=源站未提供 |
| `bookmaker` | 赔率来源公司/源站 | best | 空=未标注 |
| `outcome` | 源站原始字段(见同目录样本) | draw | 空=源站未提供 |
| `odds_value` | 源站原始字段(见同目录样本) | 2.0 | 空=源站未提供 |
| `is_closing` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-10 | 空=源站未提供 |

### ofb_matches

- 全库行数: 90,787   样本: 100 行 -> `samples/ofb_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 177038 | 不应为空 |
| `league_code` | 源站原始字段(见同目录样本) | nl.1 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Netherlands Eredivisie 2024/… | 空=源站未标注 |
| `season` | 赛季标识 | 2024/25 | 空=源站未提供 |
| `match_round` | 源站原始字段(见同目录样本) | Matchday 34 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2025-05-18 | 空=源站未提供 |
| `match_time` | 开赛时间 | 14:30 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | Sparta Rotterdam | 空=源站未覆盖 |
| `away_team` | 客队名称 | PSV | 空=源站未覆盖 |
| `ft_home` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `ft_away` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `ht_home` | 主队半场进球 | 0 | 空=无半场数据 |
| `ht_away` | 客队半场进球 | 1 | 空=无半场数据 |
| `source` | 源站原始字段(见同目录样本) | openfootball | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-12 11:06:35 | 空=历史回填无时间戳 |

### okooo_basketball_odds

- 全库行数: 212   样本: 100 行 -> `samples/okooo_basketball_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 228 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5386631 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 欧联 | 空=源站未标注 |
| `kickoff_time` | 源站原始字段(见同目录样本) | 22:00 | 空=源站未提供 |
| `home_team` | 主队名称 | 皇马 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 游击 | 空=源站未覆盖 |
| `spread_line` | 源站原始字段(见同目录样本) | -7.5 | 空=源站未提供 |
| `odds_spread_home` | 源站原始字段(见同目录样本) | 1.7 | 空=源站未提供 |
| `odds_spread_away` | 源站原始字段(见同目录样本) | 1.7 | 空=源站未提供 |
| `total_line` | 大小球盘口线 | 177.5 | 空=无大小球 |
| `odds_over` | 源站原始字段(见同目录样本) | 1.7 | 空=源站未提供 |
| `odds_under` | 源站原始字段(见同目录样本) | 1.7 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-08 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-08 09:14:23 | 空=历史回填无时间戳 |

### okooo_bet_flow

- 全库行数: 2,547   样本: 100 行 -> `samples/okooo_bet_flow.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2547 | 不应为空 |
| `match_id` | 比赛ID(源站) | 1337960 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 葡超 | 空=源站未标注 |
| `match_time` | 开赛时间 | 10-13 03:15 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | 法马利康 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 艾华卡 | 空=源站未覆盖 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `turnover` | 源站原始字段(见同目录样本) | 3545.0 | 空=源站未提供 |
| `hot_cold_index` | 源站原始字段(见同目录样本) | -8.0 | 空=源站未提供 |
| `market_index` | 源站原始字段(见同目录样本) | 34.0 | 空=源站未提供 |
| `betfair_odds` | 源站原始字段(见同目录样本) | 4.8 | 空=源站未提供 |
| `betfair_pct` | 源站原始字段(见同目录样本) | 19.92 | 空=源站未提供 |
| `avg99_odds` | 源站原始字段(见同目录样本) | 4.29 | 空=源站未提供 |
| `avg99_pct` | 源站原始字段(见同目录样本) | 21.73 | 空=源站未提供 |
| `jingcai_pct` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `sim_pnl` | 源站原始字段(见同目录样本) | 781.0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `fetch_at` | 源站原始字段(见同目录样本) | 2026-10-12T11:46:33 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-12 03:46:33 | 空=历史回填无时间戳 |

### okooo_football_odds

- 全库行数: 1,433   样本: 100 行 -> `samples/okooo_football_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1506 | 不应为空 |
| `match_id` | 比赛ID(源站) | 1337960 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 葡超 | 空=源站未标注 |
| `kickoff` | 开赛时间 | 2026-10-13 03:15:00 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | 法马利康 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 艾华卡 | 空=源站未覆盖 |
| `odds_1x2_home` | 源站原始字段(见同目录样本) | 1.7 | 空=源站未提供 |
| `odds_1x2_draw` | 源站原始字段(见同目录样本) | 3.32 | 空=源站未提供 |
| `odds_1x2_away` | 源站原始字段(见同目录样本) | 4.2 | 空=源站未提供 |
| `ah_line` | 亚洲让球盘口线 | -1.0 | 空=无亚盘 |
| `odds_ah_home` | 源站原始字段(见同目录样本) | 3.4 | 空=源站未提供 |
| `odds_ah_draw` | 源站原始字段(见同目录样本) | 3.3 | 空=源站未提供 |
| `odds_ah_away` | 源站原始字段(见同目录样本) | 1.88 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-12 03:46:35 | 空=历史回填无时间戳 |

### okooo_injuries

- 全库行数: 1,306   样本: 100 行 -> `samples/okooo_injuries.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1393 | 不应为空 |
| `match_id` | 比赛ID(源站) | 1335544 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `team` | 源站原始字段(见同目录样本) | 塞维利亚 | 空=源站未提供 |
| `number` | 源站原始字段(见同目录样本) | 23 | 空=源站未提供 |
| `position` | 源站原始字段(见同目录样本) | 后卫 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | 特谢拉 | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) | 310562 | 空=源站未提供 |
| `appearances` | 源站原始字段(见同目录样本) | 0(0) | 空=源站未提供 |
| `minutes` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `goals` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `assists` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `will_miss` | 源站原始字段(见同目录样本) | 是 | 空=源站未提供 |
| `reason` | 源站原始字段(见同目录样本) | 受伤 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-12 03:46:31 | 空=历史回填无时间戳 |

### okooo_ren9_matches

- 全库行数: 1,412   样本: 100 行 -> `samples/okooo_ren9_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1986 | 不应为空 |
| `lottery_no` | 源站原始字段(见同目录样本) | 26153 | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 1317708 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 挪超 | 空=源站未标注 |
| `match_date` | 源站原始字段(见同目录样本) | 10-31 | 空=源站未提供 |
| `match_time` | 开赛时间 | 02:00 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | 博德 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 维京 | 空=源站未覆盖 |
| `home_rank` | 源站原始字段(见同目录样本) | [2] | 空=源站未提供 |
| `away_rank` | 源站原始字段(见同目录样本) | [1] | 空=源站未提供 |
| `odds_home` | 主胜赔率 | 1.65 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 | 4.28 | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 4.09 | 空=该场无此盘口 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-29 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-29 11:00:04 | 空=历史回填无时间戳 |

### okooo_ren9_snapshots

- 全库行数: 868   样本: 100 行 -> `samples/okooo_ren9_snapshots.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 868 | 不应为空 |
| `lottery_no` | 源站原始字段(见同目录样本) | 26153 | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `home_team` | 主队名称 | 博德 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 维京 | 空=源站未覆盖 |
| `odds_home` | 主胜赔率 | 1.65 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 | 4.28 | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 4.09 | 空=该场无此盘口 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-29 | 空=源站未提供 |
| `batch_ts` | 源站原始字段(见同目录样本) | 2026-10-29 19:00:04 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-29 11:00:04 | 空=历史回填无时间戳 |

### over_shadow_bets

- 全库行数: 333   样本: 100 行 -> `samples/over_shadow_bets.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 610 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 386a4861e564 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Peru - Liga 1 | 空=源站未标注 |
| `home_team` | 主队名称 | Atletico Grau | 空=源站未覆盖 |
| `away_team` | 客队名称 | Asociacion Deportiva Tarma | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T20:15:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 2.5 | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.8772 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.5562 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0126 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.6884 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T07:01:50 | 空=历史回填无时间戳 |

### pin_arm_runs

- 全库行数: 18   样本: 18 行 -> `samples/pin_arm_runs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `period` | 源站原始字段(见同目录样本) | TEST02 | 空=源站未提供 |
| `run_ts` | 源站原始字段(见同目录样本) | 2026-09-16 23:06:23 | 空=源站未提供 |
| `status` | 比赛状态 | generated | 空=未知 |
| `coverage_n` | 源站原始字段(见同目录样本) | 13 | 空=源站未提供 |
| `coverage_total` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `skip_reason` | 源站原始字段(见同目录样本) | alias_unmapped=1;no_fixture=… | 空=源站未提供 |
| `detail` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### pinnacle_corner_odds

- 全库行数: 150,806   样本: 100 行 -> `samples/pinnacle_corner_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 153452 | 不应为空 |
| `corner_matchup_id` | 源站原始字段(见同目录样本) | 1638557868 | 空=源站未提供 |
| `parent_matchup_id` | 源站原始字段(见同目录样本) | 1638073271 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | France - Ligue 1 | 空=源站未标注 |
| `home_team` | 主队名称 | Brest | 空=源站未覆盖 |
| `away_team` | 客队名称 | Nice | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23 18:45:00 | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `team_side` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `line` | 源站原始字段(见同目录样本) | 5.0 | 空=源站未提供 |
| `price_amer` | 源站原始字段(见同目录样本) | -180.0 | 空=源站未提供 |
| `price_dec` | 源站原始字段(见同目录样本) | 1.5556 | 空=源站未提供 |
| `is_alternate` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `max_bet` | 源站原始字段(见同目录样本) | 100.0 | 空=源站未提供 |
| `status` | 比赛状态 | open | 空=未知 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |
| `recorded_at` | 源站原始字段(见同目录样本) | 2026-10-20T12:53:15 | 空=源站未提供 |

### pinnacle_corner_odds_tiers

- 全库行数: 237,062   样本: 100 行 -> `samples/pinnacle_corner_odds_tiers.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 250090 | 不应为空 |
| `corner_matchup_id` | 源站原始字段(见同目录样本) | 1637699331 | 空=源站未提供 |
| `parent_matchup_id` | 源站原始字段(见同目录样本) | 1637699331 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | UEFA - U21 Euro Championship… | 空=源站未标注 |
| `home_team` | 主队名称 | Sweden (Corners) | 空=源站未覆盖 |
| `away_team` | 客队名称 | North Macedonia (Corners) | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-05 16:30:00 | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `team_side` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `line` | 源站原始字段(见同目录样本) | 10.5 | 空=源站未提供 |
| `price_amer` | 源站原始字段(见同目录样本) | -169.0 | 空=源站未提供 |
| `price_dec` | 源站原始字段(见同目录样本) | 1.5917 | 空=源站未提供 |
| `is_alternate` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `max_bet` | 源站原始字段(见同目录样本) | 100.0 | 空=源站未提供 |
| `status` | 比赛状态 | open | 空=未知 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-05 | 空=源站未提供 |
| `recorded_at` | 源站原始字段(见同目录样本) | 2026-10-05T21:59:19 | 空=源站未提供 |
| `snapshot_tier` | 源站原始字段(见同目录样本) | m24h | 空=源站未提供 |

### pinnacle_correct_score_odds

- 全库行数: 62,434   样本: 100 行 -> `samples/pinnacle_correct_score_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 66140 | 不应为空 |
| `matchup_id` | 源站原始字段(见同目录样本) | 1638008128 | 空=源站未提供 |
| `parent_matchup_id` | 源站原始字段(见同目录样本) | 1638008128 | 空=源站未提供 |
| `correct_score` | 源站原始字段(见同目录样本) | 4-2 | 空=源站未提供 |
| `decimal_odds` | 源站原始字段(见同目录样本) | 39.11 | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 10227 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-12 03:45:35 | 空=历史回填无时间戳 |

### pinnacle_fixtures

- 全库行数: 8,167   样本: 100 行 -> `samples/pinnacle_fixtures.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 17724 | 不应为空 |
| `matchup_id` | 源站原始字段(见同目录样本) | 1638755556 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 224222 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | UAE - Dubai IBC | 空=源站未标注 |
| `home_team` | 主队名称 | Al Riyadi | 空=源站未覆盖 |
| `away_team` | 客队名称 | Al Ahli (UAE) | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-20 17:30:00 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `home_score` | 主队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-20 04:28:56 | 空=历史回填无时间戳 |

### pinnacle_leagues

- 全库行数: 503   样本: 100 行 -> `samples/pinnacle_leagues.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1883 | 不应为空 |
| `league_id` | 源站原始字段(见同目录样本) | 224222 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | UAE - Dubai IBC | 空=源站未标注 |
| `is_featured` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `match_count` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |

### pinnacle_odds

- 全库行数: 62,460   样本: 100 行 -> `samples/pinnacle_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 329346 | 不应为空 |
| `matchup_id` | 源站原始字段(见同目录样本) | 1638784507 | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `price` | 源站原始字段(见同目录样本) | -121.0 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 170.5 | 空=无亚盘 |
| `max_bet` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |
| `recorded_at` | 源站原始字段(见同目录样本) | 2026-10-20T12:28:57 | 空=源站未提供 |

### pinnacle_odds_history

- 全库行数: 323,715   样本: 100 行 -> `samples/pinnacle_odds_history.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 323715 | 不应为空 |
| `matchup_id` | 源站原始字段(见同目录样本) | 1638784507 | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `price` | 源站原始字段(见同目录样本) | -121.0 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 170.5 | 空=无亚盘 |
| `recorded_at` | 源站原始字段(见同目录样本) | 2026-10-20T12:28:57 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |

### pipeline_run_log

- 全库行数: 397   样本: 100 行 -> `samples/pipeline_run_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `run_name` | 源站原始字段(见同目录样本) | run_today_prediction | 空=源站未提供 |
| `run_status` | 源站原始字段(见同目录样本) | done | 空=源站未提供 |
| `start_time` | 开赛时间 | 2026-05-24 16:31:07.000000 | UTC或源站时区，需按README时区说明换算 |
| `end_time` | 源站原始字段(见同目录样本) | 2026-05-24 16:31:07.000000 | 空=源站未提供 |
| `records_in` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `records_out` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `note` | 源站原始字段(见同目录样本) | prediction_snapshot=1; odds_… | 空=源站未提供 |

### player_availability

- 全库行数: 2,475   样本: 100 行 -> `samples/player_availability.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 12786 | 不应为空 |
| `availability_key` | 源站原始字段(见同目录样本) | d00d4c46d1d210400847385bada2… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `source_team_id` | 源站原始字段(见同目录样本) | 8524 | 空=源站未提供 |
| `source_player_id` | 源站原始字段(见同目录样本) | 721089 | 空=源站未提供 |
| `source_event_id` | 源站原始字段(见同目录样本) | 5749722 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | Gianluca Scamacca | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `injury_type` | 伤病类型/描述 | injury | 空=无伤病记录，不代表健康 |
| `injury_description` | 伤病类型/描述 |  | 空=无伤病记录，不代表健康 |
| `suspension_type` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `availability_status` | 源站原始字段(见同目录样本) | unavailable | 空=源站未提供 |
| `sidelined_start_at` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `expected_return_at` | 源站原始字段(见同目录样本) | Mid November 2026 | 空=源站未提供 |
| `actual_return_at` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_updated_at` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-29T19:37:13Z | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-29T16:07:20Z | 空=源站未提供 |
| `first_seen_status` | 源站原始字段(见同目录样本) | PROVEN | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `receipt_id` | 源站原始字段(见同目录样本) | 72b25bf916afa0b7baf50ccbbc98… | 空=源站未提供 |
| `provided` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `source_json` | 源站原始字段(见同目录样本) | {"id": 721089, "age": 27, "n… | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | {"injury_description": "FotM… | 空=源站未提供 |
| `side` | 源站原始字段(见同目录样本) | awayTeam | 空=源站未提供 |
| `age` | 源站原始字段(见同目录样本) | 27 | 空=源站未提供 |
| `position_id` | 源站原始字段(见同目录样本) | 1000 | 空=源站未提供 |
| `country_code` | 源站原始字段(见同目录样本) | ITA | 空=源站未提供 |
| `country_name` | 源站原始字段(见同目录样本) | Italy | 空=源站未提供 |
| `market_value` | 源站原始字段(见同目录样本) | 20868092 | 空=源站未提供 |
| `injury_id` | 源站原始字段(见同目录样本) | 69 | 空=源站未提供 |
| `expected_return_text` | 源站原始字段(见同目录样本) | Mid November 2026 | 空=源站未提供 |
| `expected_return_date` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `null_reasons` | 源站原始字段(见同目录样本) | {"injury_description": "FotM… | 空=源站未提供 |

### prediction_snapshot

- 全库行数: 1,824   样本: 100 行 -> `samples/prediction_snapshot.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id_internal` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | wnba | 空=源站未提供 |
| `source_name` | 源站原始字段(见同目录样本) | run_today_prediction | 空=源站未提供 |
| `home_team_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_team_name_std` | 源站原始字段(见同目录样本) | New York Liberty W | 空=源站未提供 |
| `away_team_name_std` | 源站原始字段(见同目录样本) | Portland Fire W | 空=源站未提供 |
| `best_pick` | 源站原始字段(见同目录样本) | 主胜 | 空=源站未提供 |
| `best_prob` | 源站原始字段(见同目录样本) | 0.5625 | 空=源站未提供 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.85 | 空=源站未提供 |
| `best_kelly` | 源站原始字段(见同目录样本) | 0.0478 | 空=源站未提供 |
| `home_win_prob` | 源站原始字段(见同目录样本) | 0.5625 | 空=源站未提供 |
| `draw_prob` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_win_prob` | 源站原始字段(见同目录样本) | 0.4375 | 空=源站未提供 |
| `home_exp_score` | 源站原始字段(见同目录样本) | 26.0 | 空=源站未提供 |
| `away_exp_score` | 源站原始字段(见同目录样本) | 23.53 | 空=源站未提供 |
| `total_exp` | 源站原始字段(见同目录样本) | 49.53 | 空=源站未提供 |
| `confidence_grade` | 源站原始字段(见同目录样本) | B级 (弱正 edge) | 空=源站未提供 |
| `odds_source` | 源站原始字段(见同目录样本) | 默认估值 | 空=源站未提供 |
| `run_tag` | 源站原始字段(见同目录样本) | today_prediction | 空=源站未提供 |
| `actual_result` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `is_hit` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `actual_home_score` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `actual_away_score` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `result_verified_at` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-05-26 | 空=源站未提供 |

### qiety_h2h_history

- 全库行数: 168,590   样本: 100 行 -> `samples/qiety_h2h_history.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 171373 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5763532 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `relation` | 源站原始字段(见同目录样本) | away_recent | 空=源站未提供 |
| `home_team_id` | 源站原始字段(见同目录样本) | 533150 | 空=源站未提供 |
| `home_team_name` | 源站原始字段(见同目录样本) | 钢铁战舰 | 空=源站未提供 |
| `home_team_score` | 源站原始字段(见同目录样本) | 93 | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | 533152 | 空=源站未提供 |
| `away_team_name` | 源站原始字段(见同目录样本) | 幻影 | 空=源站未提供 |
| `away_team_score` | 源站原始字段(见同目录样本) | 117 | 空=源站未提供 |
| `begin_time` | 源站原始字段(见同目录样本) | 2026-09-14 17:45 | 空=源站未提供 |
| `handicap_val` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `handicap_result` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `overunder_val` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `overunder_result` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `result` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `tournament_name` | 源站原始字段(见同目录样本) | 菲律宾国家联赛 | 空=源站未提供 |
| `third_match_id` | 源站原始字段(见同目录样本) | 2099162842576105473 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### qiety_lineup_scrape_log

- 全库行数: 14,942   样本: 100 行 -> `samples/qiety_lineup_scrape_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | 5413891 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-07-30 | 空=源站未提供 |
| `scraped_at` | 源站原始字段(见同目录样本) | 2026-07-30 18:57:57 | 空=源站未提供 |

### qiety_lineups

- 全库行数: 86,203   样本: 100 行 -> `samples/qiety_lineups.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 87268 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5740738 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `team_side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `formation` | 源站原始字段(见同目录样本) | 0-0-0 | 空=源站未提供 |
| `role` | 源站原始字段(见同目录样本) | substitute | 空=源站未提供 |
| `position_name` | 源站原始字段(见同目录样本) | 前锋 | 空=源站未提供 |
| `position_en_name` | 源站原始字段(见同目录样本) | Forward | 空=源站未提供 |
| `shirt_number` | 源站原始字段(见同目录样本) | 55 | 空=源站未提供 |
| `player_name` | 球员姓名(公开体育数据) | 谷口大地 | 空=源站未提供 |
| `player_name_en` | 源站原始字段(见同目录样本) | Daichi Taniguchi | 空=源站未提供 |
| `player_source_id` | 源站原始字段(见同目录样本) | 936289 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### qiety_matches

- 全库行数: 29,800   样本: 100 行 -> `samples/qiety_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 58298 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5735687 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 塞浦路斯甲级联赛 | 空=源站未标注 |
| `home_team` | 主队名称 | 卡米奥提萨 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 尼科西亚奥林匹亚科斯 | 空=源站未覆盖 |
| `kickoff_time` | 源站原始字段(见同目录样本) | 2026-10-31 01:00 | 空=源站未提供 |
| `status` | 比赛状态 | NS | 空=未知 |
| `home_score` | 主队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |

### qiety_odds

- 全库行数: 4,860   样本: 100 行 -> `samples/qiety_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 5472 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5430791 | 空=源站未提供 |
| `bookmaker` | 赔率来源公司/源站 | qiety_yb | 空=未标注 |
| `market_type` | 源站原始字段(见同目录样本) | 1x2 | 空=源站未提供 |
| `line` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `odds_home` | 主胜赔率 | 1.42 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 |  | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 2.41 | 空=该场无此盘口 |
| `over_odds` | 大/小球赔率 |  | 空=无对应盘口 |
| `under_odds` | 大/小球赔率 |  | 空=无对应盘口 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-10 | 空=源站未提供 |

### qiety_odds_snapshots

- 全库行数: 91,301   样本: 100 行 -> `samples/qiety_odds_snapshots.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 91307 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5735687 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `odds_type` | 源站原始字段(见同目录样本) | over_under | 空=源站未提供 |
| `odds_home` | 主胜赔率 | 1.77 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 |  | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 2.03 | 空=该场无此盘口 |
| `handicap_line` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `total_line` | 大小球盘口线 | 2.5 | 空=无大小球 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-10-31 | 空=源站未提供 |
| `batch_ts` | 源站原始字段(见同目录样本) | 2026-10-30 13:10:40 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-30 13:18:53 | 空=历史回填无时间戳 |

### qiety_standings

- 全库行数: 224,487   样本: 100 行 -> `samples/qiety_standings.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 227664 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5754321 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | basketball | 空=源站未提供 |
| `ranking_id` | 源站原始字段(见同目录样本) | 261647 | 空=源站未提供 |
| `ranking_name` | 源站原始字段(见同目录样本) | 波多黎各女子联赛 | 空=源站未提供 |
| `ranking_round` | 源站原始字段(见同目录样本) | 联赛 | 空=源站未提供 |
| `team_cn_name` | 源站原始字段(见同目录样本) | 卡里杜拉斯法哈多(女) | 空=源站未提供 |
| `team_en_name` | 源站原始字段(见同目录样本) | 卡里杜拉斯法哈多(女) | 空=源站未提供 |
| `third_team_source_id` | 源站原始字段(见同目录样本) | 600881 | 空=源站未提供 |
| `position` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `matches_played` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `win` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `draw` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `loss` | 源站原始字段(见同目录样本) | 9 | 空=源站未提供 |
| `goals_for` | 源站原始字段(见同目录样本) | 631 | 空=源站未提供 |
| `goals_against` | 源站原始字段(见同目录样本) | 765 | 空=源站未提供 |
| `goal_diff` | 源站原始字段(见同目录样本) | -134 | 空=源站未提供 |
| `points` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `promotion_cn_name` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### qiumibao_match_results

- 全库行数: 31,565   样本: 100 行 -> `samples/qiumibao_match_results.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 85328 | 不应为空 |
| `source_match_id` | 源站原始字段(见同目录样本) | 2323717 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 10000181 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 乌拉后备 | 空=源站未标注 |
| `status_code` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-27T13:00:00Z | 空=源站未提供 |
| `home_team` | 主队名称 | 蒙特维多城图尔克后备 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 阿尔比恩后备队 | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 4 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `home_corners` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `away_corners` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `corners_confidence` | 源站原始字段(见同目录样本) | unconfirmed_field_index | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-27 | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-10-27 22:58:36 | 空=历史回填无时间戳 |

### qiumibao_odds_snapshot

- 全库行数: 1,348   样本: 100 行 -> `samples/qiumibao_odds_snapshot.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1485 | 不应为空 |
| `source_match_id` | 源站原始字段(见同目录样本) | 2077961 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_id` | 源站原始字段(见同目录样本) | 149 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 罗甲 | 空=源站未标注 |
| `status_code` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-12T15:00:00Z | 空=源站未提供 |
| `home_team` | 主队名称 | 阿格斯 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 克卢日 | 空=源站未覆盖 |
| `lottery_periods` | 源站原始字段(见同目录样本) | 北391 | 空=源站未提供 |
| `odds_raw` | 源站原始字段(见同目录样本) | 胜平负,2.6,3,2.6/,,,/北单胜负,13,-0… | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `fetched_at` | 源站原始字段(见同目录样本) | 2026-10-12 11:46:40 | 空=源站未提供 |

### ren9_live_slips

- 全库行数: 235   样本: 100 行 -> `samples/ren9_live_slips.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 423 | 不应为空 |
| `period` | 源站原始字段(见同目录样本) | 26152 | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `mode` | 源站原始字段(见同目录样本) | double | 空=源站未提供 |
| `pick` | 源站原始字段(见同目录样本) | 主胜+平局 | 空=源站未提供 |
| `slip_type` | 源站原始字段(见同目录样本) | live | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-28 21:53:38 | 空=历史回填无时间戳 |
| `batch` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### ren9_rule_review

- 全库行数: 69   样本: 69 行 -> `samples/ren9_rule_review.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 139 | 不应为空 |
| `period` | 源站原始字段(见同目录样本) | 26125 | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `home_team` | 主队名称 | 博德 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 桑纳菲 | 空=源站未覆盖 |
| `odds_home` | 主胜赔率 | 1.11 | 空=该场无此盘口/未抓取，不是0 |
| `odds_draw` | 平局赔率 | 9.6 | 空=无平局盘口 |
| `odds_away` | 客胜赔率 | 15.82 | 空=该场无此盘口 |
| `actual` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `old_picks` | 源站原始字段(见同目录样本) | 主胜 | 空=源站未提供 |
| `new_picks` | 源站原始字段(见同目录样本) | 主胜 | 空=源站未提供 |
| `old_hit` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `new_hit` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-15 12:12:18 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-15 02:18:21 | 空=历史回填无时间戳 |
| `dp_mode` | 源站原始字段(见同目录样本) | single | 空=源站未提供 |
| `dp_pick` | 源站原始字段(见同目录样本) | 主胜 | 空=源站未提供 |
| `dp_hit` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `top2_hit` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `flip_hit` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `live_dp_pick` | 源站原始字段(见同目录样本) | 主胜 | 空=源站未提供 |
| `live_dp_hit` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `pin_diverge` | Pinnacle来源字段 | 0 | 空=未匹配Pinnacle |
| `pin_dp_hit` | Pinnacle来源字段 | 1 | 空=未匹配Pinnacle |
| `dp_hit_recalc` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |

### ren9_shadow_v2

- 全库行数: 2   样本: 2 行 -> `samples/ren9_shadow_v2.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 3 | 不应为空 |
| `period` | 源站原始字段(见同目录样本) | 26119 | 空=源站未提供 |
| `strategy` | 源站原始字段(见同目录样本) | double_anti_favorite | 空=源站未提供 |
| `matches_json` | 源站原始字段(见同目录样本) | [{"seq": 1, "home": "埃弗顿", "… | 空=源站未提供 |
| `lines_json` | 源站原始字段(见同目录样本) | [[13, "single", [0]], [9, "s… | 空=源站未提供 |
| `actual_json` | 源站原始字段(见同目录样本) | {"1": 1, "2": 3, "3": 0, "4"… | 空=源站未提供 |
| `hit` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `n_lines` | 源站原始字段(见同目录样本) | 32 | 空=源站未提供 |
| `cost_yuan` | 源站原始字段(见同目录样本) | 64.0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-07 | 空=源站未提供 |
| `settled_date` | 源站原始字段(见同目录样本) | 2026-09-07 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-09-07 19:25:32 | 空=历史回填无时间戳 |

### ren9_warning_signals

- 全库行数: 476   样本: 100 行 -> `samples/ren9_warning_signals.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 476 | 不应为空 |
| `period` | 源站原始字段(见同目录样本) | 26152 | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `run_ts` | 源站原始字段(见同目录样本) | 2026-10-28 21:54:44 | 空=源站未提供 |
| `fav_dir` | 源站原始字段(见同目录样本) | 客胜 | 空=源站未提供 |
| `okooo_drift_pp` | 源站原始字段(见同目录样本) | 0.08 | 空=源站未提供 |
| `okooo_batches` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `qiety_drift_pp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `qiety_batches` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `qiety_stale` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `pin_diff_pp` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `pin_dir` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `jc_premium_pp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `level` | 源站原始字段(见同目录样本) | 无 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-28 21:54:52 | 空=历史回填无时间戳 |
| `outcome_hit` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `okooo_top_right` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `pin_top_right` | Pinnacle来源字段 |  | 空=未匹配Pinnacle |
| `note` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### scraper_run_log

- 全库行数: 4,212   样本: 100 行 -> `samples/scraper_run_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 4255 | 不应为空 |
| `scraper` | 源站原始字段(见同目录样本) | 29_qiety_yb_full_scraper.run… | 空=源站未提供 |
| `run_at` | 源站原始字段(见同目录样本) | 2026-10-12T13:10:02 | 空=源站未提供 |
| `status` | 比赛状态 | ok | 空=未知 |
| `records_written` | 源站原始字段(见同目录样本) | 105 | 空=源站未提供 |
| `error_msg` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `stdout_tail` | 源站原始字段(见同目录样本) | 补爬(token刷新后): 38场成功 105条赔率 | 空=源站未提供 |

### season_identity_evidence

- 全库行数: 55   样本: 55 行 -> `samples/season_identity_evidence.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `season_identity_id` | 源站原始字段(见同目录样本) | 1ca6b7d23b72afe500320daddedd… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `league_id` | 源站原始字段(见同目录样本) | 47 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Premier League | 空=源站未标注 |
| `league_code` | 源站原始字段(见同目录样本) | EPL | 空=源站未提供 |
| `season_id` | 源站原始字段(见同目录样本) | 36781 | 空=源站未提供 |
| `season_name` | 源站原始字段(见同目录样本) | 2026/2027 | 空=源站未提供 |
| `template_id` | 源站原始字段(见同目录样本) | 47 | 空=源站未提供 |
| `stage_id` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `country_code` | 源站原始字段(见同目录样本) | ENG | 空=源站未提供 |
| `relative_path` | 源站原始字段(见同目录样本) | stats/47/season/36781/topsta… | 空=源站未提供 |
| `source_url` | 源站原始字段(见同目录样本) | https://www.fotmob.com/api/d… | 空=源站未提供 |
| `raw_response_sha256` | 源站原始字段(见同目录样本) | ad52102d99edce9a2bde84f576e2… | 空=源站未提供 |
| `verified_http_status` | 源站原始字段(见同目录样本) | 200 | 空=源站未提供 |
| `verified_bytes` | 源站原始字段(见同目录样本) | 839816 | 空=源站未提供 |
| `verified_season_name_present` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T04:12:43Z | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T04:12:43Z | 空=源站未提供 |
| `first_seen_status` | 源站原始字段(见同目录样本) | PROVEN | 空=源站未提供 |
| `null_reasons` | 源站原始字段(见同目录样本) | {"season_id_field": "Tournam… | 空=源站未提供 |

### settle_summary

- 全库行数: 8   样本: 8 行 -> `samples/settle_summary.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 8 | 不应为空 |
| `created_at` | 抓取/写入时间 | 2026-07-03T12:37:29.708400 | 空=历史回填无时间戳 |
| `total_bets` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `wins` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `losses` | 源站原始字段(见同目录样本) | 9 | 空=源站未提供 |
| `pushes` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `total_stake` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `total_pnl` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `roi` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `win_rate` | 源站原始字段(见同目录样本) | 10.0 | 空=源站未提供 |
| `settle_date` | 源站原始字段(见同目录样本) | 2026-07-01 | 空=源站未提供 |
| `slip_label` | 源站原始字段(见同目录样本) | score_prediction | 空=源站未提供 |

### shadow_recommendations

- 全库行数: 3,930   样本: 100 行 -> `samples/shadow_recommendations.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 10826 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 4ed3b339e7e0 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Belgium - Pro League | 空=源站未标注 |
| `home_team` | 主队名称 | KV Kortrijk | 空=源站未覆盖 |
| `away_team` | 客队名称 | Mechelen | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T18:45:00Z | 空=源站未提供 |
| `shadow_type` | 源站原始字段(见同目录样本) | htft_nofilter | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | ht_ft | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | home-home | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 |  | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 3.5845 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.279 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.279 | 空=源站未提供 |
| `predicted_score` | 源站原始字段(见同目录样本) | - | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T07:01:50 | 空=历史回填无时间戳 |

### soccerway_matches

- 全库行数: 2,259   样本: 100 行 -> `samples/soccerway_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 95345 | 不应为空 |
| `sw_match_id` | 源站原始字段(见同目录样本) | EycsIRSI | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | uecl | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | uecl | 空=源站未标注 |
| `season` | 赛季标识 | current | 空=源站未提供 |
| `home_team` | 主队名称 | Lincoln Red Imps (Gib) | 空=源站未覆盖 |
| `away_team` | 客队名称 | Larne (Nir) | 空=源站未覆盖 |
| `home_team_id` | 源站原始字段(见同目录样本) | EVPCpHv2 | 空=源站未提供 |
| `away_team_id` | 源站原始字段(见同目录样本) | txIb8KW8 | 空=源站未提供 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-08-20T16:00:00 | 空=源站未提供 |
| `status` | 比赛状态 | FT | 空=未知 |
| `home_score` | 主队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `home_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `venue` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `referee` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-12 04:18:40 | 空=历史回填无时间戳 |

### sofa_bball_matches

- 全库行数: 837   样本: 100 行 -> `samples/sofa_bball_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 6579 | 不应为空 |
| `event_id` | 源站原始字段(见同目录样本) | 15878336 | 空=源站未提供 |
| `tournament_id` | 源站原始字段(见同目录样本) | 406 | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) | czech_nbl | 空=源站未提供 |
| `home_team` | 主队名称 | Mjällby AIF | 空=源站未覆盖 |
| `away_team` | 客队名称 | Hammarby IF | 空=源站未覆盖 |
| `start_timestamp` | 源站原始字段(见同目录样本) | 1778765400 | 空=源站未提供 |
| `home_score` | 主队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 1 | 空=未开赛或源站未覆盖，不是0 |
| `status` | 比赛状态 | Ended | 空=未知 |
| `round_info` | 源站原始字段(见同目录样本) | 29 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-20 | 空=源站未提供 |

### sofa_bball_stats

- 全库行数: 3,750   样本: 100 行 -> `samples/sofa_bball_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 58684 | 不应为空 |
| `event_id` | 源站原始字段(见同目录样本) | 15878336 | 空=源站未提供 |
| `team_side` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Hammarby IF | 空=源站未提供 |
| `stat_key` | 源站原始字段(见同目录样本) | goalKicks | 空=源站未提供 |
| `stat_value` | 源站原始字段(见同目录样本) | 8 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-20 | 空=源站未提供 |

### soft_odds_snapshots

- 全库行数: 204,679   样本: 100 行 -> `samples/soft_odds_snapshots.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 204776 | 不应为空 |
| `source` | 源站原始字段(见同目录样本) | qiety | 空=源站未提供 |
| `book` | 赔率来源公司/源站 | qiety_yb | 空=未标注 |
| `match_key` | 源站原始字段(见同目录样本) | 5770617 | 空=源站未提供 |
| `pinn_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `home_team` | 主队名称 | 奥卡斯 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 瓜亚基尔巴塞罗那 | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-25T21:30:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | OU | 空=源站未提供 |
| `line` | 源站原始字段(见同目录样本) | 2.25 | 空=源站未提供 |
| `selection` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `price_dec` | 源站原始字段(见同目录样本) | 1.87 | 空=源站未提供 |
| `book_last_update_utc` | 源站原始字段(见同目录样本) | 2026-10-25T11:39:59Z | 空=源站未提供 |
| `captured_at_utc` | 源站原始字段(见同目录样本) | 2026-10-25T14:57:16Z | 空=源站未提供 |
| `row_hash` | 源站原始字段(见同目录样本) | 327c2caa82c41c7a3ad9db5b7881… | 空=源站未提供 |
| `qc_flag` | 数据质量标记 |  | 空=未质检 |
| `league` | 联赛/赛事名称 | 厄瓜多尔甲级联赛 - 附加赛 | 空=源站未标注 |
| `src_row_id` | 源站原始字段(见同目录样本) | 90087 | 空=源站未提供 |

### soft_snap_seen

- 全库行数: 1   样本: 1 行 -> `samples/soft_snap_seen.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `k` | 源站原始字段(见同目录样本) | __qiety_snap_id__ | 空=源站未提供 |
| `last_hash` | 源站原始字段(见同目录样本) | 90087 | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-25T14:57:19Z | 空=源站未提供 |

### source_collection_runs

- 全库行数: 9   样本: 9 行 -> `samples/source_collection_runs.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `run_id` | 源站原始字段(见同目录样本) | f0d38ba409818f667dfe504bd700… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | The Odds API | 空=未标注 |
| `script` | 源站原始字段(见同目录样本) | 35_theoddsapi_multi_scraper.… | 空=源站未提供 |
| `scope` | 源站原始字段(见同目录样本) | sport:soccer_epl | 空=源站未提供 |
| `args_json` | 源站原始字段(见同目录样本) | {"fetch_date": "2026-10-09",… | 空=源站未提供 |
| `host` | 源站原始字段(见同目录样本) | DESKTOP-6ILDITG | 空=源站未提供 |
| `pid` | 源站原始字段(见同目录样本) | 15324 | 空=源站未提供 |
| `invoked_by` | 源站原始字段(见同目录样本) | manual:35_theoddsapi_multi_s… | 空=源站未提供 |
| `started_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:36:07Z | 空=源站未提供 |
| `finished_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:36:07Z | 空=源站未提供 |
| `duration_s` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `requests_total` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `requests_ok` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `requests_failed` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `bodies_new` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `bodies_deduplicated` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `rows_written_json` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `status` | 比赛状态 | blocked | 空=未知 |
| `blocked_reason` | 源站原始字段(见同目录样本) | quota_below_threshold | 空=源站未提供 |
| `exit_code` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `legacy_run_log_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | total_remaining=11 | 空=源站未提供 |

### source_evidence_limitations

- 全库行数: 12   样本: 12 行 -> `samples/source_evidence_limitations.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `limitation_id` | 源站原始字段(见同目录样本) | 20261009_fotmob_http_dispatc… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `scope` | 源站原始字段(见同目录样本) | run:2026-10-09T02:11:22Z..02… | 空=源站未提供 |
| `claim` | 源站原始字段(见同目录样本) | 本次采集共发生 477 次 HTTP 派发（observ… | 空=源站未提供 |
| `verdict` | 源站原始字段(见同目录样本) | NOT_PROVABLE | 空=源站未提供 |
| `provable_lower_bound` | 源站原始字段(见同目录样本) | 418 | 空=源站未提供 |
| `counter_value` | 源站原始字段(见同目录样本) | 477 | 空=源站未提供 |
| `dispatch_receipts` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `ledger_epoch_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:00:00Z | 空=源站未提供 |
| `corroboration_json` | 源站原始字段(见同目录样本) | {"leagues_with_repeat": 61, … | 空=源站未提供 |
| `counterexample` | 源站原始字段(见同目录样本) | matchDetails: 计数 350 次 vs 身份… | 空=源站未提供 |
| `recorded_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:42:11Z | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | 477 只能表述为『body 落库计数』；真实派发次数上… | 空=源站未提供 |

### source_exception_audit

- 全库行数: 3   样本: 3 行 -> `samples/source_exception_audit.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `exception_id` | 源站原始字段(见同目录样本) | e5c1fc7e996600b6a48a1eb0ed31… | 空=源站未提供 |
| `run_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | The Odds API | 空=未标注 |
| `occurred_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:35:40Z | 空=源站未提供 |
| `severity` | 源站原始字段(见同目录样本) | warning | 空=源站未提供 |
| `category` | 源站原始字段(见同目录样本) | quota | 空=源站未提供 |
| `endpoint` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_entity_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `http_status` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `exception_type` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `message` | 源站原始字段(见同目录样本) | 额度闸拦截：七槽合计 11 < 下限 50；未发送任何请… | 空=源站未提供 |
| `attempt_index` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `handled` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `retry_count` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `raw_response_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `context_json` | 源站原始字段(见同目录样本) | {"total_remaining": 11} | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### source_field_observations

- 全库行数: 25,484   样本: 100 行 -> `samples/source_field_observations.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 25486 | 不应为空 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `source_entity_type` | 源站原始字段(见同目录样本) | match | 空=源站未提供 |
| `source_entity_id` | 源站原始字段(见同目录样本) | 5795472 | 空=源站未提供 |
| `field_name` | 源站原始字段(见同目录样本) | __absent__ | 空=源站未提供 |
| `field_value` | 源站原始字段(见同目录样本) | season_id,season_name | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:13:35Z | 空=源站未提供 |
| `first_seen_status` | 源站原始字段(见同目录样本) | PROVEN | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:13:35Z | 空=源站未提供 |
| `observation_count` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `source_event_time_utc` | 源站原始字段(见同目录样本) | 2026-10-11T15:30:00 | 空=源站未提供 |
| `provider_updated_at_utc` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `data_version` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `data_version_kind` | 源站原始字段(见同目录样本) | unknown | 空=源站未提供 |
| `match_state` | 源站原始字段(见同目录样本) | prematch | 空=源站未提供 |
| `available_before_kickoff` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `first_receipt_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `last_receipt_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | PROVEN-ABSENT: 截至该观察时间，FotMo… | 空=源站未提供 |
| `evidence_grade` | 源站原始字段(见同目录样本) | TIME_ONLY | 空=源站未提供 |

### source_identity_crosswalk

- 全库行数: 1   样本: 1 行 -> `samples/source_identity_crosswalk.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `crosswalk_id` | 源站原始字段(见同目录样本) | 3a7a508e4cf8d0c25974d1054352… | 空=源站未提供 |
| `entity_type` | 源站原始字段(见同目录样本) | fixture | 空=源站未提供 |
| `provider_a` | 源站原始字段(见同目录样本) | FotMob | 空=源站未提供 |
| `source_id_a` | 源站原始字段(见同目录样本) | 5795472 | 空=源站未提供 |
| `provider_b` | 源站原始字段(见同目录样本) | The Odds API | 空=源站未提供 |
| `source_id_b` | 源站原始字段(见同目录样本) | 6dbab232dd8d2aed0cb1d6f7978f… | 空=源站未提供 |
| `match_basis` | 源站原始字段(见同目录样本) | exact_team_names+identical_k… | 空=源站未提供 |
| `confidence` | 源站原始字段(见同目录样本) | exact | 空=源站未提供 |
| `status` | 比赛状态 | PROPOSED | 空=未知 |
| `evidence_json` | 源站原始字段(见同目录样本) | {"fotmob_home": "Liverpool",… | 空=源站未提供 |
| `created_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:24:31Z | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | PROPOSED only — canonical fi… | 空=源站未提供 |

### source_identity_evidence

- 全库行数: 5   样本: 5 行 -> `samples/source_identity_evidence.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 5 | 不应为空 |
| `identity_key` | 源站原始字段(见同目录样本) | b09c469a0c35e1200c15ed7db41b… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | The Odds API | 空=未标注 |
| `entity_type` | 源站原始字段(见同目录样本) | fixture | 空=源站未提供 |
| `source_id` | 源站原始字段(见同目录样本) | 6dbab232dd8d2aed0cb1d6f7978f… | 空=源站未提供 |
| `entity_name` | 源站原始字段(见同目录样本) | Liverpool vs Manchester City | 空=源站未提供 |
| `parent_entity_type` | 源站原始字段(见同目录样本) | league | 空=源站未提供 |
| `parent_source_id` | 源站原始字段(见同目录样本) | soccer_epl | 空=源站未提供 |
| `source_observation_time` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `first_seen_status` | 源站原始字段(见同目录样本) | PROVEN | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) | 71d7c0fa7e3bba11e1d40abe736f… | 空=源站未提供 |
| `receipt_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `evidence_json` | 源站原始字段(见同目录样本) | {"sport_key": "soccer_epl", … | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | The Odds API event id from s… | 空=源站未提供 |

### source_incident_log

- 全库行数: 3   样本: 3 行 -> `samples/source_incident_log.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `incident_id` | 源站原始字段(见同目录样本) | 20261009_mock_row_cleanup | 空=源站未提供 |
| `kind` | 源站原始字段(见同目录样本) | data_deletion | 空=源站未提供 |
| `occurred_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T00:35:51Z | 空=源站未提供 |
| `recorded_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:51:04Z | 空=源站未提供 |
| `actor` | 源站原始字段(见同目录样本) | hermes | 空=源站未提供 |
| `description` | 源站原始字段(见同目录样本) | 开发期首版失败模式测试未隔离 DB，把 2 行 mock… | 空=源站未提供 |
| `affected_table` | 源站原始字段(见同目录样本) | theodds_api_raw_responses | 空=源站未提供 |
| `before_count` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `after_count` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `affected_rows_json` | 源站原始字段(见同目录样本) | [{"observation_id": "737c8e3… | 空=源站未提供 |
| `reason` | 源站原始字段(见同目录样本) | test isolation bug: TestOdds… | 空=源站未提供 |
| `verifier` | 源站原始字段(见同目录样本) | 清理后 COUNT(*) theodds_api_raw… | 空=源站未提供 |
| `evidence_json` | 源站原始字段(见同目录样本) | {"cleanup_sql": "DELETE FROM… | 空=源站未提供 |
| `evidence_status` | 源站原始字段(见同目录样本) | RECONSTRUCTED_FROM_SESSION | 空=源站未提供 |

### source_quota_receipts

- 全库行数: 107   样本: 100 行 -> `samples/source_quota_receipts.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `receipt_id` | 源站原始字段(见同目录样本) | b82a435a6ad055d71b408d5c31e6… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | The Odds API | 空=未标注 |
| `slot_id` | 源站原始字段(见同目录样本) | THE_ODDS_API_SLOT_1 | 空=源站未提供 |
| `key_fingerprint` | 源站原始字段(见同目录样本) | … | 空=源站未提供 |
| `endpoint` | 源站原始字段(见同目录样本) | /sports/ | 空=源站未提供 |
| `http_status` | 源站原始字段(见同目录样本) | 200 | 空=源站未提供 |
| `quota_remaining` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `quota_used` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `quota_last` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T03:06:49Z | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | backfilled from local quota … | 空=源站未提供 |

### source_request_ledger

- 全库行数: 4,842   样本: 100 行 -> `samples/source_request_ledger.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `receipt_id` | 源站原始字段(见同目录样本) | 626180cd6f1e487cf6bdcf070899… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | FotMob | 空=未标注 |
| `endpoint` | 源站原始字段(见同目录样本) | matchDetails | 空=源站未提供 |
| `source_match_id` | 源站原始字段(见同目录样本) | 5795472 | 空=源站未提供 |
| `source_league_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_event_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `sport_key` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `request_url` | 源站原始字段(见同目录样本) | https://www.fotmob.com/api/d… | 空=源站未提供 |
| `request_params_sanitized` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `request_started_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T05:55:58Z | 空=源站未提供 |
| `request_finished_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T05:56:00Z | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T05:56:00Z | 空=源站未提供 |
| `http_status` | 源站原始字段(见同目录样本) | 200 | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | ok | 空=源站未提供 |
| `transport_error` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `attempt_index` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `response_sha256` | 源站原始字段(见同目录样本) | ccbac9bb0196d26fd3f3329e3a2e… | 空=源站未提供 |
| `response_bytes` | 源站原始字段(见同目录样本) | 58713 | 空=源站未提供 |
| `raw_response_id` | 源站原始字段(见同目录样本) | 2785d841d53b1b5159d00c0c3a3b… | 空=源站未提供 |
| `body_deduplicated` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `etag` | 源站原始字段(见同目录样本) | W/"998cokusfw195g" | 空=源站未提供 |
| `last_modified` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `content_type` | 源站原始字段(见同目录样本) | application/json; charset=ut… | 空=源站未提供 |
| `quota_remaining` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `quota_used` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `quota_last` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `evidence_grade` | 源站原始字段(见同目录样本) | DIRECT_HTTP_RECEIPT | 空=源站未提供 |
| `request_scope` | 源站原始字段(见同目录样本) | matchDetails:5795472 | 空=源站未提供 |
| `quota_cost` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `error_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### sqlite_sequence

- 全库行数: 137   样本: 100 行 -> `samples/sqlite_sequence.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `name` | 源站原始字段(见同目录样本) | basketball_matches | 空=源站未提供 |
| `seq` | 源站原始字段(见同目录样本) | 56568 | 空=源站未提供 |

### statsbomb_national_xg_matches

- 全库行数: 377   样本: 100 行 -> `samples/statsbomb_national_xg_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 20781 | 不应为空 |
| `match_id` | 比赛ID(源站) | 3930158 | 空=源站未提供 |
| `competition_id` | 源站原始字段(见同目录样本) | 55 | 空=源站未提供 |
| `competition_name` | 源站原始字段(见同目录样本) | UEFA Euro | 空=源站未提供 |
| `season_name` | 源站原始字段(见同目录样本) | 2024 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2024-06-14 | 空=源站未提供 |
| `home_team` | 主队名称 | Germany | 空=源站未覆盖 |
| `away_team` | 客队名称 | Scotland | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 5 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 1 | 空=未开赛或源站未覆盖，不是0 |
| `home_xg` | 预期进球xG | 1.8446 | 空=源站无xG |
| `away_xg` | 预期进球xG | 0.0605 | 空=源站无xG |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### statsbomb_national_xg_teams

- 全库行数: 228   样本: 100 行 -> `samples/statsbomb_national_xg_teams.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 10156 | 不应为空 |
| `competition_name` | 源站原始字段(见同目录样本) | UEFA Euro | 空=源站未提供 |
| `season_name` | 源站原始字段(见同目录样本) | 2024 | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Albania | 空=源站未提供 |
| `matches_played` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `total_xg` | 源站原始字段(见同目录样本) | 2.1837 | 空=源站未提供 |
| `total_xga` | 源站原始字段(见同目录样本) | 4.2601 | 空=源站未提供 |
| `avg_xg` | 源站原始字段(见同目录样本) | 0.7279 | 空=源站未提供 |
| `avg_xga` | 源站原始字段(见同目录样本) | 1.42 | 空=源站未提供 |
| `goals_scored` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `goals_conceded` | 源站原始字段(见同目录样本) | 5 | 空=源站未提供 |
| `update_time` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |

### statsbomb_team_xg

- 全库行数: 469   样本: 100 行 -> `samples/statsbomb_team_xg.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1338 | 不应为空 |
| `team_name` | 源站原始字段(见同目录样本) | Napoli | 空=源站未提供 |
| `competition` | 源站原始字段(见同目录样本) | Serie A | 空=源站未提供 |
| `season` | 赛季标识 | 1986/1987 | 空=源站未提供 |
| `xg` | 预期进球xG | 0.0 | 空=源站无xG |
| `xga` | 源站原始字段(见同目录样本) | 0.0 | 空=源站未提供 |
| `matches` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-06 | 空=源站未提供 |

### team_form

- 全库行数: 2,382   样本: 100 行 -> `samples/team_form.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 3573 | 不应为空 |
| `team` | 源站原始字段(见同目录样本) | Nurnberg | 空=源站未提供 |
| `sport` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `venue` | 源站原始字段(见同目录样本) | overall | 空=源站未提供 |
| `games` | 源站原始字段(见同目录样本) | 10 | 空=源站未提供 |
| `wins` | 源站原始字段(见同目录样本) | 4 | 空=源站未提供 |
| `draws` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `losses` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `goals_for` | 源站原始字段(见同目录样本) | 18.0 | 空=源站未提供 |
| `goals_against` | 源站原始字段(见同目录样本) | 10.0 | 空=源站未提供 |
| `form_str` | 源站原始字段(见同目录样本) | DWWDD | 空=源站未提供 |
| `form_score` | 源站原始字段(见同目录样本) | 0.7 | 空=源站未提供 |
| `as_of_date` | 源站原始字段(见同目录样本) | 2026-06-24 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-24 | 空=源站未提供 |

### team_gnn_courtmotion

- 全库行数: 96   样本: 96 行 -> `samples/team_gnn_courtmotion.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | nba | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | Atlanta Hawks | 空=源站未提供 |
| `sport_type` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `gnn_correlation_score` | 源站原始字段(见同目录样本) | 1.0938 | 空=源站未提供 |
| `court_motion_factor` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |

### team_lstm_state

- 全库行数: 544   样本: 100 行 -> `samples/team_lstm_state.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | allsvenskan | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | AIK | 空=源站未提供 |
| `state_score` | 源站原始字段(见同目录样本) | 1.98 | 空=源站未提供 |
| `state_level` | 源站原始字段(见同目录样本) | 稳定 | 空=源站未提供 |

### team_master

- 全库行数: 125   样本: 100 行 -> `samples/team_master.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `team_id_internal` | 源站原始字段(见同目录样本) | 124 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `team_name_std` | 源站原始字段(见同目录样本) | 摩洛哥 | 空=源站未提供 |
| `source_team_name` | 源站原始字段(见同目录样本) | 摩洛哥 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-07 10:40:46 | 空=历史回填无时间戳 |

### team_multimodal

- 全库行数: 48   样本: 48 行 -> `samples/team_multimodal.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | nba | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | Atlanta Hawks | 空=源站未提供 |
| `injury_factor` | 源站原始字段(见同目录样本) | 0.8839065927166055 | 空=源站未提供 |
| `suspension_factor` | 源站原始字段(见同目录样本) | 0.9317504496025024 | 空=源站未提供 |
| `sentiment_factor` | 源站原始字段(见同目录样本) | 0.9861812610553391 | 空=源站未提供 |
| `multimodal_total` | 源站原始字段(见同目录样本) | 0.8121995231040762 | 空=源站未提供 |

### team_name_map

- 全库行数: 746   样本: 100 行 -> `samples/team_name_map.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2781 | 不应为空 |
| `en_name` | 源站原始字段(见同目录样本) | Vila Nova | 空=源站未提供 |
| `zh_name` | 源站原始字段(见同目录样本) | Vila Nova FC | 空=源站未提供 |
| `sport` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `confidence` | 源站原始字段(见同目录样本) | 0.75 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | substr_norm | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-06-19 13:50:31 | 空=历史回填无时间戳 |

### team_preview_notes

- 全库行数: 112   样本: 100 行 -> `samples/team_preview_notes.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `note_id` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `season` | 赛季标识 | 2026-27 | 空=源站未提供 |
| `league_name_cn` | 源站原始字段(见同目录样本) | 德乙 | 空=源站未提供 |
| `team_name_cn` | 源站原始字段(见同目录样本) | 科特布斯 | 空=源站未提供 |
| `team_status` | 源站原始字段(见同目录样本) | 升班马 | 空=源站未提供 |
| `outlook` | 源站原始字段(见同目录样本) | 中性 | 空=源站未提供 |
| `key_signings` | 源站原始字段(见同目录样本) | 不莱梅老将比腾考特回归(中场实力提升) | 空=源站未提供 |
| `key_departures` | 源站原始字段(见同目录样本) | 主力门将、2名主力中卫离队 | 空=源站未提供 |
| `manager_note` | 源站原始字段(见同目录样本) | 沃利茨(兼俱乐部总监，稳定) | 空=源站未提供 |
| `summary` | 源站原始字段(见同目录样本) | 前东德球队，主场进球能力强(德丙主场进球第二多)，关键球… | 空=源站未提供 |
| `author_pick` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `source_article_id` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `ingested_at` | 源站原始字段(见同目录样本) | 2026-08-23 03:28:05 | 空=源站未提供 |

### team_rl_mas

- 全库行数: 48   样本: 48 行 -> `samples/team_rl_mas.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | nba | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | Atlanta Hawks | 空=源站未提供 |
| `rl_home_bonus` | 源站原始字段(见同目录样本) | 1.1264 | 空=源站未提供 |
| `rl_away_bonus` | 源站原始字段(见同目录样本) | 1.1344 | 空=源站未提供 |

### team_total_shadow_full

- 全库行数: 639   样本: 100 行 -> `samples/team_total_shadow_full.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1481 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 5726bae4854f | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Ireland - Premier | 空=源站未标注 |
| `home_team` | 主队名称 | Bohemians | 空=源站未覆盖 |
| `away_team` | 客队名称 | Shelbourne | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T18:45:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | team_total_home | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 1.5 | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 2.28 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.5114 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0324 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.6742 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T07:01:50 | 空=历史回填无时间戳 |

### team_transformer_state

- 全库行数: 496   样本: 100 行 -> `samples/team_transformer_state.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `league` | 联赛/赛事名称 | allsvenskan | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | AIK | 空=源站未提供 |
| `trans_score` | 源站原始字段(见同目录样本) | 1.7865 | 空=源站未提供 |

### theodds_api_bookmakers

- 全库行数: 3   样本: 3 行 -> `samples/theodds_api_bookmakers.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `bookmaker_key` | 源站原始字段(见同目录样本) | unibet | 空=源站未提供 |
| `bookmaker_title` | 源站原始字段(见同目录样本) | Unibet | 空=源站未提供 |
| `regions_seen` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `markets_seen` | 源站原始字段(见同目录样本) | h2h,totals | 空=源站未提供 |
| `market_count` | 源站原始字段(见同目录样本) | 145 | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-24T10:30:29Z | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-24T10:30:29Z | 空=源站未提供 |

### theodds_api_events

- 全库行数: 895   样本: 100 行 -> `samples/theodds_api_events.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `event_id` | 源站原始字段(见同目录样本) | b870dcfba5e5920d3f1551a3aa1e… | 空=源站未提供 |
| `sport_key` | 源站原始字段(见同目录样本) | soccer_epl | 空=源站未提供 |
| `sport_title` | 源站原始字段(见同目录样本) | EPL | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | EPL | 空=源站未标注 |
| `commence_time` | 开赛时间 | 2026-10-10T11:30:00Z | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | Arsenal | 空=源站未覆盖 |
| `away_team` | 客队名称 | Leeds United | 空=源站未覆盖 |
| `source_event_identity` | 源站原始字段(见同目录样本) | provider_event_id | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `last_observation_id` | 源站原始字段(见同目录样本) | 16be2a3acdf4f1006d1c84651f2e… | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) | 71d7c0fa7e3bba11e1d40abe736f… | 空=源站未提供 |

### theodds_api_market_catalog

- 全库行数: 56   样本: 56 行 -> `samples/theodds_api_market_catalog.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `market_key` | 源站原始字段(见同目录样本) | spreads | 空=源站未提供 |
| `description` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `category` | 源站原始字段(见同目录样本) | spreads | 空=源站未提供 |
| `period_scope` | 源站原始字段(见同目录样本) | full | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | official_docs | 空=源站未提供 |
| `verified` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `notes` | 源站原始字段(见同目录样本) | documented in The Odds API v… | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-24T10:30:29Z | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-24T10:30:29Z | 空=源站未提供 |

### theodds_api_odds

- 全库行数: 180,505   样本: 100 行 -> `samples/theodds_api_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 345784 | 不应为空 |
| `event_id` | 源站原始字段(见同目录样本) | c053847753ea72ff5c917f7ae0ec… | 空=源站未提供 |
| `sport` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `sport_key` | 源站原始字段(见同目录样本) | soccer_usa_mls | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | MLS | 空=源站未标注 |
| `home_team` | 主队名称 | Vancouver Whitecaps FC | 空=源站未覆盖 |
| `away_team` | 客队名称 | San Diego FC | 空=源站未覆盖 |
| `commence_time` | 开赛时间 | 2026-10-29T02:30:00Z | UTC或源站时区，需按README时区说明换算 |
| `bookmaker` | 赔率来源公司/源站 | unibet | 空=未标注 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `odds` | 源站原始字段(见同目录样本) | 2.02 | 空=源站未提供 |
| `point` | 源站原始字段(见同目录样本) | 3.5 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-24 | 空=源站未提供 |

### theodds_api_odds_history

- 全库行数: 10,960   样本: 100 行 -> `samples/theodds_api_odds_history.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `observation_id` | 源站原始字段(见同目录样本) | 0ad0ac888a3a0263401a393d2fca… | 空=源站未提供 |
| `contract_key` | 源站原始字段(见同目录样本) | 0ad0ac888a3a0263401a393d2fca… | 空=源站未提供 |
| `event_id` | 源站原始字段(见同目录样本) | b870dcfba5e5920d3f1551a3aa1e… | 空=源站未提供 |
| `sport_key` | 源站原始字段(见同目录样本) | soccer_epl | 空=源站未提供 |
| `sport_title` | 源站原始字段(见同目录样本) | EPL | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | EPL | 空=源站未标注 |
| `home_team` | 主队名称 | Arsenal | 空=源站未覆盖 |
| `away_team` | 客队名称 | Leeds United | 空=源站未覆盖 |
| `commence_time` | 开赛时间 | 2026-10-10T11:30:00Z | UTC或源站时区，需按README时区说明换算 |
| `bookmaker_key` | 源站原始字段(见同目录样本) | betfair_ex_uk | 空=源站未提供 |
| `bookmaker_title` | 源站原始字段(见同目录样本) | Betfair | 空=源站未提供 |
| `bookmaker_region` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `market_key` | 源站原始字段(见同目录样本) | h2h | 空=源站未提供 |
| `market_period` | 源站原始字段(见同目录样本) | full | 空=源站未提供 |
| `market_last_update` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:02Z | 空=源站未提供 |
| `bookmaker_last_update` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:02Z | 空=源站未提供 |
| `outcome_name` | 源站原始字段(见同目录样本) | Arsenal | 空=源站未提供 |
| `outcome_description` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `point` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `price` | 源站原始字段(见同目录样本) | 1.41 | 空=源站未提供 |
| `raw_odds_format` | 源站原始字段(见同目录样本) | decimal | 空=源站未提供 |
| `normalized_decimal_odds` | 源站原始字段(见同目录样本) | 1.41 | 空=源站未提供 |
| `source_sid` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_link` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_bet_limit` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `rotation_number` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-09 | 空=源站未提供 |
| `raw_response_hash` | 源站原始字段(见同目录样本) | 71d7c0fa7e3bba11e1d40abe736f… | 空=源站未提供 |
| `source_endpoint` | 源站原始字段(见同目录样本) | https://api.the-odds-api.com… | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `snapshot_timestamp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `snapshot_previous_timestamp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `snapshot_next_timestamp` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | The Odds API | 空=未标注 |

### theodds_api_raw_responses

- 全库行数: 88   样本: 88 行 -> `samples/theodds_api_raw_responses.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `observation_id` | 源站原始字段(见同目录样本) | 16be2a3acdf4f1006d1c84651f2e… | 空=源站未提供 |
| `provider` | 赔率来源公司/源站 | The Odds API | 空=未标注 |
| `endpoint` | 源站原始字段(见同目录样本) | /sports/soccer_epl/odds/ | 空=源站未提供 |
| `request_url` | 源站原始字段(见同目录样本) | https://api.the-odds-api.com… | 空=源站未提供 |
| `request_params_sanitized` | 源站原始字段(见同目录样本) | {"bookmakers":"bet365,betfai… | 空=源站未提供 |
| `source_event_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `sport_key` | 源站原始字段(见同目录样本) | soccer_epl | 空=源站未提供 |
| `request_started_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:14Z | 空=源站未提供 |
| `observed_at_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `http_status` | 源站原始字段(见同目录样本) | 200 | 空=源站未提供 |
| `quota_remaining` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `quota_used` | 源站原始字段(见同目录样本) | 499 | 空=源站未提供 |
| `quota_last` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `etag` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `last_modified` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `content_type` | 源站原始字段(见同目录样本) | application/json; charset=ut… | 空=源站未提供 |
| `source_version` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `source_version_note` | 源站原始字段(见同目录样本) | The Odds API 未提供官方报价版本号；本地 s… | 空=源站未提供 |
| `raw_sha256` | 源站原始字段(见同目录样本) | 71d7c0fa7e3bba11e1d40abe736f… | 空=源站未提供 |
| `response_bytes` | 源站原始字段(见同目录样本) | 25948 | 空=源站未提供 |
| `raw_response` | 源站原始字段(见同目录样本) | [{"id":"b870dcfba5e5920d3f15… | 空=源站未提供 |
| `first_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `last_seen_utc` | 源站原始字段(见同目录样本) | 2026-10-09T02:14:17Z | 空=源站未提供 |
| `observation_count` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |

### theodds_fixtures

- 全库行数: 49,560   样本: 100 行 -> `samples/theodds_fixtures.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 225994 | 不应为空 |
| `source` | 源站原始字段(见同目录样本) | pinnacle | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | soccer | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Paraguay - Reserve League | 空=源站未标注 |
| `home_team` | 主队名称 | Deportivo Recoleta | 空=源站未覆盖 |
| `away_team` | 客队名称 | Sportivo Ameliano | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-30T10:30:00Z | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `pinn_id` | 源站原始字段(见同目录样本) | 1639289890 | 空=源站未提供 |
| `op_event_id` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-30 05:10:37 | 空=历史回填无时间戳 |

### theodds_odds

- 全库行数: 426,530   样本: 100 行 -> `samples/theodds_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2102401 | 不应为空 |
| `fixture_id` | 源站原始字段(见同目录样本) | 222197 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | pinnacle | 空=源站未提供 |
| `bookmaker` | 赔率来源公司/源站 | pinnacle | 空=未标注 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `period` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `price` | 源站原始字段(见同目录样本) | 104.0 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 4.5 | 空=无亚盘 |
| `max_bet` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-10-30T13:10:37 | 空=历史回填无时间戳 |

### theodds_odds_history

- 全库行数: 2,102,401   样本: 100 行 -> `samples/theodds_odds_history.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2102401 | 不应为空 |
| `fixture_id` | 源站原始字段(见同目录样本) | 222197 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | pinnacle | 空=源站未提供 |
| `bookmaker` | 赔率来源公司/源站 | pinnacle | 空=未标注 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | under | 空=源站未提供 |
| `price` | 源站原始字段(见同目录样本) | 104.0 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 4.5 | 空=无亚盘 |
| `recorded_at` | 源站原始字段(见同目录样本) | 2026-10-30T13:10:37 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-30 | 空=源站未提供 |

### titan007_1x2_odds

- 全库行数: 21,546   样本: 100 行 -> `samples/titan007_1x2_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 32153 | 不应为空 |
| `match_id` | 比赛ID(源站) | 2607481 | 空=源站未提供 |
| `company` | 赔率来源公司/源站 | Pinnacle | 空=未标注 |
| `open_home` | 源站原始字段(见同目录样本) | 1.12 | 空=源站未提供 |
| `open_draw` | 源站原始字段(见同目录样本) | 9.13 | 空=源站未提供 |
| `open_away` | 源站原始字段(见同目录样本) | 15.26 | 空=源站未提供 |
| `close_home` | 源站原始字段(见同目录样本) | 1.12 | 空=源站未提供 |
| `close_draw` | 源站原始字段(见同目录样本) | 9.5 | 空=源站未提供 |
| `close_away` | 源站原始字段(见同目录样本) | 26.0 | 空=源站未提供 |
| `close_return_rate` | 源站原始字段(见同目录样本) | 96.47 | 空=源站未提供 |
| `kelly_home` | 源站原始字段(见同目录样本) | 0.95 | 空=源站未提供 |
| `kelly_draw` | 源站原始字段(见同目录样本) | 1.0 | 空=源站未提供 |
| `kelly_away` | 源站原始字段(见同目录样本) | 1.22 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-07 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-07 05:09:06 | 空=历史回填无时间戳 |

### titan007_handicap_odds

- 全库行数: 17,057   样本: 100 行 -> `samples/titan007_handicap_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 19971 | 不应为空 |
| `match_id` | 比赛ID(源站) | 2999955 | 空=源站未提供 |
| `company` | 赔率来源公司/源站 | Pinnacle | 空=未标注 |
| `open_home` | 源站原始字段(见同目录样本) | 0.89 | 空=源站未提供 |
| `open_line` | 源站原始字段(见同目录样本) | -1.25 | 空=源站未提供 |
| `open_away` | 源站原始字段(见同目录样本) | 0.88 | 空=源站未提供 |
| `close_home` | 源站原始字段(见同目录样本) | 1.02 | 空=源站未提供 |
| `close_line` | 源站原始字段(见同目录样本) | -1.25 | 空=源站未提供 |
| `close_away` | 源站原始字段(见同目录样本) | 0.84 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-06 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-05 19:22:02 | 空=历史回填无时间戳 |

### titan007_match_history

- 全库行数: 1,645,374   样本: 100 行 -> `samples/titan007_match_history.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 1646067 | 不应为空 |
| `match_date` | 源站原始字段(见同目录样本) | 2025-12-25 | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 2914982 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | 日大学女锦 | 空=源站未标注 |
| `match_time` | 开赛时间 | 26日10:00 | UTC或源站时区，需按README时区说明换算 |
| `home_team` | 主队名称 | 早稻田大学女足 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 大阪体育大学女足 | 空=源站未覆盖 |
| `home_score` | 主队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `ht_home_score` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `ht_away_score` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `handicap_line` | 源站原始字段(见同目录样本) | 1.75 | 空=源站未提供 |
| `handicap_label` | 源站原始字段(见同目录样本) | 球半/两球 | 空=源站未提供 |
| `total_line` | 大小球盘口线 | 3 | 空=无大小球 |
| `total_label` | 源站原始字段(见同目录样本) | 3 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-07-27 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-07-26 23:01:28 | 空=历史回填无时间戳 |

### titan007_totals_odds

- 全库行数: 17,058   样本: 100 行 -> `samples/titan007_totals_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 19166 | 不应为空 |
| `match_id` | 比赛ID(源站) | 2999953 | 空=源站未提供 |
| `company` | 赔率来源公司/源站 | Pinnacle | 空=未标注 |
| `open_over` | 源站原始字段(见同目录样本) | 0.79 | 空=源站未提供 |
| `open_line` | 源站原始字段(见同目录样本) | 2.25 | 空=源站未提供 |
| `open_under` | 源站原始字段(见同目录样本) | 0.97 | 空=源站未提供 |
| `close_over` | 源站原始字段(见同目录样本) | 0.91 | 空=源站未提供 |
| `close_line` | 源站原始字段(见同目录样本) | 3.0 | 空=源站未提供 |
| `close_under` | 源站原始字段(见同目录样本) | 0.93 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-08-06 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-08-05 18:04:06 | 空=历史回填无时间戳 |

### transfermarkt_squad_values

- 全库行数: 203   样本: 100 行 -> `samples/transfermarkt_squad_values.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 9048 | 不应为空 |
| `season` | 赛季标识 | 2025 | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | Portugal - Primeira Liga | 空=源站未标注 |
| `team` | 源站原始字段(见同目录样本) | CS Marítimo | 空=源站未提供 |
| `squad_size` | 源站原始字段(见同目录样本) | 30 | 空=源站未提供 |
| `avg_age` | 源站原始字段(见同目录样本) | 25.2 | 空=源站未提供 |
| `total_value` | 源站原始字段(见同目录样本) | €559k | 空=源站未提供 |
| `total_value_eur` | 源站原始字段(见同目录样本) | 559000.0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-09-19 | 空=源站未提供 |

### under_shadow_bets

- 全库行数: 3,027   样本: 100 行 -> `samples/under_shadow_bets.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 13490 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 82fd798661b5 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | France - Ligue 2 | 空=源站未标注 |
| `home_team` | 主队名称 | 克莱蒙 | 空=源站未覆盖 |
| `away_team` | 客队名称 | 甘冈 | 空=源站未覆盖 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T18:00:00Z | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | total | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 | 2.5 | 空=无亚盘 |
| `best_odds` | 源站原始字段(见同目录样本) | 1.885 | 空=源站未提供 |
| `model_prob` | 源站原始字段(见同目录样本) | 0.6235 | 空=源站未提供 |
| `kelly_fraction` | 源站原始字段(见同目录样本) | 0.0495 | 空=源站未提供 |
| `hit_score` | 源站原始字段(见同目录样本) | 0.739 | 空=源站未提供 |
| `status` | 比赛状态 | pending | 空=未知 |
| `profit_loss` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-23T07:01:50 | 空=历史回填无时间戳 |

### understat_matches

- 全库行数: 12,174   样本: 100 行 -> `samples/understat_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 58204 | 不应为空 |
| `us_match_id` | 源站原始字段(见同目录样本) | 28776 | 空=源站未提供 |
| `league` | 联赛/赛事名称 | RFPL | 空=源站未标注 |
| `season` | 赛季标识 | 2025 | 空=源站未提供 |
| `home_team` | 主队名称 | FC Krasnodar | 空=源站未覆盖 |
| `away_team` | 客队名称 | FC Orenburg | 空=源站未覆盖 |
| `match_datetime` | 源站原始字段(见同目录样本) | 2026-05-17 15:00:00 | 空=源站未提供 |
| `home_goals` | 主队进球(全场) | 3 | 空=未开赛或源站未覆盖，不是0 |
| `away_goals` | 客队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `home_xg` | 预期进球xG | 1.57545 | 空=源站无xG |
| `away_xg` | 预期进球xG | 0.471873 | 空=源站无xG |
| `home_xga` | 源站原始字段(见同目录样本) | 0.471873 | 空=源站未提供 |
| `away_xga` | 源站原始字段(见同目录样本) | 1.57545 | 空=源站未提供 |
| `is_result` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-07-12 | 空=源站未提供 |

### understat_team_stats

- 全库行数: 678   样本: 100 行 -> `samples/understat_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 3222 | 不应为空 |
| `league` | 联赛/赛事名称 | RFPL | 空=源站未标注 |
| `season` | 赛季标识 | 2025 | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Dynamo Makhachkala | 空=源站未提供 |
| `matches` | 源站原始字段(见同目录样本) | 30 | 空=源站未提供 |
| `wins` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `draws` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `losses` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `scored` | 源站原始字段(见同目录样本) | 19 | 空=源站未提供 |
| `missed` | 源站原始字段(见同目录样本) | 37 | 空=源站未提供 |
| `xg` | 预期进球xG | 30.28 | 空=源站无xG |
| `xga` | 源站原始字段(见同目录样本) | 30.71 | 空=源站未提供 |
| `npxg` | 源站原始字段(见同目录样本) | 25.62 | 空=源站未提供 |
| `npxga` | 源站原始字段(见同目录样本) | 26.18 | 空=源站未提供 |
| `ppda` | 源站原始字段(见同目录样本) | 197.8 | 空=源站未提供 |
| `deep` | 源站原始字段(见同目录样本) | 139.0 | 空=源站未提供 |
| `pts` | 源站原始字段(见同目录样本) | 26 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-07-12 | 空=源站未提供 |

### understat_xg_matches

- 全库行数: 5,976   样本: 100 行 -> `samples/understat_xg_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 136413 | 不应为空 |
| `match_id` | 比赛ID(源站) | 30769 | 空=源站未提供 |
| `league_slug` | 源站原始字段(见同目录样本) | rfpl | 空=源站未提供 |
| `season` | 赛季标识 | 2026 | 空=源站未提供 |
| `home_team` | 主队名称 | FK Akhmat | 空=源站未覆盖 |
| `away_team` | 客队名称 | CSKA Moscow | 空=源站未覆盖 |
| `home_goals` | 主队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `away_goals` | 客队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `home_xg` | 预期进球xG | 0.0 | 空=源站无xG |
| `away_xg` | 预期进球xG | 0.0 | 空=源站无xG |
| `match_date` | 源站原始字段(见同目录样本) | 2027-05-29 15:00:00 | 空=源站未提供 |
| `is_result` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |

### understat_xg_teams

- 全库行数: 336   样本: 100 行 -> `samples/understat_xg_teams.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 7414 | 不应为空 |
| `league_slug` | 源站原始字段(见同目录样本) | rfpl | 空=源站未提供 |
| `season` | 赛季标识 | 2026 | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Rodina | 空=源站未提供 |
| `matches_played` | 源站原始字段(见同目录样本) | 11 | 空=源站未提供 |
| `xg_off` | 源站原始字段(见同目录样本) | 0.9144 | 空=源站未提供 |
| `xg_def` | 源站原始字段(见同目录样本) | 2.2263 | 空=源站未提供 |
| `npxg_off` | 源站原始字段(见同目录样本) | 0.9144 | 空=源站未提供 |
| `npxg_def` | 源站原始字段(见同目录样本) | 2.0206 | 空=源站未提供 |
| `update_time` | 源站原始字段(见同目录样本) | 2026-10-20 | 空=源站未提供 |

### unified_matches

- 全库行数: 74,621   样本: 100 行 -> `samples/unified_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 520659 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | a943acb3ae37 | 空=源站未提供 |
| `sport_code` | 源站原始字段(见同目录样本) | football | 空=源站未提供 |
| `league_code` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `league_name` | 联赛/赛事名称 | 瓦尔基里杯 2026 (8分钟) | 空=源站未标注 |
| `home_team_std` | 源站原始字段(见同目录样本) | 曼联 | 空=源站未提供 |
| `away_team_std` | 源站原始字段(见同目录样本) | 切尔西 | 空=源站未提供 |
| `kickoff_utc` | 源站原始字段(见同目录样本) | 2026-10-23T06:31:00 | 空=源站未提供 |
| `status` | 比赛状态 | NS | 空=未知 |
| `home_score` | 主队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) |  | 空=未开赛或源站未覆盖，不是0 |
| `source_count` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `sources_json` | 源站原始字段(见同目录样本) | {"qiety_yb": "5799139"} | 空=源站未提供 |
| `last_updated` | 源站原始字段(见同目录样本) | 2026-10-23T14:42:25 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `home_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `away_score_ht` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |

### unified_odds

- 全库行数: 560,846   样本: 100 行 -> `samples/unified_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 2960734 | 不应为空 |
| `unified_id` | 源站原始字段(见同目录样本) | 02e96dae3285 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | fd_pinnacle | 空=源站未提供 |
| `market` | 源站原始字段(见同目录样本) | moneyline | 空=源站未提供 |
| `outcome` | 源站原始字段(见同目录样本) | away | 空=源站未提供 |
| `odds_value` | 源站原始字段(见同目录样本) | 2.5 | 空=源站未提供 |
| `weight` | 源站原始字段(见同目录样本) | 0.78 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-23 | 空=源站未提供 |
| `handicap` | 亚洲让球盘口线 |  | 空=无亚盘 |

### wc2026_group_standings

- 全库行数: 48   样本: 48 行 -> `samples/wc2026_group_standings.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 96 | 不应为空 |
| `group_letter` | 源站原始字段(见同目录样本) | L | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Panama | 空=源站未提供 |
| `played` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `won` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `drawn` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `lost` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `gf` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `ga` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `gd` | 源站原始字段(见同目录样本) | -2 | 空=源站未提供 |
| `points` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `xg_for` | 源站原始字段(见同目录样本) | 0.75 | 空=源站未提供 |
| `xg_against` | 源站原始字段(见同目录样本) | 2.3 | 空=源站未提供 |
| `form` | 源站原始字段(见同目录样本) | LL | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-06-26T17:35:07 | 空=历史回填无时间戳 |

### wc2026_groups

- 全库行数: 12   样本: 12 行 -> `samples/wc2026_groups.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `group_id` | 源站原始字段(见同目录样本) | A | 空=源站未提供 |
| `team1` | 源站原始字段(见同目录样本) | Mexico | 空=源站未提供 |
| `team2` | 源站原始字段(见同目录样本) | South Africa | 空=源站未提供 |
| `team3` | 源站原始字段(见同目录样本) | South Korea | 空=源站未提供 |
| `team4` | 源站原始字段(见同目录样本) | Czech Republic | 空=源站未提供 |

### wc2026_h2h

- 全库行数: 48   样本: 48 行 -> `samples/wc2026_h2h.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 48 | 不应为空 |
| `home_team` | 主队名称 | Colombia | 空=源站未覆盖 |
| `away_team` | 客队名称 | DR Congo | 空=源站未覆盖 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-06-24 | 空=源站未提供 |
| `competition` | 源站原始字段(见同目录样本) | FIFA World Cup | 空=源站未提供 |
| `home_score` | 主队进球(全场) | 1 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `home_xg` | 预期进球xG |  | 空=源站无xG |
| `away_xg` | 预期进球xG |  | 空=源站无xG |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-06-24 | 空=源站未提供 |

### wc2026_match_events

- 全库行数: 258   样本: 100 行 -> `samples/wc2026_match_events.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 258 | 不应为空 |
| `event_id` | 源站原始字段(见同目录样本) | 258 | 空=源站未提供 |
| `match_id` | 比赛ID(源站) | 44 | 空=源站未提供 |
| `minute` | 源站原始字段(见同目录样本) | 82 | 空=源站未提供 |
| `event_type` | 源站原始字段(见同目录样本) | Goal | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 38 | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Algeria | 空=源站未提供 |
| `player_id` | 源站原始字段(见同目录样本) | 971 | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-06-22 | 空=源站未提供 |

### wc2026_match_team_stats

- 全库行数: 88   样本: 88 行 -> `samples/wc2026_match_team_stats.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 88 | 不应为空 |
| `match_id` | 比赛ID(源站) | 44 | 空=源站未提供 |
| `team_id` | 源站原始字段(见同目录样本) | 38 | 空=源站未提供 |
| `team_name` | 源站原始字段(见同目录样本) | Algeria | 空=源站未提供 |
| `match_date` | 源站原始字段(见同目录样本) | 2026-06-22 | 空=源站未提供 |
| `opponent_name` | 源站原始字段(见同目录样本) | Jordan | 空=源站未提供 |
| `is_home` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `total_shots` | 源站原始字段(见同目录样本) | 18 | 空=源站未提供 |
| `shots_on_target` | 源站原始字段(见同目录样本) | 6 | 空=源站未提供 |
| `corners` | 角球数 | 7 | 空=源站未覆盖角球 |
| `fouls` | 源站原始字段(见同目录样本) | 9 | 空=源站未提供 |
| `offsides` | 源站原始字段(见同目录样本) | 2 | 空=源站未提供 |
| `saves` | 源站原始字段(见同目录样本) | 1 | 空=源站未提供 |
| `home_xg` | 预期进球xG | 0.88 | 空=源站无xG |
| `away_xg` | 预期进球xG | 1.92 | 空=源站无xG |
| `home_score` | 主队进球(全场) | 1 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `data_source` | 源站原始字段(见同目录样本) | fifa.com | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-06-24 | 空=历史回填无时间戳 |

### wc2026_matches

- 全库行数: 70   样本: 70 行 -> `samples/wc2026_matches.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `match_id` | 比赛ID(源站) | wc2026_0001 | 空=源站未提供 |
| `group_id` | 源站原始字段(见同目录样本) | A | 空=源站未提供 |
| `home_team` | 主队名称 | Mexico | 空=源站未覆盖 |
| `away_team` | 客队名称 | South Africa | 空=源站未覆盖 |
| `kickoff_bj` | 源站原始字段(见同目录样本) | 2026-06-12 03:00 | 空=源站未提供 |
| `utc_offset` | 源站原始字段(见同目录样本) | UTC-6 | 空=源站未提供 |
| `venue` | 源站原始字段(见同目录样本) | Mexico City | 空=源站未提供 |
| `status` | 比赛状态 | FT | 空=未知 |
| `home_score` | 主队进球(全场) | 2 | 空=未开赛或源站未覆盖，不是0 |
| `away_score` | 客队进球(全场) | 0 | 空=未开赛或源站未覆盖，不是0 |
| `ht_home` | 主队半场进球 | 1 | 空=无半场数据 |
| `ht_away` | 客队半场进球 | 0 | 空=无半场数据 |
| `competition` | 源站原始字段(见同目录样本) | FIFA World Cup 2026 | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-06-26T17:35:07 | 空=历史回填无时间戳 |

### wc2026_teams

- 全库行数: 48   样本: 48 行 -> `samples/wc2026_teams.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `team_name` | 源站原始字段(见同目录样本) | Mexico | 空=源站未提供 |
| `group_id` | 源站原始字段(见同目录样本) | A | 空=源站未提供 |
| `competition` | 源站原始字段(见同目录样本) | FIFA World Cup 2026 | 空=源站未提供 |
| `updated_at` | 抓取/写入时间 | 2026-06-12 18:08:53 | 空=历史回填无时间戳 |
| `manager_name` | 源站原始字段(见同目录样本) | Javier Aguirre | 空=源站未提供 |
| `elo_rating_pretournament` | 源站原始字段(见同目录样本) | 1810 | 空=源站未提供 |
| `fifa_ranking_pretournament` | 源站原始字段(见同目录样本) | 14 | 空=源站未提供 |
| `confederation` | 源站原始字段(见同目录样本) | CONCACAF | 空=源站未提供 |
| `fifa_code` | 源站原始字段(见同目录样本) | MEX | 空=源站未提供 |

### yb_corner_odds

- 全库行数: 658   样本: 100 行 -> `samples/yb_corner_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 682 | 不应为空 |
| `match_id` | 比赛ID(源站) | 1579586 | 空=源站未提供 |
| `chpid` | 源站原始字段(见同目录样本) | 114 | 空=源站未提供 |
| `market_type` | 源站原始字段(见同目录样本) | corner_over_under_ft | 空=源站未提供 |
| `hlf` | 源站原始字段(见同目录样本) | 0 | 空=源站未提供 |
| `hv` | 源站原始字段(见同目录样本) | 9.5 | 空=源站未提供 |
| `ott` | 源站原始字段(见同目录样本) | 小  | 空=源站未提供 |
| `odds` | 源站原始字段(见同目录样本) | 1.9 | 空=源站未提供 |
| `ov2` | 源站原始字段(见同目录样本) |  | 空=源站未提供 |
| `fetched_at` | 源站原始字段(见同目录样本) | 2026-06-17 14:02:35 | 空=源站未提供 |
| `source` | 源站原始字段(见同目录样本) | scoremer | 空=源站未提供 |

### yb_correct_score_odds

- 全库行数: 369,031   样本: 100 行 -> `samples/yb_correct_score_odds.csv`

| 字段名 | 中文含义 | 示例(真实样本) | 空值含义 |
|---|---|---|---|
| `id` | 记录主键 | 428126 | 不应为空 |
| `match_id` | 比赛ID(源站) | 5763528 | 空=源站未提供 |
| `correct_score` | 源站原始字段(见同目录样本) | 3-4 | 空=源站未提供 |
| `decimal_odds` | 源站原始字段(见同目录样本) | 85.0 | 空=源站未提供 |
| `fetch_date` | 源站原始字段(见同目录样本) | 2026-10-12 | 空=源站未提供 |
| `created_at` | 抓取/写入时间 | 2026-10-12 04:46:08 | 空=历史回填无时间戳 |
