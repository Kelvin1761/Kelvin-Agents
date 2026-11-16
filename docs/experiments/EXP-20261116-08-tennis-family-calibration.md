# EXP-20261116-08 — Tennis：逐 family 校準 prop 機率（冷門 odds ≥3 蝕錢）

- 日期：2026-11-16；平台：Tennis；類型：模型候選（研究），**冇改 live code**。
- 提問（Kelvin）：(1) 每個 player prop 可唔可以有專屬公式；(2) odds >3 嘅注表現特別差，錯喺邊、點改善。
- 已搜舊記錄：EXP-20261110-03（模型對市場冇增量）、EXP-20261009-01／AUDIT_2026-08-09（**比賽勝率** Platt REJECT）、
  EXP-20261027-05、EXP-20261105-10。今次唔同之處：逐 **prop family** fit，同埋用 holdout 選注 P/L 判，唔係只睇 Brier。
- Baseline：main `c03e045a`；模型 `tennis-v1` 冇郁。

## 起因（唯讀診斷，睇結果之後先登記下面嘅測試）

精選（EXP-20261105-10）按賠率段：<2 47 注 −4.75u；2–3 37 注 +5.42u；**≥3 10 注 0 中 −10u**。
嗰 10 注模型平均 51.6%，去水市場 25.7%。如果市場啱，全輸機率約 5%（預期中 2.6 注），所以有運氣成分。
大樣本（全部賽前定價行，6 個 family，odds ≥3）按「模型 − 市場」分歧分：

| 分歧 | n | 模型 | 市場 | 實際 | ROI |
|---|---:|---:|---:|---:|---:|
| 15–25pp | 295 | 0.456 | 0.251 | 0.251 | −9.4% |
| ≥25pp | 322 | 0.515 | 0.180 | **0.165** | −18.0% |

賽果跟市場，唔跟模型；模型將冷門高估 20–35pp。精選按 edge 排名，所以 ≥3 嘅注平均 edge 0.26（<3 係 0.16），
3／10 係當日第 1 名 —— 選注規則專揀模型錯得最勁嗰啲。

## 預先登記（寫喺 `patches/tennis_family_calibration_20261116/study.py` docstring，跑之前）

- 語料：live `prop_tracker` 唯讀，`is_point_in_time=1`、WON/LOST、非 DISPUTED、精選 6 個 family；
  evidence 品質 ≥0.65（evidence 10 月尾先有，之前嘅行冇得套，跑之前改咗做「有先套」，所有 arm 一樣）。
- 切法：dev ≤ 2026-10-15（3,920 行，只 fit）；holdout 2026-10-16 至 11-16（3,647 行／1,441 場，只報）。
- Arm：A 現行 `model_prob_raw`；B 逐 family Platt（只用模型）；C 逐 family 市場錨定
  `logit p = a + b·logit(fair) + g·(logit(model) − logit(fair))`。dev 少過 50 行嘅 family 冇 fit，用返 A。
- 選注：`is_value_selection`（各 family 原有 min_edge、賠率帶）；每注 1u。按場 bootstrap 4000、seed 20260826。
- 判決：KEEP 要 holdout LL 唔差過 A，**而且** 選注 P/L 勝 A 嘅 CI 全正。只係少落蝕錢注而 P/L 升，記做安全欄，唔當 edge。

## 結果（holdout）

| Arm | LL（對市場） | 注數 | ROI | P/L | odds ≥3 注 | ΔP/L 對 A |
|---|---|---:|---|---:|---:|---|
| 市場 | 0.6185 | — | — | — | — | — |
| A 現行 | 0.6733（+0.055 [+0.038, +0.071]） | 1,204 | −11.2% [−20.2, −2.5] | −135.1u | 133 | — |
| B Platt | 0.6721（+0.054） | 1,003 | −10.8% [−19.6, −2.0] | −108.3u | **174** | +26.8u [−34.6, +96.7] |
| C 市場錨定 | 0.6282（+0.010 [+0.005, +0.015]） | 330 | −14.9% [−24.6, −4.9] | −49.2u | 8 | +86.0u [−17.9, +189.9] |

dev fit 嘅分歧系數 g：首盤勝方 +0.035；**讓局 −0.468；贏一盤 −0.198；球員總局 −0.205** —— 模型同市場越唔同，
越應該信市場（反向）。校準後首盤勝方同贏一盤 holdout 零注；C 剩低嘅 330 注入面 240 注係冇 fit 嘅兩個 family
（首盤讓局、讓盤，等同 A），fit 咗嘅讓局 88 注仍然 −14.5u。

## 判斷：**B REJECT、C REJECT（冇 edge）**

- **B（只用模型嘅 Platt）解決唔到冷門問題**，odds ≥3 注數反而多咗（133→174）；同 8 月／10 月 Platt REJECT 一致。
  原因：Platt 只係將模型拉向 family 平均，市場話 18% 而模型話 51% 嗰類，拉完仍然遠高過市場。
- **C 正確校準後 ≈ 市場本身**：LL 由 +0.055 收窄到 +0.010，但 value 注幾乎冇晒，剩低嘅照蝕。即係
  「每個 family 專屬校準」嘅誠實答案係：校準啱咗，模型就冇嘢可以落。
- 答 Kelvin 第 1 條：每個 family 寫專屬公式唔會加資訊 —— 7 個 family 只係兩個輸入（保發率、比賽勝率）嘅函數，
  而兩個輸入都輸市場。要有 family 層面嘅 edge，需要新資料（外部參考價、family 專屬特徵），唔係新公式。
- 答第 2 條：odds >3 蝕嘅根源係模型高估冷門 + 精選按 raw edge 排名；可以做嘅只係**安全欄**（例如分歧 >20pp 唔出、
  或精選賠率上限 3.0），即係少落蝕錢注，**唔係 edge**。改精選規則 = 新 forward arm，要 Kelvin 拍板，今次冇做。

## 限制

- dev 窗口跨兩個 code 年代（11-06 重建前後）；8–9 月冇 evidence，品質閘冇得套。
- 首盤讓局／讓盤 dev 樣本 <50，冇 fit。
- 單一莊家（Sportsbet）、最後賽前價；歷史係混合 regime，唔係 untouched OOS。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 docs/experiments/patches/tennis_family_calibration_20261116/study.py \
  --db tennis-wong-choi/tennis_wc.db \
  --json-out docs/experiments/patches/tennis_family_calibration_20261116/result.json
```
