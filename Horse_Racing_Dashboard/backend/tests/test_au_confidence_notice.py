"""大爛地可信度提示：用引擎嘅大爛地定義，只顯示（Kelvin 2026-11-21）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.au_confidence_notice import confidence_notice  # noqa: E402

TEMPLATE = Path(__file__).resolve().parents[2] / "static_template.html"


def test_heavy_only():
    for g in ("Heavy 8", "Heavy 10", "Heavy"):
        n = confidence_notice(g)
        assert n and n["label"] == "大爛地 · 預測可信度較低" and "唔入評分" in n["detail"]
    for g in ("Soft 7", "Good 4", "Synthetic", "", None):
        assert confidence_notice(g) is None


def test_template_renders_notice():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "renderConfidenceNotice(analysis.confidence_notice)" in text
