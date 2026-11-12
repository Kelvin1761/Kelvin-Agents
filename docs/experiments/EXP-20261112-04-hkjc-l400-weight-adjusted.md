# EXP-20261112-04 HKJC 段速按今仗負磅調整上仗 L400

- **日期**：2026-11-12
- **平台**：HKJC
- **觸發**：Kelvin：「輕磅做出嚟嘅段速同頂磅應該有分別？應該用今場磅數做標準調整之前嘅段速？」
- **假設**：上仗 L400 按（今仗負磅 − 上仗負磅）調整之後再過引擎門檻，排名會改善
- **搜索過嘅舊記錄**：EXP-20261112-01（`l400_w` 直線特徵跨零，但用嘅係最快 L400 嗰仗、冇真正調整 L400）；
  EXP-20261016-14（L400 絕對值有貢獻）；EXP-20261105-03／20261111-11（L400 按場地路程標準化）
- **改到嘅檔案／組件**：冇 live 改動；arm monkeypatch `SpeedScorer._data`

## 配置
- **baseline**：origin/main `4e6dae6a`
- **arm**（跑之前寫死）：調整後 L400 = 上仗 L400 + C ×（今仗實際負磅 − 上仗實際負磅），C ∈ {0.02, 0.04} 秒／磅；
  上仗 L400 要同 Logic `raw_l400` 相差 ≤0.02s 先調；其餘段速訊號唔郁；`fixed_rule`

## 一、負磅對 L400 嘅實際影響（量度）
同一匹馬唔同仗比較（馬匹 fixed effect ＋ 場地×路程×場地狀況 fixed effect），9,811 仗／1,063 匹，CI 用馬匹 cluster bootstrap：

| 設計 | 每加 1 磅 L400 慢 | 95% CI | 10 磅 |
|---|---|---|---|
| 基本 | +0.0099s | [+0.0075, +0.0124] | +0.10s |
| 再控制早段步速 | **+0.0127s** | [+0.0103, +0.0151] | +0.13s |
| 　≤1200m | +0.0074s | [+0.0037, +0.0112] | |
| 　1400–1650m | +0.0159s | [+0.0118, +0.0199] | |
| 　≥1800m | +0.0211s | [+0.0118, +0.0319] | |

**物理效應係真，方向同 Kelvin 講嘅一樣，路程越長越大。** 但幅度細：引擎門檻一格 0.6s、L400 同條件內 SD 0.80s；
今仗同上仗差 ≥10 磅嘅馬只有 12%。

## 二、預測力（354 讓磅場／4,258 匹）
- 模型之上，再加「今仗 − 上仗負磅」：每磅 −0.0025 [−0.0140, +0.0098]（方向啱，但等於零）
- 調整後加減分 − 原本，模型之上嘅係數：C=0.02 +0.029 [−0.042, +0.104]；C=0.04 +0.027 [−0.024, +0.077]；
  反方向對照 C=−0.04 −0.025 [−0.079, +0.036] —— 符號一致，全部跨零
- 上仗 L400 ≤23.0 嘅馬：今仗重 3–9 磅 **+5.31pp**、重 ≥10 磅 **+4.75pp**（相對模型預期），輕咗 ≥3 磅 −0.52pp ——
  加磅嘅快馬反而跑好過預期。香港加磅唔係外加負擔，係贏咗馬被加分；「加磅」本身帶住「狀態好」嘅資訊，抵銷咗物理效應

## 三、A/B（389 場）
| 指標 | C=0.02 | C=0.04 |
|---|---|---|
| 段速分升／跌（匹） | 287／312 | 546／540 |
| 排名有變場次 | 102 | 162 |
| Gold | 0.00 [−0.77, +0.76] | −0.26 [−1.06, +0.52] |
| Good 位置 | +0.26 [−0.53, +1.26] | −0.26 [−1.36, +0.78] |
| top3 capture@5 | +0.09 | +0.09 |
| NDCG@5 | +0.002 [−0.002, +0.005] | +0.002 [−0.002, +0.005] |
| 頭三換入／換出上名 | 6／18 vs 5／18 | 8／31 vs 11／31 |
| **判決** | **REJECT / ranking_evidence_too_weak** | **REJECT / primary_regression** |

> **更正（EXP-20261112-06）**：上面「加磅＝近況好，抵銷物理效應」嘅解讀唔成立 —— 控制評分後負磅係數不變，加磅之後表現數字係跌。
> 「加磅快馬 +5pp」只係相對現行模型預期嘅殘差。

## 檢查
- **leakage-audit**：PASS —— 負磅同 L400 全部來自賽前賽績檔，歷史仗用賽日過濾
- **wiring**：兩個 arm 段速分都有幾百匹郁；**golden_scoring**：冇郁；**退步**：live 冇改

## 結論
1. 負磅真係會拖慢 L400（每磅約 0.013s），Kelvin 嘅前提啱。
2. 但按呢個調整，排名冇可量度嘅改善：C=0.02（最接近實測值）102 場郁、全部指標打和，冇一項負；C=0.04 微負。
3. 原因有兩個：(a) 效應細過門檻一格好多，只有約 12% 馬有 ≥10 磅差；(b) 加磅同「近況好」綁埋一齊，方向相反。
4. C=0.02 唔係「有害」，係「判唔到」。如果當正確性修正（§7）上線，係 Kelvin 嘅決定；要改管線（Logic 帶上仗負磅）。
   未試：C 按路程變（實測 0.007／0.016／0.021）——屬於事後擬合，要先登記先可以跑。

**決定**：REJECT（按 `fixed_rule`）；物理量度保留做參考
**commit**：未 commit 任何 model code

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_l400_weight_screen.py base.jsonl
WC_EXP_L400_C=0.02 PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_l400_weight_adjusted.py --out c02.jsonl
WC_EXP_L400_C=0.04 PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_l400_weight_adjusted.py --out c04.jsonl
python3 $H compare base.jsonl c02.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare base.jsonl c04.jsonl --stage4 fixed_rule --leakage-audit-passed
```
