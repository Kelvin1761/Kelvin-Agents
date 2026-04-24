#!/usr/bin/env python3
"""
LangGraph Racing Pipeline — Graph Core
========================================
Builds the StateGraph with conditional edges.
Phase 2: SQLite checkpoint for crash recovery.
"""
import os
import sys
from typing import Literal

from langgraph.graph import StateGraph, START, END

# Local imports
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

from racing_graph_state import MeetingState
from racing_graph_nodes import (
    node_check_raw_data, node_check_intelligence, node_generate_facts,
    node_setup_race, node_generate_workcard, node_watch_and_validate,
    node_batch_qa, node_global_qa, node_compute_verdict,
    node_compile_analysis, node_run_monte_carlo, node_final_qa,
    node_advance_race, node_generate_reports,
)


# ═══════════════════════════════════════════════════════════════
# ROUTING FUNCTIONS (replace the giant if/elif chain)
# ═══════════════════════════════════════════════════════════════

def route_after_raw_check(state: MeetingState) -> Literal["check_intel", "__end__"]:
    if state.get("raw_data_ready"):
        return "check_intel"
    return "__end__"  # Can't proceed without raw data


def route_after_intel_check(state: MeetingState) -> Literal["gen_facts", "__end__"]:
    if state.get("intelligence_ready"):
        return "gen_facts"
    return "__end__"


def route_after_facts(state: MeetingState) -> Literal["setup_race", "__end__"]:
    if state.get("facts_ready"):
        return "setup_race"
    return "__end__"


def route_after_setup(state: MeetingState) -> Literal["gen_workcard", "global_qa"]:
    """After race setup: if pending horses → workcard, else → global QA."""
    races = state.get("races", {})
    r = state.get("current_race", 1)
    race_state = races.get(str(r), {})
    pending = race_state.get("horses_pending", [])
    if pending:
        return "gen_workcard"
    return "global_qa"  # All horses already done


def route_after_watch(state: MeetingState) -> Literal["batch_qa", "gen_workcard", "global_qa", "__end__"]:
    """After horse watch: check result → batch QA / next horse / done."""
    if state.get("should_stop"):
        return "__end__"

    result = state.get("current_horse_result", "")
    if result == "timeout":
        return "__end__"

    completed = state.get("completed_in_session", 0)
    races = state.get("races", {})
    r = state.get("current_race", 1)
    race_state = races.get(str(r), {})
    pending = race_state.get("horses_pending", [])

    # Batch QA every 3 horses
    if completed > 0 and completed % 3 == 0:
        return "batch_qa"

    if pending:
        return "gen_workcard"
    return "global_qa"


def route_after_batch_qa(state: MeetingState) -> Literal["gen_workcard", "global_qa"]:
    """After batch QA: if pending → next horse, else → global QA."""
    races = state.get("races", {})
    r = state.get("current_race", 1)
    race_state = races.get(str(r), {})
    pending = race_state.get("horses_pending", [])
    if pending:
        return "gen_workcard"
    return "global_qa"


def route_after_global_qa(state: MeetingState) -> Literal["verdict", "__end__"]:
    if state.get("should_stop"):
        return "__end__"
    return "verdict"


def route_after_final_qa(state: MeetingState) -> Literal["advance_race", "__end__"]:
    if state.get("should_stop"):
        return "__end__"
    return "advance_race"


def route_after_advance(state: MeetingState) -> Literal["setup_race", "reports"]:
    if state.get("overall_stage") == "COMPLETE":
        return "reports"
    return "setup_race"


# ═══════════════════════════════════════════════════════════════
# GRAPH BUILDER
# ═══════════════════════════════════════════════════════════════

