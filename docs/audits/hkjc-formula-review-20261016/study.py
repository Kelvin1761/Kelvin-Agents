"""Bounded HKJC audit: exact downstream replay, fixed arms, coverage and power."""
import argparse
import ast
import copy
import datetime as dt
import json
import re
import sys
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for path in (REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts",
             REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
             REPO / ".agents/skills/shared_racing"):
    sys.path.insert(0, str(path))
import hkjc_auto_orchestrator as orch  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402
from hkjc_racing_engine.features.form import FormScorer  # noqa: E402
from hkjc_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402

METRICS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5",
           "competitive_recall_at5", "mean_top3_model_rank")
STABILITY = ("no_form", "no_consistency", "rank67_equal45", "top3_margin", "fallback_same_scale")


def load_baseline_methods():
    """Pin the two corrected history parsers for baseline research only."""
    from hkjc_racing_engine import engine_core

    relative = ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/engine_core.py"
    source = subprocess.check_output(["git", "show", "dd22b05d:" + relative], cwd=REPO, text=True)
    cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == "RacingEngine")
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"_consistency_score", "_parse_recent_runs"}:
            namespace = dict(engine_core.__dict__)
            exec(compile(ast.Module(body=[node], type_ignores=[]), "baseline_history.py", "exec"), namespace)
            setattr(RacingEngine, node.name, namespace[node.name])


