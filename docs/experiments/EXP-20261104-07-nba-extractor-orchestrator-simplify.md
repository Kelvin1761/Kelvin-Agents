# EXP-20261104-07 — NBA extractor／orchestrator 剷死 code

- 日期：2026-11-04
- 平台：NBA（`nba_data_extractor/scripts/nba_extractor.py`、`nba_orchestrator.py`）
- 基準 commit：`d500aa8b`（對比用）；發佈喺 `ed805961` 之上
- 類型：**工程簡化，唔改模型**。`nba_engine` 讀嘅欄位一個都冇郁。

## 改咗咩

**Extractor（1611 → 935 行）**：剷走冇任何 consumer 嘅輸出，同埋抓取佢哋嘅 code。

| 剷走 | 之前做咩 | 點解冇人用 |
|---|---|---|
| `odds`（Action Network／The Odds API） | 第三方賠率 | 賠率只嚟自 `Sportsbet_Odds_*.json`；engine、dashboard、research 都唔讀 package 嘅 `odds` |
| `news` | ESPN 每隊 5 條新聞 | LLM 年代嘅閱讀材料 |
| `players[].h2h` | 對手歷史（多讀兩季 × RS／Playoffs game log） | 冇 consumer |
| `players[].splits`、`splits_season` | 主客／休息日分組 | 只餵 `prop_analytics`／`fatigue` |
| `players[].prop_analytics`、`fatigue` | 舊「Python Math Engine」嘅 +EV／疲勞 | 只有舊引擎用（已於 EXP-20261103-15 退役） |
| 概覽模式（冇 `--game`） | 寫 `NBA_Data_Package_Auto.md` | orchestrator 一律傳 `--game`；而家冇 `--game` 會報錯 |
| `detect_season_phase`、curl_cffi | 冇人叫 | — |

保留不變（`nba_availability`、`nba_data_contract`、`nba_research_evidence`、`nba_prop_training` 讀緊）：`gamelog`（連 `*_stats`／`*_label`）、`advanced`、`injuries`、`team_stats`、`team_dvp`、`key_defenders`、`usage_redistribution`、`correlation_warnings`、`opportunity_features`、`opponent_context`、`team_recent`、`meta`。

**Orchestrator（919 → 約 715 行）**：

- 剷走：`--legacy`、`--banker-search-audit`、`--debug-skip-extractor`（連 debug fallback JSON）。
- 剷走：`[FILL]`／NEXT_CMD，同埋 release 狀態入面嘅 fill／compile 兩級（新引擎從來唔寫 `[FILL]`）。release 而家只有 deploy／blocked 兩種（`_release_action`）。
- 剷走：`report_release_current` 別名。
- 剷走：Phase 1A.5 `validate_json_schema.py`，連兩份 schema。佢同現有閘重複：Sportsbet JSON 已經過 `sportsbet_json_matches_target`／`player_milestone_markets_available`；extractor JSON 已經過 `statistics_current`／`availability_current`／`extractor_cache_current`。

排程用嘅 CLI 不變：`--date --auto --skip-cloudflare-deploy [--game]`、`--compile-only --games`。`--auto` 照收，但冇作用。

## 驗證

**1. Extractor 逐欄對比**

用 `docs/experiments/evidence/EXP-20261104-07-nba-extractor-parity.py`，對 2026-11-05 全部 14 場逐場跑：同一場舊版跑完即刻跑新版，相隔約 30 秒。

- 14/14 場、408 名球員：**除咗下面兩類，每一欄都一樣**（gamelog、advanced、injuries、availability rosters、team_stats、opportunity_features 嘅數值、opponent_context／team_recent 嘅表……）。
- 時間戳類：
  - `meta.extracted_at`、`meta.availability.captured_at`、`opportunity_features.*.captured_at`、`opponent_context`／`team_recent` 嘅 `captured_at`。
  - `tables_sha256` 都唔同，因為個表入面包住 `captured_at`。剔走時間戳之後，兩邊個表一樣。
- 刻意剷走嘅欄位：
  - 每場：`odds`、`news`。
  - 每名球員：`fatigue`、`h2h`、`prop_analytics`、`splits`、`splits_season`。
- 新版每場快 2–7 秒（例如 LAL_SAC 33s → 27s）。

**2. Orchestrator 11-05 乾跑**

命令：`--date 2026-11-05 --auto --skip-cloudflare-deploy`。輸出寫喺 worktree，唔 deploy。

- 2 分 52 秒跑完全條流程。
- 12 場由 Sportsbet → extractor → nba_engine → 防火牆 → SGM 匯總全部通過。
- IND_MEM、MIL_BOS 嘅球員盤未開，正確回報 `waiting_player_markets`（exit 75）。
- 用嗰批真實新引擎報告跑 dashboard 匯出：10 個正式組合，全部 `sportsbet_sgm_quoted`，標題同 CoV 都由 sidecar 嚟。

**3. 測試**

NBA 全部測試過。刪咗測試已剷 code 嘅 `test_splits_from_gamelog…`；`_pipeline_release_action` 嘅測試改為測新嘅 `_release_action`。
