# EXP-20261016-31 預先登記：騎練訊號內部份額按 AUC − 0.5 分配（單一固定候選，§8 兩邊都 refit）

> 量度之前寫。結果另寫 `EXP-20261016-31-au-jockey-trainer-inner-shares-results.md`。

- **日期**：2026-10-16；**平台**：AU；**baseline**：main `05dd1b20`。
- **用戶指示**：「預先登記 EXP-20261016-31：騎練訊號內部份額只用一個固定候選（按 AUC − 0.5 比例分配），用 §8 兩邊都 refit 判。」
- **現況**：騎練訊號 = 0.333333 騎師分 + 0.285714 練馬師分 + 0.380952 人馬配搭分（係數 0.6627）。
  EXP-20261016-12 J6 喺**成個乾淨窗**量到場內入位 AUC：騎師 0.5884、練馬師 0.5968、人馬配搭 0.5622
  —— 最唔準嗰個份額最大。呢組數包含 OOS 日子，**唔用嚟砌候選**。
- **之前**：重配**維度之間**份額五次過唔到 holdout；**維度內**份額從來冇 fit 過，refit 程序亦唔會郁佢。

## 候選（單一、固定，喺睇任何 arm 之前由規則決定）

```
AUC_k = 場內入位 pairwise AUC（入位 = 名次 ≤ 派彩位數；8 匹以上 3 位，否則 2 位）
        只用乾淨窗 2026-08-05 → 2026-09-04（walk-forward 暖身 30 日，即 OOS 第一日之前）
share_k = (AUC_k − 0.5) / Σ (AUC_j − 0.5)
```

如果任何 AUC_k ≤ 0.5 → 停，唔測（份額會變負，規則唔適用）。份額四捨五入到 6 位小數，總和 = 1。
其他一切（leaf 公式、維度係數 0.6627、其他維度）不變。

## 語料同工具

- dump：`scratch/au_jt_audit_dump_20261016.py` 喺 `05dd1b20` 跑，用 `k2` 特徵做 production baseline。
- 研究變體：`scratch/au_paceperf_variants_20261016.py` 加 `jt_auc` 變體，只喺研究 process patch
  `MATRIX_FORMULAS["jockey_trainer"]`；dump、arm 重算同 refit 三個 process 用同一個變體。
- refit：`au_walkforward_refit.py` 程序 hash `f92c8377…`（同 EXP-06／09／10／12），兩邊一樣。

## 判決（合約 §8，判決器 `evaluate_with_refit_arms`）

- A0 = baseline leaf + live 權重；A1 = 候選份額 + live 權重；B0／B1 = 各自 walk-forward refit。
- fixed arm（A1 vs A0）WIN → 用 live 權重上線。否則 refit arm（B1 vs B0）WIN 而 live guard（B1 vs A0）唔係
  `primary_regression`／`ranking_metric_harm` → 份額連 refit 權重一齊上線。兩個 arm 做 Holm。其他一律 REJECT。
- 另報 v3 fixed_rule 全紀錄（2,485 場）同跑包尾（頭兩名 $15+ 跑尾三分一），只作參考。

## 詮釋同限制（照寫）

- §8 原文話「純權重候選唔適用」。今次份額唔喺 refit 程序 fit 範圍入面，所以當一個「改變維度資訊組合」嘅候選用 §8 判；
  呢個詮釋喺登記時已寫明，唔係睇完結果先揀。
- §8 判決器喺 `claude-refit-both-arms-20261015`，**未發佈去 main**。候選就算贏，都要先發佈 §8 把尺，再發模型改動。
- 同一個 41 日 OOS 窗已經用過多次（EXP-06／09／10／12）；就算 WIN，亦要記錄為「重用窗口嘅證據」。

## 唔准做

改 AUC 定義、暖身截止日或者份額公式；試第二組份額；改其他維度。
