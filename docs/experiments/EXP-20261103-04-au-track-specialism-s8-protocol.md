# EXP-20261103-04 預先登記：場地「相對生涯專長」（SP）用 §8 兩邊 refit 重測

> 量度之前寫。結果另寫 `EXP-20261103-04-au-track-specialism-s8-results.md`。

- **日期**：2026-11-03；**平台**：AU；**baseline**：`origin/main` `b34b8b07`（包括 `cc09e1a5` 截斷紀錄修正）。
- **用戶**：「see if we can find performance from other dimension, from those 會更準 但係 signal 俾其他地方食左既 experiment」
  →「yes go. and see if we can find the performance back for the good −0.12pp」。

## 點解短名單得一個

合約 §8：重測舊 REJECT 要「揀一張短名單，預先登記成一個 family」，唔准逐個舊 REJECT 用 B arm 再試。
入選條件（全部要符合）：① leaf 準確度有顯著改善（CI 唔跨零）；② **未用 §8 測過**；③ 08-05 起乾淨、冇洩漏；
④ 改嘅係**已經有權重**嘅 leaf（加零權重 leaf 唔係 §8 嘅範圍，亦試過失敗）。

| 舊候選 | 結果 | 入唔入 |
|---|---|---|
| **場地 SP（EXP-20261103-01）** | leaf AUC +0.0191 [+0.0133, +0.0253]；fixed arm Good −0.03pp（1 場） | **入** |
| 全程速度（EXP-20261101-41） | 已用 §8：both_arms_reject | ✗ ② |
| 位置估算 L600（EXP-20261101-40） | 已用 §8 | ✗ ② |
| L600 point-in-time 標準（EXP-20261101-31／33） | 已用 §8 | ✗ ② |
| 試閘（EXP-20261016-77／79） | 已用 §8 | ✗ ② |
| 路程分重新定中心（EXP-20260901-03） | `distance_score` 冇入任何維度 | ✗ ④ |
| 預測起步位（EXP-20260902-05） | 新特徵，冇現成維度 | ✗ ④ |

## 候選（同 EXP-20261103-01 SP 一模一樣，常數唔改）

    生涯率 c = (生涯上名 + K·P0) / (生涯出賽 + K)          生涯紀錄唔齊 → c = P0
    專長 rel(紀錄) = (上名 + K·c) / (出賽 + K) − c            冇出賽／紀錄唔齊 → 0
    track_score = clip(60 + S × (rel(同場) + rel(今日地況 bucket)), 0, 100)

K = 4、P0 = 0.3715、S = 50；今日 bucket 好地／軟地／重地，好地 = `going_stats_line` 第一段。濕地 overlay 照舊。
開關：`WC_AU_TRACK_SPECIALISM_ARM=SP`（預設關）。

## 四個 arm（§8）

| | 現行權重 | walk-forward refit（`au_walkforward_refit.py predict`） |
|---|---|---|
| baseline | A0 | B0 |
| SP | A1 | B1 |

refit 程序 = `au_walkforward_refit.PROCEDURE`（EXP-20261015-02：warmup 30 賽日、7 日窗、256 draws、seed 7、place 目標、
五塊四塊不負、逐維度中位數共識、fallback 現行權重）。B0／B1 用同一 commit 跑，procedure hash 一樣先判。

## 判決（`model_evaluation_decision.evaluate_with_refit_arms`）

fixed arm A1 vs A0（`fixed_rule`）同 refit arm B1 vs B0（`walk_forward_oos`）一個 family，Holm；
ranking metrics `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`；賽日 bootstrap（判決器預設）。
採用：判決器俾 `candidate_with_live_weights` 或 `candidate_with_refit_weights`，**而且**預先聲明分層
（馬匹數、今場地況、首選 SP、路程，Gold／Good）冇 CI 全負。否則 REJECT，記錄點失敗，live 唔郁。

## 「搵返 Good −0.12pp」—— 點樣量、點樣唔量

`cc09e1a5` 嗰 −0.12pp 嚟自剷走一個讀錯數據嘅副作用（扣「出賽多」），而且全部喺 2026-08 嘅 130 場。
**唔會**專登設計一個特徵去追返嗰 4 場 —— 喺 130 場入面 fit 4 場係純過擬合。
會報告 **stale 比較 B0 vs A0**：喺修正後嘅 baseline 上，walk-forward 重配權重本身有冇幫手。
如果 B0 贏 A0，嗰份係純權重候選，要另開實驗過閘，唔可以夾帶上線。

## 唔准

睇完結果改 K、P0、S、arm 定義、refit 程序或者 ranking metrics；要改就開新實驗。
