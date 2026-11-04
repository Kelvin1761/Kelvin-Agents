# EXP-20261104-12 排程收到 SIGTERM 後收尾

EXP-11 的現役紀錄顯示 Tennis 卡中斷後留下 `running`，兩次復原被 `duplicate_active` 擋住。當日中斷訊號仍未確定。本輪用同一個 manifest adapter、真子程序及獨立工作鎖，隔離重現其中一條可修正路徑。[EXP-11](EXP-20261104-11-tennis-schedule-capture-run-gap.md)

基線向等待中的 scheduler 發送 SIGTERM，scheduler 直接以 `-15` 終止。修改後，主執行緒使用預設 SIGTERM handler 時，訊號交由現有 process-group 清理路徑處理，adapter 保存 `failed`。在 spawn 期間先記下訊號，取得子程序 handle 後才清理。測試核對工作鎖可重取，並由原生 `--force` 選擇 attempt 2。初版使用 `InterruptedError`，被 Python selectors 當作可重試的中斷，測試逾時。改用獨立例外類別後，23項針對測試通過。

再用實際 `control_plane.main` 和 Tennis adapter 對隔離工作入口重播。第一次收到訊號以exit 1終結，manifest記錄 `adapter_exception:SchedulerTerminated`。鎖可重取，同一 `--force` 入口成功執行attempt 2，exit 0並寫入 `succeeded`。工作入口為測試fixture，兩次均無讀寫正式資料。

Quick檢查全綠。此checkpoint時完整檢查仍運行，候選只存研究分支。此候選處理可攔截的 SIGTERM，既有殘留 manifest 仍需按原lock與子程序證據作獨立收尾。正式環境寫入0，未新增合格賽前樣本，準確度仍待量度。

外置證據 `tennis-scheduler-sigterm-v1-20261104/`，manifest SHA256 `ce1a9f375b19bbe64a280b85e53d30973b0b6fe070819aa1b469b97c84c8e86f`。

## 獨立發佈及既有紀錄

完整盤點145份Tennis run manifest，3份仍標記running，日期為10月23、10月24及11月4日。均為09:00 card、attempt 1、無operation，超過各自7200秒上限。逾時只作盤點旗標，各舊紀錄仍須獨立核實後收尾。

從當時主線 `82abbc1c` 建立獨立發佈worktree，只套用 runner及測試兩檔。Central dry-run確認code/full政策及四線同步，沒有installer或Dashboard deploy。新worktree的quick閘通過，正式發佈完整閘已啟動。合併及啟用以其terminal結果及不可變release證據為準。

外置預演及盤點 `tennis-scheduler-release-preflight-v1-20261104/`，manifest SHA256 `ce38f4a79eb6c7e8625c384e8bc60823c9a75c50a3f90dda7b825fd175a3d848`。

三份既有attempt再逐一核對原始hash及鎖，預演前後均未見已知Tennis runner。每份在臨時副本經原生API轉failed，`--force`從attempt 1改選attempt 2。正式manifest未寫入，沒有舊卡重跑。外置預演 `tennis-run-closure-preview-v1-20261104/`，manifest `7a5b933c5f92cb6625d34134b25d7da169024f47f21c7b8f798cb7ae4b98357a`。

研究分支完整檢查已terminal exit 0。Shared Wong Choi 1799項，Tennis 1156項。外置完整log及manifest `tennis-scheduler-sigterm-full-v1-20261104/`，SHA256 `e13b19ce37b9376f03cef7b519f8a4b3afc9a65940fc6b6ba8c60f6f22b7d111`。正式候選 `fb72eca512c6` 的獨立發佈閘此刻仍運行。
