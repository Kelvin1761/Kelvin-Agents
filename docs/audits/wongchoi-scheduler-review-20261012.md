# Wong Choi 排程審查 — 2026-10-12

今次係審查及調整建議，未修改排程、prediction engine、已安裝 plist 或 production checkout，亦未 commit／push／activate。

## 審查依據

- 實際讀取 `~/Library/LaunchAgents/com.antigravity.*.plist`，逐個以 `launchctl print gui/501/<label>` 驗證；23 個現役 Antigravity plist 全部 loaded。
- 四線 runner 指向 `/Users/imac/wongchoi-scheduler`，審查時 production HEAD 為 `16c028ab86364b0b1c1348f1438e54d2244aff03`。工作目錄已有其他 session 修改，不能將 working tree 當成 live code。
- 讀取 production HKJC／AU／NBA logs、production control-plane retry 邏輯、工作目錄排程及 Central read-only status。沒有重跑賽事或發送訊息。
- 時間全部以 `Australia/Sydney` 表示。2026-10-12 悉尼 UTC+11、香港 UTC+8；香港對照時間由時區換算，不能全年硬寫相差三小時。

## 已確認問題

| 優先度 | 問題及證據 | 建議處理 |
|---|---|---|
| 高 | AU 22:00、HKJC 23:30／00:30、NBA 00:30 直接撞每日遊戲時段；HKJC recovery 每 1800 秒仍可開完整 pipeline。startup／睡醒補跑亦沒有共用遊戲時段閘。 | 22:00–01:00 禁止啟動重型工作，所有入口及重試都要經同一個閘；pending 記錄必須保留，之後補跑。 |
| 高 | production `shared_wong_choi/control_plane.py:224` 的 `execute_with_retry` 沒有等待，即刻再 execute。NBA 2026-10-12 21:00:06、21:00:16、21:00:22 三次皆 partial。 | 將「來源未發佈／盤口未開」改為有 `next_retry_at` 的等待狀態；短暫網絡錯誤才作有限次、帶退避的即時重試。 |
| 高 | HKJC recovery 呼叫完整 prerace；2026-10-12 21:19、21:25 兩次仍然只有 6/9 refreshed formguides，但 PDF 已 OK。watch 等鎖 620 秒。 | 先作有效 PDF／缺失賽績頁的輕量 readiness probe；未齊不重抽全日。保留 existing valid files 和 fresh-data publish gate，不能為求成功而放寬。 |
| 高 | AU 最近四次晚更分別用 139.9、329.0、181.4、125.9 分鐘；單純改為 20:00 不足以避開遊戲時間。晚更串連覆盤、賽果 ingestion、shadow、翌日分析及 deploy。 | 翌日分析優先；shadow／全歷史 maintenance 分開排。21:45 前在安全 checkpoint 停止新增重型步驟；延後工作於 01:00 後續跑。不能粗暴 kill 正在寫資料的程序。 |
| 高 | NBA 18:30／21:30 postgame 記錄 `live_analysis_has_no_prediction_snapshot`，立即重試仍失敗。 | 查清缺 snapshot 的生成／恢復路徑；標記待恢復並避免重複做 settlement。不能補造歷史 prediction 或無 evidence 結算。 |
| 中 | NBA 21:00 是 warmup，`publish_allowed=False`；把 00:30 改時鐘不等於提前收到正式卡。 | 在遊戲前增加／移動 production 角色，但只在球員盤口及資料齊時發佈；保留 06:30 final refresh。 |
| 中 | 時間散落於 plist templates、`schedule_policy.py`、control-plane slot maps／NBA target-day 判斷；shared policy 未涵蓋 AU midday、HKJC lineup／weekly 等全部現役 job。 | 一個完整 schedule 定義生成／驗證 templates、slot identity 及 target date。尤其改 NBA warmup 時間後，不能遺漏原本 `slot == "21:00"` 的翌日判斷。 |
| 中 | AU evening 設 `WC_SB_PEOPLE_TTL_DAYS=0`，每個場次強制刷新騎練統計。 | 評估同一輪以 identity 去重、共用已刷新的值；仍保留晚更 freshness 要求。先量請求數及 elapsed time，未量度前不聲稱更快。 |

## 建議時間表（未啟用）

