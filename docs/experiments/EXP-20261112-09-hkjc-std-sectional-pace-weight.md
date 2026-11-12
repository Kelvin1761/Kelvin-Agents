# EXP-20261112-09 HKJC 步速修正偏差改為「逐段對馬會標準」＋近 6 仗＋負磅換算

- **日期**：2026-11-12 ｜ **平台**：HKJC
- **觸發**：Kelvin：「步速修正完成時間偏差唔係應該同標準時間比咩？唔應該等於輸頭馬幾多秒」「應該係每一段段速對馬會該路程同場地嘅標準去修正」
  「唔好唔記得負磅，想一齊修好」
- **假設**：按呢個定義重做嘅數值（取代，或者加入）排名會改善；步速修正同負磅換算各自有邊際貢獻
- **搜索過嘅舊記錄**：EXP-20261112-06／-07／-08；EXP-20261016-14／-16
- **改到嘅檔案／組件**：冇 live 改動；`hkjc_std_pace_table.py`、`hkjc_arm_std_pace_level.py`、`hkjc_arm_std_pace_added.py`

## 定義（跑之前寫喺 `hkjc_std_pace_table.py` docstring）
- 標準：馬會標準分段（`hkjc_standard_times.json` reference_sectionals），一律用**今仗班次**做共同標準
- dev = Σ(匹馬自己分段 − 標準分段)；賽績檔分段確認係匹馬自己嘅（分段之和 = 賽果庫完成時間 94／94）
- 步速修正：adj = dev − (1 − ρ) × 早段偏差；ρ = 0.382（早段每慢 1 秒、末段追返 0.38 秒；馬匹 FE，只用 2026-05-03 之前 5,541 仗；
  分路程 0.41／0.32／0.38，登記用單一值）
- 負磅換算：+ 0.01123 × 路程(km) ×（今仗 − 當時實際負磅）
- 近 6 仗權重 1/k，最少 2 仗；覆蓋 4,764／5,207 匹（91.5%）
- P0 = dev、P1 = adj、P2 = adj＋負磅（主）；四級門檻 = dev 半現行比例嘅分位數，唔睇賽果
- 取代版：新數值取代現行等級；加入版：保留現行等級，另加一項，加減分減半（+4／+0.5／−2／−4）

## 結果（全語料 389 場／holdout 186 場）
| arm | Gold（全） | Good（全） | Gold（holdout） | Good（holdout） | 頭三換入／換出上名 | 判決 |
|---|---|---|---|---|---|---|
| 取代 P0 | −1.54 [−3.37, +0.26] | −0.51 | −1.08 | −1.08 | 21／81 vs 31／82 | REJECT |
| 取代 P1 | −1.03 [−2.57, +0.26] | −0.77 | −0.54 | −1.08 | 23／82 vs 29／82 | REJECT |
| 取代 P2 | −0.77 [−2.33, +0.75] | −0.51 | −0.54 | −1.61 | 23／79 vs 28／79 | REJECT |
| 加入 P1 | 0.00 [−0.76, +0.77] | −0.51 [−2.01, +0.79] | 0.00 | 0.00 | 16／52 vs 22／52 | REJECT |
| 加入 P2 | 0.00 [−0.76, +0.77] | −0.26 [−1.80, +1.29] | 0.00 | −0.54 | 17／50 vs 21／50 | REJECT |

## 檢查
- **leakage-audit**：FLAG（輕微）—— 標準分段表係 2026-08-25 版，包含評估窗頭三個月嘅賽事；ρ 同 β 只用評估窗之前；冇用賠率、冇用賽果定門檻
- **wiring**：取代版 ~2,200 匹段速分有郁；**golden_scoring**：冇郁；**退步**：live 冇改

## 結論
1. 現行嗰項名不副實（係輸頭馬幾多秒），但作為預測項，佢好過今日試過嘅五個以時間計嘅替代品（表現數字 U／W、P0／P1／P2）。
2. 取代版每加一步 Gold 都好啲（−1.54 → −1.03 → −0.77）—— 步速修正同負磅換算方向都啱，但追唔返換走現行項嘅損失。
3. 加入版 Gold 0、Good −0.26 至 −0.51（全跨零）—— 判唔到，冇改善。
4. 今日同一批 389 場已經試咗 19 個 arm；再試落去揀到嘅好結果好大機會係運氣。乾淨證據要靠 forward。

**決定**：REJECT（全部）；命名修正同顯示／forward shadow 未做
**commit**：未 commit 任何 model code

## 重跑
```bash
P=docs/experiments/patches; H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_std_pace_table.py base.jsonl stdtable.json
WC_EXP_STD_TABLE=stdtable.json WC_EXP_STD_MODE=P2 PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_std_pace_level.py --out P2.jsonl
WC_EXP_STD_TABLE=stdtable.json WC_EXP_STD_MODE=P2 PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_std_pace_added.py --out addP2.jsonl
python3 $H compare base.jsonl P2.jsonl --stage4 fixed_rule --leakage-audit-passed
```
