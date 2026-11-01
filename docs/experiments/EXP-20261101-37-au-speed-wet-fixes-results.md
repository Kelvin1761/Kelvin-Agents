# EXP-20261101-37 結果：GW（地況配對權重）、GWX（再關 wet overlay）—— 兩個都 REJECT，而且差過 G

- **預先登記**：[protocol](EXP-20261101-37-au-speed-wet-fixes-protocol.md)（`ae452d99`，量度之前）。
- **語料**：同 EXP-33；replica 0 匹差；重建嘅 G arm 同 EXP-33 G 逐匹一樣（0 匹差）。

## 判決（對 production）

| arm | v3 Gold | v3 Good | ranking | §8 | 分層 CI 全負 |
|---|---|---|---|---|---|
| G（參照，EXP-33） | −0.09pp | −0.52pp | top3@5 +0.0037 ✅ | both_arms_reject | 冇 |
| GW | −0.06pp [−0.82, +0.68] | −0.80pp [−1.66, +0.03] | 全部跨零 | both_arms_reject | 冇 |
| GWX | −0.31pp [−1.25, +0.56] | **−0.86pp [−1.71, −0.07]** | 全部跨零 | both_arms_reject | 9–12 匹 Good、≤8 匹 Gold、後備表高 Good |

Holm p 1.0；live guard 全部 primary_regression。

## 頭 2／頭 5 換馬（換入 − 換走上名率）

| | 乾地 頭 2 | 乾地 頭 5 | 濕地 頭 2 | 濕地 頭 5 |
|---|---:|---:|---:|---:|
| G | −11.2pp | +5.9 | −2.1 | +5.2 |
| GW | −10.5 | +2.9 | −7.6 | +3.7 |
| GWX | −10.5 | +2.9 | −7.8 | +0.4 |

## 解讀 —— EXP-36 嘅兩個解釋都唔成立

- **「濕地往績被過度加分」唔係原因**：降低唔同地況往績嘅權重，乾地頭 2 仍然 −10.5pp，而頭 5 嘅改善反而減半。
  EXP-36 見到「推入頭 2 嘅馬 60% 往績係濕地」係**伴隨特徵**（佢哋喺舊表下被低估，所以 G 一修正就上升），唔係錯誤來源。
- **「G 同 wet overlay 重複計」唔係原因**：EXP-36 嘅「冇 wet overlay +4.0pp」係**兩邊都**拎走 overlay 嘅比較；
  只喺候選拎走（GWX）就係丟失 production 本身需要嘅資訊，濕地日更差。
- 教訓：喺同一批數據逐格切出嚟嘅解釋，未經獨立測試唔可以信 —— 兩個都喺第一次真測試就倒。
- G 乾地日頭 2 蝕仍然未有解釋。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X=<外置碟>/EXP-20261101-37 Y=<外置碟>
python3 scratch/au_speed_wet_fixes_eval_20261101.py --root "$(cat .wongchoi_au_data_root)" \
  --dump $Y/EXP-20261101-30/dump_shipped.json --races $Y/EXP-20261101-31/races.json --outdir $X/arms
python3 scratch/au_l600_pit_standard_judge_20261101.py $X/arms/base.json $X/arms/GW.json $X/v3/GW.json
# §8：au_walkforward_refit.py predict（base／GW／GWX）→ au_paceperf_s8_20261016.py
```

證據：`EXP-20261101-37-evidence/`。
