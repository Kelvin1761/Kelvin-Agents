from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
AU = SCRIPTS.parents[1]
sys.path.insert(0, str(AU))
import claw_sportsbet_form as form  # noqa: E402
import sb_people_stats as people  # noqa: E402


def block_bs4(monkeypatch):
    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "bs4":
            raise ModuleNotFoundError("fixture: No module named bs4", name="bs4")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)


@pytest.mark.parametrize("parser", [form.parse_overview, people.parse_person_tables])
def test_missing_parser_dependency_is_not_empty_source(monkeypatch, parser):
    block_bs4(monkeypatch)
    with pytest.raises(ModuleNotFoundError, match="bs4"):
        parser("<table></table>")


def test_people_refresh_reports_dependency_failure_and_preserves_cache(monkeypatch, tmp_path):
    path = tmp_path / "people.json"
    path.write_text('{"existing": {"name": "Keep"}}')
    before = path.read_bytes()
    html = tmp_path / "person.html"
    html.write_text("<table></table>")

    class Fetcher:
        def _cache_path(self, url):
            return html

        def get(self, url):
            return html.read_text()

    block_bs4(monkeypatch)
    with pytest.raises(ModuleNotFoundError, match="bs4"):
        people.refresh([("Jockey", "1", "Fixture Rider")], path=path,
                       fetcher=Fetcher(), ttl_days=0, cache_only=True, verbose=False)
    assert path.read_bytes() == before
    assert not people.snapshot_path(path).exists()


def test_empty_html_remains_empty_when_parser_dependency_exists():
    assert form.parse_overview("<html></html>") == {}
    assert people.parse_person_tables("<html></html>") == {}


def dump_fixture(monkeypatch, tmp_path, missing=None):
    spec = importlib.util.spec_from_file_location("audit_dump_dependency_test", SCRIPTS / "au_dump_engine_leaves.py")
    dump = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dump)
    meeting = tmp_path / "2026-08-05 Fixture Race 1"
    meeting.mkdir()
    horses = {str(i): {"horse_name": f"Fixture {i}"} for i in range(1, 5)}
    (meeting / "Race_1_Logic.json").write_text(json.dumps({
        "race_analysis": {"race_number": 1}, "horses": horses,
    }))
    rows = [{"horse_slug": f"Fixture {i}", "pos": i} for i in range(1, 5)]
    archive = ModuleType("au_archive_calibrator")
    archive.ARCHIVE_ROOT = tmp_path
    archive.HISTORICAL_RESULTS_CSV = tmp_path / "never-read.csv"
    archive.choose_track_rows = lambda rows, track: rows
    archive.detect_meeting_date = lambda folder: "2026-08-05"
    archive.detect_meeting_track = lambda folder, sample: "Fixture"
    archive.get_true_horse_name = lambda horse: horse["horse_name"]
    archive.load_historical_results = lambda path: {("2026-08-05", 1): rows}
    archive.normalize_horse_name = lambda name: name.lower()
    archive.parse_int = lambda value, default=0: int(value) if value else default
    auto = ModuleType("au_auto_orchestrator")
    auto._build_field_summary = lambda horses: {"count": len(horses)}
    core = ModuleType("au_racing_engine.engine_core")

    class Engine:
        def __init__(self, *args, **kwargs):
            pass

        def analyze_horse(self):
            return {"feature_scores": {"fixture": 60.0}, "ability_score": 60.0}

    core.RacingEngine = Engine
    core.backfill_prize_column = lambda *args: 0
    for name in ("backfill_pf_metrics", "refresh_pf_own_l600", "refresh_form_quality"):
        if name != missing:
            setattr(core, name, lambda *args: 0)
    scoring = ModuleType("au_racing_engine.scoring")
    scoring.FEATURE_KEYS = ("fixture",)
    for name, module in ((archive.__name__, archive), (auto.__name__, auto),
                         (core.__name__, core), (scoring.__name__, scoring)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(dump, "_corpus_meeting_dirs", lambda root: [meeting])
    dest = tmp_path / "dump.json"
    monkeypatch.setattr(sys, "argv", ["au_dump_engine_leaves.py", "--out", str(dest)])
    return dump, dest


@pytest.mark.parametrize("missing", ["backfill_pf_metrics", "refresh_pf_own_l600", "refresh_form_quality"])
def test_dump_missing_serving_enrichment_fails_before_output(monkeypatch, tmp_path, missing):
    dump, dest = dump_fixture(monkeypatch, tmp_path, missing)
    with pytest.raises(ImportError, match=missing):
        dump.main()
    assert not dest.exists()


def test_dump_available_dependencies_preserves_four_runner_output(monkeypatch, tmp_path):
    dump, dest = dump_fixture(monkeypatch, tmp_path)
    dump.main()
    races = json.loads(dest.read_text())["races"]
    assert len(races) == 1
    assert races[0]["field"] == 4
    assert [row["name"] for row in races[0]["rows"]] == [f"Fixture {i}" for i in range(1, 5)]
    assert [row["features"] for row in races[0]["rows"]] == [{"fixture": 60.0}] * 4
    assert [row["ability"] for row in races[0]["rows"]] == [60.0] * 4
