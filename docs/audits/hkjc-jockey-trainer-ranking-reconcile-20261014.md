# HKJC 官方騎練排名：唔入評分，改做賽果庫對數（2026-10-14）

- **問題**：「騎練排名應該入評分？」—— `crawl_hkjc_jockey_trainer.py` 存在但冇人叫。
- **判決**：**唔入評分**（冇新資訊 + 回測必然前視）。改為每週 review 嘅
  數據質素檢查（只警告，唔攔 pipeline）。
- **冇改評分 code／權重／golden**，所以唔使跑 regression gate。

## 1. 頁面而家有咩

`racing.hkjc.com/{zh-hk,en-us}/local/info/{jockey,trainer}-ranking` 係 Next.js
client render；HTML 冇 table 數據。數據嚟自 GraphQL `info.cld.hkjc.com/graphql/base/`：

| operation | 內容 |
|---|---|
| `rw_GetJockeyRanking(season)` / `rw_GetTrainerRanking(season)` | 每人 `ssnStat[]`：頭／二／三／四／五、出賽、獎金；按 `ven`(ST/HV) × `trk`(TURF/AWT) 再細分（似係按路程，`dist` 欄唔喺白名單 query 入面），加一行 ALL/ALL；`dhStat[]` 平頭馬 |
| `rw_LastMeeting` | 官方統計截至嘅賽日 + 季度 |
| `rw_RacingSeasonPeriod` | 只返本季 `26/27` 同上季 `25/26` |

- 季度：只得本季同上季（`24/25`、`23/24` 返 0 行）。冇近 30 日、冇騎練組合、冇海外
  （頁面明寫「Overseas records not included」）。
- 有白名單：自己砌 query 回 `WHITELIST_ERROR`；要用網站本身 operation 形狀
  （空白無所謂）。

**舊 crawler 狀態**：死。爬 `<table>` 同 `__NEXT_DATA__`，新站兩樣都冇 → 永遠 0 行；
舊 `.aspx` URL 302 去新 SPA。由來冇 caller（只喺 `preflight_environment_check.py`
檔名清單出現）。

## 2. 同我哋自己數嘅比較

我哋數法：`hkjc results YYYY YY/*/full_day_results.json`，退出（`WV`、`WV-A`、`WX-A`、
`WXNR`、`---`）唔計出賽，`PU/UR/DNF/DISQ` 計出賽冇名次，「1 平頭馬」計頭馬。

| 季度 | 騎師 [頭..五,出賽] 完全一致 | 練馬師 | 出賽總數 官方 / 我哋 | 頭馬總數差 |
|---|---|---|---|---|
| 26/27（至 2026-10-11，10 賽日） | **22/22** | **23/23** | 1221 / 1221 | 0 |
| 25/26（全季） | 28/47 | 25/44 | 10797 / 10769 | 2 |

`comprehensive_stats/26_27/{jockey,trainer}_master_stats.csv`（引擎讀嘅檔）嘅
勝／出賽／前三亦 22/22、23/23 一致。

**25/26 嘅 28 個出賽、2 個頭馬差（0.26%）**：全部係我哋少（冇一個人我哋多），分佈
係沙田草地 ~14、沙田全天候 ~14、跑馬地 0 —— 似係漏咗兩場沙田賽事。已排除：
- 21 個短場賽日逐個對官方場數，全部一致（2025-09-21 R9–10、2025-11-15 R8–10 係
  官方宣佈取消／VOID，我哋冇係啱）。
- 冇重複場次（同一賽日兩場出賽名單一樣：0）。
- 21 個空資料夾（2025-09-13、10-05、11-16、12-28、2026-02-15、04-05、05-10 等）
  官方全部「No information」，唔係本地賽日。
- 頭馬差：騎師 潘頓、金誠剛各 −1；練馬師 告東尼、游達榮各 −1。

**未解決**（證據不足以話係邊兩場）。影響：25/26 騎練率每人最多差 1 勝 / 3 出賽，
對評分可以忽略；但記低，唔好假設上季完整。

## 3. 點解唔入評分

1. **冇新資訊**：本季逐人逐格同我哋賽果一樣。海外策騎官方都唔計。場地／泥草
   分拆我哋已有（`jockey_venue_track_stats.csv`；EXP-20260905-03 試過場地拆分）。
2. **Point-in-time**：頁面只係「而家」快照，回測舊賽日用佢 = 前視（同 AU 騎練率
   前視一樣，見 memory `au-people-stats-have-lookahead`）。季內 as-of 值頁面重建唔到，
   但由賽果可以 —— `trainer_signal` 已經係咁做（`live_priors` / `pit_backtest`）。
3. 上季數字官方同我哋差 0.26%，即使用官方版亦唔會令 prior 有可量度分別。

所以冇嘢可以預先登記：A/B 嘅 candidate 同 baseline 數據逐格一樣，結果必然係
bit-identical。

## 4. 之前試過嘅騎練改動（唔好重做）

| 記錄 | 改動 | 結果 |
|---|---|---|
| EXP-20260905-03 | 練馬師訊號按場地拆分 | 193 場量唔到（UNRESOLVABLE，`good_positional` −1.04pp） |
| EXP-20261004-01 | 新季統計自動發現 + 季度感知 prior | KEEP 數據修補；live 權重不變 |
| EXP-20261005-01 | 練馬師 90/180 日近況 | REJECT（terminal Good −1.96pp） |
| EXP-20261010-01 | 換季後「兩季 EB」寫死 `24_25` | CORRECTNESS PROMOTE（Stage 4 v2 本身 REJECT／證據弱） |
| EXP-20260904-05 | 顯示尺 | `騎練訊號` 原始 76.7 其實係第 99 百分位 —— 係**顯示**低估，唔係排名 |

## 5. 改咗咩

- `hkjc_race_extractor/scripts/crawl_hkjc_jockey_trainer.py`：重寫做 GraphQL +
  對數（`build_report` 永遠唔拋 exception；`status` = ok / warn / unavailable）。
  警告條件：官方最近賽日唔喺賽果庫；騎師出賽總數差 > 14（多過一場滿閘）；頭馬總數有差。
  只對到官方 `lastMeeting` 為止（我哋早入嘅新賽日唔當差異）。
- `hkjc_daily_auto/hkjc_daily_schedule.py`：每週 review 尾加一段
  `results_db_reconcile_section()`；失敗只係少一段。
- 測試：`hkjc_race_extractor/tests/test_jockey_trainer_ranking_reconcile.py`、
  `hkjc_daily_auto/tests/test_weekly_results_reconcile_section.py`（兩個目錄都喺
  `run_tests.sh` suite 入面）。

手動：`python3 .agents/skills/hkjc_racing/hkjc_race_extractor/scripts/crawl_hkjc_jockey_trainer.py [--season 25/26] [--json]`
