# EXP-20260928-06 — HKJC 7D＋Race-shape hierarchical constrained refit

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：REJECT_DEV / TERMINAL UNOPENED
- **假設**：現役 `race_shape=27.37%` 過重，但過往一次過 joint refit 將噪音分畀
  health 等維度；將 outer 7D 同 venue-specific race-shape components 分層、正則化、
  expanding-time 擬合，可以找到較穩健而可解釋嘅 replacement。
- **搜索過嘅舊記錄**：EXP-20260902-03/08/10、EXP-20260904-05/07、
  EXP-20260927-03/04、EXP-20260928-01/03。舊證據一致話 shape 過重，但候選均未過
  primary gate；今輪新增資料係 320 場語料、PIT surface performance，同明確 nested
  outer/inner ablation。
- **Harness**：`docs/experiments/patches/hkjc_hierarchical_refit.py`

## 固定資料與防洩漏

- 語料固定 `/tmp/hkjc_ranking_dataset_20260928_v2.csv`；同一 meeting/race 不拆。
- 唯一日期排序，最後 15% 日期鎖作 terminal；任何 optimizer／候選選擇都不可讀。
- dev 以最早 40% 日期起步，餘下日期切成 5 個連續 expanding-time validation blocks。
- surface quality 只讀同馬、`history_date < target_date`、同表面、路程 ±200m、730 日、
  365 日半衰、4 個中性 pseudo-runs。
- shape draw／fit／trip 只由賽前 Logic 重建；結果只作 training label／評估，唔入特徵。
- 不用 odds、當場結果、事後 incident、預測跑法、leader/on-pace/backmarker score。
- 初出馬整套 scoring 鎖定；所有候選只改標準馬，保留 post-matrix adjustments。

## 固定擬合

共同 objective：官方頭三對同場較後馬匹嘅 weighted pairwise logistic loss，temperature=6；
所有參數用 L2 `0.18` 收縮返 production baseline。唔搜尋 loss／regularization／split。

### Outer 7D

- 七個權重非負、和為 1、每項上限 0.40。
- baseline 係 production 7D。
- final dev fit 以 80 次 meeting-date bootstrap 成功解嘅逐參數中位數作 consensus，
  再正規化；唔取最好一次、唔用 terminal 揀。
- 80 次之中少過 60 次成功收斂，視為參數不穩，terminal 不開。

### Race-shape inner

- 沙田草／AWT：
  `60 + wd(draw−60) + wf(fit−60) + wt(trip−60) + ws(surface−60)`；四權非負、和為1。
  baseline `[.55,.25,.20,0]`。
- 跑馬地：
  `60 + wd(draw−60) + clip(wf·fit_delta + wt·trip_delta + ws(surface−60),−10,+7)`；
  `wd∈[.5,1.25]`、`wf/wt∈[0,1.5]`、`ws∈[0,.75]`；baseline `[1,1,1,0]`。
- 分數最後 clip 0–100。跑馬地係 component multiplier，唔冒充總和為1嘅權重。

## 預先鎖定 arms 與選擇

| Arm | Outer | Shape inner | 身份 |
|---|---|---|---|
| `current_live` | production | production | baseline |
| `outer_only` | fit | production | eligible |
| `inner_only` | production | fit | eligible |
| `combined` | fit | fit；交替 outer/inner 最多3輪 | eligible interaction |

每個 arm 先用5段 expanding-time dev OOS。可進 terminal 必須：

1. aggregate dev Gold、Good 都不低過 baseline；
2. 至少 3/5 fold 同時 Gold、Good 不低過 baseline；
3. `top3_capture_at5`、`competitive_recall_at5`、`ndcg_at5` 至少兩項 aggregate 正。

多個合格時固定優先 `outer_only` → `inner_only` → `combined`（最簡單優先）；只開
一個 locked arm 嘅 terminal。若全不合格，terminal 不開，判 `REJECT_DEV`。

開 terminal 後用 Stage-4 v2：Gold／Good 任一 terminal 點估計負即 REJECT；其餘
PRIMARY/RANKING 判決完全跟 `docs/model-evaluation-contract.md`。另報 ST turf、HV turf、
ST AWT、field-size cohort；AWT 樣本不足只描述，不獨立選 formula。

## 結果

先做咗 baseline-replica gate。初版 harness 因直接重建 shape 而同 production 有落差，
`mean |delta|=0.987`、最大 11.256、807 行超過 0.05，判無效，冇用嗰次結果。
修正為只將候選 formula 相對 production formula 嘅 delta 加返落 archive 已存
`matrix_race_shape` 後，baseline 3,972 行逐行完全一致（mean/max delta 0、0 行超過0.05）。

5 段 expanding-time OOS 共 163 場：

| Arm | Gold Δ | Good Δ | capture@5 Δ | recall@5 Δ | NDCG@5 Δ | primary 非負 folds |
|---|---:|---:|---:|---:|---:|---:|
| outer-only | −1.8405pp | −1.2270pp | +0.8180pp | +1.7791pp | +1.5409pp | 2/5 |
| inner-only | −2.4540pp | −1.2270pp | −0.4090pp | −0.1227pp | −0.1402pp | 2/5 |
| combined | −1.8405pp | −1.2270pp | +0.8180pp | +1.7791pp | +1.5409pp | 2/5 |

`outer-only` competitive-recall CI `[+0.2147,+3.4049]pp`，但 Gold／Good primary
回歸。`inner-only` Gold CI `[−4.9080,−0.6135]pp` 全負。三個 arm 全部不合格，
所以 terminal 46 場嚴格未開。

全 dev direct-fit 只作方向診斷：outer 將 race-shape 壓到 3.67%，同時錯誤放大
`horse_health` 到 17.07%；ST inner 約為 draw 47.29%、fit 23.45%、trip 23.00%、
surface 6.26%，HV surface scale 近零。呢啲方向未能守住 OOS primary，唔係 production
建議。原始輸出：`/tmp/hkjc_hierarchical_refit_20260928.json`。

**判決：REJECT_DEV。** Joint refit 證實 ranking objective 想大幅減 shape，但亦證實單一
pairwise objective 會錯配其他弱維度；唔開 terminal、唔改 live 權重。
