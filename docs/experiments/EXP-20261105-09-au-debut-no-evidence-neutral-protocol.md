# EXP-20261105-09 預先登記：初出馬「冇證據」穩定性分 52.4 → 60（D1）

- **日期**：2026-11-05（寫喺實作同任何量度之前）；**平台**：AU；**用戶**：「測 D1」。
- **baseline**：`origin/main` 585a801f（C2 + C2 refit 權重 + 重播生涯場數修正 EXP-20261105-08）。
- **背景**：[EXP-20261105-07](EXP-20261105-07-au-debut-gap-diagnosis.md) —— 混合場模型頭三揀 339 個初出 vs 實際 563、市場 602；
  模型名次 7+ 嘅初出入三 0.169 vs 出過賽 0.126。主要嚟自 stability −1.70。

## 機制（結構，唔靠結果）

初出馬冇近績質素 raw → `stability.composite` = 0.6 × 近績分 + 0.4 × 表現質素分。初出馬表現質素分走 `consistency_fallback`，
抄 `consistency_score`，而 `consistency_score` 初出 = `CONSISTENCY_MICRO_WEIGHTS["career0_base"]` = **52.4**（全部 2,034 匹初出一樣）。
→ 近績質素 0.6 × 60 + 0.4 × 52.4 = **57.0**。52.4 冇實測來源（EXP-20261013-03 只係「保持原樣」）。`consistency_score` 本身唔入任何維度，
只經呢條 fallback 影響排名，即係**只郁初出馬**（`_career_starts() == 0`）。

## 候選（一個，冇 fit）

- **D1**：`CONSISTENCY_MICRO_WEIGHTS["career0_base"]` 52.4 → **60.0**（「冇證據 = 60」）→ 初出馬近績質素 fallback = 60。
  研究開關 `WC_AU_DEBUT_NEUTRAL=1`（只喺分支）。班次分初出 57.7 **唔郁**（EXP-20261028-13：剷走有害）。

## 已知風險（事前寫低）

混合場入三率初出 0.289 < 出過賽 0.315 —— 「真正中性」可能略低過 60（[au-neutral-point-is-per-leaf] 試過 jockey_horse_fit 冇證據群組要低過 60）。
今次唔 fit 第二個值；D1 輸就記錄，唔會換值再試（換值 = 用結果揀參數，要另開協議 + dev/holdout）。

## 量度同判決（預先固定）

- 全語料 dump BASE、D1；v3 fixed_rule（08-05 起）同分層：`scratch/au_track_simplify_judge_20261103.py`。
- §8 四 arm：`au_walkforward_refit.py predict` + `scratch/au_track_sp_s8_judge_20261103.py`。
- 額外描述（唔做判決）：混合場模型頭三入面初出數；初出馬按模型名次嘅入三率。
- **上線條件**：§8 WIN（`evaluate_with_refit_arms`），冇分層 CI 全負。refit arm 先 WIN 就要連 refit 權重一齊上（同 C1／C2 一樣處理）。
  冇 WIN → 唔上線，記錄；用戶可以另外決定。
