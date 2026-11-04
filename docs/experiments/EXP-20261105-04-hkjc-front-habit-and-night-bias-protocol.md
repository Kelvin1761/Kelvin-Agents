# EXP-20261105-04：HKJC 前置習慣入分，加當晚偏差開關（預先登記）

- **登記日期**：2026-11-05，喺跑任何全紀錄 arm 之前 commit 同 push
- **平台**：HKJC；A 係 Stage 4 v3 `fixed_rule`（K 家族）＋ §8 refit；C 係 **forward only**（靠 EXP-20261104-11 即場資料）
- **觸發**：Kelvin 問「預計步速準唔準，可唔可以將跑法同步速加入 scoring」，同埋「好似今日偏外檔守中嘅情況點算」。

## 篩選證據（只係篩選，唔係判決；全部 < 2026-10-11）

### 1. 全場步速預測唔準 → 步速唔入分

賽前「習慣放頭馬數目」（近 3 仗第一沿途位平均 ≤ 2.5）對實際步速（短評 7 級，1,143 場）：
Spearman **+0.125**（沙田 +0.167、跑馬地 +0.044）。冇放頭馬嘅場次，實際偏快都有 35.8%；≥2 匹嘅場次偏快 47.7%。
同 EXP-20261010-12（今仗位置預測 ρ 0.49，未過 D12 門檻 0.6）一致：**比賽當刻嘅步速賽前預測唔到，唔入分。**
事後步速 × 實際跑法嘅上名率差好大（慢步速前置 39.1%／後上 12.9%；快步速 29.8%／18.6%），但嗰個要賽後先知。

### 2. 模型低估習慣前置馬（cohort，對同一模型排名區間）

349 場、35 賽日（2026-04 → 10-10），模型分取存檔 Logic `ability_score_raw`（冇就 `ability_score`）：

| 模型排名 | 習慣前置 | 習慣中置 | 習慣後上 |
|---|---:|---:|---:|
| 1–3 | 46.9% | 42.2% | 38.8% |
| 4–6 | 36.0% | 29.0% | 21.0% |
| 7+ | 19.3% | 16.8% | 13.4% |

前置 − 後上 上名率超額 **+8.6pp [+4.1, +13.4]**（賽日 bootstrap）。單騎放頭（場內 ≤1 匹習慣放頭）再好啲，+7.0pp [−1.9, +15.0]，未顯著，**唔登記**。

### 3. 分層（只報）

| 分層 | 前置 − 後上 | 場數 |
|---|---|---:|
| 沙田 | +11.1 [+6.1, +16.0] | 225 |
| 跑馬地 | +4.3 [−4.1, +12.4] | 124 |
| A／B／C／C+3 賽道 | +8.7／**−3.0**／+6.4／+14.6 | 80／63／38／64 |
| ≤1200／1201–1650／≥1800 | +10.0／+7.3／−0.9 | 173／140／36 |

### 4. 當晚偏差持續性（研究用，用事後賽果，**唔可以入分**）

「當晚之前已跑場次實際前置（第一沿途位 ≤ 3）嘅上名率超額」分三份（280 場）：

| 當晚之前 | 今場 前置 − 後上 |
|---|---|
| 前置唔著數（最低三分一） | **+0.3pp [−6.0, +7.4]** |
| 中性 | +12.0pp [+2.4, +21.6] |
| 前置著數 | +11.0pp [+6.1, +15.7] |

即係 Kelvin 講嘅「偏外檔守中」晚上，前置優勢消失。呢個要喺 forward 用 `captured_at` 驗證先算數（EXP-20261104-11 嘅規矩）。

重現：`docs/experiments/patches/hkjc_pace_prediction_screen.py`、`docs/experiments/patches/hkjc_front_habit_strata_screen.py`
（輸入 `hkjc_dump_results_rows.py` 嘅 rows.pkl；第 2–4 節嘅模型排名讀存檔 Logic）。

## 候選（固定，唔准改）

### A_K：前置習慣 ±K，K ∈ {2, 4, 6}

- 習慣 `h` = 賽日**之前**最近 3 仗第一個沿途位平均（賽果庫 `RunningPos`，最少 2 仗）。
- 今仗出賽馬數 `N` = Logic 入面唔係「(退出)」嘅馬。
- `h / N ≤ 0.25` → `race_shape_context_score` **+K**；`h / N > 0.60` → **−K**；其他、往績少過 2 仗、初出 → 0。clip 0–100。
- 之後全場 race-shape 封頂（同場中位數 ±10）照舊，所以初出馬同其他馬嘅值可能跟住中位數輕微郁 —— 同 live 一致，唔另外處理。
- K 嘅理由：同 EXP-20261025-08 一樣用 {2, 4, 6}；檔位與走位權重 27.37%，K=4 ≈ 綜合分 ±1.1。
- 實作：`docs/experiments/patches/hkjc_arm_front_habit.py`，`WC_FRONT_K=2|4|6`。smoke（09-28 → 10-01，11 場）9 場排序郁。

