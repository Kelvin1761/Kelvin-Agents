#!/usr/bin/env python3
"""Market-free AU dual-objective performance-figure walk-forward research.

This is a research-only harness.  It does not mutate Race_X_Logic.json or the
production AU Wong Choi scoring matrix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import binomtest
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import joblib


ROOT = Path(__file__).resolve().parents[1]
AU_ROOT = ROOT / "Wong Choi Horse Race Analysis/AU_Racing"
RACE_CACHE = Path("/private/tmp/au_ranking_structural_review_cache.json")
PF_CACHE = AU_ROOT / "AU_PF_Historical_Backfill_Cache_2026-07-13.json"
OUT_JSON = AU_ROOT / "AU_Dual_Objective_Performance_Research_2026-07-13.json"
OUT_MD = AU_ROOT / "AU_Dual_Objective_Performance_Research_2026-07-13.md"
GATE_FILE = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/resources/dual_objective_shadow_gate_v1.json"
MODEL_PACK = Path(os.environ.get(
    "AU_DUAL_MODEL_PACK",
    ROOT / ".agents/skills/au_racing/au_wong_choi_auto/resources/dual_objective_shadow_v1.joblib",
))
MODEL_META = Path(os.environ.get(
    "AU_DUAL_MODEL_META",
    ROOT / ".agents/skills/au_racing/au_wong_choi_auto/resources/dual_objective_shadow_v1_model.json",
))

BASE_KEYS = (
    "stability", "pace_perf", "race_shape", "jockey_trainer",
    "class_weight", "track", "form_line",
)
PROFILE_FIELDS = (
    "raw_sustain", "raw_burst", "std_sustain", "std_burst", "pf_count",
)
METRICS = (
    "top1", "top2_place", "top2_both", "top3_coverage", "top3_exact",
    "top4_coverage", "top4_exact", "top5_exact", "winner_rr",
)


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def raw_targets(run):
    sustained_parts = []
    for key, weight in (("race_time_diff", 0.45), ("l800_delta", 0.30), ("l600_delta", 0.25)):
        value = finite(run.get(key))
        if value is not None:
            sustained_parts.append((value, weight))
    sustained = None
    if sustained_parts:
        sustained = sum(value * weight for value, weight in sustained_parts) / sum(weight for _, weight in sustained_parts)

    l800 = finite(run.get("l800_delta"))
    late_parts = []
    if l800 is not None:
        for key, weight in (("l400_delta", 0.35), ("l200_delta", 0.65)):
            value = finite(run.get(key))
            if value is not None:
                late_parts.append((value - l800, weight))
    burst = None
    if late_parts:
        burst = sum(value * weight for value, weight in late_parts) / sum(weight for _, weight in late_parts)
    return sustained, burst


def context_row(run):
    return {
        "track": str(run.get("track") or "Unknown"),
        "going": str(run.get("going_bucket") or "Unknown"),
        "early_runner_pace": str(run.get("early_runner_pace") or "Unknown"),
        "early_race_pace": str(run.get("early_race_pace") or "Unknown"),
        "distance": finite(run.get("distance")),
        "weight": finite(run.get("weight")),
    }


class PFNormaliser:
    categorical = ("track", "going", "early_runner_pace", "early_race_pace")
    numeric = ("distance", "weight")

    def __init__(self):
        self.models = {}
        self.scales = {}
        self.capabilities = {}

    @staticmethod
    def _rows_to_matrix(rows):
        # ColumnTransformer accepts a list of dicts poorly across sklearn
        # versions, so use a compact object array in a fixed column order.
        columns = PFNormaliser.categorical + PFNormaliser.numeric
        return np.asarray([[row.get(key) for key in columns] for row in rows], dtype=object)

    @classmethod
    def _pipeline(cls):
        cat_indices = list(range(len(cls.categorical)))
        num_indices = list(range(len(cls.categorical), len(cls.categorical) + len(cls.numeric)))
        preprocess = ColumnTransformer([
            ("cat", Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=2)),
            ]), cat_indices),
            ("num", Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]), num_indices),
        ])
        return Pipeline([("preprocess", preprocess), ("ridge", Ridge(alpha=12.0))])

    def fit(self, observations):
        rows = [context_row(run) for run in observations]
        targets = [raw_targets(run) for run in observations]
        matrix = self._rows_to_matrix(rows)
        for index, name in enumerate(("sustain", "burst")):
            keep = [i for i, values in enumerate(targets) if values[index] is not None]
            if len(keep) < 80:
                continue
            x = matrix[keep]
            y = np.asarray([targets[i][index] for i in keep], dtype=float)
            model = self._pipeline()
            model.fit(x, y)
            residual = y - model.predict(x)
            scale = float(np.std(residual))
            self.models[name] = model
            self.scales[name] = max(scale, 0.05)
        return self

    def precompute(self, runs):
        unique = {id(run): run for run in runs}
        for index, target_name in enumerate(("sustain", "burst")):
            selected = []
            values = []
            for run in unique.values():
                raw_value = raw_targets(run)[index]
                if raw_value is not None:
                    selected.append(run)
                    values.append(raw_value)
            if not selected:
                continue
            if target_name in self.models:
                matrix = self._rows_to_matrix([context_row(run) for run in selected])
                expected = self.models[target_name].predict(matrix)
                scores = [-(raw - prediction) / self.scales[target_name] for raw, prediction in zip(values, expected)]
            else:
                scores = [-raw for raw in values]
            for run, score in zip(selected, scores):
                self.capabilities[(id(run), target_name)] = float(score)
        return self

    def capability(self, run, target_name, raw_value):
        if raw_value is None:
            return None
        cached = self.capabilities.get((id(run), target_name))
        if cached is not None:
            return cached
        if target_name not in self.models:
            return -raw_value
        x = self._rows_to_matrix([context_row(run)])
        expected = float(self.models[target_name].predict(x)[0])
        return -(raw_value - expected) / self.scales[target_name]


def cache_horse(pf_payload, race, horse):
    meeting = pf_payload["meetings"].get(race["meeting"], {})
    horses = meeting.get("races", {}).get(str(race["race"]), {})
    direct = horses.get(str(horse["horse_number"]))
    if direct and direct.get("horse_name", "").strip().lower() == horse["horse_name"].strip().lower():
        return direct
    wanted = "".join(ch for ch in horse["horse_name"].lower() if ch.isalnum())
    for item in horses.values():
        candidate = "".join(ch for ch in item.get("horse_name", "").lower() if ch.isalnum())
        if candidate == wanted:
            return item
    return {"horse_name": horse["horse_name"], "runs": []}


def dedup_training_runs(races, pf_payload):
    observations = {}
    for race in races:
        for horse in race["horses"]:
            for run in cache_horse(pf_payload, race, horse).get("runs", []):
                key = (
                    horse.get("horse_slug") or horse["horse_name"].lower(),
                    run.get("run_date"), run.get("track"), run.get("race_number"),
                    run.get("distance"), run.get("weight"),
                )
                observations[key] = run
    return list(observations.values())


def unique_runs(races, pf_payload):
    runs = {}
    for race in races:
        for horse in race["horses"]:
            for run in cache_horse(pf_payload, race, horse).get("runs", []):
                runs[id(run)] = run
    return list(runs.values())


def weighted_average(values):
    values = [value for value in values if value[0] is not None]
    if not values:
        return None
    return sum(value * weight for value, weight in values) / sum(weight for _, weight in values)


def horse_profile(race, horse, pf_payload, normaliser):
    runs = sorted(
        cache_horse(pf_payload, race, horse).get("runs", []),
        key=lambda item: item.get("run_date") or "",
        reverse=True,
    )[:5]
    weights = (1.0, 0.85, 0.70, 0.55, 0.40)
    raw_sustain = []
    raw_burst = []
    std_sustain = []
    std_burst = []
    usable = 0
    for index, run in enumerate(runs):
        sustain, burst = raw_targets(run)
        if sustain is not None or burst is not None:
            usable += 1
        weight = weights[index]
        raw_sustain.append((-sustain if sustain is not None else None, weight))
        raw_burst.append((-burst if burst is not None else None, weight))
        std_sustain.append((normaliser.capability(run, "sustain", sustain), weight))
        std_burst.append((normaliser.capability(run, "burst", burst), weight))
    shrink = usable / (usable + 2.0) if usable else 0.0
    values = {
        "raw_sustain": weighted_average(raw_sustain),
        "raw_burst": weighted_average(raw_burst),
        "std_sustain": weighted_average(std_sustain),
        "std_burst": weighted_average(std_burst),
        "pf_count": math.log1p(usable),
    }
    for key in ("raw_sustain", "raw_burst", "std_sustain", "std_burst"):
        if values[key] is not None:
            values[key] *= shrink
    return values


def augment_races(races, pf_payload, normaliser):
    output = []
    for race in races:
        cloned = dict(race)
        cloned["horses"] = []
        for horse in race["horses"]:
            item = dict(horse)
            item["profile"] = horse_profile(race, horse, pf_payload, normaliser)
            cloned["horses"].append(item)
        output.append(cloned)
    return output


def feature_vector(horse, variant):
    vector = [finite(horse["matrices"].get(key)) for key in BASE_KEYS]
    profile = horse.get("profile", {})
    if variant == "base":
        return vector
    if variant == "raw_combined":
        sustain = finite(profile.get("raw_sustain"))
        burst = finite(profile.get("raw_burst"))
        combined = None if sustain is None and burst is None else np.nanmean([value for value in (sustain, burst) if value is not None])
        return vector + [combined, finite(profile.get("pf_count"))]
    if variant == "std_sustain":
        return vector + [finite(profile.get("std_sustain")), finite(profile.get("pf_count"))]
    if variant == "std_combined":
        sustain = finite(profile.get("std_sustain"))
        burst = finite(profile.get("std_burst"))
        combined = None if sustain is None and burst is None else np.nanmean([value for value in (sustain, burst) if value is not None])
        return vector + [combined, finite(profile.get("pf_count"))]
    if variant == "std_separated":
        return vector + [
            finite(profile.get("std_sustain")), finite(profile.get("std_burst")),
            finite(profile.get("pf_count")),
        ]
    raise ValueError(variant)


def model_pipeline():
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
        ("logit", LogisticRegression(C=0.30, max_iter=2500, random_state=20260713)),
    ])


def fit_place(races, variant):
    x, y, weights = [], [], []
    for race in races:
        race_weight = 1.0 / max(len(race["horses"]), 1)
        for horse in race["horses"]:
            x.append(feature_vector(horse, variant))
            y.append(int(horse["actual_pos"] <= 3))
            weights.append(race_weight)
    model = model_pipeline()
    model.fit(np.asarray(x, dtype=float), y, logit__sample_weight=np.asarray(weights))
    return model


def fit_coverage(races, variant, boundary_weighted=False):
    x, y, weights = [], [], []
    for race in races:
        positives = [horse for horse in race["horses"] if horse["actual_pos"] <= 3]
        negatives = [horse for horse in race["horses"] if horse["actual_pos"] > 3]
        baseline_rank = {
            horse["horse_number"]: rank
            for rank, horse in enumerate(sorted(race["horses"], key=lambda item: -item["ability"]), start=1)
        }
        for positive in positives:
            p = np.asarray(feature_vector(positive, variant), dtype=float)
            for negative in negatives:
                n = np.asarray(feature_vector(negative, variant), dtype=float)
                x.extend((p - n, n - p))
                y.extend((1, 0))
                weight = 1.0
                if boundary_weighted:
                    # Structural training emphasis on the exact Top4 boundary:
                    # rescue placegetters outside the baseline four and reject
                    # non-placegetters occupying baseline Top4 slots.
                    weight += 1.5 * (baseline_rank[positive["horse_number"]] > 4)
                    weight += 1.0 * (baseline_rank[negative["horse_number"]] <= 4)
                weights.extend((weight, weight))
    model = model_pipeline()
    model.fit(np.asarray(x, dtype=float), y, logit__sample_weight=np.asarray(weights))
    return model


def fit_coverage_boundary(races, variant):
    return fit_coverage(races, variant, boundary_weighted=True)


def distance_family(race):
    label = str(race.get("distance") or "")
    if label.startswith("Sprint"):
        return "Sprint <=1400m"
    if label.startswith("Middle"):
        return "Middle 1401-1800m"
    if label.startswith("Staying"):
        return "Staying 1801m+"
    return "Unknown"


def predict_model(model, race, variant):
    x = np.asarray([feature_vector(horse, variant) for horse in race["horses"]], dtype=float)
    return model.predict_proba(x)[:, 1]


def distance_models(train, variant, fitter):
    global_model = fitter(train, variant)
    local = {}
    counts = {}
    for bucket in sorted({distance_family(race) for race in train}):
        subset = [race for race in train if distance_family(race) == bucket]
        counts[bucket] = len(subset)
        if len(subset) >= 60:
            local[bucket] = fitter(subset, variant)
    return global_model, local, counts


def predict_distance(models, race, variant):
    global_model, local, counts = models
    global_score = predict_model(global_model, race, variant)
    bucket = distance_family(race)
    model = local.get(bucket)
    if model is None:
        return global_score
    local_score = predict_model(model, race, variant)
    n = counts.get(bucket, 0)
    local_weight = min(0.75, n / (n + 80.0))
    return local_weight * local_score + (1.0 - local_weight) * global_score


def race_metric_row(race, scores):
    ranked = [
        horse for _, horse in sorted(
            zip(scores, race["horses"]),
            key=lambda item: (-float(item[0]), int(item[1]["horse_number"])),
        )
    ]
    positions = [int(horse["actual_pos"]) for horse in ranked]
    winner_rank = positions.index(1) + 1
    top2_places = sum(position <= 3 for position in positions[:2])
    top3_places = sum(position <= 3 for position in positions[:3])
    top4_places = sum(position <= 3 for position in positions[:4])
    return {
        "top1": float(positions[0] == 1),
        "top2_place": top2_places / 2.0,
        "top2_both": float(top2_places == 2),
        "top3_coverage": top3_places / 3.0,
        "top3_exact": float(top3_places == 3),
        "top4_coverage": top4_places / 3.0,
        "top4_exact": float(top4_places == 3),
        "top5_exact": float(sum(position <= 3 for position in positions[:5]) == 3),
        "winner_rr": 1.0 / winner_rank,
        "track": race["track"],
        "distance": race["distance"],
        "condition": race["condition"],
        "date": race["date"],
    }


def mean_metrics(rows):
    return {metric: float(np.mean([row[metric] for row in rows])) for metric in METRICS}


def paired_stats(candidate, baseline, samples=4000):
    rng = np.random.default_rng(20260713)
    output = {}
    for metric in METRICS:
        deltas = np.asarray([c[metric] - b[metric] for c, b in zip(candidate, baseline)], dtype=float)
        n = len(deltas)
        draws = rng.integers(0, n, size=(samples, n))
        boot = deltas[draws].mean(axis=1)
        nonzero = deltas[deltas != 0]
        sign_p = 1.0
        if len(nonzero):
            positives = int(np.sum(nonzero > 0))
            sign_p = float(binomtest(positives, len(nonzero), 0.5).pvalue)
        output[metric] = {
            "delta": float(np.mean(deltas)),
            "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
            "paired_sign_p": sign_p,
        }
    return output


def segment_stats(candidate, baseline, key, min_races=10):
    groups = defaultdict(list)
    for candidate_row, baseline_row in zip(candidate, baseline):
        groups[candidate_row[key]].append((candidate_row, baseline_row))
    output = {}
    for value, pairs in sorted(groups.items()):
        if len(pairs) < min_races:
            continue
        output[value] = {
            "races": len(pairs),
            "top1_delta": float(np.mean([a["top1"] - b["top1"] for a, b in pairs])),
            "top2_place_delta": float(np.mean([a["top2_place"] - b["top2_place"] for a, b in pairs])),
            "top4_exact_delta": float(np.mean([a["top4_exact"] - b["top4_exact"] for a, b in pairs])),
            "top4_coverage_delta": float(np.mean([a["top4_coverage"] - b["top4_coverage"] for a, b in pairs])),
        }
    return output


def run_fold(train_raw, test_raw, pf_payload):
    observations = dedup_training_runs(train_raw, pf_payload)
    normaliser = PFNormaliser().fit(observations)
    normaliser.precompute(unique_runs(train_raw + test_raw, pf_payload))
    train = augment_races(train_raw, pf_payload, normaliser)
    test = augment_races(test_raw, pf_payload, normaliser)

    place_models = {
        name: fit_place(train, variant)
        for name, variant in (
            ("place_base", "base"),
            ("place_raw_combined", "raw_combined"),
            ("place_std_sustain", "std_sustain"),
            ("place_std_combined", "std_combined"),
            ("place_std_separated", "std_separated"),
        )
    }
    coverage_models = {
        "coverage_base": fit_coverage(train, "base"),
        "coverage_std_separated": fit_coverage(train, "std_separated"),
        "coverage_boundary_base": fit_coverage_boundary(train, "base"),
        "coverage_boundary_std": fit_coverage_boundary(train, "std_separated"),
    }
    place_distance = distance_models(train, "std_separated", fit_place)
    coverage_distance = distance_models(train, "std_separated", fit_coverage)

    candidates = defaultdict(list)
    for race in test:
        candidates["baseline"].append(race_metric_row(race, [horse["ability"] for horse in race["horses"]]))
        for name, model in place_models.items():
            candidates[name].append(race_metric_row(race, predict_model(model, race, {
                "place_base": "base",
                "place_raw_combined": "raw_combined",
                "place_std_sustain": "std_sustain",
                "place_std_combined": "std_combined",
                "place_std_separated": "std_separated",
            }[name])))
        for name, model in coverage_models.items():
            variant = "base" if name in {"coverage_base", "coverage_boundary_base"} else "std_separated"
            candidates[name].append(race_metric_row(race, predict_model(model, race, variant)))
        candidates["place_distance"].append(race_metric_row(race, predict_distance(place_distance, race, "std_separated")))
        candidates["coverage_distance"].append(race_metric_row(race, predict_distance(coverage_distance, race, "std_separated")))
    diagnostics = {
        "training_races": len(train),
        "test_races": len(test),
        "normaliser_unique_runs": len(observations),
        "place_distance_counts": place_distance[2],
        "coverage_distance_counts": coverage_distance[2],
    }
    return dict(candidates), diagnostics


def merge_rows(target, source):
    for candidate, rows in source.items():
        target[candidate].extend(rows)


def choose_models(dev_rows):
    baseline = mean_metrics(dev_rows["baseline"])
    place_names = [name for name in dev_rows if name.startswith("place_")]
    viable_place = []
    for name in place_names:
        metrics = mean_metrics(dev_rows[name])
        if metrics["top1"] >= baseline["top1"] - 0.005:
            viable_place.append((metrics["top2_place"], metrics["top2_both"], metrics["top1"], name))
    place = max(viable_place)[-1] if viable_place else "baseline"

    coverage_names = [name for name in dev_rows if name.startswith("coverage_")]
    viable_coverage = []
    for name in coverage_names:
        metrics = mean_metrics(dev_rows[name])
        if metrics["top4_coverage"] >= baseline["top4_coverage"] - 0.002:
            viable_coverage.append((metrics["top4_exact"], metrics["top4_coverage"], metrics["top5_exact"], name))
    coverage = max(viable_coverage)[-1] if viable_coverage else "baseline"
    return place, coverage


def fold_signs(fold_rows, candidate, metric):
    signs = []
    for rows in fold_rows:
        if candidate not in rows:
            continue
        delta = mean_metrics(rows[candidate])[metric] - mean_metrics(rows["baseline"])[metric]
        signs.append(delta)
    return {
        "nonnegative": sum(value >= -1e-12 for value in signs),
        "positive": sum(value > 1e-12 for value in signs),
        "folds": len(signs),
        "deltas": signs,
    }


def pct(value):
    return f"{value * 100:.2f}%"


def pp(value):
    return f"{value * 100:+.2f}pp"


def render_report(payload):
    lines = [
        "# AU Wong Choi：雙目標 Performance Figure 結構研究",
        "",
        f"生成時間：{payload['generated_at']}",
        "",
        "> Research-only；完全不使用 market odds，亦無修改 production 7D rating、Race_X_Logic.json 或正式排名。",
        "",
        "## 資料及防洩漏 QA",
        "",
        f"- Benchmark：{payload['dataset']['races']} 場、{payload['dataset']['horses']} 匹 runners。",
        f"- 統一 PF cache：{payload['pf_cache']['meeting_count']} meetings、{payload['pf_cache']['race_count']} 場 form guides、{payload['pf_cache']['run_count']} 個舊跑績 PF runs。",
        f"- 日期洩漏拒絕數：{payload['pf_cache']['leakage_rejections']}；cache 標記 `pre_race_only=true`。",
        f"- Development：{payload['split']['development_test_races']} 場（4 個 expanding folds）；final holdout：{payload['split']['final_holdout_races']} 場。",
        "",
        "## Development ablation（只用嚟揀結構）",
        "",
        "| Candidate | Top1 | Top2 place | Top2 both | Top4 exact | Top4 coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in payload["development"]["metrics"].items():
        lines.append(
            f"| {name} | {pct(metrics['top1'])} | {pct(metrics['top2_place'])} | "
            f"{pct(metrics['top2_both'])} | {pct(metrics['top4_exact'])} | {pct(metrics['top4_coverage'])} |"
        )
    lines.extend([
        "",
        f"Development 鎖定 Place model：`{payload['selected']['place']}`；Coverage model：`{payload['selected']['coverage']}`。",
        "",
        "## Final 20% holdout（一次性驗證）",
        "",
        "| Ranking | Top1 | Top2 place | Top2 both | Top3 coverage | Top4 exact | Top4 coverage | Top5 exact |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for name in ("baseline", payload["selected"]["place"], payload["selected"]["coverage"]):
        metrics = payload["final"]["metrics"][name]
        lines.append(
            f"| {name} | {pct(metrics['top1'])} | {pct(metrics['top2_place'])} | {pct(metrics['top2_both'])} | "
            f"{pct(metrics['top3_coverage'])} | {pct(metrics['top4_exact'])} | {pct(metrics['top4_coverage'])} | {pct(metrics['top5_exact'])} |"
        )

    lines.extend(["", "## 相對 baseline 統計", ""])
    for role in ("place", "coverage"):
        name = payload["selected"][role]
        stats = payload["final"]["paired"][name]
        focus = "top2_place" if role == "place" else "top4_exact"
        item = stats[focus]
        lines.append(
            f"- `{name}` / `{focus}`：{pp(item['delta'])}，95% paired bootstrap CI "
            f"[{pp(item['ci95'][0])}, {pp(item['ci95'][1])}]，paired sign p={item['paired_sign_p']:.4f}。"
        )
    lines.extend([
        "",
        "## 獨立 ablation 結果",
        "",
        "| 測試 | Development | Final holdout | 決定 |",
        "|---|---:|---:|---|",
    ])
    for name, item in payload["ablations"].items():
        lines.append(
            f"| {name} ({item['focus_metric']}) | {pp(item['development_delta'])} | "
            f"{pp(item['final_delta'])} | {item['decision']} |"
        )
    lines.extend([
        "",
        "## 結構結論",
        "",
        "- `place_base` 量度只重估現有 matrix；`place_raw_combined` 加未標準化時間；`place_std_combined` 測試環境標準化；`place_std_separated` 再將持續速度與末段爆發分開。",
        "- `coverage_*` 使用 race-wise pairwise learning，直接學習將實際前三名排喺非前三名之前，目標係 Top4 trifecta coverage，並非人工 swap 或微調名次。",
        "- `*_distance` 為 sprint／middle／staying 分開模型，再按樣本量 shrink 回 global model；只有 development 通過先會被鎖定入 final。",
        "- 結果建議將 `place_base` 進入 forward shadow；Top4 同時保留 `coverage_base` 同 `coverage_std_separated` 兩個凍結候選。PF 版 final coverage 訊號較好，但佢唔係 development 預先鎖定 winner，所以唔可直接當主模型。",
        "",
        "## Shadow 升級主模型閘門",
        "",
        "升級唔應由單一 meeting 決定。候選先要通過 archive development + untouched holdout，之後至少累積 150 場 forward shadow、3 個或以上 tracks，而且三類途程各至少 30 場。Place Rating 要 Top2 place +2pp、95% CI 下限大於 0、Top1 不倒退；Coverage Rating 要 Top4 exact／coverage 不倒退且至少一項有正 CI；4 個時間 blocks 至少 3 個非負，任何足夠樣本 segment 不可出現重大倒退。最後先 canary，再正式 promotion；rolling 50-race 跌穿 rollback threshold 就自動退回 baseline。",
        "",
        f"詳細機器可讀結果：`{OUT_JSON.name}`",
        f"升級／rollback 機器閥門：`{GATE_FILE.name}`",
    ])
    return "\n".join(lines) + "\n"


def export_frozen_model_pack(races, pf_payload):
    observations = dedup_training_runs(races, pf_payload)
    normaliser = PFNormaliser().fit(observations)
    normaliser.precompute(unique_runs(races, pf_payload))
    augmented = augment_races(races, pf_payload, normaliser)
    pack = {
        "version": "AU_DUAL_OBJECTIVE_SHADOW_V1",
        "trained_through": max(race["date"] for race in races),
        "training_races": len(races),
        "training_runners": sum(len(race["horses"]) for race in races),
        "market_inputs": False,
        "matrix_order": list(BASE_KEYS),
        "place_model": fit_place(augmented, "base"),
        "coverage_7d_model": fit_coverage(augmented, "base"),
        "coverage_pf_model": fit_coverage(augmented, "std_separated"),
        "pf_normaliser": {
            "sustain_model": normaliser.models.get("sustain"),
            "sustain_scale": normaliser.scales.get("sustain", 1.0),
            "burst_model": normaliser.models.get("burst"),
            "burst_scale": normaliser.scales.get("burst", 1.0),
        },
        "profile_spec": {
            "max_runs": 5,
            "recency_weights": [1.0, 0.85, 0.70, 0.55, 0.40],
            "shrinkage_prior_runs": 2.0,
        },
    }
    joblib.dump(pack, MODEL_PACK, compress=3)
    digest = hashlib.sha256(MODEL_PACK.read_bytes()).hexdigest()
    metadata = {
        key: pack[key]
        for key in (
            "version", "trained_through", "training_races", "training_runners",
            "market_inputs", "matrix_order", "profile_spec",
        )
    }
    metadata.update({
        "model_file": MODEL_PACK.name,
        "sha256": digest,
        "generator": str(Path(__file__).relative_to(ROOT)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    MODEL_META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=int, default=4000)
    parser.add_argument("--export-model-pack", action="store_true")
    args = parser.parse_args()
    race_payload = json.loads(RACE_CACHE.read_text(encoding="utf-8"))
    pf_payload = json.loads(PF_CACHE.read_text(encoding="utf-8"))
    races = sorted(race_payload["races"], key=lambda race: (race["date"], race["meeting"], race["race"]))
    n = len(races)
    cut40, cut50, cut60, cut70, cut80 = [int(n * value) for value in (0.40, 0.50, 0.60, 0.70, 0.80)]
    folds = ((0, cut40, cut50), (0, cut50, cut60), (0, cut60, cut70), (0, cut70, cut80))

    dev_rows = defaultdict(list)
    dev_fold_rows = []
    diagnostics = []
    for _, train_end, test_end in folds:
        rows, info = run_fold(races[:train_end], races[train_end:test_end], pf_payload)
        merge_rows(dev_rows, rows)
        dev_fold_rows.append(rows)
        diagnostics.append(info)
    selected_place, selected_coverage = choose_models(dev_rows)

    final_rows, final_info = run_fold(races[:cut80], races[cut80:], pf_payload)
    final_metrics = {name: mean_metrics(rows) for name, rows in final_rows.items()}
    paired = {
        name: paired_stats(rows, final_rows["baseline"], samples=args.bootstrap)
        for name, rows in final_rows.items() if name != "baseline"
    }
    dev_metrics = {name: mean_metrics(rows) for name, rows in dev_rows.items()}

    def ablation(candidate, reference, metric, decision):
        return {
            "candidate": candidate,
            "reference": reference,
            "focus_metric": metric,
            "development_delta": dev_metrics[candidate][metric] - dev_metrics[reference][metric],
            "final_delta": final_metrics[candidate][metric] - final_metrics[reference][metric],
            "decision": decision,
        }

    ablations = {
        "PF backfill + separated PF versus 7D-only Place": ablation(
            "place_std_separated", "place_base", "top2_place", "reject_for_place"
        ),
        "context standardisation versus raw combined time": ablation(
            "place_std_combined", "place_raw_combined", "top2_place", "no_consistent_gain"
        ),
        "separate sustained/burst versus combined time": ablation(
            "place_std_separated", "place_std_combined", "top2_place", "diagnostic_only"
        ),
        "sustained-speed-only versus 7D-only Place": ablation(
            "place_std_sustain", "place_base", "top2_place", "not_selected"
        ),
        "three distance matrices versus global Place": ablation(
            "place_distance", "place_std_separated", "top2_place", "reject_no_robust_advantage"
        ),
        "three distance matrices versus global Coverage": ablation(
            "coverage_distance", "coverage_std_separated", "top4_exact", "reject"
        ),
        "boundary-weighted Top4 loss versus pairwise Coverage": ablation(
            "coverage_boundary_base", "coverage_base", "top4_exact", "reject"
        ),
        "separated PF versus 7D-only Coverage": ablation(
            "coverage_std_separated", "coverage_base", "top4_coverage", "secondary_forward_shadow"
        ),
    }
    segment = {}
    segment_candidates = {selected_place, selected_coverage, "coverage_std_separated"} - {"baseline"}
    for name in segment_candidates:
        segment[name] = {
            key: segment_stats(final_rows[name], final_rows["baseline"], key)
            for key in ("distance", "condition", "track")
        }

    payload = {
        "version": "AU_DUAL_OBJECTIVE_PF_RESEARCH_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "market_inputs_used": False,
        "production_changed": False,
        "dataset": {
            "races": n,
            "horses": sum(len(race["horses"]) for race in races),
            "first_date": races[0]["date"],
            "last_date": races[-1]["date"],
        },
        "pf_cache": {key: pf_payload[key] for key in (
            "meeting_count", "race_count", "horse_count", "run_count", "leakage_rejections",
        )},
        "split": {
            "development_test_races": sum(end - start for _, start, end in folds),
            "development_folds": [{"train_end": start, "test_end": end} for _, start, end in folds],
            "final_train_races": cut80,
            "final_holdout_races": n - cut80,
            "final_holdout_start": races[cut80]["date"],
        },
        "development": {
            "metrics": dev_metrics,
            "diagnostics": diagnostics,
        },
        "ablations": ablations,
        "selected": {"place": selected_place, "coverage": selected_coverage},
        "shadow_entry": {
            "place_base": "eligible_for_frozen_forward_shadow_not_main",
            "coverage_base": "eligible_for_frozen_forward_shadow_not_main",
            "coverage_std_separated": "eligible_as_secondary_frozen_forward_shadow_not_main",
            "production_main": "unchanged_until_forward_gate_passes",
        },
        "final": {
            "metrics": final_metrics,
            "paired": paired,
            "segments": segment,
            "diagnostics": final_info,
            "fold_consistency": {
                selected_place: {
                    "top1": fold_signs(dev_fold_rows, selected_place, "top1"),
                    "top2_place": fold_signs(dev_fold_rows, selected_place, "top2_place"),
                },
                selected_coverage: {
                    "top4_exact": fold_signs(dev_fold_rows, selected_coverage, "top4_exact"),
                    "top4_coverage": fold_signs(dev_fold_rows, selected_coverage, "top4_coverage"),
                },
            },
        },
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_report(payload), encoding="utf-8")
    model_metadata = export_frozen_model_pack(races, pf_payload) if args.export_model_pack else None
    print(json.dumps({
        "selected": payload["selected"],
        "final_baseline": final_metrics["baseline"],
        "final_place": final_metrics[selected_place],
        "final_coverage": final_metrics[selected_coverage],
        "json": str(OUT_JSON),
        "markdown": str(OUT_MD),
        "model_pack": model_metadata,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
