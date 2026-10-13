"""Reproduce the frozen 2026-10-14 drift-monitor usefulness experiment."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/monitoring"))
from corpus_paths import logic_files
from data_contract import calibrate, check, resolve_root
from drift_monitor import compare, cohort_report, read_rows


def main():
    out = REPO / "scratch/evidently-20261014"
    out.mkdir(parents=True, exist_ok=True)
    protocol_path = out / "protocol.json"
    if not protocol_path.exists():
        recorded = json.loads((REPO / "docs/experiments/evidence/evidently-20261014.json").read_text())
        protocol_path.write_text(json.dumps(recorded["protocol"], indent=2) + "\n")
    protocol = json.loads(protocol_path.read_text())
    results = {"protocol": protocol, "commit": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(), "platforms": {}}
    results["code_sha256"] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), REPO / ".agents/skills/shared_racing/monitoring/drift_monitor.py",
        REPO / ".agents/skills/shared_racing/scripts/data_contract.py")}
    for platform in ("au", "hkjc"):
        all_paths = logic_files(resolve_root(platform))
        ref_paths = [p for p in all_paths if "2026-10-01" <= Path(p).parent.name[:10] <= "2026-10-07"]
        current_paths = [p for p in all_paths if "2026-10-08" <= Path(p).parent.name[:10] <= "2026-10-13"]
        ref_rows, ref_manifest = read_rows(ref_paths)
        current_rows, current_manifest = read_rows(current_paths)
        if not ref_rows or not current_rows:
            results["platforms"][platform] = {"status": "insufficient_data"}
            continue
        started = time.monotonic()
        natural = compare(ref_rows, current_rows, out / f"{platform}_natural.html")
        cohorts = cohort_report(ref_rows, current_rows)
        # Calibrate the legacy comparator on the exact same stored scores used
        # for fault injection, so model-generation differences cannot hide faults.
        sample = current_paths[:30]
        base_rows, _ = read_rows(sample)
        baselines = [json.loads(Path(p).read_bytes()) for p in sample]
        cases = []
        with tempfile.TemporaryDirectory(prefix="wc-drift-fault-") as temp:
            baseline = calibrate(platform, sample, Path(temp) / "baseline.json")
            for case in protocol["controls"] + protocol["faults"]:
                with tempfile.TemporaryDirectory(dir=temp) as arm:
                    paths, horse_i = [], 0
                    for source, original in zip(sample, baselines):
                        data = copy.deepcopy(original)
                        for horse in data["horses"].values():
                            fields = horse["python_auto"]["feature_scores"]
                            field = protocol["fault_field"]
                            if case == "field_removed":
                                fields.pop(field, None)
                            elif case == "missing_33pct" and horse_i % 3 == 0:
                                fields.pop(field, None)
                            elif case == "all_neutral":
                                fields[field] = 60.0
                            elif case == "add_4_points":
                                fields[field] += 4.0
                            elif case == "compress_spread_25pct":
                                fields[field] = 60.0 + 0.75 * (fields[field] - 60.0)
                            horse_i += 1
                        destination = Path(arm) / Path(source).parent.name / Path(source).name
                        destination.parent.mkdir(exist_ok=True)
                        destination.write_text(json.dumps(data))
                        paths.append(destination)
                    rows, _ = read_rows(paths)
                    if case == "row_shuffle":
                        random.Random(7).shuffle(rows)
                    violations, summary = check(baseline, paths, platform)
                    fields = compare(base_rows, rows)
                    focal = fields[protocol["fault_field"]]
                    cases.append({"case": case, "races": summary["races"], "horses": len(rows),
                                  "legacy_findings": [vars(v) for v in violations],
                                  "evidently": focal,
                                  "evidently_drift_detected": focal["status"] == "drift"})
        controls_clean = all(not c["legacy_findings"] and c["evidently"]["status"] == "stable" for c in cases[:2])
        incremental = [c["case"] for c in cases[2:] if c["evidently_drift_detected"] and not c["legacy_findings"]]
        # Every source byte must still match its pre-run digest.
        manifest = ref_manifest + current_manifest
        unchanged = all(hashlib.sha256(Path(m["path"]).read_bytes()).hexdigest() == m["sha256"] for m in manifest)
        results["platforms"][platform] = {"reference_races": len(ref_paths), "current_races": len(current_paths),
            "reference_horses": len(ref_rows), "current_horses": len(current_rows),
            "natural_unverified": natural, "cohorts": cohorts, "cases": cases,
            "controls_clean": controls_clean, "incremental_faults": incremental,
            "source_bytes_unchanged": unchanged, "elapsed_seconds": round(time.monotonic() - started, 2),
            "decision": "ADOPT_ADVISORY" if controls_clean and incremental and unchanged else "DO_NOT_ADOPT",
            "manifest": manifest}
        print(platform, results["platforms"][platform]["decision"], "extra", incremental, "cohorts", sum(c["status"] == "evaluated" for c in cohorts), flush=True)
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