def read(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def score(horses):
    """Use live summation order, rounding, SIP, shape cap and raw tie-break."""
    work = copy.deepcopy(horses)
    for horse in work.values():
        auto = horse["python_auto"]
        m = auto["matrix_scores"]
        e = RacingEngine(horse, {})
        raw = round(e._ability_score(m), 2)
        auto.update(ability_score_raw=raw, ability_score=round(scoring.to_display_scale(raw), 2))
        auto["grade"] = scoring.compute_grade(auto["ability_score"])
        auto.pop("sip_flags", None)
    orch._apply_sip_enhancements(work)
    orch.HKJCAutoOrchestrator._apply_mainline_shape_robustness(work)
    return work


def prepare(evidence):
    horses = {}
    for number, rec in evidence["horses"].items():
        h = copy.deepcopy(rec["input"])
        h["python_auto"] = copy.deepcopy(rec["auto"])
        auto = h["python_auto"]
        robust = auto.get("race_shape_robustness") or {}
        if "base_race_shape" in robust:
            auto["matrix_scores"]["race_shape"] = robust["base_race_shape"]
        horses[number] = h
    return horses


def patched_c(engine, features, arm):
    detail = engine._consistency_shadow_detail()
    if arm == "fallback_same_scale" and detail is None and not engine._is_debut():
        ranks = [int(x) for x in re.findall(r"\b\d+\b", str(engine.horse_data.get("last_6_finishes") or ""))[:6] if int(x) > 0]
        if ranks:
            surrogate = copy.deepcopy(engine.horse_data)
            surrogate.setdefault("_data", {})["recent_6_detail"] = " | ".join(
                f"第{i+1}仗: {rank}名 N/A" for i, rank in enumerate(ranks))
            detail = RacingEngine(surrogate, engine.race_context)._consistency_shadow_detail()
    value = detail["score"] if detail else engine._consistency_score(features)[0]
    if arm == "top3_margin" and detail:
        runs = engine._parse_recent_runs(engine._text("recent_6_detail"))[:6]
        weights = [1, .85, .7, .55, .45, .35]
        total = sum(weights[:len(runs)])
        lost = sum(weights[i] * (1 - 3 / run["margin"])
                   for i, run in enumerate(runs)
                   if 2 <= run["rank"] <= 3 and run["margin"] is not None and run["margin"] > 3)
        value -= 18 * lost / total if total else 0
    return scoring.clip_score(value)


def candidate(horses, context, arm):
    work = copy.deepcopy(horses)
    for horse in work.values():
        auto = horse["python_auto"]
        if arm.startswith("neutral_"):
            auto["matrix_scores"][arm.removeprefix("neutral_")] = 60.0
            continue
        engine = RacingEngine(horse, context)
        features = {**auto["feature_scores"], **auto["derived_feature_scores"]}
        features["form_score"] = scoring.clip_score(FormScorer(horse, context).compute()[0])
        features["consistency_score"] = patched_c(engine, features, "current")
        if arm == "no_form":
            features["form_score"] = 60.0
            features["consistency_score"] = patched_c(engine, features, arm)
        elif arm == "no_consistency":
            features["consistency_score"] = 60.0
        elif arm == "rank67_equal45":
            # Same parsing/overseas path as production; only the 6/7 buckets move.
            original = scoring.FORM_MICRO_WEIGHTS["rank_other"]
            # FormScorer has a shared 6+ bucket. Reproduce its list via a
            # production scorer per single rank, and change only eligible rows.
            data = horse.get("_data") or {}
            ranks = []
            for token in str(horse.get("last_6_finishes") or "").replace("-", " ").replace(",", " ").split():
                try:
                    rank = int(token.split("/")[0])
                    if rank > 0:
                        ranks.append(rank)
                except ValueError:
                    pass
            dates = str(data.get("recent_6_detail") or "")
            for row in data.get("pdf_overseas_races") or []:
                day = str(row.get("date", "")).strip()
                if day and day not in ("-", "N/A") and day in dates:
                    continue
                try:
                    rank = int(str(row.get("rank", "")).split("/")[0])
                    if rank > 0:
                        ranks.append(rank)
                except ValueError:
                    pass
            ranks = ranks[:6]
            if ranks:
                gain = sum((60.0 - original) / (i + 1) for i, rank in enumerate(ranks) if rank in (6, 7))
                features["form_score"] = scoring.clip_score(features["form_score"] + gain / sum(1 / (i + 1) for i in range(len(ranks))))
            features["consistency_score"] = patched_c(engine, features, arm)
        else:
            features["consistency_score"] = patched_c(engine, features, arm)
        mapped = map_features_to_matrix_scores(features)
        auto["matrix_scores"]["stability"] = mapped["stability"]
        auto["feature_scores"].update({k: round(features[k], 2) for k in ("form_score", "consistency_score")})
    return score(work)


def ranked(horses):
    return [int(n) for n, _ in sorted(horses.items(), key=lambda pair: (-pair[1]["python_auto"]["ability_score_raw"], int(pair[0])))]


def row_for(base, horses, arm):
    picks = ranked(horses)
    pos = {h["n"]: h["pos"] for h in base["horses"] if h.get("pos")}
    m = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
    m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
    return {**{k: v for k, v in base.items() if k != "horses"}, **{k: m.get(k) for k in METRICS},
            "champion": m.get("champion"), "picks": picks, "arm": arm}


def clustered_stats(rows, dates, boot_indices):
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)
    a = np.array([[sum(float(r[k]) for r in by_day[d]) for k in METRICS] for d in dates])
    n = np.array([len(by_day[d]) for d in dates])
    return a, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("evidence")
    ap.add_argument("output")
    args = ap.parse_args()
    load_baseline_methods()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    bases = [r for r in read(args.baseline) if "error" not in r and "speed_score" not in r.get("meeting_dead_fields", [])]
    ev = {(r["meeting"], r["race"]): r for r in read(args.evidence)}
    arms = ("aa", *STABILITY, *("neutral_" + k for k in (*scoring.MATRIX_WEIGHTS, *scoring.CENTRED_MATRIX_WEIGHTS)))
    rows = {arm: [] for arm in arms}
    coverage = Counter()
    leaves = defaultdict(list)
    correlations = []
    errors = []
    for race_index, b in enumerate(bases):
        if race_index % 25 == 0:
            print(f"audit replay {race_index}/{len(bases)}", flush=True)
        e = ev[(b["meeting"], b["race"])]
        h = prepare(e)
        aa = score(h)
        differences = [n for n in h if abs(aa[n]["python_auto"]["ability_score_raw"] - e["horses"][n]["auto"]["ability_score_raw"]) > .000001]
        if differences or ranked(aa) != b["picks"]:
            errors.append([b["meeting"], b["race"], differences])
        for arm in arms:
            work = aa if arm == "aa" else candidate(h, e["context"], arm)
            rows[arm].append(row_for(b, work, arm))
        pos = {r["n"]: r["pos"] for r in b["horses"]}
        race_leaf = defaultdict(list)
        fc = []
        for n, horse in h.items():
            a = horse["python_auto"]
            eng = RacingEngine(horse, e["context"])
            runs = eng._parse_recent_runs(eng._text("recent_6_detail"))[:6]
            coverage["runners"] += 1
            coverage["debut"] += eng._is_debut()
            coverage["consistency_detail"] += bool(runs) and not eng._is_debut()
            coverage["consistency_fallback_non_debut"] += not runs and not eng._is_debut()
            form = str(horse.get("last_6_finishes") or "")
            ranks = [int(v) for v in re.findall(r"\b\d+\b", form)[:6]]
            coverage["last6_zero"] += 0 in ranks
            coverage["last6_rank_slash"] += bool(re.search(r"\d+\s*/\s*\d+", form))
            valid_ranks = [rank for rank in ranks if rank > 0]
            coverage["rank_sequence_mismatch"] += bool(runs) and bool(valid_ranks) and valid_ranks[:len(runs)] != [r["rank"] for r in runs][:len(valid_ranks)]
            dates = []
            for d, m, y in re.findall(r"第\d+仗\((\d{2})/(\d{2})/(\d{4})", eng._text("recent_6_detail")):
                try:
                    dates.append(dt.date(int(y), int(m), int(d)).isoformat())
                except ValueError:
                    coverage["invalid_date"] += 1
            coverage["dated_runners"] += bool(dates)
            coverage["non_descending_dates"] += dates != sorted(dates, reverse=True)
            coverage["current_or_future_history"] += any(d >= b["date"] for d in dates)
            for r in runs:
                coverage["history_runs"] += 1
                coverage["history_missing_margin"] += r["margin"] is None
                coverage["top3_over3L"] += 1 <= r["rank"] <= 3 and r["margin"] is not None and r["margin"] > 3
                coverage["rank6plus_close"] += r["rank"] >= 6 and r["margin"] is not None and r["margin"] <= 2.5
            fs = {**a["feature_scores"], **a["derived_feature_scores"]}
            for k, v in fs.items():
                coverage[k + "_60"] += v == 60
                if pos.get(int(n)) and v != 60:
                    race_leaf[k].append((v, pos[int(n)] <= 3))
            fc.append([fs["form_score"], fs["consistency_score"]])
        arr = np.asarray(fc)
        correlations.extend((arr - arr.mean(axis=0)).tolist())
        for k, values in race_leaf.items():
            pairs = [(x > y) + .5 * (x == y) for x, p in values if p for y, q in values if not q]
            if pairs:
                leaves[k].append((b["date"], float(np.mean(pairs))))
    if errors:
        raise RuntimeError(f"A/A failed: {errors[:10]}")
    dates = sorted({r["date"] for r in bases})
    rng = np.random.default_rng(20261016)
    boot = rng.integers(0, len(dates), size=(2000, len(dates)))
    ba, counts = clustered_stats(bases, dates, boot)
    reports, pvals = {}, {}
    for arm, rr in rows.items():
        (out / (arm + ".jsonl")).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rr))
        ca, _ = clustered_stats(rr, dates, boot)
        delta = ca - ba
        draws = delta[boot].sum(axis=1) / counts[boot].sum(axis=1)[:, None]
        point = delta.sum(axis=0) / counts.sum()
        stats = {}
        for j, k in enumerate(METRICS):
            lo, hi = np.quantile(draws[:, j], [.025, .975])
            p = min(1.0, 2 * min((np.count_nonzero(draws[:, j] <= 0) + 1) / 2001,
                                  (np.count_nonzero(draws[:, j] >= 0) + 1) / 2001))
            stats[k] = {"delta": float(point[j]), "ci": [float(lo), float(hi)], "p": p,
                        "mde_halfwidth": float((hi - lo) / 2)}
            if arm in STABILITY:
                pvals[arm + ":" + k] = p
        cohorts = {}
        for label, test in {"field_le8": lambda r: r["field"] <= 8,
                            "field9_10": lambda r: 9 <= r["field"] <= 10,
                            "field11_12": lambda r: 11 <= r["field"] <= 12,
                            "field13plus": lambda r: r["field"] >= 13,
                            "AWT": lambda r: r["awt"],
                            "HV": lambda r: "跑馬地" in r["venue"],
                            "ST_turf": lambda r: "沙田" in r["venue"] and not r["awt"]}.items():
            ix = [i for i, r in enumerate(bases) if test(r)]
            if ix:
                cohorts[label] = {"races": len(ix), **{k: float(np.mean([float(rr[i][k])-float(bases[i][k]) for i in ix])) for k in METRICS}}
        # This is descriptive evidence. Provenance flags prevent promotion.
        verdict = evaluate_full_record(domain="hkjc", mode="fixed_rule", dates=[r["date"] for r in bases],
                                      baseline_rows=bases, candidate_rows=rr, leakage_audit_passed=False,
                                      ranking_metrics=METRICS[2:])
        screen = evaluate_full_record(domain="hkjc", mode="fixed_rule", dates=[r["date"] for r in bases],
                                     baseline_rows=bases, candidate_rows=rr, leakage_audit_passed=True,
                                     ranking_metrics=METRICS[2:])
        reports[arm] = {"changed_races": sum(b["picks"] != c["picks"] for b, c in zip(bases, rr)),
                        "metrics": stats, "cohorts": cohorts, "safety_verdict": verdict,
                        "statistical_screen_assuming_provenance_pass": screen}
    leaf_report = {}
    for k, values in leaves.items():
        by_day = defaultdict(list)
        for day, value in values:
            by_day[day].append(value)
        ds = sorted(by_day)
        indices = rng.integers(0, len(ds), size=(2000, len(ds)))
        sums = np.array([sum(by_day[d]) for d in ds])
        ns = np.array([len(by_day[d]) for d in ds])
        draws = sums[indices].sum(axis=1) / ns[indices].sum(axis=1)
        leaf_report[k] = {"races": len(values), "auc": float(np.mean([v for _, v in values])),
                          "ci": np.quantile(draws, [.025, .975]).tolist()}
    result = {"baseline_races": len(bases), "dates": [dates[0], dates[-1]], "meetings": len(dates),
              "baseline": {k: float(np.mean([r[k] for r in bases])) for k in METRICS},
              "aa_exact": not errors, "coverage": dict(coverage), "leaf_auc_non60": leaf_report,
              "within_race_form_consistency_r": float(np.corrcoef(np.array(correlations).T)[0, 1]),
              "arms": reports, "holm_stability": holm_adjust(pvals),
              "limitations": ["Historical source availability not certified by date-order checks alone",
                              "Official SP cohort source not joined; no promotion claim",
                              "New rules have no unseen forward confirmation"]}
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"races": len(bases), "aa_exact": not errors, "coverage": dict(coverage),
                      "arms": {k: {"changed": v["changed_races"], "gold": v["metrics"]["gold"]["delta"],
                                    "good": v["metrics"]["good_positional"]["delta"],
                                    "ndcg": v["metrics"]["ndcg_at5"]["delta"]} for k, v in reports.items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
