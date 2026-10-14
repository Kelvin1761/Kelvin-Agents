# Stability 設計：固定 development 消融

**唔係已證實改善；terminal 未開，唔准部署本輪權重或候選。**

A：非初出 PQ fallback 移除固定正截距；B：按歷史途程／跑道接近程度重算完整 PQ；AB：兩項組合。

| 候選 | Gold Δ | Good Δ | 救返失手／破壞成功 | Gold＋Good無回歸 folds | 判決 |
|---|---:|---:|---:|---:|---|
| A | -0.057pp | -0.114pp | 3/1 | 3/5 | DEV_REJECT |
| B | +0.057pp | +0.227pp | 17/11 | 3/5 | DEV_ONLY_NOT_VALIDATED |
| AB | -0.114pp | +0.227pp | 19/12 | 3/5 | DEV_REJECT |

## 排序指標

| 候選 | capture@5 Δ | 前三平均rank Δ | NDCG@5 Δ | Top5 AUC Δ |
|---|---:|---:|---:|---:|
| A | +0.00076 | -0.00378 | +0.00048 | +0.00052 |
| B | -0.00114 | -0.00170 | +0.00194 | -0.00025 |
| AB | +0.00019 | -0.00492 | +0.00235 | +0.00020 |

所有 bootstrap CI、五段日期 folds、cohorts、stability 消融預算及組合邊際見 results.json。

## FORM:PQ 配比（單獨改配比）

| FORM:PQ | Gold Δ | Good Δ | 判決 |
|---|---:|---:|---|
| 0%:100% | -0.908pp | +0.341pp | DEV_REJECT |
| 20%:80% | -0.284pp | +0.624pp | DEV_REJECT |
| 40%:60% | +0.057pp | +0.795pp | DEV_ONLY_NOT_VALIDATED |
| 60%:40% | +0.000pp | +0.000pp | DEV_ONLY_NOT_VALIDATED |
| 80%:20% | -0.795pp | -0.057pp | DEV_REJECT |
| 100%:0% | -1.873pp | -1.135pp | DEV_REJECT |

## 前段選配比，後段測試

| Fold | 鎖定 FORM 份額 | Gold Δ | Good Δ |
|---|---:|---:|---:|
| 2 | 20% | -1.746pp | -0.748pp |
| 3 | 40% | -2.749pp | +0.000pp |
| 4 | 60% | +0.000pp | +0.000pp |
| 5 | 60% | +0.000pp | +0.000pp |

## 來源健康

| PQ 來源 | 馬匹 | FORM缺可用名次 | PQ高於60 | 有生涯但正式entries缺失 |
|---|---:|---:|---:|---:|
| class_adjusted_margin_field_relative | 15104 | 1726 | 8483 | 7 |
| consistency_fallback | 1811 | 1153 | 946 | 33 |
| sportsbet_complete_form_archive_recovery | 6 | 0 | 6 | 0 |

## 解讀界線

- 高分往績、今日適用性、證據可信程度分開保存；波動本身只作 risk metadata，唔自動扣分。
- context 權重只改原有最多四場完整 dated runs 嘅平均；完全同情境時應不變。
- 場內尺度包括完整賽前馬群；無賽果馬仍參與原本 PQ field summary。
- 來源缺資料仍保留 unknown；recovered score 不冒認完整 raw evidence。
- 之前 terminal 已曝光，本輪完全冇分析；dev folds 已曝光，唔叫 pristine holdout。
- 現行 baseline 全量 runtime 重建，PIT 歷史統計未逐欄核證；只適合研究。

Snapshot SHA256：`3782d6f6e3cb60c2ed870f07959818c0e660d697ef0d08678e3630081a19cf37`
