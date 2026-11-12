# EXP-20261112-08 HKJC 段速維度：「步速修正等級」輸入換做 PIT 表現數字

- **日期**：2026-11-12 ｜ **平台**：HKJC
- **假設**：用近 6 仗 PIT 表現數字（EXP-06）取代「輸頭馬幾多秒」定四級，排名會改善；按今仗負磅換算（W）好過唔換算（U）
- **搜索過嘅舊記錄**：EXP-20261112-06／-07
- **改到嘅檔案／組件**：冇 live 改動；`hkjc_fig_level_table.py`、`hkjc_arm_fig_level.py`

## 配置（跑之前寫死）
門檻 = dev 半（< 2026-09-06）現行四級比例（14.4／45.4／26.9／13.4%）喺 F 上嘅分位數，唔睇賽果；四級加減分唔郁；
冇表現數字嘅馬保留原本等級；`fixed_rule`，另報 holdout 半

## 結果
| arm | 語料 | Gold | Good | capture@5 | 判決 |
|---|---|---|---|---|---|
| U | 全 389 | −1.29 [−2.90, +0.26] | −0.26 [−2.02, +1.49] | +0.86 | REJECT |
| U | holdout 186 | −1.08 | −0.54 | +0.54 | REJECT |
| W | 全 389 | −1.54 [−3.31, 0.00] | +0.77 [−0.76, +2.34] | +0.51 | REJECT |
| W | holdout 186 | −1.08 | +0.54 | +0.72 | REJECT |

頭三換入／換出上名：U 23／78 vs 26／78；W 21／84 vs 29／84。

## 結論
W 嘅 Good 好過 U 約 1pp（負磅換算有幫助，同 EXP-06 一致），但兩個 Gold 都跌 1–1.5pp。取代現行輸入係蝕。
**決定**：REJECT ｜ **commit**：未 commit 任何 model code ｜ leakage-audit PASS（PIT 表現數字）

## 重跑
```bash
P=docs/experiments/patches; H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_fig_level_table.py base.jsonl figtable.json
WC_EXP_FIG_TABLE=figtable.json WC_EXP_FIG_MODE=W PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_fig_level.py --out figW.jsonl
python3 $H compare base.jsonl figW.jsonl --stage4 fixed_rule --leakage-audit-passed
```
