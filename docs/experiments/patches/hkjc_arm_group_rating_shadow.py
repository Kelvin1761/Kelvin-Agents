"""EXP-20261124-10 NRGf；β 5.64 取自該實驗 walk-forward。forward shadow，唔入 live。"""
import math

ARM_NAME = "group_rating_shadow"


def apply():
    from hkjc_racing_engine import straight_figure, performance_figure as pf
    from hkjc_racing_engine.market_history import horse_code
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    from hkjc_racing_engine import tags
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
        if not any(c in str(rc.get("race_class") or "") for c in ("一級賽", "二級賽", "三級賽")):
            return count
        # Eligibility applies to the entire field, including unscored runners.
        ratings, weights = {}, {}
        for key, horse in horses.items():
            if not isinstance(horse, dict) or tags.is_foreign(horse):
                return count
            try:
                rating = float((horse.get("_data") or {}).get("current_rating"))
                weight = float(horse.get("weight"))
            except (TypeError, ValueError):
                return count
            if not math.isfinite(rating) or not math.isfinite(weight):
                return count
            ratings[key], weights[key] = rating, weight
        if len(scored) != len(horses):
            return count
        n = len(scored)
        mr, mw = sum(ratings.values()) / n, sum(weights.values()) / n
        table = pf.figures_as_of(date)
        figs = {k: pf.figure_w(table.get(horse_code(h) or ""), weights[k]) for k, h in scored.items()}
        have = [v for v in figs.values() if v is not None]
        mean_fig = sum(have) / len(have) if have else 0.0
        nets = {k: ((ratings[k] - mr) - (weights[k] - mw)) / 10 *
                (0.5 if figs[k] is not None and figs[k] < mean_fig else 1.0) for k in scored}
        mean_net = sum(nets.values()) / n
        adjustments = {k: 5.64 * (v - mean_net) for k, v in nets.items()}

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
