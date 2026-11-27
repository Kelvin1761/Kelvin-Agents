# 網球數據完整性審計

日期：2026-11-27。生產 DB 唯讀；日期以本機日曆日計。

## 1. 來源新鮮度

最新日期採用資料日期；7／30 日採用新增時間（有 created_at 時），否則使用資料日期。窗口包括今日。⚠ 表示 7 日零行但 30 日有行。

| 表 | 來源 | 資料日期／新增欄 | 最新 | 落後日 | 7日 | 30日 | 標記 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| raw_api_responses | bsd_tennis | fetched_at/created_at | 2026-05-08 | 203 | 0 | 0 |  |
| raw_api_responses | composite | fetched_at/created_at | 2026-11-26 | 1 | 208 | 898 |  |
| raw_api_responses | curated_tournament_metadata | fetched_at/created_at | 2026-11-26 | 1 | 24 | 103 |  |
| raw_api_responses | jeff_sackmann | fetched_at/created_at | 2026-06-02 | 178 | 0 | 0 |  |
| raw_api_responses | jeff_sackmann_elo | fetched_at/created_at | 2026-11-26 | 1 | 24 | 103 |  |
| raw_api_responses | mock | fetched_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| raw_api_responses | sportsbet | fetched_at/created_at | 2026-11-26 | 1 | 951 | 4103 |  |
| raw_api_responses | tennis_wc_pipeline | fetched_at/created_at | 2026-11-26 | 1 | 24 | 309 |  |
| raw_api_responses | tennisexplorer | fetched_at/created_at | 2026-11-26 | 1 | 6 | 28 |  |
| raw_api_responses | tennismylife_history | fetched_at/created_at | 2026-11-26 | 1 | 26 | 104 |  |
| raw_api_responses | wta_official_stats | fetched_at/created_at | 2026-11-05 | 22 | 0 | 48 | ⚠ |
| provider_entities | bsd_tennis | created_at/created_at | 2026-05-08 | 203 | 0 | 0 |  |
| provider_entities | composite | created_at/created_at | 2026-11-23 | 4 | 55 | 3525 |  |
| provider_entities | healer | created_at/created_at | 2026-05-10 | 201 | 0 | 0 |  |
| provider_entities | jeff_sackmann | created_at/created_at | 2026-06-02 | 178 | 0 | 0 |  |
| provider_entities | mock | created_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| provider_entities | sportsbet | created_at/created_at | 2026-11-26 | 1 | 276 | 1229 |  |
| provider_entities | tennismylife_history | created_at/created_at | 2026-11-26 | 1 | 44 | 44 |  |
| players | bsd_tennis | created_at/created_at | 2026-05-08 | 203 | 0 | 0 |  |
| players | composite | created_at/created_at | 2026-11-23 | 4 | 34 | 729 |  |
| players | jeff_sackmann | created_at/created_at | 2026-06-02 | 178 | 0 | 0 |  |
| players | mock | created_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| players | sportsbet | created_at/created_at | 2026-11-26 | 1 | 216 | 932 |  |
| players | tennisexplorer | created_at/created_at | 2026-11-26 | 1 | 31 | 405 |  |
| players | tennismylife_history | created_at/created_at | 2026-10-26 | 32 | 0 | 0 |  |
| tournaments | bsd_tennis | created_at/created_at | 2026-05-08 | 203 | 0 | 0 |  |
| tournaments | composite | created_at/created_at | 2026-11-21 | 6 | 1 | 11 |  |
| tournaments | healer | created_at/created_at | 2026-05-10 | 201 | 0 | 0 |  |
| tournaments | jeff_sackmann | created_at/created_at | 2026-06-02 | 178 | 0 | 0 |  |
| tournaments | mock | created_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| tournaments | sportsbet | created_at/created_at | 2026-11-26 | 1 | 48 | 245 |  |
| tournaments | tennismylife_history | created_at/created_at | 2026-11-26 | 1 | 27 | 27 |  |
| matches | bsd_tennis | match_date/created_at | 2026-05-10 | 201 | 0 | 0 |  |
| matches | composite | match_date/created_at | 2026-11-27 | 0 | 33 | 418 |  |
| matches | mock | match_date/created_at | 2026-08-30 | 89 | 0 | 0 |  |
| matches | sportsbet | match_date/created_at | 2026-11-27 | 0 | 564 | 2378 |  |
| odds_snapshots | mock | fetched_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| odds_snapshots | sportsbet | fetched_at/created_at | 2026-11-26 | 1 | 1695 | 6772 |  |
| player_match_history | composite | match_date/created_at | 2026-11-26 | 1 | 70 | 972 |  |
| player_match_history | jeff_sackmann | match_date/created_at | 2026-05-18 | 193 | 0 | 0 |  |
| player_match_history | mock | match_date/created_at | 2026-04-20 | 221 | 0 | 0 |  |
| player_match_history | tennisexplorer | match_date/created_at | 2026-11-25 | 2 | 1558 | 12584 |  |
| player_match_history | tennismylife_history | match_date/created_at | 2026-11-22 | 5 | 21416 | 21418 |  |
| rankings_history | atp_official_numeric_pdf | ranking_date/created_at | 2026-11-23 | 4 | 2319 | 9194 |  |
| rankings_history | composite | ranking_date/created_at | 2026-10-30 | 28 | 0 | 2153 | ⚠ |
| rankings_history | jeff_sackmann | ranking_date/created_at | 2026-05-18 | 193 | 0 | 0 |  |
| rankings_history | mock | ranking_date/created_at | 2026-08-30 | 89 | 0 | 0 |  |
| rankings_history | tennismylife_history | ranking_date/created_at | 2026-11-22 | 5 | 1081 | 1081 |  |
| rankings_history | wta_numeric_pdf | ranking_date/created_at | 2026-11-09 | 18 | 0 | 3055 | ⚠ |
| rankings_history | wta_ranked_players_api | ranking_date/created_at | 2026-11-23 | 4 | 1515 | 7635 |  |
| tournament_levels | bsd_tennis | created_at/created_at | 2026-05-08 | 203 | 0 | 0 |  |
| tournament_levels | competition_name_heuristic | created_at/created_at | 2026-11-26 | 1 | 27 | 163 |  |
| tournament_levels | composite | created_at/created_at | 2026-11-21 | 6 | 1 | 11 |  |
| tournament_levels | curated_tournament_metadata | created_at/created_at | 2026-10-29 | 29 | 0 | 1 | ⚠ |
| tournament_levels | jeff_sackmann | created_at/created_at | 2026-06-02 | 178 | 0 | 0 |  |
| tournament_levels | mock | created_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| tournament_levels | sportsbet | created_at/created_at | 2026-11-26 | 1 | 48 | 245 |  |
| tournament_levels | tennisdata_tournament_index | created_at/created_at | 2026-11-07 | 20 | 0 | 4 | ⚠ |
| tournament_levels | tennismylife_history | created_at/created_at | 2026-11-26 | 1 | 27 | 27 |  |
| player_opponent_rank_bucket_stats | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 8981 | 37191 |  |
| player_tournament_level_stats | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 1275 | 5284 |  |
| player_round_stats | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 1283 | 5358 |  |
| player_big_match_stats | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 1283 | 5313 |  |
| player_bo_format_stats | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 1283 | 5314 |  |
| feature_snapshots | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 1404 | 5844 |  |
| predictions | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 702 | 2919 |  |
| closing_odds_snapshots | mock | fetched_at/created_at | 2026-08-29 | 90 | 0 | 0 |  |
| closing_odds_snapshots | sportsbet | fetched_at/created_at | 2026-11-05 | 22 | 0 | 519 | ⚠ |
| match_results | composite | created_at/created_at | 2026-11-26 | 1 | 96 | 765 |  |
| match_results | composite_resolver | created_at/created_at | 2026-10-30 | 28 | 0 | 2 | ⚠ |
| match_results | local_history_resolver | created_at/created_at | 2026-11-04 | 23 | 0 | 5 | ⚠ |
| match_results | tennisexplorer | created_at/created_at | 2026-11-26 | 1 | 1235 | 3058 |  |
| match_results | tennismylife | created_at/created_at | 2026-11-26 | 1 | 255 | 829 |  |
| backtest_runs | (無來源欄) | created_at/created_at | 2026-06-17 | 163 | 0 | 0 |  |
| market_odds_snapshots | sportsbet | fetched_at/created_at | 2026-11-26 | 1 | 27244 | 132154 |  |
| market_predictions | (無來源欄) | created_at/created_at | 2026-11-04 | 23 | 0 | 13199 | ⚠ |
| clv_tracker | (無來源欄) | match_date/recorded_at | 2026-11-05 | 22 | 0 | 328 | ⚠ |
| combo_tracker | (無來源欄) | match_date/recorded_at | 2026-08-16 | 103 | 0 | 0 |  |
| prop_tracker | (無來源欄) | match_date/recorded_at | 2026-11-27 | 0 | 955 | 5819 |  |
| player_aliases | (無來源欄) | created_at/created_at | 2026-11-26 | 1 | 88 | 960 |  |
| player_elo_history | (無來源欄) | as_of_date/as_of_date | 2026-11-25 | 2 | 1338 | 12569 |  |
| prop_tracker_pre_rebuild | (無來源欄) | match_date/recorded_at | 2026-08-09 | 110 | 0 | 0 |  |
| player_elo_history_v2 | (無來源欄) | as_of_date/as_of_date | 2026-11-25 | 2 | 1338 | 12569 |  |
| prop_price_log | (無來源欄) | match_date/match_date | 2026-11-05 | 22 | 0 | 2666 | ⚠ |
| preclose_odds_snapshots | sportsbet | fetched_at/created_at | 2026-11-26 | 1 | 48 | 442 |  |
| preclose_market_odds_snapshots | sportsbet | fetched_at/created_at | 2026-11-26 | 1 | 5623 | 40389 |  |
| wta_match_stats | wta_official_stats | match_date/fetched_at | 2026-11-04 | 23 | 0 | 396 | ⚠ |
| fixture_observations | composite | observed_at/observed_at | 2026-11-26 | 1 | 81 | 949 |  |
| fixture_observations | sportsbet | observed_at/observed_at | 2026-11-26 | 1 | 1101 | 4298 |  |
| result_observations | composite | observed_at/observed_at | 2026-11-26 | 1 | 34 | 591 |  |
| result_observations | composite_resolver | observed_at/observed_at | 2026-10-30 | 28 | 0 | 2 | ⚠ |
| result_observations | local_history_resolver | observed_at/observed_at | 2026-11-04 | 23 | 0 | 5 | ⚠ |
| result_observations | tennisexplorer | observed_at/observed_at | 2026-11-26 | 1 | 526 | 2606 |  |
| result_observations | tennismylife | observed_at/observed_at | 2026-11-26 | 1 | 485 | 2765 |  |
| market_captures | sportsbet | captured_at/captured_at | 2026-11-26 | 1 | 2074 | 8622 |  |
| history_observations | (無來源欄) | observed_at/observed_at | 2026-11-26 | 1 | 41179 | 53109 |  |
| retained_payload_refs | (無來源欄) | archived_at/archived_at | 2026-11-26 | 1 | 465 | 1410 |  |
| featured_picks | (無來源欄) | match_date/featured_at | 2026-11-27 | 0 | 54 | 200 |  |
| featured_shadow_picks | (無來源欄) | match_date/featured_at | 2026-11-27 | 0 | 122 | 175 |  |
| betfair_markets | (無來源欄) | first_seen_at/first_seen_at | 2026-11-26 | 1 | 557 | 958 |  |
| betfair_price_snapshots | (無來源欄) | fetched_at/fetched_at | 2026-11-26 | 1 | 23135 | 37998 |  |
| sharp_forward_picks | (無來源欄) | match_date/match_date | 2026-11-27 | 0 | 40 | 47 |  |

