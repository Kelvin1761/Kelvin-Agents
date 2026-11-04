# EXP-20261104-12 排程收到 SIGTERM 後收尾

EXP-11 的現役紀錄顯示 Tennis 卡中斷後留下 `running`，兩次復原被 `duplicate_active` 擋住。當日中斷訊號仍未確定。本輪用同一個 manifest adapter、真子程序及獨立工作鎖，隔離重現其中一條可修正路徑。[EXP-11](EXP-20261104-11-tennis-schedule-capture-run-gap.md)

基線向等待中的 scheduler 發送 SIGTERM，scheduler 直接以 `-15` 終止。修改後，主執行緒使用預設 SIGTERM handler 時，訊號交由現有 process-group 清理路徑處理，adapter 保存 `failed`。在 spawn 期間先記下訊號，取得子程序 handle 後才清理。測試核對工作鎖可重取，並由原生 `--force` 選擇 attempt 2。初版使用 `InterruptedError`，被 Python selectors 當作可重試的中斷，測試逾時。改用獨立例外類別後，23項針對測試通過。

再用實際 `control_plane.main` 和 Tennis adapter 對隔離工作入口重播。第一次收到訊號以exit 1終結，manifest記錄 `adapter_exception:SchedulerTerminated`。鎖可重取，同一 `--force` 入口成功執行attempt 2，exit 0並寫入 `succeeded`。工作入口為測試fixture，兩次均無讀寫正式資料。

Quick檢查全綠。此checkpoint時完整檢查仍運行，候選只存研究分支。此候選處理可攔截的 SIGTERM，既有殘留 manifest 仍需按原lock與子程序證據作獨立收尾。正式環境寫入0，未新增合格賽前樣本，準確度仍待量度。

外置證據 `tennis-scheduler-sigterm-v1-20261104/`，manifest SHA256 `ce1a9f375b19bbe64a280b85e53d30973b0b6fe070819aa1b469b97c84c8e86f`。
