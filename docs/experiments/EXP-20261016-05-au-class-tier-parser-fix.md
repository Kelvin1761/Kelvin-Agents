# EXP-20261016-05 正確性修正：AU 班次 tier parser

- **日期**：2026-10-16；**平台**：AU
- **性質**：合約 §7 正確性修正。**呢個冇通過表現閘，唔係一個已證實嘅改善。**
- **起因**：EXP-20261016-04 M1 —— 往績班次標籤 9 月起 100% 有，但 `_get_class_tier` 只認得
  34–37%。用戶 2026-10-16 要求先修 parser，再討論近績分／表現質素分合併。
- **改到**：`engine_core.race_class_tier()`（新，module 級），`_get_class_tier` 改為呼叫佢；
  `tests/test_race_class_tier.py`（32 個 case）。

## 錯處（唔靠績效數字都證明到）

舊 parser 用 substring：

| 情況 | 舊 | 應該 |
|---|---|---|
| `Designer Coolrooms Maiden Plate` | `"lr" in "coolrooms"` → **Listed（3）** | 新馬（8） |
| `LENNOX HOTEL BENCHMARK 66 HANDICAP` | 只認 `bm\d+` → 預設 7 | BM66（6） |
| `RDO EQUIPMENT TAREE BENCHMARK 82 HANDICAP` | 預設 7 | BM82（5） |
| `MDN-SW`、`CB MDN PLT` | 只認 `maiden` → 預設 7 | 新馬（8） |
| `0 - 56`、`GRAD HCP 60+`、`HIGHWAY-C3` | 預設 7 | BM56（7）、評分 60+（7）、第 3 班（6） |

新 parser 一律要字界；冇班次資訊嘅標籤（`HCP`、`2Y HCP`、`TAB HANDICAP`、`SWP`）照舊當未知 7。

## 覆蓋（乾淨窗）

| | 舊 | 新 |
|---|---:|---:|
| 今場賽事名認得 | 1,200 / 2,485 | **1,696** / 2,485 |
| 往績班次標籤認得 | 36.2% | **87.6%**（59,578 行） |
| 今場 tier 改變 | — | 221 場 |

## 點解會郁排名

而家 parser 只喺近績分用：`today_tier`（今場賽事名）同 `entry_tier`。`entry_tier` 仍然讀緊
唔存在嘅 `entry["class"]`（EXP-20260903-01），所以永遠係 7；即係呢個修正只改今場 tier，
從而改全場近績分乘數（0.7／0.85／1.0／1.1／1.2）。221 場、1,932 匹馬嘅近績分有變。
**`entry_tier` 駁去 `source_race_class`（K2）係另一個候選，今次冇做。**

## §7 條件

1. **錯處獨立證明** ✅ —— 上表。
2. **零顯著退步** ✅ —— v3 fixed_rule 全紀錄（2,485 場）：Gold **±0.00**
   [−0.12, +0.12]pp；Good **−0.16pp** [−0.39, +0.04]；Top3@5 −0.0003、NDCG −0.0002、
   Top5 AUC −0.0003，全部 CI 跨零。判決器字面係 `REJECT / primary_regression`（Good 點估計負），
   正正就係 §7 要處理嘅情況。預先聲明分層（馬匹數 ×4、首選 SP ×5）**冇一個 CI 全負**；
   最差係首選 $8–15 Good −0.34pp [−1.13, 0.00]。
3. **leakage** ✅ —— 賽事名同往績標籤都係賽前資料。
4. 本記錄寫明唔係已證實改善。

「如果數字係相反方向，仲會唔會改？」—— 會。將贊助商名入面嘅 `lr` 當 Listed 係錯嘅，同績效無關。

## 檢查

- golden：120 匹抽樣馬冇一匹喺受影響場次 → 全部一致，冇重錄。
- data contract：2,000 場／19,799 匹重新 calibrate，引擎指紋 `97a66cda4c56`。
- 模型說明：生成器重生成（只係指紋同日期）。`./檢查.sh` 全過。
- S2 forward shadow 喺凍結 commit `3903102b` 跑，唔受影響。

## 下一步（未做）

- K2：`entry_tier` 用往績 `source_race_class`。往績標籤而家 87.6% 認得，可以另開登記。
- 近績分／表現質素分合併（用戶提議）：等討論。

## 重跑

```bash
python3 scratch/au_stability_dump_20261016.py --variant f6a --out $S/tierfix.json   # 修正後
python3 scratch/au_tier_fix_eval_20261016.py $S/stab.json $S/tierfix.json $S/tierfix_eval.json
```
