# EXP-20261015-08 — AU 純速度與聯合重配

- 日期：2026-10-15；平台：AU；基準 `ca2c4bd6b8435373158dc438765006f24a8df73b`。
- 假設：逐駒全程時間有獨立場內辨識力；現有模型會重疊吸收部分訊號，需以中性測試及聯合重配分開驗證。
- 舊記錄：EXP-20261015-02/04/05/06/07、EXP-20260901-04、EXP-20260821-02。
  04/05/06 在已保存研究分支，非 production release。今輪沒有新增時間公式。
- 預先登記：[protocol](EXP-20261015-08-au-neutral-speed-protocol.md)。
- 改動只在研究腳本與記錄；沒有模型／dashboard／golden／data-contract baseline 改動。

## 香港參考與方法

HKJC `inject_hkjc_fact_anchors.py:get_standard_time/compute_sectional_from_splits` 用
馬場／途程／班次標準時間及逐段標準，保留段距，值得沿用這個比較原則。
但其完成時間修正式 `raw_dev-(estimated_winner-standard)` 會大致化簡為
`margin×0.17`（四捨五入除外），而 `L600_approx` 是末400加前段一半。
這些不是獨立量度的真實早段及L600，沒有移植AU。

純速度只用 A 或 B，不讀任何其餘leaf／overlay；等效全部其他leaf60、overlay0。
正gain只改尺度不改順位，因此不用純速度的最佳gain聲稱「重要性」。
全中性AUC=0.5、馬號tie-break只作確定性排序；缺證據不當慢馬。
joint refit保留原六維分數標尺，新增速度為60+10×可靠度收縮z。
擬合權重受標尺、共線性及缺值率影響，不是馬匹實力的因果百分比。

## 資料及重跑

現行引擎重新dump；與原frozen contextual features逐場逐馬嚴格配對。
只用2026-08-05至2026-10-14乾淨時段；首30賽日warmup，之後六個7賽日窗口
（最後窗口6日），每窗fit只收之前資料。這些舊窗已被觀察，非新forward holdout。

原始完整結果、逐馬預測、匹配輸入、fresh leaves及執行log存於：
`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-neutral-speed-research/`。
舊context artifact不複製：同層`AU-contextual-speed-research/au-context-speed-features-xml.json`。

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-speed-neutral-current-leaves.json
python3 -u scratch/au_neutral_speed_20261015.py \
  --leaves /private/tmp/au-speed-neutral-current-leaves.json \
  --context /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-contextual-speed-research/au-context-speed-features-xml.json \
  --out /private/tmp/au-neutral-results.json
