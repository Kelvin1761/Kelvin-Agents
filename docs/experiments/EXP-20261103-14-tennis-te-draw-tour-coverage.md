# EXP-20261103-14：TE 固定窗口來源覆蓋、draw／tour 缺口

採集／分析日期2026-11-03 UTC，悉尼已跨至11-04。接續[缺Elo全量診斷](../audits/tennis-missing-elo-inputs-20261103.md)及[統一計劃](../../tennis-research-execution-plan-20261028.md)。**本輪完成公開資料採集與輸入診斷；未改live資料、入口、模型或資格，未量度準確度。** 原十五個REJECT_DEV與tennis-v1不變。

## 固定範圍及取得的資料

保留同一55-card的40個缺Elo sides／39位球員，不按結果或有沒有找到資料縮小分母。窗口固定2026-10-01至11-02，只量來源／身份覆蓋，不選最有利回測窗。

先盤點外置`tennis-unified-20261028`研究目錄2422檔，未找到另外日期的TE結果HTML；這不是全機／全COLD語料審計。既有原文涵蓋10-31、11-01、11-02三日，11-01有兩個不同時間版本，全部保留。因此只新取10-01至10-30共30頁：串行、單次、最少2秒間距、每次30秒timeout、頁面4MiB／總64MiB上限，遇403／429／challenge停止。

30／30 HTTP200，未遇challenge，decoded HTML共17,754,629 bytes。每頁保留request／final URL、真正fetch UTC、decoded及gzip SHA256；沒有以賽果日期冒充取得時間。連同4個既有版本，共34個HTML版本／33個unique source days；原文selected-calendar日子34／34與requested day一致。日期一致不證明TE涵蓋當日所有比賽。

現役parser共返回**14,325個賽果版本、319個skipped版本**。11-01版本之間可有重複；不是14,325場獨立比賽、訓練標籤或forward樣本。任何後續訓練仍須按canonical match／來源身份／時間去重及審計。

## 全39人身份候選

用原有`player_name_score>=0.92`保留所有候選，再擷取候選涉及的全部32個公開球員頁；沒有挑最吻合的人或自動建立alias。32／32擷取成功，`table.plDetail`中的完整姓名／sex結構皆可讀。

| 固定39位球員的結果 | 人數 |
|---|---:|
| 有結果頁姓名候選 | 26 |
| 完全相同normalized結果頁姓名 | 0 |
| 候選只有一個profile URL | 22 |
| 候選涉及多個profile URL | 4 |
| 來源profile完整姓名token集合一致，且只有一個吻合profile | 23 |
| 未有完整姓名吻合profile | 16 |
| 原players.tour為UNKNOWN | 39 |
| 嚴格姓名＋已知tour資格／獨立ownership確認 | 0 |

23個完整姓名吻合比單憑縮寫強，但不是獨立ownership證明。現有players表沒有DOB／country可作第二個識別對照；全部39個tour未知，不是與來源相反的tour。不能把未知當一致，也不能直接改成ATP／WTA來製造合格紀錄。未找到候選的13位及另3位只有不吻合候選的球員，都不能推論「沒有歷史」。

已實際見到同surname＋initial候選的完整given name不同，原有0.95姓名分亦會誤指另一人；本輪沒有沿用這種分數自動合併。原始私人fixture／book payload未匯出；封存的target reference只含39位球員的公開姓名、ID、tour及這次reference capture時間，不能當舊forecast已知證據。

## 兩項可重現的入口缺陷

來源head links明文帶`/atp-men/`、`/wta-women/`及`?type=double`；雙打每邊是`/doubles-team/`連結，單打每邊是`/player/`。用同一source header、雙側相同context及對應side links核對，34版本內所有14,325個parsed results均可分流，無餘下unresolved draw。

| source所示類別 | 賽果版本 |
|---|---:|
| ATP單打 | 6,462 |
| WTA單打 | 5,321 |
| ATP雙打 | 1,397 |
| WTA雙打 | 1,145 |

**D01，draw資訊流失。** 現役`ParsedResult`沒有draw kind，`_store_history`無單雙打分流，會把含斜線的組合名稱當單一player name處理。此窗口2,542個雙打版本全部送往同一history迴圈；這是現役程式路徑與固定source比較，沒有真的入庫，不能稱2,542筆已污染live或量成受影響注單。

**T01，tour資訊流失。** 現役parser沒有保留head URL的tour，history呼叫`_tour_of(tournament_name,None)`從名稱猜。像Templeton ITF的原文URL明示`wta-women`，名稱卻不含WTA／W15等token，會落到ATP預設。14,325個版本內有6,215個現有推斷與source明示tour不符；只看11,783個單打版本，仍有**5,116個不符**。

兩個問題的來源語義已重現；尚未量舊history實際ownership、Elo影響或模型LL／Brier。雙打組合ID亦不必然污染個人Elo，不能將上述數量直接當個人評分錯誤。

