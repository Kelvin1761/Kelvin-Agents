# Antigravity Agent Ecosystem Reference

This document defines the structure, conventions, and existing agents of the Antigravity plugin. All new agents MUST follow these conventions for consistency.

---

## Plugin Structure

```
.agents/
├── .claude-plugin/
│   └── plugin.json          # Plugin metadata
├── scripts/               # Native Python Tools (Zero-Cost Architecture)
│   ├── safe_file_writer.py
│   ├── completion_gate_v2.py
│   └── ...
└── skills/
    ├── agent_architect/     # Meta-agent (no category prefix)
    ├── hkjc_racing/         # Hong Kong racing agents
    │   ├── hkjc_wong_choi/
    │   ├── hkjc_race_extractor/
    │   ├── hkjc_horse_analyst/
    │   ├── hkjc_batch_qa/
    │   ├── hkjc_compliance/
    │   ├── hkjc_reflector/
    │   └── hkjc_reflector_validator/
    ├── au_racing/           # Australian racing agents
    │   ├── au_wong_choi/
    │   ├── au_race_extractor/
    │   ├── au_horse_analyst/
    │   ├── au_batch_qa/
    │   ├── au_compliance/
    │   ├── au_horse_race_reflector/
    │   └── au_reflector_validator/
    ├── nba/                 # NBA agents
    │   ├── nba_wong_choi/
    │   ├── nba_data_extractor/
    │   ├── nba_analyst/
    │   ├── nba_batch_qa/
    │   ├── nba_compliance/
    │   ├── nba_reflector/
    │   └── nba_reflector_validator/
    ├── horserace_game_developers/  # 賽馬遊戲開發 agents
    ├── shared_instincts/          # 跨引擎共享本能模組
    └── antigravity-awesome-skills/ # 精選技能集
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

### Zero-Cost Multi-Perspective Analysis
Instead of using expensive and brittle multi-agent setups (CrewAI/AutoGen):
- **[SIP-DA01]**: Embedded 5-step debate protocol inside Wong Choi Verdict (Form -> Track -> Place Prob -> Value -> Final) for rigorous self-auditing.
- **[NBA-DA01]**: 4-step embedded parlay auditing protocol.
- **[REF-DA01]**: 5-angle post-mortem reflection protocol applied in all Reflector agents (Outcome -> Process -> SIP Audit -> Generalizability -> Design Pattern Proposal).

### CSV Data Contract
Agents that chain to downstream agents output structured CSV blocks:
```csv
[Race Number], [Distance], [Jockey], [Trainer], [Horse Number], [Horse Name], [Grade]
```

---

## Existing Agents

| Agent | Role | Upstream | Downstream |
|-------|------|----------|------------|
| **Wong Choi** (HKJC/AU) | Meeting-level commander. Sets pace context, weather, track bias. Orchestrates per-race analysis. Writes intelligence package to file. | User input / race URL | Race Extractor → Horse Analyst → Batch QA → Compliance |
| **Race Extractor** (HKJC/AU) | Raw data extraction from race cards and form guides. | URL / PDF | Horse Analyst |
| **Horse Analyst** (HKJC/AU) | Deep per-horse analysis with algorithmic engine, forensic evaluation, EEM. Outputs Top 3-4 selections. | Extractor data + Wong Choi context + Intelligence Package | Batch QA → Compliance Agent |
| **Native Validation Engine** | Zero-Cost python gating utility (`completion_gate_v2.py`) deployed across Wong Choi variants to strictly enforce templates. | Analyst report | Wong Choi |
| **Batch QA** (HKJC/AU) | Per-batch quality gate. Structural scan, semantic scan, anti-laziness. Called after each batch. | Analyst batch output | Wong Choi (pass/fail) |
| **Compliance Agent** (HKJC/AU) | Quality police. Cross-batch trend analysis, SIP verification, anti-laziness audit, self-improvement hub. Tiered remediation (CRITICAL→full redo, structural MINOR→batch redo). | Analyst report + SIP index + SIP changelog | Wong Choi (pass/fail verdict) |
| **Reflector** (HKJC/AU) | Post-race review with narrative post-mortem. Distinguishes bad logic from bad luck. Maintains SIP changelog. Proposes design patterns. | Race results + Analyst predictions | Reflector Validator / User / Agent Architect |
| **Reflector Validator** (HKJC/AU) | Blind re-analysis gatekeeper. Validates SIP updates via selective race-by-race testing with user checkpoints. | Race folder + SIP changelog | User (validation report) |
| **Agent Architect** | Meta-agent. Designs, optimises, and audits agents (3 modes: Build/Optimise/Audit). Agent Health Check. | User requirements | New/updated SKILL.md |
| **Racecourse Weather Prediction** (AU) | Weather and track condition forecasting. | Race date + venue | Wong Choi / Analyst |
| **NBA Wong Choi** | NBA Parlay analysis commander. Orchestrates data extraction and parlay strategy analysis. Defaults to all games on specified date. | User input (date / specific games) | NBA Data Extractor → NBA Analyst → NBA Compliance → NBA Batch QA |
| **NBA Data Extractor** | Real-time NBA data extraction: rosters, injuries, defensive profiles, player stats (L10), match context, and player/team news. Outputs structured data package. | NBA Wong Choi / User | NBA Analyst |
| **NBA Analyst** | Quantitative parlay analysis: CoV volatility engine, contextual adjustments (incl. news), safety gate, 3-tier parlay builder (Banker/Value/High Odds). Bet365 compliant. | NBA Data Extractor data package | NBA Wong Choi / User |
| **NBA Batch QA** | Per-batch structural QA gate. Format drift detection, anti-laziness scan, cross-game consistency check. | Analyst batch output | Wong Choi (pass/fail) |
| **NBA Compliance** | Per-game compliance audit. Template adherence, [FILL] residual scan, math verification, Bet365 format check. Tiered remediation. | Analyst report | Wong Choi (pass/fail verdict) |
| **NBA Reflector** | Post-game review. Compares NBA parlay predictions vs actual box scores, identifies systematic blind spots in volatility engine/safety gate/parlay engine, proposes SIPs. 6-angle REF-DA01 framework. | Game results (web search) + Analyst predictions | Reflector Validator / User / Agent Architect |
| **NBA Reflector Validator** | Blind re-analysis gatekeeper. Validates analytic logic updates via selective game-by-game testing with user checkpoints. | Analysis folder + SIP changelog | User (validation report) |
| **Agent Architect** | Meta-agent. Designs, optimises, and audits agents (3 modes: Build/Optimise/Audit). Health Check with Confidence Scoring. Cross-platform enforcement. | User requirements / Reflector proposals | New/updated SKILL.md + audit_history.md |
| **Game Producer** | 賽馬遊戲開發的總指揮。負責專案的敏捷管理，跨職能協調，將高層次需求拆解為具體任務並推動執行。 | User (Game requirements) | Whole Game Dev Team |
| **Lead Designer** | 遊戲架構師。負責遊戲核心機制、經濟循環與整體體驗設計。 | Game Producer | Content Designer / UX |
| **Content Designer** | 遊戲內容設計師。專注於任務腳本、世界觀與遊戲劇情文字編寫。 | Lead Designer | Game Producer |
| **Pixel Artist** | 遊戲美術開發 (Game Art)。主要產出復古像素風格視覺資產。 | Game Producer / Lead Designer | Game Producer |
| **Sound Designer** | 遊戲音效設計師。負責 BGM 音樂與遊戲音效資產設計。 | Game Producer / Lead Designer | Game Producer |
| **Frontend Engineer**| 遊戲前端開發。主要負責網頁畫面的 UI 構建與動畫呈現。 | Game Producer | Game QA |
| **Backend Engineer** | 遊戲後端開發。負責伺服器架構、API 連接、資料庫等核心邏輯。 | Game Producer | Game QA |
| **Mobile Engineer** | 跨平台手機遊戲開發。負責原生或混合 Mobile App 開發與體驗優化。 | Game Producer | Game QA |
| **Game QA** | 遊戲品質保證工程師 (QA)。負責自動化測試 (Playwright)、邊界條件檢查並發掘潛在 Bug。 | Game Producer / Engineers | Game Producer |
| **Game Ops** | 遊戲營運與客服專家。分析用戶反饋並制定營運策略。 | Game Producer / Analytics Data | Game Producer |

### Agent Chaining Flow — Horse Racing (HKJC/AU)
```
User → Wong Choi (meeting setup + intelligence gathering)
         ↓
       Intelligence Package (written to file — Pattern 13)
         ↓
       Extractor (raw data)
         ↓
       Horse Analyst (per-race deep analysis, batched)
         ↓ per batch
       Batch QA 🚨 (structural + semantic + anti-laziness)
         ↓ PASS ✔️          ↓ FAIL ❌
       next batch        Analyst (redo batch)
         ↓ all batches done
       Compliance Agent (cross-batch trends + SIP audit)
         ↓ PASS ✔️          ↓ FAIL ❌
       Wong Choi           CRITICAL: full redo / MINOR: batch redo
         ↓
       User (final selections)
         ↓ (post-race)
       Reflector (narrative post-mortem + SIP proposals + changelog update)
         ↓ (SIP approved & applied)
       Reflector Validator (selective blind re-analysis with user checkpoints)
