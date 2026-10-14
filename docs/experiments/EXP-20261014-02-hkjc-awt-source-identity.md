# EXP-20261014-02 — HKJC AWT surface identity correctness

- 日期：2026-10-14；平台HKJC；狀態：CORRECTNESS CANDIDATES ONLY / PERFORMANCE FLAG。
- 用戶授權：用現有18場泥地追查原始往績→Facts→Logic→engine訊號。
- 前置記錄：EXP-20260928-05 AWT fallback、EXP-20261008-07 history identity、EXP-20261013-08 per-race oracle。
- 非模型refit：不改權重，不讀當場結果作搜索／選擇。18場全數source audit，原2026-09-09quarantine不變。

## 已獨立重現

1. Formguide parser將`沙田 "AWT"`變venue沙田／railAWT；後續只按venue分表面。149／213 records有499次prior AWT row usages被當草地。單獨修parser保留表面，同一近期formguide恢復138／213個泥地有效樣本，136個target score有變。
2. Engine讀surface effective sample跨過分隔符，攞第一個沙田草地數字；32個stored surface紀錄有27個值錯。正確stored AWT sample>0係18／213。
3. Facts三處將venue截[:4]，`沙田AWT`變`沙田AW`，table／finish-time標準lookup掉失表面。獨立renderer候選同fixture驗證。

三份patch分開，無auto apply；詳見audit REPORT。Formguide表面修正同renderer係同一身份鏈嘅不同失效點，唔係聯合調多個權重。每份可獨立重現。

## 更正舊結論

20261013輸入audit中26個positive sample沿用錯誤regex，實際係第一個草地sample；作廢，stored泥地係18個。原182個foreign list非空亦唔係true overseas coverage；重讀真正海外表面只11個，PIT/距離/本地無樣本fallback2個。

## 證據紀律

日期先filter，所有historical run dates < target；formguide馬號及馬名同固定dataset精確join。不加入profile、不補scrape、不套今天先驗重建surface樣本。Surface helper沿用既定±200m／730日／365半衰／4中性收縮。候選metadata-only213行ability／matrix完全相同；parser／renderer對完整live scoring影響未評估，唔聲稱改善。

完整profile／存檔PIT來源未清，所以績效promotion FLAG。下一步correctness paired replay需baseline／candidate同凍結profile同原cohort，分開metadata／parser／renderer；follow evaluation contract section7及cohort guardrail，唔用terminal調權重。

## 檔案／驗證

- 工具：`docs/experiments/patches/hkjc_awt_source_trace.py`。
- 測試：同目錄`test_hkjc_awt_source_trace.py`，9 tests PASS。
- 產物：`docs/audits/hkjc-awt-source-trace-20261014/REPORT.md`、`trace.json`、3份candidate patch、7個meeting現有health scans。
- `./檢查.sh --quick`最終PASS；正常權限完整`./檢查.sh` exit0、14 suite全過；原AU／HKJC golden未變。
- 冇改現役model、資料、golden、calibration；冇commit／push／deploy。
- 每份source SHA256在trace.json；執行後一致。raw資料小，無大型語料拷貝。