## 2. 定價母體覆蓋率

每個球員取 created_at 最早快照（同時刻以 id 最小）。百分比分母為可解析快照；缺失快照及 JSON 無效另外列出。

| 週一 | 級別 | 球員場次 | 有效 | 缺快照 | 無效JSON | rank | elo | surface_elo_distinct | hold | break | bp | history10 | h2h | fatigue | surface | round |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-31 | CHALLENGER | 40 | 40 | 0 | 0 | 97.5% | 97.5% | 0.0% | 85.0% | 85.0% | 95.0% | 92.5% | 20.0% | 95.0% | 10.0% | 0.0% |
| 2026-08-31 | ITF | 456 | 442 | 14 | 0 | 56.8% | 61.5% | 0.0% | 0.0% | 0.0% | 21.7% | 41.4% | 5.9% | 48.4% | 0.0% | 0.0% |
| 2026-08-31 | TOUR | 32 | 24 | 0 | 8 | 91.7% | 91.7% | 91.7% | 79.2% | 79.2% | 91.7% | 25.0% | 58.3% | 91.7% | 100.0% | 0.0% |
| 2026-08-31 | UTR | 78 | 78 | 0 | 0 | 11.5% | 26.9% | 0.0% | 0.0% | 0.0% | 1.3% | 19.2% | 0.0% | 21.8% | 0.0% | 0.0% |
| 2026-08-31 | 未知 | 26 | 0 | 26 | 0 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 |
| 2026-09-07 | CHALLENGER | 84 | 38 | 22 | 24 | 100.0% | 100.0% | 23.7% | 76.3% | 76.3% | 94.7% | 89.5% | 15.8% | 100.0% | 0.0% | 0.0% |
| 2026-09-07 | ITF | 622 | 556 | 8 | 58 | 61.9% | 71.0% | 0.0% | 0.0% | 0.0% | 23.2% | 48.7% | 3.6% | 60.4% | 0.0% | 0.0% |
| 2026-09-07 | TOUR | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 100.0% | 50.0% | 50.0% | 100.0% | 50.0% | 100.0% | 100.0% | 100.0% | 0.0% |
| 2026-09-07 | UTR | 222 | 188 | 0 | 34 | 33.5% | 47.3% | 3.2% | 0.0% | 0.0% | 3.2% | 14.4% | 1.1% | 31.9% | 0.0% | 0.0% |
| 2026-09-07 | 未知 | 50 | 6 | 42 | 2 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 83.3% | 83.3% | 33.3% | 100.0% | 0.0% | 0.0% |
| 2026-09-14 | CHALLENGER | 142 | 114 | 28 | 0 | 97.4% | 97.4% | 0.0% | 86.0% | 86.0% | 89.5% | 90.4% | 15.8% | 94.7% | 0.0% | 0.0% |
| 2026-09-14 | ITF | 338 | 330 | 8 | 0 | 78.5% | 78.8% | 0.0% | 0.0% | 0.0% | 27.0% | 47.9% | 3.0% | 61.8% | 0.0% | 0.0% |
| 2026-09-14 | UTR | 198 | 198 | 0 | 0 | 26.8% | 43.9% | 7.1% | 0.0% | 0.0% | 1.0% | 5.6% | 4.0% | 32.3% | 0.0% | 0.0% |
| 2026-09-14 | 未知 | 234 | 186 | 18 | 30 | 91.4% | 93.5% | 0.0% | 0.0% | 0.0% | 81.2% | 89.8% | 11.8% | 93.0% | 0.0% | 0.0% |
| 2026-09-21 | CHALLENGER | 76 | 58 | 18 | 0 | 94.8% | 98.3% | 70.7% | 56.9% | 56.9% | 89.7% | 75.9% | 17.2% | 96.6% | 0.0% | 0.0% |
| 2026-09-21 | ITF | 366 | 332 | 34 | 0 | 72.9% | 75.3% | 0.0% | 0.0% | 0.0% | 13.3% | 45.5% | 2.4% | 52.4% | 0.0% | 0.0% |
| 2026-09-21 | TOUR | 22 | 22 | 0 | 0 | 86.4% | 86.4% | 81.8% | 27.3% | 27.3% | 72.7% | 72.7% | 18.2% | 86.4% | 100.0% | 0.0% |
| 2026-09-21 | UTR | 74 | 74 | 0 | 0 | 9.5% | 23.0% | 0.0% | 0.0% | 0.0% | 4.1% | 20.3% | 5.4% | 23.0% | 0.0% | 0.0% |
| 2026-09-21 | 未知 | 100 | 42 | 58 | 0 | 95.2% | 90.5% | 0.0% | 0.0% | 0.0% | 61.9% | 71.4% | 19.0% | 81.0% | 0.0% | 0.0% |
| 2026-09-28 | CHALLENGER | 88 | 78 | 10 | 0 | 96.2% | 96.2% | 0.0% ⚠ | 87.2% | 87.2% | 87.2% | 92.3% | 25.6% | 93.6% | 0.0% | 2.6% |
| 2026-09-28 | ITF | 238 | 212 | 26 | 0 | 73.6% | 78.8% | 0.0% | 0.0% | 0.0% | 17.5% | 49.1% | 0.9% | 55.7% | 0.0% | 0.0% |
| 2026-09-28 | TOUR | 32 | 32 | 0 | 0 | 90.6% | 87.5% | 75.0% | 15.6% | 15.6% | 62.5% | 46.9% | 25.0% | 84.4% | 100.0% | 0.0% |
| 2026-09-28 | UTR | 182 | 182 | 0 | 0 | 22.5% | 37.4% | 0.0% | 0.0% | 0.0% | 1.6% | 12.6% | 2.2% | 25.3% | 0.0% | 0.0% |
| 2026-09-28 | 未知 | 56 | 22 | 34 | 0 | 100.0% | 95.5% | 0.0% | 0.0% | 0.0% | 40.9% | 54.5% | 18.2% | 81.8% | 0.0% | 0.0% |
| 2026-10-05 | CHALLENGER | 96 | 88 | 8 | 0 | 97.7% | 97.7% | 0.0% ⚠ | 88.6% | 88.6% | 88.6% | 93.2% | 18.2% | 96.6% | 0.0% | 0.0% |
| 2026-10-05 | ITF | 296 | 278 | 18 | 0 | 73.0% | 79.9% | 0.0% | 0.0% | 0.0% | 20.1% | 50.7% | 2.9% | 60.8% | 0.0% | 0.0% |
| 2026-10-05 | TOUR | 32 | 32 | 0 | 0 | 96.9% | 93.8% | 93.8% | 46.9% | 46.9% | 87.5% | 71.9% | 18.8% | 96.9% | 100.0% | 0.0% |
| 2026-10-05 | UTR | 30 | 30 | 0 | 0 | 33.3% | 36.7% | 0.0% | 0.0% | 0.0% | 0.0% | 10.0% | 0.0% | 23.3% | 0.0% | 0.0% |
| 2026-10-05 | 未知 | 94 | 24 | 70 | 0 | 95.8% | 95.8% | 0.0% | 0.0% | 0.0% | 62.5% | 62.5% | 0.0% ⚠ | 91.7% | 0.0% | 0.0% |
| 2026-10-12 | CHALLENGER | 128 | 110 | 18 | 0 | 100.0% | 100.0% | 0.0% ⚠ | 97.3% | 97.3% | 99.1% | 100.0% | 45.5% | 100.0% | 0.0% | 0.0% |
| 2026-10-12 | ITF | 392 | 356 | 36 | 0 | 71.9% | 78.4% | 0.0% | 0.0% | 0.0% | 29.5% | 55.1% | 2.8% | 63.2% | 0.0% | 0.0% |
| 2026-10-12 | TOUR | 8 | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% | 25.0% | 25.0% | 87.5% | 62.5% | 25.0% | 100.0% | 100.0% | 0.0% |
| 2026-10-12 | UTR | 142 | 142 | 0 | 0 | 19.0% | 33.8% | 0.0% | 0.0% | 0.0% | 2.8% | 16.2% | 4.2% | 25.4% | 0.0% | 0.0% |
| 2026-10-12 | 未知 | 50 | 0 | 50 | 0 | 無 ⚠ | 無 ⚠ | 無 | 無 | 無 | 無 ⚠ | 無 ⚠ | 無 | 無 ⚠ | 無 | 無 |
| 2026-10-19 | CHALLENGER | 140 | 124 | 16 | 0 | 99.2% | 99.2% | 23.4% | 74.2% | 74.2% | 93.5% | 79.8% | 35.5% | 96.8% | 0.0% | 0.0% |
| 2026-10-19 | ITF | 462 | 432 | 30 | 0 | 68.3% | 73.1% | 0.0% | 0.0% | 0.0% | 21.5% | 48.1% | 6.0% | 61.1% | 0.0% | 0.0% |
| 2026-10-19 | TOUR | 12 | 12 | 0 | 0 | 91.7% | 91.7% | 83.3% | 0.0% ⚠ | 0.0% ⚠ | 75.0% | 58.3% | 0.0% ⚠ | 83.3% | 100.0% | 0.0% |
| 2026-10-19 | UTR | 78 | 78 | 0 | 0 | 24.4% | 48.7% | 0.0% | 0.0% | 0.0% | 0.0% | 14.1% | 2.6% | 32.1% | 0.0% | 0.0% |
| 2026-10-19 | 未知 | 50 | 2 | 48 | 0 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| 2026-10-26 | CHALLENGER | 226 | 166 | 30 | 30 | 97.0% | 98.2% | 28.3% | 79.5% | 79.5% | 90.4% | 87.3% | 18.1% | 96.4% | 0.0% | 6.0% |
| 2026-10-26 | ITF | 472 | 298 | 68 | 106 | 76.2% | 78.5% | 0.0% | 0.0% | 0.0% | 20.8% | 50.3% | 6.7% | 63.1% | 0.0% | 0.0% |
| 2026-10-26 | TOUR | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 50.0% ⚠ | 0.0% ⚠ | 0.0% ⚠ | 25.0% ⚠ | 25.0% ⚠ | 0.0% ⚠ | 75.0% ⚠ | 100.0% | 0.0% |
| 2026-10-26 | UTR | 96 | 58 | 0 | 38 | 27.6% | 25.9% | 0.0% | 0.0% | 0.0% | 0.0% | 13.8% | 0.0% | 17.2% | 0.0% | 0.0% |
| 2026-10-26 | 未知 | 66 | 8 | 56 | 2 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 12.5% | 37.5% | 0.0% | 100.0% | 0.0% | 0.0% |
| 2026-11-02 | CHALLENGER | 160 | 126 | 22 | 12 | 96.8% | 99.2% | 11.1% | 80.2% | 80.2% | 89.7% | 86.5% | 22.2% | 97.6% | 0.0% | 0.0% |
| 2026-11-02 | ITF | 374 | 286 | 38 | 50 | 81.5% | 81.8% | 0.0% | 0.0% | 0.0% | 12.9% | 48.3% | 7.0% | 60.5% | 0.0% | 0.0% |
| 2026-11-02 | UTR | 216 | 194 | 0 | 22 | 19.1% | 28.9% | 0.0% | 0.0% | 0.0% | 0.0% | 6.2% | 0.0% | 16.5% | 0.0% | 0.0% |
| 2026-11-02 | 未知 | 32 | 4 | 26 | 2 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 0.0% | 100.0% | 0.0% | 0.0% |
| 2026-11-09 | CHALLENGER | 318 | 170 | 32 | 116 | 97.6% | 98.2% | 16.5% | 85.3% | 85.3% | 92.4% | 92.9% | 17.6% | 97.6% | 0.0% | 0.0% |
| 2026-11-09 | ITF | 764 | 484 | 70 | 210 | 81.8% | 82.9% | 0.0% | 0.0% | 0.0% | 19.0% | 51.7% | 3.7% | 62.0% | 0.0% | 0.0% |
| 2026-11-09 | UTR | 146 | 44 | 2 | 100 | 15.9% | 18.2% ⚠ | 0.0% | 0.0% | 0.0% | 0.0% | 4.5% | 0.0% | 9.1% | 0.0% | 0.0% |
| 2026-11-09 | 未知 | 44 | 0 | 42 | 2 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | 無 |
| 2026-11-16 | CHALLENGER | 326 | 262 | 46 | 18 | 96.2% | 97.7% | 23.7% | 68.7% | 68.7% | 82.4% | 84.0% | 22.9% | 93.9% | 0.0% | 6.1% |
| 2026-11-16 | ITF | 666 | 554 | 52 | 60 | 75.1% | 77.6% | 0.0% | 0.0% | 0.0% | 20.6% | 52.2% | 3.6% | 60.5% | 0.0% | 0.0% |
| 2026-11-16 | UTR | 370 | 306 | 16 | 48 | 21.2% | 33.3% | 0.0% | 0.0% | 0.0% | 1.3% | 10.1% | 1.3% | 24.5% | 0.0% | 0.0% |
| 2026-11-16 | 未知 | 36 | 24 | 12 | 0 | 91.7% | 91.7% | 0.0% | 0.0% | 0.0% | 58.3% | 83.3% | 25.0% | 91.7% | 0.0% | 0.0% |
| 2026-11-23 | CHALLENGER | 312 | 254 | 58 | 0 | 96.1% | 96.1% | 0.8% ⚠ | 83.1% | 83.1% | 83.9% | 87.8% | 24.4% | 92.1% | 0.0% | 2.4% |
| 2026-11-23 | ITF | 488 | 388 | 100 | 0 | 80.7% | 80.9% | 0.0% | 0.0% | 0.0% | 12.1% | 49.0% | 3.1% | 63.7% | 0.0% | 0.0% |
| 2026-11-23 | UTR | 106 | 106 | 0 | 0 | 33.0% | 53.8% | 0.0% | 0.0% | 0.0% | 1.9% | 35.8% | 11.3% | 44.3% | 0.0% | 0.0% |
| 2026-11-23 | 未知 | 30 | 14 | 16 | 0 | 78.6% | 78.6% | 0.0% | 0.0% | 0.0% | 57.1% | 57.1% | 14.3% | 78.6% | 0.0% | 0.0% |

