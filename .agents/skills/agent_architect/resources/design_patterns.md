# Agent Design Patterns & Anti-Patterns

Hard-won lessons from real agent failures. The Agent Architect MUST consult these patterns when designing any agent that involves data extraction, browser automation, or large-scale processing.

---

## Pattern 1: Chunked Processing for Large Data Sources
**Problem**: Browser subagents have a finite context window (~16K tokens). A single page with dense tabular data (e.g., 8000px tall, 12 entities × 8 rows × 11 columns) WILL overflow the subagent, causing infinite retry loops and incomplete output.

**Solution**: Design the agent to process data in **small, bounded chunks** (2-3 items per subagent call). Each chunk should be a self-contained extraction task that returns raw data, to be assembled by the parent agent.

**Anti-pattern**: ❌ "Extract all 12 horses from the Form Guide page"
**Correct pattern**: ✅ "Extract horses 1-2 only. Return raw text. Keep response under 8000 chars."

---

## Pattern 2: Examples ARE the Specification
**Problem**: If the example output file shows only 1 item (e.g., 1 past race per horse), the agent will extract exactly 1 item — even if the instructions say "extract all." The agent treats examples as the ground truth format.

**Solution**: Example files must demonstrate the **complete, realistic** output pattern including:
- Multiple items (not just one)
- Edge cases (empty fields, varying array lengths)
- The exact delimiter/separator format

**Rule**: If the data has repeating sub-entries, the example MUST show at least 3 sub-entries to establish the pattern clearly.

---

## Pattern 3: Separate Extraction from Formatting
**Problem**: When a browser subagent is asked to both extract data AND format it into the final output, it doubles token usage. The extraction fills the context, leaving no room for formatting logic, which triggers overflow.

**Solution**: Enforce a strict separation of concerns:
- **Subagent** → Extract raw data only (return plain text or key-value pairs)
- **Parent agent** → Receive raw data and format it into the required output structure

This halves the subagent's token burden and centralizes formatting logic.

---

## Pattern 4: Verify Tool Availability Before Design
**Problem**: Designing an agent workflow around a tool that doesn't exist in the execution environment (e.g., `browser_execute_js` for browser subagents) wastes the entire planning and implementation cycle.

**Solution**: Before finalizing the agent design:
1. List the **confirmed available tools** in the target environment
2. Design workflows using ONLY confirmed tools
3. If a preferred tool is unavailable, design a fallback using available tools

**Common unavailable tools in browser subagents**: `browser_execute_js`, `run_command`, `write_to_file` (limited paths)

---

## Pattern 5: Explicit Failure Mode Warnings
**Problem**: Instructions like "extract all data from the page" seem clear but hide failure modes. Without explicit warnings, the agent will attempt approaches that are known to fail.

**Solution**: Include `> ⚠️` warnings in skill files for any known failure modes:
- Page size limits (>5000px height = danger zone)
- Data density thresholds (>50 table rows = needs chunking)
- Tool limitations (no JS execution, file path restrictions)

**Format**:
```
> ⚠️ **CRITICAL**: [Page/data source] is [size/density]. 
> DO NOT [specific action that will fail]. 
> INSTEAD, [correct approach].
```

---

## Pattern 6: Scratchpad Accumulation for Multi-Step Tasks
**Problem**: Multi-step extraction tasks lose data between subagent calls because each subagent has isolated context. The parent agent must assemble results but may also lose track across many calls.

**Solution**: Use a temporary scratchpad file to accumulate results:
1. Each subagent writes its chunk to a designated temp file
2. The parent agent reads accumulated results before spawning the next chunk
3. Final formatting reads the complete scratchpad

This creates a persistent data pipeline across the subagent boundary.

---

## Pattern 7: Programmatic Extraction Bridge for Massive Data (Bypassing LLM Context)
**Problem**: Even with chunking (Pattern 1), injecting chunks of a massive webpage (e.g., via `read_browser_page`) can still consume 10,000+ tokens per call just in DOM overhead. This causes instability, high costs, and infinite loops for extremely data-dense pages, and limits speed drastically.

**Solution**: For massive, structured data sources (like deep data tables or recursive data grids), do NOT use the LLM visual or DOM context to read the page. Instead, build a **Programmatic Extraction Bridge**.
- Have the agent write and execute a local headless script (e.g., using Python with `playwright` for JS hydration and `beautifulsoup4` for CSS targeting) in a local `/venv`.
- The script parses the HTML algorithmically with exact CSS selectors and outputs only the final, clean, structured text.
- The agent reads the perfectly filtered text file, keeping token usage minimal, speed high, and accuracy at 100%.

