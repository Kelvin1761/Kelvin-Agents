# EXP-20260929-03 — HKJC 沙田新季 regime／資料 audit

- **日期**：2026-09-29
- **平台**：HKJC
- **狀態**：DIAGNOSTIC COMPLETE / MULTI-DIMENSION REGIME SHIFT
- **問題**：沙田全歷史 KPI 尚可，但 2026-09 新季 28 場明顯崩落；係單日噪音、
  race-shape 問題，定係多個維度／資料 coverage 一齊轉 regime？
- **搜索過嘅舊記錄**：EXP-20260910-01、EXP-20260928-01/03/06/08/09、
  EXP-20260929-02。

## 固定比較

- 舊季：2026-04-12 至 2026-07-12 沙田草地。
- 新季：2026-09-06 至 2026-09-27 沙田草地。
- 每個7D matrix、live ability、draw／fit／trip component 各自量場內 Top3-vs-rest
  pairwise AUC、平均場內 SD、60中性率、winner-vs-field edge。
- 只做診斷，不產生候選、不搜尋 cutoff、不使用 odds。

若多個維度同時掉，下一步優先修 PIT freshness／季初 prior；若只有 race-shape 掉，先
收 `draw70` forward shadow；若 ability 掉但單維度冇掉，先查權重／交互而唔改資料。

## 結果

舊季 166 場／2,135 runner；新季 28 場／361 runner。所有欄位 missing rate 均為0，
HKJC data contract亦通過；唔係「欄位消失／全變60」型資料故障。

| 訊號 | 舊季 AUC | 新季 AUC | Δ |
|---|---:|---:|---:|
| live ability | 0.7208 | 0.6119 | **−0.1089** |
| trainer signal | 0.6852 | 0.5680 | **−0.1172** |
| class advantage | 0.6480 | 0.5608 | **−0.0873** |
| stability | 0.6934 | 0.6149 | **−0.0785** |
| race shape | 0.5815 | 0.5367 | −0.0447 |
| horse health | 0.5441 | 0.5036 | −0.0405 |
| sectional | 0.5884 | 0.5848 | −0.0035 |
| form line | 0.5489 | **0.5836** | **+0.0348** |

Race-shape 入面 draw 由0.5872跌至0.5253；fit由0.5159升至0.5343；trip仍弱
（0.4730→0.4813）。所以近期沙田差唔係一個 race-shape patch 可以解決，亦唔支持
即時加大 draw 權。真正形狀係新季多維度 regime shift：最高權重 trainer／shape 同
class 同時失去大量判別力，而較穩定嘅 sectional／form-line 權重偏低。

## 結論

1. **資料合約 PASS，但 predictive drift FLAG**；要新增按 venue／season 監測 AUC/SD，
   唔可以只靠 presence gate。
2. 沙田 production 暫不重配權。28場已被看過，任何針對新季 fit 嘅權重都只可 shadow。
3. 繼續既有 `weight_refit_t02`，並喺 monitor 分開沙田草地／AWT／跑馬地報；另收
   `race_shape_st_draw70` forward evidence，但不把佢當已改善。
4. 下個有實質機會嘅候選應係「新季 reliability gating：由 trainer/shape/class 向
   sectional/form-line 收縮」，但要先凍結幅度再用未來沙田 meeting 驗證，唔准用呢28場
   做 final proof。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  docs/experiments/patches/hkjc_sha_tin_season_audit.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --output /tmp/hkjc_sha_tin_season_audit_20260929.json
```
