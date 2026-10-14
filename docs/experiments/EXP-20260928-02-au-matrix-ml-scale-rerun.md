# EXP-20260928-02 — AU 雙倍語料 Matrix／ML 重跑

**狀態：KEEP CURRENT MATRIX／ML RESEARCH ONLY／NOT SHIPPED**
**日期：** 2026-09-28 ・ **平台：** AU

## 問題

上次完整 Matrix／ML 報告只得 1,406 個 ML 可用場次，截至 2026-08-20。現時資料已
多一倍，重新問：

1. 現役七維 Matrix 權重應否 refit？
2. Logistic／LightGBM／XGBoost 或 Matrix+ML hybrid 有冇足夠 out-of-sample 證據上線？
3. 新結果可唔可以修復已識別嘅低表現場地？

判決跟 `docs/model-evaluation-contract.md` Stage 4 v2；Gold／Good 任何一項喺 dev 或
terminal 點估計回歸即 REJECT。今次冇改 split、指標或 holdout 去救候選。

## 語料

| | 2026-08-21 重跑 | 今次 | 增幅 |
|---|---:|---:|---:|
| ML 可用 races | 1,406 | **2,853** | **+102.9%** |
| ML 可用 runners | 14,063 | **28,216** | **+100.6%** |
| 最終 chronological test | 510 | **778** | +52.5% |
| 日期上限 | 2026-08-20 | **2026-09-27** | — |

Readiness：`READY WITH LIMITATIONS`。掃描 2,864 場，排除 11 場 dead heat／place-boundary
tie；duplicate race／runner 0，future/target Facts 0。ML split 鎖定為：

- development：2,075 場，2025-08-02 至 2026-09-08；
- terminal：778 場，2026-09-09 至 2026-09-27；
- market SP 只喺 prediction freeze 後做評估，唔係 feature。

## Matrix refit

`au_matrix_refit.py verify` 通過：2,866 場／28,338 runners；true engine 最大差
0.003900、mapper 最大差 0.003876，冇 runner 差異大過 0.01。

固定 `obj=place`、3,000 組、至少 4/5 folds。332 組贏 dev，119 組過 fold 閘；喺
睇 holdout 前用 119 組逐維中位數定共識權重：

```json
{"stability":0.35797842,"pace_perf":0.15731275,"race_shape":0.0053928,
 "jockey_trainer":0.67297169,"class_weight":0.34396107,
 "track":0.10197997,"preparation":0.29120192}
```

| 共識候選 Δ | dev 2,436 | terminal 430 |
|---|---:|---:|
| Gold | **−0.16pp** | 0.00pp |
| Good | +0.25pp | +0.70pp |
| Pass | +0.66pp | 0.00pp |
| Champion | +0.12pp | +0.23pp |
| Winner@3 | +0.66pp | +0.23pp |

dev Gold 已回歸，**REJECT**。只作對照嘅 argmax terminal Good −0.93pp、Pass −0.23pp、
top3 precision −0.39pp，同樣 REJECT。現役權重保持不變。

## ML 結果

Development 只用 walk-forward 揀到 XGBoost；hybrid alpha 只喺 development 三個固定值
25%／50%／75% 中揀到 50%。五個 walk-forward period：獨立 XGBoost 贏 2/5，50%
Hybrid 按舊 probability/ranking selection score 贏 5/5。

### Terminal 778 場

| 指標 | Matrix | XGBoost | 50% Hybrid | Hybrid − Matrix |
|---|---:|---:|---:|---:|
| Gold | 19.02% | 18.38% | 18.89% | **−0.13pp** |
| Good | 26.09% | 25.45% | 27.25% | **+1.16pp** |
| Pass | 49.23% | 50.00% | 52.31% | +3.08pp |
| Top-1 | 26.22% | 24.04% | 26.61% | +0.39pp |
| Top-3 | 57.58% | 56.17% | 58.23% | +0.64pp |
| Win Brier ↓ | 0.087119 | 0.087411 | 0.086977 | +0.000142 改善 |
| Place Brier ↓ | 0.184889 | 0.183488 | 0.183606 | +0.001283 改善 |

Stage 4 paired terminal：

- Hybrid Gold −0.13pp，95% CI **[−1.67,+1.67]**；dev **−0.26pp**；
- Hybrid Good +1.16pp，95% CI **[−0.77,+3.08]**；dev **+0.39pp**；
- XGBoost Gold dev／terminal **−0.51／−0.64pp**；Good **−0.26／−0.64pp**。

所以 Hybrid 雖然 probability、Top-rank、5/5 walk-forward 同 Place Brier bootstrap 都過
舊 ML gate，仍然因 dev 及 terminal Gold 點估計回歸而違反現行唯一裁判規則：
**KEEP CURRENT MATRIX**。Good／Pass 改善係有價值嘅研究訊號，但 Good CI 仍跨零，唔可
稱為已證實改善。

