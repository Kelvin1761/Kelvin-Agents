# Wong Choi 遊戲時段排程實作

狀態：已在獨立 worktree 完成實作及檢查，未 commit、push、merge 或 activate。現役 launchd 時間尚未改變。

原工作副本：`/Users/imac/.codex/worktrees/scheduler-gaming-hours/Antigravity-repo`。
2026-10-14 整合副本：`/private/tmp/codex-sort-schedule-20261014`；原候選 diff 已套用到最新 main／已保存 release 的合成基線，保留 HKJC SpeedPro 同 Tennis research-paper 文字。
起點 production SHA：`16c028ab86364b0b1c1348f1438e54d2244aff03`。主工作目錄的其他修改沒有混入。

## 新時間表（Sydney）

| Domain | 時間 |
|---|---|
| AU | 晚更 17:00；早更 10:00 維持 |
| NBA | 19:30 warmup、20:30 production（兩者均指翌日）；06:30 final refresh；postgame 18:30／20:00 |
| HKJC | watch 01:05／09:15／19:15；prerace 01:15／08:00／11:00；20:00 後完整 prerace／recovery／startup 延至 01:15 |
| Tennis | 09:00 card、18:00 日結、10:30／12:30 recovery 維持；recovery 改經共用 wrapper |

## 實作行為

- 共用 Sydney 22:00–01:00 閘，不受香港／澳洲夏令時間時差變化影響。四線 wrapper 在 self-update、DNS 等待或 dashboard 下載前先判斷；AU Telegram poller 在這時段不讀 updates，之後原有 offset 繼續處理。
- `WongChoiControl/deferred/<domain>/` 持久保存原日期、scheduled slot、role、參數及 attempt。原始 run manifests 保持 immutable。每線新增 `.deferred` job，每小時於 01–21 時之間处理一項：AU :40、HKJC :20、NBA :50、Tennis :10。
- 75／124 暫時失敗不再即時三連跑；至少冷卻 30 分鐘，等下一個可用補跑時段。普通來源失敗最多三次；checkpoint 使用獨立最多 20 attempts 的續跑上限。HKJC recovery 在遊戲時段的多次 poll 合併為一項待辦。scheduler lock 造成的阻擋也保留待辦。
- 補跑、開機及睡醒跨午夜保留原賽日；AU 晚更仍以原覆盤日推導翌日，NBA 晚間 slot 仍指原定翌日。更長時間離線或人手改日期仍應使用明確 `--date`／`--today`。
- scheduler-managed 子程序 21:45 起在新命令／AU 頁面請求邊界停下，記錄 partial，再由佇列重入。已寫好的 artifacts 留下，既有 idempotent 流程處理重入；不是保存任意 Python stack 的精確斷點。
- AU 保留 review／必要賽果 ingestion → analysis → evidence／publish 的資料依賴，只將 research shadow 放在發佈後。不改 scoring、weights 或 prediction evidence gate。
- HKJC PDF 未齊時寫 waiting-source readiness，保留已有資料，不再繼續抽全日晨操／賽績。退出馬 `field_change` 模式仍只在有效舊 PDF 情況使用原有特例；fresh racecard／formguide 閘沒有放寬。PDF HTTP request 有 connect/read timeout。
- installer、runtime verifier、中央 cutover snapshot／rollback 清單包含新 job。中央 installer 原子更新 AU 17:00 evening timer 同 queue consumer，兩者都納入 snapshot／rollback；保留執行 activation 的 AU bot。runtime verifier 同時比對已安裝 calendar／interval／startup policy、NBA mode／freshness role 及 Sydney 主機時區。

## 原候選驗證（2026-10-12，歷史紀錄）

完整命令：

```sh
PYTHONDONTWRITEBYTECODE=1 RUFF_CACHE_DIR=/private/tmp/wc-new-ruff \
WC_HKJC_SCHED_LOG_DIR=/private/tmp/wc-new-hk-tests PYTHON_BIN=/usr/bin/python3 \
./檢查.sh
```

