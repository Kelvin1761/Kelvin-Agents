# EXP-20261016-09 結果：近績質素分加返負距

- **預先登記**：[protocol](EXP-20261016-09-au-form-quality-margin-protocol.md)（commit `8a2cf010`）
- **比較對象**：已上線 eq2_N6（replica，同 EXP-06 一樣語料、refit 程序 hash `f92c8377…`）。1,482 場／41 日 OOS。
- 研究診斷（來源 FLAG）。

**決定：三個候選都唔合資格 → 保留 eq2_N6。** 加負距會減少頭兩名冷門跑包尾，但幅度未顯著，而且 Gold 有輕微代價。

| 候選 | fixed Gold | fixed Good | refit Gold | 頭兩名 $15+ 跑包尾（vs 166） | 首選跑包尾 |
|---|---:|---:|---:|---|---:|
| eq3_N6 | −0.54pp [−2.03, +0.82] | +0.27pp | −0.88pp | 157（−9 [−25, +8]） | +0.28pp |
| pen_N6 | −0.34pp [−1.60, +0.87] | −0.61pp | −0.68pp | 161（−5 [−18, +7]） | +0.28pp |
| gate_N6 | −0.07pp [−1.00, +0.82] | +0.47pp | −0.47pp | **154（−12 [−25, +1]）** | +0.16pp |

全部 `REJECT / primary_regression`（Gold 點估計 < 0）。上線規則 (B) 要 Gold／Good 都 ≥ 0 **兼** 跑包尾 CI 上界 < 0：
gate_N6 最接近（Gold −0.07pp、跑包尾 CI 上界 +1），未達。

## 解讀

- 「高班輸得遠」嘅確係被新擠入頭兩名嗰批冷門嘅特徵（EXP-08 後續診斷），而三個負距寫法都將跑包尾拉低 5–12 場，方向一致。
- 但呢批馬入面，412 匹熱門入咗位、只有 85 匹冷門跑包尾 —— 一刀切按負距扣分會連入位嘅一齊誤傷，所以 Gold 跌。
- 下一步要分得開「降班有實力」同「高班輸開冇實力」：單靠負距唔夠，可能要睇同一場馬嘅對手質素／賽績線，或者負距相對該場分散度。

## 重跑

```bash
python3 scratch/au_merged_form_quality_20261016.py build --dump $S/merge.json --outdir $S/mfq9
python3 scratch/au_paceperf_refit_20261016.py --variant f6a predict --data $S/mfq9/<cand>.json --out $S/mfq9/wf_<cand>.json
python3 scratch/au_paceperf_s8_20261016.py --base $S/mfq9/wf_eq2_N6.json --cand $S/mfq9/wf_<cand>.json --label X --out $S/mfq9/s8_<cand>.json
python3 scratch/au_l600_candidates_20261016.py flops --base $S/mfq9/eq2_N6.json --cand $S/mfq9/<cand>.json
```
