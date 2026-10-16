"""Persist compact audit evidence, full-record screens and source manifest."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study  # noqa: E402
from model_evaluation_decision import _full_record_metric, evaluate_full_record  # noqa: E402

PREFIX = Path("/private/tmp/hkjc-review-20261016")


def rows(suffix):
    return study.read(str(PREFIX) + suffix)


def compare(base, cand, mode):
    keyed = {(r["meeting"], r["race"]): r for r in cand if "error" not in r}
    assert len(base) == len({(r["meeting"], r["race"]) for r in base})
    matched = [keyed[(r["meeting"], r["race"])] for r in base]
    dates = [r["date"] for r in base]
    evidence = {k: vars(_full_record_metric([r[k] for r in base], [r[k] for r in matched], dates,
                    higher_is_better=k != "mean_top3_model_rank", blocks=6, bootstrap=2000, seed=7))
                for k in study.METRICS}
    screen = evaluate_full_record(domain="hkjc", mode=mode, dates=dates, baseline_rows=base,
                                  candidate_rows=matched, leakage_audit_passed=True,
                                  ranking_metrics=study.METRICS[2:])
    return {"races": len(base), "changed_races": sum(b["picks"] != c["picks"] for b, c in zip(base, matched)),
            "metrics": evidence, "statistical_screen_assuming_provenance_pass": screen}


def sp_cohorts(base, cand):
    """Only post-score outcome stratification; never pass SP to any engine."""
    import hkjc_eval_harness as harness
    root = harness._default_root()
    cache = {}
    keyed = {(r["meeting"], r["race"]): r for r in cand if "error" not in r}
    groups = {k: ([], []) for k in ("1-3", "3-5", "5-10", "10-21", "21+", "missing")}
    for b in base:
        meeting = b["meeting"]
        if meeting not in cache:
            matches = list((root / meeting).glob("*全日賽果.json"))
            cache[meeting] = json.loads(matches[0].read_text()) if matches else {}
        race = cache[meeting].get(str(b["race"]), {})
        try:
            runner = next(r for r in race.get("results", []) if int(r["horse_no"]) == b["picks"][0])
            sp = float(runner["win_odds"])
            label = "1-3" if sp <= 3 else "3-5" if sp <= 5 else "5-10" if sp <= 10 else "10-21" if sp < 21 else "21+"
        except (StopIteration, ValueError, KeyError, TypeError):
            label = "missing"
        groups[label][0].append(b)
        groups[label][1].append(keyed[(meeting, b["race"])])
    return {label: compare(bb, cc, "fixed_rule") for label, (bb, cc) in groups.items() if bb}


def main():
    study.load_baseline_methods()
    base = rows("-canonical.jsonl")
    summary = json.loads(Path(str(PREFIX) + "-study/summary.json").read_text())
    ml = rows("-ml-clean.jsonl")
    runtime = rows("-fallback-runtime.jsonl")
    offline = study.read(str(PREFIX) + "-study/fallback_same_scale.jsonl")
    runtime_by = {(r["meeting"], r["race"]): r for r in runtime if "error" not in r}
    assert all(r["picks"] == runtime_by[(r["meeting"], r["race"])]["picks"] for r in offline)
    result = {"baseline_commit": "dd22b05d", "study": summary,
              "fallback_runtime_rank_match": len(base), "ml_clean": compare(base, ml, "walk_forward_oos")}
    statuses = Path(str(PREFIX) + "-valid-status-runtime.jsonl")
    if statuses.exists() and len(study.read(statuses)) == 351:
        status = study.read(statuses)
        result["invalid_status"] = compare(base, status, "fixed_rule")
        result["invalid_status_sp_cohorts"] = sp_cohorts(base, status)
    # Count actual fallback evidence, not just equality to a neutral number.
    cov = Counter()
    keys = {(r["meeting"], r["race"]) for r in base}
    for r in rows("-evidence.jsonl"):
        if (r["meeting"], r["race"]) not in keys:
            continue
        for rec in r["horses"].values():
            e = study.RacingEngine(rec["input"], r["context"])
            runs = e._parse_recent_runs(e._text("recent_6_detail"))
            if any(run["rank"] <= 0 for run in runs):
                cov["detail_has_invalid_rank"] += 1
            if not runs and not e._is_debut():
                ranks = [int(x) for x in study.re.findall(r"\b\d+\b", str(rec["input"].get("last_6_finishes") or "")) if int(x) > 0]
                cov["fallback_with_valid_ranks" if ranks else "fallback_without_valid_ranks"] += 1
    result["extra_coverage"] = dict(cov)
    manifest = {}
    for suffix in ("-baseline.jsonl", "-canonical.jsonl", "-evidence.jsonl", "-capture-baseline.jsonl",
                   "-fallback-runtime.jsonl", "-ml-clean.jsonl", "-valid-status-runtime.jsonl"):
        path = Path(str(PREFIX) + suffix)
        if path.exists():
            manifest[str(path)] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    result["artifact_manifest"] = manifest
    result["decision"] = {
        "stability_rules": "KEEP_EXISTING", "all_outer_weights": "KEEP_EXISTING",
        "invalid_status": "CORRECTNESS_FIX_SECTION7", "model_gain_claim": False,
        "invalid_status_scoped_leakage_audit": "PASS: remove impossible ranks, no new or future input",
        "whole_archive_provenance": "FLAG: PIT aggregates and date checks do not certify every derived field",
        "withdrawn_test": "Original top3_margin incorrectly treated 52 winning margins as losing margins; corrected arm excludes winners. Original Good -1 claim withdrawn.",
    }
    # Raw runner dumps stay outside Git; these are paired aggregate results.
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    compact = {"ml": result["ml_clean"], "extra_coverage": result["extra_coverage"]}
    if "invalid_status" in result:
        compact["invalid_status"] = result["invalid_status"]
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