```

### Agent Chaining Flow — NBA Parlay
```
User → NBA Wong Choi (date + game selection)
         ↓
       NBA Data Extractor (web search: rosters, injuries, stats, news)
         ↓
       NBA Analyst (volatility → safety gate → 3-tier parlay builder)
         ↓ per batch
       NBA Batch QA 🚨 (structural + format drift + anti-laziness)
         ↓ PASS ✔️          ↓ FAIL ❌
       next batch        Analyst (redo batch)
         ↓ all batches done
       NBA Compliance (per-game template adherence + math verification)
         ↓ PASS ✔️          ↓ FAIL ❌
       NBA Wong Choi      CRITICAL: full redo / MINOR: batch redo
         ↓
       User (final parlay report + auto-save)
         ↓ (post-game)
       NBA Reflector (review & improvement proposals)
         ↓ (SIP approved & applied)
       NBA Reflector Validator (selective blind re-analysis)
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
| **HKJC Wong Choi** | systematic-debugging | 合規 FAILED 2 次 → 3-Phase 閉環(診斷 → 修正 → 重做 Batch) | 🤖 自動 |
| **AU Wong Choi** | systematic-debugging | 合規 FAILED 2 次 → 3-Phase 閉環(診斷 → 修正 → 重做 Batch) | 🤖 自動 |
| **NBA Wong Choi** | systematic-debugging, brainstorming | 品質掃描 FAILED / 自檢總結 | 🤖 自動 |
| **HKJC Horse Analyst** | systematic-debugging | QG-CHECK 連續失敗 2 次 → 根因分析 → 針對性修正 | 🤖 自動 |
| **AU Horse Analyst** | systematic-debugging | QG-CHECK 連續失敗 2 次 → 根因分析 → 針對性修正 | 🤖 自動 |
| **Game Producer** | brainstorming, plan-writing, systematic-debugging | 新功能 / 設計輸出 / QA 失敗 | 🤖 自動 |

**All Wong Choi engines** also reference AG Kit orchestrator patterns: Agent Boundary Enforcement + Conflict Resolution + Status Board.
**All Wong Choi + Analyst debugging** includes **硬性熔斷 (Circuit Breaker)** — 自動修復最多執行 1 次,防止無限 loop。

### Loading Principle
```
Agent 需要 AG Kit skill 時:
1. view_file `.agent/skills/[skill]/SKILL.md`
2. 按需載入原則(lazy-load)— 唔會預先讀取
3. 只讀取,唔複製內容到自己嘅 SKILL.md
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
