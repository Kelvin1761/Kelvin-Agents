# EXP-20260928-09 — HKJC race-shape coordinate transfer

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：REJECT_DEV / BEST CANDIDATE SHADOW-ONLY
- **上游**：EXP-06/07/08；terminal 全部未開。
- **假設**：shape 減權本身改善排序但 proportional redistribution 損害 primary；將細份額
  只交予較可信單一維度，可能保住 Gold／Good。
- **Harness**：`docs/experiments/patches/hkjc_shape_coordinate_transfer.py`

## 固定候選

- transfer `2pp / 4pp / 6pp`，由現役 race-shape 27.37%直接移去一個維度；其餘不變。
- destination 固定：`stability`、`form_line`、`trainer_signal`、`class_advantage`。
- 不測 `horse_health`：過往場內 AUC低過0.5，而 EXP-06 optimizer已錯誤放大佢。
- 不測 `sectional`：多次 PIT refit均要求向下，shape→sectional固定候選亦已 REJECT。
- inner shape、初出馬、post-matrix adjustment全部鎖定。

同 EXP-08 使用相同 dev 274／terminal 46、5個日期 block、metrics同 eligibility gate。
選擇順序固定為 transfer 由小至大；同 transfer 依 `stability → form_line → trainer → class`。
揀第一個 pass，唔取 argmax。只開一個 terminal，Stage-4 v2照舊。

## 結果

12/12 固定候選 fail，terminal 未開。最接近合格係 `t02_stability`：由 race-shape
轉 2pp 去 stability（27.37%→25.37%；9.83%→11.83%）：

- Gold −0.365pp（274 場少 1 場），Good／Champion 0；
- capture@5 +0.9732pp，CI `[+0.3650,+1.7032]pp`；
- competitive recall +0.7482pp，CI `[+0.2737,+1.2774]pp`；
- NDCG +0.3825pp，CI 跨 0；
- 只有 2/5 reporting blocks 同時守住 Gold／Good。

其餘 2pp destination：form Gold −1.095pp／Good −0.365pp；trainer Gold 0但 Good
−1.095pp；class Gold／Good各 −0.730pp。4pp、6pp 通常令 ranking 再升，但 Gold 仍負，
所以唔存在「只係 redistribution destination 揀錯」嘅證據。原始輸出：
`/tmp/hkjc_shape_coordinate_transfer_20260928.json`。

**判決：REJECT_DEV。** `t02_stability` 已喺 EXP-20260928-10 凍結成 prospective
shadow，但未達 live promotion gate；所有 production 權重不變。
