# AU Wong Choi full-code reset audit — 2026-08-08

Baseline：`099c718`（Claude 大改後版本）。所有比較固定同一份 Sportsbet result truth，
唔混用舊 Racenet corpus。

## 結論

- Active source alignment：822/822 Logic 有唯一 Facts、Racecard、Formguide；race number、
  馬號、馬名全部一致。
- 可對賽果：623 場 / 6,400 匹；195 場未有對應賽果，4 場不足四匹或前三 overlap。
- Current model 較 `adc0adc` 全樣本 Gold、Good、Pass、Winner@3/5 全部改善；terminal
  AUC 方向亦正，但 95% CI 跨 0，所以唔誇大成「統計已證實」。
- 新配權同 pairwise ranker 未過 promotion gate；保留簡單 linear matrix，唔疊新模型。
- WIN/PLACE discovery strategy 都未過 holdout ROI gate，唔 promotion 做投注規則。

## 修正嘅 correctness bugs

1. Runtime audit 以前直接食 stale Logic，冇重現正式 pipeline 嘅 Facts/Formguide
   enrichment，而且錯將 Logic path 當 Facts path。現已共用 `prepare_logic_for_scoring()`。
2. Facts resolver 會揀中同名 `Race_1_Facts.md` directory，引發 `IsADirectoryError`；
   現只接受 regular file。
3. Sportsbet HTML flatten 將 `Track: Good` 後面嘅 `25°C/29°C` 當成 `Good 25/29`；
   parser 同 archive canonicalizer 都會拒絕不可能 grade。
4. Main orchestrator 嘅 Sportsbet URL 以前只行 `--probe`，之後用 Racenet regex 搵 folder，
   所以必然失敗。現會由 tracked meeting index 解出完整 meeting 並真正抽取。
5. Architecture audit 重算 class matrix 時漏咗 display gain，令已退役 weight leaf 睇落
   會改 370 場排名；現時 live formula parity 只剩 rounding 級差異。
6. Coverage denominator 曾包含已退役 `sectional_score`、`weight_score`；現只量 11 個
   ranking-evidence leaves。Ranking matrix registry 亦唔再包含 0-weight `form_line`，但
   report schema 繼續保留佢，避免破壞解讀輸出。
7. `au_eval` baseline 曾只印 AUC、漏 Pass 等 KPI，而且按 race row 切 holdout；現支援
   leaves/runtime 兩種 schema、列齊 metrics，並按完整賽日切分。

## Final current-runtime baseline（623 場）

| Metric | All | Dev | Terminal holdout |
|---|---:|---:|---:|
| Top-5 pairwise AUC | 0.6776 | 0.6796 | 0.6694 |
| All-field AUC | 0.6670 | 0.6707 | 0.6533 |
| Gold（actual Top 3 全在 model Top 4） | 15.09% | 16.37% | 9.48% |
| Gold strict（model Top 3 全上名） | 6.26% | 6.31% | 6.03% |
| Good（model Pick 1 + Pick 2 都上名） | 21.19% | 22.68% | 14.66% |
| Good any-2 | 43.02% | 44.18% | 37.93% |
| Pass（model Top 3 至少一匹上名） | 88.60% | 89.15% | 86.21% |
| Champion（首選頭馬） | 23.92% | 23.47% | 25.86% |
| Winner in Top 3 | 56.18% | 55.82% | 57.76% |
| Winner in Top 5 | 75.92% | 75.94% | 75.86% |

Facts refresh 將 audit 入面 `Unknown going` 由 492 場降至 39 場；其餘可識別分布已
canonicalize，`Synthetic 8` 同 `Soft 5 (Turf)` 不再拆成假 cohort。

## `adc0adc` → latest，同一資料/同一 enrichment

| Metric | Old | Latest | Delta |
|---|---:|---:|---:|
| Gold | 14.45% | 15.09% | +0.64pp |
| Good positional | 20.22% | 21.19% | +0.96pp |
| Good any-2 | 41.73% | 43.02% | +1.28pp |
| Pass | 87.32% | 88.60% | +1.28pp |
| Winner in Top 3 | 53.93% | 56.18% | +2.25pp |
| Winner in Top 5 | 72.07% | 75.92% | +3.85pp |
| NDCG@5 | 52.74% | 55.39% | +2.65pp |

Top-5 AUC delta：dev `+0.0204`；terminal `+0.0103`，terminal 95% CI
`[-0.0087, +0.0294]`。所以整體改善清楚，但 terminal 樣本單獨仍未足以宣稱顯著。

## 未 promotion 嘅候選

- Balanced consensus：Good 約 +4.01pp、Top-5 AUC dev +0.0089 / terminal +0.0086，
  但 terminal CI `[-0.0069, +0.0260]`。
- Place consensus：Good 約 +3.37pp，但 terminal CI 跨 0，且舊 leaves dev 微負。
- 四個 pairwise ranker：全部未過 walk-forward/terminal promotion gate。
- Betting：WIN 候選 terminal ROI +8.9%，CI `[-24.2%, +74.8%]`；PLACE terminal
  ROI -5.2%。兩者均 FAIL。

## Runtime / verification

- Auto engine：Randwick 10 場重算 `0.63s`。
- Full mainline：首次 stale Facts/Logic rebuild `7.85s`；第二次 warm run `0.70s`。
- Tests：AU auto 203 + daily scheduler 57 = 260 passed；compileall、shell syntax passed。

## 已知限制

歷史 Sportsbet jockey/trainer `(LY:)` 係抓取當日 rolling 12-month aggregate，唔係每個
歷史 race date 嘅 point-in-time snapshot。舊版/新版公平比較使用同一份 prepared data，
所以模型差異比較受控；但任何單獨引用 absolute backtest rate 都仍要帶住呢個 confound。