| Domain | 建議悉尼時間 | 備註 |
|---|---|---|
| AU | 約 17:00–18:00 開始翌日分析；10:00 保留賽日刷新 | 開始時間需確認翌日資料可用性及尾場賽果時間。分析優先，未齊來源用輕量檢查；覆盤／shadow 分開。21:45 checkpoint，未完成排至 01:00 後。 |
| NBA | 19:30 warmup、20:30 production、06:30 final refresh | warmup 仍指向翌日；20:30 production 亦須明確指向翌日。未開盤不能保證遊戲前有完整卡，可設 01:45 補跑且與 HKJC 錯峰。21:30 第二輪 postgame 移至較早或 01:00 後。 |
| Tennis | 09:00 card、10:30／12:30 recovery、18:00 日結維持 | 現在已在遊戲前；18:00 不宜取代 09:00 card，翌日 book 未必已開。 |
| HKJC | 01:05 readiness watch、01:15 第一輪正式分析；08:00／11:00 賽日刷新保留 | 01:15 在當前夏令時間等於香港前一日 22:15；此時間不保證來源必定齊，仍需 readiness。取消 21:30／23:30／00:30 完整分析；遊戲前 discovery 可保留但不能觸發完整抽取。 |

延期補跑要記住原本 meeting／target date／scheduled slot，不能過午夜就變成另一個賽日。遊戲時段閘要覆蓋 control-plane、AU auxiliary、HKJC direct weekly／intraday、Tennis recovery、bot 觸發的重型命令及 release activation 的 startup；保留輕量訊息接收不代表可以啟動分析。

## 營運狀態及限制

- Central 30 日 slot 健康率：AU 66/66（100%）、HKJC 2349/2410（97.47%）、Tennis 60/60（100%）、NBA 130/187（69.52%）。這是排程狀態統計，並非每日卡成功率或預測準確率；dormant／skipped 等分母定義需一起理解。
- 最新狀態：AU succeeded、HKJC running、Tennis succeeded、NBA partial。Model registry：AU／HKJC production，Tennis／NBA shadow；registry stage 不能當成目前 runtime code SHA。
- Central `status` 未傳 production mapping 時回 `runtime:not_configured`，不是 launchd 未安裝；今次另讀已安裝 plist 及 loaded state驗證。
- Dashboard configured；D1 verified backup age 18.44 小時、local restore／WARM verified，最新副本 COLD 未 verified；整體 catalog COLD 14/16 verified。
- 內置 HOT free 約 16.81 GiB，低於 Central 20 GiB critical floor；外置 WARM 可用約 837.93 GiB。避免遊戲時段及本機重型研究／語料複製，不能未驗證備份就刪原件。
- Central 同時報 pending／failed release，需要逐項查 release record；不能因此判定最新 activation 失敗，最新記錄 activation 是 succeeded。

## 下一步驗證

實作前保留 exact scope 及 production rollback SHA；不合入其他 session 修改。回歸案例應涵蓋 21:59／22:00／00:59／01:00、Sydney DST、HK 日期換算、延期 target date、startup／catch-up、來源 waiting 不即時三連跑、checkpoint 恢復、NBA publish role 及 snapshot 缺失恢復。安裝後重新讀 plist／loaded state，觀察至少數日 gaming overlap、卡完成時間、來源重試數、request count 及 runtime，才可宣稱效率改善。

## 今次檢查結果

- `./檢查.sh --quick`：通過。
- `./檢查.sh`：未全綠，AU Wong Choi 及 HKJC daily auto suites 失敗；其餘列出 13 個 suite 通過。AU failures 出現 test interpreter 找不到 `lxml` parser；HKJC failures 出現 sandbox 不允許寫預設 repo log。不能當成 live scheduler 已壞，亦不能宣稱完整檢查通過。
- 用可寫暫存 log 目錄獨立重跑 HKJC：`WC_HKJC_SCHED_LOG_DIR=/private/tmp/wc-scheduler-review-hkjc-logs PYTHONDONTWRITEBYTECODE=1 python3 -m pytest .agents/skills/hkjc_racing/hkjc_daily_auto/tests -q`，70 passed（2.84 秒）。
- production runner 的 `/usr/bin/python3`（3.9.6）可 import `lxml 6.0.2`；完整 suite 的失敗 trace 使用 3.14 test environment，兩者不可混為一談。沒有為此修改或安裝依賴。
- logs：`/private/tmp/wc-scheduler-review-quick.log`、`/private/tmp/wc-scheduler-review-full.log`、`/private/tmp/wc-scheduler-review-hkjc-tests.log`。沒有 commit，沒有 push。
