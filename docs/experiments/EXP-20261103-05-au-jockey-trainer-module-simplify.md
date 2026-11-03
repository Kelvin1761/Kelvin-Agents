# EXP-20261103-05 AU 騎練訊號：簡化 code（逐匹分數同報告文字不變）

- **日期**：2026-11-03；**平台**：AU；**baseline**：`origin/main`（`git merge-base`，同場地簡化之後）。
- **用戶**：「yes i want you to help me rebuild this section with simplest code and removing all the bugs and dead code」。
- **性質**：重構。逐匹分數、報告文字、證據標籤全部同 baseline 一樣，唔需要過表現閘。

## 改咗乜

新檔 `au_racing_engine/jockey_trainer.py` 係騎師分、練馬師分、人馬配搭分嘅唯一計算位置（公式寫喺 docstring）。
`RacingEngine` 只係砌數字同敘述。

全語料路徑掃描（4,105 場、40,216 匹；乾淨窗 08-05 起 31,717 匹）先，再剷：

| 剷走 | 證據 |
|---|---|
| 練馬師「empirical fill」（`_trainer_empirical_base`、`_TRAINER_LY_*` 六個常數） | **0 匹**：要 ≥10 場先觸發，但 ≥10 場已經行統一上名率 |
| `WC_AU_PEOPLE_METRIC` 研究開關（`trainer_win`／`wins`／`place` 三個模式、`_TRAINER_WIN_*`、`_TRAINER_LOGWINS_*`、`_logwins_pct`） | production 一直係預設 `measured` |
| `FIT_MICRO_WEIGHTS` 六個 0.0 key 同佢哋嘅 `.get(key, default)` 分支（離開已證明配搭、未及上仗騎師、回配、沿用上仗騎師、上仗騎師往績連續項 ×2） | 已經退出計分；新 code 用 `w[key]` 直接讀，冇 default 可以復活 |
| 人馬配搭分入面 4 個計咗冇用嘅變數 | ruff F841 |
| `au_fit_continuity_ab.py` | 只係用嚟重測上面已剷嘅連續性項；冇任何地方 import |
| `_rating_tier_text`、`_unified_place_rate`、`_place_rate_score`、`_jockey_ly_score` | 併入 `jockey_trainer` |

`FIT_MICRO_WEIGHTS` → `jockey_trainer.FIT_WEIGHTS`（`au_runtime_micro_ablation` 照樣逐 key 消融）。

路徑實際觸發（全語料）：騎師統一率 39,685、騎師薄樣本 LY 96、騎師資料庫 tier **0**、騎師中性 435；
練馬師統一率 37,900、練馬師資料庫 tier 317、練馬師中性／薄樣本 1,999；練馬師場館三條全部 delta 0（報告用）。

## 驗證

1. `au_dump_engine_leaves.py` 全語料，baseline worktree 對 candidate：4,105 場、40,216 匹，**全部 feature、overlay、ability 零差異**。
2. 2026-09-20 → 10-05 十二個場次 797 匹：`feature_notes`（騎師／練馬師／配搭／試閘備戰）、`jt_signal_detail`、
   `jt_fit_detail`、`preparation_detail`、`score_provenance`、騎練維度判讀句 **全部一樣**。
3. AU 單元測試 1,238 個全過；golden、數據合約綠。

## 搵到但冇喺呢度改（會改輸出）

1. **薄樣本騎師用另一把尺**：LY 少過 10 場嘅騎師（96 匹）唔係中性，而係用另一條公式（prior 0.365、spread 100，
   對比統一率 0.3564／140）。練馬師同樣情況就係中性。例：John Velazquez 去年澳洲 1 騎 0 上名 → 58.3（低過中性）。
2. **練馬師證據標籤永遠係 observed**：`_feature_evidence_state` 用「base_label 冇『資料庫無記錄』」判斷有冇資料，
   但呢句由來冇出現過，所以冇數據嘅練馬師（1,999 匹）都當有證據，令「資料覆蓋」偏高。唔入分。

兩樣另開 EXP-20261103-06 量度。