所有研究投注策略仍然負 ROI：Matrix −23.31%、XGBoost −13.80%、Hybrid −7.39%；
唔會用「輸少咗」冒充正 edge。

## 低表現場地

terminal 場地樣本仍然太細，唔足以支持 venue override：

| 場地 | terminal n | Hybrid Gold Δ | Good Δ | Pass Δ |
|---|---:|---:|---:|---:|
| Kalgoorlie | 7 | 0.00pp | 0.00pp | 0.00pp |
| Randwick | 10 | 0.00pp | +10.00pp | +20.00pp |
| Caulfield | 19 | 0.00pp | 0.00pp | +5.26pp |
| Ballarat Synthetic | 0 | — | — | — |

呢啲係 0–19 場描述性切片，判 `UNRESOLVABLE`。唔會因 Randwick 10 場結果另開場地權重。
低場地問題繼續由 `EXP-20260927-02` 嘅 PIT speed shadow 做預先登記監察。

## 速度方向點解仍值得追

今次通用 ML 冇加入新 `WinningTime speed_best3`，所以唔係速度候選嘅替代測試。現有
feature 入面，Place permutation importance 排頭五係：

1. `leaf_performance_quality_score` +0.003060
2. `field_size` +0.001700
3. **`leaf_pace_figure_score` +0.001322**
4. `leaf_rating_score` +0.001098
5. `leaf_form_score` +0.001005

即係現役 pace/speed family 仍然有料，但新 WinningTime 訊號要按自己鎖定嘅 PIT 公式
判決，唔可以用今次 ML 結果代替。Speed shadow 喺 prospective outcome 仍為 0 場時已按
power 將揭盲門檻由 1,000 修正為 2,000；現時收集 41／2,000，outcome 仍封存。

## Harness 修正

今次發現兩個評估器問題，均只修 research harness，冇改模型／split：

1. 100-race learning curve 嘅 XGBoost 可對每場輸出常數；Spearman 無定義時舊 code
   `mean([])` crash。依家保守記為 correlation 0，並加 regression test。
2. 舊 ML promotion gate 冇執行 Stage 4 Gold／Good no-regression，所以同一結果會錯印
   `PROMOTE MATRIX + ML HYBRID`。依家加入 dev／terminal Gold、Good 點估計同 paired
   bootstrap；修正後正式 verdict 係 `KEEP CURRENT MATRIX`。

## 重現

```bash
PYTHONDONTWRITEBYTECODE=1 python3 au_dump_engine_leaves.py \
  --out /private/tmp/au_leaves_20260928.json

PYTHONDONTWRITEBYTECODE=1 python3 au_matrix_refit.py verify \
  --data /private/tmp/au_leaves_20260928.json
PYTHONDONTWRITEBYTECODE=1 python3 au_matrix_refit.py refit \
  --data /private/tmp/au_leaves_20260928.json --obj place --n 3000 \
  --min-folds 4 --seed 20260801

PYTHONDONTWRITEBYTECODE=1 python3 au_ml_rebuild.py \
  --archive-root "<AU_Racing>" --results-csv "<historical-results.csv>" \
  --work-dir /private/tmp/au_ml_20260928 \
  --report-dir /private/tmp/au_ml_20260928/report --skip-training

PYTHONPATH=/private/tmp/au_ml_runtime_20260928 \
MPLCONFIGDIR=/private/tmp/matplotlib-cache PYTHONDONTWRITEBYTECODE=1 \
python3 au_ml_program.py \
  --dataset /private/tmp/au_ml_20260928/au_ml_dataset.json \
  --readiness-audit /private/tmp/au_ml_20260928/au_ml_readiness_audit.json \
  --output-json /private/tmp/au_ml_20260928/report/au_ml_program_results_stage4.json \
  --output-md /private/tmp/au_ml_20260928/report/au_ml_program_report_stage4.md
```

本機 `libomp` 只由已安裝 scikit-learn bundle 複製／relink 到 `/private/tmp` 隔離 runtime；
冇安裝 package、冇改系統 library。

SHA-256：

- leaves：`8982cbd42b7b019693956ce8a7e3356dd3d4ce40a45524b331eb06495fc3d921`
- ML dataset：`8aa8731f2392bb732be35966aea32f027b7cab7fe48d4db198fa1d1e3a702efe`
- readiness：`99922b8f1264e0ffb82e6ace56c3e030771fbbe0342ee525083c4d2a519c40cb`
- Stage-4 result：`823ba5da152355cdb24395fd77c392c0129472fe18687b5769253ce623c32e32`

## 決定

- **Matrix refit：REJECT。**
- **獨立 XGBoost：REJECT。**
- **50% Matrix + XGBoost：PROMISING BUT REJECT／RESEARCH ONLY。**
- 冇改 production scoring、權重、golden、data contract 或部署。
