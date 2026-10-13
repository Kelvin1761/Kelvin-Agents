# EXP-20261013-09 引擎讀唔到短途頭馬時間（正確性修正）

- **日期**：2026-10-13
- **平台**：AU
- **類別**：§7 正確性修正 —— **冇通過表現閘，唔係一個已證實嘅改善**（亦唔需要：排名 bit-identical）
- **假設**：`engine_core._parse_formguide_entries` 用 `_parse_time_to_seconds`（硬要 `M:SS.mmm`）
  讀 `WinningTime:`，所以 <60 秒嘅 `WinningTime:58.420` 全部變 None。
- **搜索過嘅舊記錄**：EXP-20260831-07（claw `RE_WINNING_TIME` 同一個 bug，已修喺抽取層）
- **改到嘅檔案**：`au_racing_engine/engine_core.py`（`_parse_winning_time`、`_WINNING_TIME_TOKEN`；
  `_parse_running_position` 過時 docstring；`timing_trial_600m_avg_speed` 註解）、
  `tests/test_sportsbet_extended_fields.py`

## 錯處（可獨立證明，唔靠績效）
- 語料 3,628 份 Formguide，`WinningTime:` token 201,421 個，**37,902 個（18.8%）冇 `M:`**，引擎全部讀唔到
- 抽取層 08-31 修好，引擎層冇跟 —— 同一個失敗模式第八次

## 檢查
- **consumer**：`winner_time_seconds` 喺 repo 入面冇任何讀者（只有 producer + 1 個 test）→ 排名不可能變
- **golden_scoring**：✅ 120 匹馬全部一致
- **leakage-audit**：PASS（只改 parse，唔改資訊集）
- **test**：新 `test_engine_reads_sub_minute_winning_time`；檔案 15 passed

## 同場順手（唔郁行為）
- `_parse_running_position` docstring 寫住「四個 marker 0% 命中」—— 已過時：
  2026-10-13 量 `pos_800`／`pos_400` 99.8%、`settled_pos` 70.1%（Ascot 10-14，539 條）
- `timing_*`（Racenet `600m / MM:SS.mmm`）**live 永遠 None** → 三個試閘速度加分 live 永遠唔觸發；
  但 ≤2026-08-01 嘅 68 個舊賽日仍有 105,927 條，回放會觸發，所以**唔剷**，只加註解

**決定**：KEEP（正確性修正）
**commit**：未 commit（等 Kelvin 講保存）