## 3. 球員往績新鮮度

每個球員場次及來源取比賽日前最近一場，僅計 ACTIVE 往績；無紀錄另列，>30 日比例以有往績者為分母；非當時已知資料的回溯審計。

| 週一 | 級別 | 來源 | 有往績球員場次 | 無往績 | 中位日數 | >30 日數 | >30 日比例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-31 | CHALLENGER | composite | 17 | 23 | 469 | 14 | 82.4% |
| 2026-08-31 | CHALLENGER | jeff_sackmann | 19 | 21 | 338 | 19 | 100.0% |
| 2026-08-31 | CHALLENGER | tennisexplorer | 33 | 7 | 1 | 0 | 0.0% |
| 2026-08-31 | CHALLENGER | tennismylife_history | 38 | 2 | 4.0 | 1 | 2.6% |
| 2026-08-31 | ITF | composite | 53 | 403 | 55 | 39 | 73.6% |
| 2026-08-31 | ITF | jeff_sackmann | 67 | 389 | 519 | 67 | 100.0% |
| 2026-08-31 | ITF | tennisexplorer | 181 | 275 | 1 | 16 | 8.8% |
| 2026-08-31 | ITF | tennismylife_history | 94 | 362 | 112.0 | 79 | 84.0% |
| 2026-08-31 | TOUR | composite | 20 | 12 | 1.0 | 0 | 0.0% |
| 2026-08-31 | TOUR | jeff_sackmann | 26 | 6 | 120.5 | 26 | 100.0% |
| 2026-08-31 | TOUR | tennisexplorer | 20 | 12 | 4.5 | 3 | 15.0% |
| 2026-08-31 | TOUR | tennismylife_history | 17 | 15 | 1 | 0 | 0.0% |
| 2026-08-31 | UTR | composite | 1 | 77 | 525 | 1 | 100.0% |
| 2026-08-31 | UTR | jeff_sackmann | 1 | 77 | 209 | 1 | 100.0% |
| 2026-08-31 | UTR | tennisexplorer | 17 | 61 | 2 | 1 | 5.9% |
| 2026-08-31 | UTR | tennismylife_history | 2 | 76 | 281.5 | 2 | 100.0% |
| 2026-08-31 | 未知 | composite | 0 | 26 | 無 | 0 | 無 |
| 2026-08-31 | 未知 | jeff_sackmann | 0 | 26 | 無 | 0 | 無 |
| 2026-08-31 | 未知 | tennisexplorer | 2 | 24 | 17.0 | 0 | 0.0% |
| 2026-08-31 | 未知 | tennismylife_history | 0 | 26 | 無 | 0 | 無 |
| 2026-09-07 | CHALLENGER | composite | 26 | 58 | 61.5 | 17 | 65.4% |
| 2026-09-07 | CHALLENGER | jeff_sackmann | 27 | 57 | 217 | 27 | 100.0% |
| 2026-09-07 | CHALLENGER | tennisexplorer | 60 | 24 | 2.5 | 7 | 11.7% |
| 2026-09-07 | CHALLENGER | tennismylife_history | 58 | 26 | 6.0 | 14 | 24.1% |
| 2026-09-07 | ITF | composite | 70 | 552 | 75.5 | 54 | 77.1% |
| 2026-09-07 | ITF | jeff_sackmann | 110 | 512 | 425.5 | 110 | 100.0% |
| 2026-09-07 | ITF | tennisexplorer | 307 | 315 | 1 | 28 | 9.1% |
| 2026-09-07 | ITF | tennismylife_history | 144 | 478 | 153.0 | 124 | 86.1% |
| 2026-09-07 | TOUR | composite | 1 | 1 | 1 | 0 | 0.0% |
| 2026-09-07 | TOUR | jeff_sackmann | 2 | 0 | 126.0 | 2 | 100.0% |
| 2026-09-07 | TOUR | tennisexplorer | 1 | 1 | 1 | 0 | 0.0% |
| 2026-09-07 | TOUR | tennismylife_history | 0 | 2 | 無 | 0 | 無 |
| 2026-09-07 | UTR | composite | 4 | 218 | 621.0 | 4 | 100.0% |
| 2026-09-07 | UTR | jeff_sackmann | 2 | 220 | 362.5 | 2 | 100.0% |
| 2026-09-07 | UTR | tennisexplorer | 77 | 145 | 1 | 10 | 13.0% |
| 2026-09-07 | UTR | tennismylife_history | 26 | 196 | 618.5 | 26 | 100.0% |
| 2026-09-07 | 未知 | composite | 7 | 43 | 1 | 0 | 0.0% |
| 2026-09-07 | 未知 | jeff_sackmann | 7 | 43 | 145 | 7 | 100.0% |
| 2026-09-07 | 未知 | tennisexplorer | 4 | 46 | 11.0 | 1 | 25.0% |
| 2026-09-07 | 未知 | tennismylife_history | 0 | 50 | 無 | 0 | 無 |
| 2026-09-14 | CHALLENGER | composite | 52 | 90 | 25.0 | 19 | 36.5% |
| 2026-09-14 | CHALLENGER | jeff_sackmann | 35 | 107 | 253 | 35 | 100.0% |
| 2026-09-14 | CHALLENGER | tennisexplorer | 95 | 47 | 2 | 12 | 12.6% |
| 2026-09-14 | CHALLENGER | tennismylife_history | 108 | 34 | 5.0 | 13 | 12.0% |
| 2026-09-14 | ITF | composite | 50 | 288 | 67.5 | 44 | 88.0% |
| 2026-09-14 | ITF | jeff_sackmann | 87 | 251 | 407 | 87 | 100.0% |
| 2026-09-14 | ITF | tennisexplorer | 167 | 171 | 2 | 36 | 21.6% |
| 2026-09-14 | ITF | tennismylife_history | 65 | 273 | 163 | 55 | 84.6% |
| 2026-09-14 | UTR | composite | 6 | 192 | 627.5 | 6 | 100.0% |
| 2026-09-14 | UTR | jeff_sackmann | 1 | 197 | 366 | 1 | 100.0% |
| 2026-09-14 | UTR | tennisexplorer | 66 | 132 | 2.0 | 9 | 13.6% |
| 2026-09-14 | UTR | tennismylife_history | 16 | 182 | 959.5 | 16 | 100.0% |
| 2026-09-14 | 未知 | composite | 132 | 102 | 20.0 | 27 | 20.5% |
| 2026-09-14 | 未知 | jeff_sackmann | 186 | 48 | 215.5 | 186 | 100.0% |
| 2026-09-14 | 未知 | tennisexplorer | 184 | 50 | 7.0 | 37 | 20.1% |
| 2026-09-14 | 未知 | tennismylife_history | 198 | 36 | 1.0 | 17 | 8.6% |
| 2026-09-21 | CHALLENGER | composite | 38 | 38 | 30.0 | 19 | 50.0% |
| 2026-09-21 | CHALLENGER | jeff_sackmann | 24 | 52 | 230.5 | 24 | 100.0% |
| 2026-09-21 | CHALLENGER | tennisexplorer | 49 | 27 | 6 | 10 | 20.4% |
| 2026-09-21 | CHALLENGER | tennismylife_history | 56 | 20 | 5.0 | 6 | 10.7% |
| 2026-09-21 | ITF | composite | 34 | 332 | 77.5 | 25 | 73.5% |
| 2026-09-21 | ITF | jeff_sackmann | 66 | 300 | 466.5 | 66 | 100.0% |
| 2026-09-21 | ITF | tennisexplorer | 151 | 215 | 1 | 31 | 20.5% |
| 2026-09-21 | ITF | tennismylife_history | 53 | 313 | 63 | 35 | 66.0% |
| 2026-09-21 | TOUR | composite | 13 | 9 | 2 | 0 | 0.0% |
| 2026-09-21 | TOUR | jeff_sackmann | 16 | 6 | 143.0 | 16 | 100.0% |
| 2026-09-21 | TOUR | tennisexplorer | 10 | 12 | 6.0 | 2 | 20.0% |
| 2026-09-21 | TOUR | tennismylife_history | 7 | 15 | 2 | 0 | 0.0% |
| 2026-09-21 | UTR | composite | 3 | 71 | 545 | 3 | 100.0% |
| 2026-09-21 | UTR | jeff_sackmann | 0 | 74 | 無 | 0 | 無 |
| 2026-09-21 | UTR | tennisexplorer | 17 | 57 | 1 | 0 | 0.0% |
| 2026-09-21 | UTR | tennismylife_history | 5 | 69 | 229 | 4 | 80.0% |
| 2026-09-21 | 未知 | composite | 23 | 77 | 21 | 4 | 17.4% |
| 2026-09-21 | 未知 | jeff_sackmann | 29 | 71 | 167 | 29 | 100.0% |
| 2026-09-21 | 未知 | tennisexplorer | 28 | 72 | 4.5 | 9 | 32.1% |
| 2026-09-21 | 未知 | tennismylife_history | 24 | 76 | 2.0 | 0 | 0.0% |
| 2026-09-28 | CHALLENGER | composite | 35 | 53 | 8 | 10 | 28.6% |
| 2026-09-28 | CHALLENGER | jeff_sackmann | 38 | 50 | 234.0 | 38 | 100.0% |
| 2026-09-28 | CHALLENGER | tennisexplorer | 65 | 23 | 7 | 15 | 23.1% |
| 2026-09-28 | CHALLENGER | tennismylife_history | 74 | 14 | 5.0 | 13 | 17.6% |
| 2026-09-28 | ITF | composite | 30 | 208 | 37.5 | 18 | 60.0% |
| 2026-09-28 | ITF | jeff_sackmann | 32 | 206 | 432.0 | 32 | 100.0% |
| 2026-09-28 | ITF | tennisexplorer | 107 | 131 | 1 | 13 | 12.1% |
| 2026-09-28 | ITF | tennismylife_history | 36 | 202 | 254.5 | 30 | 83.3% |
| 2026-09-28 | TOUR | composite | 16 | 16 | 12.0 | 0 | 0.0% |
| 2026-09-28 | TOUR | jeff_sackmann | 25 | 7 | 151 | 25 | 100.0% |
| 2026-09-28 | TOUR | tennisexplorer | 12 | 20 | 10.0 | 2 | 16.7% |
| 2026-09-28 | TOUR | tennismylife_history | 7 | 25 | 11 | 0 | 0.0% |
| 2026-09-28 | UTR | composite | 3 | 179 | 42 | 3 | 100.0% |
| 2026-09-28 | UTR | jeff_sackmann | 2 | 180 | 382.5 | 2 | 100.0% |
| 2026-09-28 | UTR | tennisexplorer | 47 | 135 | 1 | 0 | 0.0% |
| 2026-09-28 | UTR | tennismylife_history | 12 | 170 | 19.5 | 5 | 41.7% |
| 2026-09-28 | 未知 | composite | 11 | 45 | 6 | 0 | 0.0% |
| 2026-09-28 | 未知 | jeff_sackmann | 14 | 42 | 341.5 | 14 | 100.0% |
| 2026-09-28 | 未知 | tennisexplorer | 13 | 43 | 6 | 4 | 30.8% |
| 2026-09-28 | 未知 | tennismylife_history | 2 | 54 | 2.5 | 0 | 0.0% |
| 2026-10-05 | CHALLENGER | composite | 36 | 60 | 46.5 | 22 | 61.1% |
| 2026-10-05 | CHALLENGER | jeff_sackmann | 38 | 58 | 454.0 | 38 | 100.0% |
| 2026-10-05 | CHALLENGER | tennisexplorer | 79 | 17 | 3 | 11 | 13.9% |
| 2026-10-05 | CHALLENGER | tennismylife_history | 85 | 11 | 22 | 24 | 28.2% |
| 2026-10-05 | ITF | composite | 57 | 239 | 25 | 28 | 49.1% |
| 2026-10-05 | ITF | jeff_sackmann | 47 | 249 | 429 | 47 | 100.0% |
| 2026-10-05 | ITF | tennisexplorer | 148 | 148 | 1.0 | 27 | 18.2% |
| 2026-10-05 | ITF | tennismylife_history | 60 | 236 | 29.0 | 30 | 50.0% |
| 2026-10-05 | TOUR | composite | 19 | 13 | 8 | 2 | 10.5% |
| 2026-10-05 | TOUR | jeff_sackmann | 27 | 5 | 158 | 27 | 100.0% |
| 2026-10-05 | TOUR | tennisexplorer | 22 | 10 | 10.5 | 7 | 31.8% |
| 2026-10-05 | TOUR | tennismylife_history | 21 | 11 | 6 | 1 | 4.8% |
| 2026-10-05 | UTR | composite | 0 | 30 | 無 | 0 | 無 |
| 2026-10-05 | UTR | jeff_sackmann | 3 | 27 | 1275 | 3 | 100.0% |
| 2026-10-05 | UTR | tennisexplorer | 4 | 26 | 3.0 | 1 | 25.0% |
| 2026-10-05 | UTR | tennismylife_history | 3 | 27 | 452 | 3 | 100.0% |
| 2026-10-05 | 未知 | composite | 10 | 84 | 3.5 | 0 | 0.0% |
| 2026-10-05 | 未知 | jeff_sackmann | 22 | 72 | 343.0 | 22 | 100.0% |
| 2026-10-05 | 未知 | tennisexplorer | 20 | 74 | 6.0 | 7 | 35.0% |
| 2026-10-05 | 未知 | tennismylife_history | 0 | 94 | 無 | 0 | 無 |
| 2026-10-12 | CHALLENGER | composite | 79 | 49 | 26 | 38 | 48.1% |
| 2026-10-12 | CHALLENGER | jeff_sackmann | 82 | 46 | 249.0 | 82 | 100.0% |
| 2026-10-12 | CHALLENGER | tennisexplorer | 103 | 25 | 3 | 16 | 15.5% |
| 2026-10-12 | CHALLENGER | tennismylife_history | 110 | 18 | 4.0 | 9 | 8.2% |
| 2026-10-12 | ITF | composite | 86 | 306 | 35.5 | 47 | 54.7% |
| 2026-10-12 | ITF | jeff_sackmann | 90 | 302 | 467.5 | 90 | 100.0% |
| 2026-10-12 | ITF | tennisexplorer | 196 | 196 | 1.0 | 29 | 14.8% |
| 2026-10-12 | ITF | tennismylife_history | 102 | 290 | 50.5 | 63 | 61.8% |
| 2026-10-12 | TOUR | composite | 5 | 3 | 2 | 1 | 20.0% |
| 2026-10-12 | TOUR | jeff_sackmann | 8 | 0 | 164.5 | 8 | 100.0% |
| 2026-10-12 | TOUR | tennisexplorer | 5 | 3 | 4 | 2 | 40.0% |
| 2026-10-12 | TOUR | tennismylife_history | 2 | 6 | 2.0 | 0 | 0.0% |
| 2026-10-12 | UTR | composite | 1 | 141 | 34 | 1 | 100.0% |
| 2026-10-12 | UTR | jeff_sackmann | 1 | 141 | 188 | 1 | 100.0% |
| 2026-10-12 | UTR | tennisexplorer | 37 | 105 | 1 | 4 | 10.8% |
| 2026-10-12 | UTR | tennismylife_history | 5 | 137 | 325 | 5 | 100.0% |
| 2026-10-12 | 未知 | composite | 0 | 50 | 無 | 0 | 無 |
| 2026-10-12 | 未知 | jeff_sackmann | 0 | 50 | 無 | 0 | 無 |
| 2026-10-12 | 未知 | tennisexplorer | 3 | 47 | 3 | 0 | 0.0% |
| 2026-10-12 | 未知 | tennismylife_history | 0 | 50 | 無 | 0 | 無 |
| 2026-10-19 | CHALLENGER | composite | 58 | 82 | 57.0 | 40 | 69.0% |
| 2026-10-19 | CHALLENGER | jeff_sackmann | 53 | 87 | 387 | 53 | 100.0% |
| 2026-10-19 | CHALLENGER | tennisexplorer | 107 | 33 | 3 | 18 | 16.8% |
| 2026-10-19 | CHALLENGER | tennismylife_history | 119 | 21 | 4 | 26 | 21.8% |
| 2026-10-19 | ITF | composite | 91 | 371 | 48 | 60 | 65.9% |
| 2026-10-19 | ITF | jeff_sackmann | 77 | 385 | 488 | 77 | 100.0% |
| 2026-10-19 | ITF | tennisexplorer | 219 | 243 | 1 | 27 | 12.3% |
| 2026-10-19 | ITF | tennismylife_history | 99 | 363 | 83 | 79 | 79.8% |
| 2026-10-19 | TOUR | composite | 6 | 6 | 4.0 | 0 | 0.0% |
| 2026-10-19 | TOUR | jeff_sackmann | 10 | 2 | 169.5 | 10 | 100.0% |
| 2026-10-19 | TOUR | tennisexplorer | 3 | 9 | 5 | 1 | 33.3% |
| 2026-10-19 | TOUR | tennismylife_history | 0 | 12 | 無 | 0 | 無 |
| 2026-10-19 | UTR | composite | 2 | 76 | 347.0 | 2 | 100.0% |
| 2026-10-19 | UTR | jeff_sackmann | 0 | 78 | 無 | 0 | 無 |
| 2026-10-19 | UTR | tennisexplorer | 25 | 53 | 1 | 1 | 4.0% |
| 2026-10-19 | UTR | tennismylife_history | 0 | 78 | 無 | 0 | 無 |
| 2026-10-19 | 未知 | composite | 2 | 48 | 11.0 | 0 | 0.0% |
| 2026-10-19 | 未知 | jeff_sackmann | 2 | 48 | 156.0 | 2 | 100.0% |
| 2026-10-19 | 未知 | tennisexplorer | 3 | 47 | 12 | 1 | 33.3% |
| 2026-10-19 | 未知 | tennismylife_history | 2 | 48 | 11.0 | 0 | 0.0% |
| 2026-10-26 | CHALLENGER | composite | 116 | 110 | 40.0 | 73 | 62.9% |
| 2026-10-26 | CHALLENGER | jeff_sackmann | 103 | 123 | 267 | 103 | 100.0% |
| 2026-10-26 | CHALLENGER | tennisexplorer | 154 | 72 | 3.0 | 25 | 16.2% |
| 2026-10-26 | CHALLENGER | tennismylife_history | 187 | 39 | 4 | 30 | 16.0% |
| 2026-10-26 | ITF | composite | 92 | 380 | 33.5 | 53 | 57.6% |
| 2026-10-26 | ITF | jeff_sackmann | 82 | 390 | 460.0 | 82 | 100.0% |
| 2026-10-26 | ITF | tennisexplorer | 228 | 244 | 1.0 | 38 | 16.7% |
| 2026-10-26 | ITF | tennismylife_history | 97 | 375 | 159 | 84 | 86.6% |
| 2026-10-26 | TOUR | composite | 2 | 2 | 1.0 | 0 | 0.0% |
| 2026-10-26 | TOUR | jeff_sackmann | 3 | 1 | 397 | 3 | 100.0% |
| 2026-10-26 | TOUR | tennisexplorer | 1 | 3 | 7 | 0 | 0.0% |
| 2026-10-26 | TOUR | tennismylife_history | 0 | 4 | 無 | 0 | 無 |
| 2026-10-26 | UTR | composite | 2 | 94 | 562.5 | 2 | 100.0% |
| 2026-10-26 | UTR | jeff_sackmann | 1 | 95 | 577 | 1 | 100.0% |
| 2026-10-26 | UTR | tennisexplorer | 19 | 77 | 1 | 1 | 5.3% |
| 2026-10-26 | UTR | tennismylife_history | 2 | 94 | 1408.0 | 2 | 100.0% |
| 2026-10-26 | 未知 | composite | 12 | 54 | 1.0 | 1 | 8.3% |
| 2026-10-26 | 未知 | jeff_sackmann | 8 | 58 | 415.0 | 8 | 100.0% |
| 2026-10-26 | 未知 | tennisexplorer | 10 | 56 | 3.0 | 2 | 20.0% |
| 2026-10-26 | 未知 | tennismylife_history | 0 | 66 | 無 | 0 | 無 |
| 2026-11-02 | CHALLENGER | composite | 83 | 77 | 70 | 63 | 75.9% |
| 2026-11-02 | CHALLENGER | jeff_sackmann | 66 | 94 | 274.0 | 66 | 100.0% |
| 2026-11-02 | CHALLENGER | tennisexplorer | 123 | 37 | 4 | 24 | 19.5% |
| 2026-11-02 | CHALLENGER | tennismylife_history | 131 | 29 | 5 | 32 | 24.4% |
| 2026-11-02 | ITF | composite | 87 | 287 | 38 | 59 | 67.8% |
| 2026-11-02 | ITF | jeff_sackmann | 86 | 288 | 455.5 | 86 | 100.0% |
| 2026-11-02 | ITF | tennisexplorer | 175 | 199 | 8 | 44 | 25.1% |
| 2026-11-02 | ITF | tennismylife_history | 47 | 327 | 76 | 37 | 78.7% |
| 2026-11-02 | UTR | composite | 0 | 216 | 無 | 0 | 無 |
| 2026-11-02 | UTR | jeff_sackmann | 10 | 206 | 506.5 | 10 | 100.0% |
| 2026-11-02 | UTR | tennisexplorer | 32 | 184 | 6.0 | 6 | 18.8% |
| 2026-11-02 | UTR | tennismylife_history | 3 | 213 | 346 | 3 | 100.0% |
| 2026-11-02 | 未知 | composite | 8 | 24 | 1.0 | 0 | 0.0% |
| 2026-11-02 | 未知 | jeff_sackmann | 8 | 24 | 185.0 | 8 | 100.0% |
| 2026-11-02 | 未知 | tennisexplorer | 4 | 28 | 4.0 | 1 | 25.0% |
| 2026-11-02 | 未知 | tennismylife_history | 2 | 30 | 1.0 | 0 | 0.0% |
| 2026-11-09 | CHALLENGER | composite | 180 | 138 | 79.0 | 144 | 80.0% |
| 2026-11-09 | CHALLENGER | jeff_sackmann | 163 | 155 | 280 | 163 | 100.0% |
| 2026-11-09 | CHALLENGER | tennisexplorer | 262 | 56 | 1.0 | 54 | 20.6% |
| 2026-11-09 | CHALLENGER | tennismylife_history | 281 | 37 | 4 | 34 | 12.1% |
| 2026-11-09 | ITF | composite | 153 | 611 | 49 | 108 | 70.6% |
| 2026-11-09 | ITF | jeff_sackmann | 147 | 617 | 467 | 147 | 100.0% |
| 2026-11-09 | ITF | tennisexplorer | 360 | 404 | 13.5 | 102 | 28.3% |
| 2026-11-09 | ITF | tennismylife_history | 170 | 594 | 129.0 | 148 | 87.1% |
| 2026-11-09 | UTR | composite | 1 | 145 | 632 | 1 | 100.0% |
| 2026-11-09 | UTR | jeff_sackmann | 6 | 140 | 979.0 | 6 | 100.0% |
| 2026-11-09 | UTR | tennisexplorer | 25 | 121 | 18 | 10 | 40.0% |
| 2026-11-09 | UTR | tennismylife_history | 4 | 142 | 586.5 | 4 | 100.0% |
| 2026-11-09 | 未知 | composite | 2 | 42 | 1.0 | 0 | 0.0% |
| 2026-11-09 | 未知 | jeff_sackmann | 2 | 42 | 194.0 | 2 | 100.0% |
| 2026-11-09 | 未知 | tennisexplorer | 11 | 33 | 51 | 8 | 72.7% |
| 2026-11-09 | 未知 | tennismylife_history | 0 | 44 | 無 | 0 | 無 |
| 2026-11-16 | CHALLENGER | composite | 148 | 178 | 87.0 | 137 | 92.6% |
| 2026-11-16 | CHALLENGER | jeff_sackmann | 130 | 196 | 318.5 | 130 | 100.0% |
| 2026-11-16 | CHALLENGER | tennisexplorer | 242 | 84 | 3.0 | 61 | 25.2% |
| 2026-11-16 | CHALLENGER | tennismylife_history | 261 | 65 | 4 | 54 | 20.7% |
| 2026-11-16 | ITF | composite | 157 | 509 | 58 | 109 | 69.4% |
| 2026-11-16 | ITF | jeff_sackmann | 116 | 550 | 490.0 | 116 | 100.0% |
| 2026-11-16 | ITF | tennisexplorer | 326 | 340 | 19.0 | 86 | 26.4% |
| 2026-11-16 | ITF | tennismylife_history | 137 | 529 | 102 | 107 | 78.1% |
| 2026-11-16 | UTR | composite | 8 | 362 | 125.0 | 8 | 100.0% |
| 2026-11-16 | UTR | jeff_sackmann | 6 | 364 | 771.0 | 6 | 100.0% |
| 2026-11-16 | UTR | tennisexplorer | 75 | 295 | 34 | 44 | 58.7% |
| 2026-11-16 | UTR | tennismylife_history | 15 | 355 | 135 | 15 | 100.0% |
| 2026-11-16 | 未知 | composite | 23 | 13 | 18 | 3 | 13.0% |
| 2026-11-16 | 未知 | jeff_sackmann | 21 | 15 | 237 | 21 | 100.0% |
| 2026-11-16 | 未知 | tennisexplorer | 16 | 20 | 41.0 | 8 | 50.0% |
| 2026-11-16 | 未知 | tennismylife_history | 0 | 36 | 無 | 0 | 無 |
| 2026-11-23 | CHALLENGER | composite | 101 | 211 | 94 | 99 | 98.0% |
| 2026-11-23 | CHALLENGER | jeff_sackmann | 88 | 224 | 359.0 | 88 | 100.0% |
| 2026-11-23 | CHALLENGER | tennisexplorer | 227 | 85 | 2 | 38 | 16.7% |
| 2026-11-23 | CHALLENGER | tennismylife_history | 234 | 78 | 11.0 | 65 | 27.8% |
| 2026-11-23 | ITF | composite | 137 | 351 | 45 | 93 | 67.9% |
| 2026-11-23 | ITF | jeff_sackmann | 99 | 389 | 478 | 99 | 100.0% |
| 2026-11-23 | ITF | tennisexplorer | 194 | 294 | 26.0 | 71 | 36.6% |
| 2026-11-23 | ITF | tennismylife_history | 41 | 447 | 192 | 36 | 87.8% |
| 2026-11-23 | UTR | composite | 2 | 104 | 361.5 | 2 | 100.0% |
| 2026-11-23 | UTR | jeff_sackmann | 0 | 106 | 無 | 0 | 無 |
| 2026-11-23 | UTR | tennisexplorer | 45 | 61 | 29 | 15 | 33.3% |
| 2026-11-23 | UTR | tennismylife_history | 10 | 96 | 1032.5 | 10 | 100.0% |
| 2026-11-23 | 未知 | composite | 10 | 20 | 23.0 | 4 | 40.0% |
| 2026-11-23 | 未知 | jeff_sackmann | 10 | 20 | 254.5 | 10 | 100.0% |
| 2026-11-23 | 未知 | tennisexplorer | 8 | 22 | 86.5 | 6 | 75.0% |
| 2026-11-23 | 未知 | tennismylife_history | 4 | 26 | 18.0 | 1 | 25.0% |

