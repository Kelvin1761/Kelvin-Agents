"""出賽名單掃描：偵測退出／換馬，但**唔准**將抓取失敗當成名單變動。

點解要有：`run_prerace` 排喺 21:30 / 23:30 / 00:30 / 08:00 / 11:00（悉尼），
香港頭場約 15:00 悉尼 —— 開賽前 4 個鐘之後成個賽日冇覆蓋，而香港退出馬
好多喺賽日早上先公布。

**權威來源係賽績，唔係排位表** —— `inject_hkjc_fact_anchors.parse_hkjc_formguide()`
個馬匹迴圈食嘅就係佢，成條鏈係 賽績 → Facts → Logic → 板面。呢個 module
最初比對排位表，後果係：排位表出咗退出馬 → 偵測到 → 重跑 → 重跑由賽績砌名單
→ 隻馬仲喺度 → 永遠唔收斂，而板上一直掛住隻已退出嘅馬。

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
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["changed"] is False, "timeout 唔可以觸發重跑"
    assert "TimeoutExpired" in out["error"]


def test_a_nonzero_exit_is_an_error_not_a_change(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    done = subprocess.CompletedProcess(["x"], 1, stdout="", stderr="boom")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["changed"] is False
    assert "exit=1" in out["error"]


def test_an_empty_page_is_an_error_not_a_full_field_scratching(tmp_path):
    """呢個就係最危險嗰個：空白頁 = 全部馬退出 = 一次假重跑 + 假通知。"""
    logic = _logic(tmp_path, 1, FIELD)
    done = subprocess.CompletedProcess(["x"], 0, stdout="", stderr="")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["changed"] is False
    assert out["scratched"] == []
    assert "唔完整" in out["error"]


def test_a_truncated_page_is_an_error_not_a_partial_scratching(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    truncated = _card(FIELD[:2]) + "\n馬號: 3\n"      # 第三隻只得號碼
    done = subprocess.CompletedProcess(["x"], 0, stdout=truncated, stderr="")
    with mock.patch.object(scan.subprocess, "run", return_value=done):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
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
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
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


# ────────────── 權威來源：賽績，唔係排位表 ──────────────

def _two_sources(form_md, card_md, form_rc=0, card_rc=0):
    """`_lineup_from` 用 script 路徑分辨邊個來源，所以 side_effect 按 argv 派。"""
    def run(cmd, **_kw):
        script = str(cmd[1])
        if "formguide" in script:
            return subprocess.CompletedProcess(cmd, form_rc, stdout=form_md, stderr="")
        return subprocess.CompletedProcess(cmd, card_rc, stdout=card_md, stderr="")
    return run


def test_the_formguide_decides_not_the_racecard(tmp_path):
    """排位表話退出咗，賽績仲有 —— 重建鏈食賽績，所以唔准報變動。

    報咗就會觸發一個永遠唔收斂嘅重跑：重跑由賽績砌名單，隻馬照樣返嚟。
    """
    logic = _logic(tmp_path, 1, FIELD)
    with mock.patch.object(scan.subprocess, "run",
                           side_effect=_two_sources(_card(FIELD), _card(FIELD[:2]))):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["changed"] is False
    assert out["scratched"] == []
    assert "排位表已經冇：3 錶之星河" in out["source_disagreement"]


def test_a_change_in_the_formguide_is_reported(tmp_path):
    """反過嚟：賽績先行，就係真變動 —— 即使排位表未跟上。"""
    logic = _logic(tmp_path, 1, FIELD)
    with mock.patch.object(scan.subprocess, "run",
                           side_effect=_two_sources(_card(FIELD[:2]), _card(FIELD))):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["changed"] is True
    assert out["scratched"] == [{"no": 3, "horse": "錶之星河"}]
    assert out["source_disagreement"]


def test_agreeing_sources_report_no_disagreement(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    with mock.patch.object(scan.subprocess, "run",
                           side_effect=_two_sources(_card(FIELD), _card(FIELD))):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["source_disagreement"] == ""


def test_a_failed_racecard_does_not_block_the_formguide_verdict(tmp_path):
    """第二意見抓唔到就算數，唔可以拖累權威來源。"""
    logic = _logic(tmp_path, 1, FIELD)
    with mock.patch.object(scan.subprocess, "run",
                           side_effect=_two_sources(_card(FIELD[:2]), "", card_rc=1)):
        out = scan.scan_race("http://card", logic, formguide_url="http://form")
    assert out["changed"] is True
    assert out["error"] == ""


def test_no_formguide_url_refuses_to_guess(tmp_path):
    """冇賽績就唔可以退而求其次用排位表。"""
    logic = _logic(tmp_path, 1, FIELD)
    out = scan.scan_race("http://card", logic)
    assert out["changed"] is False
    assert "冇賽績 URL" in out["error"]


# ────────────── verify_applied：驗結果唔好信機制 ──────────────

def test_verify_applied_passes_when_the_horse_is_gone(tmp_path):
    logic = _logic(tmp_path, 1, FIELD[:2])
    assert scan.verify_applied(logic, {"scratched": [{"no": 3, "horse": "錶之星河"}]}) == ""


def test_verify_applied_catches_a_rerun_that_changed_nothing(tmp_path):
    """`run_prerace` 回 0 唔代表改動入咗 —— 呢個係唯一擋得住嗰種形狀嘅嘢。"""
    logic = _logic(tmp_path, 1, FIELD)          # 隻馬仲喺度
    reason = scan.verify_applied(logic, {"scratched": [{"no": 3, "horse": "錶之星河"}]})
    assert "仍然喺 Logic 入面" in reason
    assert "3 錶之星河" in reason


def test_verify_applied_catches_an_unswapped_substitution(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    reason = scan.verify_applied(
        logic, {"replaced": [{"no": 3, "was": "錶之星河", "now": "新馬"}]})
    assert "仍然係舊馬" in reason


def test_verify_applied_catches_a_missing_addition(tmp_path):
    logic = _logic(tmp_path, 1, FIELD)
    reason = scan.verify_applied(logic, {"added": [{"no": 9, "horse": "新馬"}]})
    assert "新馬仲未入到" in reason


def test_verify_applied_treats_an_unreadable_logic_as_unapplied(tmp_path):
    reason = scan.verify_applied(tmp_path / "nope.json",
                                 {"scratched": [{"no": 3, "horse": "X"}]})
    assert reason
