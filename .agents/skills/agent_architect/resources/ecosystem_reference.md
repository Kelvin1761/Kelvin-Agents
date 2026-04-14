# Antigravity Agent Ecosystem Reference

This document defines the structure, conventions, and existing agents of the Antigravity plugin. All new agents MUST follow these conventions for consistency.

---

## Plugin Structure

```
.agents/
├── .claude-plugin/
│   └── plugin.json          # Plugin metadata
└── skills/
    ├── agent_architect/     # Meta-agent (no category prefix)
    ├── hkjc_racing/         # Hong Kong racing agents
    │   ├── hkjc_wong_choi/          # V4 Python-First — orchestrator.py 控制
    │   ├── hkjc_race_extractor/
    │   ├── hkjc_horse_analyst/
    │   ├── hkjc_batch_qa/           # [DEPRECATED → V8 Orchestrator]
    │   ├── hkjc_compliance/         # [DEPRECATED → V8 Orchestrator]
    │   ├── hkjc_reflector/          # V2 Python-First (merged Reflector + Validator)
    │   └── hkjc_reflector_validator/ # [DEPRECATED → hkjc_reflector V2]
    ├── au_racing/           # Australian racing agents
    │   ├── au_wong_choi/            # V4 Python-First — orchestrator.py 控制
    │   ├── au_race_extractor/
    │   ├── au_horse_analyst/
    │   ├── au_batch_qa/             # [DEPRECATED → V8 Orchestrator]
    │   ├── au_compliance/           # [DEPRECATED → V8 Orchestrator]
    │   ├── au_reflector/              # V2 Python-First (merged Reflector + Validator)
    │   ├── au_horse_race_reflector/  # [DEPRECATED → au_reflector V2]
    │   ├── au_reflector_validator/   # [DEPRECATED → au_reflector V2]
    │   └── au_racecourse_weather_prediction/
    ├── nba/                 # NBA agents
    │   ├── nba_wong_choi/           # V3 Python-First
    │   ├── nba_data_extractor/
    │   ├── nba_analyst/
    │   ├── nba_batch_qa/
    │   ├── nba_compliance/
    │   ├── nba_reflector/
    │   └── nba_reflector_validator/
    ├── lol_wong_choi/       # LoL esports orchestrator
    ├── lol_reflector/       # LoL post-match forensic analyst
    ├── betting_accountant/  # Cross-domain Kelly sizing gatekeeper
    ├── shared_instincts/    # Cross-domain instinct registry (SIP tracking)
    └── horserace_game_developers/  # 旺財街機遊戲開發
        ├── game_producer/
        ├── lead_designer/
        ├── systems_designer/
        ├── content_designer/
        ├── frontend_engineer/
        ├── game_engine_dev/
        ├── pixel_artist/
        ├── sound_designer/
        ├── game_qa/
        ├── game_ops/
        └── mobile_engineer/
```

### Agent Folder Structure
```
[agent_name]/
    ├── SKILL.md          # Required — agent definition
    └── resources/        # Optional — context files, engines, templates
        ├── 01_xxx.md
        ├── 02_xxx.md
        └── ...
```

## SKILL.md Conventions

### Frontmatter (Required)
```yaml
---
name: [Display Name]
description: This skill should be used when the user wants to "[trigger 1]", "[trigger 2]"...
version: 1.0.0
---
```
- `description` MUST use third-person format with specific trigger phrases.
- Include concrete user queries that should activate this agent.

### Body Structure (Standard Sections)
1. **Role** — Who the agent is (1-2 sentences).
2. **Objective** — What the agent does end-to-end.
3. **Persona & Tone** — Communication style and language requirements.
4. **Scope & Strict Constraints** — What it must/must not do, anti-laziness protocols.
5. **Interaction Logic** — Step-by-step workflow.
6. **Recommended Tools & Assets** — Tools and resource file references.

### Resource Read-Once Protocol
If the agent has `resources/` files, include a Read-Once Protocol section:
- List all resource files to read at session start.
- Instruct the agent to retain them in memory for the entire session.
- Prohibit re-reading per batch/iteration — only re-read on session restart or task switch.

---

## Established Conventions

### Language
- All user-facing output: **Hong Kong style Traditional Chinese** (廣東話語氣).
- Trainer/jockey names: **Always English** — never translate to Chinese.
- Racing terminology: Use authentic HK/AU racing jargon.

### Anti-Laziness & Chunking Protocol
All data-heavy agents MUST include an anti-laziness protocol:
- Process data in small bounded batches (1-3 items per batch).
- Enforce strict sequential ordering (e.g., by horse number, race number).
- Prohibit depth reduction across batches — every item gets full analysis.
- Pause between batches and ask user to continue.

