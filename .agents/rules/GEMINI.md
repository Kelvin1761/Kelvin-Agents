# GEMINI.md

> Deprecated for onboarding and day-to-day use. Keep only for legacy tool compatibility.

## Legacy Compatibility Note

呢份文件仲保留喺 repo，主要原因係：

- 某啲外部 agent / editor integration 仍然會預設查找 `GEMINI.md`
- 舊文檔、舊 snapshot、舊操作習慣可能仍然會引用呢個路徑

但對目前 Antigravity 主線而言，請先知道以下事實：

- `HKJC Wong Choi` 已經係 **full Python pipeline**
- `AU Wong Choi` 已經係 **full Python pipeline**
- 運行 HKJC / AU 主流程 **唔需要 Gemini**
- 運行 HKJC / AU 主流程 **唔需要任何 LLM**

## Current Source Of Truth

請優先閱讀：

1. [`AGENTS.md`](../../AGENTS.md)
2. [`SETUP.md`](../../SETUP.md)
3. [`.agents/ARCHITECTURE.md`](../ARCHITECTURE.md) 只作高層 folder map 參考

## Minimal Guidance For External Agents

如果你係透過舊 integration 讀到呢份檔，請按以下原則理解 repo：

1. 先 inspect 真實 repo structure、scripts 同 active entrypoints，唔好沿用舊 prompt 假設。
2. HKJC 主入口係 `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py`。
3. AU 主入口係 `.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py`。
4. 若已經有 `Race_X_Logic.json`，優先用對應 auto orchestrator 重跑 deterministic engine。
5. 文檔若同實際 code 不一致，以實際 code 為準，並應先更新文檔。

## Historical Note

Antigravity 早期確實大量依賴 LLM-oriented skeleton、prompting rules 同 Gemini-style operational guidance。呢段歷史仍然反映喺：

- 某啲 archived scripts
- 某啲 legacy resources
- 部分未完全移除嘅舊名詞

但呢啲已經唔應該令新用戶誤會：

- `HKJC Wong Choi` 需要 Gemini
- `AU Wong Choi` 需要 Gemini
- 生成最終分析一定要經 LLM

以上三點，現況全部都唔正確。