### C：A_4 ＋ 當晚偏差開關（forward only）

- 當晚之前、而且 `captured_at` 早過今場開跑嘅場次：實際第一沿途位 ≤ 3 嘅馬，上名（頭 3）減「模型排名區間期望上名率」嘅平均。
  期望上名率凍結：模型排名 1–3 **0.4167**、4–6 **0.2627**、7+ **0.1507**（上面第 2 節語料）。
- 已觀察實際前置馬 ≥ 6 匹，而平均超額 **< 0.0691**（篩選嘅最低三分一界線）→ 今場 K = 0；其他 → K = 4。
- 未夠 6 匹（通常係頭兩三場）→ 照用 K = 4。
- 只可以用 `HKJC_Race_Results_Database/_live/<日期>.json` ＋ `state.json` 嘅 `captured_at`；冇 `captured_at` 嘅場次當未知。

### 唔做

全場步速預測入分（第 1 節）、單騎放頭額外加分（第 2 節，未顯著）、按場地／賽道開關（第 3 節係睇咗數先見到，唔准當規則）。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
W=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_weight_study.py
P=docs/experiments/patches
python3 $H run --until 2026-10-10 --dump-matrix --out base.jsonl
for K in 2 4 6; do WC_FRONT_K=$K python3 $H run --until 2026-10-10 --dump-matrix --arm $P/hkjc_arm_front_habit.py --out a$K.jsonl; done
for K in 2 4 6; do python3 $H compare base.jsonl a$K.jsonl --stage4 fixed_rule --leakage-audit-passed; done
python3 $W base.jsonl --arm wf_refit --out base_wf.jsonl
python3 $W a4.jsonl --arm wf_refit --out a4_wf.jsonl
python3 $H compare base_wf.jsonl a4_wf.jsonl --stage4 walk_forward_oos --leakage-audit-passed
```

- **全紀錄窗口**：語料開始 → **2026-10-10**；用登記 commit 嘅 main。
- **判決**：`evaluate_full_record`，v3 次序；A2／A4／A6 ＋ A4 refit 同一家族 Holm，調整後先可以報 WIN。
- **分層（只報，唔可以用嚟救）**：沙田／跑馬地、賽道 A／B／C／C+3、路程段、首選 SP 五段。任何場地 Gold 或 Good 點估計 < 0 → ⚠️。

## §6 功效前置

MDE 沿用 EXP-20261016-14：Gold ±1.96pp、Good ±1.76pp、top3_capture@5 ±1.51pp、NDCG@5 ±0.0101。
所有 arm |Δ| < MDE → `UNRESOLVABLE`，唔准換指標或者窗口。

## Leakage audit（PASS，附條件）

- 習慣只用賽日之前嘅 `RunningPos`（官方賽果，賽後即日公佈）。今仗沿途位、今仗步速、今仗賽果一律唔用。
- 今仗出賽馬數係賽前排位表資料。
- C 嘅當晚偏差只用 `captured_at` 早過開跑時間嘅場次；全紀錄回測**唔做 C**（用 `full_day_results.json` 回填 = 洩漏）。
- 篩選第 4 節用咗事後賽果做研究，所以 C 嘅門檻（0.0691）同期望上名率都係睇咗 2026-10-11 之前嘅數先定 → C 只可以喺 2026-11-04 起嘅 forward 判。

## 已知偏差

A 嘅方向同閾值（0.25／0.60）係睇咗篩選先定，全紀錄結果只算篩選級證據；WIN 一定要過 forward。

## Forward 確認（只開一次）

- **A**：全紀錄 Holm 後有 WIN 嘅 K 入面取中位數（唔准 argmax），用 2026-10-11 起嘅賽日，累積 ≥ 60 場判一次。
- **C**：用 EXP-20261104-11 收集嘅完整賽晚（`live_nights`），≥ 60 晚判一次；比較 C vs A_4 vs base。
  已加入 `hkjc_forward_tracker.py` 嘅 `FORWARD_TESTS`（`front_habit_night_gate`），夠數即 Telegram。
- **判決（寫死）**：Gold Δ ≥ 0、Good Δ ≥ 0、NDCG@5 Δ ≥ 0 → 可以提交上線；任何一項 < 0 → REJECT。
- 上線之前：習慣要喺 live 計（Facts「沿途位」或者賽果庫），寫入 Logic `_data` 供覆核；C 要喺排程入面讀 `_live` 資料。上唔上線由 Kelvin 決定。

## 結果

（未跑）
