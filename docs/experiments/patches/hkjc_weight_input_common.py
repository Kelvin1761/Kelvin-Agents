"""Shared plumbing for the EXP-20261029-30 weight_score input arms.

Re-reads each race's racecard (排位表) after the production header alignment and
stashes, per runner, the declared weight (排位表負磅, before the apprentice claim)
and the field's highest official rating. Nothing else in the pipeline changes.
"""
from __future__ import annotations


def install_racecard_context():
    import hkjc_auto_orchestrator as orch

    if getattr(orch, "_exp30_context_installed", False):
        return
    original = orch._align_runner_headers

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        path = orch._racecard_path_for_logic(logic_path, race_context.get("race_number"))
        if not path or not path.exists():
            return
        _cls, info = orch._parse_racecard_meta(path.read_text(encoding="utf-8"))
        ratings = []
        for num, horse in horses.items():
            entry = info.get(str(num)) if isinstance(horse, dict) else None
            if entry and entry.get("rating") is not None:
                ratings.append(int(entry["rating"]))
        top = max(ratings) if ratings else None
        for num, horse in horses.items():
            entry = info.get(str(num)) if isinstance(horse, dict) else None
            if not entry:
                continue
            data = horse.setdefault("_data", {})
            if entry.get("weight") is not None:
                data["exp30_declared_weight"] = int(entry["weight"]) + int(entry.get("jockey_claim") or 0)
            if top is not None and entry.get("rating") is not None:
                data["exp30_rating_gap"] = top - int(entry["rating"])

    orch._align_runner_headers = patched
    orch._exp30_context_installed = True


def bucket(is_light, is_heavy):
    from hkjc_racing_engine import scoring
    w = scoring.WEIGHT_MICRO_WEIGHTS
    if is_light:
        return w.get("light_weight_base", 54.0)
    if is_heavy:
        return w.get("heavy_weight_base", 70.0)
    return w.get("base", 64.0)
