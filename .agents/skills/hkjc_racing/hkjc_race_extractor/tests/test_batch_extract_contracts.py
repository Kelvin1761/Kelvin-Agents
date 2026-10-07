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


# ───────────────────── 發佈閘：field_change 模式 ─────────────────────
#
# `WC_HKJC_GATE=field_change` 只鬆 starter PDF 一格。排位表同賽績照樣要 fresh
# —— 佢哋決定名單（賽績尤其：`inject_hkjc_fact_anchors` 個馬匹迴圈食嘅就係
# 佢），鬆咗就會由舊檔重建，隻退出馬返晒嚟。
#
# 點解 PDF 鬆得：實測 2026-09-06 沙田嘅 `最終版本` 截止喺 09-05 上午 11:30
# —— 定義上早過賽事，冇可能載到賽日退出馬；而 `初版`→`最終版本` 2,347 行
# 只有 3 行抬頭唔同，2,344 行數據逐位元一樣。

def _gate_source():
    return SCRIPT.read_text(encoding="utf-8")


def test_field_change_relaxes_only_the_pdf():
    src = _gate_source()
    block = src[src.index("gate_mode = os.environ.get"):src.index("ready = pdf_gate")]
    assert 'pdf_state in ("fresh", "kept")' in block
    # 個 ready 條式只可以有 PDF 呢一格會隨模式變。
    ready = src[src.index("ready = pdf_gate"):].splitlines()[0]
    assert ready.strip() == "ready = pdf_gate and total_rc == len(races) and total_fg == len(races)"


def test_racecards_and_formguides_still_require_fresh():
    """`total_rc` / `total_fg` 數嘅係 `*_ok`（今次刷新成功），唔係 `*_valid`。"""
    src = _gate_source()
    assert "total_rc = sum(1 for r in all_results if r['racecard_ok'])" in src
    assert "total_fg = sum(1 for r in all_results if r['formguide_ok'])" in src


def test_an_unknown_gate_mode_falls_back_to_strict():
    """打錯字唔可以靜靜變成放寬 —— 一定要 fail closed。"""
    src = _gate_source()
    idx = src.index("gate_mode = os.environ.get")
    block = src[idx:src.index("ready = pdf_gate")]
    assert 'gate_mode != "strict"' in block
    assert "當 strict 處理" in block
    # else 分支用嘅係 pdf_ok（fresh only）
    assert "pdf_gate = pdf_ok" in block


def test_the_default_is_strict():
    assert 'os.environ.get("WC_HKJC_GATE", "strict")' in _gate_source()


def test_the_gate_mode_is_recorded_in_the_manifest():
    """事後要查得返「呢次係用邊個閘過嘅」。"""
    assert '"gate_mode": gate_mode,' in _gate_source()
