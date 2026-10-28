# EXP-20260929-01 — HKJC 跑馬地 Race Shape V3 實驗主線

- **日期**：2026-09-29
- **平台**：HKJC
- **狀態**：**USER-ACCEPTED EXPERIMENTAL LIVE / 未通過正式 promotion 門檻**
- **上游**：EXP-20260928-01/03/10
- **baseline commit**：`0116c740` 加當前未提交 HKJC 修正

## 決定

用戶明確要求先啟用歷史結果最一致嘅跑馬地候選。只限非初出馬跑馬地：

`race_shape = draw + 0.45 × (PIT individual HV-turf performance − 60)`

歷史 fit／trip 保留作解釋及 rollback 診斷，但 live 權重為 0；不使用已移除、近兩次
跑馬地只有約 44–46% 命中嘅今仗跑法預測。field tempo 固定 withheld。沙田草地、
沙田 AWT、初出馬同外層 7D 權重完全不變。

## 證據與限制

同一批 320 場 retrospective replay 入面，跑馬地 115 場相對舊公式：Gold +0.87pp、
Good +3.48pp（95% paired CI +0.87 至 +6.96pp）、NDCG@5 +1.01pp
（+0.29 至 +1.79pp）。沙田係 exact no-op。

但候選係睇過呢批 cohort 結果後形成，未達 EXP-10 預註冊嘅 80 場 forward 門檻，
所以以上只證明接線及歷史方向，**唔係正式 out-of-sample promotion 證據**。今次係用戶
接受風險嘅有限實驗上線，唔可以描述成已證實改善。

## 安全與 leakage

- surface 只用同馬、`history_date < target_date`、同表面、路程±200m、730日、
  365日半衰、4個中性 pseudo-runs；無資料=60。
- 結果只喺 immutable snapshot 之後 join，唔入評分。
- run contract 保存實際公式；預設 `v3_surface`。
- 緊急回退：`WC_HKJC_HV_RACE_SHAPE_PROFILE=legacy_v2`。
- 每次新 snapshot 同時計 `race_shape_v2_legacy_hv`，20場跑馬地後只觸發人工 rollback
  review，永不自動改模型。

## Ablation／範圍

| 變更 | 狀態 | 理由 |
|---|---|---|
| HV 子公式 V3 | experimental live | 歷史 HV primary/ranking 同向；用戶接受未滿 forward 門檻 |
| 7D weight t02 | shadow | pooled Gold 仍負，不隨 V3 一起上線 |
| 沙田套用 surface formula | reject | ST turf Gold −1.55 至 −2.58pp |
| 初出馬套用 V3 | locked/no-op | 冇可用個體 surface history，避免假精準 |

## 驗證

- HKJC Wong Choi Auto：124 passed；HKJC daily auto：66 passed。
- 語法編譯通過；HKJC golden：120 匹馬全部一致。golden corpus 冇命中今次 HV
  surface 分支，所以另外有公式、legacy shadow、env rollback 同 ST/AWT no-op 單元測試。
- HKJC data contract 以 342 場／4,300 匹馬重新校準，引擎 fingerprint
  `4ba256d1c33f`；最近 150 場／1,906 匹馬全部欄位符合基準。
- `./檢查.sh --quick` 全綠；`./檢查.sh` 全部 15 個 suites 通過（包括
  HKJC extractor 48、reflector 49、shared racing 74、race compliance 26）。
- AU data contract 只剩 `stale-baseline`／`preparation_score` new-field 警告，gate
  仍通過；屬並行 AU 工作，未用今次 HKJC 校準覆蓋。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 \
  docs/experiments/patches/hkjc_weight_shape_v3_shadow_replay.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --output /tmp/hkjc_weight_shape_v3_shadow_replay_20260929.json
```

**決定**：USER-ACCEPTED EXPERIMENTAL LIVE；未 commit／未 push。

## 2026-10-27 — rollback review（`race_shape_v2_legacy_hv`，27/20 場）

- **規則（量度前定）**：呢份記錄冇寫判決規則，所以借用 shadow monitor 現成嘅 rollback gate：舊版喺 Gold 或 Good
  淨多贏 ≥ 2 場、另一個 primary 唔係負數 → 建議 rollback；另報按賽日 bootstrap 嘅配對 CI。
- **資料**：immutable 賽前快照 ledger（`HKJC_Weight_RaceShape_V3_Prospective.json`），跑馬地 active 27 場／3 個賽日
  （10-07、10-14、10-21），頭四有變 17 場。
- **結果（舊版 − live V3）**：Gold 淨 0、Good 淨 −1、頭馬淨 −2；頭五捕捉平均 −0.0494 [−0.0741, −0.0370]、
  NDCG@5 −0.0679 [−0.1111, −0.0294]（兩個 CI 全負 = live V3 較好）。
- **決定**：唔觸發 rollback，**維持 V3**。⚠️ 只得 3 個賽日，bootstrap 以日做單位好粗；呢個係「冇理由退」，
  唔係「V3 已證實」。`race_shape_v2_legacy_hv` shadow 照計，做緊急對照。
