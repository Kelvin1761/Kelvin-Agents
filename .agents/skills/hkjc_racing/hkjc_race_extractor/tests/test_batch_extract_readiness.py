from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "batch_extract.py"
SPEC = importlib.util.spec_from_file_location("hkjc_batch_extract", SCRIPT)
assert SPEC and SPEC.loader
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)

HELPERS_SCRIPT = (
    SCRIPT.parents[2] / "hkjc_wong_choi" / "scripts" / "hkjc_orchestrator_helpers.py"
)
HELPERS_SPEC = importlib.util.spec_from_file_location("hkjc_orchestrator_helpers_test", HELPERS_SCRIPT)
assert HELPERS_SPEC and HELPERS_SPEC.loader
helpers = importlib.util.module_from_spec(HELPERS_SPEC)
HELPERS_SPEC.loader.exec_module(helpers)


def test_failed_refresh_preserves_last_valid_artifact(tmp_path: Path) -> None:
    path = tmp_path / "09-06 Race 1 賽績.md"
    old = "馬號: 1\n馬名: 測試馬\n" + ("valid formguide " * 20)
    path.write_text(old, encoding="utf-8")

    ok, error = batch._keep_valid_candidate(
        str(path), "沒有賽績紀錄", "Formguide", 1, 0
    )

    assert ok is False
    assert "not published/ready" in error
    assert path.read_text(encoding="utf-8") == old


def test_formguide_headers_without_runner_rows_are_not_ready() -> None:
    content = (
        "#### 賽事概覽 (Race Overview)\n"
        "- 賽事日期 / 場次 / 跑道及場地狀況: / 第1場 /\n"
        "#### 全場馬匹分析 (Full Field Analysis)\n"
    )
    assert "no runner rows" in batch._content_error(content, "Formguide", 1)


def test_unknown_race_count_never_falls_back_to_a_guessed_total() -> None:
    with mock.patch.object(helpers.urllib.request, "urlopen", side_effect=TimeoutError):
        assert helpers.detect_total_races_from_url("https://example.test?Racecourse=ST") is None


def test_partial_batch_writes_manifest_and_exits_temporary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--base_url",
            "https://racing.hkjc.com/zh-hk/local/information/racecard"
            "?racedate=2026/09/06&Racecourse=ST&RaceNo=1",
            "--races",
            "1",
            "--output_dir",
            str(tmp_path),
            "--max_workers",
            "1",
        ],
    )
    partial = {
        "race": 1,
        "racecard_ok": True,
        "formguide_ok": False,
        "errors": ["Formguide R1: source not published/ready"],
    }
    with (
        mock.patch.object(batch, "extract_starter_pdf", return_value=(True, "")),
        mock.patch.object(
            batch,
            "extract_trackwork_meeting",
            return_value={"ok": False, "races": {1: {"json_ok": False, "md_ok": False}}, "error": ""},
        ),
        mock.patch.object(batch, "extract_single_race", return_value=partial),
        pytest.raises(SystemExit) as raised,
    ):
        batch.main()

    assert raised.value.code == 75
    readiness = json.loads((tmp_path / "Extraction_Readiness.json").read_text())
    assert readiness["status"] == "waiting_source"
    assert readiness["formguides_ready"] == 0
    assert readiness["self_recovery"] == "automatic_retry"
