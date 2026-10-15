from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def load_tiers():
    # Resolve relative to this module (…/scripts/racing_engine/features/) so the
    # loader works regardless of the process working directory. Was hardcoded as
    # a CWD-relative path, which raised FileNotFoundError unless run from repo root.
    skill_root = Path(__file__).resolve().parents[3]  # hkjc_wong_choi_auto/
    path = skill_root / "resources" / "05_jockey_trainer_tiers.json"
    return json.loads(path.read_text(encoding="utf-8"))


def tiers_available(as_of_date) -> bool:
    """Point-in-time gate for the hand-maintained tier table.

    ``05_jockey_trainer_tiers.json`` is undated and edited in place, i.e. it is
    always "today's tiers".  Live cards (race date today or later) may use it.
    A historical replay may use it only when the file declares an ``as_of_date``
    on or before the race date; otherwise it is neutral (EXP-20261015-02).
    Unknown race dates are fail-closed.
    """
    from hkjc_racing_engine.live_priors import _parse_as_of_date, is_live_race_date
    if is_live_race_date(as_of_date):
        return True
    requested = _parse_as_of_date(as_of_date)
    table_date = _parse_as_of_date(load_tiers().get("as_of_date"))
    return requested is not None and table_date is not None and table_date <= requested


HISTORICAL_TIER_REASON = "歷史回放：層級表冇該日版本，中性60"


def score_tier(group, raw_name, default_reason, *, as_of_date=None, live=False):
    """Tier lookup.  Pass ``as_of_date`` (the race date) on every scoring path;
    ``live=True`` is only for explicit live-card callers without a context."""
    if not live and not tiers_available(as_of_date):
        return 60.0, HISTORICAL_TIER_REASON
    name = str(raw_name or "").upper()
    for tier in load_tiers().get(group, []):
        if any(str(item).upper() in name for item in tier.get("names", [])):
            score = float(tier["score"])
            # Be explicit when materialized two-season ratings are unavailable:
            # this is the audited tier fallback, not a live empirical estimate.
            reason = f"層級後備實績評分{score:.1f}（{tier['reason']}）"
            return score, reason
    return 60.0, default_reason
