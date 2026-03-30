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
- Batch 1 = `write_to_file` (create new file)
- Batch 2+ = individual `replace_file_content` (append to file)
- Self-check: If about to write 4+ items in one tool call → STOP and split

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

**Solution**: NEVER use heredoc for writing analysis/report content. Use dedicated file writing tools:
- `write_to_file` for new files
- `replace_file_content` for appending/editing
- `run_command` ONLY for executing scripts (Python, shell)

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
