# EXP-20261104-05：全39人來源事件核對及兩人 binding proposal

2026-11-04 Sydney。來源身份研究，**未批准任何binding、未改live資料、未新增合格forward、未量準確度**。原39人及整批card資格保持；不是挑出兩人作新的模型評估cohort。

## 完整來源範圍

沿既有32份公開profile原文，全部核對upcoming區塊。v1錯誤預期actor profile links，v2只認td而真實Match欄為th，兩版各留下19個unresolved，沒有當成「無數據」。v3同時認td／th：14個profile有15條賽事詳情reference、合共14個獨立ID；13頁明示No upcoming matches，5頁仍未解。三版原文來源、程式及結果均保留。

對全部14個公開詳情URL一次GET、逐頁2秒限速／30秒timeout，HTTP200共14，實際取得2026-11-04T00:15:37至00:16:39 UTC。無私人資料用於請求；保存公開HTML、URL／UTC／hash。網頁工具先出cache miss，再用限速HTTP取得原文，未執行外部程式或頁面script。

## 事件核對與時間更正

同一份60筆normalized book原文只留記憶體，SQLite讀取ro／query_only／100ms busy／5秒deadline；比對後只輸出公開ID、source URL、hash、counts及flags。原immutable receipt26353取得2026-11-02T22:22:17 UTC，hash `20b522cb8ef3883892ced9d57c149ce174326df388560008f050702a749e6ca9`；foreign receipt26492仍不當book使用。v2按原capture時計及hash唯一重取原receipt，避免current player pointer移動便換輸入。

雙側都要求完整姓名token multiset精確吻合（至少兩個、不能initial）、唯一source pair、日期及明示tour；沒有fuzzy／新增容忍窗。v1只對calendar date得3場候選／4個target，但stdout的coverage誤把defaultdict空key也計入而印39；原result逐人狀態實際只覆蓋13，v2已修正，原錯誤保留。

公開頁面明示GMT+1及顯示時鐘。v2只有在時鐘與實際fetched_at相差不超過120秒時才解讀Today，並換成UTC；同時只認h1之後、第一個h2前的primary table，排除某頁稍後另一場比賽的table。這是實際來源格式證據，沒有猜timezone或放寬時間窗。

| 全14份詳情 | 數量 |
|---|---:|
| 沒有完整雙側book pair | 8 |
| pair／日期／tour相符，但UTC start不同 | 2 |
| 完整pair／日期／tour／精確UTC start候選 | 1 |
| 來源仍未能完整確認 | 3 |

精確候選為[公開詳情3365751](https://www.tennisexplorer.com/match-detail/?id=3365751)，UTC start為2026-11-03T02:30。來源actors為`/player/miroshnichenko-94494/`及`/player/zhytelna/`，涉及原公開target21247／1865。原日期候選的22856／26282因時間不一致保留未確認，沒有用最佳容忍值救回。只在目前已捕捉來源範圍唯一，不宣稱全世界identity uniqueness。

## 具體beforeimage／proposal

只讀保存上述兩人的public player欄位、provider mappings／aliases beforeimages及digest，既有source key碰撞0、history角色行0／0；兩人的當前tour仍UNKNOWN。Proposal綁雙側公開event原文hash及book receipt hash，**PROPOSED_NOT_APPROVED**，沒有寫provider mapping、history、cache或merge pointer。

下一步用穩定source actor URL驗namespace，不能用姓名導出的book key或首字母＋姓氏充當來源身份。任何apply須先核對精確beforeimage、雙側closure、來源／knowledge clocks、generation及rollback；時間只可由真正驗證／啟用起生效，不倒填舊賽日前。原37位未有此精確事件證據的人沒有被刪出名單。

## 封存

共同根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `event-identity-crosscheck-v1-20261104/`：43檔／406253 bytes，manifest `dffc91bf979482e6d05d00fa135bc95f744d18e301bb98b53238e89950c55665`。包括三版upcoming盤點、14份公開HTML、兩版同事件比對及計數／時間修正；私人body／fixture／DB沒有匯出。
- `book-tour-owner-rejection-v1-20261104/`：16檔／118489 bytes，manifest `c1e014bd485b79c7ac2984009e1c4563bd306bc4924ca987e7da42656c3ebf2c`。反例、公開profile proof、兩人beforeimages／proposal、候選取消、Central拒絕及未部署核對均保留。初次封存因驗證helper預期event名稱`rejected`而失敗；修正為Central實際schema的`approval_rejected`後核對，沒有放寬source／SHA／ancestry條件。

重跑需新輸出目錄，先驗所有公開manifest和原private receipt的hash；私人source仍只准在記憶體。新public頁的取得時鐘晚於原forecast，不能回填為原先已知；事件吻合亦不取代Elo generation資格及獨立模型驗證。

原核對使用研究commit `b7a7cc32cceb090875d51e4ea6c0031b34370e63` 的book classifier、name normalizer及start-time helper；其中明示tour解讀未部署。重播必須使用同SHA的隔離checkout／相同source bytes，再調整腳本的source root，不能用main舊prefix路徑重跑後當成同一個結果。原生對照的實際source亦在EXP-04候選封存包保留。

這兩人是另一份prospective source-binding proposal，不取代原Sigsgaard四場／八行的修補範圍，兩條假設及baseline分開。下一個入口修正先驗：相同首字母／姓氏但不同source actor不得接入；穩定source ref須優先；legacy未綁定actor明示留置；新actor、既有binding及雙側失敗都要核對。未完成前不重試原tour-only release。
