# EXP-20261121-32 AU 把尺：加「頭二選有中／頭二上名率／頭三上名率」做 ranking metric

- 日期：2026-11-21　平台：AU　類型：**判決規則改動（把尺）**，獨立改動，唔同任何候選一齊改
- 決定：Kelvin 2026-11-21「Other than gold and good, same as hkjc if we can have better order for top 1 & 2,
  improved 0 hits, better position at 5 or better position at 3 i think we should consider them」→「先改 AU 把尺」
- 狀態：**上線**（`au_eval.RANKING_METRICS`；合約「Ranking metric 登記（AU）」）

## 改咗乜

| Kelvin 講法 | 指標 | 狀態 |
|---|---|---|
| 頭 5 位置 | `top3_capture_at5` | 已有 |
| 頭 3 位置 | `top3_place_rate`（頭三選上名數 ÷ 3） | 新 |
| 頭 1、2 排序 | `top2_place_rate`（頭二選上名數 ÷ 2） | 新 |
| 0 中改善 | `top2_any_hit`（頭二選最少一隻上名，同 HKJC 一樣） | 新 |
| — | `ndcg_at5`、`top5_pairwise_auc` | 已有 |

- 以前呢串 tuple 喺 `au_eval` 兩處、6 個 forward、`au_walkforward_refit` 各自抄一次（違反「一樣嘢只准有一個標準」）；
  而家只有 `au_eval.RANKING_METRICS`。
- 跑緊嘅 6 個 forward（預先登記喺 11-21 之前）用 `RANKING_METRICS_PRE_20261121` 凍結舊尺。
- 判決次序唔變：Gold／Good 點估計 < 0 照樣 REJECT；新指標只喺 Gold／Good 冇跌先有作用，同時多咗「有害」偵測。
- 冇郁模型、冇郁分數。

## 驗證（命令：`docs/experiments/patches/au_ruler_top2/rejudge.py`，dump 喺外置碟 `scratch/au-noise-20261113` 等）

語料：3,736 場（08-05 起、有頭馬兼 ≥3 上名），v3 `fixed_rule`，賽日 bootstrap 2,000。

1. **A/A**：舊尺、新尺都 REJECT ✅（`ranking_evidence_too_weak`）。
2. **純噪音候選**（ability + N(0,σ)）：σ 0.5 同 2.0 各 40 個 seed —— 誤判 WIN **舊 0/80、新 0/80**。
3. **人工真改善敏感度**（30 seed 一格；WIN 次數 舊／新）：

   | 改善 | 舊 | 新 |
   |---|---:|---:|
   | 全部上名馬 1% 加 0.3 分 | 9 | 10 |
   | 全部上名馬 0.5% 加 0.3 分 | 3 | 3 |
   | 排第 3–5 嘅上名馬 1% 加 1.0 分 | 28 | 28 |
   | 排第 3–5 嘅上名馬 0.5% 加 1.0 分 | 13 | 14 |

   新尺**冇變易過**，亦冇明顯多咗功效：真係令頭二選多中嘅改動，通常 Good 都會一齊升，舊尺已經捉到。
4. **舊候選重判**（13 個 fixed_rule，同一份 dump）：冇一個變 WIN。

   | 候選 | 舊尺 | 新尺 |
   |---|---|---|
   | EXP-20261113-21 FINAL／WA／WB | ranking_evidence_too_weak | **ranking_metric_harm**（`top3_place_rate` −0.21／−0.17／−0.19pp，CI 唔跨零） |
   | EXP-20261113-21 FLFIX | too_weak | too_weak |
   | EXP-20261113-21 P1／T1／T2／T3 | primary_regression | primary_regression |
   | EXP-20261111 近績質素尺度 F1／F2 | primary_regression | primary_regression |
   | EXP-20261113-43 前置直路 V1／V2 | primary_regression | primary_regression |
   | 賽道幾何補數 NEW | too_weak | too_weak |

   證據：`EXP-20261121-32-evidence/`。

## 結論同限制

- 新尺對準 Kelvin 落注用法（頭二選），誤判率冇升，舊判決冇一個翻案；真正新增嘅係「Gold／Good 打和但頭二／頭三變差」會被攔。
- **冇解決** AU 把尺最大嘅問題：Gold／Good 好粗、細而真嘅改善大約一半機會判死（HKJC 11-15 因為咁改用 log-loss＋歷史回放）。
  AU 要做同樣嘅事，要先有長嘅 point-in-time 歷史語料，係另一個項目，要 Kelvin 決定。
- 走勢／walk-forward 候選（短直路 W1、上仗賠率 P、外層 refit R）冇 dump，冇重判。
