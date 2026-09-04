# AU 模型候選：production 啟用前檢查（2026-09-03）

> 已解決：用戶其後明確批准四線共用 production 對齊；2026-09-03 13:45:54
> Central 記錄 `6b97eea1808c` activation succeeded，四線實際版本與 main 一致。
> 下文保留原來問題及調查紀錄；最新結果見 `production-alignment-20260903.md`。

用戶已批准公開 commit／push／merge／automation。發佈使用 Central exact-scope 流程。
本報告只記已觀察的 production 狀態；不會改寫其檔案、HEAD、排程或管治規則。

## 現況

- Telegram 已於 Sydney 2026-09-03 09:53:26 批准 `6b97eea1808c`；09:53:28
  合併 main。09:53:31 activation 因四個 dirty paths 失敗；production SHA 完全未變，
  rollback 結果 `already_rolled_back`。原批准有效，毋須用戶重發。
- 真實四線 launchd plist 全部指向 `/Users/imac/wongchoi-scheduler`，已 loaded、aligned。
- Production HEAD：`dae33573ef18e1671f0a6d7c1bed11ceb9c902ba`。
- Main 基底：`165f923a1aa43a34f9ae0c1e2a1df0e328b6090e`。
- Production 使用舊 cherry-pick 歷史，並非 main 祖先；Central `_sync_checkout`
  的 fast-forward 條件不成立。兩者 96 個 committed 檔案不同，含 Tennis 模型／資料管線。
  不能把這當成只差本次 AU 27 檔、直接 reset 到 main。
- Production 有四個未保存的 operational source/test 改動：
  `au_daily_schedule.py`、`au_diagnose.py`、`tests/test_au_daily_schedule.py`、
  `sb_browser_fetch.py`。另有可變 runtime mapping `sb_archive_meeting_ids.json`。
- 本輪 09:00 Tennis card 工作曾處於 running，切換前須重新驗證已完成。

## 已做保護

完整五檔原內容、binary patch、HEAD、SHA256 清單只讀保存於
`/tmp/au-production-preservation-20260903/`。未重設或清理 production。
未保存 operational changes 的兩檔已與 main 相同，另兩檔不相同；不能直接全抹。

後續逐 hunk 核對：`au_daily_schedule.py` 的全部未提交修改可在 approved tree
reverse-apply；`au_diagnose.py`、`sb_browser_fetch.py` 整檔相同；production
`test_au_daily_schedule.py` 全部 bytes 是 approved test 的完整 prefix，後者只追加
Speedmap 測試。因此四個 hotfix 已被 main 包含，兩檔不相同不代表 hotfix 尚未整合。
保留現場及備份，未執行 `restore`／`reset`／切換 branch。

## 已批准版本與 production 的具體遷移範圍

目標：`6b97eea1808cbdfff9be16403a957ef952006c74`。
來源：`dae33573ef18e1671f0a6d7c1bed11ceb9c902ba` 加已保存五個 working files。
115 個 committed paths 不同：AU 23、Tennis 43、Dashboard 3、共用 5、
文件／實驗／生成說明 41。115 是完整版本差異，27 是本次 AU release 相對 main parent
的 scope，兩者不能混稱。逐檔 SHA256 清單：
`docs/handoff/au-production-reconciliation-20260903.json`。

Tennis 差異含實際行為：`bet_filter.py` 增加 tournament tier、缺排名、缺場地的
投注 gate；`surface_elo.py` 修正大小寫及 fallback；`probability_model.py`
增加缺排名／場地警告，並有 identity merge、ranking ingestion、settlement 等變更。
本輪 AU 評估不等於這些 Tennis 差異的獨立上線證據。

### 供獨立遷移審核的要求

1. 確認四線共用 checkout 的遷移範圍，逐項交代上述 Tennis 既有變更及其證據。
2. 保留完整舊 checkout、Git branch/history、五檔 hash/patch、installed plists 及
   runtime mapping；Tennis live DB、interpreter、logs 路徑必須固定。
3. 使用獨立、明確可審核的 production reconciliation release，提供來源 SHA、
   目標 SHA、預期檔案 hashes、回復程序及 smoke 結果；不能偽造 ancestry、
   改 mutable allowlist、繞過 Central 的 dirty／fast-forward gate。
4. 切換前重新確認沒有 domain run、資料庫 read-only quick-check、工作檔沒有
   concurrent changes；經批准的 migration 機制及 allowlisted installer 執行後，
   驗證實際 loaded plists、四線 Git SHA 及 AU scoring module hashes。
5. 任一步失敗，還原捕捉的 checkout/plists/runtime mapping；若有 concurrent
   source writes，停止 rollback 並列明衝突，不覆蓋他人工作。

現時並無已批准的 divergent-checkout 遷移機制可直接執行；這是新部署範圍，
不能用重發同一 AU approval 來解決。

## 本輪唯讀營運快照

四線 launchd loaded/aligned；AU evening succeeded、Tennis card succeeded、
HKJC recovery dormant、NBA pregame dormant。Registry 仍記 AU/HKJC production、
Tennis/NBA shadow，記錄 code SHA `8b149c85aafa`；這不是實際 checkout 最新 SHA
或本次 release 啟用證明。Dashboard configured，本輪未寫 D1／未 deploy。
D1 最近備份 local restore verified，WARM copy pending。HOT 可用約 20.8 GiB，
WARM available；catalog 的 5 個 COLD artifacts 已由 Google Drive 驗證。
這些營運資訊獨立於本次 activation failure，沒有在本輪改動它們。

## 必須解決的啟用條件

1. 把現有 production hotfix 與 main 的差異分開審核，保留尚未整合的行為。
2. 以可退回、經驗證的獨立變更修復兩邊歷史／版本對齊；不混入本次模型的已批准 scope。
3. 沒有 domain job 執行，production 沒有未批准 source dirty，才走 Central activation。
4. Central 的 immutable SHA approval 必須如實記錄批准來源；不得冒充 Telegram issuer。

本次 scoring 修正不會更改 Central 的 dirty／fast-forward／approval 保護條件。