## 4. 身份衝突

日誌以每行日期及類型計，同一行可屬多類；姓名只從同一類型後的錯誤片段中抽取，未列名不代表無受影響球員。

| 日期 | 類型 | 出現次數 | 可抽出不同姓名數 |
| --- | --- | --- | --- |
| 2026-11-06 | PlayerIdentityConflict | 3 | 2 |
| 2026-11-06 | RankingIdentityHoldError | 6 | 2 |
| 2026-11-06 | event_identity_rejected | 4 | 0 |
| 2026-11-07 | PlayerIdentityConflict | 7 | 2 |
| 2026-11-07 | RankingIdentityHoldError | 10 | 2 |
| 2026-11-08 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-08 | RankingIdentityHoldError | 8 | 2 |
| 2026-11-08 | event_identity_rejected | 2 | 0 |
| 2026-11-09 | PlayerIdentityConflict | 9 | 4 |
| 2026-11-09 | RankingIdentityHoldError | 10 | 2 |
| 2026-11-09 | event_identity_rejected | 2 | 0 |
| 2026-11-10 | PlayerIdentityConflict | 5 | 2 |
| 2026-11-10 | RankingIdentityHoldError | 10 | 3 |
| 2026-11-10 | event_identity_rejected | 3 | 0 |
| 2026-11-11 | PlayerIdentityConflict | 10 | 4 |
| 2026-11-11 | RankingIdentityHoldError | 12 | 3 |
| 2026-11-12 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-12 | RankingIdentityHoldError | 8 | 3 |
| 2026-11-12 | event_identity_rejected | 1 | 0 |
| 2026-11-13 | PlayerIdentityConflict | 3 | 2 |
| 2026-11-13 | RankingIdentityHoldError | 6 | 3 |
| 2026-11-13 | event_identity_rejected | 3 | 0 |
| 2026-11-13 | player_identity_conflict | 1 | 2 |
| 2026-11-14 | PlayerIdentityConflict | 5 | 2 |
| 2026-11-14 | RankingIdentityHoldError | 10 | 3 |
| 2026-11-14 | event_identity_rejected | 1 | 0 |
| 2026-11-14 | player_identity_conflict | 2 | 4 |
| 2026-11-15 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-15 | RankingIdentityHoldError | 8 | 3 |
| 2026-11-15 | event_identity_rejected | 1 | 0 |
| 2026-11-15 | player_identity_conflict | 4 | 4 |
| 2026-11-16 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-16 | RankingIdentityHoldError | 8 | 3 |
| 2026-11-16 | player_identity_conflict | 1 | 2 |
| 2026-11-17 | PlayerIdentityConflict | 3 | 2 |
| 2026-11-17 | RankingIdentityHoldError | 4 | 3 |
| 2026-11-18 | PlayerIdentityConflict | 5 | 2 |
| 2026-11-18 | RankingIdentityHoldError | 5 | 2 |
| 2026-11-18 | event_identity_rejected | 3 | 0 |
| 2026-11-19 | PlayerIdentityConflict | 1 | 2 |
| 2026-11-19 | RankingIdentityHoldError | 2 | 2 |
| 2026-11-19 | event_identity_rejected | 1 | 0 |
| 2026-11-20 | PlayerIdentityConflict | 5 | 2 |
| 2026-11-20 | RankingIdentityHoldError | 5 | 2 |
| 2026-11-20 | event_identity_rejected | 1 | 0 |
| 2026-11-20 | player_identity_conflict | 1 | 2 |
| 2026-11-21 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-21 | RankingIdentityHoldError | 4 | 2 |
| 2026-11-21 | event_identity_rejected | 2 | 0 |
| 2026-11-22 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-22 | RankingIdentityHoldError | 4 | 2 |
| 2026-11-22 | event_identity_rejected | 2 | 0 |
| 2026-11-23 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-23 | RankingIdentityHoldError | 7 | 4 |
| 2026-11-23 | event_identity_rejected | 1 | 0 |
| 2026-11-24 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-24 | RankingIdentityHoldError | 8 | 2 |
| 2026-11-24 | event_identity_rejected | 1 | 0 |
| 2026-11-25 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-25 | RankingIdentityHoldError | 8 | 2 |
| 2026-11-25 | event_identity_rejected | 1 | 0 |
| 2026-11-26 | PlayerIdentityConflict | 4 | 2 |
| 2026-11-26 | RankingIdentityHoldError | 8 | 2 |
| 2026-11-27 | RankingIdentityHoldError | 2 | 2 |

