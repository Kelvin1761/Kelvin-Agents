# EXP-20260929-02 — HKJC 沙田 Race Shape component shrink

- **日期**：2026-09-29
- **平台**：HKJC
- **狀態**：**ELIGIBLE REJECT；DRAW70 FORWARD SHADOW**
- **假設**：沙田現行 `55% draw + 25% fit + 20% trip` 對 fit／trip 信得過多；只將
  trip 一半向中性60收縮，可能保留 Gold 同時改善排序穩定性。
- **搜索過嘅舊記錄**：EXP-20260904-05/07、EXP-20260927-03/04、
  EXP-20260928-01/03/04/08/09。

## 預註冊 arms

初出馬、跑馬地、沙田 AWT 全部 no-op；只改沙田草地標準馬匹。外層 7D 權重不變。

| Arm | 沙田草地 race-shape | 身份 |
|---|---|---|
| baseline | `.55 draw + .25 fit + .20 trip` | 現役 |
| `trip_half` | `.55 draw + .25 fit + .10 trip + .10×60` | **唯一 eligible** |
| `fit_half` | `.55 draw + .125 fit + .20 trip + .125×60` | diagnostic ablation |
| `both_half` | `.55 draw + .125 fit + .10 trip + .225×60` | interaction diagnostic |
| `draw70` | `.70 draw + .15 fit + .15 trip` | diagnostic；測 draw 集中化 |

理由：draw 喺19/19 walk-forward folds正；fit係數接近0；raw trip 只有1/19正，但舊消融
完全剷 trip 令沙田 Gold 點估計跌，所以 eligible 只做保守一半收縮。唔再測已知令沙田
Gold跌1.55–2.58pp嘅 surface replacement，亦唔測 rejected 同日 position bias。

## 判決

- 唯一日期尾15%作 terminal；唔准用 terminal 揀 arm。
- `trip_half` Gold／Good 喺 dev 或 terminal 任一負數即 REJECT。
- primary 無回歸先睇 capture@5、competitive recall@5、NDCG@5；Stage-4 v2不改。
- 必報沙田草地、距離、field-size、course configuration cohort；AWT樣本不足不作公式。
- diagnostic arm 即使最好，本輪亦不可上線，只可凍結成下一個 hypothesis。

## Leakage contract

只用 immutable dataset 內賽前分數及已完成賽果作事後評估；候選不讀 odds、當場結果、
事後 incident、今仗預測跑法或未來統計。所有馬匹同場配對；無資料仍係中性60。

## 結果

語料 32 meeting／320 race／3,972 runner；沙田草地 194 場（dev 176、terminal 18）。

| Arm | ST Gold Δ | ST Good Δ | ST capture@5 Δ | ST NDCG Δ | Stage-4 |
|---|---:|---:|---:|---:|---|
| `trip_half` | −0.52pp | +1.55pp | +0.34pp | +0.16pp | **REJECT: dev Gold負** |
| `fit_half` | −0.52pp | 0.00pp | +0.69pp | +0.45pp | **REJECT: dev Gold負** |
| `both_half` | −1.03pp | +1.55pp | +0.86pp | +0.36pp | **REJECT: dev Gold負** |
| `draw70` | **0.00pp** | **0.00pp** | +0.34pp | +0.19pp | ranking evidence too weak |

`trip_half` 係唯一 eligible，按預註冊 primary 規則淘汰。三個 shrink arm 都顯示相同
trade-off：排序略升但 Gold 下跌，唔會改 production。

`draw70` 係唯一 Gold／Good 全樣本同 dev 都打和嘅 arm，但排名 CI 未過閘，而且原本只係
diagnostic。依規矩唔會事後升格上線；凍結成 `race_shape_st_draw70` forward shadow，最少
80 場 active 沙田草地先人工 Stage-4 review。AWT、HV、初出馬 no-op。

**決定**：`trip_half`／`fit_half`／`both_half` REJECT；`draw70` NEEDS FORWARD EVIDENCE。
production 沙田公式不變。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 \
  docs/experiments/patches/hkjc_sha_tin_shape_shrink.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --output /tmp/hkjc_sha_tin_shape_shrink_20260929.json
```
