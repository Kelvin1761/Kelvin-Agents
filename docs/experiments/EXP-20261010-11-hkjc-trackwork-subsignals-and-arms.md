# EXP-20261010-11 — 晨操子訊號篩選 + 兩個晨操規則 arm（全紀錄判決）

- **日期**：2026-10-10；平台：HKJC；baseline = main `f7d07b03`
- **Kelvin 要求**：晨操要更詳細；晨操升做獨立維度之後，佢內部嘅分數要唔要重建
- **語料**：harness 回放 286 場（剔走 04 月 `speed_score` 死日）；篩選用 9D dump、前 60% 日期 fit、後 40%（114 場）測

## 1. 子訊號篩選（喺模型之上有冇剩餘訊號）

`docs/experiments/patches/hkjc_screen_trackwork.py dump_9d.jsonl`，方法同 EXP-07／10（模型綜合分做 offset 嘅 conditional logit）。

| 子訊號 | 覆蓋 | OOS ΔLL | 95% CI | cohort 超額 |
|---|---:|---:|---|---:|
| 近 21 日快操課數 | 100% | −0.0016 | [−0.0082, +0.0054] | 快操 ≥ 4：+0.3pp |
| 近 21 日試閘次數 | 100% | **+0.0035** | [−0.0003, +0.0080] | 試閘 ≥ 1：+1.9pp（n 1,379） |
| 負荷（快操 + 2 × 試閘） | 100% | +0.0038 | [−0.0040, +0.0145] | — |
| 今仗騎師有策騎晨操 | 100% | −0.0033 | [−0.0091, +0.0023] | +0.1pp |
| 快操時間轉快／轉慢 | 100% | +0.0018 | [−0.0026, +0.0066] | 轉快 **−1.2pp**；轉慢 **+1.4pp** |
| 最快末段 200 米 | 86% | −0.0028 | [−0.0061, +0.0004] | — |
| 近 21 日完全冇快操／試閘 | 13 匹 | — | — | −27.8pp（n 太細） |

另：現行晨操 leaf（`trackwork_trend_score`）場內 AUC **0.4984** [0.4592, 0.5425] —— 同擲毫冇分別。

**讀法**：
- 冇一個子訊號 CI 唔跨零。試閘次數最接近，但仍然跨零。
- 快操時間趨勢喺模型之上**方向相反**：轉慢嘅馬跑得好過預期，轉快嘅差過預期。即係現行 leaf 用「加強 70／放緩 46.24」用得太重（或者方向錯）。

## 2. 兩個預先登記嘅 arm（固定規則，冇 fit，Stage 4 v3 `fixed_rule` 全紀錄）

| Arm | 改動 | 郁到場數 | Gold | Good | 判決 |
|---|---|---:|---|---|---|
| `hkjc_arm_trackwork_trend_neutral.py` | 加強／放緩 base → 60 | 116 | +0.35pp [−0.71, +1.43] | **−0.70pp** [−1.75, 0.00] | REJECT（primary_regression） |
| `hkjc_arm_trackwork_activity_off.py` | 活躍度加分 → 0 | 21 | 0.00 | +0.35pp [−0.71, +1.42] | REJECT（ranking_evidence_too_weak） |

重跑：
```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --out k_base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run \
  --arm docs/experiments/patches/hkjc_arm_trackwork_trend_neutral.py --out k_trend.jsonl
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare k_base.jsonl k_trend.jsonl \
  --stage4 fixed_rule --leakage-audit-passed
```

Leakage：兩個 arm 都只係將現有賽前常數設返中性，冇引入新資訊。

## 結論

- **維持現行晨操 leaf。** 趨勢中性化喺篩選睇落方向啱，但全紀錄 Good 跌 0.70pp（CI 上界 0）。篩選嘅剩餘訊號同真正排名改動對唔上：晨操得 0.98% 權重，改內部細節嘅效果細過噪音。
- **晨操重建（試閘時間、負荷）唔做。** 冇子訊號喺模型之上過得到 CI。試閘次數係唯一接近嘅，入重測清單。
- **重開條件**：
  - 有晨操嘅賽日 ≥ 60 個（而家 30 個），重跑篩選；試閘次數 CI 下界 > 0 先做 arm。
  - 或者試閘逐課**名次同段速**抽到（而家 `trial_sectionals` 大部分空，`trial_sectional_signal` 多數 `unknown`）。
- `LEGACY_STABILITY_SPLIT` shim 照留：佢只係用嚟保持 9D 拆分排名不變，冇重建就唔使剷。
