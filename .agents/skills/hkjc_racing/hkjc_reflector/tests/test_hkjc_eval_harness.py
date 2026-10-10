"""Unified HKJC eval harness: paired compare must produce a Stage 4 verdict and
drop meetings whose leaves were dead (e.g. 2026-04 speed_score)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hkjc_eval_harness as harness  # noqa: E402


def _rows(path: Path, good_flip: bool, dead_first: bool):
    lines = []
    for day_index in range(10):
        day = f"2026-09-{day_index + 1:02d}"
        for race in range(1, 4):
            good = bool((race + day_index) % 2) if not good_flip else True
            lines.append(json.dumps({
                "arm": "x", "date": day, "meeting": f"{day}_ShaTin", "race": race,
                "venue": "沙田", "awt": False, "distance": 1200, "field": 12,
                "picks": [1, 2, 3], "gold": good, "gold_strict": good, "good_positional": good,
                "champion": good, "top3_capture_at5": 0.6, "ndcg_at5": 0.5,
                "competitive_recall_at5": 0.5, "mean_top3_model_rank": 4.0,
                "meeting_dead_fields": ["speed_score"] if dead_first and day_index == 0 else [],
            }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_compare_produces_verdict_and_excludes_dead_meetings(tmp_path, capsys):
    base, cand = tmp_path / "b.jsonl", tmp_path / "c.jsonl"
    _rows(base, good_flip=False, dead_first=True)
    _rows(cand, good_flip=False, dead_first=True)
    out = tmp_path / "r.json"
    assert harness.main(["compare", str(base), str(cand), "--leakage-audit-passed", "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["races"] == 27            # first meeting (3 races) dropped: dead speed_score
    assert report["races_with_ranking_change"] == 0
    assert report["verdict"]["verdict"] == "REJECT"   # identical arms cannot win


def test_meeting_pattern_ignores_analyst_copies():
    assert harness.MEETING_RE.match("2026-10-07_HappyValley")
    assert not harness.MEETING_RE.match("2026-04-01_ShaTin (Kelvin)")
