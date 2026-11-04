# EXP-20261105-03：HKJC 近績分直線名次＋剷穩定性分、L400 按場地路程標準化，預先登記

- **登記日期**：2026-11-05，喺跑任何 arm 之前 commit 同 push
- **平台**：HKJC；Stage 4 v3 `fixed_rule`，加 §8 兩邊 refit（`walk_forward_oos`）
- **觸發**：Kelvin 問：（1）段速表現要唔要好似 AU 咁做加權；（2）近績分同穩定性分要唔要合併；
  （3）AU 嘅狀態與穩定性（名次 + 獎金）可唔可以參考，但香港班次穩定，獎金未必啱用。
- **前置**：冇。現行計法見 `features/form.py`、`engine_core._consistency_score`、`features/speed.py`。

## 篩選證據（只係篩選，唔係判決）

全部 point-in-time：目標賽事只用嗰日之前嘅往績，目標窗 **< 2026-10-11**（forward holdout 冇用過）。
指標係場內上名（頭 3）AUC，賽日 bootstrap 1,000 次。

### 狀態與穩定性（賽果庫，2025-01-01 → 2026-10-07，1,487 場、16,574 匹、152 賽日，最少 2 仗往績）

| 讀法 | AUC | Δ 對現行穩定性 [95% CI] | 場內 ρ（對現行） |
|---|---:|---|---:|
| 現行穩定性（近績 5/9 ＋ 穩定性 4/9） | 0.6672 | — | 1.000 |
| 淨用現行近績分 | 0.6694 | +0.0022 [−0.0015, +0.0058] | 0.908 |
| 淨用現行穩定性分 | 0.6448 | **−0.0224 [−0.0268, −0.0183]** | 0.905 |
| 直線名次（唔理出馬數），1/(i+1) | 0.6793 | **+0.0122 [+0.0064, +0.0176]** | — |
| 直線名次，12 名封頂，1/(i+1) | 0.6794 | **+0.0123 [+0.0067, +0.0179]** | — |
| 名次百分位（AU z_place），1/(i+1) | 0.6842 | +0.0171 [+0.0117, +0.0224] | 0.865 |
| 名次百分位，AU 權重 1.0／0.8／… | 0.6830 | +0.0158 [+0.0107, +0.0206] | 0.880 |
| 名次百分位 ＋ 往績班次（AU 獎金對應） | 0.6724 | +0.0052 [−0.0020, +0.0123] | 0.768 |
| 名次百分位 ＋ 落後頭馬秒數 | 0.6813 | +0.0142 [+0.0086, +0.0191] | 0.852 |
| 往績班次單獨 | 0.4599 | −0.2072 | −0.352 |

讀法：
- **穩定性分冇額外資訊**：同近績分讀同一串名次（ρ 0.9），單獨仲差 0.022。合併冇代價。
- **改善嚟自「名次用連續數」**：現行 6–14 名全部 40 分。唔理出馬數已經有 +0.012（Kelvin：香港出馬數穩定）。
  百分位再多 0.005，主要喺少數細場；第一版唔加，live 唔使新增資料來源。
- **班次唔啱用**：香港贏先升班、輸先跌班，所以「上仗跑高班」通常係近況差（AUC 0.46）。加入去反而拉低。

### 段速 L400（Facts「完整賽績檔案」近 6 仗，36 賽日、359 場、4,283 匹）

| 讀法 | AUC | Δ 對上仗絕對值 [95% CI] |
|---|---:|---|
| 上仗 L400 絕對值（現行輸入） | 0.5787 | — |
| **上仗 L400 按（場地, 路程）標準化** | **0.5896** | **+0.0108 [+0.0032, +0.0187]** |
| 近 6 仗加權平均，絕對值 | 0.5768 | −0.0019 [−0.0140, +0.0115] |
| 近 6 仗加權平均，標準化 | 0.5907 | +0.0120 [−0.0019, +0.0272] |
| 近 3 仗加權平均，標準化 | 0.5881 | +0.0094 [−0.0026, +0.0229] |
| 近 6 仗最快，標準化 | 0.5770 | −0.0017 [−0.0240, +0.0197] |

讀法：**加權平均冇幫到；有用嘅係標準化**（上仗喺跑馬地 1650 同沙田 1000 平均差 1.43 秒，大過門檻兩級之間嘅 0.6 秒）。
同 EXP-20261020-01（+0.0064，CI 跨零）同方向。

重現：`docs/experiments/patches/hkjc_stability_form_screen.py <rows.pkl>`、
`docs/experiments/patches/hkjc_l400_recency_standardised_screen.py <HK_Racing 資料根> <rows.pkl>`；
`rows.pkl` 由 `hkjc_dump_results_rows.py` 產生（賽果庫 23,038 行，2024-09-08 → 2026-11-01）。

## 候選（固定，唔准改）

### A1：狀態與穩定性 = 單一 leaf「直線名次近績」