- `./檢查.sh --quick` 通過；完整 `./檢查.sh` 15 suites 全過、ruff／AU+HKJC golden／模型說明 freshness 通過。
- 隔離副本未配置 live corpus，AU／HKJC data contract 步驟明確跳過；不能稱已重驗 live extraction values。
- 完整 Shared Wong Choi 1260 passed；最後 AU 次序回歸重跑 380 passed；installer／NBA／wrapper 針對測試 43 passed；其他邊界／PDF／policy 針對測試 35 passed。
- 針對測試覆蓋 21:59／22:00／00:59／01:00、Sydney DST、跨午夜日期、cooldown、retry cap、重複入列、HKJC recovery 合併、PDF 早退保留檔案、Tennis DB 路徑及隔離 cutover／rollback。
- 檢查記錄：`/private/tmp/wc-new-final-gate.log`、`/private/tmp/wc-new-au-final.log`、`/private/tmp/wc-new-install-final.log`、`/private/tmp/wc-new-target-final.log`。

## 限制及待辦

- 已啟動的子程序安全完成，仍可能越過 22:00；沒有強制 kill 寫入程序，不能宣稱遊戲時段一定零負載。人工直接跑研究／引擎腳本也不受 scheduler 閘保護。
- HKJC PDF 已齊而個別賽績頁未 ready 的情況，目前使用有冷卻的整批重試；逐個缺頁的 lightweight probe 尚未實作。
- NBA 球員盤口可能到遊戲後才開，20:30 不保證能出完整卡；保留翌朝刷新。歷史 `live_analysis_has_no_prediction_snapshot` 的 evidence 恢復不在此排程修正中，不能補造歷史 prediction。
- 未量新排程多日 request count／elapsed time／gaming overlap，不能聲稱實測效率改善。
- 最近審查的 Central 狀態見主 repo 的 scheduler review：AU／HKJC registry production、NBA／Tennis shadow，NBA SLO/evidence 有待處理；D1 WARM backup verified、COLD backlog、HOT headroom 偏低。今次沒有更改 ledger、storage 或 model registry。

下一步：獲明確保存／交付／release 指示後，以本 worktree exact scope 經 `保存.sh --path … --expected-result …` 及 Central immutable gate 保存／啟用；若 main 已前進，先合併最新版並重驗。不應直接把整個主 worktree 保存，亦不應單改 NBA plist 而沿用舊 target-day mapping。啟用後必須讀已安裝 plist／loaded state，並觀察多日遊戲時段重疊及卡完成時間。


## 2026-10-14 整合核驗

- queue 使用原日期、slot 同保存的 attempt；一般 launchd 在 cooldown 結束後再次觸發，也會讀保存中的 retry budget。checkpoint 不消耗來源暫時失敗三次的額度，但整體 attempt 仍以 20 封頂。沒有覆寫已有 immutable run manifests。
- 跨午夜明確日期沿 AU `--today`、NBA `--date`、Tennis `--today` 傳入原流程。HKJC recovery／discovery 有意重新找當前可跑 meeting；舊日期只保留於 control-plane identity，並非承諾重跑已過期的昨日 pre-race。
- `./檢查.sh --quick` 通過。AU data-contract 有既存 stale-baseline 提示（d31085dcf1c1 對 073fc80cd76e）；今次沒有改評分或重新 calibrate。
- 六個 scheduler-focused shared tests：57 passed；隔離 installer／snapshot／rollback：9 passed；AU／NBA／HKJC extractor／Tennis launchd：204 passed。新增混合 checkpoint／waiting-source 次數、cooldown 後正常 launch 保留 attempt、AU 原覆盤日、runtime 舊 calendar／NBA role／timezone 偵測案例。
- 完整 Shared 目錄測試為避免跟主線完整 gate 競爭而中止；不以該次執行宣稱整套通過。完整驗證及正式 activation 由整合主線另行執行。此副本沒有實際安裝、部署、commit 或 push。
- 針對紀錄：`/tmp/codex-sort-schedule-targeted.log`、`/tmp/codex-sort-schedule-installer.log`、`/tmp/codex-sort-schedule-domain.log`、`/tmp/codex-sort-schedule-quick.log`。
