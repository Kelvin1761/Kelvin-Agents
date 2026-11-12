# EXP-20261112-07 HKJC 段速維度：現有「步速修正偏差」逐仗按負磅換算

- **日期**：2026-11-12 ｜ **平台**：HKJC ｜ **觸發**：Kelvin「跑段速維度版」
- **假設**：`finish_time_adj`（近 3 仗）逐仗按（今仗負磅 − 當時負磅）換算後再分四級，排名會改善
- **搜索過嘅舊記錄**：EXP-20261112-04／-05／-06；EXP-20261016-14／-16（段速維度審查）
- **改到嘅檔案／組件**：冇 live 改動；arm `hkjc_arm_sectional_weight_converted.py`

## 發現（唔係假設嘅一部分）
`inject_hkjc_fact_anchors.py` V5.1：`adj_dev = raw_dev − (頭馬時間 − 標準)` = 完成時間 − 頭馬時間 = **輸頭馬幾多秒**（`margin × 0.17`）。
即係「步速修正完成時間偏差」呢個名唔啱，佢係一個相對當場對手嘅數，同標準時間無關。

## 配置（跑之前寫死）
baseline origin/main `4e6dae6a`；每仗偏差 += 0.01123 × 路程(km) × 負磅差；四級門檻唔郁；
`ft`（只換算偏差）、`ft+l400`（再加 EXP-05 嘅 L400 換算，主 arm）；`fixed_rule`

## 結果（389 場）
| arm | 郁咗場次 | Gold | Good | 頭三換入／換出上名 | 判決 |
|---|---|---|---|---|---|
| ft | 154 | −0.77 [−1.88, +0.26] | −0.77 [−2.34, +0.78] | 5／26 vs 10／26 | REJECT / primary_regression |
| ft+l400 | 189 | −1.29 [−2.60, 0.00] | −0.51 [−2.06, +1.03] | 11／37 vs 13／37 | REJECT / primary_regression |

## 結論
輸頭馬幾多係相對數：降班馬喺高班輸得多、今仗又加磅，按絕對負磅差換算會罰兩次。EXP-06 證實有效嘅負磅換算係建基於扣走賽事效應嘅時間數字。
**決定**：REJECT ｜ **commit**：未 commit 任何 model code ｜ leakage-audit PASS（賽前賽績檔）

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
WC_EXP_SEC_PARTS=ft+l400 PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm docs/experiments/patches/hkjc_arm_sectional_weight_converted.py --out cand.jsonl
python3 $H compare base.jsonl cand.jsonl --stage4 fixed_rule --leakage-audit-passed
```
