# `generate_meeting_intel.py` — 2026-08-21 退役

## 點解退役

呢個腳本出一個 `_Meeting_Intelligence_Package.md`（天氣、場地狀況、場地資料）。
2026-08-21 逐項核實：

- **冇任何 live code 或文件叫佢。** 只有 `.agents/archive/wong_choi_legacy_snapshot_20260526/`
  嘅 AU / HKJC legacy orchestrator 讀嗰個輸出檔 —— 即係 pre-Python-pipeline 嘅 LLM 流程。
- **佢一直係壞嘅。** 用咗 `Path` 但成個檔冇 `import`，所以 `extract_track_conditions()`
  每次 call 都 `NameError`。冇人發現，因為冇人 call。（已修，見 `f385c0cc`。）
- **輸出停產。** 90 個 AU 場次只有 20 個有過 `_Meeting_Intelligence_Package.md`，
  最新一個係 2026-05-06。
- **功能已被取代。** 場地狀況而家由 Sportsbet API `trackStatus` 經
  `au_daily_schedule.py` 嘅 `--going` 直接傳入引擎 —— 零額外請求，而且同評分用
  嘅係同一個數字。天氣方面另有 `au_racecourse_weather_prediction/scripts/track_predictor.py`。

## 想用返

檔案完整可跑（`Path` bug 已修）。搬返 `au_wong_choi/scripts/` 就得，但要留意：
場地狀況已經有一條更可靠嘅路，唔應該再開第二個真源。

## `patch_playwright.py` 一齊退役

佢 `files` list 只有一個目標 —— 就係 `generate_meeting_intel.py`。目標歸檔之後
佢變成 no-op（有 `os.path.exists` 護欄所以唔會 crash，但咩都唔會做）。
