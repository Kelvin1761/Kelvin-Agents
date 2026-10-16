"""Separate correctness experiment: nonpositive finishes are not completed runs."""
import re

ARM_NAME = "invalid_status_excluded"


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine

    original_parse = RacingEngine._parse_recent_runs
    original_fallback = RacingEngine._consistency_score

    def valid_runs(self, detail):
        return [run for run in original_parse(self, detail) if run["rank"] > 0]

    def valid_fallback(self, features):
        original = self.horse_data
        try:
            ranks = [int(v) for v in re.findall(r"\b\d+\b", str(original.get("last_6_finishes") or "")) if int(v) > 0][:6]
            self.horse_data = {**original, "last_6_finishes": "-".join(map(str, ranks))}
            return original_fallback(self, features)
        finally:
            self.horse_data = original

    RacingEngine._parse_recent_runs = valid_runs
    RacingEngine._consistency_score = valid_fallback
