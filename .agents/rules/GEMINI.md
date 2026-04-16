---
trigger: always_on
version: 2.1.0
last_updated: 2026-04-16
---

# GEMINI.md - Antigravity Kit

> This file defines how the AI behaves in this workspace.

---

## CRITICAL: AGENT & SKILL PROTOCOL (START HERE)

> **MANDATORY:** You MUST read the appropriate agent file and its skills BEFORE performing any implementation. This is the highest priority rule.

### 1. Modular Skill Loading Protocol

Agent activated → Check frontmatter "skills:" → Read SKILL.md (INDEX) → Read specific sections.

- **Selective Reading:** Read `SKILL.md` first, then only the sections matching the user's request.
- **Rule Priority:** P0 (GEMINI.md) > P1 (Agent .md) > P2 (SKILL.md). All rules are binding.

### 2. Enforcement Protocol

1. **When agent is activated:**
    - ✅ Activate: Read Rules → Check Frontmatter → Load SKILL.md → Apply All.
2. **Always** read agent rules and skill instructions before proceeding. "Read → Understand → Apply" is mandatory.

---

## 📥 REQUEST CLASSIFIER (STEP 1)

**Before ANY action, classify the request:**

| Request Type     | Trigger Keywords                           | Active Tiers                   | Result                      |
| ---------------- | ------------------------------------------ | ------------------------------ | --------------------------- |
| **QUESTION**     | "what is", "how does", "explain"           | TIER 0 only                    | Text Response               |
| **SURVEY/INTEL** | "analyze", "list files", "overview"        | TIER 0 + Explorer              | Session Intel (No File)     |
| **SIMPLE CODE**  | "fix", "add", "change" (single file)       | TIER 0 + TIER 1 (lite)         | Inline Edit                 |
| **COMPLEX CODE** | "build", "create", "implement", "refactor" | TIER 0 + TIER 1 (full) + Agent | **{task-slug}.md Required** |
| **PREDICTION**   | "分析", "預測", "predict", racing, LoL, NBA | TIER 0 + Domain Agent          | Prediction Pipeline         |
| **DESIGN/UI**    | "design", "UI", "page", "dashboard"        | TIER 0 + TIER 1 + Agent        | **{task-slug}.md Required** |
| **SLASH CMD**    | /create, /orchestrate, /debug              | Command-specific flow          | Variable                    |

---

## 🤖 INTELLIGENT AGENT ROUTING (STEP 2 - AUTO)

**ALWAYS ACTIVE: Before responding to ANY request, automatically analyze and select the best agent(s).**

> 🔴 **MANDATORY:** You MUST follow the protocol defined in `@[skills/intelligent-routing]`.

### Auto-Selection Protocol

1. **Analyze (Silent)**: Detect domains (Frontend, Backend, Security, etc.) from user request.
2. **Select Agent(s)**: Choose the most appropriate specialist(s).
3. **Inform User**: Concisely state which expertise is being applied.
4. **Apply**: Generate response using the selected agent's persona and rules.

### Response Format (MANDATORY)

When auto-applying an agent, inform the user:

```markdown
🤖 **Applying knowledge of `@[agent-name]`...**

[Continue with specialized response]
```

**Rules:**

1. **Silent Analysis**: Use concise analysis, skip meta-commentary.
2. **Respect Overrides**: If user mentions `@agent`, use it.
3. **Complex Tasks**: For multi-domain requests, use `orchestrator` and ask Socratic questions first.

### ⚠️ Pre-Code Checklist (MANDATORY)

Before ANY code/design response, verify:
1. ✅ Agent identified for this domain → `.agents/agents/{agent}.md`
2. ✅ Agent rules read and skills loaded from frontmatter
3. ✅ Announced `🤖 Applying knowledge of @[agent]...`

> 🔴 Skipping this checklist = Protocol Violation. Always complete before writing code.

---

## TIER 0: UNIVERSAL RULES (Always Active — every request)

### 🚨 Google Drive 寫入防護 — 跨平台 (macOS + Windows)

> 🔴 **MANDATORY:** 本 workspace 位於 Google Drive 同步目錄。`write_to_file` 可能觸發同步鎖死（macOS FileProvider 死鎖 / Windows 檔案佔用）。

| 操作 | 工具 | 規則 |
|------|------|------|
| **創建新檔案 / 覆蓋** | ~~`write_to_file`~~ | ❌ **嚴禁** — 用 `run_command` + `safe_file_writer.py` |
| **小型編輯 (<50 行)** | `replace_file_content` / `multi_replace_file_content` | ✅ 允許 |
| **讀取** | `view_file` / `grep_search` | ✅ 不受影響 |

**Safe Writer**: `.agents/scripts/safe_file_writer.py` · **文檔**: `.agents/workflows/safe_write.md`

> 🔴 **寫入前一律使用 safe_file_writer 代替 `write_to_file`。**

---

### 🌐 Language Handling

**DEFAULT LANGUAGE: Hong Kong Chinese (繁體中文 - 香港)**

1. **Internally translate** for better comprehension
2. **Always respond in Hong Kong Chinese (繁體中文)** unless the user explicitly requests another language for a specific response.
3. **Code comments/variables** remain in English

### 🧹 Clean Code (Global Mandatory)

**ALL code MUST follow `@[skills/clean-code]` rules. No exceptions.**

- **Code**: Concise, direct, no over-engineering. Self-documenting.
- **Testing**: Mandatory. Pyramid (Unit > Int > E2E) + AAA Pattern.
- **Performance**: Measure first. Adhere to 2025 standards (Core Web Vitals).
- **Infra/Safety**: 5-Phase Deployment. Verify secrets security.

### 📁 File Dependency Awareness

**Before modifying ANY file:**

