# EXP-20261016-72 結果：同場比率 + 地況扣分集中一處 + 合成跑道

- **預先登記**：[protocol](EXP-20261016-72-au-track-rate-and-centralise-protocol.md)（`0e6ed716`，rebase 後 `f6566014`，量度之前）。
- 證據：`EXP-20261016-72-evidence/`。

## A. 集中扣分 —— 上線（純重構）

② 今場地況往績同 ③ 爛地／重地專項合併成 `_going_adjustment()`：每項數值同次序不變，逐項加落分數（避免浮點次序差），
報告由幾行變**一句**，例如「地況適應：軟地 2 戰未有前列、爛地實績未經驗證（合計 −11.2）」。
`track_detail["going_adjustment"]` 記合計。

驗證：改動前後真引擎 dump，**32,448 匹 feature 同 ability 零差異，排名零改變**。

## B. 同場比率（候選 R）—— REJECT

R：有上名 → 收縮上名率 (上名 + 0.9)/(出賽 + 3)，加分 clip((r − 0.30) × 30, ±9)。

- v3 fixed（2,485 場）：Gold **−0.32pp [−0.69, 0.00]**、Good −0.04pp；NDCG +0.0009 [0.0000, +0.0019]。
- §8：both_arms_reject；fixed OOS Gold −0.41pp，refit Gold +0.14pp，全部 CI 跨零。

EXP-70 量到嘅跨層差距（1 次上名：1–2 戰 +6.9pp、6+ 戰 −11.0pp）係真，但改用比率**冇改善排名** ——
低比率馬嘅弱勢好可能已經由近績同穩定性講咗（同 EXP-70 T1「−2.6 已由其他 leaf 講咗」同一個形態）。研究碼保存喺分支 `claude-au-dist-track-research-20261016`（commit `8fdcf071`），
已由 production 剷走。

## C. 合成跑道

維持當好地處理（現行行為，冇改）。EXP-70 量到乾淨窗 85 場、836 匹、492 匹有 `Synth:` 紀錄；Formguide 有，Facts 冇。
到 100 場就按 EXP-70 T6 嘅候選（`Synth:` 紀錄行乾地規則）登記測。
