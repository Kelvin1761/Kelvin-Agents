from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine import au_draw_bias_calculator as draw  # noqa: E402


def inputs(monkeypatch, tmp_path, distances=1, runners=4):
    path = tmp_path / "input.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Date", "Track", "Race", "Distance", "Barrier", "Pos"])
        writer.writeheader()
        for race in range(1, distances + 1):
            for number in range(1, runners + 1):
                writer.writerow({"Date": "2026-08-05", "Track": "Fixture", "Race": str(race),
                                 "Distance": str(1000 + race * 100), "Barrier": str(number), "Pos": str(number)})
    out = tmp_path / "matrix.json"
    monkeypatch.setattr(draw, "CSV_PATH", str(path))
    monkeypatch.setattr(draw, "BACKFILL_CSV_PATH", str(tmp_path / "absent-backfill.csv"))
    monkeypatch.setattr(draw, "OUTPUT_JSON", str(out))
    monkeypatch.setattr(sys, "argv", ["au_draw_bias_calculator.py"])
    return path, out


def baseline(cells):
    return {"global_general": {}, "tracks": {"Fixture": {
        "track_general": {}, "distances": {str(1000 + i * 100): {} for i in range(1, cells + 1)},
    }}}


@pytest.mark.parametrize("old", ["broken-json", "[]", "{}",
                                  '{"tracks": []}', '{"tracks": {"Fixture": null}}',
                                  '{"tracks": {"Fixture": {"distances": []}}}'])
def test_unverifiable_existing_baseline_is_preserved(monkeypatch, tmp_path, old, capsys):
    _, out = inputs(monkeypatch, tmp_path)
    out.write_text(old)
    before = out.read_bytes()
    assert draw.main() == 1
    assert out.read_bytes() == before
    assert "Successfully generated" not in capsys.readouterr().out


def test_permission_error_reading_existing_baseline_refuses_write(monkeypatch, tmp_path, capsys):
    _, out = inputs(monkeypatch, tmp_path)
    out.write_text(json.dumps(baseline(1)))
    before = out.read_bytes()
    original = Path.read_text

    def reading(path, *args, **kwargs):
        if path == out:
            raise PermissionError("fixture baseline access denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reading)
    assert draw.main() == 1
    assert out.read_bytes() == before
    assert "Successfully generated" not in capsys.readouterr().out


def test_missing_csv_is_nonzero_and_preserves_existing_output(monkeypatch, tmp_path):
    path, out = inputs(monkeypatch, tmp_path)
    out.write_text(json.dumps(baseline(1)))
    before = out.read_bytes()
    path.unlink()
    assert draw.main() == 1
    assert out.read_bytes() == before


def test_actual_cli_missing_csv_is_nonzero(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    env = dict(os.environ, WONGCHOI_AU_DATA_ROOT=str(root), WONGCHOI_DATA_ROOT=str(tmp_path),
               PYTHONDONTWRITEBYTECODE="1", WC_DISABLE_POST_SUCCESS_DEPLOY="1")
    completed = subprocess.run([sys.executable, "-B", str(Path(draw.__file__))], env=env,
                               capture_output=True, text=True)
    assert completed.returncode == 1
    assert "not found" in completed.stdout
    assert "Successfully generated" not in completed.stdout


@pytest.mark.parametrize("cells,distances,accepted", [(10, 8, True), (10, 7, False), (1, 1, True)])
def test_existing_eighty_percent_guard_boundary(monkeypatch, tmp_path, cells, distances, accepted):
    _, out = inputs(monkeypatch, tmp_path, distances=distances)
    out.write_text(json.dumps(baseline(cells)))
    before = out.read_bytes()
    assert draw.main() == (0 if accepted else 1)
    if accepted:
        assert len(json.loads(out.read_text())["tracks"]["Fixture"]["distances"]) == distances
    else:
        assert out.read_bytes() == before


@pytest.mark.parametrize("old", [None, baseline(0)])
@pytest.mark.parametrize("runners,category", [(4, "field_1_8"), (10, "field_9_12"), (14, "field_13_plus")])
def test_first_build_and_valid_empty_baseline(monkeypatch, tmp_path, old, runners, category):
    _, out = inputs(monkeypatch, tmp_path, runners=runners)
    if old is not None:
        out.write_text(json.dumps(old))
    assert draw.main() == 0
    matrix = json.loads(out.read_text())
    assert sum(cell["sample_size"] for cell in matrix["global_general"][category].values()) == runners
    assert set(matrix["tracks"]["Fixture"]["distances"]) == {"1100"}


def test_explicit_force_keeps_existing_override_semantics(monkeypatch, tmp_path):
    _, out = inputs(monkeypatch, tmp_path)
    out.write_text("broken-json")
    monkeypatch.setattr(sys, "argv", ["au_draw_bias_calculator.py", "--force"])
    assert draw.main() == 0
    assert json.loads(out.read_text())["tracks"]["Fixture"]["distances"]