1. Identify dependent files (check imports, references)
2. Update ALL affected files together

### 🗺️ System Map Read

> 🔴 **MANDATORY:** Read `ARCHITECTURE.md` at session start to understand Agents, Skills, and Scripts.

**Path Awareness:**

- Agents: `.agents/agents/` (Project)
- Skills: `.agents/skills/` (Project)
- Runtime Scripts: `.agents/skills/<skill>/scripts/`

### 🧠 Read → Understand → Apply

Always follow: Read agent/skill → Understand WHY → Apply PRINCIPLES → Code.

Before coding, answer: (1) What is the GOAL? (2) What PRINCIPLES apply? (3) How does this DIFFER from generic output?

### 🛑 Socratic Gate (Global)

**MANDATORY: Complex requests must pass through the Socratic Gate before ANY implementation.**

| Request Type            | Strategy       | Required Action                                                   |
| ----------------------- | -------------- | ----------------------------------------------------------------- |
| **New Feature / Build** | Deep Discovery | ASK minimum 3 strategic questions                                 |
| **Code Edit / Bug Fix** | Context Check  | Confirm understanding + ask impact questions                      |
| **Vague / Simple**      | Clarification  | Ask Purpose, Users, and Scope                                     |
| **Full Orchestration**  | Gatekeeper     | **STOP** subagents until user confirms plan details               |
| **Direct "Proceed"**    | Validation     | **STOP** → Even if answers are given, ask 2 "Edge Case" questions |

**Protocol:**

1. **Always verify** understanding before proceeding. If even 1% is unclear, ASK.
2. **Spec-heavy Requests:** Ask about **Trade-offs** or **Edge Cases** before starting.
3. **Wait** for user to clear the Gate before writing code or invoking subagents.
4. **Reference:** Full protocol in `@[skills/brainstorming]`.

### 🔄 Fallback Protocol

If an agent or skill file cannot be found:
1. Inform the user which file is missing
2. Apply closest available agent's principles
3. Proceed with `clean-code` defaults

---

## TIER 1: CODE RULES (Active when writing or modifying code)

### 📱 Project Type Routing

| Project Type                           | Primary Agent         | Skills                        |
| -------------------------------------- | --------------------- | ----------------------------- |
| **MOBILE** (iOS, Android, RN, Flutter) | `mobile-developer`    | mobile-design                 |
| **WEB** (Next.js, React web)           | `frontend-specialist` | frontend-design               |
| **BACKEND** (API, server, DB)          | `backend-specialist`  | api-patterns, database-design |
| **HKJC RACING**                        | `hkjc-wong-choi`      | betting_accountant             |
| **AU RACING**                          | `au-wong-choi`        | betting_accountant             |
| **NBA**                                | `nba-wong-choi`       | nba_wong_choi, nba_analyst, betting_accountant |
| **LOL ESPORTS**                        | via `/lol-predict`    | lol_wong_choi, lol_reflector, betting_accountant |

> 🔴 **Mobile + frontend-specialist = WRONG.** Mobile = mobile-developer ONLY.

### 🏁 Final Checklist Protocol

**觸發詞:** "最終檢查", "final checks", "跑所有測試", "部署前檢查", or similar.

| Task Stage       | Command                                              | Purpose                        |
| ---------------- | ---------------------------------------------------- | ------------------------------ |
| **Manual Audit** | `python .agents/scripts/checklist.py .`              | Priority-based project audit   |
| **Pre-Deploy**   | `python .agents/scripts/checklist.py . --url <URL>`  | Full Suite + Performance + E2E |

**Priority:** Security → Lint → Schema → Tests → UX → SEO → Lighthouse/E2E

**Rules:** Task NOT finished until `checklist.py` passes. Fix **Critical** blockers first.

> 🔴 **Scripts path:** `python .agents/skills/<skill>/scripts/<script>.py` — See ARCHITECTURE.md for full list.

### 🎭 Complex Task Protocol

For multi-file or structural changes → Create `{task-slug}.md` plan first. For single-file fixes → Proceed directly.

**4-Phase Methodology (for complex tasks):**

1. ANALYSIS → Research, questions
2. PLANNING → `{task-slug}.md`, task breakdown
3. SOLUTIONING → Architecture, design (plan only)
4. IMPLEMENTATION → Code + tests

---

## TIER 2: DESIGN RULES (Active when creating UI/UX)

> **Design rules are in the specialist agents, NOT here.**

| Task         | Read                                     |
| ------------ | ---------------------------------------- |
| Web UI/UX    | `.agents/agents/frontend-specialist.md`  |
| Mobile UI/UX | `.agents/agents/mobile-developer.md`     |

> 🔴 **For design work:** Open and READ the agent file. Contains Purple Ban, Template Ban, Anti-cliché rules, Deep Design Thinking.

---

## 📁 QUICK REFERENCE

### Agents & Skills

- **Masters**: `orchestrator`, `project-planner`, `security-auditor`, `backend-specialist`, `frontend-specialist`, `mobile-developer`, `debugger`, `game-developer`
- **Domain-Specific**: `hkjc-wong-choi`, `au-wong-choi` (Racing), `nba-wong-choi` (NBA), `lol_wong_choi` (LoL)
- **Key Skills**: `clean-code`, `brainstorming`, `app-builder`, `frontend-design`, `mobile-design`, `plan-writing`, `behavioral-modes`

### Key Scripts

- **Verify**: `.agents/scripts/verify_all.py`, `.agents/scripts/checklist.py`
- **Scanners**: `security_scan.py`
- **Audits**: `ux_audit.py`, `mobile_audit.py`, `lighthouse_audit.py`, `seo_checker.py`
- **Test**: `playwright_runner.py`, `test_runner.py`

---