### Resource File Naming
Use numbered prefixes for ordered reading:
```
resources/01_system_context.md
resources/02_algorithmic_engine.md
resources/03_forensic_evaluation.md
resources/06_output_templates.md
```

### Anti-Hallucination
- If data is missing, output `N/A (數據不足)` — never guess.
- Internal reasoning goes in `<thought>` tags, never in final output.

### CSV Data Contract
Agents that chain to downstream agents output structured CSV blocks:
```csv
[Race Number], [Distance], [Jockey], [Trainer], [Horse Number], [Horse Name], [Grade]
```

---

## Existing Agents

| Agent | Role | Upstream | Downstream |
|-------|------|----------|------------|
| **Wong Choi** (HKJC/AU) | V4 Python-First orchestrator. 執行 `orchestrator.py`，LLM 只負責填寫 `[FILL]` 欄位。Python 狀態機控制 extraction → analysis → QA → verdict 全流程。 | User input / race URL | Python Orchestrator → Horse Analyst (LLM fill) |
| **Race Extractor** (HKJC/AU) | Raw data extraction from race cards and form guides via Python scripts. | URL / PDF | Horse Analyst |
| **Horse Analyst** (HKJC/AU) | Deep per-horse analysis with algorithmic engine, forensic evaluation, EEM. Outputs Top 3-4 selections. | Extractor data + `.runtime/Active_Horse_Context.md` | Python Orchestrator (QA built-in) |
| ~~**Batch QA**~~ (HKJC/AU) | **[DEPRECATED]** Functions absorbed into V8 Python Orchestrator state machine. Do NOT invoke. | — | — |
| ~~**Compliance Agent**~~ (HKJC/AU) | **[DEPRECATED]** Functions absorbed into V8 Python Orchestrator state machine. Do NOT invoke. | — | — |
| **Reflector V2** (HKJC/AU) | Python-First 10-Step 覆盤引擎。合併原 Reflector + Validator。Python 做統計/Calibration/MC Re-run，LLM 做深度分析/SIP BAKE。含 Market Edge Analysis + Walk-Forward Validation + MC Parameter Check。 | Race results + Analyst predictions + MC logic.json | User (覆盤報告 + SIP proposals) |
| ~~**Reflector Validator**~~ (HKJC/AU) | **[DEPRECATED]** Functions merged into Reflector V2 (Python-First). Do NOT invoke. | — | — |
| **Racecourse Weather Prediction** (AU) | Weather and track condition forecasting. | Race date + venue | Wong Choi / Analyst |
| **Agent Architect** | Meta-agent. Designs, optimises, and audits agents (4 modes: Build/Optimise/Audit/Debug). Agent Health Check. | User requirements | New/updated SKILL.md |
| **NBA Wong Choi** | V3 Python-First NBA Parlay analysis commander. | User input (date / specific games) | NBA Data Extractor → NBA Analyst |
| **NBA Data Extractor** | Real-time NBA data extraction: rosters, injuries, defensive profiles, player stats (L10), match context, and player/team news. Outputs structured data package. | NBA Wong Choi / User | NBA Analyst |
| **NBA Analyst** | Quantitative parlay analysis: CoV volatility engine, contextual adjustments (incl. news), safety gate, 3-tier parlay builder (Banker/Value/High Odds). Sportsbet compliant. | NBA Data Extractor data package | NBA Wong Choi / User |
| **NBA Batch QA** | Per-output quality gate for NBA analysis. | Analyst output | NBA Wong Choi (pass/fail) |
| **NBA Compliance** | Cross-game quality inspection for NBA pipeline. | Full analysis set | NBA Wong Choi (pass/fail) |
| **NBA Reflector** | Post-game review. API-First box score extraction. Compares predictions vs actual, identifies systematic blind spots, proposes SIPs. | Game results (API/web) + Analyst predictions | Analyst (improvement proposals) |
       Reflector V2 (Python-First 10-Step Pipeline)
          Steps 1-3: 🐍 賽果擷取 → KPI + Calibration → 問題掃描 + Market Edge
          Steps 4-6: 🧠 引擎邏輯審視 → SIP 草擬 → 泛化性篩選
          Step 7:    🐍 MC Re-run → 🧠 Deep Validation
          Step 7.5:  🐍 MC Parameter Consistency Check
          Step 8:    📋 報告 + Walk-Forward flags → ⏸ 等用戶審批
          Step 9:    🧠 LLM BAKE approved SIPs
```

### Agent Chaining Flow — NBA Parlay
```
User → NBA Wong Choi (date + game selection)
         ↓
       NBA Data Extractor (web search: rosters, injuries, stats, news)
         ↓
       NBA Analyst (volatility → safety gate → 3-tier parlay builder)
         ↓
       NBA Wong Choi (quality check + override + self-debug)
         ↓
       User (final parlay report + auto-save)
         ↓ (post-game)
       NBA Reflector (review & improvement proposals)