| 來源 | entity_type | HTTP | 記錄 | held 條目數 | 不同姓名 | 無效JSON |
| --- | --- | --- | --- | --- | --- | --- |
| composite | ranking | 206 | 40 | 0 | 0 | 0 |
| composite | ranking_identity_hold | 206 | 183 | 2748 | 70 | 0 |
| composite | ranking_source_evidence | 206 | 25 | 0 | 0 | 0 |

held 條目可重複；206 包括快取及來源證據，並非全部身份擱置。

| 日期 | Sportsbet 場次 | 兩表均無 match_id | 比例 |
| --- | --- | --- | --- |
| 2026-09-01 | 55 | 0 | 0.0% |
| 2026-09-02 | 46 | 0 | 0.0% |
| 2026-09-03 | 52 | 4 | 7.7% |
| 2026-09-04 | 57 | 1 | 1.8% |
| 2026-09-05 | 54 | 1 | 1.9% |
| 2026-09-06 | 52 | 12 | 23.1% |
| 2026-09-07 | 48 | 0 | 0.0% |
| 2026-09-08 | 63 | 1 | 1.6% |
| 2026-09-09 | 145 | 55 | 37.9% |
| 2026-09-10 | 54 | 0 | 0.0% |
| 2026-09-11 | 51 | 0 | 0.0% |
| 2026-09-12 | 54 | 0 | 0.0% |
| 2026-09-13 | 75 | 14 | 18.7% |
| 2026-09-14 | 50 | 0 | 0.0% |
| 2026-09-15 | 57 | 0 | 0.0% |
| 2026-09-16 | 51 | 0 | 0.0% |
| 2026-09-17 | 57 | 0 | 0.0% |
| 2026-09-18 | 62 | 0 | 0.0% |
| 2026-09-19 | 92 | 13 | 14.1% |
| 2026-09-20 | 87 | 24 | 27.6% |
| 2026-09-21 | 51 | 8 | 15.7% |
| 2026-09-22 | 42 | 0 | 0.0% |
| 2026-09-23 | 54 | 0 | 0.0% |
| 2026-09-24 | 47 | 0 | 0.0% |
| 2026-09-25 | 48 | 0 | 0.0% |
| 2026-09-26 | 43 | 1 | 2.3% |
| 2026-09-27 | 34 | 1 | 2.9% |
| 2026-09-28 | 31 | 1 | 3.2% |
| 2026-09-29 | 45 | 0 | 0.0% |
| 2026-09-30 | 48 | 0 | 0.0% |
| 2026-10-01 | 49 | 0 | 0.0% |
| 2026-10-02 | 39 | 0 | 0.0% |
| 2026-10-03 | 40 | 0 | 0.0% |
| 2026-10-04 | 46 | 8 | 17.4% |
| 2026-10-05 | 28 | 0 | 0.0% |
| 2026-10-06 | 46 | 0 | 0.0% |
| 2026-10-07 | 48 | 0 | 0.0% |
| 2026-10-08 | 38 | 0 | 0.0% |
| 2026-10-09 | 37 | 0 | 0.0% |
| 2026-10-10 | 32 | 0 | 0.0% |
| 2026-10-11 | 45 | 7 | 15.6% |
| 2026-10-12 | 39 | 0 | 0.0% |
| 2026-10-13 | 41 | 0 | 0.0% |
| 2026-10-14 | 51 | 0 | 0.0% |
| 2026-10-15 | 58 | 0 | 0.0% |
| 2026-10-16 | 52 | 0 | 0.0% |
| 2026-10-17 | 57 | 0 | 0.0% |
| 2026-10-18 | 62 | 16 | 25.8% |
| 2026-10-19 | 53 | 0 | 0.0% |
| 2026-10-20 | 87 | 0 | 0.0% |
| 2026-10-21 | 56 | 0 | 0.0% |
| 2026-10-22 | 53 | 0 | 0.0% |
| 2026-10-23 | 49 | 0 | 0.0% |
| 2026-10-24 | 35 | 0 | 0.0% |
| 2026-10-25 | 38 | 0 | 0.0% |
| 2026-10-26 | 45 | 0 | 0.0% |
| 2026-10-27 | 40 | 0 | 0.0% |
| 2026-10-28 | 106 | 0 | 0.0% |
| 2026-10-29 | 56 | 0 | 0.0% |
| 2026-10-30 | 78 | 0 | 0.0% |
| 2026-10-31 | 50 | 0 | 0.0% |
| 2026-11-01 | 57 | 0 | 0.0% |
| 2026-11-02 | 45 | 0 | 0.0% |
| 2026-11-03 | 59 | 0 | 0.0% |
| 2026-11-05 | 71 | 0 | 0.0% |
| 2026-11-06 | 48 | 0 | 0.0% |
| 2026-11-07 | 78 | 0 | 0.0% |
| 2026-11-08 | 90 | 0 | 0.0% |
| 2026-11-09 | 78 | 0 | 0.0% |
| 2026-11-10 | 85 | 0 | 0.0% |
| 2026-11-11 | 114 | 0 | 0.0% |
| 2026-11-12 | 101 | 0 | 0.0% |
| 2026-11-13 | 95 | 0 | 0.0% |
| 2026-11-14 | 87 | 0 | 0.0% |
| 2026-11-15 | 76 | 0 | 0.0% |
| 2026-11-16 | 93 | 0 | 0.0% |
| 2026-11-17 | 87 | 0 | 0.0% |
| 2026-11-18 | 117 | 0 | 0.0% |
| 2026-11-19 | 93 | 0 | 0.0% |
| 2026-11-20 | 118 | 0 | 0.0% |
| 2026-11-21 | 91 | 0 | 0.0% |
| 2026-11-22 | 100 | 0 | 0.0% |
| 2026-11-23 | 91 | 0 | 0.0% |
| 2026-11-24 | 89 | 0 | 0.0% |
| 2026-11-25 | 101 | 0 | 0.0% |
| 2026-11-26 | 102 | 0 | 0.0% |
| 2026-11-27 | 85 | 0 | 0.0% |

