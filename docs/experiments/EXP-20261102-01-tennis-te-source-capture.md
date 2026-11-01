# EXP-20261102-01：TennisExplorer history 按日保留原文

工程來源修正；不是模型／準確度候選。正式 full gate、merge／activation 狀態以 immutable release manifest 為準；本報告不代替 production run health 證明。

## 問題及修改

先前完整 frozen 盤點的240146行TE history，232766行的logical raw body已空，7380行只連summary。原ingester每次backfill先存一份summary，再fetch／parse多個日子，沒有保存真正scoreboard。前置proposal及完整限制保存在研究分支的[EXP-20261101-44](https://github.com/Kelvin1761/Kelvin-Agents/blob/53d2613b784ededa5fef3cdcc5dfccbd1d316967/docs/experiments/EXP-20261101-44-tennis-source-split-and-te-retention.md)；本次不把該分支未完成的身份工具一併發佈。

`TennisExplorerResultsProvider.fetch_results_page_for_date` 現在回傳 `ResultsPage`：request date／URL、實際fetch後UTC時計及精確decoded HTML。既有 `fetch_results_for_date` 仍用原parser返回同一results tuple，沒有改比分／winner parsing。

history ingester每個日期先獨立存raw receipt，再validate source metadata、parse及寫history。receipt包括 `format=tennisexplorer-results-html-v1`、HTML的UTF-8 SHA、URL及source fetch時刻；raw_api_responses本身的fetched_at仍是store時刻。兩者不冒充賽事時間、發布時間或過去已知。這是decoded text，沒有宣稱保存壓縮傳輸層wire bytes或redirect final URL。

- parse或後續history寫入失敗，已commit的原文仍保留；errors列出date、phase及已有raw ID。
- source存檔失敗，不進入parser／history寫入。
- date／request URL／timezone／future clock／空HTML不符，先保留所回傳receipt，再停止該日history寫入。
- 空賽日有非空原page時照保存；parser原有skipped規則不變。
- 只提供ParsedResult、沒有原文的custom provider不能冒充raw來源，history入口會報fetch錯誤；如要注入provider，須提供ResultsPage API。其他results-only API caller不因此新增DB寫入。

page metadata正確不等於所有賽果／人物身份已獨立認證，也不會因保存HTML就解除所有source warning。本次沒有改TennisExplorer settlement入口、fixture配對、Elo公式／權重、正式source資格或模型ruler。

## 針對測試

28個TE parser／history／source測試通過（其中15個新source測試）：跨日raw IDs與history link、完整Unicode HTML及SHA、parse失敗繼續下一日、store失敗停止、source metadata錯誤、缺source custom provider、空日、results API一致、history寫入失敗仍留原文，以及無損retention後accessor逐byte還原。原有canonical reuse及較低級別Elo測試保留。

相同HTML的合成baseline／candidate比較亦核對雙側facts、player IDs、Elo數值及完整Elo v2表。

## 公開頁面隔離對照

只下載全新公開HTTPS結果頁，沒有開啟live DB，也沒有匯出內部fixture／投注payload：

| URL／requested day | 實際fetch UTC | parser matches／skipped | decoded bytes |
|---|---|---:|---:|
| [2026-10-31](https://www.tennisexplorer.com/results/?type=all&year=2026&month=10&day=31) | 2026-11-01 12:59:34 | 235／6 | 396749 |
| [2026-11-01](https://www.tennisexplorer.com/results/?type=all&year=2026&month=11&day=01) | 2026-11-01 12:59:36 | 76／3 | 477892 |

頁面可隨時更新；以上只指已保存的固定HTML。以`37c4d8f4`原parser／ingester作baseline，candidate與它使用**同一份已擷取HTML**，各自初始化一個全新隔離SQLite，強制核對DATABASE_URL目的地，再重算Elo：

| 項目 | baseline | candidate |
|---|---:|---:|
| matches／雙側history | 311／622 | 311／622 |
| players created | 522 | 522 |
| parse skipped／errors | 9／0 | 9／0 |
| 按日source receipts | 1份summary | 2份HTML |
| 舊版Elo實際序列行 | 592 | 592 |
| Elo v2實際序列行 | 592 | 592 |

parsed results逐欄相同，history／players的數值與身份投影相同，兩版Elo序列亦相同；Elo v2的player/date/surface/rating/matches_played五欄全數比較。builder summary的622次v2寫入不是592個最終唯一rows，沒有混用兩種數字。raw IDs／capture timestamp等來源metadata本來預期不同，未拿它們作數值差異。

兩份真實HTML receipt再在記憶體跑現有無損retention，inline JSON共990504 bytes，新增gzip blobs80652 bytes，原文逐byte還原通過。這是logical UTF-8／blob大小，不是filesystem淨釋放空間。

HTML首次擷取時間就是本輪實際時間；**沒有把它回填成10-31或11-01較早時刻已知**，亦不是實際舊prediction重建、untouched forward或準確度比較。

## 舊資料及後續限制

既有upsert遇到相同facts會保留原history raw ID；重新抓到HTML不會自動替舊summary行改來源或追認舊資格，測試明確鎖住此行為。若要新增source confirmation／generation，必須另外保存其實際可用時鐘，不能藉此倒填舊回測。

這次停止未來history原文繼續流失，不恢復舊空body，不解決所有canonical身份／Elo lineage、main-tour serve輸入或整批feature證據。15個REJECT_DEV及frozen ruler維持，**未量LL／Brier／accuracy／ROI，沒有宣稱預測改善**。

## 可重現證據

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/te-source-capture-20261101/`。

- `public-parity-v1/`：執行前protocol、原public HTML gzip／SHA與fetch metadata、37c4d8f4 baseline source、candidate source、兩個隔離DB、完整比較projection／result及manifest。
- `v2-retention-check-v1/`：只讀前件DB，補驗592行Elo v2與兩份原文retention；未重抓網站、未改原隔離DB。
- `/private/tmp/tennis-te-source-public-smoke-20261101.py`、`tennis-te-source-v2-retention-check-20261101.py` 原執行script已另存各artifact source.py。於乾淨worktree根，用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python <script>`；重播改為全新輸出目錄。下載新page不能冒充原件重播。

public HTML SHA：10-31 `c6a22510db0373f4b6730e1ef936b58cde3fbefabe3097c3da4cd4e3257982a0`；11-01 `98ce33842a2d2844d34d40c185771965eff60d2bffe02c60132e3b5eec62fa06`。public-parity manifest SHA `dec00b524af0e2e05cb9a1d04aff8881fdb69c31895a6c11896750af4e0c4cbc`。

`./檢查.sh --quick`已通過。正式full／release必須完成才交付；預期影響只限可追溯來源保存與失敗證據，運行效果及下一批實際receipt仍需按部署後證據驗證。

## 正式交付核對

`41cad292cede34a6e3797cbeac80ba8e08b90968` 的 single-clean full gate通過（855.387秒，unit suites851秒、Tennis1080 passed），已確認在origin/main；2026-11-01 13:33:27 UTC的append-only event為`activation_succeeded`。Tennis runtime `/Users/imac/wongchoi-scheduler` HEAD及兩個修改source檔逐byte相同，新ResultsPage API亦從runtime路徑成功import。

immutable初始manifest：`/Users/imac/WongChoiData/WongChoiControl/releases/wc-release%3A41cad292cede%3A2026-11-01T133312.937821_0000.json`。其初始status是pushed／activation not_started，不能單靠該靜態值判最終結果；最終merged／activation_succeeded事件在同release ID的`release-events/`，未改寫原manifest。測試／manifest／events另存外置證據根`release-41cad292cede/`。

這只證明工程交付及已安裝code對齊，未宣稱部署後已實際擷取第一批新receipt、四線run health或模型準確度改善。後續仍須核實實際run及處理舊identity／Elo lineage。
