# Plugin Skill Blueprints — Complete Reference

Extracted blueprints from ALL official Claude Code plugins. Use these when designing agents that need equivalent capabilities — no plugin installation required.

**Table of Contents**:
- [1. Code Simplifier](#blueprint-1) — Autonomous code refinement
- [2. Code Reviewer](#blueprint-2) — Multi-agent PR review with confidence scoring
- [3. Agent SDK Dev](#blueprint-3) — SDK app wizard + verification agents
- [4. CLAUDE.md Management](#blueprint-4) — Audit/improve CLAUDE.md + session learning capture
- [5. Claude Code Setup](#blueprint-5) — Automation recommender (hooks, MCP, skills, subagents)
- [6. Commit Commands](#blueprint-6) — Git commit, push, PR workflow
- [7. Feature Dev](#blueprint-7) — 7-phase guided feature development
- [8. Frontend Design](#blueprint-8) — Distinctive UI creation, anti-AI-slop aesthetics
- [9. Hookify](#blueprint-9) — Rule-based hook automation from conversation analysis
- [10. PR Review Toolkit](#blueprint-10) — 6 specialised review agents
- [11. Plugin Dev](#blueprint-11) — 8-phase plugin creation workflow
- [12. Skill Creator](#blueprint-12) — Skill creation, eval, benchmarking, description optimisation
- [13. Security Guidance](#blueprint-13) — PreToolUse security pattern detection
- [14. Explanatory Output Style](#blueprint-14) — Educational insights mode
- [15. Learning Output Style](#blueprint-15) — Interactive learning + educational mode
- [16. Playground](#blueprint-16) — Interactive HTML playground builder
- [17. Ralph Loop](#blueprint-17) — Continuous self-referential iteration loops
- [18-29. LSP Plugins](#blueprint-18) — Language server integrations (12 languages)
- [30. Example Plugin](#blueprint-30) — Reference plugin structure
- [31. Antigravity](#blueprint-31) — Internal racing/sales agents (our own)

---

<a id="blueprint-1"></a>
## Blueprint 1: Code Simplifier

**Source Plugin**: `code-simplifier`
**Type**: Background subagent (autonomous, runs after code is modified)
**Model**: Opus

### Core Capability
Simplifies and refines code for clarity, consistency, and maintainability while preserving ALL functionality. Focuses on recently modified code unless instructed otherwise.

### Design Pillars

**1. Preserve Functionality**: Never change what the code does — only how it does it.

**2. Apply Project Standards**: Follow CLAUDE.md coding standards (ES modules, `function` keyword preference, explicit return types, React Props types, error handling patterns, naming conventions).

**3. Enhance Clarity**:
- Reduce complexity and nesting
- Eliminate redundant code/abstractions
- Improve variable/function names
- Consolidate related logic
- Remove obvious comments
- AVOID nested ternaries — prefer switch/if-else
- Choose clarity over brevity

**4. Maintain Balance**: Don't over-simplify. Avoid overly clever solutions, don't combine too many concerns, don't remove helpful abstractions.

**5. Focus Scope**: Only refine recently modified code.

### Process
1. Identify modified code → 2. Analyse opportunities → 3. Apply project standards → 4. Verify functionality preserved → 5. Confirm simpler/more maintainable → 6. Document significant changes

### Key Design Note
Operates autonomously and proactively — refines code immediately after modification without explicit requests.

---

<a id="blueprint-2"></a>
## Blueprint 2: Code Reviewer (Multi-Agent PR Review)

**Source Plugin**: `code-review`
**Type**: Slash command (`/code-review`)
**Architecture**: Multi-agent pipeline with confidence scoring

### Multi-Agent Pipeline

| Phase | Agent | Model | Task |
|-------|-------|-------|------|
| 1 | Eligibility Check | Haiku | Is PR closed/draft/automated/already reviewed? |
| 2 | Context Gather | Haiku | Find relevant CLAUDE.md files |
| 3 | PR Summary | Haiku | Summarise the change |
| 4a | CLAUDE.md Compliance | Sonnet | Audit changes against CLAUDE.md rules |
| 4b | Bug Scanner | Sonnet | Shallow scan for obvious bugs in diff |
| 4c | Historical Context | Sonnet | Git blame/history for context-aware bugs |
| 4d | Previous PR Comments | Sonnet | Check if past comments apply |
| 4e | Code Comment Compliance | Sonnet | Verify changes comply with code comments |
| 5 | Confidence Scoring | Haiku (per issue) | Score 0-100, filter <80 |
| 6 | Re-check Eligibility | Haiku | Confirm PR still eligible |
| 7 | Post Comment | — | `gh pr comment` with structured format |

Phase 4 agents run **in parallel**. Phase 5 agents run **in parallel** (one per issue).

### Confidence Scale
- **0**: False positive / pre-existing
- **25**: Might be real, unverified. Stylistic not in CLAUDE.md
- **50**: Real but nitpick or unimportant
- **75**: Very likely real, impacts functionality, or in CLAUDE.md
- **100**: Definitely real, frequent, evidence confirms

### False Positive Exclusions
Pre-existing issues, pedantic nitpicks, linter-catchable issues, general quality (unless CLAUDE.md requires), silenced lint issues, intentional changes, issues on unmodified lines.

### Output Format
```markdown
### Code review
Found N issues:
1. <description> (CLAUDE.md says "<...>")
   <link with full SHA + L[start]-L[end]>
```

Uses `gh` CLI only. Full git SHA required. Does NOT run builds/linters.

---

<a id="blueprint-3"></a>
## Blueprint 3: Agent SDK Dev

**Source Plugin**: `agent-sdk-dev`
**Components**: 1 slash command + 2 verification agents

### 3A. New SDK App Creator (`/new-sdk-app [name]`)

**Interactive wizard** — one question at a time:
1. Language? (TypeScript / Python)
2. Project name?
3. Agent type? (Coding/Business/Custom)
4. Starting point? (Hello World / Basic / Use-case specific)
5. Tooling choice? (npm/yarn/pnpm/bun or pip/poetry)

Then: Reference docs via WebFetch → Setup plan → Install SDK → Create starter files → Environment setup → **Verify (MANDATORY)**: `npx tsc --noEmit` for TS, syntax check for Python → Launch verifier agent → Getting Started Guide.

### 3B. TypeScript SDK Verifier (Sonnet agent)

Checks: SDK installed + current, `"type": "module"`, tsconfig.json, correct imports, agent init patterns, `npx tsc --noEmit`, package.json scripts, `.env.example`, no hardcoded keys, system prompts, model selection, permissions, README.

Report: PASS / PASS WITH WARNINGS / FAIL + Issues + Recommendations.

### 3C. Python SDK Verifier (Sonnet agent)

Same structure for Python: `claude-agent-sdk` in requirements.txt, Python 3.8+, `claude_agent_sdk` imports, syntax validation.

---

<a id="blueprint-4"></a>
## Blueprint 4: CLAUDE.md Management

**Source Plugin**: `claude-md-management`
**Components**: 1 skill (audit/improve) + 1 slash command (session learning)

### 4A. CLAUDE.md Improver (Skill)

**5-Phase Workflow**: Discovery → Quality Assessment → Report → Targeted Updates → Apply.

**Quality Scoring** (100 total):
| Criterion | Weight |
|-----------|--------|
| Commands/workflows | 20pts |
| Architecture clarity | 20pts |
| Non-obvious patterns | 15pts |
| Conciseness | 15pts |
| Currency | 15pts |
| Actionability | 15pts |

Grades: A (90-100), B (70-89), C (50-69), D (30-49), F (0-29).

Updates: Show diffs with rationale. Only add genuinely useful info. Keep minimal.

### 4B. Revise CLAUDE.md (`/revise-claude-md`)

Review session for learnings → Find CLAUDE.md files → Draft additions (one line per concept) → Show proposed diffs → Apply with approval.

**Add**: Commands, gotchas, package relationships, testing approaches, config quirks.
**Don't add**: Obvious info, generic best practices, one-off fixes, verbose explanations.

---

<a id="blueprint-5"></a>
## Blueprint 5: Claude Code Setup (Automation Recommender)

**Source Plugin**: `claude-code-setup`
**Type**: Read-only analysis skill

### Workflow
1. **Codebase Analysis**: Detect language, framework, dependencies, testing, CI/CD, issue tracking
2. **Generate Recommendations**: 1-2 per category (Hooks, MCP Servers, Skills, Subagents, Plugins)
3. **Output Report**: Structured markdown with implementation details

### Recommendation Tables

**Hooks** (`.claude/settings.json`):
| Signal | Hook |
|--------|------|
| Prettier | PostToolUse: auto-format |
| ESLint/Ruff | PostToolUse: auto-lint |
| TypeScript | PostToolUse: type-check |
| Tests dir | PostToolUse: run tests |
| .env files | PreToolUse: block edits |
| Lock files | PreToolUse: block edits |

**MCP Servers** (`.mcp.json`):
| Signal | Server |
|--------|--------|
| Popular libs | context7 (live docs) |
| Frontend UI | Playwright |
| Supabase | Supabase MCP |
| PostgreSQL | Database MCP |
| GitHub | GitHub MCP |
| AWS SDK | AWS MCP |
| Sentry | Sentry MCP |

**Skills** (`.claude/skills/<name>/SKILL.md`): api-doc, create-migration, gen-test, new-component, pr-check, release-notes, project-conventions, setup-dev.

**Subagents** (`.claude/agents/<name>.md`): code-reviewer, security-reviewer, api-documenter, performance-analyser, ui-reviewer, test-writer.

---

<a id="blueprint-6"></a>
## Blueprint 6: Commit Commands

**Source Plugin**: `commit-commands`
**Components**: 3 slash commands

### 6A. `/commit` — Create a Git Commit

**Allowed tools**: `git add`, `git status`, `git commit`

**Dynamic context injection** (injected before command runs):
```
- Current git status: !`git status`
- Current git diff: !`git diff HEAD`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`
```

Stage and commit in a single message. No other tools or text.

### 6B. `/commit-push-pr` — Full Workflow

**Allowed tools**: `git checkout --branch`, `git add`, `git status`, `git push`, `git commit`, `gh pr create`

1. Create new branch if on main
2. Create single commit with appropriate message
3. Push branch to origin
4. Create PR using `gh pr create`
5. All in a single message — no other tools or text.

### 6C. `/clean_gone` — Branch Cleanup

Cleans up local branches marked as `[gone]` (deleted on remote):
1. List branches (`git branch -v`)
2. Identify worktrees (`git worktree list`)
3. Remove worktrees for gone branches, then delete branches (`git branch -D`)

---

<a id="blueprint-7"></a>
## Blueprint 7: Feature Dev (Guided Feature Development)

**Source Plugin**: `feature-dev`
**Components**: 1 slash command + 3 specialised agents

### 7-Phase Workflow

| Phase | Goal | Key Actions |
|-------|------|-------------|
| 1. Discovery | Understand what to build | Clarify problem, constraints, requirements |
| 2. Codebase Exploration | Understand existing code | Launch 2-3 **code-explorer** agents in parallel to trace implementations, map architecture, identify patterns. Read all files they identify. |
| 3. Clarifying Questions | Resolve all ambiguities | **CRITICAL — DO NOT SKIP.** Identify edge cases, error handling, integration points, scope, preferences. Wait for answers. |
| 4. Architecture Design | Design implementation approaches | Launch 2-3 **code-architect** agents in parallel with different focuses (minimal changes, clean architecture, pragmatic balance). Present comparison + recommendation. |
| 5. Implementation | Build the feature | **Wait for user approval first.** Read relevant files, implement following chosen architecture, follow codebase conventions. |
| 6. Quality Review | Ensure code quality | Launch 3 **code-reviewer** agents (simplicity/DRY, bugs/correctness, conventions/abstractions). Present findings, ask user what to fix. |
| 7. Summary | Document accomplishment | What was built, decisions made, files modified, next steps. |

### Specialised Agents

**code-explorer** (Sonnet, yellow):
- Traces execution paths from entry points to data storage
- Maps abstraction layers, design patterns, dependencies
- Returns list of 5-10 key files to read

**code-architect** (Sonnet, green):
- Analyses existing patterns, conventions, CLAUDE.md guidelines
- Designs complete architecture with confident choices
- Outputs: patterns found, architecture decision, component design, implementation map, data flow, build sequence

**code-reviewer** (Sonnet, red):
- Reviews against CLAUDE.md with confidence scoring (0-100, report ≥80 only)
- Focuses on bugs, security, code quality — not style preferences
- Groups issues by severity (Critical vs Important)

---

<a id="blueprint-8"></a>
## Blueprint 8: Frontend Design

**Source Plugin**: `frontend-design`
**Type**: Model-invoked skill (triggers when building web components/pages/apps)

### Core Principle
Create distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics.

### Design Thinking Process
1. **Purpose**: What problem does this interface solve?
2. **Tone**: Pick a BOLD direction — brutally minimal, maximalist chaos, retro-futuristic, organic/natural, luxury/refined, playful, editorial, brutalist, art deco, soft/pastel, industrial...
3. **Constraints**: Framework, performance, accessibility
4. **Differentiation**: What makes this UNFORGETTABLE?

### Aesthetics Guidelines

**Typography**: Choose distinctive fonts. NEVER use Arial, Inter, Roboto, system fonts. Pair a display font with a refined body font.

**Color**: Commit to a cohesive aesthetic via CSS variables. Dominant colors with sharp accents > timid even palettes.

**Motion**: Focus on high-impact moments — page load with staggered reveals, scroll-triggered effects, surprising hover states. Use CSS-only for HTML, Motion library for React.

**Spatial Composition**: Unexpected layouts, asymmetry, overlap, diagonal flow, grid-breaking elements, generous negative space OR controlled density.

**Backgrounds**: Gradient meshes, noise textures, geometric patterns, layered transparencies, dramatic shadows, decorative borders, custom cursors, grain overlays.

**NEVER**: Overused fonts (Inter, Roboto, Space Grotesk), cliched purple gradients on white, predictable layouts, cookie-cutter patterns. Never converge on common choices across generations.

---

<a id="blueprint-9"></a>
## Blueprint 9: Hookify (Rule-Based Hook Automation)

**Source Plugin**: `hookify`
**Components**: 4 slash commands + 1 skill + Python hook scripts + conversation-analyser agent

### Core Capability
Create hook rules to prevent unwanted behaviours by analysing conversation patterns or from explicit instructions. Rules are stored as `.claude/hookify.{rule-name}.local.md` files.

### Rule File Format
```markdown
---
name: rule-identifier
enabled: true
event: bash|file|stop|prompt|all
pattern: regex-pattern
action: warn|block
---

Message to show Claude when rule triggers.
```

### Advanced Format (Multiple Conditions)
```markdown
---
name: warn-env-edits
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.env$
  - field: new_text
    operator: contains
    pattern: API_KEY
---
```

### Event Types
| Event | Matches | Fields |
|-------|---------|--------|
| `bash` | Bash commands | `command` |
| `file` | Edit/Write/MultiEdit | `file_path`, `new_text`, `old_text`, `content` |
| `stop` | Agent wants to stop | (transcript check) |
| `prompt` | User prompt | `user_prompt` |
| `all` | All events | — |

### Operators
`regex_match`, `contains`, `equals`, `not_contains`, `starts_with`, `ends_with`

### Workflow
1. Analyse conversation (via conversation-analyser agent) or parse user instructions
2. Present findings to user (AskUserQuestion with multiSelect)
3. Ask action: warn or block
4. Generate `.claude/hookify.{name}.local.md` files
5. Rules active immediately — no restart needed

---

<a id="blueprint-10"></a>
## Blueprint 10: PR Review Toolkit (6 Specialised Agents)

**Source Plugin**: `pr-review-toolkit`
**Components**: 1 slash command (`/review-pr`) + 6 review agents

### Review Agents

| Agent | Focus | When |
|-------|-------|------|
| **code-reviewer** | CLAUDE.md compliance, bugs, quality | Always |
| **comment-analyser** | Comment accuracy, rot, documentation | Comments/docs changed |
| **pr-test-analyser** | Behavioural test coverage, gaps, quality | Test files changed |
| **silent-failure-hunter** | Silent failures, catch blocks, error logging | Error handling changed |
| **type-design-analyser** | Type encapsulation, invariants, design quality | Types added/modified |
| **code-simplifier** | Simplify, improve clarity, apply standards | After passing review |

### Workflow
1. Determine scope (`git diff --name-only`, `gh pr view`)
2. Identify applicable reviews based on changed files
3. Launch agents (sequential by default, parallel if requested)
4. Aggregate: Critical Issues → Important Issues → Suggestions → Strengths
5. Provide action plan with file:line references

### Usage Patterns
- Full review: `/review-pr`
- Specific: `/review-pr tests errors`
- Parallel: `/review-pr all parallel`

---

<a id="blueprint-11"></a>
## Blueprint 11: Plugin Dev (Plugin Creation Toolkit)

**Source Plugin**: `plugin-dev`
**Components**: 1 slash command + 3 agents + 7 skills

### `/create-plugin` — 8-Phase Workflow

| Phase | Goal | Key Actions |
|-------|------|-------------|
| 1. Discovery | Understand plugin purpose | Clarify problem, users, type |
| 2. Component Planning | Determine needed components | Load plugin-structure skill. Plan: Skills, Agents, Hooks, MCP, Settings |
| 3. Detailed Design | Resolve all ambiguities | Per-component specification. Wait for user answers. |
| 4. Structure Creation | Create directory + manifest | `mkdir -p`, plugin.json, README.md |
| 5. Implementation | Create each component | Load relevant dev skills. Create SKILL.md, agents, hooks, MCP configs |
| 6. Validation | Quality check | Run plugin-validator agent, skill-reviewer agent, validate scripts |
| 7. Testing | Verify it works | Installation instructions, verification checklist, test cases |
| 8. Documentation | Complete docs | README completeness, marketplace entry |

### Agents
- **agent-creator**: Elite AI agent architect for designing agents
- **plugin-validator**: Validates plugin structure, manifest, naming, security
- **skill-reviewer**: Reviews skill quality, description, progressive disclosure, writing style

### Available Dev Skills
| Skill | Purpose |
|-------|---------|
| plugin-structure | Plugin component types and directory layout |
| skill-development | Creating skills with SKILL.md |
| command-development | Legacy commands/ format |
| agent-development | Agent .md files with frontmatter |
| hook-development | Hook configuration and scripts |
| mcp-integration | MCP server setup |
| plugin-settings | .local.md settings files |

### Key Conventions
- Skills preferred over legacy `commands/` format
- Third-person descriptions with trigger phrases
- Imperative form in skill bodies
- Instructions FOR Claude (not TO user)
- `${CLAUDE_PLUGIN_ROOT}` for portability
- Progressive disclosure (lean SKILL.md, details in references/)

---

<a id="blueprint-12"></a>
## Blueprint 12: Skill Creator

**Source Plugin**: `skill-creator`
**Type**: Model-invoked skill with agents, scripts, and eval viewer

### Core Capability
Create new skills, iteratively improve them via eval loops, and optimise skill descriptions for better triggering accuracy.

### Main Loop
1. Capture intent (what, when, output format, test cases?)
2. Interview and research (edge cases, formats, dependencies)
3. Write SKILL.md draft
4. Create 2-3 test prompts → run with-skill + baseline in parallel
5. While runs execute, draft quantitative assertions
6. Grade runs → aggregate benchmark → launch eval viewer for user review
7. Read user feedback → improve skill → repeat until satisfied
8. Optimise description for triggering accuracy

### Skill Writing Guide

**Structure**: `skill-name/SKILL.md` (required) + optional `scripts/`, `references/`, `assets/`

**Progressive Disclosure**:
1. Metadata (name + description) — always in context (~100 words)
2. SKILL.md body — when triggered (<500 lines ideal)
3. Bundled resources — as needed (unlimited)

**Description**: Primary triggering mechanism. Make it slightly "pushy" — Claude tends to undertrigger. Include what it does AND specific contexts.

**Writing Style**: Explain WHY things are important. Use theory of mind. Avoid heavy-handed MUSTs. Make skills general, not narrow to examples.

### Eval System

**Test Cases** (`evals/evals.json`):
```json
{
  "skill_name": "example",
  "evals": [
    {"id": 1, "prompt": "...", "expected_output": "...", "files": []}
  ]
}
```

**Runs**: For each test case, spawn 2 parallel subagents (with-skill + baseline). Capture timing data from task notifications.

**Grading**: Use `agents/grader.md`. Assertions use `text`, `passed`, `evidence` fields.

**Viewer**: `eval-viewer/generate_review.py` — shows Outputs tab (per-test feedback) + Benchmark tab (pass rates, timing, tokens). User submits feedback via `feedback.json`.

### Description Optimisation
1. Generate 20 trigger eval queries (10 should-trigger, 10 should-not-trigger — realistic, edge-case-heavy)
2. Review with user via HTML template
3. Run `scripts/run_loop.py` — splits 60/40 train/test, evaluates 3x, proposes improvements, iterates up to 5x
4. Apply best_description (selected by test score to avoid overfitting)

---

<a id="blueprint-13"></a>
## Blueprint 13: Security Guidance

**Source Plugin**: `security-guidance`
**Type**: PreToolUse hook (Python script, triggers on Edit/Write/MultiEdit)

### Core Capability
Automatically detects security vulnerability patterns in file edits and warns/blocks. Session-scoped deduplication (warns once per file+rule combination).

### Security Patterns Detected

| Pattern | Trigger | Risk |
|---------|---------|------|
| GitHub Actions Workflow | `.github/workflows/*.yml` path | Command injection via untrusted inputs |
| child_process.exec | `exec(`, `execSync(` substrings | Command injection |
| new Function() | `new Function` substring | Code injection |
| eval() | `eval(` substring | Arbitrary code execution |
| dangerouslySetInnerHTML | React substring | XSS vulnerability |
| document.write() | Substring | XSS attacks |
| innerHTML = | Substring | XSS with untrusted content |
| pickle | Substring | Arbitrary code execution via deserialisation |
| os.system | Substring | Command injection |

### Implementation Details
- Python hook script reads stdin JSON (session_id, tool_name, tool_input)
- Checks file path and content against pattern rules
- Session-scoped state file (`~/.claude/security_warnings_state_{session_id}.json`)
- Each warning shown once per file+rule per session
- Exit code 2 blocks tool execution; exit code 0 allows
- Can be disabled via `ENABLE_SECURITY_REMINDER=0` env var
- Auto-cleans state files older than 30 days (10% probability per run)

---

<a id="blueprint-14"></a>
## Blueprint 14: Explanatory Output Style

**Source Plugin**: `explanatory-output-style`
**Type**: SessionStart hook (shell script)

### Core Capability
Injects "explanatory mode" instructions at session start via `additionalContext`. Claude provides educational insights about implementation choices as it works.

### Behaviour
Before and after writing code, Claude includes insight blocks:
```
`★ Insight ─────────────────────────────────────`
[2-3 key educational points specific to the codebase]
`─────────────────────────────────────────────────`
```

Focus on codebase-specific insights, not general programming concepts. Provide inline as code is written, not batched at end.

---

<a id="blueprint-15"></a>
## Blueprint 15: Learning Output Style

**Source Plugin**: `learning-output-style`
**Type**: SessionStart hook (shell script)

### Core Capability
Combines interactive learning with explanatory functionality. Instead of implementing everything, Claude identifies opportunities for the user to write 5-10 lines of meaningful code.

### When to Request User Contributions
- Business logic with multiple valid approaches
- Error handling strategies
- Algorithm implementation choices
- Data structure decisions
- UX decisions
- Design patterns and architecture choices

### Request Pattern
1. Create file with surrounding context
2. Add function signature with clear parameters/return type
3. Include comments explaining purpose
4. Mark location with TODO
5. Explain trade-offs and frame as valuable input (not busy work)

### DON'T request contributions for
Boilerplate, obvious implementations, configuration, simple CRUD.

Also includes explanatory insights (same `★ Insight` blocks as Blueprint 14).

---

<a id="blueprint-16"></a>
## Blueprint 16: Playground (Interactive HTML Builder)

**Source Plugin**: `playground`
**Type**: Model-invoked skill with 6 templates

### Core Capability
Creates self-contained single-file HTML playgrounds with interactive controls, live preview, and copyable prompt output.

### Core Requirements
- **Single HTML file** — inline all CSS/JS, no external dependencies
- **Live preview** — updates instantly on every control change (NO "Apply" button)
- **Prompt output** — natural language mentioning only non-default values
- **Copy button** — clipboard copy with "Copied!" feedback
- **Defaults + presets** — looks good on first load, 3-5 named presets
- **Dark theme** — system font for UI, monospace for code

### State Management Pattern
```javascript
const state = { /* all configurable values */ };
function updateAll() { renderPreview(); updatePrompt(); }
// Every control calls updateAll() on change
```

### Templates

| Template | Use Case | Key Features |
|----------|----------|--------------|
| `design-playground` | Visual design decisions | Component preview, sliders, toggles, dropdowns |
| `data-explorer` | SQL/API/pipeline building | Table selection, column picking, filters, syntax highlighting |
| `concept-map` | Learning/exploration | Canvas nodes, knowledge levels, force-directed layout |
| `document-critique` | Document review | Suggestions panel, approve/reject/comment workflow |
| `diff-review` | Code diff review | Diff rendering, line-by-line commenting, file navigation |
| `code-map` | Architecture visualisation | SVG canvas, layer toggles, connection filters, zoom |

### Workflow
1. Identify playground type from user request
2. Load matching template from `templates/`
3. Follow template to build the playground
4. Run `open <filename>.html` to launch in browser

---

<a id="blueprint-17"></a>
## Blueprint 17: Ralph Loop (Iterative Self-Referential AI Loops)

**Source Plugin**: `ralph-loop`
**Type**: Stop hook + slash commands + setup script

### Core Capability
Runs Claude in a continuous while-true loop with the SAME PROMPT until task completion. Each iteration sees previous work in files and git history, enabling iterative improvement.

### How It Works
1. `/ralph-loop PROMPT [--max-iterations N] [--completion-promise TEXT]` — initialises state file `.claude/ralph-loop.local.md`
2. Claude works on the task
3. When Claude tries to exit, the Stop hook intercepts:
   - Reads state file (iteration count, session ID, completion promise)
   - Checks if max iterations reached → exits if so
   - Searches transcript for `<promise>TEXT</promise>` matching completion_promise
   - If found → removes state file (completion)
   - If not found → increments iteration, feeds same prompt back
4. `/cancel-ralph` — manually stops the loop

### Completion Promise
If set, Claude may ONLY output `<promise>TEXT</promise>` when the statement is **completely and unequivocally TRUE**. This prevents Claude from outputting false promises to escape the loop.

### Best Use Cases
- Well-defined tasks with clear completion criteria
- Iterative improvement (code quality, test coverage)
- Greenfield development with incremental goals
- Self-correction loops

### NOT suited for
- Tasks requiring human judgment
- One-shot tasks
- Unclear completion criteria

---

<a id="blueprint-18"></a>
## Blueprints 18-29: LSP Plugins (Language Server Protocol)

All LSP plugins follow the same pattern: provide code intelligence (go-to-definition, find references, error checking, diagnostics) via language-specific servers.

| # | Plugin | Language | Files | Server | Install Command |
|---|--------|----------|-------|--------|-----------------|
| 18 | `typescript-lsp` | TS/JS (.ts .tsx .js .jsx .mts .cts .mjs .cjs) | — | typescript-language-server | `npm install -g typescript-language-server typescript` |
| 19 | `pyright-lsp` | Python (.py .pyi) | — | Pyright | `npm install -g pyright` or `pip install pyright` |
| 20 | `gopls-lsp` | Go (.go) | — | gopls | `go install golang.org/x/tools/gopls@latest` |
| 21 | `rust-analyzer-lsp` | Rust (.rs) | — | rust-analyzer | `rustup component add rust-analyzer` |
| 22 | `clangd-lsp` | C/C++ (.c .h .cpp .cc .cxx .hpp .hxx) | — | clangd | Homebrew or LLVM releases |
| 23 | `jdtls-lsp` | Java (.java) | — | Eclipse JDT.LS | Homebrew or manual (requires Java 17+) |
| 24 | `kotlin-lsp` | Kotlin (.kt .kts) | — | kotlin-lsp | `brew install JetBrains/utils/kotlin-lsp` |
| 25 | `swift-lsp` | Swift (.swift) | — | SourceKit-LSP | Included with Swift toolchain (Xcode) |
| 26 | `csharp-lsp` | C# (.cs) | — | csharp-ls | `dotnet tool install --global csharp-ls` (requires .NET 6.0+) |
| 27 | `php-lsp` | PHP (.php) | — | Intelephense | `npm install -g intelephense` |
| 28 | `lua-lsp` | Lua (.lua) | — | lua-language-server | Homebrew or package managers |
| 29 | `ruby-lsp` | Ruby (.rb .rake .gemspec .ru .erb) | — | ruby-lsp | `gem install ruby-lsp` (requires Ruby 3.0+) |

### Design Note
These are configuration-only plugins (README + LICENSE). No SKILL.md files. They configure MCP server connections to language servers using `extensionToLanguage` mapping.

---

<a id="blueprint-30"></a>
## Blueprint 30: Example Plugin (Reference Implementation)

**Source Plugin**: `example-plugin`
**Type**: Reference/documentation

Demonstrates ALL Claude Code extension options:
- **Skills (modern format)**: `skills/example-skill/SKILL.md` — model-invoked with name, description, version
- **Commands (legacy format)**: `commands/example-command.md` — user-invoked with description, argument-hint, allowed-tools
- **MCP Servers**: `.mcp.json` with server configuration
- **User-invoked skills**: Same as commands but in `skills/` directory with `argument-hint` frontmatter

### Key Takeaway
Skills in `skills/<name>/SKILL.md` are the modern format. `commands/*.md` is legacy but still supported. Both load identically.

---

<a id="blueprint-31"></a>
## Blueprint 31: Antigravity (Internal Plugin)

**Source Plugin**: `antigravity`
**Type**: Our own agents — already in the ecosystem

Contains all Antigravity agents (AU racing pipeline, EternityX sales pipeline, etc.) as documented in `ecosystem_reference.md`. No need to duplicate here — refer to that resource for full details.

---

## Quick Reference: Plugin Capabilities by Category

### Code Quality & Review
| Plugin | What It Does |
|--------|-------------|
| code-simplifier | Auto-simplifies modified code |
| code-review | Multi-agent PR review with confidence scoring |
| pr-review-toolkit | 6 specialised review agents |

### Development Workflow
| Plugin | What It Does |
|--------|-------------|
| commit-commands | Git commit, push, PR automation |
| feature-dev | 7-phase guided feature development |
| frontend-design | Distinctive UI creation |
| playground | Interactive HTML playground builder |

### Meta / Tooling
| Plugin | What It Does |
|--------|-------------|
| plugin-dev | Plugin creation toolkit |
| skill-creator | Skill creation with eval/benchmarking |
| claude-code-setup | Automation recommender |
| claude-md-management | CLAUDE.md auditing and improvement |
| agent-sdk-dev | SDK app setup and verification |

### Automation & Safety
| Plugin | What It Does |
|--------|-------------|
| hookify | Rule-based hook automation |
| security-guidance | Security pattern detection |
| ralph-loop | Continuous iteration loops |

### Output Styles
| Plugin | What It Does |
|--------|-------------|
| explanatory-output-style | Educational insights mode |
| learning-output-style | Interactive learning + insights |

### Language Servers
12 LSP plugins for: TypeScript, Python, Go, Rust, C/C++, Java, Kotlin, Swift, C#, PHP, Lua, Ruby