以 match_id 關聯；未連結 match_id 的 event 價格未計入，因此是關聯缺失，不必然代表事件完全無價格。

## 5. TML 擱置衝突

同一 CSV 場次同時涉及多名衝突球員只計一次；token 重疊是機械分類，不能證實身份。

| CSV | 行數 | 狀態 |
| --- | --- | --- |
| https://stats.tennismylife.org/data/2026_challenger.csv | 7341 | DB 存檔 2026-11-26T22:31:44Z |
| https://stats.tennismylife.org/data/atp_quali/2026_atp_quali.csv | 1282 | DB 存檔 2026-11-26T22:38:33Z |

下載錯誤：https://stats.tennismylife.org/data/2026_challenger.csv：URLError <urlopen error [Errno 8] nodename nor servname provided, or not known>; https://stats.tennismylife.org/data/atp_quali/2026_atp_quali.csv：URLError <urlopen error [Errno 8] nodename nor servname provided, or not known>

| ID | DB 名 | CSV 名 | CSV 場數 | 分類 |
| --- | --- | --- | --- | --- |
| AG08 | Andres Andrade | Andy Andrade | 8 | 同一人改名（token 重疊） |
| B0C0 | Gabi Adrian Boitan | Adrian Boitan | 13 | 同一人改名（token 重疊） |
| B0GI | Alexandr Binda | Alexander Binda | 1 | 同一人改名（token 重疊） |
| B0V0 | Nikita Belozertsev | Nikita Bilozertsev | 2 | 同一人改名（token 重疊） |
| D0OU | João Pedro Didoni Bonini | JoÃƒÂ£o Pedro Didoni Bonini | 1 | 同一人改名（token 重疊） |
| EA13 | Jerome Kym | Moez Echargui | 48 | ID 重新分配（無 token 重疊） |
| EA31 | Melios Efstathiou | Menelaos Efstathiou | 3 | 同一人改名（token 重疊） |
| G0AO | Mats Rosenkranz | Alastair Gray | 40 | ID 重新分配（無 token 重疊） |
| K0DB | Inaki Montes-De La Torre | Cannon Kingsley | 17 | ID 重新分配（無 token 重疊） |
| K0FY | Mats Rosenkranz | Martin Krumich | 54 | ID 重新分配（無 token 重疊） |
| L0CK | Younes Lalami Laaroussi | Younes Lalami | 1 | 同一人改名（token 重疊） |
| M0WY | Guto Miguel | Luis Guto Miguel | 21 | 同一人改名（token 重疊） |
| N0DR | Bryce Nakashima | Bryce Nakashima Nakashima | 1 | 同一人改名（token 重疊） |
| N0FT | Alex Santino Nuñez Vera | Alex Santino Nunez Vera | 2 | 同一人改名（token 重疊） |
| P0DF | Matheus Pucinelli De Almeida | Matheus Pucinelli De Alme | 1 | 同一人改名（token 重疊） |
| S0H2 | Alexander Shevchenko | Aleksandr Shevchenko | 6 | 同一人改名（token 重疊） |
| S0TM | Inaki Montes-De La Torre | Toby Samuel | 59 | ID 重新分配（無 token 重疊） |
| W09G | J.J. Wolf | J.j Wolf | 1 | 同一人改名（token 重疊） |

