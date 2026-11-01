# EXP-20261102-03：隔離 history／Elo generation 實作

- **平台／日期**：Tennis，2026-11-02。
- **假設**：共用現役計算核心，能保全原 Elo 四路輸出；把 history、mapping 與衍生輸出固定成同一版本，可在實際切換時計之後才讀到修正，回退亦不倒填歷史知悉時間。
- **舊紀錄**：[EXP-20261101-27](EXP-20261101-27-tennis-source-owner-repair-readiness.md)、[EXP-20261102-02](EXP-20261102-02-tennis-identity-elo-cache.md)。原研究分支的 identity／last-recorded-clock prototypes 並非 runtime parity；本輪沒有宣稱把它們認證為正式來源。
- **baseline**：`2f262c0c5e43ac866973198c9ad183796ac0f752`，現役 legacy pre-match／shadow post-match 公式及 SQL eligibility/order 不變。
- **判定**：隔離工程實作；不接入 production feature reader，不改 live mapping/history，不是準確度候選。研究及 source qualification 未完成，先保存非 main 分支。

## 實作及邊界

`modelling/elo_replay.py` 從現役 builder 抽出同一段 chronological walk。builder 經 `read_elo_inputs` 保留原查詢及原順序，繼續使用原 legacy `INSERT OR IGNORE` 及 v2 shadow policy；沒有修正或提升現役 cache。

`research_elo_generations.py` 自行建立 `:memory:` connection，拒絕外部 connection、attached DB、caller 未完成 transaction；未增加 CLI／migration／ingester／feature-builder 入口。每個版本的 exact input、來源 receipt 聲明、mapping、model source digest、實際 available 時間、history opponent Elo、current player rating、legacy 及 shadow series 一起保存並有 hash／append-only trigger。建置不會切換；activate／rollback 都新增實際時間 event。相同 input 冪等；facts／mapping／reference／receipt／算法變動會建立新版本，不能抹走較晚 availability。

查詢先按 knowledge cutoff 選 activation，再按 event date 嚴格取較早 history／legacy rating。同一版本內只准 surface→overall fallback；沒有版本或 legacy rating 就缺值，不能改用 current player rating 或 v2。`snapshot_as_of` 是完整**診斷**快照，包含該 generation 全部事件，不可直接當歷史 feature matrix。

這是記憶體 JSON 快照 prototype，並非已完成可擴展、可部署的 indexed generation store。所有輸出固定標記 `UNQUALIFIED_RESEARCH_ONLY`；receipt hash 和有效時間格式不代表原文、身份或 PIT 已通過資格。也沒有驗證普通 production ingestion／merge 會沿用此版本機制；來源雙側／beforeimage／完整 alias 合約仍須正式 apply 前獨立驗證。

## 全量新舊核心對照

沿用 EXP02 同一 frozen DB SHA `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`，401046筆三來源history、20372名players、200389個ACTIVE winner rows。四臂：未修正cold、相同輸入warm control、固定八行身份假設修正warm、修正cold；不使用holdout／新權重／新切法。

candidate 的三份完整四路投影（未修正cold、修正warm、修正cold）與上一輪原算法輸出逐byte完全相同；unchanged warm control亦全數相同。每份包含legacy／v2、current player與history opponent Elo；不是只比summary或抽樣。最後只刪掉builder多餘EOF空行，最終兩個計算source的AST與已跑全量parity候選相同。

證據根 `kernel-f02-rules-20261101/elo-replay-refactor-parity-v1/`：protocol內有dirty候選source SHA、原builder／新builder／新核心、四臂DB及投影、逐byte parity結果、script。manifest SHA `23e2100303a884bb8c55b05b3dcbe02431f85df604722ddcd2bd4a435b259d52`。工作DB約252MB，開始檢查內置空間>10GB；完成複製外置碟後刪除本機工作DB。

## 公開 cluster 實際時間整合

同 EXP02 的90 perspectives／45場／42 players。只假設改八行身份2110→19626及兩個來源mapping；canonical event keys／正式 supersession 仍未改，不可拿這份假設資料做正式 apply。每組winner order由實際native SQL reader產生，不另寫研究排序。

- old／corrected generation 四路投影，分別與原算法對應cold輸出完全一致。
- 修正未activate時仍見old；修正前一微秒仍讀old及舊身份；修正後19626有四場。
- 真實三個generation／四個activation event（初始、修正、reference refresh、rollback），全部實際時間為2026-11-01 14:58:26 UTC內不同microseconds，沒有改成賽日。
- refresh不倒填舊availability；invalid winner order失敗不改active version；rollback保留中間修正版的歷史視圖。
- 2025 cutoff沒有任何已activate版本，history/Elo不可用；沒有利用今日資料重建假的2025 feature。