```

## 已知限制

歷史source capture/publication未證實，leakage audit=FLAG，正式v3判決不能WIN。
來源主要RQ；不推廣為全澳／所有途程通用能力尺。中性60排除是leaf缺證據代理，
不等於完整source-state審計。固定512個Dirichlet候選／每臂不等於找遍所有權重。
沿用原time normalization，不新增能量或因果用力修正；原研究亦未證明這類修正有增益。

第一輪腳本把前三名數量限定等於3，誤剔並列名次；在完成候選比較前已中止，
修回canonical「至少3匹且有頭馬」並重跑全部，未採用縮小樣本結果。
合成並列名次／全中性測試及整份語料的fast metric對canonical一致性均需通過。

## 實測結果

2,496場配對成功；與frozen baseline最大戰力分差=0，現行矩陣replica最大差=0。
41個驗證日共1,493場／14,487匹次；速度覆蓋3,145匹次，411場可作場內比較，
共4,774對。比較用同場上名與落第馬配對，並非選馬命中率。

| 純訊號 | 場內AUC | 按日bootstrap95% CI | 六塊結果 |
|---|---:|---|---|
| 全中性 | 0.500 | 常數基準 | 全部0.5 |
| A 全程情境速度 | 0.60725 | [0.58479,0.63060] | 6/6 >0.5 |
| B 頭段情境速度 | 0.54085 | [0.52323,0.55950] | 5/6 >0.5，1塊=0.5 |

同列使用完全相同馬匹及配對（各leaf60排除，因此不同列樣本略有不同）：

| 既有leaf | A速度 | 既有leaf | A−leaf CI | Holm p |
|---|---:|---:|---|---:|
| pace figure | 0.60725 | 0.60798 | [-0.02530,0.02369] | 1.000 |
| PQ | 0.60725 | 0.64066 | [-0.05608,-0.01047] | 0.024 |
| form | 0.60635 | 0.63997 | [-0.06076,-0.00201] | 0.175 |
| rating | 0.60280 | 0.58237 | [-0.00880,0.05184] | 0.720 |
| jockey | 0.60631 | 0.59369 | [-0.01758,0.04200] | 1.000 |
| trainer | 0.60879 | 0.61188 | [-0.03756,0.03185] | 1.000 |

A不是最強單一指標；相對PQ較弱的差異在六項Holm校正後仍可見。
不能因此說速度無用，亦不能把PQ/form內可能重疊的歷史表現當成新獨立訊號。

| 今仗途程 | 可比較場 | A全程AUC [CI] | B頭段AUC [CI] |
|---|---:|---|---|
| ≤1200 | 192 | 0.6250 [0.5935,0.6529] | 0.5885 [0.5645,0.6141] |
| 1201–1700 | 167 | 0.6260 [0.5860,0.6673] | 0.5228 [0.4899,0.5556] |
| >1700 | 52 | 0.4837 [0.4230,0.5492] | 0.4430 [0.3932,0.4966] |

長途A未證明有辨識力；B方向較差。分層CI沒有作家族校正，不據此選新cutoff或倒轉符號。

### Joint refit（同1,493場；場數）

| 配置 | Gold | Good positional | Pass | 對原無A差 |
|---|---:|---:|---:|---|
| 原無A baseline | 288 | 393 | 749 | — |
| 已部署固定A×1.5回看 | 289 | 394 | 752 | +1/+1/+3 |
| R0 六維重配 | 286 | 396 | 746 | −2/+3/−3 |
| R1 六維+A重配 | 291 | 398 | 745 | +3/+5/−4 |
| R2 六維+A+B重配 | 288 | 392 | 747 | 0/−1/−2 |

R1−R0：Gold+5／Good+2／Pass−1；R2−R1：−3／−6／+2。
R1對已部署固定A版本：+2／+4／−7；不是沒有代價的改善。
R1對原baseline Gold差+0.201pp，CI[-0.494,+0.853]pp；Good差+0.335pp，
CI[-0.374,+1.136]pp。NDCG差+0.000803，CI[-0.002744,+0.004085]；
Top5 pairwise AUC差+0.000086，CI[-0.002626,+0.002586]。沒有清晰排序收益。
三臂各七個metric家族Holm調整後p最小=1.0。

有限512候選搜索：R0只在2/6窗有合格共識，R1為3/6，R2為1/6；其他窗按預註冊規則
退回原baseline，沒有把失敗窗剔走。這不證明所有其他權重都無效，亦不構成「最佳權重」。
完整venue/going/distance/首選result-SP/馬群大小分層在results.json；result-SP只供分層。

### 功效與判決界線

預先量的固定A增量budget：只有Top5 pairwise AUC的budget0.000791略大於
CI半寬0.000736；其餘四個ranking metric的budget均小於CI半寬。
這個budget只描述A×1.5，不代表六維一起改動的完整部件預算；joint-refit §6功效證據
不完整，不能拿此budget替joint refit宣稱RANKING_WIN。
所有正式v3判決均因原source FLAG記為REJECT/leakage_audit_failed；沒有把FLAG當PASS。

**決定：NEEDS MORE TESTING；不採用今輪重配，不改已部署版本。**
純全程速度有研究辨識力，尤其短途／中途；頭段並無已證實增量，長途外推不成立。
下一個可驗證方向是先完善長途／分段標準及來源，再用新賽日驗固定方案，
不是在這41日反覆調權重、途程cutoff或分段長度。

## 重現識別

- fresh leaves SHA256：`f32292b2a4e156400ac135c0764425b5dffc6dc5107547776f39900656680f9f`
- frozen context SHA256：`7a2219256301d0ec15a4a6315b7eaca8a56770ded2ef5bfde1c80a28b1df423d`
- 所有fit metadata含train-through、test dates、合格proposal數、fallback及權重；
  所有test日期嚴格晚於train-through。沒有新模型參數寫入現役資源檔。

## 驗證與保存

`./檢查.sh --quick`、`./檢查.sh` 全部通過；AU/HKJC golden一致，現有引擎未改。
HKJC data-contract原有stale-baseline警告仍在，未因本研究重設其他平台基準。
synthetic tie/deadheat、全60＋零overlay及canonical fast-table一致性檢查通過。
今輪候選未達可發布證據，只保存到研究分支，不經release、不部署參數。
