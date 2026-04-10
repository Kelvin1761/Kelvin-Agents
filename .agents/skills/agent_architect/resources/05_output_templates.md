# Agent Architect Output Templates

本文件包含 Agent Architect 所有模式嘅輸出格式模板。從 SKILL.md v2.2.0 遷移過嚟，減少本體行數。

---

## Template A: 新建 Agent 設計輸出

### Agent Name
[A concise, functional name for the agent]

### SKILL.md Frontmatter
```yaml
---
name: [Agent Name]
description: This skill should be used when the user wants to "[trigger phrase 1]", "[trigger phrase 2]", "[trigger phrase 3]"...
version: 1.0.0
---
```

### System Instructions
```markdown
[The complete, copy-pasteable core system prompt for the new agent, incorporating all six design pillars: Persona, Scope, Knowledge & Tools, Interaction Logic, Architectural Efficiency, and Tool Offloading.]
```

### Recommended Tools & Assets
- **Tools**:
  - **[Tool 1 Name]**: [Brief reason for inclusion based on the agent's scope]
- **Assets Directory Structure**:
  - `scripts/`: [List any required executable scripts to build, e.g., 'extract_data.py']
  - `examples/`: [List any required reference pattern files, e.g., 'output_format.txt']
  - `resources/`: [List any static data files or templates, e.g., 'database_schema.sql']

### Test Case
**User Input:** `[A sample query or scenario]`
**Expected Agent Action:** `[How the agent should process and respond to this specific query based on its instructions, including which scripts or examples it would reference]`

---

## Template B: Health Check 報告（含 Confidence Scoring）

### Health Check Report: [Agent Name] v[X.Y.Z]

**日期:** [YYYY-MM-DD]
**模式:** Mode B (優化) / Mode C (審計)
**評級:** [A/B/C/D] ([score]%)

| # | 檢查項 | 評級 | 信心分數 | 備註 |
|:---|:---|:---:|:---:|:---|
| A1 | [Check item] | ✅/⚠️/❌ | [0-100] | [Detail] |

### 關鍵發現（信心 >= 76）
[Critical findings list]

### 建議修正
[Remediation steps]

---

## Template C: Reflector Feedback 接收格式

Reflector 提交新 Design Pattern Proposal 時必須遵循以下格式：

```markdown
## Proposed Pattern: [Pattern Name]

**來源:** [HKJC/AU/NBA] Reflector — [Date]
**觸發場景:** [What real-world failure triggered this proposal]
**嚴重度:** [P0 Critical / P1 High / P2 Medium / P3 Low]

### Problem
[One paragraph describing the failure mode]

### Proposed Solution
[Concrete steps to prevent recurrence]

### Anti-pattern
❌ [What NOT to do]

### Correct Pattern
✅ [What TO do]
```

**Agent Architect 接收流程:**
1. 讀取 proposal 內容
2. 同現有 `design_patterns.md` 中嘅 patterns 比較 → 去重
3. 若唔重複 → 格式化為標準 Pattern entry → append 到 design_patterns.md
4. 記錄到 `audit_history.md`
5. 通知用戶新 pattern 已入庫

---

## Template D: Audit History Entry

```markdown
## [YYYY-MM-DD] — [Agent/Ecosystem Name] — [Score]% — [Grade]

**模式:** Mode [A/B/C]
**Key Findings:**
- [Finding 1 (Confidence: XX)]
- [Finding 2 (Confidence: XX)]

**Actions Taken:**
- [Action 1]
- [Action 2]

**Baseline Change:**
- Previous: [N/A or last score]
- Current: [new score]
```

---

## Template E: Hyper-Detailed Implementation Plan (SDD)

Agent Architect 在起草 Implementation Plan 時必須遵循此格：

```markdown
# [Goal Description]

[Brief objective]

## 1. Architecture Impact (架構影響)
[Describe affected components/modules. If complex, draw a Mermaid graph.]

## 2. File-by-File Micro-Spec (微觀修改規格)
### `path/to/file.py`
- [MODIFY] Line [X]: 具體修改變數名、邏輯、Type Constraints。
- [NEW] 準確的 Function signature 同預期行為。

## 3. Edge Cases Check (邊緣測試與防禦)
1. **[Edge Case 1]**: [How the proposed code handles this]
2. **[Edge Case 2]**: [How the proposed code handles this]
3. **[Edge Case 3]**: [How the proposed code handles this]

## 4. Self-Healing Specs (驗證與自癒指令)
[列出正式交貨前，你自己會於背景執行的驗證指令，例如 `python3 -m py_compile [file]` 或 `pytest [file]`]
```
