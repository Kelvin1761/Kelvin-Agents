# EXP-20261019-04 — HKJC 逐 leaf 移除（噪音檢查）：預先登記

- **登記日期**：2026-10-19，喺跑 arm **之前** commit
- **平台**：HKJC；Kelvin 審查計劃第 3 步；**Stage 4 v3 `fixed_rule`**（只係設 60，冇 fit）
- **問題**：每個 leaf 喺現行模型入面仲有冇淨貢獻？剷走（設中性 60）會唔會更好？

## 範圍

已經做過、唔包：段速六個微訊號（EXP-20261016-14／17）、騎練六個加減項（EXP-20261018-03）、檔位與走位（EXP-20260902-08 判死）、
同程（EXP-20261019-01）。今次 9 個 leaf：

| leaf | 維度 | 有效權重 |
|---|---|---:|
| jockey_score | 騎練 | 0.1299 |
| class_score | 級數 | 0.1071 |
| trainer_score | 騎練 | 0.1063 |
| formline_strength_score | 賽績線 | 0.0801 |
| weight_score | 級數 ＋ 健康 | 0.0514 |
| form_score | 穩定性 | 0.0491 |
| consistency_score | 穩定性 | 0.0393 |
| risk_score | 健康 | 0.0247 |
| trackwork_trend_score | 晨操 | 0.0098 |

## 方法

`hkjc_reflector/scripts/hkjc_leaf_removal_study.py`：用 EXP-20261019-03 嘅 dump（main `7bbca09c` 之後冇改過引擎），
非初出馬嘅綜合分 += 有效權重 ×（60 − leaf）；初出馬不變；維度 clip 忽略。`current` arm sanity 要重現 production。

```bash
L=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_leaf_removal_study.py
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $L dump.jsonl --arm current --out current.jsonl
for x in form_score consistency_score jockey_score trainer_score class_score weight_score risk_score formline_strength_score trackwork_trend_score; do
  python3 $L dump.jsonl --arm remove_$x --out remove_$x.jsonl
  python3 $H compare current.jsonl remove_$x.jsonl --stage4 fixed_rule --leakage-audit-passed
done
```

家族 = 9 arm × 6 指標，Holm。

## 點讀

- **REJECT（primary_regression 等）** = 剷走會輸 → leaf 有用，保留。
- **WIN（Holm 後）** = 剷走更好 → 候選剷走，2026-10-19 起 forward ≥ 60 場確認先上線。
- 冇 WIN、冇顯著差 → 判唔到（§6：有效權重細嘅 leaf 預期分辨唔到）。

## 結果

見 `EXP-20261019-04-hkjc-leaf-removal-results.md`：9 個全部 REJECT（全部保留）。
