# Tennis ESPN 單雙打及 tour 入庫候選

2026-11-05 Sydney。從 `64a08c8df` 獨立 worktree。ESPN ATP scoreboard 可能同時包含女單同雙打。共同 normalizer 先攔三種明示雙打，再攔已明示性別同 endpoint tour 不符嘅單打。缺明示分類嘅輸入沿用既有行為。今次只修 draw／tour 路由。

隔離 SQLite，用正式 `ingest_upcoming_matches` 同 `ingest_historical_matches`，同一日兩個公開 endpoint 嘅原始 response 各自重播。2026-01-31 baseline 同候選均入 34 fixtures、68 履歷行、68 球員。舊程式將其中一場澳網女單決賽及兩個球員錯寫 ATP，候選全 34 場、68 條履歷及 68 個球員為 WTA。全部接受嘅履歷來源 keys 相同。2026-01-30 同一份 response 刻意供兩條路徑，baseline 身份閘已攔混雙，候選保留同樣兩場 ATP、四行履歷，提早攔錯 draw 同 tour。現役唯讀核對，女單決賽 168468 無 fixture，兩個 ESPN athlete mappings 都係 WTA。

另將兩份 1 月 31 日原文各自重播整個 1 月 18 日至 2 月 1 日澳網正賽日期窗，只保留 edition 154-2026。baseline 將 254 個女單履歷 sides 全部寫 ATP，候選 254 個全入 WTA。254 個男單 sides 照樣入 ATP。呢個係固定原文全屆壓測，唔代表當年逐日 endpoint 實際回應。

賽制係獨立問題，兩場澳網男子準決賽現有 BO3 值仍未修。原預測、評估 cohort、ruler、betting 策略無改。模型準確度未評估。
