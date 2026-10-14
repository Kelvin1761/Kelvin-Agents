#!/usr/bin/env python3
"""Retrospective AU weight diagnostics. Never exports deployable weights.

Build a result-separated current-runtime snapshot, then fit each DEVELOPMENT
race to its own results. Terminal dates are excluded before outcome validation.
Oracle rates are hindsight ceilings, never predictive performance evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
from au_eval import date_partitions  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, compose_matrix_score  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402

DIMS = tuple(MATRIX_WEIGHTS)
BASE = np.array([MATRIX_WEIGHTS[k] for k in DIMS])
BUDGET = float(BASE.sum())
TIERS = ("local", "positive", "signed")
MARGIN = 0.001


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_snapshot(archive, results, dest):
    from au_archive_calibrator import load_historical_results
    from au_runtime_failure_audit import race_metadata
    from au_runtime_micro_ablation import (
        iter_aligned_races, prepare_logic_for_scoring,
        score_variant,
    )
    sys.path.insert(0, str(ROOT / ".agents/skills/shared_racing/scripts"))
    from corpus_paths import logic_files
    files = [Path(p) for p in logic_files(archive)]
    placeholders = [p for p in files if p.stat().st_blocks == 0]
    if placeholders:
        raise ValueError(f"Incomplete corpus: {len(placeholders)} placeholders")
    historical = load_historical_results(results)
    races, rejected = [], Counter()
    for index, (path, aligned) in enumerate(iter_aligned_races(
            files, historical, prefetch_workers=1), 1):
        if aligned[0] is None:
            rejected[str(aligned[1])] += 1
            continue
        logic, rows = aligned
        prepared, facts = prepare_logic_for_scoring(logic, path)
        # score_variant joins result fields only after RacingEngine returns.
        scored = score_variant(logic, rows, path, [], include_details=True,
                               prepared_logic=prepared, facts_path=facts)
        compact = []
        for row in scored:
            matrix = row["matrix_scores"]
            compact.append({
                "n": row["horse_number"], "name": row["horse_name"],
                "pos": row["actual_pos"], "ability": row["score"],
                "features": row["feature_scores"], "matrix": matrix,
                # Freeze ALL current overlays, including proven-class.
                "overlay": row["score"] - compose_matrix_score(matrix),
                "evidence": row["feature_evidence_state"],
            })
        meta = race_metadata(path, prepared)
        races.append({"date": meta["date"], "meeting": path.parent.name,
                      "race": meta["race_number"], "metadata": meta,
                      "source": str(path), "rows": compact})
        if index == 1 or index % 50 == 0:
            print(f"Runtime snapshot {index}/{len(files)}", flush=True)
    if any(k.startswith("logic_read_error:") for k in rejected):
        raise ValueError(f"Unreadable corpus: {dict(rejected)}")
    races.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    write_json(dest, {"design": {"model": "current runtime reconstruction",
                                "rejections": dict(rejected),
                                "placeholders": len(placeholders),
                                "baseline_weights": dict(zip(DIMS, BASE))},
                      "races": races})
    print(f"Snapshot: {len(races)} races -> {dest}", flush=True)


def arrays(race):
    rows = sorted(race["rows"], key=lambda r: int(r["n"]))
    matrices = [r.get("matrix") or map_features_to_matrix_scores(r["features"])
                for r in rows]
    x = np.array([[m[k] - 60 for k in DIMS] for m in matrices], dtype=float)
    overlay = np.array([r.get("overlay", float(r.get("wet", 0))
                              + float(r.get("proven_class", 0))) for r in rows])
    reference = np.array([r["ability"] for r in rows])
    error = float(np.max(np.abs(60 + x @ BASE + overlay - reference)))
    if error > 0.01 or not np.isfinite(x).all() or not np.isfinite(overlay).all():
        raise ValueError(f"Replica failed {race['meeting']} R{race['race']}: {error}")
    return rows, x, overlay, error


def metrics(rows, scores):
    order = np.argsort(-scores, kind="stable")
    picks = [rows[i]["n"] for i in order]
    pos = {r["n"]: r["pos"] for r in rows}
    raw = race_metrics(picks, [k for k, p in pos.items() if p <= 3],
                       actual_pos=pos, field_size=len(rows))
    return {"gold": bool(raw["gold"]),
            "good": bool(raw["good_positional"]), "pass": bool(raw["pass"]),
            "mean_top3_rank": raw["top3_mean_model_rank"],
            "top4_hits": raw["top3_capture_at4_count"], "picks": picks,
            "label": raw["exclusive_label"]}


def bounds(tier):
    if tier == "local":
        return [(0.75 * b, 1.25 * b) for b in BASE]
    if tier == "positive":
        return [(0, BUDGET)] * len(BASE)
    return [(-BUDGET, BUDGET)] * len(BASE)


def cloud(tier, samples, rng):
    if tier == "local":
        # Paired transfers preserve sum and the declared +/-25% box exactly.
        weights = np.tile(BASE, (samples, 1))
        for _ in range(12):
            i, j = rng.choice(len(BASE), 2, replace=False)
            lower = np.maximum(0.75 * BASE[i] - weights[:, i],
                               weights[:, j] - 1.25 * BASE[j])
            upper = np.minimum(1.25 * BASE[i] - weights[:, i],
                               weights[:, j] - 0.75 * BASE[j])
            change = rng.uniform(lower, upper)
            weights[:, i] += change
            weights[:, j] -= change
    elif tier == "positive":
        weights = rng.dirichlet(np.ones(len(BASE)) * 0.5, samples) * BUDGET
        weights = np.vstack([weights, np.eye(len(BASE)) * BUDGET])
    else:
        candidates = rng.uniform(-BUDGET, BUDGET, (samples * 5, len(BASE)))
        candidates += (BUDGET - candidates.sum(axis=1))[:, None] / len(BASE)
        weights = candidates[(np.abs(candidates) <= BUDGET + 1e-10).all(axis=1)][:samples]
    return np.vstack([BASE, weights])


def solve_comparisons(x, overlay, comparisons, tier):
    d = len(BASE)
    a = np.array([x[j] - x[i] for i, j in comparisons])
    b = np.array([overlay[i] - overlay[j] - MARGIN for i, j in comparisons])
    aub = np.vstack([np.c_[a, np.zeros_like(a)],
                     np.c_[np.eye(d), -np.eye(d)],
                     np.c_[-np.eye(d), -np.eye(d)]])
    result = linprog(np.r_[np.zeros(d), np.ones(d)], A_ub=aub,
                     b_ub=np.r_[b, BASE, -BASE],
                     A_eq=[np.r_[np.ones(d), np.zeros(d)]], b_eq=[BUDGET],
                     bounds=bounds(tier) + [(0, None)] * d, method="highs")
    if result.success:
        return result.x[:d]
    if result.status != 2:
        raise RuntimeError(f"LP solver failed: {result.message}")
    return None


def joint_witness(x, overlay, pos, tier):
    """Exhaustive LP disjunction for simultaneous Gold AND Good.

    Choose the two podium horses occupying top2, and the ONE outsider permitted
    in top4. Require top2 above everyone else, remaining podium above every
    outsider except that one. Thus all combinatorial cases are covered.
    Failure proves infeasible only in this box, with frozen overlays and margin.
    """
    podium = np.flatnonzero(pos <= 3)
    outsiders = np.flatnonzero(pos > 3)
    for pair in combinations(podium, 2):
        remaining = next(p for p in podium if p not in pair)
        for spare in outsiders:
            comparisons = [(p, j) for p in pair for j in range(len(pos)) if j not in pair]
            comparisons += [(remaining, j) for j in outsiders if j != spare]
            # L1 distance minimisation provides a conservative, reviewable witness.
            weights = solve_comparisons(x, overlay, comparisons, tier)
            if weights is not None:
                return weights, "lp_witness"
    return None, "infeasible_at_margin"


def diagnose(race, clouds):
    rows, x, overlay, error = arrays(race)
    pos = np.array([r["pos"] for r in rows])
    base = metrics(rows, 60 + x @ BASE + overlay)
    record = {"date": race["date"], "meeting": race["meeting"], "race": race["race"],
              "metadata": race.get("metadata", {}), "field": len(rows),
              "baseline": base, "missed": not (base["gold"] or base["good"]),
              "tiers": {}, "replica_error": error}
    for tier in TIERS:
        weights = clouds[tier]
        actual_order = np.argsort(pos)
        full_witness = solve_comparisons(x, overlay, list(zip(actual_order[:-1], actual_order[1:])), tier)
        if full_witness is not None:
            weights = np.vstack([weights, full_witness])
        scores = 60 + weights @ x.T + overlay
        order = np.argsort(-scores, axis=1, kind="stable")
        placed = pos[order] <= 3
        gold = placed[:, :4].sum(axis=1) == 3
        good = placed[:, :2].sum(axis=1) == 2
        passed = placed[:, :3].sum(axis=1) >= 2
        primary = 3 * (gold.astype(int) + good.astype(int) + passed.astype(int)) + placed[:, :3].sum(axis=1)
        eligible = primary == primary.max()
        sampled_joint = gold & good
        witness, status = (None, "sample_witness") if sampled_joint.any() else joint_witness(x, overlay, pos, tier)
        if witness is not None:
            weights = np.vstack([weights, witness])
            scores = 60 + weights @ x.T + overlay
            order = np.argsort(-scores, axis=1, kind="stable")
            placed = pos[order] <= 3
            gold = placed[:, :4].sum(axis=1) == 3
            good = placed[:, :2].sum(axis=1) == 2
            passed = placed[:, :3].sum(axis=1) >= 2
            primary = 3 * (gold.astype(int) + good.astype(int) + passed.astype(int)) + placed[:, :3].sum(axis=1)
            eligible = primary == primary.max()
        # Among equal primary KPI solutions, retain full envelope. Select example
        # by top3 mean rank then within-race full-order concordance then distance.
        ranks = np.argsort(order, axis=1) + 1
        mean_rank = ranks[:, pos <= 3].mean(axis=1)
        pairs = [(i, j) for i in range(len(pos)) for j in range(len(pos)) if pos[i] < pos[j]]
        concordance = np.zeros(len(weights))
        for i, j in pairs:
            concordance += (scores[:, i] > scores[:, j]) + 0.5 * (scores[:, i] == scores[:, j])
        concordance /= max(1, len(pairs))
        distances = np.abs(weights - BASE).sum(axis=1) / BUDGET
        candidates = np.flatnonzero(eligible)
        chosen = min(candidates, key=lambda i: (mean_rank[i], -concordance[i], distances[i]))
        near = candidates[np.argmin(distances[candidates])]
        support = weights[eligible]
        record["tiers"][tier] = {
            "joint_feasible": bool((gold & good).any()), "feasibility": status,
            "full_order_feasible_at_margin": full_witness is not None,
            "best": metrics(rows, scores[chosen]),
            "example_weights": weights[chosen].tolist(),
            "nearest_found_weights": weights[near].tolist(),
            "nearest_found_l1_fraction": float(distances[near]),
            "primary_optimality": "finite search; exact LP certifies joint feasibility only",
            "equally_best_primary_count": len(support),
            "support_sparse": len(support) < 20,
            "weight_q10": np.quantile(support, 0.1, axis=0).tolist(),
            "weight_median": np.median(support, axis=0).tolist(),
            "weight_q90": np.quantile(support, 0.9, axis=0).tolist(),
            "all_best_up": ((support.min(axis=0) > BASE + 0.01 * BUDGET) & (len(support) >= 20)).tolist(),
            "all_best_down": ((support.max(axis=0) < BASE - 0.01 * BUDGET) & (len(support) >= 20)).tolist(),
        }
    # Pareto contradictions show particular podium-v-outsider problems that NO
    # positive reweighting can fix while keeping overlay and matrix signals fixed.
    dominated = []
    for i in np.flatnonzero(pos <= 3):
        for j in np.flatnonzero(pos > 3):
            if np.all(x[j] >= x[i]) and overlay[j] >= overlay[i] and (
                    np.any(x[j] > x[i]) or overlay[j] > overlay[i]):
                dominated.append({"placed": rows[i]["n"], "outsider": rows[j]["n"]})
    record["dominated_podium_pairs"] = dominated
    record["actual_podium"] = [{"n": r["n"], "name": r.get("name", ""), "pos": r["pos"]}
                               for r in rows if r["pos"] <= 3]
    record["dimension_health"] = {
        dim: {"sd": float(x[:, k].std()),
              "neutral_share": float((np.abs(x[:, k]) < 1e-9).mean())}
        for k, dim in enumerate(DIMS)}
    record["leaf_health"] = {}
    for key in sorted(set().union(*(r["features"] for r in rows))):
        values = np.array([r["features"].get(key, 60) for r in rows], dtype=float)
        comparable = [(i, j) for i in np.flatnonzero(pos <= 3)
                      for j in np.flatnonzero(pos > 3)
                      if abs(values[i] - 60) > 1e-9 and abs(values[j] - 60) > 1e-9]
        wins = sum(float(values[i] > values[j]) + 0.5 * float(values[i] == values[j])
                   for i, j in comparable)
        record["leaf_health"][key] = {"neutral_share": float((values == 60).mean()),
                                      "pairs": len(comparable), "wins": wins}
    return record


def rates(records, tier=None):
    return {key: float(np.mean([(r["baseline"] if tier is None else r["tiers"][tier]["best"])[key]
                                for r in records])) if records else None
            for key in ("gold", "good", "pass", "mean_top3_rank")}


def matched_controls(records):
    """One unique success per miss, exact field size, nearest date."""
    successes = [r for r in records if not r["missed"]]
    used, matches = set(), []
    for miss in [r for r in records if r["missed"]]:
        options = [(i, r) for i, r in enumerate(successes) if i not in used
                   and r["field"] == miss["field"]]
        if not options:
            continue
        from datetime import date
        day = date.fromisoformat(miss["date"])
        i, control = min(options, key=lambda item: abs(
            (date.fromisoformat(item[1]["date"]) - day).days))
        used.add(i)
        matches.append((miss, control))
    return matches


def summarize(records):
    misses = [r for r in records if r["missed"]]
    successes = [r for r in records if not r["missed"]]
    matches = matched_controls(records)
    controls = [control for _, control in matches]
    matched_misses = [miss for miss, _ in matches]
    out = {"races": len(records), "misses": len(misses), "successes": len(successes),
           "labels": dict(Counter(r["baseline"]["label"] for r in records)),
           "matched_pairs": len(matches), "baseline": rates(records),
           "oracle": {tier: rates(records, tier) for tier in TIERS},
           "joint_repair": {tier: sum(r["tiers"][tier]["joint_feasible"] for r in misses)
                            for tier in TIERS},
           "at_least_good_found": {tier: sum(r["tiers"][tier]["best"]["gold"] or r["tiers"][tier]["best"]["good"]
                                              for r in misses) for tier in TIERS},
           "full_order_repair": {tier: sum(r["tiers"][tier]["full_order_feasible_at_margin"] for r in misses)
                                 for tier in TIERS},
           "positive_infeasible": sum(not r["tiers"]["positive"]["joint_feasible"] for r in misses),
           "signed_infeasible": sum(not r["tiers"]["signed"]["joint_feasible"] for r in misses),
           "misses_with_dominance": sum(bool(r["dominated_podium_pairs"]) for r in misses),
           "directions": {}, "leaves": {}}
    for k, dim in enumerate(DIMS):
        out["directions"][dim] = {}
        for label, cohort in (("misses", misses), ("successes", successes),
                              ("matched_misses", matched_misses), ("matched_controls", controls)):
            out["directions"][dim][label] = {
                "n": len(cohort),
                "sufficient_support": sum(not r["tiers"]["positive"]["support_sparse"] for r in cohort),
                "all_best_up": sum(r["tiers"]["positive"]["all_best_up"][k] for r in cohort),
                "all_best_down": sum(r["tiers"]["positive"]["all_best_down"][k] for r in cohort),
                "median_shift": float(np.median([r["tiers"]["positive"]["weight_median"][k] - BASE[k]
                                                  for r in cohort])) if cohort else None}
    for key in sorted(set().union(*(r["leaf_health"] for r in records))):
        out["leaves"][key] = {}
        for label, cohort in (("misses", misses), ("successes", successes)):
            rows = [r["leaf_health"][key] for r in cohort if key in r["leaf_health"]]
            pairs = sum(r["pairs"] for r in rows)
            out["leaves"][key][label] = {
                "races": len(rows), "pairs": pairs,
                "auc_non_neutral": sum(r["wins"] for r in rows) / pairs if pairs else None,
                "mean_neutral_share": float(np.mean([r["neutral_share"] for r in rows])) if rows else None}
    groups = defaultdict(list)
    for r in records:
        bucket = "≤8" if r["field"] <= 8 else "9-10" if r["field"] <= 10 else "11-12" if r["field"] <= 12 else "13+"
        groups[f"field:{bucket}"].append(r)
        for key in ("track", "going", "race_class"):
            groups[f"{key}:{r['metadata'].get(key, 'Unknown')}"].append(r)
        distance = r["metadata"].get("distance") or 0
        groups[f"distance:{'unknown' if not distance else '≤1200' if distance <= 1200 else '1201-1600' if distance <= 1600 else '1601-2000' if distance <= 2000 else '2001+'}"].append(r)
    out["cohorts"] = {key: {"n": len(group), "misses": sum(r["missed"] for r in group),
                            "positive_joint_repairs": sum(r["missed"] and r["tiers"]["positive"]["joint_feasible"] for r in group)}
                       for key, group in sorted(groups.items())}
    return out


def transfer(records, source_races):
    """Sanity check: prior dev folds' miss consensus on next dev fold only."""
    dates = sorted({r["date"] for r in records})
    folds = np.array_split(dates, 5)
    lookup = {(r["meeting"], r["race"]): r for r in source_races}
    reports = []
    for k in range(1, 5):
        train_dates = set(np.concatenate(folds[:k]))
        test_dates = set(folds[k])
        train = [r for r in records if r["date"] in train_dates and r["missed"]]
        test = [r for r in records if r["date"] in test_dates]
        if not train or not test:
            continue
        weights = np.median([r["tiers"]["positive"]["weight_median"] for r in train], axis=0)
        weights *= BUDGET / weights.sum()
        candidate = []
        for r in test:
            rows, x, overlay, _ = arrays(lookup[(r["meeting"], r["race"])])
            candidate.append({"baseline": metrics(rows, 60 + x @ weights + overlay)})
        reports.append({"fold": k + 1, "train_misses": len(train), "test_races": len(test),
                        "test_dates": [min(test_dates), max(test_dates)],
                        "weights": weights.tolist(), "baseline": rates(test),
                        "candidate": rates(candidate),
                        "delta": {key: rates(candidate)[key] - rates(test)[key] for key in rates(test)}})
    return reports


