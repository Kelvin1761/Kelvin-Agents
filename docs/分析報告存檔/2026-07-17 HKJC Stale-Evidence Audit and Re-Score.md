# HKJC Wong Choi 陳舊證據審計與重新評分（2026-07-17）

> 以帶 AU 到 parity 嘅同一套方法審視 HKJC Wong Choi。同一把尺：
> `.agents/skills/shared_racing/eval_metrics.py`（positional Good = 頭兩推薦同入前三；
> any-2 Good；互斥標籤；MRR）。全 archive 基線 243 場 / 24 個有結果 meeting：
> Good-pos **21.0%**、any-2 **43.2%**、W-in-T3 **51.9%**、Top1 **23.5%**、Gold 9。

## 1. 陳舊證據審計 — 發現真實 schema 漂移（sectional 全盲）

`scratch/hkjc_stale_evidence_audit.py` 掃全 archive，逐月統計每個持久化 `feature_score`
嘅 default-60 率、engine 版本、derived sub-feature 覆蓋率。

| 月份 | 場次 | 馬匹 | speed_score default-60 | schema_version |
|---|---:|---:|---:|---|
| 2026-04 | 60 | 739 | **100.0%** | `None`（舊） |
| 2026-05 | 91 | 1147 | 16.8%（月合計） | 混合 `None` → `HKJC_LOGIC_V4_2` |
| 2026-06 | 71 | 899 | 3.7% | `HKJC_LOGIC_V4_2` |
| 2026-07 | 42 | 533 | 4.7% | `HKJC_LOGIC_V4_2` |

逐場劃界極清晰：**所有 `schema_version==None` 嘅場（4月全部 6 場 + 05-03），
`speed_score` 99–100% 係 default-60**，即係成個 **sectional（段速）矩陣維度完全失效**；
由 05-06（`HKJC_LOGIC_V4_2`）起，speed default 跌到 2–11%，sectional 才有作用。

關鍵證據：同一批 meeting 嘅 `Facts.md` 其實**有齊 L400／走位／能量／頭馬距離**（例：
04-19 Race 5 Facts 有 36 處 L400）。而現行 skeleton 抽取器（`create_hkjc_logic_skeleton.py`）
喺同一份 Facts 上抽得到 `raw_l400=23.00` 等 primitives。**即係話 4月係俾舊版抽取器評分，
段速數據明明喺度但冇入到 `_data`。** 呢個係 AU facts-refresh（f47f9e4）嘅 HKJC 對應版。

### Faithful-replay 契約修復（已 commit `dc24651`）

- `engine_core.py`：`python_auto.derived_feature_scores` 加持久化 `race_shape_context_score`
  （production `race_shape` 用佢，權重 1.0；但持久化嘅 12 個 feature_scores 只有 `draw_score`，
  replay 之前 fallback 錯輸入）。
- `walk_forward_auto_backtest.py`：`score_meeting()` 將持久化嘅 `derived_feature_scores`
  merge 返入 recompute features，令 `new` 欄可忠實重現 production 嘅
  form_line／stability／race_shape（限有持久化嘅版本）；WARNING 註釋改為描述真正嘅
  fidelity 邊界（舊 meeting + 矩陣後調整未 re-apply）。
- 新增 regression test：`derived_feature_scores` 必含 5 個 sub-feature，且 merge 返去必須
  重現 stability／form_line／race_shape／class_advantage 嘅 stored matrix scores。

## 2. Sandbox 重新評分 — 決定性 FAIL，不可採納

`scratch/hkjc_stale_rescore_driver.py`：源 meeting **唯讀**，全部 input（Facts／排位表／晨操／
全日賽果）clone 落 `/tmp`，逐場用**現行** skeleton + orchestrator 重新抽取＋評分，再喺同一把尺
對歷史結果評估。Pipeline 已驗證忠實：field 齊全（14→14、11→11 無跌馬）、sectional 完全
recover（speed default 14/14 → 0/14）、jockey/trainer priors 有接上、schema 升級。

**7 個 sectional-blind meeting（71 場）：**

| 口徑 | OLD（存檔，sectional 盲） | NEW（現行引擎 re-score） | 差 |
|---|---:|---:|---:|
| Good-pos | 22/71 = **31.0%** | 13/71 = **18.3%** | **−12.7pp** |
| any-2 Good | 50.7% | 43.7% | −7.0pp |
| W-in-T3 | 60.6% | 52.1% | −8.5pp |
| Top1 | 29.6% | 23.9% | −5.7pp |
| Gold | 3 | 3 | 0 |

重新評分令**每個口徑都變差**，同 AU（facts-refresh recover 咗被誤讀嘅證據、明顯有幫助）**相反**。
7 場之中 6 場持平或轉差，只有 04-12 喺個別口徑升。

### 獨立佐證（來自 §3 cohort 分析，非同一計算）

- **2026-04（sectional 盲）竟然係全 archive 最強月份**：Good-pos 31.7%（+10.7pp）、
  W-in-T3 58.3%（+6.5pp）。
- **feature coverage「rich（<15% default）」係最差 cohort**（Good-pos 16.3%，−4.6pp）；
  「medium/thin default」反而最好（28.7% / 30.0%）。

兩個獨立角度都指向同一結論：**現行 sectional 訊號喺呢個 cohort 係淨中性至輕微有害**——段速數據
越齊，排名越差。重新評分把段速「補返」反而拖低。

**結論：重新評分 FAIL 預先登記嘅 gate（Good −12.7pp，遠低於 +1.5pp 門檻，且 Top1/W-in-T3
大幅倒退）。不可採納。** 官方 archive 分數保持不變。呢個似 AU round 10（PF backfill FAILS,
do not adopt）——系統照做嘢，killed candidate 係常態。

## 3. 場地（going）持久化評估 — 唔需要 AU 式 going refresh

- HKJC `Logic`／`排位表`（賽前 racecard）**完全冇記錄 going/track condition**；`場地狀況`
  （例「好地至快地」）只喺**賽後**`全日賽果.json` 出現。所以根本冇一個賽前 going 值可以「陳舊」。
- 引擎**根本冇 race-level going 輸入**：`_track_going_score` 讀嘅係**每匹馬歷史場地往績**
  （`good_record`/`course_record`/`draw_verdict`），係 per-horse 適性 proxy，唔係當日場地。
  所以唔存在 AU「Warwick Farm 用咗陳舊 Soft 5」嗰種 bug。
- Going 變異度極低：全 archive 151 場有記錄 going 之中，78% 係 好地／好地至快地（快地端），
  Happy Valley **從無**軟地（只有好地/好地至快地），只有 6.6% 屬軟/濕地端（黏地/濕慢地）。

**結論：HKJC 唔需要 AU 式 `--going` refresh。** 加 race-level going 會係一個全新 feature
（要有自己嘅因果觸發＋過 gate），唔係 data-correctness 修復；而且賽前根本攞唔到 going，
低變異度下訊號亦有限。

## 4. 可重跑輸出

- `scratch/hkjc_stale_evidence_audit.py` → `_report.md` / `_monthly.csv` / `_meetings.csv` / `.json`
- `scratch/hkjc_stale_rescore_driver.py` → `scratch/hkjc_stale_rescore.json`
  （`--keep-sandbox` 可保留 /tmp re-score 供覆核）
- 詳見 `2026-07-17 HKJC Failure Cohorts and Attribution.md`（cohort + 歸因 + zero-hit）
  同 `2026-07-17 HKJC Candidate Shadow Tests.md`（候選 gate）。
