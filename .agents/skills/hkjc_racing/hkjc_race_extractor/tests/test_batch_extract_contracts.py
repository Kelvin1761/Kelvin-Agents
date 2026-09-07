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
import re
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


def test_the_gate_never_accepts_bare_valid():
    """個閘唔准鬆到 `*_valid`（碟上有檔就算）。

    `valid` = 「碟上有份格式正確嘅檔」—— 佢完全冇話你嗰份係唔係**當前**。
    2026-09-09 加入嘅 `verified` 係另一回事：碟上嗰份嘅名單同**今次真係刷新
    成功**嘅排位表逐個馬號馬名對得上，即係有獨立證據話佢反映當前名單。
    一隻只喺排位表退出嘅馬會令核實失敗，所以 `verified` 嚴過 `valid`。

    呢個測試釘住嘅係「`valid` 永遠唔可以入個閘」。
    """
    src = _gate_source()
    gate = src[src.index("gate_mode = os.environ.get"):]
    gate = gate[:gate.index("readiness = {")]
    counts = src[src.index("total_rc = sum("):src.index("print()", src.index("total_rc = sum("))]
    assert "racecards_valid" not in counts.replace("valid_rc", "")
    for token in ("valid_rc", "valid_fg"):
        assert token not in gate, f"{token} 唔准出現喺個閘度（佢只係「碟上有檔」）"
    assert "total_rc = sum(1 for r in all_results if r['racecard_ok'])" in src


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


def test_the_starter_pdf_timeout_has_headroom():
    """PDF 係發佈閘嘅硬條件，timeout 唔可以訂到貼身。

    實測正常耗時 11.2 秒。2026-09-06 賽日用 90 秒上限時，6 次 run 有 2 次
    （33%）TimeoutExpired，每次都卡住成個場次。放寬到 300 秒：成功嗰陣
    一樣快，慢嗰陣由「卡死」變成「過到」。
    """
    src = _gate_source()
    start = src.index("def extract_starter_pdf")
    end = src.index("\ndef ", start + 1)
    block = src[start:end]
    timeout = int(re.search(r"timeout=(\d+)", block).group(1))
    assert timeout >= 240, f"PDF timeout {timeout}s 太貼身（實測正常 11.2s，但會慢到爆 90s）"


# ══════════ 賽績核實：碟上嗰份同新鮮排位表對得上就當當前 ══════════
#
# 個閘本來問「今次刷新成功咗嗎」。HKJC 間歇回空頁（`no runner rows`），而
# `_keep_valid_candidate` 保留咗上次嘅好副本 —— 於是一份完全正確、幾個鐘前抽嘅
# 賽績會被當唔可用。2026-09-09 快活谷實測：同一場次 42 次 run 攞到 8/8、
# 26 次唔齊（62% 成功）。你收到嗰個警報係「賽績 1/8」，但碟上 8 份全部有效
# 而且逐個馬號馬名同新鮮排位表對得上。
#
# 正確嘅問題係「碟上嗰份係唔係最新」。用一個**今次真係刷新成功**嘅獨立來源
# （排位表）去答。以下守三條唔可以鬆嘅前提。

_CARD = "馬號: 1\n馬名: 甲\n負磅: 126\n\n馬號: 2\n馬名: 乙\n負磅: 120\n"


def _write_pair(tmp_path, race, card_text, form_text, prefix="09-09"):
    (tmp_path / f"{prefix} Race {race} 排位表.md").write_text(card_text, encoding="utf-8")
    (tmp_path / f"{prefix} Race {race} 賽績.md").write_text(form_text, encoding="utf-8")


def _result(race=1, *, racecard_state="fresh", formguide_state="kept"):
    return {"race": race, "racecard_ok": racecard_state == "fresh",
            "racecard_state": racecard_state, "formguide_ok": False,
            "formguide_state": formguide_state, "errors": []}


def test_a_kept_formguide_matching_a_fresh_racecard_is_verified(tmp_path):
    _write_pair(tmp_path, 1, _CARD, _CARD)
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "verified"
    assert any("名單一致" in e for e in results[0]["errors"])


def test_a_scratching_only_on_the_racecard_still_blocks(tmp_path):
    """呢個係最重要嗰條。一隻馬喺排位表冇咗但賽績仲有 = 賽績過期，
    放過佢就會用舊名單做分析。"""
    card_without_2 = "馬號: 1\n馬名: 甲\n負磅: 126\n"
    _write_pair(tmp_path, 1, card_without_2, _CARD)
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "kept", "唔一致就唔准放行"


def test_a_substitution_still_blocks(tmp_path):
    """同號唔同馬 —— 只數馬匹數目係捉唔到嘅。"""
    swapped = _CARD.replace("馬名: 乙", "馬名: 另一隻")
    _write_pair(tmp_path, 1, swapped, _CARD)
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "kept"


def test_a_kept_racecard_cannot_vouch_for_anything(tmp_path):
    """前提 1：作證嘅來源本身要係今次新鮮抽到。一份 kept 排位表可能同 kept
    賽績一樣過期 —— 兩份舊嘢對得上證明唔到任何嘢。"""
    _write_pair(tmp_path, 1, _CARD, _CARD)
    results = [_result(racecard_state="kept")]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "kept"


def test_a_truncated_racecard_does_not_verify(tmp_path):
    """前提 3：半截頁唔准作證。"""
    truncated = _CARD + "馬號: 3\n"        # 有號冇名
    _write_pair(tmp_path, 1, truncated, _CARD)
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "kept"


def test_a_truncated_formguide_does_not_verify(tmp_path):
    _write_pair(tmp_path, 1, _CARD, _CARD + "馬號: 3\n")
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "kept"


def test_two_empty_lineups_do_not_verify_each_other(tmp_path):
    """兩邊都解析唔到嘢 ≠ 一致。`card and card == form` 守呢一條。"""
    _write_pair(tmp_path, 1, "冇馬匹\n", "冇馬匹\n")
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "kept"


def test_a_fresh_formguide_is_left_alone(tmp_path):
    _write_pair(tmp_path, 1, _CARD, _CARD)
    results = [_result(formguide_state="fresh")]
    results[0]["formguide_ok"] = True
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "fresh"


def test_a_missing_formguide_is_never_verified(tmp_path):
    """完全冇檔就冇嘢可以核實 —— 唔可以由 missing 跳去 verified。"""
    (tmp_path / "09-09 Race 1 排位表.md").write_text(_CARD, encoding="utf-8")
    results = [_result(formguide_state="missing")]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")
    assert results[0]["formguide_state"] == "missing"


def test_verification_never_raises_on_unreadable_files(tmp_path):
    """核實係加分項 —— 唔可以因為佢而搞冧成個抽取。"""
    results = [_result()]
    batch._verify_kept_formguides(results, str(tmp_path), "09-09")   # 兩個檔都唔存在
    assert results[0]["formguide_state"] == "kept"


def test_the_gate_counts_verified_alongside_fresh():
    """結構閘：`total_fg` 一定要同時數 fresh 同 verified，唔然核實白做。"""
    src = _gate_source()
    line_start = src.index("total_fg = sum(")
    block = src[line_start:line_start + 260]
    assert "formguide_ok" in block
    assert "'verified'" in block or '"verified"' in block


def test_racecards_are_still_fresh_only():
    """排位表冇獨立來源可以幫佢作證，所以佢照樣要 fresh。"""
    src = _gate_source()
    line = [ln for ln in src.splitlines() if ln.strip().startswith("total_rc = sum(")][0]
    assert "racecard_ok" in line
    assert "verified" not in line
