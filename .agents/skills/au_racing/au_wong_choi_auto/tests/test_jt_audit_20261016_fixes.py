"""EXP-20261016-12／-13 兩個 §7 修正嘅回歸測試。

K2：近績分班次乘數以前讀 `entry["class"]`（由來冇存在），entry_tier 永遠係 7，
乘數變成由今場班次決定嘅全場常數。而家讀往績 `source_race_class`，認唔到就 ×1.0。

J2x-same：「沿用上仗騎師」+2.0 條件化量度方向反（同層 −3.7／−6.7pp），退出計分但保留敘述。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine import engine_core as ec  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402


def form_engine(entries, race_class):
    horse = {"horse_name": "T", "barrier": 5, "weight": 58.0, "career_race_starts": 8,
             "career_tag": "ESTABLISHED", "_data": {"career_record_line": "8:1-1-1"}}
    eng = RacingEngine(horse_data=horse, race_context={"race_class": race_class, "distance": "1200m"})
    eng._official_entry_cache = entries
    eng._form_score()
    return [row["mult"] for row in eng.form_detail["rows"]]


def run(cls):
    return {"placing": "2/10", "field_size": 10, "source_race_class": cls, "date": "2026-09-01",
            "going": "Good 4", "kind": "正式", "is_trial": False}


class TestFormEntryClassTier:
    def test_reads_the_real_past_class(self):
        # 今場 Maiden（8）；往績 BM78（5）→ 降三級 ×1.2；往績 Maiden → 同級 ×1.0
        assert form_engine([run("BM78"), run("MDN-SW")], "Maiden Plate") == [1.2, 1.0]

    def test_unrecognised_side_does_not_adjust(self):
        assert form_engine([run(""), run("HCP")], "Maiden Plate") == [1.0, 1.0]
        assert form_engine([run("BM78")], "Fixture Plate") == [1.0]

    def test_switch_off_reproduces_the_old_field_constant(self, monkeypatch):
        monkeypatch.setattr(ec, "FORM_ENTRY_CLASS_TIER", False)
        # 舊行為：往績一律當 7，今場 Maiden（8）→ 全部 ×1.1，唔理往績班次
        assert form_engine([run("BM78"), run("MDN-SW")], "Maiden Plate") == [1.1, 1.1]


class TestSameJockeySignalNotScored:
    def engine(self):
        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0,
                 "jockey": "Some Rider", "trainer": "Some Stable",
                 "_data": {"jockey_change_signal": "沿用上仗騎師 Some Rider"}}
        return RacingEngine(horse, {"race_class": "BM62", "distance": "1400m",
                                    "field_summary": {"count": 10}})

    def test_same_jockey_alone_is_no_evidence(self):
        eng = self.engine()
        score, note, _src = eng._jockey_horse_fit_score()
        assert score == pytest.approx(RacingEngine._JT_FIT_NO_EVIDENCE)
        assert eng.jt_fit_detail["adjustments"] == []
        assert "不入分" in note
