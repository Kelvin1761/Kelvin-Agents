# EXP-20261014-09 — AU 賠率變動 ML：資料時點與覆蓋審計

- 日期：2026-10-14
- 狀態：**資料審計完成；固定時窗 ML 暫不 fit；現役模型不變**
- 授權：Kelvin 希望模型學習賠率變動訊號，確認先做資料審計與獨立試驗設計。
- 這份記錄沒有候選模型績效，不使用 REJECT 表示「賠率變動無用」。
- Repo HEAD：`0116c740330db7f02f9d04d2884e211b1d494517`；worktree 有其他工作，HEAD不代表
  所有live code。實際audit script SHA及逐個input檔SHA256保存在外置`audit.json`。

## 問題與來源

要回答：控制**當時價格**及**當時AU模型分數**之後，價格變動是否仍能幫助預測勝出／前三？
縮價預測、賽果預測及扣成本回報是不同目標；本研究先處理賽果增量，不能以P(firm)代替P(win)。

已搜尋舊研究：EXP-20260826-08（價格混合主要由市場貢獻）、EXP-20260831-15（市場資訊缺口）、
EXP-20260928-02/07（ML／Hybrid、Top4 rerank）；沿用`docs/model-evaluation-contract.md`，
不更改Gold／Good／holdout規則。

使用現役`corpus_paths.meeting_dirs`，包含root、Archive及catalog-backed來源。
部分舊skill文字仍說Archive會被排除；這份審計以實際canonical reader為準。
只讀primary root `/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing`，
不遞迴把backup或prediction副本當新meeting，不讀Drive mirror，不改資料或來源parser。

## 實測覆蓋

| 指標 | odds_history.json | Odds.json |
|---|---:|---:|
| meeting | 353 | 356 |
| race | 2,731 | 2,756 |
| race-level captures | 7,869 | 5,395 |
| runner price observations | 80,507 | 56,329 |
| 至少兩次capture的race | 2,246 | 2,176 |
| 多次capture且至少有一匹能配賽果 | 2,000 | 1,895 |
| 最後capture runner數 | 27,022 | 27,299 |
| 最後capture與Logic身份配對 | 27,022 | 27,299 |
| strict文字身份賽果配對 | 23,285（86.17%） | 23,383（85.66%） |

**兩份representation有大量重疊，不能相加當成獨立樣本。**
賽果配對使用日期＋literal venue normalization＋race＋horse，沒有擴張場地alias或模糊配對。
未配對可能是退出馬、尚未結算、venue/name差異或缺結果；本次沒有把它們一律標成輸馬或SCR。
「有一匹配到」不等於完整Gold／Good可評估race，也不證明價格在賽前。

459個canonical meeting；237個meeting有immutable predictions，共520個snapshot manifest。
結果CSV35,157rows；這份strict composite key零重複、零不同名次衝突。
JSON讀取無parse問題。這些是本次存量inventory，不是市場訊號表現。

## 最重要的時點問題

1. **價格確實有變。** history首尾共同runner21,992個，15,273個價格不同；Odds.json
   是21,289個共同runner、16,399個不同。這是描述統計，沒有因果／預測結論。
2. **重複價格不能當額外独立樣本。** history有2,673個連續相同獨贏價格向量（34.0%captures），
   2,609個來源標籤是morning-rebuild。排除rebuild後，有2,033場仍有兩個其他觀察標籤。
   相同價格可代表持續不變，也可只是同一cache被重寫；本次只計數，沒有刪除或填補。
3. **明確補錄不能冒充當時觀察。** 265個backfill-from-formguide capture全部晚於meeting date；
   另有7個test-capture、8個backfill-test。未來建模必須排除，不使用mtime猜原來時間。
4. **時區證據不同。** history全部7,869個timestamp沒offset，只能暫按scheduler宣稱的
   Australia/Sydney解讀；Odds.json全部5,395個captured_at及520個manifest有明確offset。
   naive時間一律標inferred，沒有當作等同已驗證的timezone-aware observation。
5. **capture不等於quote更新。** Odds.json在meeting extraction／寫檔時打stamp，
   history的analysis／rebuild也可能讀較早Formguide/cache。沒有逐runner source_time／freshness證据。
   在有限資料下，capture time最多是聲稱的known-by時間，不能當作精確價格更新時刻。
6. **歷史jump time未完成驗證。** 已讀structured price artifacts與對應Logic race context，
   沒有非空的start_time/race_start_time/scheduled_start/jump_time/start。
   舊cache抽樣是賽後HTML，開賽時間已消失；meeting mapping亦只有日期／IDs，沒有race times。
   這不是聲稱所有來源都不可能補到時間，而是目前未取得可審計的歷史時間來源。
   所以同日capture無法可靠分成T-60/T-30/T-10之前或賽後；**不能fit後當成無洩漏**。

history有1,212個prior-day、6,392個same-day、265個later-day captures；Odds.json是
1,419個prior-day、3,976個same-day。兩份都沒有一場有兩次prior-day captures，因此目前
不能靠「全部在meeting日之前」直接建一份價格變動訓練集。
CSV的`Time`是winning time／比賽耗時，不能拿來充當scheduled jump時鐘。

## 更正 Flucs 的理解

2026-08-05起，current horse sections共28,156個：27,299個Flucs只有一個價格，857個沒有值；
沒有一個有多個current價格。全archive較舊9,384個多價格section不會因此被當成clean-era資料。
現役Sportsbet writer寫的是`Flucs:$- $fixed_win`；真實多時間點資料應從structured snapshots取。
之前「舊Flucs有價格序列」的說法太廣，本審計據值更正。

## 判決與已完成工作

**有足夠理由研究市場變動，但這份存量資料尚未通過固定時窗時點閘。**
沒有fit logistic／LightGBM，沒有用不完整snapshot造出Gold／Good或ROI結果。
也沒有用「CI跨零」判方向失敗；目前還未到性能判決階段。

已完成：存量審計、race-level診斷CSV、來源hash、6個時間／價格／重複／只讀不變性tests，
及独立試驗設計`docs/plans/2026-10-14-au-odds-signal-ml-study.md`。
6項研究tests、`./檢查.sh --quick`及完整`./檢查.sh`均通過；完整測試沿用
`WC_HKJC_SCHED_LOG_DIR=/private/tmp/horse-analyst-hkjc-test-logs`覆寫測試日誌。
現有AU／HKJC data-contract stale-baseline警告保留，沒有重校其他session的模型基準。
沒有啟動RacingBoard、collector、排程或任何帳戶／投注工具。

外置證據：
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/audits/market-readiness-20261014/`

- audit.json：總數、來源分類、timestamp品質、script/input hashes。
- races.csv：逐場capture數、重複價格、首尾變動、保守結果配對與時間FLAG。
- meetings.csv：逐meeting來源覆蓋。

沒有完整corpus複本；只讀逐檔解析，輸出是小型診斷紀錄。read bytes不等於temp佔用。

## 重現

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scratch/au-market-lab-20261014/test_market_audit.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scratch/au-market-lab-20261014/audit_market_data.py \
  --root '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing' \
  --output-dir '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/audits/market-readiness-20261014'
```

只准寫output-dir；data root只讀。若檔案在讀取途中改變，會大聲失敗而不是靜靜混用版本。
