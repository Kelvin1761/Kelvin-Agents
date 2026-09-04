#!/usr/bin/env python3
"""Bounded, pre-registered HKJC refit; production scorer and canonical metrics.

Research only. No archive writes and no model promotion. See EXP-20260902-08.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
sys.path.insert(0, str(ROOT / ".agents/skills/shared_racing"))
sys.path.insert(0, str(ROOT / ".agents/skills/shared_racing/scripts"))
import pit_backtest as pit
import rescore_backtest as bt
from corpus_paths import logic_files
from eval_metrics import race_metrics
from hkjc_results_db import build_results_index
from hkjc_auto_orchestrator import _apply_sip_enhancements
from hkjc_racing_engine import scoring
from hkjc_racing_engine.engine_core import RacingEngine
from model_evaluation_decision import _paired_metric_evidence
from wongchoi_paths import HK_RACING

SECTIONS = tuple(scoring.MATRIX_WEIGHTS)
BASE = np.array([scoring.MATRIX_WEIGHTS[k] for k in SECTIONS])
CUTOFF = "2026-06-13"  # EXP-03: never move a previously examined terminal window.
METRICS = ("gold", "gold_strict", "good_positional", "pass", "zero_hit", "one_hit",
           "champion", "winner_in_top3", "top3_capture_at5", "top3_mean_model_rank",
           "competitive_recall_at5", "ndcg_at5")
LOWER = {"zero_hit", "one_hit", "top3_mean_model_rank"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def collect():
    raw = pit.load_all_rows()
    results_index = build_results_index()
    grouped = defaultdict(list)
    for name in logic_files(HK_RACING):
        grouped[Path(name).parent].append(Path(name))
    races, prior_manifest, problems = [], [], []
    dates_missing = schema_sparse = 0
    seen = set()
    provenance = Counter()
    for md, paths in sorted(grouped.items()):
        day = md.name[:10]
        local = bt.find_results_json(md)
        result_path = local or results_index.get(day)
        if result_path is None:
            raise ValueError(f"Missing results: {md}")
        results = bt.load_results(result_path)
        n = pit.inject_as_of(raw, day)
        sub = raw[raw.Date < day]
        prior_manifest.append(dict(date=day, rows=n, latest=str(sub.Date.max()),
                                   distance_latest=str(sub[sub.Distance.notna()].Date.max())))
        for lp in sorted(paths, key=bt.race_num_from_path):
            original_bytes = lp.read_bytes()
            logic = json.loads(original_bytes)
            rn = bt.race_num_from_path(lp)
            if rn not in results:
                raise ValueError(f"Missing race results {lp}")
            key = f"{md.name}/R{rn}"
            if key in seen:
                raise ValueError(f"Duplicate race {key}")
            seen.add(key)
            context = logic.setdefault("race_analysis", {})
            dates_missing += not bool(context.get("race_date"))
            context = bt.resolve_meeting_context(logic, md)
            # Legacy narrative speed_map/verdict is not evidence for this model.
            context.pop("speed_map", None)
            context.pop("verdict", None)
            rescored = bt.rescore_logic(logic)
            row = dict(key=key, date=day, venue=context["venue"], race_class=context.get("race_class"),
                       source=str(lp), source_sha=hashlib.sha256(original_bytes).hexdigest(),
                       runners=[], actual=results[rn])
            for hn, horse in rescored["horses"].items():
                auto = horse["python_auto"]
                engine = RacingEngine(horse, context)
                fs = auto["feature_scores"]
                data = horse.get("_data") or {}
                sparse = len(data) < 20
                schema_sparse += sparse
                fields = {}
                for field in ("draw_position_fit", "position_pi", "position_window"):
                    text = str(engine._value(field) or "")
                    fields[field] = text
                    provenance[field + "_nonempty"] += bool(text and text != "N/A")
                    # This is a visible-date audit, NOT proof of immutable capture.
                    tokens = re.findall(r"20\d{2}[-/]\d{2}[-/]\d{2}", text)
                    future = [v for v in tokens if v.replace("/", "-") >= day]
                    if future:
                        problems.append(dict(race=key, horse=hn, field=field, dates=future))
                fit = engine._draw_position_fit_score()[0]
                trip = engine._trip_consumption_score()[0]
                row["runners"].append(dict(hn=int(hn), weight=horse.get("weight"),
                    barrier=horse.get("barrier"), matrix=auto["matrix_scores"],
                    features=fs, baseline_ability=auto["ability_score"],
                    debut=engine._is_debut(), sparse=sparse,
                    draw=fs["draw_score"], fit=fit, trip=trip, shape_text=fields))
            if not {h for h, p in results[rn].items() if p <= 3}.issubset(
                    {r["hn"] for r in row["runners"]}):
                raise ValueError(f"Missing placed runner {key}")
            row["sparse"] = sum(r["sparse"] for r in row["runners"]) > len(row["runners"]) / 2
            races.append(row)
        print(f"scored {md.name}: {len(paths)} races; prior<{day}: {n}", flush=True)
    races.sort(key=lambda r: (r["date"], r["key"]))
    return races, dict(raw_rows=len(raw), raw_date_range=[str(raw.Date.min()), str(raw.Date.max())],
                       raw_content_sha=digest(raw.fillna("").astype(str).to_dict("records")),
                       missing_race_dates=dates_missing, sparse_runners=schema_sparse,
                       source_presence=dict(provenance), dated_signal_violations=problems,
                       priors=prior_manifest,
                       leakage_status="FLAG: aggregate PIT repaired; archived derived-signal capture not proven")


def ordering(race, weights=BASE, ablation=None):
    horses = {}
    for r in race["runners"]:
        matrix = dict(r["matrix"])
        if ablation == "shape_neutral":
            matrix["race_shape"] = 60.0
        elif ablation and RacingEngine({}, {"venue": race["venue"]})._is_sha_tin_context():
            c = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
            fit = 60.0 if ablation in ("fit_neutral", "fit_trip_neutral") else r["fit"]
            trip = 60.0 if ablation in ("trip_neutral", "fit_trip_neutral") else r["trip"]
            matrix["race_shape"] = (c["sha_tin_draw"] * r["draw"]
                + c["sha_tin_draw_position_fit"] * fit + c["sha_tin_trip_consumption"] * trip)
        w = scoring.DEBUT_MATRIX_WEIGHTS if r["debut"] else dict(zip(SECTIONS, weights))
        score = round(sum(matrix[k] * v for k, v in w.items()), 2)
        horses[str(r["hn"])] = dict(weight=r["weight"], barrier=r["barrier"],
            python_auto=dict(ability_score=score, grade=scoring.compute_grade(score),
                             feature_scores=r["features"]))
    _apply_sip_enhancements(horses)
    scores = {int(h): v["python_auto"]["ability_score"] for h, v in horses.items()}
    return sorted(scores, key=lambda h: (-scores[h], h)), scores


def metrics(race, order):
    actual = {int(k): int(v) for k, v in race["actual"].items()}
    m = race_metrics(order, {h for h, p in actual.items() if p <= 3}, actual_pos=actual)
    m["zero_hit"], m["one_hit"] = m["hits"] == 0, m["hits"] == 1
    return {k: float(m[k]) for k in METRICS}


def summarize(rows):
    return {k: float(np.mean([r[k] for r in rows])) for k in METRICS}


def compare(races, baseline, candidate):
    dev = [i for i, r in enumerate(races) if r["date"] < CUTOFF]
    terminal = [i for i, r in enumerate(races) if r["date"] >= CUTOFF]
    out = {}
    for label, indices in (("dev", dev), ("terminal", terminal)):
        out[label] = dict(n=len(indices), baseline=summarize([baseline[i] for i in indices]),
                         candidate=summarize([candidate[i] for i in indices]))
    out["evidence"] = {k: asdict(_paired_metric_evidence(
        [r[k] for r in baseline], [r[k] for r in candidate], dev, terminal,
        higher_is_better=k not in LOWER)) for k in METRICS}
    for cohort in ("venue", "sparse", "field_size"):
        groups = defaultdict(list)
        for i in terminal:
            r = races[i]
            size = len(r["runners"])
            name = str(r.get(cohort)) if cohort != "field_size" else (
                "<=8" if size <= 8 else "9-10" if size <= 10 else "11-12" if size <= 12 else "13+")
            groups[name].append(i)
        out[cohort] = {g: dict(n=len(ix), delta={k: float(np.mean([
            candidate[i][k] - baseline[i][k] for i in ix])) for k in METRICS}) for g, ix in groups.items()}
    weak = [i for i, r in enumerate(baseline) if r["zero_hit"] or r["one_hit"]]
    out["weak_races"] = dict(n=len(weak), improved=sum(
        candidate[i]["zero_hit"] + candidate[i]["one_hit"] < 1 for i in weak))
    return out


def fit(races):
    # PL top3 likelihood. A tiny fixed ridge stabilises only zero-curvature cases;
    # no terminal statistic or candidate KPI enters this optimisation.
    stages = []
    for r in races:
        matrix = np.array([[h["matrix"][k] for k in SECTIONS] for h in r["runners"]])
        hn = [h["hn"] for h in r["runners"]]
        actual = {int(k): v for k, v in r["actual"].items()}
        remaining = list(range(len(hn)))
        for pos in (1, 2, 3):
            finishers = [i for i in remaining if actual.get(hn[i]) == pos]
            if len(finishers) != 1:  # Never impose an invented order on dead heats.
                break
            winner = finishers[0]
            stages.append((matrix[remaining] / 10, matrix[winner] / 10))
            remaining.remove(winner)
    if not stages:
        raise ValueError("No ordered PL stages in training sample")
    # Batch the same loss/gradient; avoid millions of tiny Python/NumPy calls.
    width = max(len(x) for x, _ in stages)
    tensor = np.zeros((len(stages), width, len(SECTIONS)))
    mask = np.full((len(stages), width), -np.inf)
    winners = np.array([win for _, win in stages])
    for i, (x, _) in enumerate(stages):
        tensor[i, :len(x)] = x
        mask[i, :len(x)] = 0
    def objective(beta):
        s = np.einsum("ijk,k->ij", tensor, beta) + mask
        z = logsumexp(s, axis=1)
        loss = np.mean(z - winners @ beta)
        grad = np.mean(np.einsum("ij,ijk->ik", np.exp(s-z[:, None]), tensor)-winners, axis=0)
        return loss + 1e-5*np.sum(beta**2), grad + 2e-5*beta
    opt = minimize(objective, BASE * 3, jac=True, bounds=[(0, None)] * len(BASE),
                   method="L-BFGS-B", options={"maxiter": 250})
    if not opt.success or opt.x.sum() <= 0:
        raise RuntimeError(f"PL fit failed: {opt.message}")
    return opt.x / opt.x.sum()


def consensus(races, n=200):
    # Debut scoring is locked; don't let its different equation fit standard weights.
    races = [r for r in races if not any(h["debut"] for h in r["runners"])]
    groups = defaultdict(list)
    for r in races:
        groups[r["date"]].append(r)
    dates = sorted(groups)
    rng = np.random.default_rng(20260902)
    fits = []
    for i in range(n):
        sample = [r for d in rng.choice(dates, len(dates), replace=True) for r in groups[d]]
        fits.append(fit(sample))
        if i % 40 == 0:
            print(f"dev meeting-bootstrap fit {i+1}/{n}", flush=True)
    values = np.asarray(fits)
    middle = np.median(values, axis=0)
    middle /= middle.sum()
    return middle, {k: [float(v) for v in np.quantile(values[:, j], [0.05, 0.95])]
                    for j, k in enumerate(SECTIONS)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reuse-dump", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    dump = args.out / "pit_scored.json"
    source_code = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for base in (ROOT/".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
                     ROOT/".agents/skills/hkjc_racing/hkjc_reflector/scripts")
        for p in base.rglob("*.py")}
    if args.reuse_dump:
        stored = json.loads(dump.read_text())
        if stored["source_code"] != source_code:
            raise ValueError("Engine/harness changed; regenerate dump")
        races, audit = stored["races"], stored["audit"]
    else:
        races, audit = collect()
        dump.write_text(json.dumps(dict(races=races, audit=audit, source_code=source_code), ensure_ascii=False))
    for r in races:
        order, scores = ordering(r)
        for h in r["runners"]:
            if scores[h["hn"]] != h["baseline_ability"]:
                raise ValueError(f"Production replica mismatch {r['key']} #{h['hn']}")
    print(f"replica exact: {len(races)} races / {sum(len(r['runners']) for r in races)} runners", flush=True)
    baseline = [metrics(r, ordering(r)[0]) for r in races]
    neutral = [metrics(r, ordering(r, ablation="shape_neutral")[0]) for r in races]
    # Power audit precedes candidate measurement; no post-hoc rescue.
    power = compare(races, baseline, neutral)
    dev = [r for r in races if r["date"] < CUTOFF]
    dev_dates = sorted({r["date"] for r in dev})
    folds = []
    for block in np.array_split(dev_dates, 6)[1:]:
        train = [r for r in dev if r["date"] < block[0]]
        val = [r for r in dev if r["date"] in block]
        w = fit([r for r in train if not any(h["debut"] for h in r["runners"])])
        folds.append(dict(train_dates=sorted({r["date"] for r in train}), validation_dates=list(block),
            weights=dict(zip(SECTIONS, w)), baseline=summarize([metrics(r, ordering(r)[0]) for r in val]),
            candidate=summarize([metrics(r, ordering(r, w)[0]) for r in val])))
    weights, intervals = consensus(dev)
    configs = {"joint_refit": (weights, None)}
    for dim in ("stability", "sectional"):
        w = BASE.copy()
        w[SECTIONS.index("race_shape")] -= .05
        w[SECTIONS.index(dim)] += .05
        configs["shape_to_" + dim] = (w, None)
    for ab in ("fit_neutral", "trip_neutral", "fit_trip_neutral"):
        configs[ab] = (BASE, ab)
    results = {}
    for label, (w, ab) in configs.items():
        candidate = [metrics(r, ordering(r, w, ab)[0]) for r in races]
        results[label] = compare(races, baseline, candidate)
        print(label, json.dumps(results[label]["terminal"], ensure_ascii=False), flush=True)
    ablations = {}
    for j, dim in enumerate(SECTIONS):
        w = BASE.copy() * ((1-weights[j]) / (1-BASE[j]))
        w[j] = weights[j]
        ablations[dim] = dict(weights=dict(zip(SECTIONS,w)),
            dev=summarize([metrics(r, ordering(r, w)[0]) for r in dev]))
    leaves = {}
    for section in (*SECTIONS, "draw", "fit", "trip"):
        values, pairwins, pairs = [], 0.0, 0
        sds = []
        for r in dev:
            actual = {int(k): v for k, v in r["actual"].items()}
            vals = [h["matrix"][section] if section in SECTIONS else h[section] for h in r["runners"]]
            values.extend(vals)
            sds.append(float(np.std(vals)))
            for i, h in enumerate(r["runners"]):
                for j, hh in enumerate(r["runners"]):
                    if actual.get(h["hn"],99) < actual.get(hh["hn"],99) and vals[i] != 60 and vals[j] != 60:
                        pairs += 1
                        pairwins += (1 if vals[i]>vals[j] else .5 if vals[i]==vals[j] else 0)
        leaves[section] = dict(dev_neutral_fraction=float(np.mean(np.isclose(values,60))),
            dev_mean_within_race_sd=float(np.mean(sds)), nonneutral_pairs=pairs,
            dev_pairwise_auc=pairwins/pairs if pairs else None)
    report = dict(commit=subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT,text=True).strip(),
        research_script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sample_hash=digest([(r["key"],r["source_sha"]) for r in races]),
        evaluation_contract_sha=hashlib.sha256((ROOT/"docs/model-evaluation-contract.md").read_bytes()).hexdigest(),
        races=len(races), runners=sum(len(r["runners"]) for r in races), cutoff=CUTOFF,
        audit=audit, baseline_weights=dict(zip(SECTIONS,BASE)), refit_weights=dict(zip(SECTIONS,weights)),
        intervals=intervals, shape_neutral_power=power, folds=folds, candidates=results,
        dev_single_dimension_ablations=ablations, dev_leaf_diagnostics=leaves,
        decision="NEEDS MORE TESTING: PIT repaired, but archive provenance FLAG and terminal previously inspected; no promotion")
    (args.out/"evidence.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ("races","runners","refit_weights","decision")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
