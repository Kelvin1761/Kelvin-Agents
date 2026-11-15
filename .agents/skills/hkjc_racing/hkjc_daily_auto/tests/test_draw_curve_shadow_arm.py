"""draw_curve_shadow arm（EXP-20261115-19）：凍結表讀得到、場內加減總和為零、跑馬地短途大場 1 檔有著數。"""
import importlib.util
from pathlib import Path

ARM = Path(__file__).resolve().parents[5] / "docs/experiments/patches/hkjc_arm_draw_curve_shadow.py"


def _arm():
    spec = importlib.util.spec_from_file_location("draw_curve_arm", ARM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frozen_table_and_zero_sum():
    arm = _arm()
    assert 10 < arm.BETA < 60 and len(arm.CELLS) > 100
    ra = {"venue": "跑馬地", "track": "Turf", "distance": "1200m"}
    adj = arm.adjustments({i: i for i in range(1, 13)}, ra)
    assert abs(sum(adj.values())) < 1e-9
    assert adj[1] > 0 > adj[12]


def test_groups_and_missing_draw():
    arm = _arm()
    assert arm.group({"venue": "沙田", "track": "Turf", "distance": "1000m"}) == "STRS"
    assert arm.group({"venue": "沙田", "track": "全天候跑道", "distance": "1650m"}) == "AWTL"
    assert arm.group({"venue": "沙田", "distance": ""}) is None
    adj = arm.adjustments({1: 1, 2: None, 3: 7}, {"venue": "沙田", "track": "Turf", "distance": "1400m"})
    assert abs(sum(adj.values())) < 1e-9
    assert arm.adjustments({1: 1}, {}) == {1: 0.0}
