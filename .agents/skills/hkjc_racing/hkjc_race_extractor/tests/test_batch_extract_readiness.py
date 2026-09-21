from __future__ import annotations

import importlib.util
import json
import subprocess
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

    ok, error, state = batch._keep_valid_candidate(
        str(path), "沒有賽績紀錄", "Formguide", 1, 0
    )

    assert ok is False
    assert "not published/ready" in error
    assert path.read_text(encoding="utf-8") == old
    # 保留咗有效檔 ≠ 冇數據。呢個分別要傳到警報，見
    # hkjc_daily_auto/tests/test_readiness_states.py。
    assert state == "kept"


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


class _Response:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_race_count_detection_retries_a_transient_timeout() -> None:
    html = '<a href="?RaceNo=1">1</a><a href="?RaceNo=9">9</a>'
    with (
        mock.patch.object(
            helpers.urllib.request,
            "urlopen",
            side_effect=[TimeoutError("slow"), _Response(html)],
        ) as urlopen,
        mock.patch.object(helpers.time, "sleep") as sleep,
    ):
        assert helpers.detect_total_races_from_url("https://example.test") == 9
    assert urlopen.call_count == 2
    sleep.assert_called_once()


def test_cached_official_race_count_is_used_for_the_same_meeting(tmp_path: Path) -> None:
    (tmp_path / "Extraction_Readiness.json").write_text(
        json.dumps({"meeting_date": "2026/09/23", "expected_races": 9}),
        encoding="utf-8",
    )
    url = "https://example.test?racedate=2026/09/23&Racecourse=HV&RaceNo=1"
    assert helpers.cached_expected_races(tmp_path, url) == 9


def test_cached_race_count_from_another_meeting_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "Extraction_Readiness.json").write_text(
        json.dumps({"meeting_date": "2026/09/16", "expected_races": 8}),
        encoding="utf-8",
    )
    url = "https://example.test?racedate=2026/09/23&Racecourse=HV&RaceNo=1"
    assert helpers.cached_expected_races(tmp_path, url) is None


def test_trigger_extractor_uses_cached_official_count_after_live_timeout(tmp_path: Path) -> None:
    (tmp_path / "Extraction_Readiness.json").write_text(
        json.dumps({"meeting_date": "2026/09/23", "expected_races": 9}),
        encoding="utf-8",
    )
    url = "https://example.test?racedate=2026/09/23&Racecourse=HV&RaceNo=1"
    with (
        mock.patch.object(helpers, "detect_total_races_from_url", return_value=None),
        mock.patch.object(helpers.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run,
    ):
        helpers.trigger_extractor(url, str(tmp_path))
    command = run.call_args.args[0]
    assert command[command.index("--races") + 1] == "1-9"


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
        # ⚠️ 個 mock 一定要跟足真 signature。2026-09-05 呢一行係 `(True, "")`
        # 兩個值，而 `extract_starter_pdf` 已經改成回三個 —— 呢個 mock 遮住咗
        # 真嘅 arity，所以成個 suite 綠燈，而生產環境 PDF 100% 失敗。
        # 真 caller 嘅測試喺 test_batch_extract_contracts.py。
        mock.patch.object(batch, "extract_starter_pdf", return_value=(True, "", "fresh")),
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
