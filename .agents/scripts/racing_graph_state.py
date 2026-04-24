#!/usr/bin/env python3
"""
LangGraph Racing Pipeline — State Definitions
===============================================
TypedDict schemas for the LangGraph StateGraph.
These replace the ad-hoc dict structures in .meeting_state.json
while remaining fully compatible with existing JSON persistence.
"""
from __future__ import annotations
from typing import TypedDict, Optional, Any
from typing_extensions import Annotated
import operator


class RaceState(TypedDict, total=False):
    """Per-race analysis state."""
    race_num: int
    distance: str
    race_class: str
    horses_total: int
    horses_done: list[int]
    horses_pending: list[int]
    speed_map_ready: bool
    verdict_done: bool
    compiled: bool
    mc_done: bool
    qa_strikes: int
    qa_passed: bool
    stage: str  # NOT_STARTED / AWAITING_SM / ANALYSING / VERDICT / COMPILE / MC / QA / COMPLETE


class MeetingState(TypedDict, total=False):
    """Meeting-level state — the LangGraph State object.
    
    This is the single source of truth that flows through the graph.
    Each node reads from it and returns a partial dict to update it.
    """
    # ── Identity ──
    target_dir: str
    venue: str
    date_prefix: str
    short_prefix: str
    total_races: int
    url: Optional[str]
    
    # ── Pre-conditions ──
    raw_data_ready: bool
    intelligence_ready: bool
    facts_ready: bool
    
    # ── Per-race states ──
    races: dict[str, RaceState]
    current_race: int
    
    # ── Current horse analysis ──
    current_horse: Optional[int]
    current_horse_result: Optional[str]  # 'pass' / 'fail' / 'timeout'
    completed_in_session: int
    
    # ── Global flags ──
    overall_stage: str  # EXTRACT / INTEL / FACTS / ANALYSING / COMPLETE
    should_stop: bool
    stop_reason: str
    
    # ── Domain config reference ──
    domain: str  # 'au' or 'hkjc'
    
    # ── Accumulated log messages ──
    log: Annotated[list[str], operator.add]
