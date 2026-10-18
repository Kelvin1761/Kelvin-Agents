# EXP-20261018-09 — 賽績線標籤修正（弱組用中性 64）：預先登記

- **登記日期**：2026-10-18，喺跑 arm **之前** commit
- **平台**：HKJC；**Stage 4 v3 `fixed_rule`**（一個固定值，冇 fit，冇家族）
- **Kelvin 決定（2026-10-18）**：修標籤解析，但 weak 先用中性 64，唔開動未驗證嘅 −24（EXP-20261018-08 選項 2）。

## 候選（固定，唔准改）

`_formline_strength_signal` 只睇標籤本身（剝走「(強組比例…)」）：

| 標籤 | 現行（main） | 候選 |
|---|---|---|
| 極強 | elite 88 | elite 88 |
| 強、中強 | strong 78 | strong 78 |
| 中弱、弱 | strong 78（bug） | **neutral 64** |
| 無資料、空、N/A | strong 78／unknown 60 | unknown 60 |

之後嘅 higher/same/lower bonus（≤ +8）同「全部跑唔近 → 封頂 60」不變。
實作：`docs/experiments/patches/hkjc_arm_formline_label_neutral_weak.py`。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --out base.jsonl
python3 $H run --arm docs/experiments/patches/hkjc_arm_formline_label_neutral_weak.py --out cand.jsonl
python3 $H compare base.jsonl cand.jsonl --stage4 fixed_rule --leakage-audit-passed
```

- 全紀錄（harness 而家剔 04-12、04-15）；main `ea4a43af`。
- 判決：`evaluate_full_record` v3 次序。分層照報：馬匹數 ×4、首選 SP ×5、沙田／跑馬地。

## Leakage audit

`formline_strength` 由 Facts 賽績線產生（之前交手對手其後表現），欄位同 EXP-20261018-08 一樣；今次只改解析同幅度，
冇新輸入 → 同現行一樣（PASS，現行已經用緊呢個欄位）。

## 已知偏差

EXP-20261018-08 已經喺同一語料跑過「弱 = 54」版本（Good −1.74pp），即係見過「開動弱組會蝕」嘅方向。
今次幅度（64）由 Kelvin 揀，唔係由數據 fit。

## 判決後

- **WIN** → 2026-10-19 起 forward ≥ 60 場一次性確認（Gold Δ ≥ 0、Good Δ ≥ 0、NDCG@5 Δ ≥ 0），先上線。
- **REJECT** → 唔上線；記錄做已知缺陷（現行「極強 vs 其餘」兩級）。
- 冇顯著退步但冇 WIN → 交 Kelvin 決定（解析錯係 §7 可證，但幅度唔係）。

## 結果

見 `EXP-20261018-09-hkjc-formline-neutral-weak-results.md`：**REJECT**（Good −0.87pp），唔上線。
