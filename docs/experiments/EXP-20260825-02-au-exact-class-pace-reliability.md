# EXP-20260825-02 Sportsbet 原始班次 transport 與 PacePerf 可信度

- **日期**：2026-08-25
- **平台**：AU Wong Choi（Sportsbet-only）
- **起因**：最新 `main@6356a7ab` 重建 Randwick R2 後，Dee Dee Express／
  Zubba Storm 仍排第 2／3但實際第 15／14；Lovecats 仍第 8但實際第 3。
- **假設 A（correctness）**：Sportsbet 已解析每仗原始班次（例如 `BM64`、
  `F&M CL3-SW`），但 writer 將佢丟掉，必須完整 transport。
- **假設 B（ranking）**：精確歷史班次可補充獎金 proxy，或者用來降低低班次
  race-level PacePerf 嘅可信度。
- **判決**：**A KEEP（只作 evidence、不入分）；B REJECT（holdout CI 跨零，亦
  修唔到 R2）**。

## 先鎖定最新 baseline

1. 已將 known-good AU commits 及語義修正 fast-forward merge 到 GitHub `main`，
   baseline commit：`6356a7ab`。
2. 以同一 commit 重新執行 `au_dump_engine_leaves.py`：**1,591 場／16,062 匹**，
   PacePerf 有效覆蓋 67.1%。冇沿用 2026-08-21 舊模型 dataset。
3. Randwick R2 用 2026-08-22 10:11 保存嘅 Racecard／Formguide full pipeline 重建，
   `Soft 6`、data health 0 error／0 warning、coverage 98.1%。

最新 R2 排名：Mrs Goldberg 1、Dee Dee Express 2、Zubba Storm 3、Parthenope 4、
Kakoda 5、Manoora 6、Bombay Boom 7、Lovecats 8；實際前三係 Mrs Goldberg、
Empress Tsarina、Lovecats。即係問題唔係舊模型輸出殘留。

## 已確認 transport bug

`claw_sportsbet_form.parse_race()` 嘅 `run["header"]["cls"]` 一直有值；R2 例子：

- Lovecats：`F&M CL3-SW`、`3YF HCP`、`CL2`、`CL2`；
- Dee Dee Express：`F&M BM64`、`CTRY CL1`、`CL1`、`CTRY CL1`；
- Zubba Storm：`CG&E BM64`、`CL2 BM62`、`CTRY MDN`、`3Y MDN-SW`。

但 `run_line()` 冇寫出，Facts 只有獎金 proxy。修正後以
`RaceClass:[原始標籤]` 寫入 Formguide，再追加到 Facts 最後一欄
`Sportsbet原始班次`。Engine 只保存為 `source_race_class` evidence，**刻意唔接去
`entry["class"]` 或任何 matrix leaf**，避免繞過模型閘門。

## Point-in-time A/B

- cache index：179 meetings／1,490 race pages；
- 原始班次：16,328 匹／53,142 個歷史 run labels；
- 同最新 engine dataset 成功對齊：11,459 匹；
- 有至少 3 匹班次、可作場內標準化：1,261 場；
- 歷史 run 必須 `run date < target meeting date`；
- odds／SP 完全冇進 scorer；實際名次只作 label。

候選喺開結果前固定，冇 threshold search：

1. `class_form`：`form_score += 5 × 場內 exact-class z`；
2. `class_pf`：只有低班次來源兼 PF > 60 時，按連續 class z 收縮正面 PF；
3. `both`：兩者合用。

### Development

| 候選 | dev 頭5場內 AUC 差 |
|---|---:|
| class_form | **+0.001040** |
| class_pf | +0.000162 |
| both | +0.000261 |

按預先規則只鎖定 dev 最好嘅 `class_form`，再開一次 terminal holdout：

| 指標 | 結果 |
|---|---:|
| holdout 頭5 AUC | +0.001956 |
| 95% paired bootstrap CI | **[-0.004338,+0.008180]** |
| holdout 全場 AUC | +0.000111；CI [-0.004333,+0.004659] |

點估計正，但 CI 跨零；按 `docs/model-evaluation-contract.md` **REJECT**。

## R2 case replay

固定 exact-class 候選令 Lovecats `62.54 → 63.87`，但仍排第 8；Dee Dee Express
仍第 2、Zubba Storm仍第 3。`class_pf` 對 R2 更細，排序完全冇修正。即係「班次
transport」係真 bug，但唔係今場模型失準嘅充分原因。

R2 PacePerf 本身係 Sportsbet race-level 歷史速度環境：DDE 64.82、Zubba 69.21、
Lovecats 44.64。EXP-20260823-02/EXP-20260824-03 已分別否決剔試閘、壓高分、減權、
距離過濾及只計輸距 ≤3L；今次 exact-class reliability 亦無足夠泛化增益。喺
Sportsbet-only 限制下，未有證據支持再改 PacePerf ranking。

## 驗證

- targeted transport／Facts tests：37 passed；
- AU golden：120 匹全部一致；
- AU data contract 重新校準：874 場／8,804 匹，引擎指紋 `a95a33c6ff8c`；
- research harness：`scratch/au_class_pace_eval_20260825.py`；
- report：`/private/tmp/au_class_pace_eval_20260825.json`。

## 結論

**KEEP exact-class transport as report-only evidence；REJECT exact-class scoring 及
class × PacePerf interaction。** R2 最新模型仍然係一場真失準，但現有 Sportsbet-only
資料未提供一個通過 OOS 閘門嘅 PacePerf 修法；唔因單場答案靚而改 production。
