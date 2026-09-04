"""A hand-copied engine constant is a defect that ages into a wrong conclusion.

Real cases in this repo, all found on 2026-09-04:

  * `au_archive_calibrator.MATRIX_LABELS` froze before `race_shape` retired, so
    the tool named "Calibrate AU Auto matrix weights" had raised
    `KeyError: 'race_shape'` on every run since 2026-08-22.
  * `au_ml_matrix_diagnostics.FEATURE_KEYS`, `au_miss_signal_investigation`
    and `au_failure_direction_audit` froze at 16 leaves / 7 dimensions and
    silently excluded `pace_figure_score`, `performance_quality_score` and
    `preparation_score` from every analysis they produced.
  * `unified_reflector_core.SCORE_LABELS` printed raw English keys into the
    Chinese meeting report.

The silent ones are worse than the crash: you get a clean-looking report that
says a dimension contributed nothing, because it was never in the matrix.

Deliberate subsets are fine -- but they have to say so here, with a reason.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
ENGINE_SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(ENGINE_SCRIPTS))
from au_racing_engine import scoring  # noqa: E402

# (file basename, constant name) -> why this one is allowed to be a subset.
INTENTIONAL_SUBSETS = {
    ("au_tactical_shadow_test.py", "NEW_TIGHTENING"):
        "候選收緊實驗，故意只列受影響嘅 leaf",
    ("au_failure_cause_attribution.py", "CONTROL_FEATURE_KEYS"):
        "對照組，故意排除待測 leaf",
    ("au_failure_cohorts.py", "FEATURE_KEYS_FOR_COVERAGE"):
        "覆蓋率報告只睇會出現 no-evidence 嘅 leaf",
    ("au_no_evidence_cohorts.py", "NO_EVIDENCE"):
        "定義邊幾個 leaf 有 no-evidence 狀態，本身就係子集",
    ("renderer.py", "THIN_EVIDENCE_SCORED_LEAVES"):
        "證據厚度安全欄只數真係入分嘅 leaf",
    # 歷史量測快照。呢幾個記錄嘅係 710 場語料當時嘅實況，
    # 加 preparation 落去就唔再係「當時」。
    ("test_neutral_display_scale.py", "OBSERVED_RAW_MAX"): "710 場語料嘅歷史極值",
    ("test_neutral_display_scale.py", "OBSERVED_RAW_MIN"): "710 場語料嘅歷史極值",
    ("test_neutral_display_scale.py", "PRE_NORMALISATION_WEIGHTS"): "正規化之前嘅歷史權重",
    ("test_neutral_display_scale.py", "RANK_NEUTRAL_WEIGHTS"): "歷史對照權重",
    ("test_neutral_display_scale.py", "NORMALISATION_GAINS"): "歷史 gain 快照",
}

OWNED = {
    "FEATURE_KEYS": frozenset(scoring.FEATURE_KEYS),
    "ABILITY_FEATURE_KEYS": frozenset(scoring.ABILITY_FEATURE_KEYS),
    "MATRIX_WEIGHTS": frozenset(scoring.MATRIX_WEIGHTS),
}

# AU 側先。`shared_racing` 嘅覆盤標籤由
# `shared_racing/tests/test_reflector_score_labels.py` 自己守 —— 兩個閘分開，
# 唔想一個 release 嘅測試要等另一個 release merge 咗先綠。
SEARCH_ROOTS = (REPO / ".agents/skills/au_racing",)

# 引擎自己定義呢啲常數，`ABILITY_FEATURE_KEYS` / `REPORT_ONLY_FEATURE_KEYS`
# 就係 `FEATURE_KEYS` 嘅有意分割，唔算抄。
DEFINING_FILES = {"scoring.py"}


def _string_members(node: ast.AST) -> set[str]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return {e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()


def _candidate_files():
    for root in SEARCH_ROOTS:
        for path in sorted(root.rglob("*.py")):
            parts = {p.lower() for p in path.parts}
            if "__pycache__" in parts or "archive" in parts or "scratch" in parts:
                continue
            if path.name in DEFINING_FILES:
                continue
            yield path


class NoStaleEngineConstantCopies(unittest.TestCase):
    def test_literal_copies_of_engine_constants_are_complete_or_declared(self):
        stale = []
        for path in _candidate_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                target = node.targets[0]
                name = getattr(target, "id", None)
                if not name or not name.isupper():
                    continue
                literals = _string_members(node.value)
                if len(literals) < 4:
                    continue
                for const_name, owned in OWNED.items():
                    overlap = literals & owned
                    # A copy, not a coincidence: mostly engine keys, and enough
                    # of them that a shorter unrelated list cannot trip it.
                    if len(overlap) < 4 or len(overlap) < 0.6 * len(literals):
                        continue
                    missing = owned - literals
                    if not missing:
                        continue
                    if (path.name, name) in INTENTIONAL_SUBSETS:
                        continue
                    stale.append(
                        f"{path.relative_to(REPO)}:{node.lineno} {name} 抄咗 "
                        f"scoring.{const_name}，比引擎少咗 {sorted(missing)}"
                    )
        self.assertEqual(
            [], sorted(set(stale)),
            "手抄嘅引擎常數飄咗。改成由 au_racing_engine 攞；"
            "如果真係想要子集，就加落 INTENTIONAL_SUBSETS 並寫低原因。\n  "
            + "\n  ".join(sorted(set(stale))),
        )

    def test_allowlist_has_no_dead_entries(self):
        """A stale allowlist entry hides the next real drift."""
        names = {(p.name, n) for p in _candidate_files() for n in [None]}
        basenames = {p.name for p in _candidate_files()}
        dead = sorted(f"{f}::{c}" for (f, c) in INTENTIONAL_SUBSETS if f not in basenames)
        self.assertEqual([], dead, f"allowlist 指住唔存在嘅檔案：{dead}")


if __name__ == "__main__":
    unittest.main()
