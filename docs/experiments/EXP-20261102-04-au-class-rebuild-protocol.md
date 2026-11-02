# EXP-20261102-04 預先登記：AU 班次部分重建（官方評分對位維度）

> 量度之前寫。結果另寫 `EXP-20261102-04-au-class-rebuild-results.md`。做法跟速度重建（EXP-20261101-43）：
> 先 1:1 搬去一個簡單模組，A/A 全語料證實一樣，先至改公式；公式改動逐個預先登記。

- **日期**：2026-11-02；**平台**：AU；**baseline**：`origin/main` `348049dc`。
- **用戶**：「級數分應該點 handle，正路佢應該幫到手」→ 同意「以高班實績證明做主體、取代粗規則」；
  「while doing it, please rebuild this section with the simplest code and formulas to also clean out all bugs and deadcode like what we did earlier for speed」。
- **搜索過**：EXP-20260825-03／04（proven_class overlay 0.5×z）、EXP-20260826-06（級數分復活）、EXP-20260831-06（讓磅殘差）、
  EXP-20261009-04（級數分 0.15 入維度，USER-ACCEPTED，forward 11-09 檢討）、EXP-20261016-18（R1x／R2x 等）、
  EXP-20261028-12／13／14（讓磅認字、≥15 場規則剷走、G5 幅度）、EXP-20261102-03（評分趨勢 REJECT）。
- **今日診斷**（session scratch，唔係判決）：負磅喺評分之上冇增量（讓磅賽 +0.0017 CI 跨零；非讓磅 −0.0045 CI 全負）；
  剷級數分 0.15 份額 +0.0004 CI 跨零；喺綜合分之上加重 proven_class +0.0019 [+0.0005, +0.0034]。

## 第 1 步：結構（唔改分數）

新模組 `au_racing_engine/class_rating.py`：純函數計 級數分、評分分、負磅代理、代理分、負磅分（顯示）、高班實績水平。
引擎方法只負責砌說明。同時剷死 code、修顯示錯：

| 項 | 證據 |
|---|---|
| 省賽轉都會「RT ≥68 唔扣」豁免 | Facts `L600/RT` 欄 2026-08 起 436k 行 0 行有值 → `latest_rt` 永遠 None |
| `_class_score` 計 `race_bucket` 冇用 | 賦值後冇讀 |
| 報告「負磅分基礎分 62」 | 實際由 60 起計（`wdetail["base"]` 寫錯） |
| 維度判語「級數分…參考（不入排名）」、註釋「class_score 早於 07-29 退出」 | 級數分 2026-10-09 起以 0.15 入排名 |
| 判語「負磅分 ≥63（降班配輕磅）」「≤57（爛地重磅）」 | 負磅分上限 60；爛地扣分 09-05 已剷；降班輕磅係扣分 |
| `_class_move_today` 註釋「live 一律未知」 | 今場獎金有來源，10 月「班次有回落」觸發 4,761 次 |

**判決**：全語料 `au_dump_engine_leaves.py` 重評，同 baseline dump 逐匹 `features`／`ability` 比較。
08-05 起乾淨段必須 0 差。08-05 之前（Racenet 年代）如因 RT 豁免剷走而郁，逐匹列出，唔計入判決（該段唔係判決語料）。

## 第 2 步：公式候選（一個 family，Holm）

| arm | 改動 | 類型 |
|---|---|---|
| **F1** | 混合讓磅場、冇評分、用負磅代理嘅馬，**唔再扣** `class_once`（代理冇用級數分，扣咗＝將佢維度入面嘅級數份額清零；R2x 註釋自己講「代理再用佢就計兩次」，但呢條路冇用） | §7 正確性修正 |
| **C1** | 級數分剷「降班 +2.1」同「省賽轉都會 −5.48」；保留初出馬、出賽 ≤5 場規則（EXP-20261028-13 證實剷走會傷） | fixed_rule |
| **C2** | 高班實績搬入級數分：`級數分 += 8.712 × z(proven_class)`，同時剷 `proven_class_feature` overlay。8.712 = 0.5 ÷ (0.3826194 × 0.15)，即係有評分馬嘅綜合分貢獻同 overlay 數學一樣；冇評分馬經代理（佔 0.70）會放大 —— 呢個係設計：冇評分先最需要班次 | fixed_rule |
| **C3** | C1 + C2 | fixed_rule |

全部常數係預先定（冇 fit）。F1 喺 baseline 之上量；C1–C3 喺 **F1 之上**量（F1 唔過就喺 baseline 之上）。

**窗口**：2026-08-05 → 語料最後一日，v3 全紀錄 `fixed_rule`，bootstrap 以賽日、2000 次、seed 7。
**ranking metric**：`top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`。
**分層**（預先聲明）：馬匹數 ≤8／9–12／13+、首選 SP $1–3／$3–6／$6+、路程、首選跑法；另加 **讓磅／非讓磅**、**全場有評分／混合／多數冇評分**。

**採用規則**：
- F1：§7 —— primary 冇顯著負、冇預先聲明分層 CI 全負 → 上線（寫明唔係已證實改善）。
- C1–C3：Holm 調整（3 個 arm）後 PRIMARY_WIN 或 RANKING_WIN → 上線揀 Holm 後最強嘅一個；
  C1 單獨「冇代價簡化」（Gold、Good 點估計 ≥ 0、冇 ranking CI 全負、冇分層 CI 全負）都可以上線（理由：少兩條規則）。
  其他 REJECT。
- 唔做 §8 refit（冇 fit 參數；refit 留俾之後 walk-forward 候選）。

## 唔准做

睇完結果改 8.712、改 z 門檻（≥3 匹）、加 arm、換窗、換指標；用 holdout 揀 k。
**Leakage**：proven_class 只讀今場之前嘅往績行（Facts 第 20 欄），同 overlay 一樣，EXP-20260825-03 已審。

## 限制

- proven_class 欄位 2026-08-25 先有，08 月覆蓋 17%、09 月起 74–80%：C2／C3 喺 08 月幾乎冇作用。
- 級數分 0.15 份額本身係 EXP-20261009-04 forward 中（11-09 檢討）；今次改級數分公式會令佢嘅回退影子（`class_score_live_delta`）跟新公式。