```

### Agent Chaining Flow — LoL Esports (V2)
```
User → /lol-prediction (Phase 0-2.5: data audit → execution dehydration → logic gate)
         ↓ ⛔ STOP (等賠率)
       /lol-sniper (Phase 3: odds extraction → V14 calibration → Grade → suggested sizing)
         ↓ proposal package
       Betting Accountant (Step 0: bankroll read → Step 1: edge verify → Step 2: Kelly + override)
         ↓ final sizing (≤ sniper suggestion)
       User (最終推介 + 投注)
         ↓ (bet placed + recorded)
       records/betting_record.md (含 CLV 欄位 — Phase Β)
         ↓ (post-match)
       /lol-postmortem + LoL Reflector (賽後覆盤 + Odds Forensics — Phase Β)
         ↓ (CLV data + pattern feedback)
       Betting Accountant (下次調用時 Step 0 讀取更新嘅 ROI + CLV 數據)
```

---

## Cross-System Integration (.agent ↔ .agents)

The Antigravity Kit (`.agent/`) and custom agents (`.agents/`) coexist in the workspace. Custom agents can **reference** AG Kit skills at runtime via `view_file` — content is **never duplicated**.

### Integration Map

| .agents Agent | 引用嘅 .agent Skills | 觸發條件 | 觸發方式 |
|---------------|---------------------|----------|---------|
| **Agent Architect** | brainstorming, plan-writing, systematic-debugging, architecture | Mode A/B/C 偵測 | 🤖 自動 |
| **HKJC Reflector** | brainstorming | 覆盤分析生成 SIP 時 | 🤖 自動 |
| **AU Reflector** | brainstorming | 覆盤分析生成 SIP 時 | 🤖 自動 |
| **NBA Reflector** | brainstorming | 覆盤分析生成 SIP 時 | 🤖 自動 |
| **HKJC Wong Choi** | systematic-debugging | 合規 FAILED 2 次 → 3-Phase 閉環（診斷 → 修正 → 重做 Batch） | 🤖 自動 |
| **AU Wong Choi** | systematic-debugging | 合規 FAILED 2 次 → 3-Phase 閉環（診斷 → 修正 → 重做 Batch） | 🤖 自動 |
| **NBA Wong Choi** | systematic-debugging, brainstorming | 品質掃描 FAILED / 自檢總結 | 🤖 自動 |
| **HKJC Horse Analyst** | systematic-debugging | QG-CHECK 連續失敗 2 次 → 根因分析 → 針對性修正 | 🤖 自動 |
| **AU Horse Analyst** | systematic-debugging | QG-CHECK 連續失敗 2 次 → 根因分析 → 針對性修正 | 🤖 自動 |
| **Game Producer** | brainstorming, plan-writing, systematic-debugging | 新功能 / 設計輸出 / QA 失敗 | 🤖 自動 |

**All Wong Choi engines** also reference AG Kit orchestrator patterns: Agent Boundary Enforcement + Conflict Resolution + Status Board.
**All Wong Choi + Analyst debugging** includes **硬性熔斷 (Circuit Breaker)** — 自動修復最多執行 1 次，防止無限 loop。

### Loading Principle
```
Agent 需要 AG Kit skill 時：
1. view_file `.agent/skills/[skill]/SKILL.md`
2. 按需載入原則（lazy-load）— 唔會預先讀取
3. 只讀取，唔複製內容到自己嘅 SKILL.md
```

### Key Paths
| AG Kit Skill | Path |
|---|---|
| brainstorming | `.agent/skills/brainstorming/SKILL.md` |
| plan-writing | `.agent/skills/plan-writing/SKILL.md` |
| systematic-debugging | `.agent/skills/systematic-debugging/SKILL.md` |
| architecture | `.agent/skills/architecture/SKILL.md` |

---

## Design Checklist for New Agents

When creating a new agent, verify:
- [ ] SKILL.md has correct YAML frontmatter (name, description with triggers, version)
- [ ] Description uses third-person with specific trigger phrases
- [ ] Resource Read-Once Protocol included (if resources exist)
- [ ] Anti-Laziness protocol included (if processing bulk data)
- [ ] Anti-Hallucination protocol included
- [ ] Language requirement specified (HK Traditional Chinese)
- [ ] Agent chaining interface defined (upstream/downstream data contracts)
- [ ] Resource files use numbered prefixes if order matters
- [ ] SKILL.md body stays lean (<150 lines) — heavy content in resources/
- [ ] Consulted `resources/design_patterns.md` for robustness checks
