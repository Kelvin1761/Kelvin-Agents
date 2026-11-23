"""EXP-20261123-18 AF；β 4.69／0.83 取自該實驗 walk-forward。forward shadow，唔入 live。"""
import math

ARM_NAME = "awt_figure_shadow"


def apply():
    from hkjc_racing_engine import straight_figure, performance_figure as pf
    from hkjc_racing_engine.market_history import horse_code
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    from hkjc_racing_engine import surface_move
    original = straight_figure.apply

    def wrapped(horses, race_context=None):
        count = original(horses, race_context)
        rc = race_context or {}
        date = str(rc.get("race_date") or "")[:10]
        scored = {k: h for k, h in horses.items() if isinstance(h, dict)
                  and isinstance(h.get("python_auto"), dict)
                  and h["python_auto"].get("ability_score_raw") is not None}
        if not date or not scored:
            return count
        table = pf.figures_as_of(date)
        if surface_move.today_surface(rc) != "泥地":
            return count
        segment = pf.segment_figures(date)["awt"]
        values = {}
        for key, horse in scored.items():
            code = horse_code(horse) or ""
            weight = pf._weight(horse)
            result = pf.segment_gap(table.get(code), segment.get(code), weight)
            gap = result["gap"] if result else None
            values[key] = (gap, 1.0) if gap is not None else (0.0, 0.0)
        n = len(values)
        mean_gap = sum(v[0] for v in values.values()) / n
        mean_has = sum(v[1] for v in values.values()) / n
        adjustments = {k: 4.69 * (g - mean_gap) + 0.83 * (has - mean_has)
                       for k, (g, has) in values.items()}

        for key, add in adjustments.items():
            auto = scored[key]["python_auto"]
            boost = round(add, 4)
            raw = round(float(auto["ability_score_raw"]) + boost, 4)
            auto.setdefault("sip_flags", []).append({"reason": ARM_NAME, "boost": boost, "boost_scale": "raw"})
            auto["ability_score_raw"] = raw
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            count += abs(boost) > 1e-9
        return count

    straight_figure.apply = wrapped
