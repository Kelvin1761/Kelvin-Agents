# EXP-20261031-01 NBA：stats.nba.com 封鎖期間用 ESPN 賽果計聯盟數據表

- **日期**：2026-10-31
- **平台**：NBA
- **假設**：nba.com 封鎖時，球隊進階數據（PACE／OFF／DEF rating／DEF_RANK）同球員進階數據（USG／TS／eFG／AST%）可以由 ESPN 賽果計返，貼近 nba_api；主力防守球員／對位防守（追蹤數據，ESPN 冇）缺咗對輸出影響細，可以唔再當硬性條件。
- **搜索過嘅舊記錄**：EXP-20261030-01（ESPN 球員賽績後備，94.7% 逐場一樣；聯盟數據表冇替代，只靠一日內快照）。
- **改到嘅檔案**：`.agents/skills/nba/nba_espn_league.py`（新）、`nba_extractor.py`（`espn_league_fallback`、`TRACKING_ONLY_TABLES`）、`nba_api_breaker.py`（`source_status`）、`nba_daily_schedule.py`（每日／每週 stats.nba.com 狀態）、測試。

## 背景
stats.nba.com 由 2026-10-29 21:00 起拒絕本機嘅程式請求（換 IP 都係），快照後備由頭到尾冇一份快照，10-30 至 10-31 冇 NBA 分析、冇注。

## 一、數據對齊（parity）
- **語料**：排程 `2026-10-2x NBA Analysis/nba_game_data_*.json`，`data_season=2026-27`、非快照嘅 nba_api 表；窗口 `history_date_to` 10-20..10-27。
- **ESPN**：同一個 `history_date_to` 之前所有常規賽完場 box score（56 場，3 場加時）。
- **回合數**：`FGA + 0.44·FTA − OREB + TOV`（隊伍總失誤）比 nba.com 高約 2%。用 10-22..10-24 定一個常數 `POSSESSION_SCALE=0.98`，喺 10-25..10-27 驗證：

| 球隊（測試窗，n=48） | 未修正 中位 \|Δ\| | 0.98 中位 \|Δ\| | 0.98 平均偏差 |
|---|---|---|---|
| PACE | 2.45 | **0.65** | +0.26 |
| OFF_RATING | 2.65 | **1.10** | −0.15 |
| DEF_RATING | 2.60 | **0.85** | −0.41 |
| DEF_RANK | 1 位 | **1 位** | — |

- **球員**（n=583，有本季出場）：TS%／eFG% 中位差 0.0（box score 算式一樣）；USG% 0.6（p90 2.0）；AST% 0.7（p90 3.3）。極端值全部係出場幾分鐘嘅球員。PIE 對唔上（中位差 4.5），設 `None`（下游冇讀）。
- 中途發現一個 bug：summary 嘅 `status` 冇節數，最初加時一律當 4 節；改用 line score 長度後先做以上數字。

## 二、對輸出嘅影響（同環境重跑）
- **方法**：51 場已發佈分析，用 `generate_nba_reports.py` 同一環境重跑三個設定，逐條腿（13,376 條）比 `p_final`：
  - A：原封不動輸入（基準）
  - B：`key_defenders`、`team_dvp` 清空
  - C：B ＋ ESPN 計嘅 `team_stats`／球員 `advanced`
- 注意：直接同已存報告比會見到最大 77pp 差異，原因係重跑環境有啲場冇用到 calibrated 引擎（`calibrated(hybrid)` → `hybrid`），唔係數據改動；所以基準一定要係同環境嘅 A。

| | 有變嘅腿 | 平均移動 | 最大 | 跨 50%／60%／70%／80% |
|---|---|---|---|---|
| B（冇追蹤數據） | **0 / 13,376** | 0 | 0 | 0／0／0／0 |
| C（完整 ESPN 後備） | 330（2.5%） | −0.07pp | 7.0pp | 14／10／5／4（基數 3,185／2,585／1,966／1,355） |

- B 完全唔郁：已核實 A 嘅 51 場輸入全部有 `key_defenders`（633 行有 `PCT_PLUSMINUS`），即係唔係冇接通，而係現行引擎嘅輸出唔受佢影響（`defender_pm` 喺 v3 特徵表入面，但量到嘅貢獻係零）。呢點值得另外睇，但唔屬今次範圍。

## 檢查
- **leakage-audit**：PASS —— ESPN 只讀 `history_date_to` 或之前嘅美東日期，同 nba_api 窗口一樣（測試釘死唔會讀窗口後一日）。
- **閘門**：唔適用（唔係模型改動；呢個係數據來源後備，nba.com 正常時零改變）。
- **限制**：parity 只得早季 6 個窗口；`POSSESSION_SCALE` 喺樣本大咗之後要再驗證。上季球員（本季未出場）喺後備期冇進階數據（唔會用 ESPN 抓上季 1,230 場）。

## 結論
ESPN 計嘅兩張表同 nba_api 好接近，完整後備只令 2.5% 腿嘅機率有細微變化；追蹤數據缺咗對輸出零影響。**決定：KEEP（數據來源後備）**——nba.com 唔通先用，每一輪都先試 nba.com，一通即自動切返；健康檢查每日記錄、狀態轉變同每週一 Telegram。

## 重跑
```bash
# 證據腳本喺 docs/experiments/evidence/EXP-20261031-01-*；ESPN cache 用 WC_NBA_ESPN_BOX_DIR 指去暫存目錄
WC_NBA_ESPN_BOX_DIR=<tmp>/cache python3 EXP-20261031-01-nba-espn-league-fit.py .agents/skills/nba
NBA_WC_MODEL_DIR=~/WongChoiData/NBA_ML_Dataset/models/v3 WC_NBA_ESPN_BOX_DIR=<tmp>/cache \
  python3 EXP-20261031-01-nba-espn-league-replay.py .agents/skills/nba <tmp>/replay
python3 EXP-20261031-01-nba-espn-league-compare.py <tmp>
```
