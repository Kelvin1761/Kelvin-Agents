# HKJC 現行引擎 readiness health-slot replay

## 範圍

- 完整現行引擎重播：118 場，12 個賽日。
- 主比較：現行正式 Top 2 對 frozen `readiness_health_slot` shadow Top 2。
- 賽果只用於重算完成後評分；公式及 gate 沒有因應本批結果再調整。
- 原始 Google Drive meeting folders 全程唯讀；所有引擎輸出只寫入臨時目錄。

## 分析表現

| 範圍 | 場數 | 現行 0/1/2 hit | Shadow 0/1/2 hit | Hits Δ | 頭馬 Top2 Δ | Top2 改動 |
|---|---:|---:|---:|---:|---:|---:|
| 合計 | 118 | 33/61/24 | 33/57/28 | +4 | +3 | 14 |
| external_2026_07_15 | 9 | 4/2/3 | 4/2/3 | +0 | +0 | 0 |
| independent_recent | 109 | 29/59/21 | 29/55/25 | +4 | +3 | 14 |
| HappyValley | 43 | 14/20/9 | 14/19/10 | +1 | +0 | 1 |
| ShaTin | 75 | 19/41/15 | 19/38/18 | +3 | +3 | 13 |

## 0/1-hit 與第3選救援

- 0-hit：33 → 33；0→有命中 2 場。
- Top 2 命中率：46.2% → 47.9%（+1.7pp）；二中二場率 20.3% → 23.7%。
- 1→2 hit：4 場；1→0 hit：2 場；2→下跌：0 場。
- 有效替換／有害替換：6 / 2。
- 現行第3選有效救援／有害升級：6 / 2。
- 代價：第一選中頭馬 29 → 28（-1）；但用戶投注決策範圍係 Top 2，頭馬 Top 2 仍然改善。
- 觸發集中：沙田改動 13 場；跑馬地只改動 1 場。

## 現行引擎本身（對舊 stored ranking）

- 舊 stored Top 2：0/1/2 hit = 42/57/19，總 hits 95，頭馬 Top 2 38。
- 現行引擎 Top 2：0/1/2 hit = 33/61/24，總 hits 109，頭馬 Top 2 45。
- 版本漂移：0-hit -9、總 hits +14、頭馬 Top 2 +7。
- 注意：現行 replay 使用目前兩季 prior tables，因此呢段 stored→current 差異只係版本漂移診斷，唔當成無偷睇 point-in-time 改善證據。主晉升證據係同一現行引擎 base/shadow 配對結果，再配合先前 157 場 frozen stored-matrix holdout。

## 驗證與決定

- 兩次現行引擎重跑完全一致：是。
- Logic/Facts/racecard scoring-context 完整性錯誤：0（trackwork header fallback 屬 optional）。
- 晉升 gate：PASS。

- 正式主線對凍結 shadow 逐場 parity：FAIL（118場，15個不一致）。
- 晉升後 readiness shadow 與主線相同，所以 base/shadow 改動數 gate 不再適用；正式決定以晉升前 evidence gate 加本次逐場 parity 為準。

結論：readiness health-slot 喺現行引擎 replay 仍然有非傷害兼正面訊號，可以進入正式 scoring 晉升評估。
