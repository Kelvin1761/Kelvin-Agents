"""EXP-20261121-37 forward shadow：幅度凍結、只扣 START_DATE 之後、特徵讀引擎標籤。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_age_upnil_forward as F  # noqa: E402


def test_arms_frozen():
    assert F.ARMS == {"OLD": ("old_horse", -3.46), "SUNIL": ("second_up_nil", -1.93)}
    assert F.START_DATE == "2026-11-23" and F.TARGET_RACES == 1000
    assert F.ROLLBACK == {"OLD": "old_horse", "TRES": "trainer_residual", "PRIZE": "people_prize_leaf"}
    assert F.SHADOW == {"SUNIL": ("second_up_nil", -1.93)}


def test_tag_keys_reads_engine_tags():
    auto = {"tags": {"bad": [{"key": "old_horse"}, {"key": "second_up_nil"}], "good": [], "note": [{"key": "top_weight"}]}}
    assert F.tag_keys(auto) == {"old_horse", "second_up_nil", "top_weight"}


def test_candidate_only_moves_forward_races_with_tag():
    races = [{"date": "2026-11-21", "rows": [{"ability": 70.0, "keys": ["old_horse"]}]},
             {"date": "2026-11-23", "rows": [{"ability": 70.0, "keys": ["old_horse"]}, {"ability": 65.0, "keys": []}]}]
    out = F.candidate(races, "old_horse", -3.46)
    assert out[0]["rows"][0]["ability"] == 70.0
    assert out[1]["rows"][0]["ability"] == 70.0 - 3.46 and out[1]["rows"][1]["ability"] == 65.0


def test_forward_skips_races_scored_before_labels_existed():
    text = (Path(__file__).resolve().parents[1] / "scripts" / "au_age_upnil_forward.py").read_text(encoding="utf-8")
    assert 'h.get("age") is not None' in text and "date >= START_DATE" in text



def test_rollback_baseline_removes_live_overlay_only_in_forward():
    races = [{"date": "2026-11-22", "rows": [{"ability": 70.0, "old_horse": -3.46}]},
             {"date": "2026-11-23", "rows": [{"ability": 66.54, "old_horse": -3.46, "trainer_residual": 1.0},
                                             {"ability": 65.0, "old_horse": 0.0, "trainer_residual": -1.0}]}]
    base = F.without(races, "old_horse")
    assert base[0]["rows"][0]["ability"] == 70.0
    assert abs(base[1]["rows"][0]["ability"] - 70.0) < 1e-9 and base[1]["rows"][1]["ability"] == 65.0
    tres = F.without(races, "trainer_residual")
    assert abs(tres[1]["rows"][0]["ability"] - 65.54) < 1e-9 and tres[1]["rows"][1]["ability"] == 66.0
