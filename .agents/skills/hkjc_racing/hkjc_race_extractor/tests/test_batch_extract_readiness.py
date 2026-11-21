from __future__ import annotations

import importlib.util
import json
import re
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


# ── 舊賽績檔對得上 fresh 排位表就當齊（Kelvin 2026-11-22）─────────────────

def _racecard(runners):
    head = "#### 第一部分：賽事資料 (Race Info)\n日期: 2026-11-22\n\n#### 第二部分：馬匹資料 (Horse Info)\n"
    return head + "\n".join(
        f"馬號: {n}\n馬名: {name}\n英文馬名: X\n負磅: {wt}\n騎師: {jk}\n檔位: {dr}\n練馬師: T\n"
        for n, name, dr, jk, wt in runners
    )


def _formguide(runners, date="22/11/2026"):
    head = (f"#### 賽事概覽 (Race Overview)\n- 賽事日期 / 場次 / 跑道及場地狀況: {date} / 第5場 / 沙田\n\n"
            "#### 全場馬匹分析 (Full Field Analysis)\n")
    return head + "\n".join(
        f"馬號: {n}\n馬名: {name}\n檔位: {dr}\n騎師: {jk}\n負磅: {wt}\n排位體重: 1200\n\n往績紀錄:\n"
        f"  [1] 12/07/2026 | 沙田 1200 好\n      檔位: 9 | 騎師: 別人 | 負磅: 120 | 名次: 2 / 14\n"
        for n, name, dr, jk, wt in runners
    )


RUNNERS = [(1, "跨境寶馬", "3", "艾兆禮", "135"), (2, "偵探傳奇", "7", "潘頓", "133")]


def _pair(tmp_path, rc_runners, fg_runners, **fg_kw):
    rc = tmp_path / "11-22 Race 5 排位表.md"
    fg = tmp_path / "11-22 Race 5 賽績.md"
    rc.write_text(_racecard(rc_runners), encoding="utf-8")
    fg.write_text(_formguide(fg_runners, **fg_kw), encoding="utf-8")
    return str(rc), str(fg)


def test_kept_formguide_matching_racecard_counts(tmp_path: Path) -> None:
    ok, why = batch._kept_formguide_matches_racecard(*_pair(tmp_path, RUNNERS, RUNNERS), "2026/11/22")
    assert ok, why


@pytest.mark.parametrize(
    "fg_runners, fragment",
    [
        ([RUNNERS[0]], "馬號唔同"),                                    # 少咗一匹
        ([RUNNERS[0], (2, "偵探傳奇", "7", "布文", "133")], "騎師"),     # 換騎
        ([RUNNERS[0], (2, "偵探傳奇", "7", "潘頓", "130")], "負磅"),     # 改磅
        ([RUNNERS[0], (2, "偵探傳奇", "8", "潘頓", "133")], "檔位"),     # 檔位
    ],
)
def test_kept_formguide_that_disagrees_with_racecard_does_not_count(tmp_path, fg_runners, fragment) -> None:
    ok, why = batch._kept_formguide_matches_racecard(*_pair(tmp_path, RUNNERS, fg_runners), "2026/11/22")
    assert not ok and fragment in why


def test_kept_formguide_from_another_meeting_does_not_count(tmp_path: Path) -> None:
    ok, why = batch._kept_formguide_matches_racecard(
        *_pair(tmp_path, RUNNERS, RUNNERS, date="19/11/2026"), "2026/11/22")
    assert not ok and "賽事日期" in why


def test_past_run_jockey_lines_are_not_read_as_todays_jockey(tmp_path: Path) -> None:
    # 往績行有 `騎師: 別人`，但嗰行以空格開頭兼喺 `|` 入面，唔可以當今仗騎師。
    blocks = batch._runner_blocks(_formguide(RUNNERS))
    assert blocks[2]["騎師"] == "潘頓"


def _run_main(tmp_path, monkeypatch, result):
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--base_url",
        "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/11/22&Racecourse=ST&RaceNo=1",
        "--races", "5", "--output_dir", str(tmp_path), "--max_workers", "1",
    ])
    with (
        mock.patch.object(batch, "extract_starter_pdf", return_value=(True, "", "fresh")),
        mock.patch.object(batch, "extract_trackwork_meeting",
                          return_value={"ok": False, "races": {5: {"json_ok": False, "md_ok": False}}, "error": ""}),
        mock.patch.object(batch, "extract_single_race", return_value=result),
    ):
        batch.main()
    return json.loads((tmp_path / "Extraction_Readiness.json").read_text())


def test_main_ready_when_kept_formguide_matches(tmp_path: Path, monkeypatch) -> None:
    _pair(tmp_path, RUNNERS, RUNNERS)
    readiness = _run_main(tmp_path, monkeypatch, {
        "race": 5, "racecard_ok": True, "formguide_ok": False,
        "racecard_state": "fresh", "formguide_state": "kept",
        "errors": ["Formguide R5: no runner rows (source not published/ready)"]})
    assert readiness["status"] == "ready"
    assert readiness["formguides_ready"] == 0          # 今次刷新照實報失敗
    assert readiness["formguides_usable"] == 1
    assert readiness["formguides_kept_verified"] == [5]


def test_main_waits_when_kept_formguide_mismatches(tmp_path: Path, monkeypatch) -> None:
    _pair(tmp_path, RUNNERS, [RUNNERS[0], (2, "偵探傳奇", "7", "布文", "133")])
    with pytest.raises(SystemExit) as raised:
        _run_main(tmp_path, monkeypatch, {
            "race": 5, "racecard_ok": True, "formguide_ok": False,
            "racecard_state": "fresh", "formguide_state": "kept", "errors": []})
    assert raised.value.code == 75


def test_main_waits_when_racecard_not_fresh_even_if_formguide_kept(tmp_path: Path, monkeypatch) -> None:
    _pair(tmp_path, RUNNERS, RUNNERS)
    with pytest.raises(SystemExit) as raised:
        _run_main(tmp_path, monkeypatch, {
            "race": 5, "racecard_ok": False, "formguide_ok": False,
            "racecard_state": "kept", "formguide_state": "kept", "errors": []})
    assert raised.value.code == 75


def test_apprentice_claim_and_scratched_runner_do_not_break_the_match(tmp_path: Path) -> None:
    # 2026-11-22 真檔形狀：排位表「周俊樂 (-2)」vs 賽績「周俊樂」；排位表留住
    # 「(退出)」嗰匹而賽績檔已經冇咗佢。
    rc_runners = RUNNERS + [(3, "港邊小區 (退出)", "-", "-", "-")]
    rc, fg = _pair(tmp_path, rc_runners, RUNNERS)
    text = open(rc, encoding="utf-8").read().replace("騎師: 潘頓", "騎師: 潘頓 (-2)")
    open(rc, "w", encoding="utf-8").write(text)
    ok, why = batch._kept_formguide_matches_racecard(rc, fg, "2026/11/22")
    assert ok, why
    # 賽績檔寫扣咗減磅嘅實際負磅（133 − 2 = 131）都要對得上；扣錯數就唔得。
    for carried, expect in (("131", True), ("130", False)):
        fg_text = open(fg, encoding="utf-8").read()
        fg_text = re.sub(r"(馬號: 2\n(?:.*\n){3})負磅: \d+", rf"\g<1>負磅: {carried}", fg_text)
        open(fg, "w", encoding="utf-8").write(fg_text)
        assert batch._kept_formguide_matches_racecard(rc, fg, "2026/11/22")[0] is expect
