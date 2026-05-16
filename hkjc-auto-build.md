# HKJC Wong Choi Auto Build

## Goal
Build a separate Python-only HKJC Wong Choi Auto wrapper that scores existing `Race_*_Logic.json` files without changing the classic HKJC Wong Choi pipeline.

## Tasks
- [x] Add separate `hkjc-wong-choi-auto` agent and skill entrypoint.
- [x] Build typed extraction + data availability gate.
- [x] Build 12 feature scorers, 7D matrix, grading, ranking, NLG, validation.
- [x] Build CLI wrapper + Markdown/CSV renderer.
- [x] Add unit/integration tests.
- [x] Run compile/tests/dry run.

## Done When
- [x] Every horse gets `python_auto` with 12 sub-scores, 7D numeric scores, ability score, grade, rank, pick status, reason/risk codes, provenance, and Python NLG core logic.
- [x] Race-level `python_auto_verdict` is sorted only by `ability_score`.
- [x] Auto outputs contain no tick scoring, no odds/value/pace scoring, no `[FILL]`, and no LLM-generated fields.
