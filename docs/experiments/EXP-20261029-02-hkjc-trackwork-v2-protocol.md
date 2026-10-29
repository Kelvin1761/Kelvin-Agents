# EXP-20261029-02 — HKJC 晨操 v2 讀法 + 「剷走晨操」（預先登記）

- **日期**：2026-10-29；平台：HKJC；baseline = main `6313aa1e`
- **Kelvin 要求**：唔好再淨係比首尾兩課總時間同數課數；用段速、場地、距今日數、上仗之後嘅備戰、
  馬匹平時習慣去重建晨操，睇吓搵唔搵到入分嘅讀法；同埋剷走晨操會點。
- **承接**：EXP-20261029-01 已經篩過六個訊號，全部 UNRESOLVABLE。呢次係**新家族**，
  同上次一齊報，唔會因為今次加特徵就當上次冇做過。

## 1. 剷走晨操（`fixed_rule`）

Arm `docs/experiments/patches/hkjc_arm_no_trackwork.py`：`trackwork_trend_score` → 60、
初出馬 `_prep_score`（備戰分）→ 60。即係晨操完全唔入排名。Stage 4 v3 全紀錄。

## 2. v2 讀法：新增四個特徵（全部只用賽日之前、剔出賽行、跑步機按 type_raw）

| key | 定義 |
|---|---|
| `trial_speed_z` | 最近一次試閘總時間，同**同日同地點同路程**嘅所有試閘比，z（快 = 正）；參照 < 6 個 = 缺 |
| `trial_finish_z` | 最近一次試閘最後一段，同上參照群體，z（快 = 正） |
| `work_accel_z` | 最近一課（≥2 段）快操「最後一段 − 前一段」，同同日同地點快操比，z（加速越勁 = 正） |
| `quality_work` | 窗口內快操最後一段 z ≥ +0.5 嘅課數（同日同地點參照） |

缺值 = 場內平均（中性）。

### 2a. 單項篩選（資訊用，Holm 跨四個）
方法同 EXP-20261029-01：baseline 綜合分 offset、前 60% fit、後 40% 測、OOS ΔLL bootstrap CI。

### 2b. 主判決：walk-forward 晨操 v2 調整
- 特徵 = 上次六個 + 今次四個（共十個），場內置中。
- 每個賽日 d：只用 d **之前**全部賽日 fit conditional logit（offset = baseline 綜合分/τ，τ=3，L2 = 0.01），
  得 β；d 嘅非初出馬 `raw' = raw + τ·xβ`，重新排名。頭 10 個賽日（burn-in）唔郁。
- 判決：Stage 4 v3 `walk_forward_oos`（harness compare），leakage audit 要過。
- **一次過**：唔換 λ、τ、burn-in、特徵；失敗就照記。

### 2c. 如果 2b 判 WIN
先做 ablation（十個特徵逐個拿走）先可以談上線；仲要 forward holdout（之後未睇過嘅賽日）確認。

## 3. 剩餘顯示 bug（§7，唔入分）
`trial_sectional_signal` 以前有試閘時間就係 `strong`（「試閘段速訊號強」常數）→ 改做 `timed`，
顯示「有計時（未評級）」。

## Leakage
參照群體都係賽日之前發生嘅操練／試閘；walk-forward 每個賽日只用之前嘅賽果。冇賠率。
