# HKJC泥地來源修正 — 2026-10-14

用戶「fix please」授權後，三個已獨立重現嘅correctness修正已套入現行工作目錄；冇改權重，冇改其他session嘅工作。只修改Facts generator四個位置、engine metadata reader一個位置，另新增正式回歸測試。

## 已落實

1. Formguide `沙田 "AWT"`保留venue=`沙田AWT`，避免泥地往績計成草地。
2. Facts最近／較舊表格同完成時間趨勢，使用canonical完整表面，唔再截成`沙田AW`。
3. Surface effective sample按今場target欄讀取，唔再攞第一個草地數字；target欄缺失唔借其他表面數據。

## 配對重播

18場／213個matched runner records，同原formguide、同一份profile cache、相同historical date < target、同一套權重及其餘stored inputs。

- 82個紀錄可由ID＋名字唯一對齊cached profile；131個未能唯一對齊，兩邊都明文用no-profile，唔補新資料亦唔暗中剔除。
- 重播只轉移surface文字、season/same-course統計、完成時間derived fields，其餘原Logic inputs凍結；兩邊都經同一Logic summary／finish-time parser。
- 144個紀錄相關輸入有變；15個分數有變（全部屬82個已對齊profile紀錄），範圍−3.81至+3.05顯示分。
- 6場完整排序有變；1場Top4順序有變：2026-06-07沙田R5 `[9,2,14,11] → [2,9,14,11]`。
- **18場Top2馬匹集合／Top4馬匹集合全部相同**。因此呢份有限重播嘅canonical Good／Gold不變，唔需要讀當場結果去證明。

呢個係correctness影響重播，**唔係改善證據**：未證cache係賽前凍結版本；131個profile未對齊；未包含完整meeting SIP／其他由Facts重建嘅字段。不能當正式PIT performance／promotion gate PASS。唔曾以quarantine結果調權重或挑patch。

## 驗證

- 新正式`test_hkjc_awt_source_identity.py`：7個case PASS，直接測現行程式；已加入正常Agent scripts suite發現路徑。
- 原隔離source-trace測試：9個case PASS；baseline已保存，改code之後仍可重現舊bug。
- `./檢查.sh --quick`最終PASS；AU／HKJC golden未變，模型說明及資料合約PASS。
- 完整repo檢查exit0、14個suite全部PASS，日誌見full_check.log。

baseline code snapshots（包含修正前其他session嘅已存在dirty changes）在上一輪audit baseline/。`applied_changes.patch`只記本輪baseline→fixed改動，唔包含之前dirty code；source SHA256在fix_manifest.json。

## 檔案及重現

- 現行：`.agents/scripts/inject_hkjc_fact_anchors.py`
- 現行：`.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/engine_core.py`
- 正式測試：`.agents/scripts/tests/test_hkjc_awt_source_identity.py`
- 研究重播：`docs/experiments/patches/hkjc_awt_correctness_replay.py`
- 完整逐馬影響：`paired_replay.json`

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q .agents/scripts/tests/test_hkjc_awt_source_identity.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s docs/experiments/patches -p test_hkjc_awt_source_trace.py -q
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_awt_correctness_replay.py
./檢查.sh --quick
./檢查.sh
```

冇修改／重算archive meetings、golden、calibration或權重；冇commit／push／dashboard deploy。修正令之後Facts生成使用正確泥地身份；舊已生成Facts／Logic不會自動補回。