- 每仗名次分 `s = 100 − (min(名次, 12) − 1) × 60 / 11`（1 名 100，12 名或以後 40）。
- 近 6 仗加權 `F1 = Σ s_i / (i+1) ÷ Σ 1/(i+1)`，最近一仗 i = 0（同現行近績分一樣嘅權重）。
- 海外往績：同現行一樣併入（同一條名次分）。非數字名次照現行跳過。
- 尺度（凍結，只用 2025-01-01 → 2026-03-31 共 12,902 匹嘅**分佈**計，冇用賽果）：
  `leaf = clip(−9.3736 + 0.944123 × F1, 0, 100)`，令 leaf 喺嗰段嘅平均／SD 等於現行穩定性（56.24／13.08）。
- 維度 = 100% 呢個 leaf；`consistency_score` 唔再入分。`trackwork` 嘅 10% 拆分 shim 保持
  （`LEGACY_STABILITY_SPLIT.legacy_leaves` 改為 form 0.9、trackwork 0.1）。
- **初出馬唔郁**：維持現行穩定性計法（佢哋冇名次），否則初出馬會有常數位移，改變佢哋同其他馬嘅相對位置。
- 冇往績嘅非初出馬：同現行一樣 60。
- 權重：維度權重 0.08847 唔變。

### A2：淨剷穩定性分（近績分照現行）

- 狀態與穩定性 = 100% 現行 `form_score`；初出馬同 A1 一樣唔郁。
- 用嚟答「合併」本身有冇代價，同 A1 分開「改讀法」同「剷穩定性分」嘅貢獻。

### B1：L400 門檻改為對（場地, 路程）標準化

- `raw_l400` 換成 `L400 − cell平均 + 全體平均`，再套返**現行** SpeedScorer 門檻同權重（22.4／23.0／23.6／24.0／24.6）。
- cell = 上仗嘅（場地／跑道：沙田草地、沙田全天候、跑馬地，路程）。上仗由 `recent_6_detail` 第 1 仗日期 join 賽果庫攞。
- cell 平均同全體平均：只用**目標賽日之前**嘅賽日 Logic 入面嘅 `raw_l400`（每匹馬每仗去重），
  cell 要 ≥30 個觀測；唔夠，或者搵唔到上仗 cell → 用返絕對值（即係唔郁）。
- 唔郁 L400 趨勢、能量、其他段速訊號（L400 趨勢 87% 窗口混場地，留待另一個實驗）。

### A1+B1

- 兩個一齊。只有 A1、B1 各自都有結果先解讀；合併版只答「兩樣疊唔疊加」。

### 唔做（篩選已經答咗）