已核實衝突組合 18；涉及不同場次 275；分類數 {'同一人改名（token 重疊）': 13, 'ID 重新分配（無 token 重疊）': 5}。即時下載失敗；數字僅代表所列 DB 存檔。

## 6. 賽果同結算

| 精選 週一 | 總數 | PENDING >3日 | VOID | VOID % | 狀態分布 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-02 | 20 | 0 | 1 | 5.0% | LOST:10, VOID:1, WON:9 |
| 2026-11-09 | 69 | 0 | 3 | 4.3% | LOST:34, VOID:3, WON:32 |
| 2026-11-16 | 63 | 1 | 1 | 1.6% | LOST:39, PENDING:1, VOID:1, WON:22 |
| 2026-11-23 | 48 | 0 | 0 | 0.0% | LOST:30, PENDING:3, WON:15 |

| prop_tracker 週一 | 總數 | PENDING >3日 | VOID | VOID % | 狀態分布 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 1601 | 0 | 185 | 11.6% | LOST:749, VOID:185, WON:667 |
| 2026-11-02 | 1353 | 11 | 81 | 6.0% | LOST:686, PENDING:11, VOID:81, WON:575 |
| 2026-11-09 | 1203 | 37 | 45 | 3.7% | LOST:516, PENDING:37, VOID:45, WON:605 |
| 2026-11-16 | 1176 | 63 | 23 | 2.0% | LOST:492, PENDING:63, VOID:23, WON:598 |
| 2026-11-23 | 849 | 11 | 10 | 1.2% | LOST:303, PENDING:180, VOID:10, WON:356 |

