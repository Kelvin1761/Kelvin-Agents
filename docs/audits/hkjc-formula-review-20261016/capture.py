"""Read-only production replay with compact per-runner evidence for this audit."""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
sys.path.insert(0, str(SCRIPTS))
import hkjc_eval_harness as harness  # noqa: E402


def main():
    os.environ["WC_DISABLE_HKJC_PROFILE_ENRICH"] = "1"
    os.environ["WC_DISABLE_POST_SUCCESS_DEPLOY"] = "1"
    import hkjc_auto_orchestrator as orch

    original = orch.HKJCAutoOrchestrator.score_race
    evidence_path, replay_path = sys.argv[1:]
    with open(evidence_path, "w", encoding="utf-8") as evidence:
        def capture(self, race_file):
            logic = original(self, race_file)
            if logic:
                runners = {}
                for number, horse in logic["horses"].items():
                    auto = horse.get("python_auto") or {}
                    runners[number] = {
                        "input": {k: v for k, v in horse.items() if k != "python_auto"},
                        "auto": {k: auto.get(k) for k in (
                            "feature_scores", "derived_feature_scores", "score_provenance",
                            "matrix_scores", "ability_score_raw", "reason_codes",
                            "race_shape_robustness", "sip_flags")},
                    }
                evidence.write(json.dumps({
                    "meeting": race_file.parent.name, "race": int(race_file.stem.split("_")[1]),
                    "context": logic["race_analysis"], "horses": runners,
                }, ensure_ascii=False) + "\n")
                evidence.flush()
            return logic

        orch.HKJCAutoOrchestrator.score_race = capture
        return harness.main(["run", "--until", "2026-10-10", "--dump-matrix", "--out", replay_path])


if __name__ == "__main__":
    raise SystemExit(main())