## 修正前已固定的四臂工程比較

baseline為`6d3fd8c21883282d6490358979bcde4d2e289d3f`；frozen parser、name matcher逐byte與此commit一致，legacy `_tour_of`函數亦相同。候選尚未實作／測試／部署。

| arm | 新history draw政策 | tour政策 | 事前預期的分類層差異 |
|---|---|---|---|
| C | 現役全部parsed results | 現役名稱推斷 | 14,325版本，原基線 |
| D | 只接受source明示單打 | 現役名稱推斷 | 留11,783、扣起2,542；保留單打facts逐欄相同 |
| T | 現役全部parsed results | 保留source明示tour | 只改6,215個tour標籤；score／winner／name facts不變 |
| DT | source明示單打 | source明示tour | 留11,783；其中5,116個tour標籤改變 |

這些是**分類層**預期，不是實際stored rows、修好身份數或準確度。下一輪先以同一34份原文實作／驗證上述四臂；不縮小語料、不改表來救候選。T arm保留雙打只作隔離消融，不能上production。

實作及驗收邊界：

1. parser以optional metadata保留source tournament URL、tour、draw kind，既有比分／winner parsing保持不變；results／settlement consumers維持相同賽果facts，不藉history修正改settlement。
2. history入口只接受有完整source分類的個人單打；未知、相互矛盾、混合side或雙打明示留置及計數，不能fallback ATP、靠斜線猜人或靜靜丟行。保存raw receipt先於parse／guard的規則不變。
3. 解析成單打仍不等於身份合格。現有alias／canonical target若有已知相反tour，整場留置；UNKNOWN不當成一致，不自動改live player metadata或合併身份。完整store／hold row-flow另報，不能拿分類層數字充當入庫數。
4. 不重新連結舊summary，不改寫舊history／cache／predictions；舊資料修復要另過source-owned generation、event/knowledge cutoff、beforeimage／transaction／rollback合約。新原文的可用時間就是本輪實際取得時間。
5. 加真實source縮小fixture、明示男女單打／雙打、未知分類、header與side衝突、相反tour target及rerun的負例。完成同原文四臂及針對測試後跑repo quick/full，另經Central exact-scope gate，未驗收不部署。
6. 修正入口只是停止新增可疑輸入。待來源／身份generation合格，才依既有frozen規則量同語料時間folds、LL/Brier、校準及市場增量，再作Sportsbet獨立forward；不重開十五個REJECT_DEV或回填舊card資格。

其他莊家歷史odds／逐場結果及開發ROI繼續只按原協議作training／研究，不當獨立實力標籤；缺報價時鐘不當可執行ROI。

## 可重現證據及失敗記錄

外置包：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/source-coverage-window-v1-20261103/`，115檔／2,774,343 bytes，全部唯讀；`artifact_manifest.json` SHA256 **`ace4fb34d970f1f26c43291052a534216d64efb5d5dbd60b4205525f8d7ba0d1`**。只含公開TE結果／profile、公開player reference及本輪診斷，沒有live DB複本、私人fixture、價格、ledger或credentials。

`capture.py`／`capture_profiles.py`是已執行的一次性network採集，不能重抓後冒充原件。`analyse.py`、`check_content_dates.py`、`validate_profiles.py`、`audit_source_shapes.py`保存實際分析；live讀取均mode=ro／query_only、busy100ms／5秒SQL或transaction期限。

離線`replay.py <全新輸出目錄>`用封存的公開source、39-player reference及frozen parser／matcher，不讀DB或發網絡請求。用primary Tennis venv Python、`PYTHONDONTWRITEBYTECODE=1`實際跑完；counts、全部source frames、39-person cohort及156條candidate entries與原分析完整相同。`offline-parity-result.json`保存比較；原／離線結果SHA分別`2ab7f57a375b8b54f77b2a9c9f7637be17ca8cdfc6cdd6510107655da4ee23ee`及`96cd7499a6af14630154146bb68c06c40d4eaebbbefd7d1f03ff8e22734c8d67`，protocol時間／read timing差異不拿來冒充數值差異。

初版profile helper把sidebar的h3也算姓名，曾得到0個valid profile；改為只讀`table.plDetail`，保留原code／protocol／結果。初版draw helper錯估雙打用兩個個人profile links，曾將2,542個留作UNRESOLVED；按實際`doubles-team` DOM改正，保留原版本及修正原因。離線packager初次因查找錯loop字串失敗，當時未產生replay，原失敗原因／code保留；修正後才跑上述真正離線比較。沒有隱藏失敗或把helper修正當模型勝出。

本輪只交付資料證據及事前修正協議，沒有修改repo程式。最近同程式版本的完整檢查16 suites／Tennis1096已在上一輪完成；本輪文件保存另跑Central quick gate，不能稱新入口候選已過full或模型已改善。
