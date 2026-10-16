# EXP-20261016-15 — HKJC 前置習慣（近仗第一沿途位）預先登記

- **登記日期**：2026-10-16，喺跑任何 arm **之前** commit
- **平台**：HKJC；**Stage 4 v3 `fixed_rule`**（固定值，冇 fit）
- **觸發**：EXP-20261016-14 §5 —— 同一模型排名 4–6，前置馬上名 33.9% vs 後上 20.9%；
  EXP-20261010-02 首段位置係增量訊號第一位。

## Kelvin 嘅決定（2026-10-16）

**D12 門檻（預測早段位置 ρ ≥ 0.6，EXP-20261010-12）唔適用於呢個訊號。** D12 管「預測今仗會跑咩位置」；
呢個訊號只描述**過往已經發生嘅行為**（習慣），唔聲稱預測今仗位置，報告亦唔會寫「預計前置」。

## 假設

模型低估過往慣性前置嘅馬、高估慣性後上嘅馬。將前置習慣加入 段速表現（現時六個微訊號全部係末段／完成時間）
會改善排名。

## 候選（固定值，唔准改）

- **輸入**：`_data.position_window`，取最近 3 仗有效嘅「第一沿途位」（`沿途位=N-...` 第一個數）。
- **少過 2 仗** → 唔加減（初出、資料不足）。
- **s** = 第一沿途位 ≤ 3 嘅比例（0、1/3、1/2、2/3、1）。
- **delta = K × (s − 1/3)**，加落 `speed_score`，clip 0–100。即「3 仗有 1 仗跑頭 3」= 中性。
- **家族**：K ∈ {3, 6, 9}，三個 arm。Holm 調整（3 arm × 指標）。
- **實作**：`docs/experiments/patches/hkjc_arm_early_habit.py`，`WC_EARLY_HABIT_K=3|6|9`。
  patch `engine_core.SpeedScorer`（top-level `speed` module；patch package 路徑會冇接通）。
  接線證明：`races_with_ranking_change > 0`。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --until 2026-10-10 --out base.jsonl
for K in 3 6 9; do WC_EARLY_HABIT_K=$K python3 $H run --until 2026-10-10 \
  --arm docs/experiments/patches/hkjc_arm_early_habit.py --out k$K.jsonl; done
for K in 3 6 9; do python3 $H compare base.jsonl k$K.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```

- **全紀錄窗口**：語料開始 → **2026-10-10**（2026-10-11 起留畀 forward）。
- 判決：`model_evaluation_decision.evaluate_full_record`，照 v3 次序；p 值 Holm 調整後先報 WIN。
- **分層（只報，唔用嚟救）**：沙田／跑馬地、馬匹數 ≤10 / 11–12 / 13–14、路程 ≤1200 / 1400–1650 / 1800+。
  任何一個場地嘅 Gold 或 Good 點估計 < 0 → 記 ⚠️，forward 時一齊睇。

## §6 功效前置（量度前計）

閘門 MDE（EXP-20261016-14 `no_l400_abs` 嘅 CI 半寬，同語料）：
Gold ±1.96pp、Good ±1.76pp、top3_capture@5 ±1.51pp、NDCG@5 ±0.0101、competitive_recall@5 ±0.0101、
mean_top3_rank ±0.049。新加訊號冇「部件預算」可以預先量；如果三個 arm 嘅 |Δ| 全部細過 MDE，
判 `UNRESOLVABLE` 而唔係 `REJECT`。

## Leakage audit（已做，PASS）

- 賽前可得：`position_window` 由賽績頁過往賽事建，賽前已公開。
- 實測 3,615 匹有窗口嘅 runner：**0** 個窗口包含即日或者之後嘅賽事（第 N 仗日期全部 < 賽日）。
- 冇用賠率、冇用今仗沿途位、冇用賽果。

## 已知偏差（照實寫）

EXP-20261016-14 嘅診斷**已經睇過**同一份語料（包括方向同大約幅度）。所以全紀錄結果只算**篩選**；
就算 WIN 都唔可以直接上線，要過 forward。

## Forward 確認（只開一次）

- **窗口**：2026-10-17 起嘅 HKJC 賽日（今次登記之後、未睇過），累積 ≥ 60 場先開。
- **K 點揀**：全紀錄有 WIN 嘅 arm 入面揀 K 中位數（唔准 argmax）；只有一個 WIN 就用嗰個；冇 WIN → 唔開 forward，記 REJECT。
- **判決（寫死）**：Gold Δ ≥ 0、Good Δ ≥ 0、NDCG@5 Δ ≥ 0 → 可以提交上線；任何一項 < 0 → REJECT。
  唔准換指標、換窗口或重開。

## 結果

見 `EXP-20261016-15-hkjc-early-habit-results.md`：**REJECT**，三個 K 都冇 WIN，冇開 forward。
