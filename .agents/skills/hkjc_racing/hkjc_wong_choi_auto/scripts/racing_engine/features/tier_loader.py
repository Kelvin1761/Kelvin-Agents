from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def load_tiers():
    root = Path(".agents/skills/hkjc_racing/hkjc_wong_choi_auto")
    path = root / "resources" / "05_jockey_trainer_tiers.json"
    return json.loads(path.read_text(encoding="utf-8"))


def score_tier(group, raw_name, default_reason):
    name = str(raw_name or "").upper()
    for tier in load_tiers().get(group, []):
        if any(str(item).upper() in name for item in tier.get("names", [])):
            return float(tier["score"]), str(tier["reason"])
    return 60.0, default_reason
