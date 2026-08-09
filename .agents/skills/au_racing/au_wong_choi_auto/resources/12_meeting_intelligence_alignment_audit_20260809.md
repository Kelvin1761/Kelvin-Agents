# AU meeting-intelligence alignment audit — 2026-08-09

## Outcome

修正一個會污染場地名稱同漏讀 going 嘅真實 input-alignment bug。今次只改資料解析同來源
precedence，冇加 Top-2 lock、slot rerank、賠率 feature 或 post-race data，亦冇因應單一結果
微調 scoring matrix。

## Root cause

archive 入面至少有三類 `_Meeting_Intelligence_Package.md` 格式：原始英中雙語 section、
bold inline header 配中文欄位、以及現役 bullet／compact 中文格式。舊 parser 只完整支援
第一類，導致：

- `**Date:** 2026-04-04 | **Venue:** Randwick` 被錯讀成帶 Markdown 嘅 venue；
- `Predicted Going`、`Official Going`、`場地狀況`、`跑道狀況` 等欄位未能一致解析；
- 舊 meeting package 有 provisional going 時，可能遮蓋較新 Racecard official snapshot。

## Fix

- canonical parser 統一支援歷史及現役格式，並清走 Markdown decoration；
- 中文 wrapper 內嘅英文標準 going token（例如 `好地 (Good 4)`）會正規化抽出；
- 有效 Racecard／extractor context 視為較新資料，優先於 meeting package；
- Racecard 為空或 `Unknown` 時，meeting package 仍作 fallback；
- `build_au_logic.py` 嘅舊 parser／loader 改為 canonical wrapper，避免兩套邏輯再漂移；
- 8 個 regression tests 覆蓋各格式、fallback 同 precedence。

實際 20 個 meeting package 全部可解析出乾淨 venue、date 同 going。

## Full archive rescore

用真 `RacingEngine` 重新處理 recursive archive：

- Logic files：1,027
- result-aligned races：805
- runners：8,249
- metadata 改變：72 場
- going 由 `Unknown` 修正：33 場（24 場 → Good 4；9 場 → Soft 6）
- ability score 改變：60 場／572 匹
- ranking 改變：46 場
- 最大 score delta：5.7047
- 帶 `**` 嘅 venue：歸零
- `Unknown` going：39 場降至 6 場（餘下全屬 Sale、來源本身未提供可信 going）
- horse/result identity：805 場全部對齊，冇新增 unmatched horse

## Metric effect

以下係相同六維 matrix、修正 input 前後嘅全 corpus 結果：

| Metric | Parser fix 前 | Parser fix 後 | Delta |
|---|---:|---:|---:|
| Top-5 AUC | 0.6839 | **0.6842** | +0.0003 |
| Gold | 16.02% | **16.15%** | +0.13pp |
| Good | 24.35% | **24.35%** | 0.00pp |
| Pass | 45.59% | **45.71%** | +0.12pp |
| Champion | 24.84% | **24.84%** | 0.00pp |
| Winner@3 | 55.65% | 55.53% | -0.12pp（1 race） |
| Winner@5 | 74.29% | 74.16% | -0.13pp（1 race） |
| Top-3 precision | 46.71% | **46.75%** | +0.04pp |

真正 latest-date holdout 冇受影響，因為出錯格式集中於較舊 meeting。paired 效果唔顯著，
所以唔將今次修正包裝成 performance breakthrough；保留原因係輸入已經可證實較正確。

## Ability-feature experiments not promoted

今輪亦由 scoring matrix／馬匹能力角度檢查過以下候選，全部按未見資料結果否決：

- rating-missing class fallback：development Top-5 AUC -0.0004；holdout +0.0023，
  95% CI [-0.0047, +0.0100]；
- pre-race career place-rate：88% runner coverage，feature-alone AUC 約 0.588；加入 matrix 後
  development +0.0014，但 holdout -0.0026，95% CI [-0.0073, +0.0022]；
- explainable pairwise linear ranker：四個 feature set 都未達 promotion gate；
- parser-corrected corpus 再 refit 六維 matrix：Good／Pass 等指標有改善，但 Gold -0.12pp，
  holdout Top-5 AUC +0.0018、95% CI [-0.0082, +0.0117]，因此維持現役權重。

結論：今輪保留 alignment fix，同時維持經正式 holdout 驗證嘅 matrix v2。下一輪改善應集中
於新增真正 pre-race ability evidence 或提升現有 evidence quality，而唔係調換第 3/4 個 slot。

## Verification

- AU auto + shared metric tests：340 passed
- AU daily workflow tests：66 passed
- 合共：**406 passed**
- full runtime rescore：1,027 Logic files／805 result-aligned races 完成
