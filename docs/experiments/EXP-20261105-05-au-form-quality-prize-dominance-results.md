# EXP-20261105-05 結果：C1（獎金 z 對稱上限）§8 WIN；C2、C3 REJECT

- **預先登記**：[protocol](EXP-20261105-05-au-form-quality-prize-dominance-protocol.md)（含 C3 補充）。
- **語料**：全語料 dump 4,210+ 場；v3 fixed_rule 08-05 起 3,433 場；§8 walk-forward 2,430 場、61 賽日。

| 候選 | v3 fixed（3,433 場） | §8 | 跨三候選 Holm |
|---|---|---|---|
| **C1 z_獎金 夾 ±1.567** | Gold +0.03、Good +0.20、top3@5 +0.24 [0.00, +0.49]、AUC +0.23 [+0.07, +0.39] | **RANKING_WIN**（refit arm；arm-Holm p 0.004） | **p ≈ 0.012 ✅** |
| C2 跑得好先攞獎金分 | Good **+0.79 [+0.11, +1.52]**、Gold −0.03 | REJECT / both_arms_reject | — |
| C3 PF 場數收縮 n/(n+2) | 全部 CI 跨零 | REJECT / both_arms_reject | — |

### C1 §8 細節

| arm | Gold | Good | top3_capture_at5 | top5 AUC |
|---|---|---|---|---|
| fixed（現行權重） | +0.04 [−0.44, +0.48] | +0.37 [−0.19, +0.95] | +0.26 | +0.22 [+0.00, +0.41] |
| **refit（重配權重）** | +0.17 [−0.46, +0.76] | +0.29 [−0.50, +1.06] | **+0.47 [+0.16, +0.77]** | **+0.32 [+0.08, +0.54]** |

- 分層：refit arm 冇 CI 全負；fixed arm 有（§8：13 匹以上 Gold；v3：≤1200m Gold）→ **C1 只可以連 refit 權重一齊上**。
- stale 檢查（BASE 自己 refit vs 現行）REJECT —— 改善嚟自 C1，唔係單純重配權重。
- refit 最後窗權重（現行 → C1）：stability 0.371→0.344、pace_perf 0.114→0.104、jockey_trainer 0.663→0.734、
  class_weight 0.383→0.325、track 0.141→0.100、preparation 0.252→0.316。

### 用戶點名嘅個案（2026-11-05 Flemington，scratch 副本重評，C1 + refit 權重）

| 馬 | 排名 | 近績質素 |
|---|---|---|
| R5 Single Choice（轉程 −5 都排第 1） | 1 → 5 | 95 → 85.2 |
| R9 Rey Magnerio | 1 → 3 | 100 → 74.3 |
| R6 Naraghi | 2 → 7 | 92.4 → 70.7 |
| R3 Feroce | 2 → 6 | 68.6 → 47.3 |

**轉程扣分**：原本問題係近績質素被獎金頂到 100 封頂（z +2.39 = 107.8），−5 之後仍然 95。C1 之後唔再撞頂，−5 實際生效；
唔另外加封頂（會係一個未經測試嘅新規則）。

**C3**：「一場 PF 就 94–99 分」嘅問題係真，但收縮之後排名冇改善（§8 兩邊 REJECT）—— 記錄，唔上。
