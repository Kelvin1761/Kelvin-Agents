# EXP-20261028-15 出賽經驗校準（預先登記）

- **日期**：2026-10-28
- **平台**：AU
- **背景**：EXP-20261028-11 更正（`ad522b97`）將超額對齊到模型名次 × 馬群大細，按生涯出賽數分組
  （2026-08-05 起 3,015 場）。13 組入面只有 3 組 CI 唔跨零：3 仗 +3.4pp [+0.8, +5.8]（偏低估）、
  1 仗 −2.2pp、20+ 仗 −0.9pp [−1.5, −0.4]（偏高估，頭 3 名 −3.9pp）。2 仗馬已經校準好（−0.1pp）。
- **假設**：按生涯出賽數畀綜合分一個校準加減，可以修正呢個系統性偏差，令 Gold／Good 位升。
- **搜索過嘅舊記錄**：EXP-20261028-11（收縮 REJECT）、EXP-20261028-13（≥15 仗規則剷走）、
  EXP-20261028-14（G5 幅度 REJECT）、EXP-20261009-03（初出用試閘分 REJECT）；記憶
  `au-cohort-gap-is-not-a-gain`、`cohort-cells-are-not-term-evidence`。
- **改到嘅檔案**：冇（量度喺 dump 上做，綜合分最後加一項）。

## ⚠️ 數據紀律

呢個假設係喺**成個乾淨窗**（2026-08-05 → 2026-10-27）入面睇出嚟，所以：

1. **唔准用 `fixed_rule` 全紀錄判決**（等於喺發現數據度驗證自己）。
2. 一律 `walk_forward_oos`：每個測試窗（7 個賽日）嘅加減只用之前嘅乾淨賽日 fit，warmup 30 個賽日。
3. **主 arm S1 九組全部一齊估**（0／1／2／3／4／5／6–9／10–19／20+），唔淨係揀見到差距嗰兩組 ——
   避免「13 揀 3」嘅挑選偏差。
4. S2（只估 3 仗同 20+ 仗）係發現時揀出嚟嘅，有挑選偏差，**只報告，唔可以單獨上線**。
5. v3 WIN 都唔即刻上線：要再過一次 **forward holdout**（2026-10-28 之後嘅賽日，未睇過），
   一個 family 只開一次。

## Arm（固定，唔再調）

候選綜合分 = baseline ability + offset[出賽組]（出賽數用引擎 `_career_starts()`，排位表賽前欄位）。

| arm | 估邊幾組 | 用途 |
|---|---|---|
| S1 | 九組全部 | **判決 arm** |
| S2 | 3 仗、20+ 仗（其餘 0） | 只報告 |
| AA | 冇（offset 全 0） | 把尺檢查，必須 REJECT |

**fit 程序**（S1／S2 一樣，鎖定）：
`logit P(入前三) = α[馬群 ≤8／9–12／13+] + β·(ability − 場內平均) + γ[出賽組]`，Newton 法，γ ridge 1e-3。
offset = 收縮(γ/β)，收縮係數 n／(n + 500)（n = 該組訓練匹數）；S1 再按匹數加權置中。

## 判決規則（預先寫定）

- 語料：`dump_new`（main `93f8050f` 引擎，即 B1+C3 之後），2026-08-05 起、全場有賽果。
- 判決器：`evaluate_full_record(mode="walk_forward_oos")`，primary Gold／Good 位，
  ranking `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`，賽日 bootstrap 2000 次。
- S1 同 S2 當一個 family 做 **Holm**；S2 就算過都唔上線。
- 預先聲明分層：馬群 ×4、首選 SP ×5、首選出賽組 ×9 —— 有一格 Gold 或 Good CI 全負 = REJECT。
- AA 唔係 REJECT → 把尺有問題，成個實驗作廢。
- S1 WIN → 註冊 forward shadow（offset 用上線日之前全部乾淨數據 fit 嘅值凍結），
  夠 400 場新賽事先判一次；forward 唔係 Gold／Good 都 ≥ 0 就 REJECT。
- **leakage-audit**：`career_starts` 由排位表（賽前）讀；fit 只用測試窗之前賽日。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/exp-20261028-fq-weight-class"
for a in AA S1 S2; do python3 scratch/au_starts_offset_wf_20261028.py --dump "$X/dump_new.json" --arm $a --out "$X/starts_$a.json"; done
```
