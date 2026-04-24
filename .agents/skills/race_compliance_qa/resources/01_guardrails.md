# Race Compliance Guardrails

## Shared Critical Checks
- **RAW-001 invalid raw file**: racecard/formguide/result file is too small, starts with `Error:`, or contains `Traceback`, `Could not find racecard table`, `沒有賽績紀錄`, browser/cloudflare block text, or empty tables.
- **TOP4-001 drift**: `race_analysis.verdict.top4` in Logic JSON does not match the Top4 order rendered in Analysis Markdown.
- **RESULT-001 bad results JSON**: result extractor JSON cannot produce `(race_no, pos, horse_no, horse_name)` records.
- **PLACEHOLDER-001 unresolved marker**: `[AUTO]`, `PLACEHOLDER`, `{{LLM_FILL}}`, `[FILL]`, `[N/A]` remains in a final report section that should be compiled.
- **GRADE-001 dual grading**: compiler/reporter recomputes a grade differently from the canonical engine used by the orchestrator.

## HKJC Notes
- Raw files usually include `排位表.md`, `賽績.md`, `賽果.json`, or `Race N ...`.
- Canonical verdict is Python-owned: `hkjc_orchestrator.py -> auto_compute_verdict_hkjc()`.
- Compiler should render Python-owned verdict order, not invent a second Top4 order.
- Reflector stats must accept `fast_extract_results.py` JSON as well as Markdown/text results.

## AU Notes
- Retired `au_batch_qa` and `au_compliance` are historical references only.
- Live enforcement should live in `au_orchestrator.py`, `completion_gate_v2.py`, and this shared QA layer.
- AU checks should preserve full-field analysis even for low-rated horses; D-grade does not mean abbreviated analysis.

## Output Template
```text
❌ RACE QA FAILED — {platform} {target}
- [CRITICAL] {code}: {file}:{line_or_race} — {problem}
  Fix: {specific action}

Residual risk:
- {anything scanner cannot prove}
```