**Rule**: If a page is highly structured but visually massive, abandon `read_browser_page` and switch to a native proxy script to handle the heavy extraction logic.

---

## Pattern 8: Batch Isolation Enforcement
**Problem**: When multiple batches of analysis are combined into a single file write operation, the LLM's attention budget is spread thin. Later batches/items get compressed to 50% or less of the depth of earlier ones. This was observed repeatedly in Race 5-6 analysis sessions.

**Solution**: Enforce strict 1-batch-per-write-operation rule:
- Batch 1 = `run_command` + `safe_file_writer.py --mode overwrite` 建檔
- Batch 2+ = `run_command` + `safe_file_writer.py --mode append` 追加
- Self-check: If about to write 4+ items in one tool call → STOP and split
- **寫入規則（對齊 GEMINI.md P0）：**
  - ❌ `write_to_file` → 嚴禁（Google Drive 同步鎖定風險）
  - ✅ `replace_file_content` / `multi_replace_file_content` → 允許（<50 行小型編輯）
  - ✅ `run_command` + `safe_file_writer.py` → 大量寫入 / 新建文件
- **safe_file_writer.py 相對路徑:** `.agents/scripts/safe_file_writer.py`（從 workspace root 計）
- **🚨 若 safe_file_writer.py 搵唔到 → Fallback 用 OS-native 指令直寫（Windows: `Set-Content`; macOS: `cat >`)，絕對唔可以 fallback 到 `write_to_file`！**

**Anti-pattern**: ❌ "Write all 12 horses to the analysis file"
**Correct pattern**: ✅ "Write Batch 1 (horses 1-3), then separately append Batch 2 (horses 4-6)..."

---

## Pattern 9: Anti-Pre-Judgment Shortcut
**Problem**: When the model anticipates a low rating (e.g., D grade) for an item, it unconsciously compresses the analysis — collapsing independent sections into inline notes, skipping paragraphs, or merging multi-line content into single lines. The output appears complete at a glance but lacks the required independent paragraph structure.

**Solution**: Enforce "analysis before rating" — every item must complete ALL mandatory sections as independent paragraphs BEFORE the final rating is assigned. Include a structural self-check list after each item.

**Detection**: If any section that should be an independent paragraph (≥2 lines with bold header) appears as an inline mention within another section → structural violation.

---

## Pattern 10: Session Recovery
**Problem**: Long-running pipelines (e.g., 8-race analysis taking 3+ hours) frequently hit context window limits or session interruptions. Without recovery, the user must restart from scratch.

**Solution**: At initialization, scan the output directory for previously completed work:
1. Check for existing output files (e.g., `*_Analysis.txt`)
2. List completed items and notify user
3. Ask: "Resume from item [X]?"
4. Skip completed items, continue from first incomplete

**Key**: Recovery detection MUST happen at Step 1 (before any new work begins).

---

## Pattern 11: Forced Checkpoints
**Problem**: Agents that auto-pilot through entire pipelines without pausing often accumulate errors that are only discovered at the end. Users lose visibility and control.

**Solution**: Insert mandatory pause points at critical transitions:
- After data extraction (before analysis begins)
- After each major unit of work (e.g., each race)
- Before irreversible actions (e.g., file deletion, report generation)

