# Tennis 賽前盤與走地資料防線

2026-11-05 Sydney。由 origin/main `11d49d6e0` 開獨立 worktree。此為資料入口正確性修正，沒有改模型權重、候選、dev／holdout 切法或判決門檻，沒有準確度／ROI 改善證據。

## 固定證據及對照

正常 09:00 card 成功完成，有 57 個 immutable pricing observations，但研究資格仍為 0。固定診斷快照為 `20261104T222916.029764+0000-05bfd5e3152f`，gzip SHA256 `c52e10f46e2d0be6884b07aedf2f3a4178ea24168cdc062d581e4f0e2839a69d`。只在記憶體讀原文，版本控制只存程式、彙總及雜湊。

57 場都有 start。12 場 prediction_created_at 已達或超過該 start，預測前最早已保存原文亦明示 `raw.event.status=live`，沒有在這份快照內找到該 12 場的賽前原文。另 45 場原文為 active，預測時尚未達已記錄 start。這只是固定快照範圍的首次接收比較，沒有聲稱已讀全庫 MIN(id)。

以每場原來的 prediction_created_at 固定時間，實際 feature builder 重播會保留 45 場、跳過 12 場，45 場完整 snapshot 有序 SHA256 前後皆為 `22a5c38fc80cf39d1b721f556329f1af1cdb0da6e59c132db4c9da125881bcd2`。這驗證篩選及輸入一致，未重定價或聲稱 LL／Brier 改善。程式及結果在 [replay.py](patches/tennis_pregame_phase_20261105/replay.py) 及 [result.json](patches/tennis_pregame_phase_20261105/result.json)。執行命令如下。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src python3 docs/experiments/patches/tennis_pregame_phase_20261105/replay.py
```

最初對照腳本以 pair 最後遇到的原文覆蓋先前版本，live 命中為 11。修正為逐場只取預測前最早已保存版本後，命中 12。Python 3.9 解析 Z 時區亦已明確轉 +00:00。原始 prediction、原文及 qualification 沒有回填或修改。

## 實作範圍

- Sportsbet listing／direct event 原文照保存。明示 live 的新盤不寫入賽前 quote 表，舊 quote 與 forecast 保留；listing／direct event 會撤下 current pregame market capture。live fixture 的來源狀態保留，避免錯誤標成來源已下架。
- preclose 遇 live 只保存原文，不新增偽裝成賽前的收市快照；既有 preclose 及 current capture 維持原樣。
- Sportsbet feature builder 在開始建構前及完成後檢查已知 start，邊界相等亦跳過，並記錄原因。
- predict-daily、run-agents、run-daily 三個實際 CLI 入口在定價前後再次檢查，處理排隊或計算跨過 start 的情況。跳過原因放入 pregame_skipped 輸出。

原本缺 start 的一般 operational 路徑沿用既有行為，嚴格研究資格繼續按原規則拒絕不可核實時間。未改純 pricing 函式，歷史研究可用明確固定時計。此修正不等於實際開賽時間已驗證，賽程延誤仍需來源階段／實際時間證據。props 正式推薦已有 lead-time 閘，本次不改該判法。

## 驗證及後續

27 個針對測試覆蓋 listing／direct／preclose、舊盤保留、source fixture 狀態、start 前／等於／之後、建構與定價跨時、時區錯誤。quick 通過。完整 gate 與正式發佈結果以 Central immutable release manifest 為準，未驗證啟用之前不當作 production 已修復。

原 15 個 REJECT_DEV、C14 input qualification、F10 joint props 依賴及 Sportsbet 獨立 forward 規則保留。未新開一個夠 N 場判決的 forward 測試，沒有預先宣稱資料修復已改善命中率。下一步核對正常排程的新來源接收及新 card，再繼續修復來源身份與 serve/exposure 證據。
