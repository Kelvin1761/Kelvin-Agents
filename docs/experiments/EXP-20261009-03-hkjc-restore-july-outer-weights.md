# EXP-20261009-03 — HKJC 還原被 merge 食咗嘅七月外層權重

- 日期：2026-10-09；平台：HKJC；狀態：**REJECT（primary_regression: good_positional）**
- 起因：Kelvin 問「race_shape 係咪佔太多權重」。
- 背景：live `race_shape` 0.2737 唔係任何一次 fit 嘅結果，係 2026-08-09 merge `f7d35de5`
  揀咗 parent 1；parent 2 帶住 2026-07-30 驗證過嘅 CORE_BALANCE。四次獨立 fit 都指向
  0.17–0.24，但之前所有減 race_shape 嘅測試都過唔到閘。
- 呢個係**失敗實驗**；冇改 live 權重。

## 預先登記（跑結果之前寫低，原文）

### PRE-REGISTRATION — HKJC restore lost July outer-weight fit (2026-10-09, before running)

Fact: live MATRIX_WEIGHTS (race_shape 0.2737) came from merge f7d35de5 picking parent 1;
parent 2 carried the validated 2026-07-30 CORE_BALANCE fit (2c9e6ffb). Tests and three docs
claim CORE_BALANCE is live.

Single arm, no grid: CORE_BALANCE translated to the current 7D layout with the repo's own
renormalisation (sectional 0.65×0.1849, others ×1/0.935285):
sectional 0.1285, trainer_signal 0.2469, stability 0.1090, race_shape 0.2416,
class_advantage 0.1534, horse_health 0.0404, form_line 0.0801 (sum 1.0000).
DEBUT_MATRIX_WEIGHTS unchanged.

Baseline: release 7aa8cda engine on the corpus-replay candidate Logic (333 races).
Candidate: identical except MATRIX_WEIGHTS above. Real engine, both arms.

Decision: Stage-4 v2 (`evaluate_candidate`), locked 15% terminal. Any primary point
regression on dev or terminal → REJECT. Not claimed as §7: the engine changed after July,
so restoring a July fit is a model change, not a provable-error fix. Cohorts HV/ST,
field ≤10/≥11 reported. No second arm will be tried on this corpus whatever the result.


## 結果（真 engine 兩邊，332 場可比；19 場 engine 拒絕，兩邊排除）

| 指標 | Dev Δ | Terminal Δ | Terminal CI |
|---|---:|---:|---|
| gold | +0.0036 | +0.0175 | [0.0000, +0.0526] |
| good_positional | **−0.0109** | 0.0000 | [0, 0] |
| top3_capture_at5 | +0.0061 | +0.0175 | [0.0000, +0.0409] |
| ndcg_at5 | +0.0023 | +0.0097 | [−0.0069, +0.0287] |
| competitive_recall_at5 | +0.0062 | +0.0088 | [−0.0088, +0.0263] |
| mean_top3_model_rank（越低越好） | −0.0306 | −0.0058 | [−0.0877, +0.0702] |

Cohorts（全語料 Δ）：HV 119 場 Gold +0.84pp／Good −1.68pp；ST 213 場 +0.47／−0.47；
馬匹 ≤10 29 場 +3.45／0.00；≥11 303 場 +0.33／−0.99。132 場頭四次序有變。

**判決：REJECT**。Dev Good −1.09pp（275 場入面約 3 場）。其他方向都啱，但冇一個 CI 離開零。
預先登記寫明：呢個語料唔再試第二個 arm。

## 意義

- 「race_shape 太重」呢個直覺有理據（fit 一致指向更低；權重係 merge 意外），
  但喺 333 場上，減佢嘅收益同 Good 嘅損失都細過噪音。七月值同 live 之間個 objective 係平嘅。
- 前瞻：`weight_refit_t02`（shape −2pp → stability）已經喺 immutable snapshot 量緊，
  10-07 起 9/120 場。七月值亦可以用 `scratch/hkjc_weight_restore_ab.py` 喺 10-09 之後
  嘅賽日前瞻再量一次（同一個 arm，唔改值）。
- 做呢個 A/B 時發現 `weight_refit_t02` 凍結 arm 會跟 live 權重漂移，已修（見 EXP-20261009-01）。
