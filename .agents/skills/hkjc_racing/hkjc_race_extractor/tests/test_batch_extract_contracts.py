"""每個 `_keep_valid_candidate` 嘅 caller 都要跟得住佢個 signature。

2026-09-05 嘅故障：`_keep_valid_candidate` 由回兩個值改成回三個值，但三個
call site 只改咗兩個。漏咗嗰個係 `extract_starter_pdf`，於是：

    ok, error = _keep_valid_candidate(...)   → ValueError

而個 `except Exception` 將呢個 **code bug** 當成 **來源失敗** 報出去。
因為 `starter_pdf_ready` 係發佈閘 `ready = pdf and 排位表 and 賽績` 嘅硬條件，
2026-09-06 沙田 22 次 run **0 次過閘**（PDF 佔 20 次），而抽取器本身
11.2 秒、exit 0、輸出 252 KB 完全正常。

點解走漏：舊測試只直接測 `_keep_valid_candidate`，而整批測試將
`extract_single_race` mock 咗 —— 冇一個測試 call 過 `extract_starter_pdf`。
下面補返呢個缺口，並加一個結構閘防止第四個 caller 再走漏。
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest import mock

import json

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "batch_extract.py"
_SPEC = importlib.util.spec_from_file_location("batch_extract_contracts", SCRIPT)
batch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(batch)

VALID_PDF = "=== HKJC 全日出賽馬匹資料 (20260906) ===\n" + ("馬匹資料 " * 40)


def _completed(stdout, returncode=0):
    return subprocess.CompletedProcess(args=["x"], returncode=returncode,
                                       stdout=stdout, stderr="")


# ─────────────────────────── 結構閘 ───────────────────────────

def test_every_keep_valid_candidate_caller_unpacks_three():
    """呢個先係真正防再犯嘅閘：漏改一個 caller 即刻紅。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if getattr(func, "id", None) != "_keep_valid_candidate":
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Tuple) or len(target.elts) != 3:
            bad.append(node.lineno)
    assert not bad, f"呢啲行冇解包三個值：{bad}"


def test_there_are_still_three_callers():
    """如果加咗第四個 caller，上面個閘要照睇到 —— 呢個係提醒改測試。"""
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count("_keep_valid_candidate(") == 4  # 1 個定義 + 3 個 caller


# ─────────────────────── extract_starter_pdf ───────────────────────

def test_starter_pdf_success_returns_three_values(tmp_path):
    with mock.patch.object(batch.subprocess, "run", return_value=_completed(VALID_PDF)):
        ok, error, state = batch.extract_starter_pdf("20260906", str(tmp_path), "09-06")
    assert ok is True
    assert error == ""
    assert state == "fresh"
    assert (tmp_path / "09-06 全日出賽馬匹資料 (PDF).md").exists()


def test_starter_pdf_timeout_keeps_the_valid_file_on_disk(tmp_path):
    """抽取器 timeout ≠ 冇數據。碟上有效嘅 PDF 要報 `kept`。"""
    path = tmp_path / "09-06 全日出賽馬匹資料 (PDF).md"
    path.write_text(VALID_PDF, encoding="utf-8")
    with mock.patch.object(batch.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired("x", 90)):
        ok, error, state = batch.extract_starter_pdf("20260906", str(tmp_path), "09-06")
    assert ok is False           # 閘冇放寬：只有 fresh 先算過
    assert state == "kept"       # 但警報要講得出「其實有檔」
    assert "TimeoutExpired" in error
    assert path.read_text(encoding="utf-8") == VALID_PDF


def test_starter_pdf_timeout_with_nothing_on_disk_is_missing(tmp_path):
    with mock.patch.object(batch.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired("x", 90)):
        ok, _error, state = batch.extract_starter_pdf("20260906", str(tmp_path), "09-06")
    assert ok is False
    assert state == "missing"


def test_a_bug_in_our_own_code_is_not_swallowed_as_a_source_failure(tmp_path):
    """呢個就係 2026-09-05 嗰個故障嘅形狀。

    一個 `TypeError`（我哋自己嘅 bug）唔可以再變成 `(False, "...")` 靜靜報
    「HKJC 未 ready」—— 佢要炸出嚟，等人一眼睇到係 code 壞咗。
    """
    with mock.patch.object(batch.subprocess, "run", side_effect=TypeError("boom")):
        with pytest.raises(TypeError):
            batch.extract_starter_pdf("20260906", str(tmp_path), "09-06")


# ────────────────────── extract_trackwork_meeting ──────────────────────

def _write_trackwork(tmp_path, races):
    for r in races:
        (tmp_path / f"2026-09-06 Race {r} 晨操.json").write_text("x" * 500, encoding="utf-8")
        (tmp_path / f"2026-09-06 Race {r} 晨操.md").write_text("y" * 200, encoding="utf-8")


def test_trackwork_timeout_still_counts_the_files_already_written(tmp_path):
    """`extract_trackwork.py` 逐場寫檔，所以 timeout 殺咗佢之後，
    已經寫好嗰批仍然完整 —— 個檢查唔可以連帶被跳過。"""
    _write_trackwork(tmp_path, range(1, 11))
    with mock.patch.object(batch.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired("x", 300)):
        out = batch.extract_trackwork_meeting("http://x", list(range(1, 11)),
                                              str(tmp_path), "09-06")
    assert out["ok"] is True
    assert sum(1 for v in out["races"].values() if v["json_ok"] and v["md_ok"]) == 10
    assert "TimeoutExpired" in out["error"]


