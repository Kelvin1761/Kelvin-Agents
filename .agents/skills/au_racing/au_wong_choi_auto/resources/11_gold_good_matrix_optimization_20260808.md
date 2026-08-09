# AU Gold / Good matrix optimization — 2026-08-08

## Metric contract

- **Gold**：實際三甲全部落在模型 Top 4。
- **Good**：模型 Pick 1 同 Pick 2 都跑入實際三甲。
- **Pass**：模型 Top 3 任兩匹跑入實際三甲。
- `Good Any-2` 名稱已退休；舊 any-one Pass 不再出現在現役 AU evaluator。

## Corpus scope correction

Daily scheduler 會將完成 meeting 搬入 `AU_Racing/Archive/`，但 runtime audit 原本只用
`archive_root/*/Race_*_Logic.json`，因此漏掉 2026-07-15 至 2026-08-07 嘅新資料。
Discovery 改為 recursive meeting-file discovery，並加 regression test。

- Logic files discovered：822 → **1,027**
- Result-aligned races：623 → **805**
- Runners：6,400 → **8,249**
- Date range：2025-09-06 → **2026-08-07**

## Matrix method

維持單一 deterministic linear ability score，冇加 slot rerank、賠率、post-race feature
或新 ML production layer。用六個現役 matrix 做 expanding walk-forward refit：每個窗口
只用較早日期 fit，下一個 100-race window 完全未見；最後採用五個訓練窗口共識權重
嘅逐維度中位數，而唔採用 dev argmax。

| Matrix | Before | After |
|---|---:|---:|
| stability | 0.37398 | **0.32920** |
| pace_perf | 0.14569 | **0.10559** |
| race_shape | 0.11280 | **0.13485** |
| jockey_trainer | 0.20414 | **0.22957** |
| class_weight | 0.07170 | **0.12042** |
| track | 0.09169 | **0.08037** |

Pure-ability RMS spread 變成舊版 0.94790 倍，所以 wet overlay scale/clamp 同步乘
0.94790；候選用 lockstep 版本重新驗證。

## Validation

- Expanding walk-forward objective：**5/5 windows win**
- Top-5 paired AUC delta：dev **+0.0069**
- Latest-date holdout delta：**+0.0134**
- Holdout 95% paired bootstrap CI：**[+0.0025, +0.0244]**
- All-field holdout delta：+0.0096，95% CI **[+0.0020, +0.0173]**

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Gold | 14.53% | **16.02%** | **+1.49pp** |
| Gold strict | 5.59% | **5.84%** | +0.25pp |
| Good | 21.12% | **24.35%** | **+3.23pp** |
| Pass | 42.98% | **45.59%** | **+2.61pp** |
| Champion | 23.11% | **24.84%** | +1.74pp |
| Winner@3 | 54.41% | **55.65%** | +1.24pp |
| Winner@5 | 74.41% | 74.29% | -0.12pp（1 race） |
| Top-3 precision | 45.80% | **46.71%** | +0.91pp |

完整日期 holdout（211 races）本身：Gold +3.79pp、Good +1.90pp、Pass +0.95pp、
Champion +3.32pp；Winner@5 +0.95pp。即係改善唔係由舊日期單方面推動。

## Production verification

- 真 `RacingEngine` 重跑 1,027 Logic files，805 場成功對齊。
- 8,249 匹 stored ability vs formula replica：冇一匹誤差 >0.01。
- AU auto + shared metric tests 340、daily tests 66：共 **406 passed**（包括其後新增嘅
  meeting-intelligence format regression tests）。

## Known limitation

歷史 Sportsbet jockey/trainer `(LY:)` 仍係抓取當日 rolling 12-month aggregate，唔係每場
歷史 point-in-time snapshot。不過今次真正最新 holdout（最接近抓取日期、confound 最細）
改善幅度大過 development，而且 AUC paired CI 全正；仍應繼續用未來新賽日監察 drift。

## Subsequent input-alignment correction — 2026-08-09

其後 full archive audit 發現 `_Meeting_Intelligence_Package.md` 有多種歷史格式，舊 parser
會將部分 venue 讀成 `** Randwick`，亦會漏讀中文／compact format 嘅 going。修正 parser
同資料來源 precedence 後，六維 matrix 權重維持不變；805 場重跑結果更新為：Gold
**16.15%**、Good **24.35%**、Pass **45.71%**、Top-5 AUC **0.6842**。今次修正係
input correctness 改善，唔係另一次調權；詳細影響同被否決候選見
`12_meeting_intelligence_alignment_audit_20260809.md`。
