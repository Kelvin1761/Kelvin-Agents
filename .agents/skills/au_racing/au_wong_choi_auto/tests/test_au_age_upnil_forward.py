"""EXP-20261121-37 forward shadow：幅度凍結、只扣 START_DATE 之後、特徵讀引擎標籤。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_age_upnil_forward as F  # noqa: E402


def test_arms_frozen():
    assert F.ARMS == {"OLD": ("old_horse", -3.46), "SUNIL": ("second_up_nil", -1.93)}
    assert F.START_DATE == "2026-11-22" and F.TARGET_RACES == 1000


def test_tag_keys_reads_engine_tags():
    auto = {"tags": {"bad": [{"key": "old_horse"}, {"key": "second_up_nil"}], "good": [], "note": [{"key": "top_weight"}]}}
    assert F.tag_keys(auto) == {"old_horse", "second_up_nil", "top_weight"}


def test_candidate_only_moves_forward_races_with_tag():
    races = [{"date": "2026-11-21", "rows": [{"ability": 70.0, "keys": ["old_horse"]}]},
             {"date": "2026-11-22", "rows": [{"ability": 70.0, "keys": ["old_horse"]}, {"ability": 65.0, "keys": []}]}]
    out = F.candidate(races, "old_horse", -3.46)
    assert out[0]["rows"][0]["ability"] == 70.0
    assert out[1]["rows"][0]["ability"] == 70.0 - 3.46 and out[1]["rows"][1]["ability"] == 65.0
