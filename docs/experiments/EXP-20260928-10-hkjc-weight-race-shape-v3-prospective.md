# EXP-20260928-10 — HKJC Weight refit＋Race Shape V3 prospective shadow

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：CLOSED FOR NEW B SNAPSHOTS / 歷史 immutable snapshots 繼續結算
- **上游**：EXP-20260928-03/06/07/08/09。
- **目的**：將 retrospective 最接近合格嘅 weight refit，同只喺跑馬地有一致方向嘅
  Race Shape V3，凍結成可歸因、可賽後結算嘅 forward arms。

## 凍結 arms

| Arm | Outer 7D | Race Shape | 用途 |
|---|---|---|---|
| mainline | production | production | 唯一正式排名 |
| `weight_refit_t02` | shape 27.37→25.37%；stability 9.83→11.83% | production | A：權重消融 |
| `race_shape_v3_hv` | production | HV draw＋`0.45×(PIT surface−60)`；ST production | B：子公式消融 |
| `race_shape_v3_hv_t02` | A | B | A+B interaction |

初出馬完整鎖定。B 喺沙田係 no-op；判決只睇 `profile_applied=true` 嘅 forward races。

## Race Shape V3 component contract

- `draw`：現役賽前檔位分。
- `surface_performance`：同馬、`history_date < target_date`、同表面、路程±200m、
  730日、365日半衰、4個中性 pseudo-runs；泥地無本地往績先可用外地
  Dirt/Synthetic。
- `historical_lane_fit`、`historical_trip_consumption`：保留輸出供 ablation 審計；
  HV V3 權重固定為 0。
- `field_tempo`：固定 `withheld_insufficient_reliability`、權重0。近兩次跑馬地今仗
  位置預測只有約44–46%，而 Auto contract 禁止 pace forecast；唔准改名後重新入分。
- 沙田暫維持 production，因 retrospective HV方向正、ST Gold負。

## 防洩漏與保存

- 每次 pre-race Auto 同時計三個 arms，但只寫入 `shadow_profiles`／
  `python_auto_shadow_verdicts`，不改 `python_auto_verdict`、official Top 4或報告排名。
- 賽後 monitor **只讀 immutable `Prediction_Snapshots`**；逐個 Logic SHA-256 必須同
  manifest 一致，否則拒絕結算。
- 官方賽果之後才 join；ledger deterministic upsert，唔用賽果重算 prediction。
- Ledger：HKJC daily state 旁邊
  `HKJC_Weight_RaceShape_V3_Prospective.json`；任何 profile 永不自動 promote。

## 預先鎖定 review 門檻

- A：最少120個 active races。
- B、A+B：各最少80個跑馬地 active races。
- 達場數只會轉 `ready_for_locked_review`，仍要 Stage-4 v2：Gold、Good 均不可負；
  ranking 至少兩項改善、至少一項 paired race bootstrap CI 下界>0；venue／field-size
  guardrail不可有實質 regression。
- A、B逐項先判；A+B只有喺 interaction 有額外邊際時先可保留。唔准用 prospective
  結果改 arm、公式、門檻或起始 snapshot。

## 歷史 wiring／interaction sanity check（不可晉級）

同一批已經參與形成假設嘅 320 場只用嚟確認三個 arm 接線正確：

| Arm | Gold Δ | Good Δ | capture@5 Δ | recall@5 Δ | NDCG Δ |
|---|---:|---:|---:|---:|---:|
| A：weight t02 | −0.31pp | 0.00pp | +0.83pp | +0.64pp | +0.41pp |
| B：HV V3 | +0.31pp | +1.25pp | +0.31pp | +0.31pp | +0.36pp |
| A+B | −0.31pp | +0.94pp | +1.04pp | +0.80pp | +0.46pp |

B 喺115場跑馬地 Gold +0.87pp、Good +3.48pp、NDCG +1.01pp；沙田逐項零差，
確認 venue gate 真係 no-op。A+B 排序增幅較大，但重新帶入 A 嘅 pooled Gold 負數，
所以 interaction 並冇 retrospective primary 優勢。呢批語料已睇過，三組數字一律唔可
作 promotion evidence；原始輸出：`/tmp/hkjc_weight_shape_v3_shadow_replay_20260928.json`。

## 實作

- Engine shadow：
  `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/engine_core.py`
- 多 arm orchestration：
  `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py`
- Immutable settlement／ledger：
  `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_shadow_monitor.py`
- Post-race scheduler 接線：
  `.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py`
- Diagnostic replay：
  `docs/experiments/patches/hkjc_weight_shape_v3_shadow_replay.py`

## 2026-09-29 後續

用戶明確接受未完成 prospective 門檻嘅風險，要求先啟用 B。新預測由
`EXP-20260929-01` 接手：B 成為只限跑馬地標準馬匹嘅實驗主線；沙田、AWT、初出馬
不變。舊 snapshot 仍按本文件原定規則結算，但新 snapshot 不再把 live V3 當自己嘅
candidate；改收 `race_shape_v2_legacy_hv` rollback comparator。