def markdown(report):
    s, design = report["summary"], report["design"]
    lines = ["# AU 逐場反推權重診斷", "",
             "**賽後 oracle，唔係預測改善；禁止部署逐場權重。**", "",
             f"Development：{s['races']} 場，{design['dev_dates']}；失手 {s['misses']} 場，成功 {s['successes']} 場。",
             f"Terminal {design['terminal_races']} 場完全冇做反推／分析；對照配對 {s['matched_pairs']} 組（同馬群大細、日期最近、唔重用）。", "",
             "失手＝Gold、Good 兩項都未達；Gold＝實際前三全入模型 Top4；Good＝首兩揀都上名。", "",
             "| 診斷 | Gold | Good | Pass | 實際前三平均模型排名 |",
             "|---|---:|---:|---:|---:|"]
    for label, metric in [("現行 baseline", s["baseline"])] + [(t + " hindsight", s["oracle"][t]) for t in TIERS]:
        lines.append(f"| {label} | {metric['gold']:.1%} | {metric['good']:.1%} | {metric['pass']:.1%} | {metric['mean_top3_rank']:.2f} |")
    lines += ["", "local：每維 ±25%；positive：非負任意配權；signed：每維可反向至 ±原有總係數。全部固定係數總和，全部 overlay 凍結。",
              f"失手場可同時達 Gold＋Good：local {s['joint_repair']['local']}、positive {s['joint_repair']['positive']}、signed {s['joint_repair']['signed']}。",
              f"較寬鬆嘅原定 Good 標準（Gold 或 Good 任一）：搜索已搵到 local {s['at_least_good_found']['local']}、positive {s['at_least_good_found']['positive']}、signed {s['at_least_good_found']['signed']} 場。呢個係已搵到解嘅數目，唔係 exact 不可行判決。",
              f"失手場可完整排返全場賽果次序（LP）：local {s['full_order_repair']['local']}、positive {s['full_order_repair']['positive']}、signed {s['full_order_repair']['signed']}。",
              f"positive 仍做唔到 {s['positive_infeasible']} 場；signed 仍做唔到 {s['signed_infeasible']} 場；失手場有上名馬被其他馬全維度／overlay 支配：{s['misses_with_dominance']} 場。", "",
              "有限搜索搵最好 primary 組合；未有 Gold＋Good 解時，枚舉線性規劃驗證。不可行只針對指定邊界、0.001 分 margin、六維同凍結 overlay，唔代表缺乏所有可用訊號。",
              "最近權重只係已搵到解嘅距離上界；分位數係搜索雲嘅條件分布，唔係可信區間，唔代表權重可唯一識別。", "",
              "## 重複方向（positive，同樣最好 primary 解）", "",
              "| 維度 | 失手：所有解加／減 | 成功：所有解加／減 | 配對失手加／減 | 配對成功加／減 |",
              "|---|---:|---:|---:|---:|"]
    for dim, groups in s["directions"].items():
        cells = [f"{groups[k]['all_best_up']}/{groups[k]['all_best_down']}（n={groups[k]['n']}）"
                 for k in ("misses", "successes", "matched_misses", "matched_controls")]
        lines.append(f"| {dim} | " + " | ".join(cells) + " |")
    lines += ["", "加／減門檻＝原係數總和 1%；少於 20 個同樣最好 primary 解唔計方向。方向只描述搜索到嘅賽後解集，唔係所有數學可行解。按失手條件篩選本身會產生偏差，唔係因果證據。", "",
              "## Leaf 場內判別力（剔除任一端中性 60 嘅配對）", "",
              "| Leaf | 失手 AUC／對數 | 成功 AUC／對數 | 失手中性率 |",
              "|---|---:|---:|---:|"]
    for key, cohorts in s["leaves"].items():
        def cell(row):
            return f"{row['auc_non_neutral']:.3f} / {row['pairs']}" if row['pairs'] else "N/A / 0"
        lines.append(f"| {key} | {cell(cohorts['misses'])} | {cell(cohorts['successes'])} | {cohorts['misses']['mean_neutral_share']:.1%} |")
    lines += ["", "## 只用過去 dev 失手共識，測下一個 dev fold", "",
              "| Fold | 測試場數 | Gold Δ | Good Δ | Pass Δ |", "|---|---:|---:|---:|---:|"]
    for fold in report["transfer"]:
        delta = fold["delta"]
        lines.append(f"| {fold['fold']} | {fold['test_races']} | {delta['gold']*100:+.2f}pp | {delta['good']*100:+.2f}pp | {delta['pass']*100:+.2f}pp |")
    lines += ["", "呢個係預先固定嘅可轉移性 sanity check，冇 bootstrap／promotion 判決；唔用嚟揀新配置。", "",
              "## 場次切片", "", "| Cohort | 場數 | 失手 | positive 同達 Gold＋Good |", "|---|---:|---:|---:|"]
    for key, group in s["cohorts"].items():
        if group["n"] >= 20 or key.startswith("field:"):
            lines.append(f"| {key} | {group['n']} | {group['misses']} | {group['positive_joint_repairs']} |")
    lines += ["", "## 最難修復嘅場次", "",
              "| 場次 | baseline | local／positive／signed 可同達 |", "|---|---|---|"]
    hard = sorted([r for r in report["races"] if r["missed"]], key=lambda r: (
        r["tiers"]["signed"]["joint_feasible"], r["tiers"]["positive"]["joint_feasible"],
        -r["baseline"]["mean_top3_rank"]))[:25]
    for r in hard:
        flags = "／".join("可" if r["tiers"][t]["joint_feasible"] else "不可" for t in TIERS)
        lines.append(f"| {r['meeting']} R{r['race']} | {r['baseline']['label']} | {flags} |")
    lines += ["", "## 證據限制", "",
              "- 用現行引擎重建歷史分數；唔係當日已發佈預測。舊檔、mutable J/T／draw 等來源未逐欄證明 PIT，leakage audit＝FLAG。",
              "- 預設只診斷 2026-08-05 起嘅 dev；日期篩選喺完整語料日期切分之後做，唔改 terminal 邊界。",
              "- 只查六個現行維度，唔重啟退役特徵；常數／中性率唔足以單獨證明管線故障。",
              "- 所有 oracle 權重用咗賽果，絕對唔可以當賽前配置；輸出只供提出新假設。", "",
              f"Dataset SHA256：`{design['dataset_sha256']}`", f"Engine SHA256：`{design['engine_sha256']}`",
              f"Commit：`{design['commit']}`（另記完整 dirty status）", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build-runtime", action="store_true")
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--results-csv", type=Path)
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=20261013)
    parser.add_argument("--since", default="2026-08-05")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    if args.build_runtime:
        if not args.archive_root or not args.results_csv:
            parser.error("--build-runtime requires archive/results paths")
        build_snapshot(args.archive_root, args.results_csv, args.data)
    snapshot = json.loads(args.data.read_text())
    stored_weights = snapshot.get("design", {}).get("baseline_weights")
    if stored_weights and stored_weights != dict(zip(DIMS, BASE)):
        raise ValueError("Snapshot coefficients differ from the current baseline")
    source = snapshot["races"]
    if not source or any(not r.get("date") for r in source):
        raise ValueError("Complete race dates required; row-based split forbidden")
    dev, terminal = date_partitions(source)
    if not dev or not terminal or {source[i]['date'] for i in dev} & {source[i]['date'] for i in terminal}:
        raise ValueError("A disjoint whole-date development/terminal split is required")
    alignment_results = None
    if args.results_csv:
        from au_archive_calibrator import load_historical_results, choose_track_rows
        alignment_results = load_historical_results(args.results_csv)
    selected, excluded, seen = [], Counter(), set()
    for i in dev:
        race = source[i]
        if race["date"] < args.since:
            excluded["before_since"] += 1
            continue
        identity = (race["date"], race["meeting"], race["race"])
        if identity in seen:
            raise ValueError(f"Duplicate race: {identity}")
        seen.add(identity)
        if alignment_results is not None:
            expected = choose_track_rows(alignment_results.get((race["date"], race["race"]), []),
                                         race.get("metadata", {}).get("track", ""))
            if len(expected) != len(race["rows"]):
                excluded["incomplete_runner_alignment"] += 1
                continue
        positions = [r.get("pos") for r in race["rows"]]
        numbers = [r.get("n") for r in race["rows"]]
        if (len(positions) < 4 or len(set(numbers)) != len(numbers)
                or any(not isinstance(p, int) or p < 1 for p in positions)
                or len(set(positions)) != len(positions)
                or sorted(p for p in positions if p <= 3) != [1, 2, 3]):
            excluded["incomplete_or_tied_results"] += 1
            continue
        selected.append(race)
    if not selected:
        raise ValueError("No eligible development races")
    clouds = {tier: cloud(tier, args.samples, np.random.default_rng(args.seed + k))
              for k, tier in enumerate(TIERS)}
    records = []
    for index, race in enumerate(selected, 1):
        records.append(diagnose(race, clouds))
        if index == 1 or index % 50 == 0:
            print(f"Oracle dev {index}/{len(selected)}", flush=True)
    engine_hash = hashlib.sha256()
    for path in sorted((SCRIPTS / "au_racing_engine").rglob("*.py")):
        engine_hash.update(str(path.relative_to(SCRIPTS)).encode())
        engine_hash.update(path.read_bytes())
    design = {"purpose": "hindsight diagnostics; NOT predictive performance",
              "dataset": str(args.data.resolve()),
              "dataset_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
              "results_sha256": hashlib.sha256(args.results_csv.read_bytes()).hexdigest() if args.results_csv else None,
              "complete_runner_alignment_checked": alignment_results is not None,
              "engine_sha256": engine_hash.hexdigest(),
              "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "dirty_status": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
              "command": sys.argv, "seed": args.seed, "samples": args.samples,
              "baseline_weights": dict(zip(DIMS, BASE)), "coefficient_budget": BUDGET,
              "margin": MARGIN, "terminal_races": len(terminal),
              "terminal_dates": sorted({source[i]["date"] for i in terminal}),
              "terminal_outcomes_used": False,
              "dev_dates": [min(r["date"] for r in selected), max(r["date"] for r in selected)],
              "excluded": dict(excluded), "leakage_audit": "FLAG: runtime reconstructed, PIT not certified"}
    report = {"design": design, "summary": summarize(records),
              "transfer": transfer(records, selected), "races": records}
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "diagnostics.json", report)
    fields = ["date", "meeting", "race", "field", "baseline_label", "missed", "tier",
              "gold", "good", "pass", "joint_feasible", "full_order_feasible",
              "baseline_picks", "oracle_picks", "actual_podium", "support_count",
              "nearest_found_l1_fraction", *DIMS]
    with (args.out / "race_weights.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for race in records:
            for tier, result in race["tiers"].items():
                row = {key: race[key] for key in ("date", "meeting", "race", "field", "missed")}
                row.update({"baseline_label": race["baseline"]["label"], "tier": tier,
                            "joint_feasible": result["joint_feasible"],
                            "full_order_feasible": result["full_order_feasible_at_margin"],
                            "baseline_picks": json.dumps(race["baseline"]["picks"]),
                            "oracle_picks": json.dumps(result["best"]["picks"]),
                            "actual_podium": json.dumps(race["actual_podium"], ensure_ascii=False),
                            "support_count": result["equally_best_primary_count"],
                            "nearest_found_l1_fraction": result["nearest_found_l1_fraction"]})
                row.update({key: result["best"][key] for key in ("gold", "good", "pass")})
                row.update(dict(zip(DIMS, result["example_weights"])))
                writer.writerow(row)
    (args.out / "REPORT.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"]["joint_repair"]), flush=True)
    print(f"Report -> {args.out / 'REPORT.md'}", flush=True)


if __name__ == "__main__":
    main()