精選以 prop_id 連接 prop_tracker，連不到列為無狀態。

## 7. 總結

以下按可量度的受影響定價場次，再按嚴重程度排序；快照球員缺欄只表示至少一人缺，並非因果證明。

| 問題 | 受影響 Sportsbet 場次 | 性質 |
| --- | --- | --- |
| 輪次缺失 | 5474 | 待核實（僅觀察缺欄） |
| 場地缺失 | 5431 | 待核實（僅觀察缺欄） |
| break 缺失 | 3787 | 待核實（僅觀察缺欄） |
| hold 缺失 | 3787 | 待核實（僅觀察缺欄） |
| 疲勞未知 | 2369 | 待核實（僅觀察缺欄） |
| 排名缺失 | 1934 | 待核實（僅觀察缺欄） |
| 快照缺失或無效 | 1149 | 待核實（僅觀察缺欄） |
| 兩張 odds 表均無 match_id | 167 | 待核實（可能未連結） |

WTA serve 未接線（EXP-20261026-04 REJECT）、Challenger 場地（EXP-20261113-50 REJECT）、wta_official_stats 於 11-06 重寫後停用：按題述記錄列為刻意；上述統計未拆解到各決策，不能直接推算各自影響場次。

排名來源停更新檢查：以各來源曾出現球員為母體，其他來源較該球員在目標來源最後日期更新只代表 DB 有紀錄；不保證實際讀取通過 receipt 或時效檢查。

| 來源 | 最新 ranking_date | 曾有排名球員 | 其他來源日期較新球員 | 其他來源近30日球員 | 定價場次級別（至少一人） |
| --- | --- | --- | --- | --- | --- |
| composite | 2026-10-30 | 3962 | 2987 | 2986 | CHALLENGER:918, ITF:2297, TOUR:72, UTR:359, 未知:186 |
| wta_numeric_pdf | 2026-11-09 | 1552 | 1515 | 1549 | ITF:1269, TOUR:43, UTR:118, 未知:66 |

其他來源按各來源最新排名日期比較（同一球員可計入多個來源）：

| 原來源 | 其他來源 | 同一批球員 | 較原來源新 | 近30日 | 其他來源最新日期 |
| --- | --- | --- | --- | --- | --- |
| composite | wta_ranked_players_api | 1533 | 1525 | 1525 | 2026-11-23 |
| composite | wta_numeric_pdf | 1520 | 1520 | 1520 | 2026-11-09 |
| composite | atp_official_numeric_pdf | 1466 | 1460 | 1460 | 2026-11-23 |
| composite | tennismylife_history | 1266 | 414 | 411 | 2026-11-22 |
| composite | jeff_sackmann | 1217 | 10 | 0 | 2026-05-18 |
| wta_numeric_pdf | wta_ranked_players_api | 1549 | 1515 | 1549 | 2026-11-23 |
| wta_numeric_pdf | jeff_sackmann | 532 | 0 | 0 | 2026-05-18 |
| wta_numeric_pdf | composite | 1520 | 0 | 0 | 2026-10-26 |

讀取路徑：src/tennis_wc/store/ranking_reads.py 的 RankingReader.rows/select 讀 rankings_history，包含 composite 和 wta_numeric_pdf；select 會檢查來源 receipt、日期及時效。資料庫有較新行不等於已獲選用。

時間分類：排名兩來源的最新日期見上表；是否屬最近中斷須另核對抓取及退役決策。其他缺欄未憑單次覆蓋率判斷「一直沒有」或「最近斷咗」。
