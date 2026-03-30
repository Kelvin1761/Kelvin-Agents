# Agent Health Check + Blueprint 整合指南

本文件包含兩大部分：
1. **Agent Health Check 完整清單** — Mode B（優化）同 Mode C（審計）嘅逐項檢查標準
2. **Blueprint 能力矩陣** — 將 agent 需求配對到 `plugin_skill_blueprints.md` 中嘅藍圖方案

---

# Part 1: Agent Health Check 清單

對目標 agent 逐項檢查，每項評為 ✅ / ⚠️ / ❌：

## A. 結構合規 (Structural Compliance)
- [ ] Frontmatter 完整？（name + description + version）
- [ ] Description 包含 ≥3 個觸發短語？（B12 建議：slightly pushy，唔好 undertrigger）
- [ ] 有 Role + Objective + Scope + Interaction Logic 四大 section？
- [ ] SKILL.md 本體 ≤ 200 行？（超過應拆分到 resources/ — 漸進式揭露原則，見 B12）
- [ ] Resource 文件引用全部存在？（掃描 SKILL.md 中提到嘅檔案路徑）

## B. 防護機制 (Safety Mechanisms)
- [ ] 有防無限 Loop 機制？（circuit breaker / max retries）
- [ ] 有失敗處理協議？（Failure Protocol section）
- [ ] 有 Anti-Laziness 協議？（若處理批量數據）
- [ ] 有 Anti-Hallucination 指引？（N/A 填充規則）
- [ ] 有 File Writing Protocol？（禁止 heredoc 等已知問題 — Pattern 14）

## C. 品質保障 (Quality Assurance)
- [ ] 有自檢機制？（batch completion markers / self-check）
- [ ] 有品質基線追蹤？（跨批次/跨場次一致性）
- [ ] Output 格式有明確定義？（template / example — B2 建議用信心分數 0-100）
- [ ] 有 Read-Once Protocol？（若有 resources/）

## D. 生態系統整合 (Ecosystem Integration)
- [ ] 上游/下游 agent 接口定義清晰？（data contract）
- [ ] 語言要求同其他 agent 一致？（HK Traditional Chinese）
- [ ] 同 ecosystem_reference.md 中嘅描述一致？
- [ ] 冇同其他 agent 職責重疊？

## E. 實戰經驗教訓 (Battle-Tested Lessons)
- [ ] 批次隔離規則有冇？（每 batch 獨立 file write — Pattern 8）
- [ ] 反預判捷徑有冇？（唔可以因預判 D 級而壓縮分析 — Pattern 9）
- [ ] Session Recovery 機制有冇？（偵測已完成工作，避免重做 — Pattern 10）
- [ ] 強制 Checkpoint 有冇？（關鍵節點暫停等用戶確認 — Pattern 11）

## F. Blueprint 覆蓋度 (Blueprint Coverage)
基於 `plugin_skill_blueprints.md` 中嘅 31 個藍圖，檢查 agent 有冇善用適用嘅模式：
- [ ] 若 agent 處理代碼 → 有冇參考 B1 Code Simplifier 嘅 preserve-functionality 原則？
- [ ] 若 agent 有品質檢查職責 → 有冇採用 B2 嘅 confidence scoring (0-100) 機制？
- [ ] 若 agent 係新建嘅 → Description 觸發短語有冇經過 B12 嘅 optimisation 思維？
- [ ] 若 agent 有 resources/ → 有冇遵循 B12 嘅漸進式揭露原則？（metadata ~100 words → SKILL.md <500 lines → resources 無限）
- [ ] 若 agent 寫入文件 → 有冇參考 B13 Security Guidance 嘅模式偵測思維？
- [ ] 若 agent 有迭代改善循環 → 有冇參考 B17 Ralph Loop 嘅 completion promise 機制？

### Health Check 評分
每個 ❌ 必須附帶具體修正建議。每個 ⚠️ 附帶風險說明。
最終評級：總 ✅ 數 / 總檢查項數 × 100 = 分數
- **A (90-100)**: 生產就緒
- **B (70-89)**: 可用但有改善空間
- **C (50-69)**: 需要修正先可以用
- **D (<50)**: 需要大幅重寫

---

# Part 2: Blueprint 能力矩陣

## 快速配對表：Agent 需求 → 藍圖方案

| 你嘅 Agent 需要... | 參考藍圖 | 要提取嘅核心能力 |
|:---|:---|:---|
| 品質審查/代碼審查 | **B2** Code Review, **B10** PR Review Toolkit | 多 Agent 平行流水線、信心分數 0-100、門檻過濾（≥80 先報告） |
| 分階段工作流 | **B7** Feature Dev, **B11** Plugin Dev | 7/8 階段 workflow、每階段有明確輸入輸出、強制 checkpoint |
| 代碼生成/修改 | **B1** Code Simplifier | 保全功能原則、只改 HOW 唔改 WHAT、專注最近修改嘅代碼 |
| UI/前端設計 | **B8** Frontend Design | 反 AI-slop 美學、大膽設計方向、CSS variables 統一系統 |
| 持續改善循環 | **B17** Ralph Loop | 迭代 loop + completion promise、防止虛假退出、最大迭代限制 |
| 安全檢查 | **B13** Security Guidance | 模式偵測 + Session 去重、exit code 控制、自動清理 |
| 評估/基準測試 | **B12** Skill Creator | Eval 系統（test cases → parallel runs → grading）、描述觸發詞優化 |
| 技能/插件建造 | **B11** Plugin Dev, **B12** Skill Creator | 組件規劃、驗證 Agent、漸進式揭露、第三人稱描述 |
| 配置管理/審計 | **B4** CLAUDE.md Management | 質量評分量表（100 分 6 維度）、Diff 展示 + 理由、Session 學習捕捉 |
| 自動化/Hooks | **B9** Hookify, **B5** Claude Code Setup | 規則文件格式、事件類型配對、condition operator 設計 |
| Git/版本控制流程 | **B6** Commit Commands | 動態 context injection、最小化 tool 權限 |
| 互動式原型 | **B16** Playground | 單文件 HTML、即時預覽、狀態管理模式、preset 系統 |

