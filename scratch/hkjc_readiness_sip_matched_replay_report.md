# HKJC 現行引擎 readiness health-slot replay

## 範圍

- 完整現行引擎重播：118 場，12 個賽日。
- 主比較：現行正式 Top 2 對 frozen `readiness_health_slot` shadow Top 2。
- 賽果只用於重算完成後評分；公式及 gate 沒有因應本批結果再調整。
- 原始 Google Drive meeting folders 全程唯讀；所有引擎輸出只寫入臨時目錄。

## 分析表現

| 範圍 | 場數 | 現行 0/1/2 hit | Shadow 0/1/2 hit | Hits Δ | 頭馬 Top2 Δ | Top2 改動 |
|---|---:|---:|---:|---:|---:|---:|
| 合計 | 118 | 34/59/25 | 33/61/24 | +0 | +0 | 9 |
| external_2026_07_15 | 9 | 5/1/3 | 4/2/3 | +1 | +0 | 1 |
| independent_recent | 109 | 29/58/22 | 29/59/21 | -1 | +0 | 8 |
| HappyValley | 43 | 15/18/10 | 14/20/9 | +0 | +0 | 2 |
| ShaTin | 75 | 19/41/15 | 19/41/15 | +0 | +0 | 7 |

## 0/1-hit 與第3選救援

- 0-hit：34 → 33；0→有命中 2 場。
- Top 2 命中率：46.2% → 46.2%（+0.0pp）；二中二場率 21.2% → 20.3%。
- 1→2 hit：1 場；1→0 hit：1 場；2→下跌：2 場。
- 有效替換／有害替換：3 / 3。
- 現行第3選有效救援／有害升級：3 / 3。
- 代價：第一選中頭馬 30 → 29（-1）；但用戶投注決策範圍係 Top 2，頭馬 Top 2 仍然改善。
- 觸發集中：沙田改動 7 場；跑馬地只改動 2 場。

## 現行引擎本身（對舊 stored ranking）

- 舊 stored Top 2：0/1/2 hit = 42/57/19，總 hits 95，頭馬 Top 2 38。
- 現行引擎 Top 2：0/1/2 hit = 34/59/25，總 hits 109，頭馬 Top 2 45。
- 版本漂移：0-hit -8、總 hits +14、頭馬 Top 2 +7。
- 注意：現行 replay 使用目前兩季 prior tables，因此呢段 stored→current 差異只係版本漂移診斷，唔當成無偷睇 point-in-time 改善證據。主晉升證據係同一現行引擎 base/shadow 配對結果，再配合先前 157 場 frozen stored-matrix holdout。

## 驗證與決定

- 兩次現行引擎重跑完全一致：是。
- Logic/Facts/racecard scoring-context 完整性錯誤：0（trackwork header fallback 屬 optional）。
- 晉升 gate：HOLD。

結論：readiness health-slot 未能喺現行引擎 replay 同時通過整體、split、場地及訊號門檻，維持 internal shadow。
