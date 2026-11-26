"""HKJC AI 馬匹摘要（Kelvin 2026-11-26）：分析上咗板之後先做，失敗唔可以令賽前 run 失敗。"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))

import hkjc_daily_schedule as sched  # noqa: E402


def _patch(monkeypatch, output, deploy=(0, "ok")):
    calls = {"publish": 0, "notify": []}
    monkeypatch.setattr(sched, "run_cmd", lambda cmd, **kw: (0, output))
    def publish(*dirs, **kw):
        calls["publish"] += 1
        return deploy
    monkeypatch.setattr(sched, "publish_dashboard_meetings", publish)
    monkeypatch.setattr(sched, "notify", lambda msg, **kw: calls["notify"].append(msg) or True)
    monkeypatch.setattr(sched, "log", lambda *a, **k: None)
    return calls


def test_new_summaries_republish(monkeypatch, tmp_path):
    monkeypatch.delenv("WC_HKJC_AI_SUMMARY", raising=False)
    calls = _patch(monkeypatch, 'R1: {"status": "ok", "accepted": 12, "rejected": 0}')
    assert sched.publish_ai_summaries(tmp_path) is True
    assert calls["publish"] == 1


def test_all_cached_does_not_republish(monkeypatch, tmp_path):
    monkeypatch.delenv("WC_HKJC_AI_SUMMARY", raising=False)
    calls = _patch(monkeypatch, 'R1: {"status": "cached"}\nR2: {"status": "failed", "reason": "x"}')
    assert sched.publish_ai_summaries(tmp_path) is False
    assert calls["publish"] == 0


def test_errors_never_raise(monkeypatch, tmp_path):
    monkeypatch.delenv("WC_HKJC_AI_SUMMARY", raising=False)
    calls = _patch(monkeypatch, "")
    def boom(cmd, **kw):
        raise RuntimeError("agy 死咗")
    monkeypatch.setattr(sched, "run_cmd", boom)
    assert sched.publish_ai_summaries(tmp_path) is False
    calls = _patch(monkeypatch, 'R1: {"status": "ok"}', deploy=(1, "deploy failed"))
    assert sched.publish_ai_summaries(tmp_path) is False
    assert calls["notify"] and "再上板失敗" in calls["notify"][0]


def test_switch_off(monkeypatch, tmp_path):
    monkeypatch.setenv("WC_HKJC_AI_SUMMARY", "0")
    calls = _patch(monkeypatch, 'R1: {"status": "ok"}')
    assert sched.publish_ai_summaries(tmp_path) is False
    assert calls["publish"] == 0


def test_runs_after_dashboard_publish_in_prerace():
    src = Path(sched.__file__).read_text(encoding="utf-8")
    body = src.split("def run_prerace(", 1)[1].split("\ndef ", 1)[0]
    assert body.index("publish_dashboard_meetings(meeting_dir)") < body.index("publish_ai_summaries(meeting_dir)")


def test_republish_requires_a_real_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(sched, "build_dashboard_snapshot", lambda *d: None)
    monkeypatch.setattr(sched, "run_cmd", lambda cmd, **kw: (0, ""))
    code, out = sched.publish_dashboard_meetings.__wrapped__(tmp_path, require_snapshot=True)
    assert code == 1 and "snapshot" in out
