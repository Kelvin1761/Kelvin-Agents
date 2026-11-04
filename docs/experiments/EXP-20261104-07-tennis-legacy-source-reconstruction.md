# EXP-20261104-07：304日來源重建及 legacy 全量對照

2026-11-04。**公開來源／遷移研究，未 apply、未部署、未量準確度**。承接 [EXP-06](EXP-20261104-06-tennis-source-actor-guard.md) 的正式庫零 binding 問題；本次完整範圍不是替換原33日實驗或擴大模型評估窗。

## 全期來源與 beforeimage

固定正式庫全部 ACTIVE TE history 的304個 calendar dates：2026-01-01至11-02，244088行／19189位球員。只讀連線採 ro、query_only、100ms busy及5秒進度期限；按5000行分頁，關閉連線後才寫外置檔。只輸出明確白名單的公開 normalized history／player labels，沒有複製私人 fixture、odds、原始 book body、prediction、ledger 或財務庫。

兩次完整按ID排序讀取均244088行，SHA256同為 `bf2df6c220474243a2e647b749ea4d3780c043ef65ee78d6e6ad4ca4e565a94b`；最長連線第一遍0.937秒、第二遍0.429秒。這證明兩次所讀白名單內容一致，**不是整個業務庫的原子snapshot，也不是已驗證來源身份**。舊姓名、tour、merge pointer只當 beforeimage。

304日公開來源全部成功：33日沿用先前已封存的完整日原文及其實際fetch clocks；其餘271日逐日一次GET、2秒間隔、30秒timeout。沒有重試、縮減日期或替換失敗頁，沒有403／429／challenge。新取得 decoded bytes共148744001；每頁原文、URL、hash及實際UTC保存。selected calendar link逐日相符，但不宣稱它等於每場實際開始時間或完整賽事coverage。

全期 parsed 123098個賽果版本、2380個 parse skipped、148個帶 classification warnings。所有原始版本保留，不把這些數量當成可用訓練或獨立比賽數。

## 預先固定的圖與對照規則

來源圖協議 SHA256 `81d51a3a61c0be900f30fdef32edc5c6316913082e862257faa2155586f64728`；legacy對照協議 `73eb1a80f63c6ee7313cc52a640cb9f992e0c6f9109e20467151b47eeadd4b1a`。執行前固定 actor helper及name normalizer bytes，parser hash亦固定；SQLite連線在離線腳本明確禁用。

來源版本先保留分類留置，再以穩定 event ref／actor ref 建圖。跨calendar、不同pair／score／tour、同fixture-score有多個event ID、同actor跨tour、同event任何blocked source版本，都留置，不挑一個有利版本。方向倒轉比分正規化、相同actor及外站actor拒絕的synthetic核對通過。

逐一對照全部244088舊行，用既有日期／姓名reference只找來源線索；無或多版本、tour／role／date不符、雙打、分類／圖留置、merge pointer、非雙側互反，以及一個舊ID對多個source actors或一個actor對多個舊IDs，都列明。**reference吻合不是獨立全域identity proof；即使零留置也不自動批准mapping**。本白名單沒有舊score，因此不聲稱逐分parity。

## 全量結果及審計更正

來源圖完成於2026-11-04T02:15:01 UTC：101559個通過入口分類的單打版本／event refs、13198個來源 actor refs。24個event refs涉及同fixture／score的不同ID，全部留置；101535個event refs無本圖所列衝突。沒有觀察到已過入口的actor跨tour；27個actor有多種display label。**actor ref數不是獨立真人數；圖無衝突亦不是全域ownership資格**。

第一版legacy審計錯將 `(calendar_day, NULL canonical_event_key)` 當配對key，造成236850行被誤標pair failure。核對現役schema／原始白名單後，已明示撤回這個數字及v1的2812行零留置估計，原程式／結果保留為 `REJECT_AUDIT_GROUPING`。

v2事前修訂協議 SHA256 `0f02b1917a87d01e51a4e3d57a5d63182456e151755f26c8d6542b2d1a732247`：非空canonical key照用，legacy空key改用原source／provider reference，只剝末尾winner／loser；另要求一勝一負、缺counterpart來源雙側留置，並將對手的混合／split actor狀態傳回當行。同一份244088舊行／304日來源／所有模型規則沒有更換，沒有用審計修正救模型候選。

| v2全部244088行 | 行數 |
|---|---:|
| 唯一姓名reference來源線索 | 241120 |
| 沒有來源reference吻合 | 2942 |
| 一個reference有多個來源版本 | 26 |
| 對到雙打來源 | 42090 |
| stored tour與來源tour不同 | 95583 |
| legacy配對未滿足兩行互反及一勝一負 | 28 |
| 沒有本次reconciliation留置 | 82614 |

後四列及其他留置可重疊，不能相加當獨立受影響行數。tour不符中78997行來源為單打、16586行為雙打；不將全部tour差異歸因同一個bug。12856個舊player ID取得單打source線索，其中527個連到多個actor refs；522個source actor refs連到多個舊IDs。這是需要核實的多對多連結，**未證明每個不同URI都是不同真人，亦不能直接merge或搬history**。

來源圖及兩版對照均terminal exit0；退出成功只代表腳本跑完。v1錯誤結論仍然撤回，v2零留置82614行仍不等於身份已批准或可用訓練樣本。來源圖0個owner assignments、v2亦0，正式寫入0。

## 尚未完成的資格

完整公開來源並不代表 legacy migration、來源ownership、actual match timing、Elo generation或PIT訓練資格完成。新原文的knowledge clock維持實際取得時間，不能倒填舊forecast；原prediction／ledger及正式資料未改。後續仍須雙側beforeimage closure、所有對手依賴及四份Elo輸出同generation、原子切換／rollback，以及獨立準確度評估。

本輪研究 checkpoint 保存於 `codex-tennis-source-owner-guard-20261104`；十五個 REJECT_DEV、frozen tennis-v1及Sportsbet forward規則不變。

## 封存位置

共同根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `te-legacy-public-beforeimage-v1-20261104/`：7個payload檔／107036113 bytes，manifest `0165b5f9f74bef941cd0b2dad7bc1eff51ff39fd4115b6ab40af43aafbc180ee`。
- `te-legacy-source-reconstruction-v1-20261104/`：310個payload檔／14670512 bytes，manifest `85794c03394ac357c5c94044d1130a9169110c55eea561f1afba716ee2726056`。
- `te-legacy-source-graph-v1-20261104/`：11檔／127894588 bytes，manifest `1be3b6aabed1a2fb08a0e744c2f09c8b27a27fddb08946a8cf19065f41637888`。
- `te-legacy-source-reconciliation-v1-20261104/`：11檔／138602518 bytes，manifest `f7db479a9e46147bb17ebf42b0da2fe355d370693211dbce18ec3e11eccd9f38`；含撤回狀態，不能引用其pair failure／零留置估計。
- `te-legacy-source-reconciliation-v2-20261104/`：10檔／135657700 bytes，manifest `bcf4363f1e7b8fa053c1a537d5722f0fd3d3ec8fd5ca7ec62ebed3eb884552d3`。

全部在結果完成及terminal exit0後雜湊／唯讀封存；重播須新輸出目錄，不覆蓋原失敗。後續先按全部多對多群組及28行配對問題做來源核實，再建立隔離source-owned generation；不要將82614行挑成新accuracy cohort。
