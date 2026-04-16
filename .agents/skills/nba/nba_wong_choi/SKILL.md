---
name: NBA Wong Choi
description: This skill should be used when the user wants to "analyse NBA", "NBA 過關分析", "NBA Wong Choi", "分析今晚 NBA", "幫我睇 NBA", or needs to orchestrate the full NBA player props parlay analysis pipeline from data extraction through to final parlay report generation.
version: 3.2.0
ag_kit_skills:
  - betting_accountant
---

# NBA Wong Choi — V3.2 Python-First Architecture

## ⛔ 第一鐵律：Orchestrator 強制執行

收到任何 NBA 分析指令後，你嘅**第一動作同唯一動作**係執行 Orchestrator：

```bash
# 分析全部賽事
python .agents/skills/nba/nba_orchestrator.py --date {YYYY-MM-DD}

# 只分析指定賽事 (當用戶只問「聽日」或某場比賽時使用)
python .agents/skills/nba/nba_orchestrator.py --date {YYYY-MM-DD} --game {AWAY_HOME}

# 列出可用賽事（幫用戶確認有邊幾場波）
python .agents/skills/nba/nba_orchestrator.py --date {YYYY-MM-DD} --list

# 查看當前 pipeline 狀態
python .agents/skills/nba/nba_orchestrator.py --date {YYYY-MM-DD} --status
```

### 日期解讀規則
| 用戶說法 | 轉換為（基於 AEST 時區） |
|---------|----------------------|
| 「今晚」「tonight」 | 今日日期 |
| 「聽日」「tomorrow」「tmr」 | 明日日期 |
| 「04-16」或任何具體日期 | 對應 YYYY-MM-DD |

### 賽事範圍規則
| 用戶說法 | Orchestrator 參數 |
|---------|-----------------|
| 「分析 NBA」（泛指） | `--list` 先列出 → 詢問用戶要分析邊場 |
| 「分析聽日嘅 NBA」「tmr's game」 | `--list` 先列出 → 詢問用戶 |
| 「分析 Lakers vs Rockets」「HOU LAL」 | `--game HOU_LAL` |
| 「分析全部」「all games」 | 不加 `--game`（全量模式） |

> [!CAUTION]
> 🚨 **當用戶話「analyse tmr's game」（單數）時，你必須先用 `--list` 列出賽事讓用戶揀選，而唔係自動分析全部！**

## 執行循環（NEXT_CMD 自動模式）

1. 第一次執行 Orchestrator（無 `--auto`）→ 印賽日總結 → 等用戶確認
2. 用戶確認後執行 stdout 顯示嘅 `NEXT_CMD`（包含 `--auto`）→ 進入自動模式
3. 每次 stdout 出現 `NEXT_CMD:` → 完成工作後即刻執行該指令
4. 重複直到 Pipeline 完成

> [!CAUTION]
> **NEXT_CMD 協議：** Orchestrator 每次退出時都會印一行 `NEXT_CMD: python ...`。
> 你**必須**完成當前任務後立即執行該指令，**唔好問用戶**。

## 執行規則（Orchestrator 內部自動處理）

Orchestrator V3 會自動串連以下 Python 腳本：
1. `claw_sportsbet_odds.py` → 從 Sportsbet 爬取即時盤口 JSON
2. `nba_extractor.py` → 從 nba_api/ESPN 提取球員 L10 數據
3. `generate_nba_reports.py` → 生成 Full Analysis（含 10-Factor、MC inline、SGM 組合）
4. `validate_nba_output.py` → 防火牆驗證
5. `generate_nba_sgm_reports.py` → 全日 Master SGM + Banker 報告

**你唔需要手動行上面任何一個腳本。Orchestrator 會幫你行晒。**

## 輸出檔案

Orchestrator 會生成以下檔案：

| 檔案 | 說明 |
|------|------|
| `Game_{TAG}_Full_Analysis.md` | 單場完整分析（含 MC inline、SGM 組合、球員盤口詳細分析） |
| `NBA_All_SGM_Report.txt` | 全日所有場次 SGM 組合完整分析 |
| `NBA_Banker_Report.txt` | 穩膽報告 + 跨場 Parlay |

## Anti-Bypass Guard（反繞過檢測）

以下特徵係合法 Python skeleton 嘅簽名。如果輸出缺少任何標記，即表明跳過咗pipeline：
- `Python Auto-Selection` 或 `Python 自動`
- `8-Factor` 或 `10-Factor`
- `@X.XX` 格式嘅真實賠率（唔係 "X.5" 格式）
- Sportsbet 盤口對照表（含 Edge / 隱含勝率 / 預期勝率）
- 真實球員名（唔係 "Player A/B/C"）
- 真實 L10 數組（唔係 `[1,2,3,4,5,6,7,8,9,10]`）

## 鐵律

- **嚴禁**跳過 Orchestrator 自行分析
- **嚴禁**自行建立任何 `.py` 腳本（如 `auto_fill_logic.py`）
- **嚴禁**跳過 Python 腳本自行計算數據
- **嚴禁**使用 \"Player A/B/C\" 等 placeholder 名稱
- **嚴禁**自創假 L10 數據（如連續整數序列）
- **嚴禁**重複句子灌水 — 每個句子只可出現一次
- **嚴禁**用 for-loop 批量生成所有賽事報告（P37 違規）
- 語言：香港繁體中文（廣東話口吻），球員名/球隊名保留英文
- 分析風格：Opus-Style 極度詳盡

## 進階資源

如需了解完整管線流程、品質掃描規則、文件寫入協議：
- `resources/00_pipeline_and_execution.md` — 完整管線
- `resources/engine_directives.md` — 硬性 XML 約束
- `resources/02_quality_scan.md` — 品質掃描