def test_trackwork_timeout_with_no_files_reports_zero(tmp_path):
    with mock.patch.object(batch.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired("x", 300)):
        out = batch.extract_trackwork_meeting("http://x", [1, 2], str(tmp_path), "09-06")
    assert out["ok"] is False
    assert sum(1 for v in out["races"].values() if v["json_ok"] and v["md_ok"]) == 0


def test_trackwork_partial_write_is_counted_partially(tmp_path):
    _write_trackwork(tmp_path, [1, 2, 3])
    with mock.patch.object(batch.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired("x", 300)):
        out = batch.extract_trackwork_meeting("http://x", list(range(1, 11)),
                                              str(tmp_path), "09-06")
    assert sum(1 for v in out["races"].values() if v["json_ok"] and v["md_ok"]) == 3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))


# ───────────────────── 發佈閘：starter PDF 係軟閘 ─────────────────────
#
# 2026-11-03 起 starter PDF 唔再入 `ready`。佢喺評分入面嘅唯一用途係自購馬海外
# 往績，而 `inject_hkjc_fact_anchors` 喺 PDF 冇海外節時會逐匹改用 fsc 來港前賽績。
# 以前 PDF 一斷就卡死成個場次（2026-09-06 沙田 22 次 run 有 20 次卡喺 PDF）。
# 排位表同賽績照樣要 fresh —— 佢哋決定名單，鬆咗退出馬就會返晒嚟。

def _gate_source():
    return SCRIPT.read_text(encoding="utf-8")


def test_ready_no_longer_depends_on_the_pdf():
    src = _gate_source()
    ready = src[src.index("    ready = total_rc"):].splitlines()[0]
    assert ready.strip() == "ready = total_rc == len(races) and total_fg == len(races)"
    assert "pdf_gate =" not in src


def test_racecards_and_formguides_still_require_fresh():
    """`total_rc` / `total_fg` 數嘅係 `*_ok`（今次刷新成功），唔係 `*_valid`。"""
    src = _gate_source()
    assert "total_rc = sum(1 for r in all_results if r['racecard_ok'])" in src
    assert "total_fg = sum(1 for r in all_results if r['formguide_ok'])" in src


def test_an_unknown_gate_mode_falls_back_to_strict():
    """打錯字唔可以靜靜變成另一個模式 —— 一定要 fail closed 兼記低 strict。"""
    src = _gate_source()
    idx = src.index("gate_mode = os.environ.get")
    block = src[idx:src.index("    ready = total_rc")]
    assert 'gate_mode not in ("strict", "field_change")' in block
    assert "當 strict 處理" in block


def test_the_default_is_strict():
    assert 'os.environ.get("WC_HKJC_GATE", "strict")' in _gate_source()


def test_the_gate_mode_and_pdf_soft_fail_are_recorded_in_the_manifest():
    """事後要查得返「呢次係用邊個閘過嘅」同「PDF 有冇出事」。"""
    src = _gate_source()
    assert '"gate_mode": gate_mode,' in src
    assert '"starter_pdf_gate": "soft",' in src
    assert '"starter_pdf_soft_fail": starter_pdf_soft_fail,' in src


def _run_main(tmp_path, monkeypatch, pdf_result, formguide_ok=True):
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--base_url",
        "https://racing.hkjc.com/zh-hk/local/information/racecard"
        "?racedate=2026/11/04&Racecourse=HV&RaceNo=1",
        "--races", "1", "--output_dir", str(tmp_path), "--max_workers", "1",
    ])
    race = {"race": 1, "racecard_ok": True, "formguide_ok": formguide_ok,
            "racecard_state": "fresh",
            "formguide_state": "fresh" if formguide_ok else "missing", "errors": []}
    with (
        mock.patch.object(batch, "extract_starter_pdf", return_value=pdf_result),
        mock.patch.object(batch, "extract_trackwork_meeting",
                          return_value={"ok": True, "races": {1: {"json_ok": True, "md_ok": True}},
                                        "error": ""}),
        mock.patch.object(batch, "extract_single_race", return_value=race),
    ):
        try:
            batch.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, json.loads((tmp_path / "Extraction_Readiness.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("gate", ["strict", "field_change"])
def test_missing_pdf_alone_does_not_block_the_meeting(tmp_path, monkeypatch, gate):
    monkeypatch.setenv("WC_HKJC_GATE", gate)
    code, readiness = _run_main(tmp_path, monkeypatch, (False, "HTTP 404", "missing"))
    assert code == 0
    assert readiness["status"] == "ready"
    assert readiness["starter_pdf_ready"] is False
    assert readiness["starter_pdf_soft_fail"] is True
    assert readiness["starter_pdf_error"] == "HTTP 404"


def test_missing_formguide_still_blocks_even_with_a_good_pdf(tmp_path, monkeypatch):
    code, readiness = _run_main(tmp_path, monkeypatch, (True, "", "fresh"), formguide_ok=False)
    assert code == 75
    assert readiness["status"] == "waiting_source"
    assert readiness["starter_pdf_soft_fail"] is False


@pytest.mark.parametrize("race_count, expected_timeout", [(2, 300), (11, 660)])
def test_trackwork_budget_scales_with_meeting_size(tmp_path, race_count, expected_timeout):
    with mock.patch.object(batch.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
        batch.extract_trackwork_meeting("http://x", list(range(1, race_count + 1)),
                                       str(tmp_path), "10-19")
    assert run.call_args.kwargs["timeout"] == expected_timeout
