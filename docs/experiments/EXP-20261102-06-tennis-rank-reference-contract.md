# EXP-20261102-06：排名附加說明與既有 evidence point 格式接線

工程修正協議，2026-11-02；baseline `0bfb69022a145a33990f63edb5c0a8b63d88691d`。搜尋過EXP-20261101-21、EXP-20261102-01至05及ranking date tests；不重試十五個REJECT_DEV、不改frozen ruler或v3 consumer。

## 直接觀察與固定修正範圍

113場2026-11-02 current fixture唯讀診斷：112 assemble/pricing、1 DISPUTED拒絕；初始109 ACTIVE、3 NOT_LISTED、1 DISPUTED。45場開始時計在audit之後、12已開始、56 unknown；不是新forward。當中13場component point contract通過、3場連decision/raw binding也通過；全部112個snapshot data_quality invalid，無prediction／下注／accuracy結果。75場有missing_surface、20場有elo_not_as_of／rank_seed（可重疊），不因此放寬資格。

producer為current_rank.provenance新增ranking_date、ranking_source_origin、ranking_date_kind及可選ranking_selection_diagnostics。既有evidence writer及shared consumer嚴格要求原六欄，故附加說明本身會令原point無法通過格式檢查。第一輪診斷的分支code及預設env不冒充production runtime；後續配對會明示載入launchd指向的TENNIS_ENV_FILE，僅保存非敏感設定hash。

固定修正：在**新feature assembly、pricing之前**，將上述四個附加說明無損移到player的ranking_reference sibling，原point仍保留value及原六欄provenance；warnings、raw ID、source/provider/endpoint與兩時計不變。不改嚴格validator，不刪警告，不重寫舊canonical snapshots。freshness須同時讀legacy provenance與新reference，effective date的語義／penalty保持原樣。只有完整／格式正確且不晚於match day的reference才搬移；無效／未來日期留在原point讓原validator繼續拒絕。未知provenance extra亦保留拒絕；reference衝突直接停止。

## 事前驗收

1. Synthetic active rank component：原格式因extra keys被原writer拒絕；新producer格式通過**未修改**writer及shared v3 projector；所需raw與原六欄一致。警告、未來source/calculation、wrong raw binding及unknown extra仍拒絕。
2. 全113個current fixture逐一保留去向；每個可組裝snapshot只build一次作兩臂，candidate為純記憶體格式轉換。逆轉換須與baseline完整相等；定價全份、數值、警告及固定同一clock重算的data_quality全部相等。全批報告，不選通過subset，不mint prediction ID。
3. 新舊reference同effective date的freshness完全一致，包括stale publication、backfill、invalid date及diagnostics；不改閾值或rank selection。source body及private snapshot只在記憶體，輸出只ID／狀態／hash／error taxonomy。
4. 針對測試、quick及所需系統權限的full gate。未通過不交付。此修正只恢復既有point介面，不是模型改善或新的qualified forward；後續來源／歷史身份／價格／完整card條件仍獨立成立。

## 實際全批配對

第一輪原生診斷及script保存在`/private/tmp/tennis-current-preflight-20261102/`；配對及script在`/private/tmp/tennis-rank-reference-pair-20261102/`。外置封存：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/rank-reference-contract-v1/`，`measurement_manifest.json`綁13個檔案，SHA256 `f9552747700290ff7736a8fc48c3915c9b7c0b87ec49b9972ffb6aff9857b2ad`。

兩者只輸出ID／狀態／hash／error taxonomy，私人features、odds和raw body均只在記憶體。故這是當刻memory pair，不是可從hash復原完整私人input的歷史runtime replay；重跑script會讀當時DB現況，不能冒稱同一歷史輸入。跨producer／consumer的synthetic測試則可完整重現。

以launchd四份tennis plist實際指向的`/Users/imac/Antigravity-repo/tennis-wong-choi/.env`載入設定；不保存env檔或任何key，只記相關非敏感設定hash。這是研究分支的native memory pair，不冒充完整B_live runtime replay。

鎖定原113個ID，配對開始時沒有新增fixture漏出cohort。112對成功，1個DISPUTED仍拒絕。197份player rank annotations搬移；**全部112對inverse完整相等、pricing整份相等、固定同一實際clock重算quality相等**。沒有改ranking、model probability、warning、source/body引用或時鐘。

| 必要格式條件（不是qualified samples） | control | candidate |
|---|---:|---:|
| component contract通過 | 13 | 22 |
| components＋decision inputs＋complete pricing＋raw binding全部通過 | 3 | 6 |
| data_quality valid | 0 | 0 |
| 實際寫入prediction／qualified forward | 0 | 0 |

原9個`player_a.current_rank`格式拒絕不再是first blocker；76個active warning及14個incomplete component set不變。兩臂同樣有14個unique raw ID的logical body為空，沒有透過新namespace偽造原文或追認舊來源。那些header仍存在，不等於body可驗證；live資料／舊canonical未改。

quality同樣失敗的直接理由：59個snapshot欠兩邊market point（118個error occurrences），另53個snapshot在audit當刻價格已stale。全source診斷包含非Sportsbet card／NOT_LISTED記錄，不能將59場當成正式Sportsbet card缺價；亦未刷新網絡價格，不能單憑這次盤點判排程故障或調寬TTL。6個格式通過亦不當作forward、訓練子集或成效樣本。

## 測試狀態

新增16項測試及相關stage5／ranking／indexed regression共82項通過。包括未修改writer＋shared v3 projector的完整synthetic roundtrip、保留完整annotations、無副作用與冪等、warning／future timestamp／wrong raw／unknown extra／invalid或future reference繼續拒絕、legacy與新reference freshness相同，以及mock provider全feature assembly實際接線。

初次quick捉到新增測試fixture import與參數撞名的F811；修正為獨立mock bootstrap，亦移除對未合併indexed fixture的依賴。當時完整run已無法通過，核對其cwd／stdout log後終止該process group，exit143，保留log且不當PASS。

修正後82 targeted及quick皆通過；最終所需系統權限的完整`./檢查.sh` **exit0、16 suites全過、unit suites1033秒、Tennis1166 passed／27.03秒**。4個最終程式／測試檔封存前再核對hash；writer、shared v3 reader及frozen tennis-v1三檔與baseline逐byte相同。完整gate之後只補文件結果，沒有再改code或tests。

同一外置根`artifact_manifest.json`綁20檔，SHA256 `6e9850babd37cd681edae171e54d98c545067b0fdcf85bf053f4e12dad1fc1be`。`validation-v1/`保留82 targeted、failed／fixed quick、stopped full、最終full及source freeze／unchanged guards proof；既有measurement manifest及所有資料均只讀封存。

此修正恢復既有介面，不是更改frozen v3 validator／ruler，也沒有準確度判決。下一步先作乾淨main隔離交付及actual run驗證，之後才處理來源／完整card／fresh evidence與新實驗。
