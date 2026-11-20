# EXP-20261121-30 預先登記：濕地往績 overlay 按濕度調幅度（walk-forward）

> 量度之前寫（未睇任何候選賽果）。結果另寫 `EXP-20261121-30-au-wet-overlay-by-wetness-results.md`。

- **提出**：用戶 2026-11-21「大爛地表現好差，可以點改善？」
- **baseline**：`FINAL.json`（`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/`，main `1c33b058` 評分；
  之後 AU 引擎冇改評分）。判決窗 2026-08-05 起。

## 寫登記之前已知（描述，唔做判決）

08-05 起、按評分用嘅地況：

| 地況 | 場 | 模型 Gold／Good | 市場 Gold／Good | 模型 AUC | 市場 AUC |
|---|---:|---|---|---:|---:|
| 好地 | 1,741 | 22.5／26.7 | 31.0／37.1 | 0.692 | 0.762 |
| Soft 5–6 | 1,424 | 20.2／26.9 | 28.4／36.2 | 0.677 | 0.756 |
| Soft 7+ | 255 | 13.3／26.7 | 25.5／34.5 | 0.659 | 0.738 |
| 大爛地 | 198 | 22.7／24.7 | 32.8／37.9 | 0.655 | 0.746 |

- 由好地去大爛地，模型 AUC 跌 0.037、市場只跌 0.016 —— 濕地退步大約係市場兩倍。
- 往績類 leaf 喺大爛地跌最多（近績質素 −0.039、近績 −0.037、練馬師 −0.035、L600 −0.023）。
- **濕地往績 overlay** 場內 AUC：Soft 7+ 0.561、大爛地 **0.593**，係大爛地最有預測力嘅訊號之一；但現行幅度
  （`WET_FORM_FEATURE_SCALE` 14.852、封頂 ±6.18）喺 Soft 5、Soft 7、大爛地完全一樣。
- 以前測過（EXP-20260822-03，423 場濕地）：剷走、按地況分開、只用對應地況、收縮加到 12、**整體**幅度減半 —— 全部打和；
  **未測過按濕度分開調幅度**。EXP-20261105-06 H2（大爛地近績質素用舊公式）forward 跟緊，同今次唔重疊（今次唔郁近績質素）。

## 候選 M1（唯一一個 arm）

- 每匹馬 `ability' = ability + (m_s − 1) × wet`，`wet` = 現行 overlay 值（dump 已存），s = 評分用嘅地況：
  **大爛地**（Heavy）／**Soft 7+**／**其他有 overlay 嘅濕地**（Soft ≤ 6）。乾地冇 overlay，唔郁。
- **m_s 由 walk-forward 擬合**（mode `walk_forward_oos`）：每個賽日 t 只用 t 之前嘅賽日，逐匹 logistic
  `入前三 ~ a + b·(base − 場均 base) + Σ_s c_s·1[s]·wet`，base = ability − wet；m_s = c_s ÷ b，夾 [0, 4]。
  b ≤ 0 或者唔收斂 → 當日 m = 1（等於現行）。頭 **20 個賽日** warmup：m = 1。
- 預先寫死：三個地況組、夾範圍、warmup、模型式。**唔准改**。

## 判決

- 合約 v3，`mode="walk_forward_oos"`，primary Gold／Good，ranking `top3_capture_at5`／`ndcg_at5`／`top5_pairwise_auc`，
  賽日 bootstrap 2000。§8 唔適用（overlay 幅度，唔改 leaf）。
- 預先聲明分層（任何一個 CI 全負 → 唔上線）：judge 內置（馬群、地況、首選 SP、路程、首選跑法）。**另外大爛地同 Soft 7+ 單獨報**（描述）。
- 單一 arm，唔使 Holm。冇 WIN → REJECT。

## 描述（唔做判決）

- 每個賽日 m_s 走勢、最後 m_s；三個地況組各自 Gold／Good 差同頭三命中分佈。

## 功效警告（先講）

只有濕地場次會郁（約 1,877 場），大爛地 198 場。v3 primary 用全紀錄 3,700 場平均，濕地以外嘅場 Δ = 0，所以整體效應會被攤薄；
大爛地本身 1 場 ≈ 0.5pp。冇 WIN 唔代表冇效應。

## 唔准做嘅嘢

改地況分組、夾範圍、warmup；睇完結果加 arm；只揀大爛地做主判決。