def build_au_racing_graph(checkpoint_db=None):
    """Build the AU Racing LangGraph StateGraph.
    
    Args:
        checkpoint_db: Path to SQLite DB for checkpointing (Phase 2).
                       If None, runs without persistence.
    Returns:
        Compiled LangGraph application.
    """
    builder = StateGraph(MeetingState)

    # ── Add Nodes ──
    builder.add_node("check_raw", node_check_raw_data)
    builder.add_node("check_intel", node_check_intelligence)
    builder.add_node("gen_facts", node_generate_facts)
    builder.add_node("setup_race", node_setup_race)
    builder.add_node("gen_workcard", node_generate_workcard)
    builder.add_node("watch_validate", node_watch_and_validate)
    builder.add_node("batch_qa", node_batch_qa)
    builder.add_node("global_qa", node_global_qa)
    builder.add_node("verdict", node_compute_verdict)
    builder.add_node("compile", node_compile_analysis)
    builder.add_node("mc_sim", node_run_monte_carlo)
    builder.add_node("final_qa", node_final_qa)
    builder.add_node("advance_race", node_advance_race)
    builder.add_node("reports", node_generate_reports)

    # ── Entry ──
    builder.add_edge(START, "check_raw")

    # ── Conditional Edges ──
    builder.add_conditional_edges("check_raw", route_after_raw_check)
    builder.add_conditional_edges("check_intel", route_after_intel_check)
    builder.add_conditional_edges("gen_facts", route_after_facts)
    builder.add_conditional_edges("setup_race", route_after_setup)

    # workcard → watch
    builder.add_edge("gen_workcard", "watch_validate")

    # watch → batch_qa / gen_workcard / global_qa / END
    builder.add_conditional_edges("watch_validate", route_after_watch)

    # batch_qa → gen_workcard / global_qa
    builder.add_conditional_edges("batch_qa", route_after_batch_qa)

    # global_qa → verdict / END
    builder.add_conditional_edges("global_qa", route_after_global_qa)

    # verdict → compile → mc → final_qa
    builder.add_edge("verdict", "compile")
    builder.add_edge("compile", "mc_sim")
    builder.add_edge("mc_sim", "final_qa")

    # final_qa → advance / END
    builder.add_conditional_edges("final_qa", route_after_final_qa)

    # advance → setup_race / reports
    builder.add_conditional_edges("advance_race", route_after_advance)

    # reports → END
    builder.add_edge("reports", END)

    # ── Compile ──
    compile_kwargs = {}
    if checkpoint_db:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3
            conn = sqlite3.connect(checkpoint_db, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
            compile_kwargs["checkpointer"] = checkpointer
            print(f"✅ Checkpoint DB: {os.path.basename(checkpoint_db)}")
        except Exception as e:
            print(f"⚠️ Checkpoint setup failed ({e}), running without persistence")

    return builder.compile(**compile_kwargs)


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT — for standalone testing
# ═══════════════════════════════════════════════════════════════

def run_au_langgraph(target_dir, url=None, checkpoint_db=None):
    """Run the AU Racing pipeline using LangGraph.
    
    This is the LangGraph equivalent of au_orchestrator.py's main().
    Supports crash recovery via SQLite checkpoint when checkpoint_db is provided.
    """
    dir_name = os.path.basename(target_dir)
    parts = dir_name.split(" ", 1)
    date_prefix = parts[0] if parts else "unknown"
    venue = parts[1] if len(parts) > 1 else "Unknown"
    short_prefix = date_prefix[5:] if len(date_prefix) == 10 else date_prefix

    # Import AU orchestrator for helper functions
    sys.path.insert(0, os.path.abspath(os.path.join(_SCRIPT_DIR, '..', 'skills',
                                                     'au_racing', 'au_wong_choi', 'scripts')))
    from au_orchestrator import discover_total_races, print_context_injection_au

    total_races = discover_total_races(target_dir)

    print("=" * 60)
    print("🏇 AU Wong Choi Orchestrator — LangGraph Mode")
    print("=" * 60)
    print_context_injection_au()
    print(f"✅ Target: {dir_name}")
    print(f"✅ Races: {total_races}\n")

    # Auto-detect checkpoint DB if not provided
    if not checkpoint_db:
        _db_dir = os.path.expanduser("~/.gemini/antigravity/databases")
        _db_path = os.path.join(_db_dir, "langgraph_checkpoints.db")
        if os.path.isdir(_db_dir):
            checkpoint_db = _db_path

    # Build initial state
    initial_state = {
        "target_dir": os.path.abspath(target_dir),
        "venue": venue,
        "date_prefix": date_prefix,
        "short_prefix": short_prefix,
        "total_races": total_races,
        "url": url,
        "raw_data_ready": False,
        "intelligence_ready": False,
        "facts_ready": False,
        "races": {},
        "current_race": 1,
        "current_horse": None,
        "current_horse_result": None,
        "completed_in_session": 0,
        "overall_stage": "STARTING",
        "should_stop": False,
        "stop_reason": "",
        "domain": "au",
        "log": [],
    }

    # Build and run graph (with optional checkpointing)
    app = build_au_racing_graph(checkpoint_db=checkpoint_db)
    thread_id = dir_name.replace(" ", "_").lower()
    config = {"recursion_limit": 200}
    if checkpoint_db:
        config["configurable"] = {"thread_id": thread_id}
        print(f"🔄 Thread: {thread_id} (checkpoint-enabled)")

    final_state = app.invoke(initial_state, config=config)

    # Summary
    print("\n" + "=" * 60)
    print("📊 LangGraph Pipeline Summary")
    print("=" * 60)
    if final_state.get("should_stop"):
        print(f"⚠️ Stopped: {final_state.get('stop_reason', 'unknown')}")
    elif final_state.get("overall_stage") == "COMPLETE":
        print("🎉 All races complete!")
    print(f"Log entries: {len(final_state.get('log', []))}")
    if checkpoint_db:
        print(f"💾 Checkpoint saved to: {os.path.basename(checkpoint_db)}")

    return final_state


def run_hkjc_langgraph(target_dir, url=None, checkpoint_db=None):
    """Run the HKJC Racing pipeline using LangGraph.
    
    This is the LangGraph equivalent of hkjc_orchestrator.py's main().
    """
    dir_name = os.path.basename(target_dir)
    parts = dir_name.split(" ", 1)
    date_prefix = parts[0] if parts else "unknown"
    venue = parts[1] if len(parts) > 1 else "Unknown"
    short_prefix = date_prefix[5:] if len(date_prefix) == 10 else date_prefix

    # Import HKJC orchestrator for helper functions
    _hkjc_scripts = os.path.join(_SCRIPT_DIR, '..', 'skills',
                                  'hkjc_racing', 'hkjc_wong_choi', 'scripts')
    sys.path.insert(0, os.path.abspath(_hkjc_scripts))
    from hkjc_orchestrator import discover_total_races, print_context_injection

    total_races = discover_total_races(target_dir)

    print("=" * 60)
    print("🏇 HKJC Wong Choi Orchestrator — LangGraph Mode")
    print("=" * 60)
    print_context_injection()
    print(f"✅ Target: {dir_name}")
    print(f"✅ Races: {total_races}\n")

    # Auto-detect checkpoint DB
    if not checkpoint_db:
        _db_dir = os.path.expanduser("~/.gemini/antigravity/databases")
        _db_path = os.path.join(_db_dir, "langgraph_checkpoints.db")
        if os.path.isdir(_db_dir):
            checkpoint_db = _db_path

    initial_state = {
        "target_dir": os.path.abspath(target_dir),
        "venue": venue,
        "date_prefix": date_prefix,
        "short_prefix": short_prefix,
        "total_races": total_races,
        "url": url,
        "raw_data_ready": False,
        "intelligence_ready": False,
        "facts_ready": False,
        "races": {},
        "current_race": 1,
        "current_horse": None,
        "current_horse_result": None,
        "completed_in_session": 0,
        "overall_stage": "STARTING",
        "should_stop": False,
        "stop_reason": "",
        "domain": "hkjc",  # HKJC domain
        "log": [],
    }

    app = build_au_racing_graph(checkpoint_db=checkpoint_db)
    thread_id = dir_name.replace(" ", "_").lower()
    config = {"recursion_limit": 200}
    if checkpoint_db:
        config["configurable"] = {"thread_id": thread_id}
        print(f"🔄 Thread: {thread_id} (checkpoint-enabled)")

    final_state = app.invoke(initial_state, config=config)

    print("\n" + "=" * 60)
    print("📊 LangGraph Pipeline Summary")
    print("=" * 60)
    if final_state.get("should_stop"):
        print(f"⚠️ Stopped: {final_state.get('stop_reason', 'unknown')}")
    elif final_state.get("overall_stage") == "COMPLETE":
        print("🎉 All races complete!")
    print(f"Log entries: {len(final_state.get('log', []))}")
    if checkpoint_db:
        print(f"💾 Checkpoint saved to: {os.path.basename(checkpoint_db)}")

    return final_state


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Racing LangGraph Pipeline (AU/HKJC)")
    parser.add_argument("target_dir", help="Path to race meeting directory")
    parser.add_argument("--url", help="Source URL (optional)", default=None)
    parser.add_argument("--domain", choices=["au", "hkjc"], default="au",
                        help="Racing domain: au (default) or hkjc")
    args = parser.parse_args()

    if not os.path.isdir(args.target_dir):
        print(f"❌ Not a directory: {args.target_dir}")
        sys.exit(1)

    if args.domain == "hkjc":
        run_hkjc_langgraph(args.target_dir, args.url)
    else:
        run_au_langgraph(args.target_dir, args.url)
