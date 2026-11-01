# EXP-20261101-25：Sackmann／TML已連結原始點數盤點

狀態：完成串流唯讀盤點；未fit、未改正式pricing、未量準確度、未改任何訓練資格／REJECT判決。它補充[WTA-only盤點](EXP-20261101-24-tennis-point-input-feasibility.md)，不是可部署point-skill模型。

後續語義覆核見[EXP-26](EXP-20261101-26-tennis-source-owner-identity-audit.md)：在原145539個LINKED中，2153個source-name與terminal標籤不一致，另1個terminal tour UNKNOWN；原數字及artifact沒有改寫，也沒有把新policy agreement當成獨立人物資格。確認raw點數存在不等於球員歸屬正確。

## 完整範圍及方法

使用同一凍結`ranking-date-contract/source.sqlite`，1,943,166,976 bytes；重新完整驗SHA-256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`。指定兩provider的全部160900個stored history sides均保留結果：Sackmann66738、TML94162，沒有只挑有stats的行。

逐一讀取50個被history引用的raw receipts及其原始arrays，沒有按CSV ordinal位置配對。按明示tour、tourney_id、match_num及winner/loser source ref找唯一raw key；對照provider external player ID到canonical pair／tour、原始tournament/date、history ACTIVE與非self-pair、raw fetch及history creation aware時計早於固定2026-11-01T00:00:00Z、雙方真實svpt/1stIn/1stWon/2ndWon/SvGms合法整數、0<point rate<1，以及stored兩項serve rate與raw比例一致。

來源score只接受事前固定的保守完整BO3/5子集：沒有RET／walkover等字串、只含可解析set tokens、標準6局／win-by-two／7–6終局、winner先達所需盤數。合法但不在子集的特殊賽制仍暫扣；`partial_or_unsupported_score`不能改寫成全部是壞資料或退賽。這次不是所有年代／賽事比分規則的認證。

cutoff檢查是**依據這份凍結DB時計欄位**的inventory；不單獨證明資料已在那個歷史市場時刻被獨立觀察。尤其tourney_date不是精確match start/end，不能供workload hours或F07使用。未來訓練／forward仍須在實際預測之前有canonical capture／first-observed證據，不能將本次cutoff倒填到舊預測。

## 結果

| provider | 全部sides | 通過本次raw連結檢查 | HELD |
|---|---:|---:|---:|
| jeff_sackmann | 66738 | 59412 | 7326 |
| tennismylife_history | 94162 | 86127 | 8035 |
| 合計 | 160900 | 145539 | 15361 |

145539條中，按provider/raw receipt/source-match key得到72686個兩側完整group，另167個單側group。**這不是72686個跨provider去重後的獨立可訓練matches**，也不能與WTA151場直接相加。合併source去重、選樣分佈及精確可用時間仍未認證。

原因會重疊，不能相加：provider-ID canonical pair conflict3729、partial/unsupported score6276、point counts缺失／無效／退化5672、inactive/self pair238、raw key缺失／不唯一991、raw payload不可解析858、raw date/event conflict53。50 receipts中18個不能解析JSON，錯誤與每條受影響history id均保存；沒有用後來來源補位，也未覆寫來源或刪掉held行。

通過連結的玩家數（按provider分開，不去重）：Sackmann ATP716（381人≥5條）、WTA792（419人≥5條）；TML ATP1824（1106人≥5條）。這推翻「因主history沒有point denominators，所以所有provider完全沒資料」這個概括，**不證明point skill已識別、資料符合歷史PIT或候選會更準**。

## 資源、安全及下一步

開工量到內置碟約4.5GiB，其後約5.2GiB，低於AGENTS大型實驗10GB底線；沒有開新模型訓練／大型副本實驗。這是串流唯讀inventory：DB不複製、SQLite immutable/query_only、TMPDIR及約23.8MB輸出全在已確認掛載的外置碟，peak RSS132,186,112 bytes。其他session的暫存未刪；本sessionworktrees各約62MB，已完成build環境約11MB，沒有可確認屬於本session的大型內置副本足以解決空間問題。

後續先核對完整group的跨provider重複、source refs／日期衝突與raw缺口，以及future input capture；維持原frozen ruler、15個REJECT_DEV及F10依賴。大型實驗要等內置free≥10GB；資料連結檢查通過不構成模型promotion，也沒有啟動新forward。

## 重現及證據

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/point-input-public-history-v1/`，含事前protocol、完整source.py、逐history id的rows.jsonl、50 receipts的body hash／錯誤、result及manifest。

原命令（repo根）：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python /private/tmp/tennis-public-point-input-inventory-20261101.py`。原source另存上述目錄；重播需複製source，僅將OUT改為全新外置目錄並記錄新source hash，原程式拒絕覆寫既有目錄。

- result SHA-256：`73727057a429686edeba8c3a6af9832e86aadf74081540d3e4939827e4edac45`。
- manifest SHA-256：`cd3179fd349413d4ee723c5320ff4eb78834f5b4488d1f615a4e613f7f32f92d`。

執行時checkout為已push但等待自動replay的b18478aed7639fea975c3900a885be3ef31890a3；所用既有reader／Sackmann metrics沒有改動。規則resolver後來已以37df3367b71fd3eb1294329da0527037a474f17a成功合併及同步runtime，完整gate929.056秒。兩者是獨立證據，不以resolver綠燈替此資料盤點或準確度背書。
