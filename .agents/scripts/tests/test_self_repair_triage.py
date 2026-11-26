"""自動維修第二層（Hydrogen 診斷 → Python 核證據 → 分流 Opus）。唔會真叫 AI。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import self_repair_triage as T  # noqa: E402


def _wt(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text("\n".join(f"line {i}" for i in range(10)), encoding="utf-8")
    return tmp_path


def test_evidence_must_point_at_real_lines(tmp_path):
    wt = _wt(tmp_path)
    ok, bad = T.check_evidence(["a/x.py:3 — 呢度", "a/x.py:99 — 行號超出", "nope.py:1", "冇路徑", "../../etc/passwd:1"], wt)
    assert ok == ["a/x.py:3 — 呢度"] and len(bad) == 4


def test_routing():
    good = {"fix_size": "small", "confidence": "high", "escalate": False, "fix_draft": "改 x"}
    assert T.route(good, ["a/x.py:3"]) == "opus_review"
    assert T.route(good, []) == "opus_handle"                                   # 證據對唔上
    assert T.route(good, ["a/x.py:3"], ["made/up.py:9"]) == "opus_handle"       # 有一條假證據都唔得
    assert T.route(dict(good, confidence="medium"), ["e"]) == "opus_handle"
    assert T.route(dict(good, fix_size="large"), ["e"]) == "opus_handle"
    assert T.route(dict(good, escalate=True), ["e"]) == "opus_handle"
    assert T.route(dict(good, fix_draft=""), ["e"]) == "opus_handle"
    assert T.route(None, []) == "opus_handle"


def test_main_writes_outputs_without_telegram(tmp_path, monkeypatch):
    (tmp_path / "wt").mkdir()
    wt = _wt(tmp_path / "wt")
    bundle = tmp_path / "job.json"
    bundle.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(T, "ask_ai", lambda *a, **k: ({"cause": "鎖撞", "evidence": ["a/x.py:2"], "confidence": "high",
                                                      "fix_size": "small", "fix_draft": "加等鎖", "escalate": False}, "", "Hydrogen"))
    assert T.main(["--bundle", str(bundle), "--label", "x.job", "--worktree", str(wt), "--no-telegram"]) == 0
    tri = json.loads((tmp_path / "job.triage.json").read_text())
    assert tri["decision"] == "opus_review" and tri["checked_by"] == "Hydrogen"
    md = (tmp_path / "job.diagnosis.md").read_text()
    assert "鎖撞" in md and "未套用" in md


def test_failure_message_escalates(tmp_path):
    msg = T.message("x.job", None, "429", "", [], [], "opus_handle", tmp_path / "d.md")
    assert "要 Opus 處理" in msg
    msg = T.message("x.job", {"cause": "c", "confidence": "high", "fix_size": "small"}, "", "Hydrogen", ["e"], [],
                    "opus_review", tmp_path / "d.md")
    assert "Opus 收貨" in msg and "Sol" in msg
