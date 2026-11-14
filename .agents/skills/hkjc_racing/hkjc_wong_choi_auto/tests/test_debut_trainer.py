"""初出馬練馬師初出紀錄（決定 3，EXP-20261114-06）：as-of、收縮、標籤只顯示。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import debut_trainer as dt  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402

EV = [["2025-01-01", "甲", 1], ["2025-02-01", "甲", 1], ["2025-03-01", "甲", 0], ["2025-12-01", "甲", 1], ["2025-02-01", "乙", 0]]


def test_rate_is_as_of_and_shrunk():
    r = dt.rate("甲", "2025-06-01", EV)
    assert (r["places"], r["starts"]) == (2, 3)                      # 2025-12-01 之後嘅唔計
    assert abs(r["rate"] - (2 + 0.25 * 10) / (3 + 10)) < 1e-12
    assert dt.rate("甲", "2025-01-01", EV)["starts"] == 0               # 同日唔計
    assert dt.rate("", "2025-06-01", EV) is None


def test_tag_only_for_debut_and_unscored(monkeypatch):
    monkeypatch.setattr(dt, "_EVENTS", [["2024-0%d-01" % (i % 9 + 1), "甲", 1] for i in range(20)])
    meta = {"date": "2025-06-01"}
    assert tags._debut_trainer_tag({"is_debut": False, "trainer": "甲"}, meta) == []
    out = tags._debut_trainer_tag({"is_debut": True, "trainer": "甲"}, meta)
    assert len(out) == 1 and out[0]["scored"] is False and out[0]["tone"] == "good"
