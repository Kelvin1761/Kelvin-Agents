---
name: HKJC Racing
description: Thin router for Hong Kong Jockey Club racing workflows. Use hkjc_wong_choi for pre-race analysis, hkjc_race_extractor for data extraction, hkjc_horse_analyst for per-horse analysis rules, and hkjc_reflector for post-race review.
version: 1.0.0
---

# HKJC Racing Router

This skill exists so agent frontmatter entry `hkjc_racing` resolves cleanly.

For live HKJC pre-race analysis, read and follow:
- `.agents/skills/hkjc_racing/hkjc_wong_choi/SKILL.md`

Runtime remains Python-first. Do not invoke deprecated `hkjc_batch_qa` or `hkjc_compliance` as active agents; their former checks are handled by `hkjc_orchestrator.py` and `.agents/scripts/completion_gate_v2.py`.

## Failure Protocol

If a requested child skill is missing or cannot be read, stop and report the exact missing path instead of guessing another HKJC workflow.