段速近 6 仗加權平均、近 6 仗最快、加班次／獎金、加落後秒數、名次百分位（要出馬數）。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
W=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_weight_study.py
P=docs/experiments/patches
python3 $H run --until 2026-10-10 --dump-matrix --out base.jsonl
python3 $H run --until 2026-10-10 --dump-matrix --arm $P/hkjc_arm_form_linear.py --out a1.jsonl
python3 $H run --until 2026-10-10 --dump-matrix --arm $P/hkjc_arm_form_only.py --out a2.jsonl
python3 $H run --until 2026-10-10 --dump-matrix --arm $P/hkjc_arm_l400_standardised.py --out b1.jsonl
WC_ARMS=form_linear,l400_standardised python3 $H run --until 2026-10-10 --dump-matrix --arm $P/hkjc_arm_combo.py --out a1b1.jsonl
for f in a1 a2 b1 a1b1; do python3 $H compare base.jsonl $f.jsonl --stage4 fixed_rule --leakage-audit-passed; done
# §8 兩邊 refit（A1、B1、A1+B1 改變 leaf 資訊量）
for f in base a1 b1 a1b1; do python3 $W $f.jsonl --arm wf_refit --out ${f}_wf.jsonl; done
for f in a1 b1 a1b1; do python3 $H compare base_wf.jsonl ${f}_wf.jsonl --stage4 walk_forward_oos --leakage-audit-passed; done
```

- **全紀錄窗口**：語料開始 → **2026-10-10**；用登記 commit 嘅 main。
- **接線證明**：每個 arm 報 `races_with_ranking_change`。0 = 冇接通，唔准當結果；A2 要喺有往績嘅馬上面先郁。
- **判決**：`evaluate_full_record`，跟 v3 次序；fixed 4 個 arm ＋ refit 3 個 arm 同一家族做 Holm，調整後先可以報 WIN。
- **上線規則**：fixed arm WIN → 用現行權重上線；否則 refit arm WIN 而 live guard 唔係 `primary_regression`／
  `ranking_metric_harm` → 連 refit 權重上線；其他一律 REJECT。上唔上線由 Kelvin 決定。
- **分層（只報，唔可以用嚟救）**：沙田／跑馬地、路程段、首選 SP 五段、往績仗數（2／3–5／6）。
  任何場地 Gold 或 Good 點估計 < 0 → ⚠️。

## §6 功效前置（量度之前寫低）

閘門 MDE 沿用 EXP-20261016-14 同語料嘅 CI 半寬：Gold ±1.96pp、Good ±1.76pp、top3_capture@5 ±1.51pp、
NDCG@5 ±0.0101、competitive_recall@5 ±0.0101、平均名次 ±0.049。

**預期**：狀態與穩定性只佔 8.8%，A1 leaf 改善 +0.012 AUC，傳到排名好可能細過 MDE。
所有 arm |Δ| < MDE → `UNRESOLVABLE`（判唔到），**唔等於冇用**，亦唔准換指標或者窗口去救。

## Leakage audit（PASS，附條件）

- A1／A2：只用 `last_6_finishes`（賽前欄位，對賽果庫 99.8% 一致，EXP-20261018-07）。尺度常數只用分佈，冇用賽果。
- B1：`raw_l400` 係上仗（過去）嘅官方段速；cell 平均只用**目標賽日之前**嘅賽日 Logic（唔讀同日或者之後嘅檔，
  即使入面係過去嘅值都唔讀），上仗 cell 由賽果庫過往行攞。
- 冇用賠率、今仗走位或者今仗賽果。
- 條件：A1 尺度常數同篩選用同一個賽果庫（2026-04 之前一段），只影響尺度，唔影響排序。

## 已知偏差

篩選**已經睇過** 2026-10-11 之前嘅賽果，A1 嘅「12 名封頂」同 B1 嘅「標準化而唔加權」都係睇咗篩選表先定。
所以全紀錄結果只算篩選級證據，WIN 一定要過 forward 先可以上線。

## Forward 確認（只開一次）

- **窗口**：2026-10-11 起嘅 HKJC 賽日（呢個家族嘅篩選同常數都冇用過），累積 ≥ 60 場先開。
- 只有全紀錄 Holm 後有 WIN 嘅 arm 先開；同一 arm 只開一次。
- **判決（寫死）**：Gold Δ ≥ 0、Good Δ ≥ 0、NDCG@5 Δ ≥ 0 → 可以提交上線；任何一項 < 0 → REJECT。
- 開 forward 嗰個改動要同時加入 `hkjc_daily_auto/hkjc_forward_tracker.py` 嘅 `FORWARD_TESTS`（夠數即 Telegram）。
- 上線之前：A1 喺 `FormScorer` 實作，唔可以靠 arm 注入；B1 要有 live 嘅 PIT cell 平均表（由賽果庫＋過往 Logic 生成），
  寫入 Logic `_data` 供覆核。

## 更正（2026-11-05，跑任何全紀錄 arm 之前加，候選冇改）

**篩選嘅比較基準錯咗。** 上面「狀態與穩定性」表嘅「現行穩定性」係我由賽果庫用簡單式重砌
（58 ＋ 前三 ×7 − 八名後 ×5）。但 live 嘅 `consistency_score` 喺 `_apply_mainline_context`
會俾 `_consistency_shadow_detail`（逐仗連輸距覆核：跑近前列仗數、明顯敗陣仗數、近三仗走勢）覆蓋。
用存檔 Logic 入面**真正** live 分數重量（2026-04 → 2026-10-10，342 場、3,919 匹，非初出、≥2 仗）：

| 讀法 | AUC | Δ 對 live 穩定性 [95% CI] | 場內 ρ |
|---|---:|---|---:|
| live 穩定性 | 0.6689 | — | 1.000 |
| live 近績分單獨 | 0.6674 | −0.0015 [−0.0081, +0.0050] | 0.919 |
| live 穩定性分單獨 | 0.6531 | −0.0159 [−0.0254, −0.0070] | 0.890 |
| 直線名次（A1 leaf） | 0.6679 | −0.0011 [−0.0091, +0.0072] | 0.897 |

所以：
- A1 嘅 +0.012 係對住一個弱過 live 嘅重砌版；**對 live 係打和**。登記預期由「細改善」改為「冇預期改善」。
- 「穩定性分單獨差過近績分」仍然成立；但輸距覆核令佢合埋近績分有少少用（−0.0015，CI 跨零），A2 答呢點。
- B1 唔受影響：篩選比較嘅就係 live 輸入 `raw_l400`。
- 重現：`docs/experiments/patches/hkjc_live_stability_screen.py <HK_Racing 資料根> <rows.pkl> <repo>`。

**接線修正（smoke，2026-09-28 → 10-01，11 場）**：第一版 A1／A2 喺 harness 0 場郁 ——
A2 只 patch 咗 `_consistency_score`（之後俾輸距覆核蓋返）；A1 patch 咗
`hkjc_racing_engine.features.form.FormScorer`，但引擎用 `from form import FormScorer`，係另一個 class。
修好之後：A1 9/11 場、A2 10/11 場、B1 8/11 場排序郁；初出馬 8 匹穩定性完全唔變。

## 結果

（未跑）
