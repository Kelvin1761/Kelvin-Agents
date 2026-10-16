# EXP-20261016-31 結果：騎練訊號內部份額按 AUC − 0.5 分配 —— REJECT

- **預先登記**：[protocol](EXP-20261016-31-au-jockey-trainer-inner-shares-protocol.md)（`3b3454a1`，量度之前）。
- **語料**：`scratch/au_jt_audit_dump_20261016.py` @ `05dd1b20`（`k2` 特徵 = production）。A0／A1 ability 都用 `exact_score` 重算
  （引擎 ability 有一匹馬差 1e-4 嘅 proven_class 捨入，refit 嘅 verify 會拒絕；兩邊同一種計法）。
- refit 程序 hash `f92c8377…e033`，兩邊一樣（`hash symmetric: True`）；判決器用 `claude-refit-both-arms-20261015` 嘅 §8 模組。

## 候選（暖身 08-05 → 09-04，1,003 場）

| leaf | 暖身 AUC | 現行份額 | 候選份額 |
|---|---:|---:|---:|
| 騎師分 | 0.5834 | 0.333333 | 0.344913 |
| 練馬師分 | 0.5896 | 0.285714 | 0.370554 |
| 人馬配搭分 | 0.5688 | 0.380952 | 0.284533 |

## §8 四 arm（OOS 1,482 場／41 日）

| arm | Gold | Good |
|---|---:|---:|
| A0 live | 22.00% | 27.53% |
| A1 候選 + live 權重 | 22.06% | 27.06% |
| B0 refit | 22.54% | 27.80% |
| B1 候選 + refit | 22.87% | 27.33% |

- **fixed arm**：REJECT / primary_regression —— Gold +0.07pp [−0.36, +0.53]，Good **−0.47pp [−1.00, 0.00]**。
- **refit arm**：REJECT / primary_regression —— Gold +0.34pp，Good −0.47pp [−1.23, +0.27]，**NDCG@5 −0.0046 [−0.0078, −0.0013]**（CI 全負）。
- live guard：primary_regression。Holm p：fixed 1.0、refit 1.0。研究判決 **both_arms_reject**。
- stale：`baseline_weights_stale = False`。

## 參考（v3 fixed_rule 全紀錄 2,485 場）

- Gold +0.24pp [−0.15, +0.65]、Good **−0.44pp [−0.88, 0.00]**；分層 **11–12 匹 Good CI 全負**。
- 頭兩名 $15+ 跑尾三分一：163 → **171 [+1, +15]**，CI 全正 —— 更多冷門跑包尾。

## 解讀

人馬配搭分單獨 AUC 最低，但搬走佢嘅份額令排名變差、冷門跑包尾變多。即係佢喺組合入面帶住騎師／練馬師分冇嘅資訊
（同一個人嘅年度率，對唔同馬匹都一樣；配搭分係**呢匹馬同呢個騎師**嘅紀錄）。同 memory「場內 AUC ≠ 邊際貢獻」一致：
份額要跟邊際貢獻，唔係跟單獨準確度。**唔再試其他份額組合**（登記：唔准試第二組）。

失敗實驗：研究變體 `jt_auc` 只喺 `scratch/au_paceperf_variants_20261016.py`，**冇改 production code**。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scratch/au_jt_audit_dump_20261016.py --variant f6a --out $S/jt.json     # @05dd1b20
# A0 = k2 特徵 + exact_score；A1 = 同一份特徵，variants.apply("jt_auc") 之後 exact_score
python3 scratch/au_paceperf_refit_20261016.py --variant f6a    predict --data $S/A0.json --out $S/wf_A0.json
python3 scratch/au_paceperf_refit_20261016.py --variant jt_auc predict --data $S/A1.json --out $S/wf_A1.json
python3 scratch/au_paceperf_s8_20261016.py --base $S/wf_A0.json --cand $S/wf_A1.json --label jt_auc --out $S/s8.json   # 需要 §8 模組
```
