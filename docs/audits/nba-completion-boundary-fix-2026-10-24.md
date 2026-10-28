# NBA 完成核對補強：F09 新抽取來源閘

承接 `08ec7914` runtime 修正。完成核對發現：`extractor_cache_current` 已拒絕 defender API 失敗（observed_players=0），但新抽取分支只核對 availability，之後可繼續生成報告；FW-14 亦只驗 statistics contract 版本。即係「重試有做，第一次失敗仍可能發布」嘅缺口。

修正將 `nba_data_contract.statistics_current` 作為共用來源檢查，要求 contract 2、Totals、total_attempts、正整數 observed_players。cache、新抽取完成後、FW-14 三個入口用同一判斷。來源失敗保留診斷輸入、停止生成／發佈，等排程重試；唔用空資料冒充有效統計。樣本少而未滿 20 attempts 仍可以係有效來源，冇改選 defender 門檻。

驗證：新增五個實際 process_single_game 分支案例，觀察失敗抽取只到 extractor、有效來源可以到 schema；FW-14 同時驗證空／損壞來源、0／字串／bool 數目、錯模式／錯單位。NBA 三個 suite 共 459 tests 通過，quick gate 通過；發佈以 immutable full gate、merge／activation event 為準。

呢批只修來源失敗處理，冇改機率／權重／選腿門檻；現役 C JSON 及既有 v3 shadow artifact SHA 不變，唔聲稱命中或盈利改善。原始 F01–F12 審核紀錄保留，呢份補充 F09 嘅完整處理範圍。
