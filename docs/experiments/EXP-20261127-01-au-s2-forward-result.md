# EXP-20261127-01 S2 forward shadow（EXP-20261016-03）唯一一次評估 —— ship_eligible（PRIMARY_WIN）

- 日期：2026-11-27　平台：AU　類型：forward 判決（一個 family 只開一次；用登記時嘅尺 v3 `evaluate_full_record`，唔追溯用 log-loss 尺）
- 觸發：forward tracker「S2 forward 41/41 賽日」Telegram。結果檔：`EXP-20261016-03-forward/forward_result.json`（一經寫入唔准改）。

## 評估前修正（冇睇指標）

1. **凍結 commit**：tracker 提示嘅 `c242b6c1` 有 5 個檔 hash 唔夾。逐個 commit 對 `freeze.json` 21 個 sha256 → `3903102b`
   （2026-10-16 00:48「S2 forward shadow 凍結」）全部夾，用佢。
2. **快照已搬外置碟**：凍結版腳本直讀 `<場次>/_prediction_snapshots/`（offload 機制 2026-11 先有），`status` 只見 15／41 賽日
   （176 場次 `no_pre_cutoff_snapshot`）。用指定工具 `offload_prediction_snapshots.py --restore` 攞返 176 個場次（1.8GB），
   再 `status`：41／41、冇跳過、code drift 冇 → 先跑 `evaluate`。（每晚 durability job 會再搬返去外置碟。）
   ⚠️ 教訓：forward tracker 嘅 41／41 係用 scheduler 自己數法，唔等於凍結腳本讀得到；其他舊 forward 評估前都要先 `status`。

## 結果（1,812 場、41 個賽日，10-17 → 11-23，全部未睇過）

| 比較 | Gold Δ [95%]（p） | Good Δ [95%] | capture@5 | NDCG@5 | 頭五 AUC Δ [95%] | 判決 |
|---|---|---|---|---|---|---|
| **B1 vs B0（主）** | **+1.27pp [+0.34, +2.16]**（0.004） | +0.88 [−0.20, +1.85] | +0.23 | +0.45 [+0.10, +0.77] | +0.0047 [+0.0016, +0.0076] | **PRIMARY_WIN** |
| **B1 vs A0（guard）** | **+1.27pp [+0.67, +1.88]**（<0.001） | +0.66 [−0.31, +1.65] | +0.37 | +0.37 | +0.0052 [+0.0024, +0.0078] | PRIMARY_WIN（過 guard） |
| B0 vs A0（參考） | 0.00 | −0.22 | +0.15 | −0.08 | +0.0005 | REJECT（淨換權重冇用） |

Gold：A0 20.70% → B1 21.96%；6 塊 Gold 5 正 1 負。**改善來自 S2 leaf（L600 同 Sportsbet 全程速度各半），唔係換權重。**

## 限制同下一步

- A0／B0／B1 全部係 **10-16 凍結引擎**。之後 live 加咗 C2 refit、F1、R2、老馬、練馬師剩餘表現、WinningTime 速度分（11-24）。
  S2 嘅全程速度同 11-24 速度分係同一類資訊，可能重疊。**唔可以直接搬 10-16 權重上 live。**
- 下一步（要 Kelvin 批）：將 S2 leaf 改動移植去現行 live，用 log-loss v2 尺量「S2 單獨／S2＋速度分／S2 取代速度分」，
  一樣嘢一個標準，留較好嗰個。