`elo-generation-public-cluster-v1/`保存公開input、owned memory store匯出、protocol／result／source；manifest SHA `10a878942d0fdb9f0d66ebfeda9c9175f8df50c752c8e4e1c466f15e38482a8c`。raw receipt 是**本輪衍生normalized projection**，不是原網站wire source，不追認來源資格。沒有匯出fixture、market、prediction、ledger或私人原文。

## 身份來源補強

[UTS主頁44614](https://www.ultimatetennisstatistics.com/playerProfile?playerId=44614) HTTP200、18644 bytes，actual fetch `2026-11-01T15:01:35.483302+00:00`，body SHA `2d157477dc9968304fc35f9aa3db6860076bc51b5e9f6b71674ec0db3dff7a72`，顯示Christian Sigsgaard。頁面明示的[profile tab](https://www.ultimatetennisstatistics.com/playerProfileTab?playerId=44614) HTTP200、3784 bytes，actual fetch `15:03:24.041550+00:00`、SHA `6f4e3472bc476865f5c6794fb379d14b7c084994268469a437d8dbb007e6300f`，列丹麥及DOB 14-03-1997；與EXP02已保存[丹麥總會](https://tennis.dk/nyheder-presse/davis-cup/)DOB一致。初版flags只找ISO日期而報`has_dob=false`，是字串格式差異；已直接核對保存HTML，不把flag當沒有DOB。

既有bounded公開capture中target19626全名Christian Sigsgaard、ATP、canonical pointer空，provider registry為`composite/uts:44614`及`atp_pdf:christian-sigsgaard`；只見Jumpei alias→2110，不能把它搬走。上述補強特定target namespace／出生日期，但尚未重驗live beforeimage及完整影響範圍，亦未得到第四場ATP官方成功HTTP原文receipt。UTS頁面的ranking updated日期不等同profile資訊在當時已知；本輪一律沿用實際fetch時計。

`uts-identity-binding-v1/`及`v2/`保存protocol、原HTML gzip、HTTP／hash metadata和script；manifest分別`88804c23d083a749b5d3f253eb0adc51e792c795379053f4fb4bc28aa72aed3d`、`f0be2f9291de56a6ccd101e3bde18da45e97b2568f71c531d000090e0f4e1b32`。web reader無法open tab，direct公開HTTP成功；沒有繞過登入／challenge。另以table cell解析DOB及Country、核對parent明示tab連結、三份raw body SHA及bounded provider registry，產生`uts-identity-binding-review-v1/`：判定`BOUNDED_TARGET_NAME_COUNTRY_DOB_SUPPORTED`，manifest SHA `e5fa244ea4fe3d264920d0bca2bf2dfdeab72597328f0e60383abe7c9ef0b9a2`。此判定只限已capture的target，不表示所有source pairs、live beforeimage、歷史PIT或分析準確度已通過。

## 測試、洩漏及下一步

34個新generation測試加13個既有Elo測試，共47 passed。涵蓋雙時計、同日首筆legacy／末筆shadow、共同對手後續影響、失敗建置及SQL插入、時鐘倒退、append-only、hash損壞、refresh、caller物件變動、外部／attached／unnamed temporary disk（即使journal=MEMORY）及caller transaction拒絕。最初一項synthetic test把球員賽前／賽後場數誤寫3／5；按fixture實際兩場改為2／4後通過，沒有改算法或參數來遷就測試。

`./檢查.sh --quick`及完整`./檢查.sh`均exit0；16個suite全部通過，unit suites797秒，Tennis1114 passed（23.48秒）。檢查後沒有再改程式，僅補上文件的實際測試結果。34項測試不是完整production ingestion／merge／feature-reader接線測試，不能把執行合約第4步整體勾完。

| 資訊 | 可用時間證據 | 判決 |
|---|---|---|
| 本輪版本切換／回退 | 實際UTC activation event及前一微秒測試 | memory機制通過 |
| 舊history／identity的歷史發布時計 | 本輪新projection／profile receipt不能證明舊決策前已知 | FLAG；不可當historical PIT |
| snapshot內後於event cutoff的賽果 | 只能用filtered history／legacy accessor；完整snapshot僅診斷 | 未接production，不能直接作features |
| 原current Elo／shadow v2 | 缺legacy時不採用；原production reader仍待接線 | 隔離測試通過，native未完成 |

下一步：依[generation執行合約](../plans/tennis-identity-elo-generation-20261102.md)完成persistent indexed generation／來源beforeimage及native reader／ingestion接線，然後才可正式資料apply及預先登記準確度實驗。**LL、Brier、accuracy、ROI均未測；十五個REJECT_DEV及frozen ruler不變。**

## 重播

外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/`。在本輪source版本repo root，以 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python <artifact>/source.py` 跑對應script；重播先改全新OUT／local DB路徑，不覆蓋原件。公開HTTP頁面可變；重抓不等同原receipt重播。
