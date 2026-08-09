# AU Sportsbet data / failure-direction audit — 2026-08-09

## Scope and fixed ruler

- 固定 current-runtime dataset：805 場，whole-date development 594 / terminal 211。
- Current baseline：Gold 16.77%、Good 25.71%、Pass 47.20%、Winner@3 56.27%、
  Winner@5 75.53%、Top-5 paired AUC 0.69294。
- SP 同實際名次只喺 pre-race score 固定排名之後用作 retrospective cohort label；
  賠率冇進入任何 candidate scorer。
- 用戶指定兩類錯誤：
  1. model Top 2/3、賠率大、最後包尾；
  2. 市場熱門實際入前三、model 排第 5 或更後。

## Exact failure cohorts

805 場現役模型有：

- model Top 3 + SP≥21 + 實際包尾：32 個；尾二敏感度 cohort：55 個；
- 市場頭馬實際入前三、model rank 5+：81 個；
- SP≤4 實際入前三、model rank 5+：88 個。

共同最大資料缺口係 `performance_quality_score`：

- 大冷包尾：30/32 missing/fallback；
- 市場頭馬漏捉：73/81 missing/fallback。

大冷包尾主要被 stability、class/weight、pace context、race shape 推高；熱門漏捉主要被
race shape、class/weight、stability、pace context、track 壓低。呢個 pattern 唔支持鎖 Top 2
後做 coverage-slot rerank；佢支持改善 scoring matrix 入面真正個體能力證據嘅覆蓋同語意。

可重播工具：

- `scripts/au_failure_direction_audit.py`
- regression：`tests/test_failure_direction_audit.py`

## Full Sportsbet raw-cache audit

掃描 3,627 個 HTML cache：1,090 race pages、1,695 person-profile pages、842 其他頁。
歷史往績 raw / parsed 係 138,935 / 138,526（99.71%）。

| Field | Raw | 舊 parser | 新 parser | 新/raw |
|---|---:|---:|---:|---:|
| 任一 in-running checkpoint | 100,427 | 68,132 | 100,283 | 99.86% |
| 1200m checkpoint | 31,531 | 0 | 31,466 | 99.79% |
| Winning Time | 104,776 | 0 | 104,551 | 99.79% |
| Sire | 14,607 | 0 | 14,607 | 100% |
| Gear Changes | 2,886 | 0 | 2,886 | 100% |

實際 parser bugs：

1. `Settled, 1200m, 800m, 400m` 中間一有 1200m，舊 rigid regex 會掉晒整段；
2. 只有 `400m` 嘅短格式一樣會掉；
3. Sportsbet 頭馬只寫 `Finished 1/N`，唔寫 `0L`；舊流程將 margin 當 missing，
   Performance Quality 反而丟掉所有贏馬往績；
4. winning-time parser 要求兩位分鐘，`1:52.590` 會變 None；
5. raw HTML 有齊 Sire/Dam/Foaled/Breeder/Colours/Gear，Formguide 仍寫空 pedigree；
6. race event title 有 distance/class，舊 parser 只搵全頁第一個 distance token，class 冇 transport。

修正後：checkpoint 獨立 parse；勝仗 margin 正規化為 0L；Winning Time、1200m、pedigree、
identity 同 race class 完整 transport。Gear 用 `SportsbetGear:` report-only key 保留，未過 gate
前唔用「有轉配就加分」shortcut。

可重播工具：

- `scripts/au_sportsbet_raw_field_audit.py`
- regression：`tests/test_sportsbet_extended_fields.py`

## Performance Quality coverage candidate

由 Sportsbet historical runs 重建 point-in-time complete-form quality：每仗日期必須嚴格早過
target meeting；只用輸距、賽事獎金、出馬數；SP/result 冇入分。106 個 matching meetings、
922 race pages產生 9,905 runner digests；749/805 場通過最少三匹完整 field gate，
6,026 個原本 missing/fallback runners 可補。

Development-only alpha search 選出 0.75。一次打開 terminal：

- Top-5 AUC：dev +0.00328；terminal +0.01267，95% CI `[+0.00432,+0.02210]`；
- Winner@3 +1.99pp；Winner@5 +1.49pp；Pass +1.49pp；Top-3 precision +1.12pp；
- 大冷包尾仍留 model Top3：32 → 27；
- Gold -0.25pp；Good -0.37pp；市場頭馬入前三但 rank 5+：81 → 85。

結論：能力質素 coverage 有顯著整體 ordering value，亦能剔走部分假強冷門；但 0.75 配方未
同時守住 Gold/Good，同熱門漏捉方向變差。按用戶 Gold/Good 優先規則，**唔將 0.75 blend
升做正式 scoring change**。Parser correctness 同資料 transport 照樣保留；candidate 留作可重播
research，唔用 terminal 再揀第二個 alpha。

敏感度只作 locked-selection 後報告：full alpha 1.0 Gold +0.12pp、Good -0.37pp；alpha 0.5
Good +0.37pp、Gold -0.25pp；冇一個版本同時全面解決兩類錯誤。

可重播工具：`scripts/au_sportsbet_performance_quality_candidate.py`。

## New data collection started

1,695/1,695 個 person pages 全部有 Distance、Barrier、Field Size、Spells 同 Monthly Breakdown，
但舊 `parse_person()` 將同名 Career / Last 12 Months label 壓平，只留十個基本格。

新 parser 保存：

`{section -> window -> label -> stats}`

例如 `Distance -> Last 12 Months -> 1201-1400m`、
`Field Size -> Last 12 Months -> 13+`。每次真正 refresh 會追加到
`AU_Sportsbet_People_Snapshots.jsonl`，帶 `captured_at`，唔覆蓋舊 snapshot。

呢批 contextual people data **暫時唔入分**：現時頁面係滾動 profile，唔可以用今日數字回填
舊賽果。由而家開始累積 versioned snapshots，之後只准用 `captured_at <= race time` 做 forward
validation。最優先驗證 distance band 同 field-size band，因為熱門漏捉集中喺 race-shape / track /
class context，而且大 field 仍係弱 cohort。

## Next evidence priorities

1. 用 versioned jockey/trainer distance + field-size stats做真正 forward favourite-miss audit；
2. Winning Time 先按 track + distance + going 做 rolling standard，再加 margin 推算 runner-level
   performance；未 normalize 前唔將 race-level時間冒認做個體速度；
3. 用歷史 target races建立 sire empirical-Bayes rolling profile，唔靠 hard-coded sire 名單；
4. 繼續禁止 odds 入 scoring，只用嚟定義錯誤 cohort同策略層。
