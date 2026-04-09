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

## Existing Agents (Auto-Synced)

| Agent | Role | Upstream / Note |
|-------|------|-----------------|
| **HKJC Horse Analyst** | This skill should be used when the user wants to "analyse HKJC horse", "HKJC ... | Auto-Detected |
| **HKJC Batch QA** | This skill should be used when the user wants to "check HKJC batch quality", ... | Auto-Detected |
| **HKJC Reflector** | This skill should be used when the user wants to "覆盤 HKJC", "review HKJC resu... | Auto-Detected |
| **HKJC Compliance Agent** | This skill should be used when the user wants to "check HKJC analysis quality... | Auto-Detected |
| **HKJC Race Extractor** | This skill should be used when the user wants to "extract HKJC race data", "H... | Auto-Detected |
| **HKJC Reflector Validator** | This skill should be used when the user wants to "validate HKJC SIP changes",... | Auto-Detected |
| **HKJC Wong Choi** | This skill should be used when the user wants to "analyse HKJC races", "run H... | Auto-Detected |
| **NBA Reflector Validator** | This skill should be used when the user wants to "validate NBA analysis chang... | Auto-Detected |
| **NBA Wong Choi** | This skill should be used when the user wants to "analyse NBA", "NBA 過關分析", "... | Auto-Detected |
| **NBA Compliance Agent** | This skill should be used when the user wants to "check NBA analysis quality"... | Auto-Detected |
| **NBA Batch QA** | This skill should be used when the user wants to "check NBA output quality", ... | Auto-Detected |
| **NBA Analyst** | This skill should be used when the user wants to "analyse NBA parlay", "NBA 過... | Auto-Detected |
| **NBA Reflector** | This skill should be used when the user wants to "覆盤 NBA", "review NBA result... | Auto-Detected |
| **NBA Data Extractor** | This skill should be used when the user wants to "extract NBA data", "NBA 數據提... | Auto-Detected |
| **lol_reflector** | This skill should be used when the user wants to "覆盤", "post match review", "... | Auto-Detected |
| **betting_accountant** | The rigorous Risk Manager agent for Esports prediction. Applies Fractional Ke... | Auto-Detected |
| **運維及文檔同步 (Game Ops & Doc Sync)** | 呢個 skill 用嚟「更新遊戲」「整返好個bug」「加新馬」「文檔同步」「game maintenance」「update game」「CHANGELO... | Auto-Detected |
| **主遊戲策劃 (Lead Game Designer)** | 呢個 skill 用嚟「核心機制」「遊戲總攬」「GDD打磨」「主策劃」「game design review」「遊戲定義」「成就設計」「多人規則」。旺財街... | Auto-Detected |
| **系統及數值策劃 (Systems & Balance Designer)** | 呢個 skill 用嚟「數值平衡」「賠率算法」「投注系統」「系統設計」「game balance」「經濟模型」「破產機制」「三疊四疊」「泥地賽」。旺財街機... | Auto-Detected |
| **測試工程師 (QA Tester)** | 呢個 skill 用嚟「測試遊戲」「行測試」「QA檢查」「bug報告」「test game」「品質檢查」。旺財街機嘅品質守門員，兩層質檢制度。 | Auto-Detected |
| **內容及情報策劃 (Story & Content Designer)** | 呢個 skill 用嚟「馬匹資料庫」「情報模板」「旺財晨報內容」「內容策劃」「horse database」「game content」「彩衣配色」「評述... | Auto-Detected |
| **前端工程師 (Frontend Engineer)** | 呢個 skill 用嚟「整遊戲UI」「遊戲前端」「投注面板」「街機頁面」「frontend UI」「React組件」「即時排名」「評述UI」。旺財街機嘅 ... | Auto-Detected |
| **像素美術師 (Pixel Artist)** | 呢個 skill 用嚟「像素美術」「遊戲素材」「馬匹精靈圖」「pixel art」「sprites」「UI素材」「彩衣圖標」。旺財街機嘅視覺資產創作者。 | Auto-Detected |
| **移動平台工程師 (Mobile Platform Engineer)** | 呢個 skill 用嚟「iOS」「Android」「手機版」「移動端」「mobile app」「上架 App Store」「Capacitor」。旺財街機... | Auto-Detected |
| **音效設計師 (Sound Designer)** | 呢個 skill 用嚟「遊戲音效」「音樂」「sound effects」「BGM」「街機音效」「馬蹄聲」。旺財街機嘅街機聲音靈魂。 | Auto-Detected |
| **遊戲監製 (Game Producer)** | 呢個 skill 用嚟「策劃遊戲」「設計遊戲」「下一步做咩」「遊戲藍圖」「game roadmap」「開始做遊戲」。旺財街機項目嘅總指揮，負責任務路由、分... | Auto-Detected |
| **遊戲引擎開發員 (Game Engine Developer)** | 呢個 skill 用嚟「遊戲引擎」「比賽引擎」「Canvas渲染」「馬匹物理」「game physics」「race simulation」「三疊四疊」「... | Auto-Detected |
| **AU Compliance Agent** | This skill should be used when the user wants to "check AU analysis quality",... | Auto-Detected |
| **AU Horse Race Reflector** | This skill should be used when the user wants to "覆盤 AU races", "review AU re... | Auto-Detected |
| **AU Wong Choi** | This skill should be used when the user wants to "analyse AU races", "run AU ... | Auto-Detected |
| **AU Race Extractor** | This skill should be used when the user wants to "extract AU race data", "AU ... | Auto-Detected |
| **AU Batch QA** | This skill should be used when the user wants to "check AU batch quality", "A... | Auto-Detected |
| **AU Horse Analyst** | This skill should be used when the user wants to "analyse AU horse", "澳洲馬匹分析"... | Auto-Detected |
| **AU Racecourse Weather Prediction** | This skill should be used when the user wants to "predict AU track condition"... | Auto-Detected |
| **AU Reflector Validator** | This skill should be used when the user wants to "validate AU SIP changes", "... | Auto-Detected |
| **Lead Agent Architect** | This skill should be used when the user wants to "build a new agent", "design... | Auto-Detected |
| **lol_wong_choi** | This skill should be used when the user wants to "分析[日期] [賽區]", "analyse espo... | Auto-Detected |

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

