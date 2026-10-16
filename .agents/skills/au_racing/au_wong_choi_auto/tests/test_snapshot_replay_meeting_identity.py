"""A pre-race snapshot replayed in place must read the meeting date/venue like live.

Snapshots live at `<meeting>/_prediction_snapshots/<20261014T004339…>/`; that folder
name has no date. Before `_meeting_dir`, replaying in place blanked the meeting date,
so `refresh_form_quality` dropped every run (0/376 runners on 2026-10-14) and the
date-gated Formguide parsers lost their cut-off.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine import engine_core as ec  # noqa: E402

MEETING = "2026-10-14 Caulfield Race 1-8"


def run_line(date, finish, starters, prize):
    return (f"Sandown R5 {date} 1400m cond:Good ${prize} J Rider (3) 57.0kg Flucs:$- $5.00 "
            f"3rd@800m 3rd@400m 3rd@Settled. margin:1.50L starters:{starters} "
            f"finish:{finish}/{starters} RaceClass:[BM78] WinningTime:1:23.100\n"
            "1-A (57.0kg), 2-B (57.0kg) 0.50L, 3-C (57.0kg) 0.80L\nVideo: \nNote: \nStewards: \n\n")


def formguide():
    text = "RACE 2 — 1400m | Fixture\nTrack: Good 4 | Weather: Unknown | Rail: \n" + "=" * 60 + "\n"
    for number, (finish, prize) in enumerate(((1, 120000), (5, 40000), (9, 25000)), start=1):
        text += f"[{number}] Horse {number} ({number})\n4yoG | Sire: S | Dam: D\n\n"
        text += run_line("2026-09-20", finish, 10, prize) + run_line("2026-09-01", finish, 10, prize)
        text += run_line("2026-10-14", 1, 10, 999999)  # the race itself: must be cut off
    return text


def layouts(tmp_path):
    meeting = tmp_path / MEETING
    meeting.mkdir()
    (meeting / "10-14 Race 2 Facts.md").write_text("Race 2\n", encoding="utf-8")
    (meeting / "10-14 Race 2 Formguide.md").write_text(formguide(), encoding="utf-8")
    snap = meeting / "_prediction_snapshots" / "20261014T004339.004000+1100-f721ecf9f121"
    shutil.copytree(meeting, snap, ignore=shutil.ignore_patterns("_prediction_snapshots"))
    return meeting / "10-14 Race 2 Facts.md", snap / "10-14 Race 2 Facts.md"


def logic():
    return {"race_analysis": {"race_number": 2},
            "horses": {str(n): {"horse_name": f"Horse {n}"} for n in (1, 2, 3)}}


def test_meeting_dir_resolves_snapshot_layout(tmp_path):
    live, snap = layouts(tmp_path)
    assert ec._meeting_dir(live).name == MEETING
    assert ec._meeting_dir(snap).name == MEETING


def test_form_quality_matches_live_when_replayed_in_snapshot(tmp_path):
    live, snap = layouts(tmp_path)
    a, b = logic(), logic()
    assert ec.refresh_form_quality(a, live) == 3
    assert ec.refresh_form_quality(b, snap) == 3
    for n in ("1", "2", "3"):
        assert a["horses"][n]["_data"] == b["horses"][n]["_data"]
        assert a["horses"][n]["_data"]["form_quality_run_count"] == 2  # same-day run excluded


def test_formguide_digests_and_meeting_context_match(tmp_path):
    live, snap = layouts(tmp_path)
    assert ec._load_formguide_digests(live, 2) == ec._load_formguide_digests(snap, 2)
    ctx_live = ec._meeting_context_from_extractor_files(live, 2)
    ctx_snap = ec._meeting_context_from_extractor_files(snap, 2)
    assert ctx_snap["date"] == ctx_live["date"] == "2026-10-14"
    assert ctx_snap["venue"] == ctx_live["venue"]
    assert ec._parse_formguide_pf_metrics(live) == ec._parse_formguide_pf_metrics(snap)
