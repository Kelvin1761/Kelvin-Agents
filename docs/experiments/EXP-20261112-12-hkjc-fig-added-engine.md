# EXP-20261112-12 HKJC 真引擎「兩樣都放」：保留輸頭馬等級，另加表現數字＋負磅換算等級

- **日期**：2026-11-12 ｜ **平台**：HKJC ｜ **觸發**：Kelvin「試兩樣都放」
- **假設**：EXP-11 簡化模型入面「兩樣都放」嘅改善（capture@5 +0.39 [+0.02,+0.74]、Good 7/7 季 ≥0）喺真引擎重現
- **搜索過嘅舊記錄**：EXP-20261112-08／-09（加入版用 P2，Gold 0／Good −0.26～−0.51）／-10／-11
- **改到嘅檔案／組件**：冇 live 改動；`hkjc_arm_fig_added.py`、`hkjc_added_leaf_null.py`

## 配置（跑之前寫喺 arm docstring）
baseline origin/main `4e6dae6a`；W = EXP-08 PIT 表現數字（β 0.01123，2026-05-03 之前估）；門檻 = dev 半現行四級比例嘅 W 分位數
（+0.585／+0.120／−0.183 s/km）；加減分現行一半 +3.26／+0.71／−2／−4；喺段速分最後加，唔計訊號數目；`fixed_rule`

## 結果
| 語料 | 郁咗場次 | Gold | Good 位置 | capture@5 | NDCG@5 | 判決 |
|---|---|---|---|---|---|---|
| 全 389 場 | 220 | −0.51 [−1.30, 0.00] | **−1.03 [−2.04, −0.25]** | 0.00 | −0.00 | REJECT / primary_regression |
| holdout 186 場 | 101 | 0.00 | −0.54 [−1.64, 0.00] | −0.36 | −0.00 | REJECT / primary_regression |

段速分升 3,029／跌 1,703 匹；模型頭三換入 39 匹 14 匹上名，換出 39 匹 15 匹上名。分層：沙田草地 Gold −0.89／Good −1.78，其餘 0。

隨機對照（同比例、同加減分、等級亂抽，200 次，離線 449 場）：候選 Gold 0.00／Good −0.45／NDCG −0.0024；
null 均值 −0.72／−0.85／−0.0011；候選百分位 Gold 87%、Good 69%、capture@5 27%、NDCG 33% —— **唔好過隨便加一項**。

## 檢查
- **leakage-audit**：PASS（同 EXP-08）；**wiring**：4,732 匹段速分有郁；**golden_scoring**：冇郁；**退步**：live 冇改

## 結論
簡化模型（6 個基礎特徵）入面「兩樣都放」有改善，喺真引擎冇重現，Good 仲顯著跌。差別喺真引擎已經有近績、穩定性、賽績線、
L400、評分等十幾個 leaf，同表現數字重疊；簡化模型冇呢啲，所以新項顯得有用。
今日 EXP-01 至 -12 合共：負磅效應真（每磅 ~0.01 s/km，抵銷 ~70% 評分優勢），表現數字＋負磅換算做單一 leaf 最準，
但喺真引擎入面取代、混合、加入全部過唔到閘。唯一冇主要指標跌嘅仲係 EXP-05（L400 按路程負磅換算）。

**決定**：REJECT ｜ **commit**：未 commit 任何 model code

## 重跑
```bash
P=docs/experiments/patches; H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
WC_EXP_FIG_TABLE=figtable.json WC_EXP_FIG_CUTS=figcuts.json PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_fig_added.py --out figadd.jsonl
python3 $H compare base.jsonl figadd.jsonl --stage4 fixed_rule --leakage-audit-passed
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_added_leaf_null.py base.jsonl stdP2.jsonl figtable.json figcuts.json
```
（`figcuts.json` = dev 半門檻：`{"cuts_W": [0.585, 0.1199, -0.1828]}`）
