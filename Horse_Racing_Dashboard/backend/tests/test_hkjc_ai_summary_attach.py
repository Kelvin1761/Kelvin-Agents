"""HKJC AI 摘要 sidecar 掛去每匹馬：報告冇變先掛（Kelvin 2026-11-26）。"""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from services.parser_hkjc import _attach_ai_summaries  # noqa: E402


def _setup(tmp_path, sha=None):
    analysis = tmp_path / "Race_3_Auto_Analysis.md"
    analysis.write_text("報告內容", encoding="utf-8")
    real = hashlib.sha256(analysis.read_bytes()).hexdigest()
    (tmp_path / "Race_3_AI_Summary.json").write_text(json.dumps({
        "source_sha256": sha or real, "label": "AI 摘要（未入分）",
        "horses": {"8": {"summary": "排第1名。", "evidence": ["a", "b", "c", "d", "e"]}},
    }, ensure_ascii=False), encoding="utf-8")
    horses = [SimpleNamespace(horse_number=8, ai_summary=None), SimpleNamespace(horse_number=3, ai_summary=None)]
    return analysis, horses


def test_attaches_verified_horses_only(tmp_path):
    analysis, horses = _setup(tmp_path)
    _attach_ai_summaries(analysis, horses)
    assert horses[0].ai_summary["text"] == "排第1名。"
    assert len(horses[0].ai_summary["evidence"]) == 4
    assert horses[1].ai_summary is None


def test_stale_sidecar_is_ignored(tmp_path):
    analysis, horses = _setup(tmp_path, sha="0" * 64)
    _attach_ai_summaries(analysis, horses)
    assert horses[0].ai_summary is None


def test_missing_or_broken_sidecar(tmp_path):
    analysis, horses = _setup(tmp_path)
    (tmp_path / "Race_3_AI_Summary.json").write_text("{爛", encoding="utf-8")
    _attach_ai_summaries(analysis, horses)
    assert horses[0].ai_summary is None
