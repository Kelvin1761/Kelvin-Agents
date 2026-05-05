# HKJC LangGraph Racing Pipeline — Operator Runbook

## Quick Start

### Manual Mode (Default)
```bash
python .agents/scripts/racing_graph_core.py \
    --target-dir "path/to/meeting_dir" \
    --domain hkjc
```

### Autopilot Mode
```bash
export RACING_AGENT_CMD="python .agents/scripts/run_horse_agent.py"
export HORSE_AGENT_BACKEND="antigravity"  # or "codex"

python .agents/scripts/racing_graph_core.py \
    --target-dir "path/to/meeting_dir" \
    --domain hkjc \
    --autopilot
```

---

## Pipeline Flow

```
check_raw_data → generate_facts → extract_trackwork → setup_race
    → generate_workcard → [agent fills JSON] → watch_and_validate
    → batch_qa → next_horse / compute_verdict
    → compile_analysis → monte_carlo → final_qa → advance_race
    → (repeat for next race) → generate_reports
```

## Key Environment Variables

| Variable | Purpose | Example |
|:---|:---|:---|
| `RACING_AGENT_CMD` | Autopilot bridge command | `python .agents/scripts/run_horse_agent.py` |
| `HORSE_AGENT_BACKEND` | Agent backend for bridge | `antigravity`, `codex` |

---

## Common Operations

### Resume After Timeout
The pipeline now uses `waiting` state instead of fatal `timeout`.
Simply re-run the same command — it resumes from where it stopped.

### Resume After QA Failure
QA strikes are persisted in `.qa_strikes.json` in the target directory.
Fix the flagged issues, then re-run. Strikes carry over across restarts.

### Check QA Strike Count
```bash
cat path/to/meeting_dir/.qa_strikes.json
```

### Reset QA Strikes
```bash
rm path/to/meeting_dir/.qa_strikes.json
```

---

## Troubleshooting

### Pipeline stops immediately on resume
**Cause**: `should_stop` was `True` from a previous QA failure.
**Fix**: This is now automatically reset by `node_setup_race`. If using an older version, update the code.

### "Compile script not found"
**Cause**: HKJC compiler template missing.
**Fix**: Verify `compile_analysis_template_hkjc.py` exists in:
```
.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/
```

### "Skeleton produced no valid entry"
**Cause**: Skeleton generator failed to create horse entry in Logic.json.
**Fix**: Check Facts.md has valid horse blocks (`### 馬號 X`). Re-run facts generation if needed.

### Speed map flagged as incomplete (HKJC)
**Cause**: Old code only checked `expected_pace`. HKJC uses `predicted_pace`.
**Fix**: Update to latest code — `_speed_map_ready()` now handles both.

### "Autopilot requested but RACING_AGENT_CMD is not set"
**Cause**: `--autopilot` flag used but env var missing.
**Fix**: `export RACING_AGENT_CMD="python .agents/scripts/run_horse_agent.py"`

### RecursionError / "Recursion limit reached"
**Cause**: Large meeting exceeded node transition limit.
**Fix**: Update `recursion_limit` in `racing_graph_core.py` (default now 500).

---

## Running Smoke Tests
```bash
python .agents/scripts/test_hkjc_langgraph_smoke.py
```

Expected: All 20+ tests pass. If any fail, check the specific test output for details.

---

## File Reference

| File | Purpose |
|:---|:---|
| `racing_graph_core.py` | Graph builder + entry points |
| `racing_graph_nodes.py` | Node functions (business logic wrappers) |
| `racing_graph_state.py` | State schema (MeetingState TypedDict) |
| `run_horse_agent.py` | Autopilot bridge script |
| `completion_gate_v2.py` | QA validation gate |
| `test_hkjc_langgraph_smoke.py` | Smoke tests |
