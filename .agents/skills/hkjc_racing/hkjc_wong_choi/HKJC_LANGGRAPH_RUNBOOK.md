# HKJC LangGraph Runbook

## Manual Mode

```bash
python .agents/scripts/racing_graph_core.py "<TARGET_MEETING_DIR>" --domain hkjc
```

If the local machine has no `python` launcher, use `python3` with the same arguments.

## Autopilot Mode

```bash
export RACING_AGENT_CMD="python .agents/scripts/run_horse_agent.py"
export HORSE_AGENT_BACKEND="antigravity"

python .agents/scripts/racing_graph_core.py "<TARGET_MEETING_DIR>" --domain hkjc --autopilot
```

Required env vars:
- `RACING_AGENT_CMD`: external horse-agent command.
- `HORSE_AGENT_BACKEND`: `manual`, `antigravity`, or `codex`.

## Flow

WorkCards are generated under `<TARGET_MEETING_DIR>/.runtime/Horse_N_WorkCard.md`.
The active race JSON is `<TARGET_MEETING_DIR>/Race_X_Logic.json`; only `horses.N` should be filled by the analyst or agent.

Resume is state-driven:
- LangGraph checkpoint, when configured, uses the meeting thread id.
- `.meeting_state.json` stores current race, current horse, QA strikes, waiting state, and next action.
- `--status` prints the saved session dashboard.

QA strikes are persisted in `.qa_strikes.json` as `race_X_qa`. Passing final QA resets the strike to `0`.

Dummy quarantine:
- `racing_content_guard.py` scans Logic JSON, Analysis.md, completion gate, and report inputs.
- Bad outputs move to `.runtime/quarantine/` with a matching `.reason.txt`.
- A race with quarantined analysis is not treated as compiled or complete.

Common failures:
- `Autopilot requested but RACING_AGENT_CMD is not set`: export the command or run manual mode.
- `compile_blocked_Race_X.txt`: inspect the exact field errors, then repair `Race_X_Logic.json`.
- `final_qa_failed_Race_X.txt`: repair the JSON source and recompile; do not edit Analysis.md.
- Trackwork missing: rerun extraction or use `--allow-missing-trackwork` only when deliberately accepted.

Do not:
- create `auto_fill` scripts;
- bypass WorkCards;
- manually edit `Analysis.md`;
- infer matrix from `final_rating`;
- use predicted pace as HKJC `race_shape` scoring evidence.
