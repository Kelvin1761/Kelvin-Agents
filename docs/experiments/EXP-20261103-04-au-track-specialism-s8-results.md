# EXP-20261103-04 結果：場地 SP 用 §8 兩邊 refit —— REJECT（both_arms_reject）

預先登記：`EXP-20261103-04-au-track-specialism-s8-protocol.md`。baseline `b34b8b07`。

## 判決

`evaluate_with_refit_arms` → **REJECT / both_arms_reject**，package 冇。live 唔郁。

判決窗 = walk-forward 預測覆蓋嘅場次：2026-09-05 起 **2,299 場、59 個賽日**（頭 30 個賽日係 warmup）。
refit procedure hash（B0 = B1）：`b4b19098955d19cd8c2dba339ff8703b758cbb0e39e20e0fb16d4650142b1c8c`。

| arm | 判決 | Gold | Good | top3_capture | NDCG@5 | 前五 AUC |
|---|---|---|---|---|---|---|
| fixed A1 vs A0 | REJECT / ranking_evidence_too_weak | +0.30 [−0.31, +0.85] | +0.04 [−0.75, +0.79] | +0.20 [−0.03, +0.43] | +0.11 [−0.10, +0.30] | +0.11 [−0.05, +0.26] |
| refit B1 vs B0 | REJECT / primary_regression | +0.09 [−0.74, +0.80] | −0.09 [−0.78, +0.68] | +0.17 [−0.09, +0.48] | +0.09 [−0.18, +0.37] | +0.07 [−0.14, +0.28] |
| live guard B1 vs A0 | REJECT / primary_regression | | | | | |

（Gold／Good 單位 pp；排序指標 ×100。）Holm p：fixed 1.0、refit 1.0。

| arm | Gold | Good | Pass |
|---|---|---|---|
| A0 現行 | 21.49% | 27.10% | 51.46% |
| A1 SP | 21.79% | 27.14% | 51.07% |
| B0 refit | 21.75% | 26.79% | 51.33% |
| B1 SP + refit | 21.84% | 26.71% | 51.37% |

分層：fixed 同 refit 都冇 CI 全負（最差係重地 Good −1.43pp [−4.11, 0.00]，細樣本）。

## 讀法

1. **舊權重唔係問題所在。** 用 walk-forward 俾 SP 自己 fit 權重（B1 vs B0），排序指標升幅反而細過固定權重
   （NDCG +0.09 vs +0.11），Good 轉負。即係 SP 嘅 leaf 改善（AUC +0.019）唔係「被舊權重聽唔到」，而係真係太細。
2. **refit 程序本身多數 fallback。** 9 個窗：BASE 6 個、SP 4 個用返現行權重（共識過唔到閘），即係呢個語料
   未有足夠證據支持郁權重 —— 同「重配份額過唔到 holdout（第五次）」一致。
3. **固定權重版係 EXP-20261103-01 之後最接近嘅一次**：喺 09-05 起窗口 Gold、Good 都係正，但排序 CI 跨零。
   同 EXP-01（全窗 3,302 場：排序 CI 全正、Good −1 場）一齊睇，SP 係一個真但細過閘門解析度嘅改善。

## 「搵返 Good −0.12pp」

- stale（B0 vs A0，修正後 baseline 上 walk-forward 重配權重）：Gold +0.26 [−0.10, +0.69]、**Good −0.30 [−0.83, +0.22]**，
  REJECT。重配權重唔會搵返，現行權重仲係最好。
- 嗰 −0.12pp 全部喺 2026-08 嘅 130 場（呢個判決窗嘅 warmup 之前），嚟自剷走一個讀錯數據嘅副作用。
  冇合法方法喺唔過擬合嘅情況下追返：預先登記已經寫明唔會專登 fit 嗰 4 場。

## 偏離預先登記（只係工具精度，冇改 fit 程序）

`au_walkforward_refit.verify` 拒絕 SP dump：33,000 匹得 1 匹（2026-09-02 Warwick Farm R1 Bring Me Chocolate，
59.3944 vs 59.3943）replica 同引擎差一個 4 位小數單位 —— dump 將 leaf 存 6 位令捨入打和翻轉，同 SP 無關
（嗰匹 track_score 66.98 係整數位）。容忍度由 5.1e-5 改做 1.01e-4（一個捨入單位）；fit 程序（`PROCEDURE`）冇改，
但 source hash 變咗，所以 **B0、B1 兩邊用新 hash 重跑**（hash 相同，§8 對稱）。試過將 SP leaf 捨入到 2 位，冇解決，已還原。

## 可重現

    WC_AU_TRACK_SPECIALISM_ARM=SP python3 au_dump_engine_leaves.py --out SP.json      # BASE = 唔設
    python3 au_walkforward_refit.py predict --data {BASE,SP}.json --out wf_{BASE,SP}.json
    python3 scratch/au_track_sp_s8_judge_20261103.py DUMP_DIR judge.json

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/track-s8/`。研究碼：分支 `claude-track-sp-s8-20261103`（唔入 main）。
