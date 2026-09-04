"""The reflector's factor labels must track the engines, not a hand-copy.

`SCORE_LABELS` was maintained by hand and drifted silently: by 2026-09-04 it
was missing `pace_figure_score` (11.49% of ranking weight),
`performance_quality_score`, `rating_score` and `preparation_score`, and the
raw English keys were printing inside the Chinese meeting report --
"短板 `performance_quality_score / 負磅`" in the 2026-09-03 Warrnambool run.

Nothing failed when that happened, because `SCORE_LABELS.get(name, name)`
falls back to the key. These tests are the missing alarm.
"""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
REFLECTOR = REPO / ".agents/skills/shared_racing/race_reflector/scripts"
sys.path.insert(0, str(REFLECTOR))
import unified_reflector_core as core  # noqa: E402


def _engine_feature_keys(scripts_rel: str, module: str) -> set[str]:
    scripts_dir = REPO / scripts_rel
    sys.path.insert(0, str(scripts_dir))
    try:
        return set(getattr(importlib.import_module(module), "FEATURE_KEYS", ()) or ())
    finally:
        if sys.path and sys.path[0] == str(scripts_dir):
            sys.path.pop(0)


class ReflectorLabelsTrackTheEngines(unittest.TestCase):
    def test_every_au_leaf_has_a_chinese_label(self):
        keys = _engine_feature_keys(
            ".agents/skills/au_racing/au_wong_choi_auto/scripts", "au_racing_engine.scoring"
        )
        self.assertTrue(keys, "AU engine exposed no FEATURE_KEYS")
        labels = core.score_labels_for("au")
        missing = sorted(k for k in keys if k not in labels)
        self.assertEqual(
            missing, [],
            f"AU leaves with no label -- they would print as raw English: {missing}",
        )

    def test_every_hkjc_leaf_has_a_chinese_label(self):
        keys = _engine_feature_keys(
            ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
            "hkjc_racing_engine.scoring",
        )
        self.assertTrue(keys, "HKJC engine exposed no FEATURE_KEYS")
        labels = core.score_labels_for("hkjc")
        missing = sorted(k for k in keys if k not in labels)
        self.assertEqual(missing, [], f"HKJC leaves with no label: {missing}")

    def test_no_label_is_an_ascii_passthrough(self):
        """A label equal to its own key means the fallback fired."""
        for domain, table in core.SCORE_LABELS_BY_DOMAIN.items():
            passthrough = sorted(k for k, v in table.items() if k == v)
            self.assertEqual(passthrough, [], f"{domain}: labels that are just the key: {passthrough}")

    def test_labels_are_stripped(self):
        for domain, table in core.SCORE_LABELS_BY_DOMAIN.items():
            ragged = sorted(k for k, v in table.items() if v != v.strip() or not v)
            self.assertEqual(ragged, [], f"{domain}: labels with stray whitespace: {ragged}")

    def test_keys_the_two_engines_disagree_on_are_domain_scoped(self):
        """`class_score` is 級數 for AU and 班次 for HKJC; `confidence_score` is
        信心 for AU and 資料完整度 for HKJC. A flat merge silently hands one
        domain the other's wording, so these must resolve per domain and must
        NOT appear in the domain-less fallback table."""
        au, hkjc = core.score_labels_for("au"), core.score_labels_for("hkjc")
        disputed = {k for k in au.keys() & hkjc.keys() if au[k] != hkjc[k]}
        self.assertTrue(disputed, "expected the two engines to still disagree somewhere")
        for key in disputed:
            self.assertNotIn(
                key, core.SCORE_LABELS,
                f"{key} differs per domain but sits in the flat fallback -- one side gets the wrong word",
            )


    def test_no_two_leaves_share_a_label_within_a_domain(self):
        """Two keys rendering as the same word makes 「短板 檔位」 unreadable --
        you cannot tell which signal was weak."""
        for domain, table in core.SCORE_LABELS_BY_DOMAIN.items():
            seen: dict[str, str] = {}
            clashes = []
            for key, label in sorted(table.items()):
                if label in seen:
                    clashes.append(f"{seen[label]} + {key} -> {label!r}")
                seen[label] = key
            self.assertEqual(clashes, [], f"{domain}: duplicate labels: {clashes}")


class CompositesAreNotFactors(unittest.TestCase):
    def test_model_outputs_are_excluded_from_factor_scores(self):
        """`短板 final_rank_score` is circular -- the model ranked it low
        because the model ranked it low. All composite columns end in
        `_score`, so the reflector's `key.endswith("_score")` filter used to
        sweep them in alongside the real leaves."""
        for key in ("pure_7d_score", "base_7d_score", "final_rank_score",
                    "ability_score", "rank_score"):
            self.assertIn(key, core.COMPOSITE_SCORE_KEYS, f"{key} would be read as a factor")

    def test_no_real_leaf_is_treated_as_a_composite(self):
        for rel, module in (
            (".agents/skills/au_racing/au_wong_choi_auto/scripts", "au_racing_engine.scoring"),
            (".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
             "hkjc_racing_engine.scoring"),
        ):
            overlap = _engine_feature_keys(rel, module) & core.COMPOSITE_SCORE_KEYS
            self.assertEqual(overlap, set(), f"{module}: real leaves excluded as composites: {overlap}")


class ImprovementThemesCoverEveryLeaf(unittest.TestCase):
    def test_no_au_leaf_falls_through_to_general(self):
        """Every leaf should route to a specific improvement theme. Falling to
        "general" produces the one suggestion that says nothing."""
        keys = _engine_feature_keys(
            ".agents/skills/au_racing/au_wong_choi_auto/scripts", "au_racing_engine.scoring"
        )
        unrouted = []
        for key in sorted(keys):
            theme, _text = core.derive_improvement_theme({"factor_scores": {key: 90.0}})
            if theme == "general":
                unrouted.append(key)
        self.assertEqual(unrouted, [], f"leaves with no improvement theme: {unrouted}")


if __name__ == "__main__":
    unittest.main()
