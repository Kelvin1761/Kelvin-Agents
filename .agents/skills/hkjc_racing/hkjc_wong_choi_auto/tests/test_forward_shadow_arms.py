import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import performance_figure as pf, straight_figure

ROOT = Path(__file__).resolve().parents[5]
PATCHES = ROOT / "docs/experiments/patches"


def load(name):
    spec = importlib.util.spec_from_file_location(name, PATCHES / f"hkjc_arm_{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def horse(code, rating, weight):
    return {"horse_code": code, "weight": weight, "_data": {"current_rating": rating},
            "python_auto": {"ability_score_raw": 70.0}}


@pytest.mark.parametrize("name", ["samedist_figure_shadow", "group_rating_shadow", "awt_figure_shadow"])
def test_shadow_adjusts_centred_and_registers(name):
    hs = {"1": horse("A", 120, 130), "2": horse("B", 100, 120), "3": horse("C", 110, 125)}
    runs = {"A": [(2., 130, 1.2), (1., 130, 1.2)], "B": [(0., 120, 1.2), (0., 120, 1.2)]}
    segment = {"A": [(3., 130, 1.2)], "B": [(0., 120, 1.2)]}
    rc = {"race_date": "2026-11-26", "race_class": "一級賽", "distance": "1200m", "track": "全天候", "venue": "沙田"}
    with patch.object(straight_figure, "apply", return_value=0), patch.object(pf, "figures_as_of", return_value=runs), \
         patch.object(pf, "distance_runs_as_of", return_value=segment), \
         patch.object(pf, "segment_figures", return_value={"awt": segment}):
        load(name).apply()
        straight_figure.apply(hs, rc)
        boosts = [h["python_auto"]["sip_flags"][-1]["boost"] for h in hs.values()]
        assert sum(boosts) == pytest.approx(0, abs=0.00015)
        assert any(abs(b) > 0.01 for b in boosts)
        assert all(h["python_auto"]["sip_flags"][-1]["boost_scale"] == "raw" for h in hs.values())
        if name == "awt_figure_shadow":
            untouched = {"1": horse("A", 120, 130)}
            straight_figure.apply(untouched, dict(rc, track="草地"))
            assert "sip_flags" not in untouched["1"]["python_auto"]
        if name == "group_rating_shadow":
            for context, foreign, missing in [(dict(rc, race_class="第一班"), False, False), (rc, True, False), (rc, False, True)]:
                field = {"1": horse("A", 120, 130), "2": horse("B", 100, 120)}
                if missing:
                    del field["2"]["weight"]
                with patch("hkjc_racing_engine.tags.is_foreign", return_value=foreign):
                    straight_figure.apply(field, context)
                assert all("sip_flags" not in h["python_auto"] for h in field.values())


def test_distance_runs_as_of_filters_before_selecting_six():
    rows = []
    for i, (date, dist) in enumerate([(f"2026-01-{day:02}", 1000 if day % 2 else 1400) for day in range(1, 15)] + [("2026-02-01", 1200)]):
        for code, offset in [("A", 0), ("B", .2)]:
            km = dist / 1000
            time = 60 * km + offset
            rows.append(dict(date=date, race=f"{i}", code=code, w=120, km=km, dist=dist,
                             beaten=offset, tkm=time/km, tkm_cap=time/km, hs=code, surface="田草", straight=False))
    pf._CACHE.clear()
    try:
        with patch.object(pf, "load_results", return_value=pd.DataFrame(rows)):
            selected = pf.distance_runs_as_of("2026-02-01", 1200)["A"]
            assert len(selected) == 6
            assert all(abs(r[2] * 1000 - 1200) <= 200 and r[3] < "2026-02-01" for r in selected)
            assert selected[0][3] == "2026-01-14"
            assert pf.distance_runs_as_of("2026-02-01", 1200, tol=0) == {}
    finally:
        pf._CACHE.clear()
