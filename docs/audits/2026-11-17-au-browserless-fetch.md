# AU sportsbetform 唔使 Chrome 抓取（2026-11-17）

Kelvin（2026-11-16）：「can we try using nba and tennis way」「as long as we can get all the data and transition smoothly from using the chrome」。

## 結論

排程預設改用 `sb_http_fetch.HybridFetcher`：curl_cffi（chrome120）攞**同一條 URL**、寫**同一個 cache**，下游 parser／寫檔唔使改；
撞到任何非 200／攔截頁即停唔重試，今次 run 餘下嘅頁轉返 headed 真 Chrome。`WC_SB_FETCH=browser` 行返舊路。
賠率（JS 填，raw HTML 冇）改由 sportsbet.com.au `RacecardWithContext` 喺攞頁嗰刻寫 sidecar `<cache>.odds.json`。

## 證據（同一部機、同一個 IP、每版隔 25 秒、全部 200、零 403）

| 測試 | 結果 |
|---|---|
| `/form/<CODE>.html` vs 瀏覽器 cache，11-17 賽前 16 場（`docs/experiments/patches/au_form_page_probe/`，分支 `claude-au-mobile-form-20261116`） | 往績 1,700 條一致、5 條對手騎師全名 vs 縮寫（Facts 冇用）、0 條只得一邊 |
| 騎練個人頁 13 版 vs 瀏覽器 cache | 13/13 所有表格逐格一樣 |
| 賽事頁（賽前）2 版 vs 22:00 瀏覽器 cache | 往績同馬匹區塊一樣；退出馬 curl 版**較新**（Kyneton R1 夜晚多 3 匹，API `statusCode=S` 證實） |
| 賽事頁（賽後）11-16 Goulburn R1 | 當日名次／頭馬距離／SP 一樣，所有往績一樣（`sb_results` 用） |
| `/{date}/` 索引頁、`?view=Speedmap` | 200；索引 parse 到 10 個場次（2026-08-05 記錄係 403） |
| **端到端**：11-17 Scone 8 場，HTTP 同真 Chrome 先後各抓賽事頁＋Speedmap（共 32 版），各自 `write_meeting` | 18 個輸出檔 16 個完全一樣；Racecard 8/8 一樣；2 個 Formguide 只差幾匹馬嘅賠率數字（兩次抓相隔幾分鐘，市價郁咗） |

端到端第一次跑發現 Formguide `Flucs:` 行（讀 JS 填嘅賠率格，排程市場警號 `market_odds_from_formguide` 用）喺 HTTP 版係空 →
改為冇賠率格就用 sidecar 獨贏價（同樣兩位小數）。修完先係上面 16/18。

## 評分輸入

Racecard 全部一樣；Formguide 只有賠率欄唔同，而賠率唔入評分（`_write_odds_snapshot` docstring、`test_odds_capture.py`）。
`./檢查.sh` 評分 golden（AU／HKJC）全綠。所以呢個係抓取層改動，唔係模型改動。

## 風險同監察

- 個站之前（2026-08-05）會 403 curl_cffi；而家放寬咗唔代表永遠。`HybridFetcher` 一被拒絕即轉 Chrome；
  `close_browser` 嘅 run step 記 `fetch_mode`、`http_fallback`、`odds_sidecars`、`odds_missed`。
- 賠率對唔上唯一一場（同名馬場同場次號唔唯一）就唔貼，寧願冇賠率。
- 樣本：今次每類頁幾版到幾十版；第一晚 22:00 正式 run 係真正嘅量（約 100+ 版）。
