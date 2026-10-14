# EXP-20261014-03 — Apply HKJC AWT source correctness fixes

- 授權：用戶2026-10-14「fix please」。
- 前置：EXP-20261014-02、AWT18場source trace，已獨立證明三個資料／解析錯誤。
- 狀態：IMPLEMENTED IN WORKING TREE；正式performance promotion仍FLAG，唔聲稱改善。
- 修正：保留quoted AWT venue；Facts venue不截[:4]；engine target sample只讀今場surface欄。未改權重／formula。
- 相容：保留root其他工作；exact pre-fix snapshots已保存，applied_changes.patch只含本次delta。

## 配對影響

18場213紀錄，不讀target results／不fit weights。82精確ID＋名字profile、131 unresolved明文雙邊no-profile；同sources同PIT日期過濾，移轉surface／same-course統計／finish-time fields，其餘stored inputs固定。

144個input有變、15個ability有變（−3.81至+3.05）；6場order有變、1場Top4順序有變（2026-06-07R5首兩揀對調）。18場Top2／Top4集合都一樣，所以此有限replay嘅canonical Gold／Good必定不變。唔等於完整pipeline無變，唔等於績效改善。

Profile cache PIT未證、131個未唯一對齊、未完整meeting SIP，performance/leakage promotion FLAG保持。校正基於surface identity錯誤嘅獨立證據，唔由holdout結果選擇；原quarantine不變。

## 驗證及產物

新正式live-code regression7case PASS；隔離source-trace regression9case PASS。quick最終PASS，AU/HKJC golden／docs／contract未變。完整suite結果完成後附加。

完整修正報告、before/after、exact patch／source hash：`docs/audits/hkjc-awt-source-fix-20261014/`。
未commit／push／deploy，未改archive／golden／calibration。之後正常重建Facts會用修正來源；唔自動覆寫舊存檔。

最終完整`./檢查.sh` exit0，14個suite全部PASS；正式新回歸tests已由Agent scripts suite執行。`git diff --check`通過。
