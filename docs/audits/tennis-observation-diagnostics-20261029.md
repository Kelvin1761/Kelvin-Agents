# Tennis：研究投影被拒絕後遺失當時輸入

2026-10-29 Sydney；統一研究F00來源問題跟進。**呢個係診斷保存修正，唔係模型準確度改善或資格規則變更。** 原15個研究候選保持拒絕，現役model release仍係shadow `8b149c85aafa`。

最新證據同較早研究snapshot有分別：10月29日09:00 same-day card成功，45場已分析並部署；10月28日晚next-day因零價／來源不足失敗。不能再將「今日每日板仍缺失」當持續故障。另有rankings_atp、history_lowtier來源錯誤及WTA serve profile過期，未因本修正解決。

Canonical feature verifier重新實跑：121份prediction records、119個verified bundles、**0份feature projection／0個qualified predictions**。已安裝Tennis launchd均loaded；本次檢視runtime／主checkout SHA同為`ffdc47d047994c4765e4ae4732bb58e33f9e3338`。診斷只讀實際DB及native紀錄，冇改舊snapshot／ledger。

## 原因及重現

今朝canonical `Tennis_Research_Status_2026-10-29.json`記錄prediction15853被`active Tennis component has unresolved warnings`拒絕。其保存pricing顯示surface Elo有`missing_surface`，概率.5739756899806522；Toray Pan Pacific metadata目前surface空白，兩個Elo component均用overall值。呢個警告有實質影響，來源閘拒絕係正確行為。

`_record_daily_evidence`已有exact in-memory observations及引用raw responses；但`build_prediction_artifacts`一旦遇上任何不合格row，就整批raise，只留下第一個status reason，當時完整輸入亦隨process結束消失。不能用之後DB玩家／fixture／odds狀態倒填當時snapshot，更不能刪警告／只發布較早合格row去救數字。

## 修正

保留原嚴格builder及shared verifier。只有projection失敗時，另外將**全部已收到嘅原樣observations及已讀raw response rows**保存成`Tennis_Research_Diagnostics_<date>.json.gz`，隨原canonical snapshot嘅manifest綁hash。其schema明示`DIAGNOSTIC_ONLY_UNVERIFIED`、feature availability false、promotion false；不產生`Tennis_Feature_Evidence_*`，不改研究blocked status、定價、推薦或publication gate。

Journal保留原prediction clocks、完整warnings／缺值／重複及未配對IDs，唔補記憶、唔插值、唔重讀較新DB修復coverage。只有原六欄raw查詢資料可入檔；request headers／settings／environment不複製。無法讀到嘅raw不造出來，診斷仍不合資格。

以streaming JSON／gzip限128MiB未壓縮、16MiB壓縮（低於canonical reader每檔32MiB上限）；超預算／非有限值則整份診斷失敗、明列reason，唔截斷成部分成功，原card及研究blocker仍保存。合格projection路徑完全不新增journal，既有artifact bytes golden hash保持一致。

## 驗證及限制

- 34個相關測試通過：原good-artifact byte golden不變；effectful warning及一個壞row仍拒絕全批；兩個observations及raw文字完整round-trip；coverage不足／重複／budget／NaN明列；diagnostic失敗不抹走原card。
- 使用今朝45個保存pricing、90份player payload fragments及28個raw responses作**事後size／round-trip probe**：原raw文字46,749,508 bytes，journal未壓縮57,069,859、壓縮3,684,907 bytes；全部原樣讀回，實際15853警告成功重現。
- Probe明示原完整記憶已不存在，只係posthoc player fragments，無當作舊pregame完整重建、無登記canonical evidence、零新增qualified樣本。呢份probe唔證明live新journal已產生。
- Quick gate通過（首輪sandbox擋ruff cache，正常權限原檢查通過）；完整交付gate及activation狀態以Central immutable release manifest為準。

外置證據：原統一run嘅`runtime-diagnostics/`，含修正前feature verifier、actual-size probe／script／原raw hashes及事後probe壓縮檔；原始研究snapshot未複製。Code由獨立最新main worktree交付，唔將研究分支被拒絕嘅模型code一併release。

下一個正常Tennis run先驗證新診斷檔嘅manifest hash、完整ID／raw coverage及blocked status仍在；今次不因驗收而重跑／發布另一張正式card。之後按保存下來嘅具體輸入處理missing surface、stale WTA profile及identity來源問題，過原有資料／模型評估閘先可聲稱改善。
