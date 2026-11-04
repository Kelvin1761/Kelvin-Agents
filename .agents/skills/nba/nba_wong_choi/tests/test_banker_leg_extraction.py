"""SGM summary reports come from the sidecars, never the Markdown.

Banker 速覽 showed N/A on every row (2026-10-22) when it searched the report text for a
label the report never printed. The 穩膽 banker leg is the highest-EV leg inside combo 1.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_nba_sgm_reports.py"
sys.path.insert(0, str(SCRIPT.parent))
from generate_nba_sgm_reports import banker_leg  # noqa: E402

LEGS = [{"player": "Paolo Banchero", "market": "reb", "line": 8.0, "price": 1.52, "p_final": 0.98,
         "desc": "Paolo Banchero (ORL) REB 8+"},
        {"player": "Wendell Carter Jr.", "market": "ast", "line": 2.0, "price": 1.87, "p_final": 0.73,
         "desc": "Wendell Carter Jr. (ORL) AST 2+"}]
SIDECAR = {"combos": [{"combo_id": "1", "legs": LEGS, "sportsbet_sgm_price": 2.84, "adjusted_joint_prob": 0.7,
                       "heading": "🛡️ 組合 1: Banker SGM（2 Legs）— 組合賠率 @2.84"},
                      {"combo_id": "2", "legs": [{"player": "Someone", "market": "pts", "line": 30.0, "price": 7.5,
                                                  "p_final": 0.6, "desc": "Someone (ATL) PTS 30+"}]}],
           "legs": LEGS}


def test_picks_highest_ev_leg_inside_combo_one() -> None:
    assert banker_leg(SIDECAR) == "Paolo Banchero (ORL) REB 8+ @1.52 (EV +49.0%)"


def test_does_not_use_another_combos_longshot() -> None:
    assert "Someone" not in banker_leg(SIDECAR)


def test_no_combo_one_gives_none() -> None:
    assert banker_leg({"combos": []}) is None


def _write(folder: Path, tag: str, sidecar: dict, text: str = "# report\n") -> Path:
    report = folder / f"Game_{tag}_Full_Analysis.md"
    report.write_text(text, encoding="utf-8")
    payload = {**sidecar, "report_sha256": hashlib.sha256(text.encode()).hexdigest()}
    Path(str(report) + ".market_legs.json").write_text(json.dumps(payload), encoding="utf-8")
    return report


def test_reports_are_built_from_bound_sidecars(tmp_path) -> None:
    folder = tmp_path / "2026-11-05 NBA Analysis"
    folder.mkdir()
    _write(folder, "ORL_ATL", SIDECAR)
    _write(folder, "BOS_NYK", {"combos": [], "selection_diagnostics": {"no_bet_reason": "no_b2_combo"}})
    result = subprocess.run([sys.executable, str(SCRIPT), "--dir", str(folder)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    everything = (folder / "NBA_All_SGM_Report.txt").read_text(encoding="utf-8")
    banker = (folder / "NBA_Banker_Report.txt").read_text(encoding="utf-8")
    assert "組合賠率 @2.84" in everything and "NO BET — no_b2_combo" in everything
    assert "已報價 SGM 組合數: 1" in everything
    assert "Paolo Banchero (ORL) REB 8+ @1.52 (EV +49.0%)" in banker


def test_a_report_edited_after_its_sidecar_blocks_the_summary(tmp_path) -> None:
    folder = tmp_path / "2026-11-05 NBA Analysis"
    folder.mkdir()
    report = _write(folder, "ORL_ATL", SIDECAR)
    report.write_text("# edited\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--dir", str(folder)], capture_output=True, text=True)
    assert result.returncode == 1
    assert not (folder / "NBA_All_SGM_Report.txt").exists()
