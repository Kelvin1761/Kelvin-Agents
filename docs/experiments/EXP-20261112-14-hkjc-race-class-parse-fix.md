# EXP-20261112-14 HKJC 今仗班次解析修正（Facts 中文數字班次、排位表空白班次行）

- **日期**：2026-11-12 ｜ **平台**：HKJC ｜ **類型**：§7 正確性修正（數據）
- **觸發**：EXP-20261112-13 發現 Logic `race_class` 有 18% 場次係預設「第四班」；Kelvin：「please fix」
- **改到嘅檔案／組件**：`.agents/scripts/inject_hkjc_fact_anchors.py`（`extract_race_context`）、
  `hkjc_auto_orchestrator.py`（`_parse_racecard_meta`）、兩個測試檔

## 問題
1. **Facts 班次**：`extract_race_context` 用 `第(\d)班` 搵班次，但賽績檔寫「第三班」（中文數字）→ 永遠搵唔到 →
   預設 `C4`。2026-04 起 450 場 Logic：365 場同排位表一致（全部本身就係第四班）、**78 場錯**、7 場兩邊都讀唔到。
   即係**所有唔係第四班嘅讓磅賽**，Facts／Logic 都寫成第四班。
2. **排位表班次**：`re.search(r"班次:\s*(.+)")` 嘅 `\s*` 會食咗換行；新馬／平磅賽「班次:」係空，
   就捉咗下一行「#### 第二部分：馬匹資料 (Horse Info)」做班次 —— 報告「賽事格局」就咁顯示，評分時亦用咗呢個字串。

## 影響
- 評分時 orchestrator 用排位表班次覆蓋 Logic（`_align_runner_headers`），所以讓磅賽排名本來就用啱班次。
- 受影響嘅係：Facts／Logic 檔本身（研究腳本、回放 harness、EXP-09 標準時間表都讀咗錯班次）、
  新馬賽報告標題、Facts 嘅「今仗標準時間」輸出。
- 回放 449 場：修正前後**排名 0 場唔同、raw 分 0 匹唔同**（`fixed_rule` REJECT／ranking_evidence_too_weak 係預期，因為冇郁排名）。

## 修正
- `第([1-5一二三四五])班` → C1–C5；三級賽等分級賽次序唔變
- 排位表 `^班次:[ \t]*(\S.*)$`（唔跨行；空就返空字串，保留 Logic 班次）
- 舊 Facts／Logic 檔**冇重寫**（不可變存檔）；需要正確班次嘅研究一律讀排位表（`_parse_racecard_meta`）

## 檢查
- 新測試：中文數字班次 4 個、分級賽、排位表空班次行唔跨行、正常班次行
- **leakage-audit**：N/A（賽前資料解析）

**決定**：KEEP（§7，冇排名影響）
