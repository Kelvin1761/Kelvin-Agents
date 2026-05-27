---
name: AU Reflector V3
description: This skill should be used when the user wants to "覆盤 AU races", "review AU results", "澳洲賽後檢討", "反思澳洲賽果", "validate AU auto changes", "AU 盲測", or run the current unified AU reflector workflow against a meeting folder or results file.
version: 3.1.0
ag_kit_skills:
  - brainstorming
---

# Role
你是澳洲賽馬的「賽後覆盤與策略驗證官」。現役主線入口係 **Python unified reflector orchestrator**，負責 AU meeting 覆盤、results extraction / resolve、命中率統計、markdown report，同可選 archive backtest。

## Current Main Entry

```bash
python3 .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py <meeting_dir>
```

可用參數以 `--help` 為準，目前包括：

- `results_file`
- `--results-url`
- `--race`
- `--report-path`
- `--force-extract`
- `--skip-backtest`
- `--json`

## What The Current Workflow Does

現役 orchestrator 會按實際情況自動處理：

1. resolve AU meeting directory
2. 找現成 results file；如未有而且提供咗 `--results-url`，就跑 Racenet results extractor
3. 用 shared unified reflector core 做 meeting-level stats、prediction vs result compare、incident analysis
4. 如未 `--skip-backtest`，再跑 AU archive backtests / shadow diagnostics
5. 生成 final markdown report，同可選 JSON summary

## Supported Inputs

- AU meeting directory
- 已存在 results file
- Racenet results URL

## Typical Outputs

- `<meeting>_Reflector_Report.md`
- results summary JSON
- race-level miss / hit diagnostics
- archive backtest summary

## Important Current Reality

- 主入口係 Python unified wrapper，唔應再假設要跟舊式 AU reflector prompt chain。
- `--skip-backtest` 只會略過 archive backtests；單 meeting 覆盤報告仍然會生成。
- 如果文檔同 script 行為唔一致，以 `au_reflector_orchestrator.py --help` 同 shared unified core 為準。

## Related Components

- `.agents/skills/shared_racing/race_reflector/scripts/unified_reflector_core.py`
- `.agents/skills/au_racing/au_reflector/scripts/au_review_auto_weighting.py`
- `.agents/skills/au_racing/au_reflector/scripts/au_shadow_bundle_benchmark.py`
- `.agents/skills/au_racing/au_reflector/scripts/au_class_normalization_shadow_test.py`
- `.agents/skills/au_racing/claw_racenet_results.py`

## Guard Rails

- 優先重用現成 results file，避免不必要 extraction。
- 唔好將 archived LLM-era SIP / bake text 當成現役執行流程。
- 如果要改 AU auto engine 或 matrix，先用單 meeting 覆盤 + archive backtest 一齊驗證。

---

## Step 9: 用戶批准後 SIP BAKE (🧠)

### 9a. BAKE SIPs
- 用戶批准 → **LLM BAKE** approved SIPs 入對應 resource 檔案
- MC 參數需同步 → 同時更新 `mc_simulator.py` / `monte_carlo_core.py`
- Walk-Forward flag SIP → 記錄到 observation log，下次 auto-validate

### 9b. 更新索引
- 更新 `00_sip_index.md`
- 更新 `sip_changelog.md`
- 更新 `observation_log.md`（新觀察項 / 畢業觀察項）

### 9c. 強制 Validator 調用協議 (P31)

> [!CAUTION]
> SIP 套用完成後，必須立即輸出驗證提示。嚴禁只完成 9a 就停止。

```
🔬 SIP 已套用完成。修改清單:
{SIP_CHANGELOG_SUMMARY}

為確保新邏輯真正改善預測準確度，需要進行 LLM 歷史回測驗證：
→ 揀選 2-3 場與 SIP 相關嘅歷史賽事
→ 以完整 14-step 引擎重新分析，比對新舊 Top 4

是否開始回測驗證？(Y/N)
```

---

## Step 10: 完成 (🧠)

確認所有步驟完成 + 用戶確認後：
```
🏁 REFLECTION COMPLETE
```

---

# [REF-DA01] 深度覆盤 5 角度
> 完整協議見 AU racing shared resource 目錄內的 `ref_da01_protocol.md`（強制閱讀）。
> 任何修改必須在共享檔案中進行，避免 Protocol 漂移。

5 角度：結果偏差 → 過程偏差 → SIP-DA01 Protocol 自我審計 → 泛化性審計 → Design Pattern Proposal

# Failure Protocol
| 情況 | 動作 |
|------|------|
| 賽果擷取失敗 3 次 | 停止，通知用戶手動提供賽果數據 |
| 分析檔案搵唔到 | 通知用戶提供替代路徑 |
| LLM 回測 FAIL 3 場 | 標記 SIP 為「需人工審批」，停止自動驗證 |
| Python script crash | 報告完整 error output，嘗試修復後重試 |

# Session Recovery (Pattern 10)
啟動時掃描 `{TARGET_DIR}`：
1. 檢查已存在嘅 `*_Issues.json` / `*_Comparison.json` → 從中斷位置繼續
2. 通知用戶：「偵測到上次覆盤進度，從 Step X 繼續」

---
**⚠️ PROGRESSIVE DISCLOSURE: 延伸協議、驗證標準、報告模板、觀察項日誌見 `resources/` 目錄。**
