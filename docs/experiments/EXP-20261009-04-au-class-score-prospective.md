# EXP-20261009-04 class_score 入排名（現行無 gain 架構，預先登記）—— dev 門檻 REJECT → USER-ACCEPTED EXPERIMENTAL LIVE

- **日期**：2026-10-09
- **平台**：AU
- **假設**：`class_score`（2026-10-09 修正咗「今場降班」錯位、今場獎金改由 RA 補之後）
  有排名價值，加入 `class_weight` 維度可以改善 Gold／Good。
- **搜索過嘅舊記錄**：EXP-20260826-06（原登記，OBSOLETE）、EXP-20260927-01（判 OBSOLETE，
  要求現行架構重新登記）、EXP-20260831-09（直接 class bonus：AUC 0.5620，holdout −0.0026 跨零）、
  EXP-20261009-02（class_move 錯位修正）、記憶 `au-class-label-only-exists-in-holdout`、
  `au-class-adjustment-dead-in-corpus`
- **改到嘅檔案／組件**：冇（scorer 層；通過先另開 release）

## 點解要前瞻 terminal

1. 舊語料 2026-08 起冇今場獎金，`_class_move_today()` 一律未知 —— 語料量到嘅只係
   class_score 嘅一部分；live 由 2026-10-09 起先有完整版本。
2. `au_eval` 嘅 terminal（09-19 → 10-08）落喺 EXP-20261009-01 檢討過嘅窗口入面
   （Stakes 賽偏差就係喺嗰度發現），唔再係乾淨 holdout。

## 鎖定（寫喺量之前）

- **候選**：`ability + c·(class_score − 60)`，`c = MATRIX_WEIGHTS["class_weight"] × k`
  ＝ 喺 `class_weight` 配方加 `("class_score", k)`。
- **k 網格**：{0.15, 0.30, 0.60}；**只用 dev = date < 2026-09-09** 揀，準則 = dev Gold+Good 配對差總和最大，
  打和揀細嘅 k。揀定之後唔再改。
- **dev 門檻**（唔過就唔開 terminal、直接 REJECT）：揀中嘅 k 喺 dev Gold、Good 點估計都 ≥ 0，
  5 個完整賽日 fold 入面 Gold+Good ≥ 0 嘅 fold ≥ 3。
- **terminal**：2026-10-10 起新完成、有賽果、Logic 有今場獎金（`race_analysis.prize > 0`）嘅場次；
  2026-11-09 排程（`au-post-fix-review-2026-11`）時有幾多用幾多，唔延長、唔切日。
  場數少過 600 → `UNRESOLVABLE`，延到 12 月同一規則再判，唔改 k。
- **terminal 判決（Stage 4）**：Gold、Good 點估計都唔可以負，至少一項配對按場 bootstrap 95% CI
  下界 > 0；馬匹數 cohort（≤8／9-10／11-12／13+）冇一格 CI 全負。過咗都只係候選，要另開 release
  同 owner `/approve SHA`。

## Dev 結果

語料：現行引擎（已含 EXP-20261009-02 修正）全語料重評分 `au_dump_engine_leaves.py`，
dev = 2025-08-02 → 2026-09-08，2,087 場。配對 bootstrap 按場、2,000 次、seed 7。

| k | Gold | Good位 | Gold+Good 合計 | fold ≥0 |
|---|---|---|---:|---:|
| 0.15 | −0.10pp [−0.34, +0.14] | +0.19pp [+0.05, +0.38] | +2 場 | 3/5 |
| 0.30 | +0.10pp [−0.24, +0.43] | −0.05pp [−0.43, +0.34] | +1 場 | 3/5 |
| 0.60 | −0.14pp [−0.67, +0.34] | −0.24pp [−0.82, +0.29] | −8 場 | 2/5 |

照預先準則揀 k = 0.15（合計最大），但 dev Gold 點估計 −0.10pp < 0 → **過唔到 dev 門檻**。

## 檢查
- **leakage-audit**：PASS —— class_score 全部由賽前賽績表同今場排位表計。
- **golden_scoring**：冇郁（冇改 code）

## 結論
**REJECT（dev 門檻），terminal 唔開。** 同 EXP-20260831-09 一致：class_score 有單獨判別力，但加入排名
之後 Gold／Good 冇同時改善 —— 佢講嘅嘢大部分已經由 `rating_score` 講咗。

保留意見：dev 語料 2026-08 起冇今場獎金，修正後 `_class_move_today()` 喺嗰段一律未知，所以 dev 量到嘅係
class_score 嘅部分版本。要測完整版，只可以等 2026-10-09 之後有今場獎金嘅數據累積（建議 ≥ 3 個月），
再**另開新實驗**重新登記，唔可以喺今次結果上改 k 或者改門檻。

**決定（統計）**：REJECT（dev 門檻）

## 2026-10-09 用戶決定：USER-ACCEPTED EXPERIMENTAL LIVE

睇咗 k=0.15 嘅完整 dev 指標之後，Kelvin 明確接受少 2 場 Gold 換其他指標：

| 指標 | Δ | 95% CI |
|---|---:|---|
| Gold | −0.10pp | [−0.34, +0.14] |
| Good位 | +0.19pp | [+0.05, +0.38] |
| Pass | +0.10pp | [−0.29, +0.48] |
| 首選勝出 | +0.19pp | [−0.14, +0.53] |
| 頭馬喺頭三揀 | +0.24pp | [−0.10, +0.58] |
| top3_capture_at5 | +0.08pp | [−0.06, +0.22] |
| NDCG@5 | +0.13 | [+0.02, +0.25] |
| MRR | +0.14 | [−0.03, +0.30] |
| Top5 AUC | +0.00069 | [−0.00023, +0.00167] |

**呢個唔係已證實嘅改善**，Stage 4 原判保留。先例：HKJC EXP-20260929-01、EXP-20261008-03。

- **上線內容**：`matrix_mapper.MATRIX_FORMULAS["class_weight"]` 加 `("class_score", 0.15)`；
  `class_score` 由 REPORT_ONLY 移去 ABILITY（`scoring.CLASS_SCORE_LIVE`）。
- **真引擎核對**：全語料重評分，dev 2,085 場 Gold −2 場、Good +4 場，同 scorer 模擬一致。
- **即時回退**：`WC_AU_CLASS_SCORE_LIVE=0`（ability 同 golden 都返舊值）。
- **回退影子**：每匹馬 `python_auto.class_score_live_delta`；舊公式分 = 綜合分 − 呢個數。
- **前瞻回退閘**：上線後 ≥600 場（有今場獎金），新舊公式配對比較；舊公式淨贏 ≥2 場 Gold 或 Good
  而另一項非負 → 建議回退（2026-11-09 排程 `au-post-fix-review-2026-11` 檢查；唔會自動改 production）。
- **golden**：保留原 120 個樣本，只用新 code 重算預期值（82 匹變，全部只係 class_weight → 綜合分 → 評級）。

**commit**：見 release
