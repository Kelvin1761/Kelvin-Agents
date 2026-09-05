"""出賽名單掃描：偵測退出／換馬，但**唔准**將抓取失敗當成名單變動。

點解要有：`run_prerace` 排喺 21:30 / 23:30 / 00:30 / 08:00 / 11:00（悉尼），
香港頭場約 15:00 悉尼 —— 開賽前 4 個鐘之後成個賽日冇覆蓋，而香港退出馬
好多喺賽日早上先公布。

最關鍵嗰組測試係「失敗唔可以扮變動」。一個 timeout、一個半截頁、一個
exit≠0，如果被讀成「啲馬唔見咗」，就會喺賽日觸發一次冇必要嘅全場重跑
（7 分鐘）同一個假通知。2026-09-05 個 starter PDF 故障就係同一個形狀：
自己嘅 bug 被當成來源問題報咗出去。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_lineup.py"
_SPEC = importlib.util.spec_from_file_location("scan_lineup_test", SCRIPT)
scan = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(scan)


def _card(pairs):
    out = []
    for num, name in pairs:
        out.append(f"馬號: {num}\n馬名: {name}\n英文馬名: X\n負磅: 126\n檔位: {num}\n")
    return "\n".join(out)


def _logic(tmp_path, race, pairs):
    path = tmp_path / f"Race_{race}_Logic.json"
    path.write_text(json.dumps(
        {"horses": {str(n): {"horse_name": h} for n, h in pairs}}, ensure_ascii=False),
        encoding="utf-8")
    return path


FIELD = [(1, "嘉應高昇"), (2, "合夥奔馳"), (3, "錶之星河")]


# ───────────────────────── 解析 ─────────────────────────

def test_parse_lineup_reads_number_and_name():
    assert scan.parse_lineup(_card(FIELD)) == {1: "嘉應高昇", 2: "合夥奔馳", 3: "錶之星河"}


def test_a_page_with_a_number_but_no_name_is_incomplete():
    """半截頁唔可以扮成「有隻馬唔見咗」。"""
    broken = _card(FIELD) + "\n馬號: 4\n"
    lineup = scan.parse_lineup(broken)
    assert 4 not in lineup
    assert scan.lineup_looks_complete(broken, lineup) is False


def test_a_complete_page_passes_the_completeness_check():
    md = _card(FIELD)
    assert scan.lineup_looks_complete(md, scan.parse_lineup(md)) is True


# ───────────────────────── diff ─────────────────────────

def test_no_change_is_reported_as_no_change():
    d = scan.diff_lineup(dict(FIELD), dict(FIELD))
    assert d["changed"] is False


def test_a_scratching_is_detected():
    current = {1: "嘉應高昇", 2: "合夥奔馳"}
    d = scan.diff_lineup(current, dict(FIELD))
    assert d["changed"] is True
    assert d["scratched"] == [{"no": 3, "horse": "錶之星河"}]


def test_a_substitution_is_detected_even_though_the_count_is_the_same():
    """換馬：馬號一樣、馬名唔同。只比對號碼係捉唔到嘅。"""
    current = dict(FIELD) | {3: "另一隻馬"}
    d = scan.diff_lineup(current, dict(FIELD))
    assert d["changed"] is True
    assert d["replaced"] == [{"no": 3, "was": "錶之星河", "now": "另一隻馬"}]
    assert d["scratched"] == [] and d["added"] == []


def test_an_added_runner_is_detected():
    current = dict(FIELD) | {4: "新馬"}
    d = scan.diff_lineup(current, dict(FIELD))
    assert d["added"] == [{"no": 4, "horse": "新馬"}]


# ─────────────── 失敗唔可以扮變動（呢組先係重點）───────────────

def test_a_fetch_timeout_is_an_error_not_a_change(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    with mock.patch.object(scan.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired("x", 60)):
        out = scan.scan_race("http://x", logic)
    assert out["changed"] is False, "timeout 唔可以觸發重跑"
    assert "TimeoutExpired" in out["error"]


def test_a_nonzero_exit_is_an_error_not_a_change(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    done = subprocess.CompletedProcess(["x"], 1, stdout="", stderr="boom")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://x", logic)
    assert out["changed"] is False
    assert "exit=1" in out["error"]


def test_an_empty_page_is_an_error_not_a_full_field_scratching(tmp_path):
    """呢個就係最危險嗰個：空白頁 = 全部馬退出 = 一次假重跑 + 假通知。"""
    logic = _logic(tmp_path, 1, FIELD)
    done = subprocess.CompletedProcess(["x"], 0, stdout="", stderr="")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://x", logic)
    assert out["changed"] is False
    assert out["scratched"] == []
    assert "唔完整" in out["error"]


def test_a_truncated_page_is_an_error_not_a_partial_scratching(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    truncated = _card(FIELD[:2]) + "\n馬號: 3\n"      # 第三隻只得號碼
    done = subprocess.CompletedProcess(["x"], 0, stdout=truncated, stderr="")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://x", logic)
    assert out["changed"] is False
    assert "唔完整" in out["error"]


def test_a_missing_logic_is_an_error_not_a_change(tmp_path):
    out = scan.scan_race("http://x", tmp_path / "Race_9_Logic.json")
    assert out["changed"] is False
    assert "未分析過" in out["error"]


def test_a_real_change_still_gets_through(tmp_path):
    """守到咁多防線之後，真變動仍然要偵測到 —— 唔可以矯枉過正。"""
    logic = _logic(tmp_path, 1, FIELD)
    done = subprocess.CompletedProcess(["x"], 0, stdout=_card(FIELD[:2]), stderr="")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://x", logic)
    assert out["changed"] is True
    assert out["scratched"] == [{"no": 3, "horse": "錶之星河"}]


# ───────────────────────── 摘要 ─────────────────────────

def test_describe_names_every_kind_of_change():
    text = scan.describe({
        3: {"scratched": [{"no": 3, "horse": "錶之星河"}], "added": [], "replaced": []},
        7: {"scratched": [], "added": [],
            "replaced": [{"no": 2, "was": "舊馬", "now": "新馬"}]},
    })
    assert "R3：退出 3 錶之星河" in text
    assert "R7：換馬 2 舊馬→新馬" in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
