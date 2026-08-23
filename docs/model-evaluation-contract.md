# 模型評估合約（AU / HKJC Wong Choi）

**呢份係「一個候選好唔好」嘅唯一裁判規則。** 建立於 2026-08-21，由 code 反推
（之前冇呢份文件，所以同一個候選喺唔同 harness 之下可以得出相反結論）。

每一項都標明**來源**：`code` = 由現行 code 讀出，`推斷` = 我推斷，`實測` = 當日跑出嚟。
**唔准喺呢度填估出嚟嘅值。** 改咗 code 就要改呢度。

> ⚠️ 改動呢份文件 = 改動判決規則。`model-regression-gate` 明文禁止「換指標／換窗／
> 換 top-K 去救一個候選」。要改把尺就當一個**獨立**改動，先單獨論證，唔可以同
> 候選一齊改。

---

## AU

### 判決規則（PRIMARY）

> **頭 K=5 位配對嘅場內 AUC，holdout 上 95% 配對 bootstrap 區間唔過 0。
> dev 點估計唔准係負。就係咁多。**

來源：`au_eval.py` docstring 寫死。

**點解唔用場數指標做主裁判**：2026-08-04 校準過 —— 對 leaf 加 ±0.3 **確定中性**
嘅隨機擾動跑 40 次，dev 5-fold + walk-forward + holdout 三道閘全過嘅係 **0/40**。
假陽性 0 好，但同時代表真 +1pp 嘅改動大機會過唔到。場數指標照要報，但係**次要**。

### 規格

| 項 | 值 | 來源 |
|---|---|---|
| 基準命令 | `au_dump_engine_leaves.py --out X` → `au_eval.py --data X` | code |
| 前置 | `au_matrix_refit.py verify --data X`（replica 一致性，未 verify 過唔好信搜索結果） | code |
| 主指標 | 頭 K=5 位配對場內 AUC | code |
| bootstrap | 2000 次，**按場**重抽（同場配對唔獨立，按對重抽會低估區間）；`seed=7` 已固定 | `BOOT=2000`, `_boot_ci` |
| 次要指標 | gold, gold_strict, good_positional, pass, champion, winner_in_top3/5, t3prec, mrr, ndcg5, blowout | `eval_metrics.py` |
| **搜索目標（判決）** | **`place` = (gold, good_pos, pass, t3prec)** —— 2026-08-23 由 `balanced` 改。本 project KPI 係上名捕捉，`balanced` 會令搜索用 `champ`/`winT3`/`mrr` 買走 `pass`/`t3prec`。歷史紀錄（08-01/08-03/08-08 三次重 fit）係 `balanced` 出嘅，要對比要明確傳 `--obj balanced` | `au_matrix_refit.OBJ_PRESETS` |
| **分層指標** | 場數指標按馬群大細分四桶（≤8 / 9-10 / 11-12 / 13+）—— **必報** | `au_eval.FIELD_BUCKETS` |
| dev/holdout | 按**唯一日期**切，尾 15% 日期入 holdout；唔切開同一日 | `date_partitions()` |
| fold | dev 內部 5 個時間 fold | `au_feature_ab` / `au_matrix_refit` |
| 訓練期 | **不適用** —— 冇訓練步驟，六維權重手工擬合 | 推斷 |
| 隨機種子 | `golden_scoring.SAMPLE_SEED=20260821`；bootstrap `seed=7` | code |
| 必需數據 | `AU_Racing/**/Race_*_Logic.json`（用 `corpus_paths`，要包 `Archive/`）+ `AU_Historical_Raw_Race_Results.csv` | code |
| 排除記錄 | 前三不足 3 匹、冇頭馬嘅場次（`_counts` 直接 `continue`） | code |
| 樣本 | 1,413 場 / 14,121 匹 | 實測 2026-08-21 |

### 現行 baseline（commit `b51793d7`，喺 `99d81e64` 一樣成立）

| 指標 | all | dev (901) | holdout (512) |
|---|---|---|---|
| **頭5位 AUC** | 0.6793 | 0.6871 | 0.6631 |
| 全場 AUC | 0.6655 | 0.6725 | 0.6503 |
| gold | 17.79% | 16.13% | 20.70% |

