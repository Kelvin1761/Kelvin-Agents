# EXP-20261026-08 S_v4 shadow 接線同 forward 判決協議（未有數據之前凍結）

- **日期**：2026-10-26（Claude Code，用戶要求）
- **承接**：EXP-20261026-07（S_v4 開發：2024 季初揀參數，2025 季初驗證 log-loss −0.0061 [−0.0092, −0.0037]；只計有上季比賽嘅腿係 −0.0109）。
- **凍結時狀態**：ledger 入面帶 `season_rate_v4_*` 嘅腿 = 0。

## 接線

- **`nba_season_rate.season_rate_prob_v4`**：S_v2 嘅共用核心加每場權重。上季比賽權重 0.25；轉咗隊嘅話，PTS 再乘 0.25、AST 再乘 0.5，REB 同 3PM 唔再額外減。
  - **轉隊定義**：最近一場上季比賽嘅球隊，同今日球隊唔同。
  - **今季**：讀 `meta.roster_season`。
- **Extractor**：`season_log.teams` 記錄每場比賽嘅球隊，即 `MATCHUP` 嘅第一個字；冇 `MATCHUP` 就唔寫，唔會估。
- **唔會亂估**：歷史入面有上季比賽但冇球隊資料，就報 `no_team_history`；冇今季資料就報 `no_current_season`。
- **欄位**：`season_rate_v4_prob_S／_version／_status／_inputs` 寫入 sidecar 同 ledger。`inputs` 包括 `previous_games`、`moved`、`previous_weight`。冇任何選腿、EV 或者 C 會讀呢啲欄位。
- **一致性**：
  - 共用核心喺權重 = 1 時同改之前完全一樣（乘 1.0 唔會改變浮點數）。
  - 同研究 harness 逐行核對 9,600 個機率：v2（重構後）同 v4 最大差都係 0.00005，只係四捨五入。
  - 參數同 `tune_v4.json` 一致，有測試釘住。

## Forward 判決（`nba_season_rate_v4_forward.py`）

- **比較**：S_v4 對 S_v2，**只計有上季比賽嘅腿**（`season_rate_v4_inputs.previous_games > 0`）。冇上季比賽嘅腿，兩者完全一樣，計入去只會沖淡效應。
- **配對**：同一隻腿、同一個最新已發佈賽前快照（量嘅係機率準唔準，所以用最新快照）；只計 Over；settlement `y ∈ {0,1}`；梯級權重 1。
- **Epoch**：2026-10-27。
- **只判一次**：
  - **時間**：連續 3 個有比賽嘅日子都冇受影響嘅腿（即係季初完結），或者到 2026-12-01，以較早者為準。
  - **樣本**：受影響嘅腿要 ≥100 場比賽，唔夠就 NEEDS_MORE_TESTING，延到下季季初再量。
- **判斷**：加權 log-loss（S_v4 − S_v2），比賽日 cluster bootstrap 95% CI（4,000 次，seed 20261027）。
  - **KEEP**：CI 上限 < 0。
  - **REJECT**：CI 下限 > 0，或者點估計 ≥ 0。
  - 其他：NEEDS_MORE_TESTING。
- **數據守則**：`last_game_date` 一定要早過賽事日，否則報 INVALID_DATA。
- **功效（2025 季初受影響嘅腿）**：每日 SD 大約 0.011 至 0.018。以 21 日計，MDE 大約 0.007 至 0.011，開發效應係 −0.0109，所以有合理功效。

## 唔准做嘅嘢

- forward 期間唔准改權重、轉隊定義或判決規則。
- KEEP 只代表 S_v4 喺季初好過 S_v2。要用嚟取代 C 入面嘅 L10，仍然要行 MS 系列 forward 測試同 model-regression-gate；而家已經有 EXP-12、14、15、EXP-20261026-01 四個並行測試，切換之前要做 Holm 調整。

## 執行

```bash
cd .agents/skills/nba/nba_daily_auto
PYTHONDONTWRITEBYTECODE=1 python3 nba_season_rate_v4_forward.py --until YYYY-MM-DD
```