---

## 核心設計模式提取

### 模式 A：多 Agent 平行流水線（來源：B2, B7, B10）

適用於需要從多角度審查嘅任務。設計要點：
1. **階段分明** — 每個階段有獨立 Agent，職責單一
2. **平行執行** — 無依賴關係嘅 Agent 同時運行
3. **結果聚合** — 最後由主 Agent 統一收集結果，按嚴重度排序
4. **信心分數** — 每個發現附帶 0-100 分數，過濾低信心噪音

```
主 Agent → [Agent A, Agent B, Agent C] (平行) → 聚合結果 → 用戶報告
```

### 模式 B：漸進式揭露架構（來源：B12）

適用於知識密集嘅 Agent。三層結構：
1. **第一層 — Metadata (~100 words)**: name + description，永遠在 context 入面
2. **第二層 — SKILL.md (<500 lines)**: 被觸發時載入，包含核心邏輯
3. **第三層 — Resources (無限)**: 按需載入嘅深層數據、模板、引擎

原則：SKILL.md 保持精簡 → 重度內容放 resources/ → 用 `view_file` 按需讀取

### 模式 C：信心分數門檻過濾（來源：B2）

適用於品質把關 Agent。量表定義：
| 分數 | 含義 |
|:---:|:---|
| 0 | 誤報 / 既有問題 |
| 25 | 可能真實但未驗證 |
| 50 | 真實但屬雞蛋挑骨頭 |
| 75 | 好大概率真實，影響功能 |
| 100 | 確実真實，有證據支持 |

**建議門檻：** 只報告 ≥80 嘅發現，避免噪音淹沒真正問題。

### 模式 D：迭代式自我改善（來源：B17）

適用於需要反覆執行直到完成嘅任務：
1. 設定 **completion promise** — 一個只有喺條件完全滿足時先可以輸出嘅標記
2. 設定 **最大迭代次數** — 防止無限 loop
3. 每次迭代 Agent 可以睇到之前嘅工作（透過文件 / git history）
4. 若達到最大迭代 → 自動退出，唔好強行完成

### 模式 E：Description 觸發詞優化（來源：B12）

設計 SKILL.md 嘅 description 時嘅最佳實踐：
1. **唔好太保守** — Claude 傾向 undertrigger，寧願稍為「pushy」
2. **包含具體 context** — 唔止寫「做乜」，仲要寫「喺乜情況下用」
3. **用第三人稱** — "This skill should be used when the user wants to..."
4. **≥3 個觸發短語** — 覆蓋用戶可能嘅表達方式
5. **測試觸發準確度** — B12 建議生成 20 個 eval queries（10 should-trigger + 10 should-not）

### 模式 F：質量評分量表（來源：B4）

設計審計/評分 Agent 時嘅參考量表：
| 維度 | 權重 |
|:---|:---:|
| 核心功能完整性 | 25% |
| 架構清晰度 | 20% |
| 防護機制 | 15% |
| 可維護性 | 15% |
| 生態系統一致性 | 15% |
| 文檔/範例品質 | 10% |

---

## Agent 類型快速模板

### 數據提取 Agent
參考：B1 (preservation) + Pattern 1 (chunking) + Pattern 7 (programmatic bridge)
- 必須有：Anti-Laziness、Chunking Protocol、Output Format
- 建議：Python Script Offloading

### 品質把關 Agent
參考：B2 (confidence scoring) + B10 (specialised review) + Pattern 12 (tiered gates)
- 必須有：信心分數、Failure Protocol、嚴格嘅 pass/fail 標準
- 建議：多角度平行審查

### 分析/推理 Agent
參考：B7 (phased workflow) + Pattern 8 (batch isolation) + Pattern 9 (anti-pre-judgment)
- 必須有：明確階段劃分、Anti-Pre-Judgment、Quality Baseline
- 建議：Session Recovery、Forced Checkpoints

### 覆盤/反思 Agent
參考：B17 (iterative loop) + Pattern 15 (feedback loop) + Pattern 16 (state persistence)
- 必須有：Session State 持久化、改善建議格式、Completion Criteria
- 建議：Reflector → Architect Feedback Loop

### 統籌/指揮 Agent
參考：B7 (multi-phase) + Pattern 11 (checkpoints) + Pattern 13 (intelligence file)
- 必須有：Agent 路由邏輯、Checkpoint Gates、Session Recovery
- 建議：Intelligence Package 文件化、Tiered Quality Gates
