# EXP-20260928-03 — HKJC Race Shape v2 deterministic A/B

- 日期：2026-09-28；平台：HKJC。
- 狀態：**REJECT / SHADOW FOLLOW-UP**。唯一可晉級候選未過 Stage-4；沒有改 live formula。
- 上游診斷：`EXP-20260928-01-hkjc-surface-shape-ml.md`。
- Harness：`docs/experiments/patches/hkjc_race_shape_v2_ab.py`。

## 固定假設

現役 race-shape 外權 27.37%。上游嚴格 PIT 診斷顯示 draw 穩定正向、fit 接近零、
trip consumption 19 folds 只有 1 fold 正向，而個別目標場地表現 19/19 folds 正向。
今輪只驗證 deterministic mapping，唔搜尋權重。

## 預先鎖定 arms

| Arm | 沙田 | 跑馬地 | 身份 |
|---|---|---|---|
| `current_live` | 現役 55% draw + 25% fit + 20% trip | draw + fit/PI/trip delta | baseline |
| `no_trip` | trip 設中性 60 | 移除「近仗消耗」delta | 單項 ablation |
| `surface_replaces_trip` | 55% draw + 25% fit + 20% surface | 移除 trip delta，再加 `0.20 × (surface−60)` | **唯一可晉級候選** |
| `draw_only` | 55% draw + 45% 中性 60 | 只保留 draw | diagnostic ablation |
| `draw_surface` | 55% draw + 45% surface | draw + `0.45 × (surface−60)` | diagnostic ablation |

`surface` 固定沿用 EXP-01：同一 horse ID、嚴格 date < target、目標表面、路程
±200m、730 日上限、365 日半衰、4 個中性 pseudo-runs、field-size normalized，
再映射成 `clip(60 + 40 × (posterior−0.5), 40, 80)`。無資料等於 60。

不使用賠率、當場賽果、事後 incident、預測跑法或未來資料。外層 7D 權重保持不變；
只用線性等價方式替換 race-shape 分，初出馬用現役 20%，其餘用 27.37%。

## 鎖定判決

- dev / terminal 依唯一日期排序，尾 15% 日期為 terminal；同一日不可拆開。
- `surface_replaces_trip` 先走 Stage-4 v2：任何 Gold 或 Good 喺 dev 或 terminal
  點估計倒退即 REJECT。
- 若 primary 無回歸，才看預先登記 ranking metrics：`top3_capture_at5`、
  `competitive_recall_at5`、`ndcg_at5`；正式 `PRIMARY_WIN` / `RANKING_WIN`
  定義完全沿用 `docs/model-evaluation-contract.md`。
- 沙田草地、跑馬地草地、沙田 AWT 分 cohort。任何有合理樣本 cohort 嘅 Gold／Good
  明顯倒退，候選維持 shadow；AWT 樣本太少只報數，不獨立作 formula。
- 其他三個 arm 只解釋邊個 component 有效；即使最好亦唔可以喺今輪晉級。
- 今輪語料已用於上游探索，唔係 untouched final confirmation。即使通過，只可成為
  frozen shadow candidate；要 prospective meeting 再確認先可改 live formula。

## 結果

重建後語料為 32 meeting、320 race、3,972 runners，2026-04-12 至 2026-09-27；
surface history coverage 87.89%。尾 15% 唯一日期形成 274-race dev / 46-race terminal。

### 唯一 eligible arm：`surface_replaces_trip`

相對 current live：

| 指標 | all 320 | dev 274 | terminal 46 |
|---|---:|---:|---:|
| Gold | **−0.94pp** | **−1.09pp** | 0.00pp |
| Good | +1.25pp | +1.09pp | +2.17pp |
| Champion | +0.31pp | 0.00pp | +2.17pp |
| Top3 capture@5 | **+1.35pp** [95% CI +0.63,+2.19] | +1.34pp | +1.45pp |
| Competitive recall@5 | **+1.16pp** [+0.55,+1.78] | +1.17pp | +1.09pp |
| NDCG@5 | **+0.57pp** [+0.09,+1.06] | +0.48pp | +1.13pp |

Stage-4 verdict：**REJECT — `primary_regression: gold`**。雖然三個排序指標全樣本均有
正 CI，規則係先守 Gold／Good；dev Gold 點估計跌已經足夠淘汰，不可用 secondary
ranking 救候選。

### Component ablation

| Arm | Gold | Good | Top3 capture@5 | 判讀 |
|---|---:|---:|---:|---|
| `no_trip` | −0.63pp | +0.94pp | +0.52pp | trip 拆走改善部分排序，但 Gold 代價仍在 |
| `draw_only` | −0.63pp | **+2.50pp** | **+1.25pp** | fit/trip 整體噪音嫌疑強，但仍未守住 Gold |
| `draw_surface` | −1.25pp | +1.25pp | **+1.67pp** | 排序最好，Gold 代價亦最大 |

三個 diagnostic arm 亦全部因 dev Gold 負數而 REJECT；按預註冊規則本身亦冇晉級資格。

### Venue cohort

`surface_replaces_trip`：

- 跑馬地 115 場：Gold 0.00pp、Good +0.87pp、Champion +1.74pp、Top3 capture@5
  +1.16pp [95% CI +0.29,+2.32]、NDCG@5 +0.71pp [+0.18,+1.36]。
- 沙田草地 194 場：Gold **−1.55pp**、Good +2.06pp、Champion −0.52pp；雖然
  Top3 capture@5 +1.20pp，但 cohort primary trade-off 解釋咗 pooled candidate 點解失敗。
- 沙田 AWT 11 場：樣本不足；Good 少 1 場，不作公式結論。

`draw_surface` 喺跑馬地更加一致（Gold +0.87pp、Good +3.48pp，Good CI
[+0.87,+6.96]pp；NDCG +1.01pp [+0.29,+1.79]），但沙田 Gold −2.58pp。因此新證據
**唔支持拆兩套完整 7D**，但支持下一個 frozen hypothesis：保留沙田 current live，
只為跑馬地將 race-shape 改為 draw + PIT surface，fit／trip 退出排名。

呢個跑馬地候選係睇完 cohort 結果先形成，唔可以用同一 320 場宣稱通過。正確處理係
加入 non-ranking shadow，等未來 meeting 做 prospective confirmation；未有新數據前
不可改 production score。

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  .agents/skills/hkjc_racing/hkjc_reflector/scripts/build_hkjc_ranking_dataset.py \
  --output /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --summary-output /tmp/hkjc_ranking_dataset_20260928_v2_summary.json

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 \
  docs/experiments/patches/hkjc_race_shape_v2_ab.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --output /tmp/hkjc_race_shape_v2_ab_20260928.json
```