> ⚠️ **`gold` 嘅定義好易讀錯。** 佢係「**實際前三全部落喺模型頭四揀之內**」
> （捕捉率 —— 三隻上名馬有冇一隻走漏），**唔係**「頭馬喺模型頭四揀之內」。
> 2026-08-23 有一次分析全程用錯後者並叫佢 `gold@4`，令幾個候選睇落有「gold 升」
> 嘅好處，用正確定義重測之後嗰個好處**完全消失**（pace_perf 減權 Good位 −2.43 ❌、
> 剷濕地 overlay Gold −0.17、PF×PI 降權 Good位 −1.08 ❌）。舊定義叫 `gold_strict`
> （模型頭三揀全部上名）。三個數字唔可以混住講。
| gold_strict | 6.24% | 6.01% | 6.64% |
| good_positional | 23.53% | 21.47% | 27.15% |
| pass | 46.99% | 43.72% | 52.73% |
| champion | 25.73% | 24.81% | 27.34% |
| winner_in_top3 | 56.13% | 54.62% | 58.79% |
| t3prec | 47.51% | 46.13% | 49.93% |

分層（Gold，dev / holdout）：≤8 匹 31.58% / 33.63% ｜ 9-10 15.38% / 13.33% ｜
11-12 9.21% / 9.65% ｜ 13+ 8.91% / 5.00%

---

## HKJC

**用完全另一套閘門**，同 AU 嘅 AUC 判決規則**唔通用**。

| 項 | 值 | 來源 |
|---|---|---|
| 命令 | `hkjc_no_regression_gate.py`（冇 `--baseline` 模式，設計上比較候選） | code |
| maximize keys | gold, good, min_threshold, champion, top3_has_champion, mrr, avg_top4_hits | code |
| 樣本 | 264 場 | 實測 |

### 現行 baseline

Gold 19（**7.20%**）· Good 68（25.76%）· Pass 124（46.97%）· Champion 73（27.65%）
· MRR 0.4656 · Order Issue 101 · Avg Top4 Hits 2.083 · Passing candidates: none

> ⚠️ **AU 同 HKJC 嘅 Gold 唔可以直接比。** HKJC 個 7.20% 接近 AU 嘅
> `gold_strict` 6.24%，**唔係** AU 個 `gold` 17.79%。冇任何文件講兩套指標點對應 ——
> 呢個係已知缺口。

---

## 已知缺陷（記錄，未修）

1. **「85/15」呢句話係錯嘅。** `date_partitions` 切嘅係**日期**。新語料每日場次密度
   高好多，所以 15% 日期 = **36.2% 場次**（512 / 1,413）。
   `au_eval.py` 而家一定印 `holdout_share_of_races`，但 repo 內仍有 docstring 寫「85/15」。
2. **dev / holdout 係 regime 切分，唔止時間切分。**
   dev 只有 11.0% 係乾淨 point-in-time、平均馬群 10.51；
   holdout 100% 乾淨、平均馬群 9.08。`au_eval.py` 差距 >0.5 會出警號。
3. **場數指標唔按馬群正規化。** dev 內 Gold 由 ≤8 匹 31.58% 跌到 13+ 匹 8.91%（3.5×）。
   pooled 比較會被組成變化冒充成模型變化 —— 所以分層係**必報**，唔係可選。
4. **2026-08-05 之前嘅檔位相關 A/B 唔可信。** `au_draw_bias_matrix.json` 由完整賽果
   重建，回測舊場次時矩陣含住嗰場自己嘅賽果。live 冇問題（評分嗰刻未來未存在）。
   詳見 [EXP-06](experiments/EXP-20260821-06-au-race-shape-contribution.md)。
5. **HKJC 嚴重缺實驗** —— 絕大部分實驗都係 AU。

---

## 相關

- 完整審計：[`audits/2026-08-21-repo-model-audit.md`](audits/2026-08-21-repo-model-audit.md)
- Codex 交接：[`handoff/2026-08-21-codex-handoff.md`](handoff/2026-08-21-codex-handoff.md)
- 實驗記錄：[`experiments/INDEX.md`](experiments/INDEX.md)
- 紀律規則：`AGENTS.md` 嘅「改模型嘅規矩」；`.claude/skills/model-regression-gate/`
