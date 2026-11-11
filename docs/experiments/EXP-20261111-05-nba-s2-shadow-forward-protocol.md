# EXP-20261111-05 協議：自己模型佔更大份額（市場＋S2）—— shadow 接線＋forward 預先登記

- **日期**：2026-11-11（喺任何 forward 數據存在之前 commit）
- **平台**：NBA
- **決定人**：Kelvin（2026-11-11：「go ahead and implement」「go ahead and 接 shadow 並登記 forward 測試」；目標係 S 佔更大份額）
- **凍結**：判決腳本 `docs/experiments/patches/nba_s2_forward/evaluate.py`；時間模型係數 `nba_engine/config.json` 嘅 `minutes_v2`；兩個混合公式嘅係數寫死喺判決腳本。全部同本文件同一個 commit。
- **唔改發佈機率**：`p_final` 照舊係 MS（`probability_model_id` 不變）；B2、精選、SGM 全部唔受影響。

## 接咗乜（shadow）
- `nba_minutes.py`：每場賽前用 ESPN 例行賽 box score（同 extractor 已經讀緊嗰批，只用比賽日之前）同原始 summary 嘅正選標記，計每個球員嘅時間特徵 → `nba_game_data_<TAG>.json` 嘅 `minutes_context`。
- `nba_engine`：每條腿多一個 `p_s2`（S 嘅均值乘以 v2 時間 ÷ 基本時間，比例夾喺 0.5–1.6）同 `minutes_ratio`；寫入 sidecar 同 ledger `model_obs`。讓分用 21:00 Sportsbet `game_lines.spread_away`。
- 母體同擬合一樣：今季 ≥5 場、基本預測 ≥15 分鐘、有讓分；其餘 `p_s2` = None。
- 核對：重建 2026-11-05、11-09 共 195 個球員-場次，特徵同研究語料 0 差；11-09 DEN_HOU 端到端 196 腿，`p_final` 完全一樣，`p_s2` 149 條。

## 擬合（11-03…11-10，7,520 腿，唔再郁）
`logit p = a_stat + β·logit(clip(1/價)) + γ·logit(clip(S))`，clip 0.02–0.98：

| 混合 | 用嘅 S | a PTS／REB／AST／3PM | β（市場） | γ（S） |
|---|---|---|---|---|
| 現行 MS（發佈） | S | −0.4057／−0.2735／−0.4232／−0.0624 | 0.9264 | 0.1099 |
| **MS2（候選）** | **S2** | −0.2285／−0.1958／−0.1767／−0.0545 | **0.6514** | **0.3494** |
| MSR（對照：同一批數據重擬合舊 S） | S | −0.2473／−0.2090／−0.1993／−0.0728 | 0.7087 | 0.2868 |

- 喺同一批數據留一日法：MS2 0.4542、MSR 0.4546、發佈 MS 0.4556；MS2 − 發佈 −0.0014 [−0.0035, +0.0012]；MS2 − MSR −0.0004 [−0.0007, −0.0001]。
- 即係話：S 份額升到 0.29–0.35 喺樣本內比現行好啲，但 CI 跨零；新時間預測再加少少。**樣本內，唔係證據。**
- 警告：MS 嘅原本擬合係 10-22…10-28，而家呢批日子包括咗佢之後嘅數據；7 日、全部季初。

## 判決（全部凍結）
- **母體**：target_date ≥ 2026-11-12；每條腿第一個開波前 `production` `model_obs`，要同時有 `p_final`、`p_s`、`p_s2`、價同結算（void 唔計）。
- **主指標**：Δ = 平均 log-loss(MS2) − 平均 log-loss(`p_final`)。
- **夠數**：≥14 個比賽日而且 ≥10,000 腿；用到夠數嗰日為止（成日計），判一次，結果凍結。
- **PASS**：Δ 嘅 95% CI 上限 < 0（按日 cluster bootstrap，2,000 次，seed 20261111）。
- 次要（只報告）：MSR − 發佈（「純粹重擬合」有幾多）、MS2 − MSR（新時間預測有幾多）、S2 − S、逐 stat Δ。
- 夠數由 `nba_forward_tracker` 自動判一次，Telegram primary 推一次。

## 功效（預先講明）
11-03…11-10 每日約 1,000 條有 `p_s2` 嘅腿 → 14 日約 14,000 腿，大約兩個星期夠數。留一日法嘅 Δ CI 闊約 ±0.0025，所以真改善要 ≳0.002 先判得出。

## 洩漏檢查
- 時間特徵只用比賽日之前嘅比賽（`history_cutoff_day`）；正選標記係嗰啲舊比賽嘅；讓分係 21:00 抽嘅。
- 混合係數喺 forward 開始之前定死；判決只用 11-12 之後嘅腿。

## 判決之後
- PASS：申請將發佈機率換做 MS2，要過 `model-regression-gate`，由 Kelvin 決定。
- 未過：記低，維持 MS。唔准喺同一批數據改係數、改窗、改門檻再判。

## 重跑
```bash
python3 docs/experiments/patches/nba_s2_forward/evaluate.py status
python3 docs/experiments/patches/nba_s2_forward/evaluate.py evaluate
```
