# EXP-20261101-44：Christian／Jumpei 來源拆分 proposal 與 TE 原文缺口

狀態：**完成唯讀 proposal／引用盤點；未 apply、未改模型、未量準確度。** 延續 EXP-26–29，不把研究時鐘工具或具名來源標籤當成完整人物／runtime 資格。

## 1. 從來源賽事建立具體拆分範圍

2026-11-01 12:33:22 UTC，唯讀 transaction（約4.893秒，有5秒中斷上限）擷取 Christian Sigsgaard／Jumpei Yamasaki 的相同姓名、canonical descendants 及明確 canonical player 引用。群組為2110、2711、4457、19626。`wta_player_id` 是供應商 namespace，不當成 `players.id`；`provider_entities` 只取 entity_type=player。

現有12個 ACTIVE public-history perspectives 分成8個 Christian 來源視角、4個其他來源視角；另有78個 TennisExplorer ACTIVE perspectives。逐個 source response 保留精確解碼內容、SHA及gzip，沒有按模型勝負／ROI揀樣本。

| provider／raw ID | 原雙側 history IDs | source event／人物 | 假設新 player IDs（winner／loser） |
|---|---|---|---|
| Sackmann／1448 | 24211／24212 | 2021泰國–丹麥 Davis Cup；Christian／Wishaya Trongcharoenchaikul | 19626／1994 |
| Sackmann／1449 | 29943／29944 | 2022印度–丹麥 Davis Cup；Ramkumar Ramanathan／Christian | 350／19626 |
| Sackmann／1449 | 29983／29984 | 2022丹麥–薩爾瓦多 Davis Cup；Marcelo Arevalo／Christian | 378／19626 |
| TML／7182 | 204373／204374 | 2025-692／R32；Emilio Nava／Christian | 216／19626 |

來源 Christian 的 Jeff ID=144841、TML ID=SY00，四個來源 event 的 ioc 都是 DEN。每對在記憶體通過既有 `propose_split` 的 reciprocal／source-role／target name-tour 檢查。另列2個 provider mapping 的 exact before-image，擬將 Jeff144841、TML SY00 由2110轉19626；沒有整體rename／merge 2110群組。四個非Christian public perspectives保留，78個TE亦沒有因為共用ID而一起搬動。