Format: Present summary + ask user to confirm before proceeding.
Exception: Within a batch, auto-proceed (don't ask per-item).

---

## Pattern 12: Tiered Quality Gates
**Problem**: A single quality check at the end of a pipeline only catches issues after all work is done. Reanalysing everything is expensive.

**Solution**: Use TWO levels of quality assurance:
1. **Lightweight QA** (per-batch): Structural completeness, word count, duplicate detection. Fast, immediate feedback loop.
2. **Heavyweight QA** (per-race/per-unit): Full audit including rule compliance, cross-reference validation, self-improvement scan. Runs after all batches complete.

Benefit: Structural errors caught early (before full race is done), while systemic issues caught at unit boundary.

**Anti-pattern**: ❌ Putting both QA levels inside the orchestrator's prompt
**Correct pattern**: ✅ Lightweight QA as a dedicated agent; heavyweight QA as another dedicated agent

---

## Pattern 13: Intelligence Package File
**Problem**: Meeting-level context (weather, track bias, etc.) collected by the orchestrator is trapped in its context window. If the session breaks or a different agent needs it, the data is lost.

**Solution**: Write shared intelligence to a file in the output directory (e.g., `_Meeting_Intelligence_Package.md`). All downstream agents read this file directly instead of receiving the data through the orchestrator.

Benefit: Cross-session reuse, orchestrator context window relief, single source of truth.

---

## Pattern 14: Heredoc / Terminal Hang Prevention
**Problem**: Using `cat << EOF` or heredoc syntax via `run_command` to write large text blocks causes terminal processes to hang indefinitely. Known production incident: 9+ hour hang.

**Solution**: All analysis/report file writing MUST use the Safe-Writer Protocol:
- **首選:** `run_command` + `safe_file_writer.py`（base64 編碼 → 原子寫入）
- **次選:** OS-native 指令（Windows: PowerShell `Set-Content`; macOS: `cat >`）
- **寫入規則（對齊 GEMINI.md P0）：**
  - ❌ `write_to_file` → 嚴禁
  - ✅ `replace_file_content` / `multi_replace_file_content` → 允許（<50 行小型編輯）
  - ✅ `run_command` + scripts → 大量寫入

Include this as an explicit ⚠️ CRITICAL warning in any agent that writes files.

---

## Pattern 15: Reflector → Architect Feedback Loop
**Problem**: Post-deployment failures and new anti-patterns discovered by Reflector agents are not automatically fed back to the Agent Architect. New agents repeat the same mistakes.

**Solution**: After each Reflector session that discovers new failure patterns:
1. Reflector proposes a new design pattern entry
2. User approves the pattern
3. Pattern is appended to `design_patterns.md` with: pattern name, source, date, severity
4. Agent Architect references these patterns in Step 3 (Robustness Checklist)

This creates a continuous improvement loop: Deploy → Fail → Learn → Prevent.

---

## Pattern 16: Session State Persistence
**Problem**: When long-running pipelines span multiple sessions (due to context window limits), downstream agents in the new session lose critical state: quality baselines, completed work tracking, accumulated issue logs.

**Solution**: Write session state to a persistent file (e.g., `_session_state.md`) in the output directory:
```
# Session State
- BATCH_BASELINE: [X words per horse]
- COMPLETED_RACES: [1, 2, 3, 4, 5]
- LAST_COMPLETED_BATCH: Race 5, Batch 4
- QUALITY_TREND: [Stable / Declining / Improving]
```

At session start, check for this file and resume from saved state rather than recomputing.

**Combines with**: Pattern 10 (Session Recovery) — Pattern 10 detects completed FILES; Pattern 16 preserves in-flight STATE.

---

## Pattern 17: Advanced Agentic Toolchain Selection
**Problem**: As the `.agents` ecosystem grows, relying entirely on simple Python scripts and single-shot Prompt Engineering leads to brittle execution (File I/O hangs, formatting drift, and poor multi-dimensional judgments). 

**Solution**: The Agent Architect MUST prescribe specialized frameworks based on the exact problem domain, keeping in mind the **Zero-Cost Principle**:
1. **Safe-Writer Protocol (Stability)**: Prescribe for ALL agents that perform Google Drive File I/O. Uses `run_command` + `safe_file_writer.py` (base64 → atomic write) to eliminate sync lock issues (macOS FileProvider / Windows FileStream). 寫入規則：`write_to_file` 嚴禁; `replace/multi_replace` 允許 <50 行; 大量寫入用 `safe_file_writer.py`。
2. **Native Python Validation Engine (Compliance)**: Prescribe when an agent needs a **Linear Pipeline** with strict Output Formatting (e.g., Data Prep → Analysis → QA Edit). Use Python assertions and string matching (e.g., `completion_gate_v2.py`) to ensure the output format is 100% compliant with templates, completely avoiding expensive framework overhead like CrewAI.
3. **Embedded Protocol Checkpoints (Debate/Consensus)**: Prescribe for **Debate and Consensus** scenarios (e.g., NBA Wong Choi or AU Wong Choi). Instead of dispatching multiple LLM agents (like Microsoft AutoGen), embed a Multi-Perspective Protocol directly into the single agent's prompt, forcing it to debate itself step-by-step before culminating in a verdict.
4. **curl_cffi/Playwright (Extraction)**: Native web execution protocols that are adequate for 99% of stealth web scraping, completely replacing the need for paid/heavy third party extractors.

---

## Pattern 18: Zero-Cost Multi-Perspective Analysis Protocol (SIP-DA01)
**Problem**: Advanced AI frameworks (like AutoGen, CrewAI, LangChain) impose high API costs, complex system dependencies, and Docker-bound execution environments. Multi-agent debate is expensive. Relying on them destroys portability across standard macOS/Windows host environments.

**Solution**: Simulate multi-agent dialogue and debate within a **single API call** by embedding structured multi-perspective analytical protocols (e.g. `[SIP-DA01]`) directly into the orchestration prompts. By forcing the Agent to conduct a sequential mock-debate (e.g., "Step A: Form Selection -> Step B: Track/Pace Challenge -> Step C: Place Probability Audit") before finalization, we achieve the same analytical depth and critical rigor of Multi-Agent Systems with **ZERO added dependency and ZERO overhead cost**.

**Rule**: Always design Multi-Perspective protocols natively in markdown instructions rather than introducing heavy third-party framework dependencies.

---

## Pattern 19: Cross-Platform Agent Design
**Problem**: Agents designed on macOS contain hardcoded paths (`/tmp`, `/Users/...`), shell-specific syntax (`cat <<EOF`, `cp`), and OS-specific assumptions. When the workspace moves to Windows (or vice versa), agents break silently — scripts fail, file writes hang, and paths resolve to nothing.

**Solution**: All agent designs MUST be OS-agnostic:
1. **Paths**: Use relative paths from workspace root (e.g., `.agents/scripts/`), never absolute OS paths
2. **File Writing**: Use `safe_file_writer.py` (Python — cross-platform) as primary, OS-native commands as fallback
3. **Shell Syntax**: Avoid heredoc (`cat <<EOF`), backtick subshells, and Unix-only pipes in agent instructions. Use Python scripts for complex text assembly
4. **Environment Detection**: If an agent truly needs OS-specific behaviour, include explicit branching:
   ```
   Windows: PowerShell `Set-Content`, `Get-Content`
   macOS/Linux: `cat >`, `cp`, shell heredoc
   ```
5. **Testing**: When prescribing a new script, verify it runs on both Python (Windows) and python3 (macOS)

**Anti-pattern**: ❌ Hardcoding `/Users/imac/Library/CloudStorage/...` or `/tmp/output.txt`
**Correct pattern**: ✅ Using `.agents/scripts/safe_file_writer.py` with `--target` relative path

---

## Pattern 20: Health Check Confidence Scoring
**Problem**: Binary ✅/❌ Health Check ratings lose nuance. A minor naming inconsistency (❌) appears equally severe as a critical security gap (❌). Reviewers waste time on low-impact findings while missing the truly dangerous ones.

**Solution**: Every Health Check finding MUST include a **confidence score (0-100)** alongside the ✅/⚠️/❌ rating:

| Score | Meaning |
|:---:|:---|
| 0-25 | Cosmetic / style preference — fix if convenient |
| 26-50 | Minor inconsistency — should fix before production |
| 51-75 | Significant gap — must fix, impacts reliability |
| 76-100 | Critical defect — blocks production, known failure mode |

**Reporting threshold**: Only include findings with score ≥ 30 in the summary. Bundle 0-29 scores into an appendix.

**Format**:
```
| # | Check | Rating | Confidence | Note |
|---|-------|--------|------------|------|
| B5 | File Writing Protocol | ❌ | 95 | macOS paths on Windows — confirmed broken |
| D3 | Ecosystem sync | ⚠️ | 40 | Missing 3 groups — cosmetic, no runtime impact |
```

**Combines with**: Pattern 12 (Tiered Quality Gates) — confidence scores enable automatic triage into CRITICAL vs MINOR remediation tiers.

---

## Pattern 21: Reflection-Driven Pattern Ingestion
**Problem**: Reflector agents (HKJC/AU/NBA) learn from real-world failures and propose new design patterns (SIPs). But these proposals require manual copy-paste to update `design_patterns.md`. Without a systematic intake process, valuable lessons get lost between sessions.

**Solution**: Agent Architect MUST process Reflector proposals through a graded intake pipeline:

```
Reflector submits proposal (Template C format)
         ↓
Agent Architect receives → run_command agent_health_scanner.py to check for duplicates
         ↓ NOT duplicate
Evaluate Impact Score (0-100):
  ≥76 Critical  → One-line user confirmation ("Pattern X (95) — 入庫？")
  51-75 Important → Show summary, ask user to confirm
  26-50 Minor    → Queue for next audit cycle (record in audit_history.md)
  0-25 Cosmetic  → Log but don't ingest
         ↓ User Confirmed
Format as standard Pattern entry → append to design_patterns.md
         ↓
Update audit_history.md with ingestion record
         ↓
List affected agents → suggest re-audit
```

**Non-Degradation Policy**: Before ingestion, verify the new pattern does not contradict any existing pattern. If conflict detected → present both to user for resolution.

**Anti-pattern**: ❌ Auto-ingesting patterns without user confirmation
**Correct pattern**: ✅ Graded confirmation with impact scoring

---

## Pattern 22: Python-First Offloading（減壓原則）
**Problem**: LLMs waste context window, hallucinate, and burn tokens on deterministic tasks that a Python script can handle perfectly in milliseconds. Observed failure modes:
- Math errors in odds calculation (EEM, win probability)
- Template drift from copy-paste (missing fields, format inconsistency)
- Slow file scanning that could be instant with `grep`/`pathlib`
- JSON/CSV format errors from manual LLM generation

**Solution**: When designing any agent, apply the **Python-First Decision Matrix**:

| Task Type | Assign To | Reason |
|:---|:---:|:---|
| Math calculation | 🐍 Python | LLM arithmetic error rate is high |
| Template filling / Copy-paste | 🐍 Python | Reduces context pressure + prevents omissions |
| Format conversion (JSON/CSV/MD) | 🐍 Python | 100% precision, zero tokens |
| File scanning / grep / diff | 🐍 Python | Fast + doesn't consume context |
| Data validation (schema check) | 🐍 Python | Deterministic judgment |
| Strategic reasoning / analysis | 🧠 LLM | Core LLM strength |
| Multi-dimensional weighted evaluation | 🧠 LLM | Requires domain knowledge |
| Anomaly detection / blind spot analysis | 🧠 LLM | Requires creative reasoning |
| Edge case handling | 🧠 LLM | Requires contextual judgment |

**Design-Time Self-Check** (MANDATORY when building new agents):
> "Can this step achieve 100% accuracy with a Python script?"
> If YES → MUST build a script. Do NOT let the LLM do it.
> If NO (requires judgment / reasoning / creativity) → LLM does it.

**Benefits:**
- 🎯 **Accuracy**: Scripts are deterministic — zero hallucination for mechanical tasks
- 💰 **Token Savings**: A 200-line Python scan replaces thousands of LLM context tokens
- 🧠 **Focus**: LLM context window is freed for what it's actually good at — logic and judgment
- ⚡ **Speed**: Script execution in ms vs LLM reasoning in seconds

**Anti-pattern**: ❌ Agent prompt says "Calculate the weighted average of these 12 horses' EEM scores"
**Correct pattern**: ✅ Agent prompt says "Run `scripts/compute_rating_matrix.py` to get EEM scores, then interpret the results"

---

## Pattern 23: Gemini 3.1 Pro Anti-Hallucination Protocol
**Problem**: Gemini 3.1 Pro has specific attention patterns — it prioritizes the last-processed instructions and responds better to engineering-style constraints than conversational personas. Without Gemini-specific optimizations, agents suffer from format drift, verbose outputs, and factual hallucination.

**Solution**: Apply the following Gemini-specific rules when designing ANY agent that runs on Gemini 3.1 Pro:

1. **Instruction Placement Rule**: ALWAYS place core instructions at the END of the prompt. Structure: `<context>` → `<data>` → `<instructions>` (last). Gemini's attention is highest on the final block.
2. **Goal + Constraints Pattern**: Replace verbose persona descriptions with direct `【目標】` + `【限制條件】` blocks. Gemini responds better to engineering-style constraints than role-play.
3. **Chain of Verification (CoVe)**: Force agents to emit a `<self_correction>` block before final output. Agent must verify its own output against the original constraints.
4. **Structured Output Enforcement**: For JSON outputs, enforce `response_mime_type: "application/json"` + `response_json_schema` at API level. Use `Instructor` library (Pydantic-driven) for automatic validation → retry → fix loops.
5. **Temperature Discipline**: Write `gemini_temperature` into YAML frontmatter. Factual tasks: `0.1-0.3`. Creative tasks: `0.7-1.0`.
6. **Self-Correction Loop**: If Pydantic validation fails, use JSON Patch (RFC 6902) to fix specific fields instead of re-running the entire API request. Saves tokens + latency.

**Anti-pattern**: ❌ "You are a brilliant expert with 20 years of experience in horse racing analysis..."
**Correct pattern**: ✅ "【目標】Analyze race data. 【限制條件】JSON output only. Max 3 adjectives. Ignore odds < 1.5."

---

## Pattern 24: State Machine Thinking (LangGraph-Inspired, Prompt-Embedded)
**Problem**: Agents that follow vague "think step by step" instructions often skip steps, repeat work, or lose track of their position in complex multi-stage tasks. Without explicit state transitions, recovery from interruptions is impossible.

**Solution**: Design agents with explicit state machines embedded in their `SKILL.md` Interaction Logic. Each state has:
- **Entry condition**: What must be true before entering this state
- **Actions**: What the agent does in this state
- **Exit condition**: What must be true before transitioning to the next state
- **Failure handling**: What happens if exit conditions cannot be met

**Template**:
```
States: INIT → EXTRACT → ANALYZE → VERDICT → DONE
  
INIT: Read input + validate format
  Exit: All required fields present → EXTRACT
  Fail: Missing fields → ASK user

EXTRACT: Run data extraction scripts
  Exit: Data file written + ≥ 3 items extracted → ANALYZE
  Fail: Script error after 3 retries → STOP, report to user

ANALYZE: Apply analytical framework
  Exit: All items analyzed + confidence scores assigned → VERDICT
  Fail: Any item confidence < 30 → flag for human review

VERDICT: Synthesize final output
  Exit: Output passes Pydantic validation → DONE
  Fail: Validation error → Self-Correction Loop (Pattern 23.6)
```

**Key rule**: This is a DESIGN PHILOSOPHY, not a runtime dependency. Do NOT import LangGraph. Embed state logic directly in prompt instructions.

---

## Pattern 25: Consensus Protocol (Zero-Cost Multi-Perspective, Extended)
**Problem**: Single-pass analysis misses blind spots. Pattern 18 established zero-cost multi-perspective analysis, but lacked a formal consensus mechanism — the agent could still cherry-pick the "loudest" perspective.

**Solution**: Extend Pattern 18 with a mandatory **Weighted Consensus Gate**:

1. Agent conducts sequential multi-perspective analysis (as per Pattern 18)
2. Each perspective assigns an independent score (0-100)
3. **Consensus Gate**: If all perspectives agree (spread < 15 points) → proceed. If disagreement detected (spread ≥ 15 points) → agent must write a `⚠️ SPLIT VERDICT` section explaining the disagreement and present BOTH conclusions to the user.

**Benefit**: Prevents the agent from silently resolving internal contradictions. User sees disagreement explicitly.

**Combines with**: Pattern 18 (Zero-Cost Multi-Perspective), Pattern 20 (Confidence Scoring)

---

## Pattern 26: Execution Journal (Structured Agent Logging)
**Problem**: When agents fail, there is no structured record of what happened. Debugging relies on reading raw conversation logs — which are unstructured, massive, and cross-session. Advanced diagnostic tools (GEPA trace analysis, Langfuse import, Mode D replay) all require structured execution data that does not exist.

**Solution**: ALL agents must write a lightweight execution journal during task execution:

**Format** (append to `_execution_log.md` via `safe_file_writer.py --mode append`):
```
> 📝 LOG: Step [name] | Tool: [tool_used] | Result: [Success/Fail] | Notes: [brief]
```

**Rules**:
1. One log line per major step (NOT per micro-action — avoid flooding)
2. Log MUST include: step name, tool used, success/fail, and any error message if failed
3. Log file location: same directory as the agent's output files
4. Writing method: `safe_file_writer.py --mode append` (Pattern 8 compliant)
5. Journal is APPEND-ONLY — never overwrite previous entries

**Example**:
```
> 📝 LOG: Step 1 Data Extract | Tool: run_command nba_scraper.py | Result: Success | Notes: 12 players extracted
> 📝 LOG: Step 2 Analysis | Tool: LLM reasoning | Result: Success | Notes: All items scored
> 📝 LOG: Step 3 Write Report | Tool: safe_file_writer.py | Result: Fail | Notes: Permission denied on output path
> 📝 LOG: Step 3 Retry | Tool: safe_file_writer.py --target alt_path | Result: Success | Notes: Wrote to fallback path
```

**Combines with**: Pattern 10 (Session Recovery), Pattern 16 (Session State Persistence)

---

## Pattern 27: Version Control & Rollback for Agent Modifications
**Problem**: When Agent Architect modifies a `SKILL.md` (via Mode B optimization or Reflexion auto-fix), there is no way to undo the change if the new version performs worse. Without versioning, a single bad edit can permanently degrade an agent.

**Solution**: Enforce a strict **Snapshot Before Modify** protocol:

1. **Before ANY `SKILL.md` modification**, Architect must copy the current file to:
   ```
   resources/archive/SKILL_v{YYYYMMDD}.md
   ```
2. **After modification**, run evaluation (DeepEval / Promptfoo) comparing new vs old version
3. **Auto-rollback trigger**: If new version scores drop > 10% on any metric → automatically restore from snapshot and notify user
4. **Audit trail**: All modifications recorded in `resources/audit_history.md` with:
   - Date, modifier (Architect/Reflector/User), change summary, before/after scores

**Anti-pattern**: ❌ Directly editing SKILL.md without backup
**Correct pattern**: ✅ Snapshot → Edit → Evaluate → Commit (or Rollback)

**Combines with**: Pattern 21 (Reflection-Driven Ingestion), Pattern 20 (Confidence Scoring)

---

## Pattern 28: Sports Analytics Toolbox Blueprint (Wong Choi Engine)
**Problem**: Wong Choi agents (Horse Racing, NBA, LoL) need quantitative depth beyond surface-level analysis. Without a standardized toolkit, each agent reinvents the wheel for probability models, risk management, and data sourcing.

**Solution**: When designing or optimizing ANY Wong Choi agent, Agent Architect must reference the following toolkit blueprint and guide the user to build the appropriate Python scripts:

### 🏇 Horse Racing (HKJC + AU)
| Capability | Python Tool | Script to Build |
|:---|:---|:---|
| True Probability Model | `sklearn.LogisticRegression` or `xgboost` | `scripts/ev_model.py` |
| Expected Value (EV) | Formula: `EV = (True_Prob × Decimal_Odds) - 1` | Embed in verdict template |
| Kelly Criterion Staking | `sports-betting` package or pure math | `scripts/kelly_calculator.py` |
| Time-Series Backtesting | `sklearn.TimeSeriesSplit` (anti look-ahead bias) | `scripts/backtest_engine.py` |
| Feature Engineering | L400, weight change, pace, EEM + `StandardScaler` | `scripts/feature_pipeline.py` |
| Velocity Profile (1D) | Sectional times → speed curve → deceleration point | `scripts/velocity_profiler.py` |

### 🏀 NBA
| Capability | Python Tool | Script to Build |
|:---|:---|:---|
| Official Stats | `nba_api` + `pandas` | `scripts/nba_data_fetcher.py` |
| Play-by-Play / On-Off | `pbpstats` | `scripts/lineup_chemistry.py` |
| Free Box Score API | `balldontlie` API (no key needed) | `scripts/boxscore_fetcher.py` |
| Injury Impact Model | PIE + Tracking Data → regression | `scripts/injury_impact.py` |

### 🎮 LoL Esports
| Capability | Python Tool | Script to Build |
|:---|:---|:---|
| Pro Match Data | `mwclient` → Leaguepedia Cargo SQL | `scripts/lol_data_fetcher.py` |
| Historical Analysis | `pandas` → Oracle's Elixir datasets | `scripts/lol_team_ratings.py` |
| EGR/MLR Rating | Early Game Rating + Mid/Late Rating | Embed in analysis template |

**Key rules**:
1. ALL quantitative calculations → Python scripts (Pattern 22). LLM only interprets results.
2. Agent must NEVER hardcode odds or probabilities — always compute from data.
3. Backtesting must use TimeSeriesSplit — NEVER random cross-validation on time-series data.
4. If a script dependency is not installed, Architect must prompt user with `pip install` command before proceeding.

**Anti-pattern**: ❌ Agent says "This horse has about a 30% chance based on my analysis"
**Correct pattern**: ✅ Agent runs `ev_model.py` → outputs "True Prob: 0.312, Market Odds: 4.2, EV: +0.31 ✅ Value Bet"

---
