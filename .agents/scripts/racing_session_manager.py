#!/usr/bin/env python3
"""
Racing Session Manager
======================
Safe session status persistence for AU/HKJC LangGraph runs.

No horse analysis, no racing validation, and no domain business logic lives here.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any


SESSION_VERSION = "LG_SESSION_V1"


def session_state_path(target_dir: str) -> str:
    return os.path.join(target_dir, ".meeting_state.json")


def load_session_state(target_dir: str) -> dict[str, Any]:
    path = session_state_path(target_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def save_session_state(target_dir: str, state: dict[str, Any]) -> None:
    path = session_state_path(target_dir)
    tmp_path = path + ".tmp"
    payload = dict(state)
    payload.setdefault("_version", SESSION_VERSION)
    payload["_last_updated"] = dt.datetime.now().isoformat(timespec="seconds")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def normalise_done_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int):
        return value
    return 0


def build_session_snapshot(graph_state: dict[str, Any]) -> dict[str, Any]:
    races = graph_state.get("races", {})
    safe_races = races if isinstance(races, dict) else {}
    snapshot = {
        "_version": SESSION_VERSION,
        "_last_updated": dt.datetime.now().isoformat(timespec="seconds"),
        "target_dir": graph_state.get("target_dir", ""),
        "venue": graph_state.get("venue", ""),
        "date_prefix": graph_state.get("date_prefix", ""),
        "short_prefix": graph_state.get("short_prefix", ""),
        "total_races": graph_state.get("total_races", 0),
        "current_race": graph_state.get("current_race", 1),
        "current_horse": graph_state.get("current_horse"),
        "overall_stage": graph_state.get("overall_stage", ""),
        "should_stop": bool(graph_state.get("should_stop", False)),
        "stop_reason": graph_state.get("stop_reason", ""),
        "autopilot": bool(graph_state.get("autopilot", False)),
        "waiting_for_agent": bool(graph_state.get("waiting_for_agent", False)),
        "completed_in_session": graph_state.get("completed_in_session", 0),
        "trackwork_ready": bool(graph_state.get("trackwork_ready", False)),
        "trackwork_status": graph_state.get("trackwork_status", ""),
        "trackwork_required": bool(graph_state.get("trackwork_required", False)),
        "allow_missing_trackwork": bool(graph_state.get("allow_missing_trackwork", False)),
        "races": safe_races,
    }
    snapshot["next_action"] = determine_next_action(snapshot)
    return snapshot


def determine_next_action(session: dict[str, Any]) -> dict[str, Any]:
    if session.get("should_stop"):
        return {"type": "STOPPED", "reason": session.get("stop_reason", "")}

    if (
        session.get("trackwork_required")
        and not session.get("trackwork_ready")
        and not session.get("allow_missing_trackwork")
    ):
        return {
            "type": "TRACKWORK_REQUIRED",
            "message": "HKJC trackwork is missing or failed. Analysis has stopped before setup_race.",
            "status": session.get("trackwork_status", ""),
        }

    if session.get("waiting_for_agent"):
        return {
            "type": "WAIT_FOR_AGENT",
            "race": session.get("current_race"),
            "horse": session.get("current_horse"),
            "message": "Waiting for agent to complete current horse.",
        }

    if session.get("overall_stage") == "COMPLETE":
        return {"type": "COMPLETE"}

    races = session.get("races", {})
    current_race = str(session.get("current_race", 1))
    race_state = races.get(current_race, {}) if isinstance(races, dict) else {}
    pending = race_state.get("horses_pending", []) if isinstance(race_state, dict) else []
    if pending:
        return {
            "type": "ANALYSE_NEXT_HORSE",
            "race": session.get("current_race", 1),
            "horse": pending[0],
        }
    if race_state:
        return {
            "type": "CONTINUE_RACE",
            "race": session.get("current_race", 1),
            "stage": race_state.get("stage", session.get("overall_stage", "")),
        }
    return {"type": "RUN_GRAPH", "stage": session.get("overall_stage", "")}


def _trackwork_label(session: dict[str, Any]) -> str:
    if not session.get("trackwork_required"):
        return "NOT REQUIRED"
    if session.get("trackwork_ready"):
        return f"READY ({session.get('trackwork_status', '')})"
    status = str(session.get("trackwork_status", "")).upper() or "MISSING"
    return status


def print_session_dashboard(session: dict[str, Any]) -> None:
    next_action = session.get("next_action") or determine_next_action(session)
    print("=" * 60)
    print("📊 Racing Session Dashboard")
    print("=" * 60)
    print(f"Target: {session.get('target_dir') or session.get('_target_dir', '')}")
    print(f"Autopilot: {'ON' if session.get('autopilot') else 'OFF'}")
    print(f"Trackwork: {_trackwork_label(session)}")
    print(f"Allow missing trackwork: {'YES' if session.get('allow_missing_trackwork') else 'NO'}")
    print(f"Overall: {session.get('overall_stage') or session.get('next_action', '')}")
    print(f"Current: Race {session.get('current_race', '-')} Horse {session.get('current_horse', '-')}")
    print("Race progress:")
    races = session.get("races", {})
    if isinstance(races, dict) and races:
        for r_key in sorted(races, key=lambda x: int(x) if str(x).isdigit() else 999):
            rs = races.get(r_key, {})
            if not isinstance(rs, dict):
                continue
            done = normalise_done_count(rs.get("horses_done", 0))
            total = rs.get("horses_total", 0)
            stage = rs.get("stage", "UNKNOWN")
            strikes = rs.get("qa_strikes", 0)
            print(f"Race {r_key}: {done}/{total} horses done | stage={stage} | qa_strikes={strikes}")
    else:
        print("(no race state yet)")
    print(f"Next action: {next_action}")
    print("=" * 60)


def persist_graph_state(target_dir: str, graph_state: dict[str, Any]) -> dict[str, Any]:
    snapshot = build_session_snapshot(graph_state)
    save_session_state(target_dir, snapshot)
    return snapshot