target19626現有`composite/uts:44614`；獨立可讀的[UTS playerId44614頁](https://www.ultimatetennisstatistics.com/playerProfile?playerId=44614) header為Christian Sigsgaard／DEN，[ATP SY00頁](https://www.atptour.com/es/players/christian-sigsgaard/sy00/overview)亦有姓名。直接頁DOB等仍是動態placeholder，沒有假裝已驗DOB／完整registry。這是部分namespace／name／country佐證，不是四個對手及所有alias／fixture均已獨立認證，亦不使用舊UTS頁的排名作今日值。

**proposal狀態固定為 `REVIEW_ONLY_NOT_APPLY_READY`。** 記憶體每對只clone該pair，collision檢查不能代替全corpus／alias／event核對；來源讀取在table capture之後，各自有讀取時刻，並非一個全局atomic source snapshot。持久化修補器、native identity-availability guard、完整衍生Elo／排名及fixture ownership仍未齊。沒有修改不可變prediction、ledger、raw receipts或observation。

## 2. 引用範圍不能只數 selection_player_id

直接player引用包括90行history、5個fixtures、8個predictions、13個feature snapshots、2個prop_tracker、51＋51個兩版Elo history、124個rankings_history及各種聚合表。這些是引用，不是已證明錯誤的模型輸出。

第二次獨立唯讀 transaction於12:43:38 UTC完成，約0.831秒；從5個fixture IDs沿supersedes parent／child檢查，再列出所有宣告INTEGER canonical match_id的表。五個原fixture與第一輪逐欄相同。只輸出數量及hash：

| match scope 表 | 行數 |
|---|---:|
| predictions | 10（直接選球員只見8） |
| feature_snapshots | 26（直接player只見13） |
| market_predictions | 45 |
| prop_tracker／prop_price_log | 4／4 |
| match_results／result_observations | 4／4 |
| market_odds_snapshots／closing_odds_snapshots | 81／25 |
| fixture_observations／market_captures | 8／12 |
| bet_ledger／clv_tracker／combo_tracker | 此次各0 |

不把直接player與match scope數目相加，不把全部引用當成受污染預測／注單，也不由此推論ROI或所有間接ledger foreign-key鏈已核對。尚須按實際來源分類，而不是重寫這些歷史紀錄。

原本擬匯出live fixture bodies的動作被automatic approval review拒絕，理由是payload可能包含內部投注／市場資料。改用只含counts／IDs／hashes的替代方案完成第二輪；沒有匯出該輪fixture原文或table payload。沒有繞過拒絕，也沒有待用戶批准才能完成的彙總工作。

## 3. 新發現：TE history 的原始scoreboard沒有保存在這些來源記錄

為查78行TE的身份證據，核對現行 `ingest_tennisexplorer_history.py`：先存一份 `{summary: ...}`，再fetch／parse各日結果，所有history指向這份summary；provider `_fetch_html`沒有在該流程保存實際HTML。已安裝runtime與worktree ingester逐byte相同，SHA：`012469a7cc280f557fc71466fe72d6ed9b36ce025d29bf522fe6db7bc3ce0ebc`。

繼而擴到**全部 frozen TennisExplorer history**，不是只看這78行：

| 原始來源狀態 | history perspectives |
|---|---:|
| accessor讀出的logical body空白 | 232766 |
| 非空，但只有summary，沒有結果原文 | 7380 |
| 全部 | **240146，分布81個raw-response groups** |

raw fetched_at屬於那份已存summary，不證明缺失的scoreboard內容曾經被保存。本次沒有從空白造內容、將normalized history假裝原始HTML，或用今日重抓回填當年已知。這是指定frozen raw-response路徑的缺口；未窮盡所有備份／其他輸出，不能宣稱每場舊賽事永久無法恢復。某些已有CREATED after-images可驗記錄時鐘，也不能補出不存在的raw HTML。

第一版inventory在空原文`json.loads`失敗，完整source／protocol保留於v1；v2明列EMPTY、SUMMARY、不可讀及其他類別，保留全部240146行去向，沒有刪失敗行或縮語料。

## 4. 下一個實作優先次序

先修**未來TE來源保存**，避免繼續增加無原文history，再推進這份身份proposal：

1. provider暴露精確request URL／日子、實際fetch時計及HTML；每個日期獨立source receipt，先保存原文再parse，parse失敗仍留證據。
2. 正常history指向該日真實source。只回傳ParsedResult而無source的custom provider不能冒充原始回應；原本results-only API其他caller的用途另作清楚處理。
3. 驗相同HTML前後parsed results、player選取、勝負／比分及Elo數值；另驗跨日raw IDs、壞parse／fetch、空日、來源hash、冪等與source保留。raw metadata改動不當作模型改善。
4. 已有history的相同facts重跑可能仍保留原raw ID（既有upsert忽略raw ID差異）；必須明列，不能稱新抓HTML已追認舊來源或覆蓋舊資格。任何source confirmation／generation更新須另外保存實際觀察時鐘。
5. 身份proposal仍需全量collision、可回退persistent transaction及所有相關reader對新身份時計的處理；不能靠新raw保存解除舊FLAG。之後才做同語料baseline/candidate比較，準確度未量不稱提升。

本輪free約21GiB，沒有新fit／大DB副本，沒有native prediction／live DB寫入。15個REJECT_DEV、main-tour範圍及frozen ruler維持。

## 證據與交付

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `christian-source-proposal-v1/`：執行前protocol、source、current引用before-images、四個來源body gzip／SHA、逐行分類、pair proposals及result；共4個public raw bodies解碼14,167,830 bytes。
- `christian-match-closure-v1/`：safe alternative的protocol、source、彙總result及manifest；沒有fixture／table原文輸出。
- `te-history-source-inventory-v1/`、`te-history-source-inventory-v2/`：原失敗及完整盤點，含raw摘要／空內容的receipts、ingester source及SHA。
- `primary-identity-bridge-v1/`：獨立URL與工具返回節錄、限制；不是完整raw HTML或發布時計。

三份script原位於`/private/tmp/tennis-christian-source-repair-proposal-20261101.py`、`tennis-christian-match-closure-20261101.py`、`tennis-te-history-source-inventory-20261101.py`，均另存各自source.py；重播須使用新輸出目錄，live後續會變，不能把新資料倒填為舊結果。

今輪repo只改筆記；沿用已驗證相同source的e933c1cb完整gate（Tennis1121 passed，1630秒），沒有為文件重跑模型或改判決。研究／來源修補未完成，保存自己的非main研究分支，未release／activate。
