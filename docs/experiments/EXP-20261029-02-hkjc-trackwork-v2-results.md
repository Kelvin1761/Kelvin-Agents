# EXP-20261029-02 — HKJC 晨操 v2 讀法 + 「剷走晨操」（結果）

- 預先登記：`EXP-20261029-02-hkjc-trackwork-v2-protocol.md`（commit `28ae9765`，跑新特徵之前）
- baseline = main `6313aa1e`；harness 411 場，判決用 345 場（剔 speed_score 死日）
- 腳本：`docs/experiments/patches/hkjc_arm_no_trackwork.py`、`hkjc_trackwork_v2.py`、`hkjc_sec7_strata.py`

## 1. 剷走晨操（`fixed_rule`）

晨操兩條入分路（`trackwork_trend_score` 維度、初出馬備戰分）全部設 60。

| 指標 | Δ | 95% CI |
|---|---:|---|
| Gold | 0.00 | [−1.20, +1.44] |
| Good | 0.00 | [−1.45, +1.19] |
| top3_capture@5 | −0.19pp | [−0.58, +0.19] |
| NDCG@5 | −0.0003 | [−0.0025, +0.0019] |
| competitive_recall@5 | 0.00 | [−0.33, +0.34] |
| 前三平均名次 | −0.0106（細 = 好） | [−0.0248, +0.0028] |

**135 場排名有郁，但 Gold／Good 淨變化都係零**；九個 cohort 冇 CI 全負。判決器：`REJECT / ranking_evidence_too_weak`。
同 EXP-20261019-04（淨剷 leaf，73 場郁，0.00）一致：**而家嘅晨操對排名冇貢獻，有冇佢都一樣。**

## 2. v2 新特徵單項篩選（Holm 跨四個）

| 訊號 | 覆蓋 | OOS ΔLL | 95% CI | Holm | 場內 AUC |
|---|---:|---:|---|---:|---:|
| `trial_speed_z` 試閘總時間 vs 同日同地同路程 | 34% | **−0.0176** | [−0.0307, −0.0061] | 1.000 | 0.4900 |
| `trial_finish_z` 試閘末段 | 34% | −0.0012 | [−0.0041, +0.0015] | 1.000 | 0.5007 |
| `work_accel_z` 快操加速度 | 89% | −0.0015 | [−0.0047, +0.0015] | 1.000 | 0.5029 |
| `quality_work` 高質快操課數 | 100% | −0.0001 | [−0.0009, +0.0007] | 1.000 | 0.4896 |

試閘速度喺前 60% fit 出正 β，後 40% 顯著蝕 —— 典型「訓練期見到、測試期反轉」。

## 3. 主判決：十特徵 walk-forward 調整（`walk_forward_oos`）

每個賽日只用之前嘅賽日 fit（頭 10 個賽日唔郁）；sanity：唔調整嘅重排 404 場 picks 同 production 0 差異。

| 指標 | Δ | 95% CI |
|---|---:|---|
| Gold | −0.29pp | [−2.26, +1.72] |
| Good | −0.87pp | [−2.94, +1.16] |
| top3_capture@5 | −0.77pp | [−2.05, +0.48] |
| NDCG@5 | −0.0017 | [−0.0089, +0.0055] |
| competitive_recall@5 | −0.70pp | [−1.97, +0.44] |
| 前三平均名次 | −0.0106 | [−0.0487, +0.0262] |

275 場排名有郁，**primary 兩個點估計都負** → `REJECT / primary_regression`。冇 ablation（2c 只喺 WIN 先做）。
最後一個賽日嘅 β 全部細（|β| ≤ 0.08）—— 模型自己都揀「差唔多唔用」。

## 4. 「操得快嘅馬跑輸預期」拆解

按最近快操末段 z 分五組（上名實際 vs 模型預期）：z≈−2 **+2.4pp**、−1 +1.2、0 −0.2、+1 −1.8、+2 **+2.1pp**。
**唔係單調**（最快嗰組反而跑贏），即係噪音形狀，唔係「操得快 = 跑得差」。
快操速度同綜合分相關 ρ 只有 +0.027（同晨操 leaf +0.16），模型本身就冇獎勵操得快嘅馬，冇嘢可以「反轉」。

## 5. 顯示 bug（§7，唔入分）

`trial_sectional_signal` 有試閘時間就係 `strong` → 每匹有試閘嘅馬都印「試閘段速訊號強」。改做 `timed`，
顯示「有計時（未評級）」；舊檔嘅 `strong` 同樣顯示「有計時（未評級）」。只入 `trackwork_trainer` 文字，冇入分。

## 結論

- 兩個實驗、十六個讀法（EXP-20261029-01 六個 + 今次四個 + 十個合併 walk-forward）都冇贏。
  **用而家有嘅資料（21 日窗、36 個賽日），晨操讀唔出準備度訊號**；讀得越多，模型越跟噪音走。
- 剷走晨操同保留佢結果一樣（Gold／Good 0.00）。舊讀法嘅設計確實粗糙，但佢只得 ~1% 權重，冇害亦冇益。
  剷唔剷屬於簡化決定，判決器冇俾 WIN，所以冇自動改。
- 下一次值得試嘅只有**新資料**，唔係新讀法：試閘嘅名次同頭馬距離（晨操頁冇，要抽試閘結果頁）、
  更長嘅操練歷史（而家淨係 21 日）。Forward `trackwork_rescreen` 照舊 60 個賽日重跑。

## 重跑

```bash
S=<scratch>; H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out $S/v2_base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm docs/experiments/patches/hkjc_arm_no_trackwork.py --out $S/v2_notw.jsonl
python3 $H compare $S/v2_base.jsonl $S/v2_notw.jsonl --stage4 fixed_rule --leakage-audit-passed
P=docs/experiments/patches/hkjc_trackwork_v2.py
python3 $P screen $S/v2_base.jsonl
python3 $P walkforward $S/v2_base.jsonl --current --out $S/v2_cur.jsonl
python3 $P walkforward $S/v2_base.jsonl --out $S/v2_wf.jsonl
python3 $H compare $S/v2_cur.jsonl $S/v2_wf.jsonl --stage4 walk_forward_oos --leakage-audit-passed
```

## 決定（2026-10-29，Kelvin）：晨操退出排名

- `scoring.TRACKWORK_SCORING = "off"`：`trackwork_trend_score` 同初出馬 `_prep_score` 一律 60；舊讀法保留喺 `"on"`。
  晨操分析、時間線、pattern 照顯示。
- 核實：live 開關回放 404 場，picks 同第 1 節 `hkjc_arm_no_trackwork.py` **零差異** —— 上線嘅就係被量度嘅嗰個。
- 預期影響：Gold／Good 0.00（第 1 節）。**係簡化，唔係改善**；判決器冇俾 WIN，係 Kelvin 揀咗「同樣結果下用簡單啲嘅模型」。
- 連帶：`data_contract` 唔再閘 `trackwork_trend_score`（恆定 60 會被當死欄位攔發佈），HKJC 基準重新 calibrate；
  模型說明生成器標明「已退出排名」。
- 晨操維度權重（~1%）冇刪：恆定 60 對所有馬一樣，排名唔受影響；改權重要另做 refit。
- 重新入分嘅條件：forward `trackwork_rescreen`（60 個賽日）或者抽到新資料（試閘名次／頭馬距離、更長歷史）之後過 Stage 4 v3。
