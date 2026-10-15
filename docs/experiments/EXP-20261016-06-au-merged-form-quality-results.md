# EXP-20261016-06 結果：近績分 + 表現質素分合併

- **預先登記**：[protocol](EXP-20261016-06-au-merged-form-quality-protocol.md)（commit `eeaef509`，量度之前）
- **baseline**：`e684d05a`（F6a + 班次 parser 修正）。研究 dump 同 baseline 逐匹 ability 差 0.0；
  6 場 digest 嘅頭 4 場同 production 19,852／19,852 一致。
- **來源 availability 仍係 FLAG**：正式判決全部 `REJECT / leakage_audit_failed`。以下係研究診斷。

**決定：NEEDS MORE TESTING —— 最強候選 eq2_N6，建議 forward shadow。** 冇嘢上線。

## 標準化常數（只用 run_date < 2026-08-05 嘅 41,647 條往績，冇賽果標籤）

σ_pct 0.3191；負距 μ 4.104、σ 4.156；log10 獎金 μ 4.586、σ 0.354。
合併 leaf 覆蓋：N4 71.8%、N6 76.7%（其餘用返而家嘅 stability 合成分）。

## 閘 1：leaf（診斷）—— 合併版**略差**

而家 stability 合成 AUC 0.6461。

| 候選 | AUC | Δ | 95% CI | Holm p |
|---|---:|---:|---|---:|
| eq3_N4 | 0.6398 | −0.0063 | [−0.0130, −0.0005] | 0.116 |
| eq3_N6 | 0.6401 | −0.0060 | [−0.0150, +0.0020] | 0.483 |
| eq2_N4 | 0.6412 | −0.0050 | [−0.0131, +0.0026] | 0.483 |
| eq2_N6 | 0.6401 | −0.0060 | [−0.0162, +0.0038] | 0.483 |

全場配對 AUC 計晒所有馬（包括尾段馬之間）；排名指標只睇頭幾位。兩者方向唔同係可能嘅
（memory `leaf-auc-gains-do-not-convert-to-ranking` 嘅反面）。依登記 leaf 唔攔。

## 閘 2：§8 四 arm（1,482 場／41 日 OOS）

| 候選 | fixed arm（現行權重） | refit arm | live guard | arm Holm p | 跨候選 Holm |
|---|---|---|---|---:|---:|
| eq3_N4 | REJECT（too weak） | **RANKING_WIN** | PRIMARY_WIN | 0.006 | **0.024 ✅** |
| eq3_N6 | RANKING_WIN | RANKING_WIN | too weak | 0.026 | 0.052 |
| eq2_N4 | REJECT（too weak） | **PRIMARY_WIN** | PRIMARY_WIN | 0.038 | 0.052 |
| **eq2_N6** | **PRIMARY_WIN** | **PRIMARY_WIN** | PRIMARY_WIN | **0.006** | **0.024 ✅** |

### eq2_N6（名次 + 賽事質素，6 場）

| arm | Gold | Good | Top5 AUC |
|---|---|---|---|
| fixed | **+1.62pp [+0.14, +3.30]**（5/6 塊） | +0.94pp [−0.68, +2.81] | +0.0049 [−0.0009, +0.0109] |
| refit | **+1.89pp [+0.73, +3.12]**（6/6） | **+1.75pp [+0.14, +3.55]**（6/6） | **+0.0075 [+0.0018, +0.0132]** |

場數：A0 Gold 19.91% → B1 21.93%；Good 26.65% → 28.00%；Pass 50.13% → 51.75%。

### 唔係權重效應

合併 leaf 嘅離散度大過兩個 leaf 平均，fixed arm 等於加重咗 `stability`。但 refit arm 會兩邊各自重配權重，
而 eq2_N6 嘅 refit **將 stability 權重由 0.371 減到 0.25–0.29**（6 窗全部共識、冇 fallback；
現行 leaf 嘅 refit 有 3 窗 fallback）。好處嚟自 leaf 本身，唔係多咗權重。

### Ablation

- **負距（eq3 − eq2）**：N6 下 refit Gold +1.01 vs +1.89、Good +1.75 vs +1.75 → 加負距冇幫手，
  甚至略差。用戶原意（賽事質素判名次）係最好嘅版本。
- **6 場 vs 4 場（N6 − N4）**：eq2 下 fixed arm 由 too weak 變 PRIMARY_WIN；refit Gold +1.48 → +1.89、
  Good +1.15 → +1.75 → 多兩場有幫手。

## 洩漏檢查

- 往績名次、出賽數、負距、獎金：全部係目標日之前嘅往績（digest 已經 `date < meeting_date`），落注時知道 ✅
- 標準化常數只用 08-05 之前嘅往績、冇賽果 ✅
- 同而家 PQ／近績分用同一份 Formguide，資訊集冇擴大 ✅
- Formguide 頁面賽前抓取未逐筆證實 → **FLAG**（同 EXP-01／02／03 一樣）

## 下一步（建議）

eq2_N6 做 forward shadow（同 EXP-20261016-03 一樣：凍結 code + pooled refit 權重、賽前快照重播、
≥ 41 個賽日評一次）。注意 S2（pace_perf）嘅 forward 已經喺跑：兩個係唔同 family，各自判；
兩個都過嘅話，上線前要再測合併。

## 重跑

```bash
python3 scratch/au_stability_dump_20261016.py --variant f6a --out $S/merge.json
python3 scratch/au_merged_form_quality_20261016.py build --dump $S/merge.json --outdir $S/mfq
python3 scratch/au_merged_form_quality_20261016.py leaf  --dump $S/merge.json --outdir $S/mfq --out $S/mfq/leaf.json
for a in base eq3_N4 eq3_N6 eq2_N4 eq2_N6; do
  python3 scratch/au_paceperf_refit_20261016.py --variant f6a predict --data $S/mfq/$a.json --out $S/mfq/wf_$a.json; done
for a in eq3_N4 eq3_N6 eq2_N4 eq2_N6; do
  python3 scratch/au_paceperf_s8_20261016.py --base $S/mfq/wf_base.json --cand $S/mfq/wf_$a.json --label $a --out $S/mfq/s8_$a.json; done
```
