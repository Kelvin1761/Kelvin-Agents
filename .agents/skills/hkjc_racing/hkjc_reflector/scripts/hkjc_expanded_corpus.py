#!/usr/bin/env python3
"""HKJC expanded point-in-time corpus — every race in the results database.

Phase 0 of the 2026-10 9D audit. The scored corpus (Logic.json) is ~360 races,
so Good moves ~0.3pp per race and most candidates sit inside the noise floor.
The results database has ~2,000 races (2024-09 → now) with, per runner:
draw, carried weight, body weight, jockey, trainer, finishing position, beaten
margin, running positions, finish time, and the stewards' incident text.

This script rebuilds, for every runner, features that depend **only on races
strictly before the race date** (point-in-time), and writes one CSV row per
runner. It never uses the race's own result, incident text or odds as a
feature; odds are kept in a clearly named `market_*` column for benchmarking
only and must not enter a model.

What it can rebuild: recent form, margins, consistency, layoff, body-weight
change, distance change (first time up / down), same-distance and
same-course-distance record, class move, carried weight within the field,
running style (first-call position), jockey change taxonomy, stable transfer,
J/T as-of strike rates, forgiveness of previous runs (from stewards' text).

What it cannot: sectional splits, trackwork, form-line opponent strength,
official rating (only the class band), gear.

    python3 hkjc_expanded_corpus.py --out corpus.csv
    python3 hkjc_expanded_corpus.py screen corpus.csv          # within-race AUC table
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

BRAND_RE = re.compile(r"\(([A-Z]\d{3})\)")
DIST_RE = re.compile(r"(\d{3,4})米")
CLASS_RE = re.compile(r"(第[一二三四五]班|一級賽|二級賽|三級賽|國際一級賽|國際二級賽|國際三級賽|新馬賽|條件限制)")
BAND_RE = re.compile(r"\((\d+)-(\d+)\)")
CLASS_LEVEL = {"第五班": 5, "第四班": 4, "第三班": 3, "第二班": 2, "第一班": 1,
               "三級賽": 0.5, "二級賽": 0.3, "一級賽": 0.1,
               "國際三級賽": 0.5, "國際二級賽": 0.3, "國際一級賽": 0.1}

# Stewards' wording → forgiveness severity of THAT run (used only for later runs).
# Severe: the run is not evidence of ability. Mild: partial excuse.
FORGIVE_SEVERE = ("流鼻血", "心律不正常", "跛行", "不良於行", "呼吸", "失蹄", "被嚴重碰撞", "收慢至幾乎停下",
                  "幾乎跌倒", "受嚴重阻礙", "被夾", "勒避", "受困", "未能望空", "無法望空", "空位不足",
                  "出閘時失去平衡", "出閘時跌", "獸醫", "拉傷", "受傷")
FORGIVE_MILD = ("出閘笨拙", "出閘緩慢", "受擠迫", "被碰撞", "互相碰撞", "受阻", "收慢", "搶口", "走外疊",
                "沒有遮擋下走外疊", "斜跑", "外閃", "內閃", "窘境", "蝕位")


def forgiveness(text: str) -> float:
    """0 = clean run, 0.5 = mild excuse, 1 = severe (not ability evidence)."""
    if not text:
        return 0.0
    if any(token in text for token in FORGIVE_SEVERE):
        return 1.0
    if any(token in text for token in FORGIVE_MILD):
        return 0.5
    return 0.0


def _num(value, default=None):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _lbw(value) -> float | None:
    text = str(value or "").strip()
    if text in ("---", "-", ""):
        return 0.0
    if any(word in text for word in ("頭", "頸", "鼻")):
        return 0.2
    total = 0.0
    for part in text.split("-"):
        if "/" in part:
            a, b = part.split("/")
            total += _num(a, 0) / max(_num(b, 1), 1)
        else:
            total += _num(part, 0)
    return total


def _incidents(report) -> dict[str, str]:
    """Split the per-race stewards' text into {brand: text}.

    Most files store one flat string; a few (e.g. 2026-05-03) store a list of
    {horse_name, comment} rows.
    """
    out = {}
    if isinstance(report, list):
        for item in report:
            brand = BRAND_RE.search(str((item or {}).get("horse_name") or ""))
            if brand:
                out[brand.group(1)] = str(item.get("comment") or "")
        return out
    if not report:
        return out
    # Format: "<pos> <horse_no> <name> (<brand>) text ... <pos> <horse_no> ..."
    for match in re.finditer(r"(\d+)\s+(\d+)\s+\S+\s*\(([A-Z]\d{3})\)\s*(.*?)(?=\s\d+\s+\d+\s+\S+\s*\([A-Z]\d{3}\)|$)",
                             report, flags=re.S):
        out[match.group(3)] = match.group(4).strip()
    return out


@dataclass
class Run:
    day: str
    venue: str
    track: str
    distance: int | None
    class_level: float | None
    draw: int | None
    field: int
    pos: int | None
    pct: float | None          # finishing percentile, 0 = winner, 1 = last
    lbw: float | None
    first_call_pct: float | None
    carried: float | None
    body: float | None
    jockey: str
    trainer: str
    forgive: float


@dataclass
class History:
    runs: list[Run] = field(default_factory=list)


def _race_meta(race: dict) -> dict:
    header = " ".join(" ".join(str(x) for x in row) for row in (race.get("cumulative_times") or race.get("sectional_times") or []))
    dist = DIST_RE.search(header)
    cls = CLASS_RE.search(header)
    band = BAND_RE.search(header)
    track = "AWT" if ("全天候" in header or "泥地" in header) else "TURF"
    return {
        "distance": int(dist.group(1)) if dist else None,
        "class_name": cls.group(1) if cls else "",
        "class_level": CLASS_LEVEL.get(cls.group(1)) if cls else None,
        "band_hi": int(band.group(1)) if band else None,
        "band_lo": int(band.group(2)) if band else None,
        "track": track,
    }


def load_races(root: Path) -> list[dict]:
    races = []
    for path in sorted(root.glob("hkjc results */*/full_day_results.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in data.items():
            if not str(key).isdigit() or not isinstance(race, dict):
                continue
            day = str(race.get("racedate") or path.parent.name)[:10]
            races.append({"day": day, "race_no": int(race.get("race_no") or key),
                          "venue": race.get("venue") or "", **_race_meta(race),
                          "results": race.get("results") or [],
                          "incidents": _incidents(race.get("incident_report") or "")})
    races.sort(key=lambda r: (r["day"], r["race_no"]))
    return races


def _severe_forgiven(hist: list) -> dict:
    kept = [r for r in hist if r.forgive < 1.0][-3:]
    pct = [r.pct for r in kept if r.pct is not None]
    lbw = [r.lbw for r in kept if r.lbw is not None]
    return {
        "avg3_pct_sev": sum(pct) / len(pct) if pct else None,
        "avg3_lbw_sev": sum(lbw) / len(lbw) if lbw else None,
        "last_clean_pct": kept[-1].pct if kept else None,
    }


def _rate(hits: int, n: int, prior: float, k: float = 20.0) -> float:
    return (hits + k * prior) / (n + k)


def build(root: Path, out: Path) -> int:
    races = load_races(root)
    horses: dict[str, History] = defaultdict(History)
    jockey_stats = defaultdict(lambda: [0, 0])     # places, starts (as-of)
    trainer_stats = defaultdict(lambda: [0, 0])
    trainer_recent = defaultdict(list)              # (day, placed)
    base_place = 3 / 12
    rows_out = 0
    fieldnames = None
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = None
        by_day = defaultdict(list)
        for race in races:
            by_day[race["day"]].append(race)
        for day in sorted(by_day):
            pending_updates = []
            for race in by_day[day]:
                runners = []
                for row in race["results"]:
                    brand = BRAND_RE.search(str(row.get("horse_name") or ""))
                    pos = re.fullmatch(r"(\d+)(?:\s+平頭馬)?", str(row.get("pos") or "").strip())
                    runners.append((row, brand.group(1) if brand else None, int(pos.group(1)) if pos else None))
                finishers = [r for r in runners if r[2]]
                n = len(finishers)
                if n < 4:
                    continue
                carried_field = [_num(r[0].get("actual_wt")) for r in runners if _num(r[0].get("actual_wt"))]
                top_weight = max(carried_field) if carried_field else None
                mean_weight = sum(carried_field) / len(carried_field) if carried_field else None
                for row, brand, pos in runners:
                    if not brand:
                        continue
                    hist = horses[brand].runs
                    jockey = str(row.get("jockey") or "").strip()
                    trainer = str(row.get("trainer") or "").strip()
                    carried = _num(row.get("actual_wt"))
                    body = _num(row.get("horse_wt"))
                    draw = _num(row.get("draw"))
                    last = hist[-1] if hist else None
                    prev3 = hist[-3:]
                    weights = [1.0 - r.forgive for r in prev3]
                    def wmean(values):
                        pairs = [(v, w) for v, w in zip(values, weights) if v is not None and w > 0]
                        tot = sum(w for _, w in pairs)
                        return sum(v * w for v, w in pairs) / tot if tot else None
                    pct_raw = [r.pct for r in prev3]
                    lbw_raw = [r.lbw for r in prev3]
                    dists = [r.distance for r in hist if r.distance]
                    same_dist = [r for r in hist if r.distance == race["distance"]]
                    same_cd = [r for r in same_dist if r.venue == race["venue"] and r.track == race["track"]]
                    jockey_on_horse = [r for r in hist if r.jockey == jockey]
                    j_places, j_starts = jockey_stats[jockey]
                    t_places, t_starts = trainer_stats[trainer]
                    last_j = last.jockey if last else ""
                    lj_places, lj_starts = jockey_stats[last_j] if last_j else (0, 0)
                    j_rate = _rate(j_places, j_starts, base_place)
                    lj_rate = _rate(lj_places, lj_starts, base_place)
                    if not last:
                        jockey_change = "debut"
                    elif jockey == last_j:
                        jockey_change = "same"
                    elif any(r.pct is not None and r.pos and r.pos <= 3 for r in jockey_on_horse):
                        jockey_change = "return_placed"
                    elif j_rate - lj_rate > 0.04:
                        jockey_change = "upgrade"
                    elif lj_rate - j_rate > 0.04:
                        jockey_change = "downgrade"
                    else:
                        jockey_change = "lateral"
                    runs_with_trainer = 0
                    for r in reversed(hist):
                        if r.trainer != trainer:
                            break
                        runs_with_trainer += 1
                    transferred = bool(hist) and runs_with_trainer < len(hist)
                    recent = [p for d, p in trainer_recent[trainer] if (date.fromisoformat(day) - date.fromisoformat(d)).days <= 30]
                    out_row = {
                        "day": day, "season": f"{(int(day[:4]) if int(day[5:7]) >= 8 else int(day[:4]) - 1) % 100:02d}",
                        "race_id": f"{day}|{race['race_no']}", "venue": race["venue"], "track": race["track"],
                        "distance": race["distance"], "class_level": race["class_level"],
                        "band_hi": race["band_hi"], "field": n, "horse": brand,
                        "horse_no": str(row.get("horse_no") or "").strip(),
                        "draw": draw, "draw_pct": (draw - 1) / max(len(runners) - 1, 1) if draw else None,
                        "straight1000": int(race["venue"].startswith("沙田") and race["track"] == "TURF" and race["distance"] == 1000),
                        # --- point-in-time features (only earlier races) ---
                        "starts": len(hist),
                        "days_since": (date.fromisoformat(day) - date.fromisoformat(last.day)).days if last else None,
                        "last_pct": last.pct if last else None,
                        "last_forgive": last.forgive if last else None,
                        "avg3_pct_raw": (sum(p for p in pct_raw if p is not None) / len([p for p in pct_raw if p is not None])) if any(p is not None for p in pct_raw) else None,
                        "avg3_pct_forgiven": wmean(pct_raw),
                        "avg3_lbw_raw": (sum(v for v in lbw_raw if v is not None) / len([v for v in lbw_raw if v is not None])) if any(v is not None for v in lbw_raw) else None,
                        "avg3_lbw_forgiven": wmean(lbw_raw),
                        # Severe excuses only (mild wording is noise on this corpus):
                        # drop the excused run and reach one run further back.
                        **_severe_forgiven(hist),
                        "place_rate_hist": (sum(1 for r in hist if r.pos and r.pos <= 3) / len(hist)) if hist else None,
                        "first_call_avg3": (lambda v: sum(v) / len(v) if v else None)([r.first_call_pct for r in prev3 if r.first_call_pct is not None]),
                        "body_change": (body - last.body) if (body and last and last.body) else None,
                        "carried": carried,
                        "carried_vs_top": (carried - top_weight) if (carried and top_weight) else None,
                        "carried_vs_mean": (carried - mean_weight) if (carried and mean_weight) else None,
                        "dist_change": (race["distance"] - last.distance) if (race["distance"] and last and last.distance) else None,
                        "first_up_in_trip": int(bool(dists) and race["distance"] is not None and race["distance"] > max(dists)),
                        "first_down_in_trip": int(bool(dists) and race["distance"] is not None and race["distance"] < min(dists)),
                        "same_dist_starts": len(same_dist),
                        "same_dist_place_rate": (sum(1 for r in same_dist if r.pos and r.pos <= 3) / len(same_dist)) if same_dist else None,
                        "same_cd_starts": len(same_cd),
                        "same_cd_place_rate": (sum(1 for r in same_cd if r.pos and r.pos <= 3) / len(same_cd)) if same_cd else None,
                        "class_move": (race["class_level"] - last.class_level) if (race["class_level"] is not None and last and last.class_level is not None) else None,
                        "jockey_rate": j_rate, "trainer_rate": _rate(t_places, t_starts, base_place),
                        "trainer_30d_rate": (sum(recent) / len(recent)) if len(recent) >= 5 else None,
                        "jockey_change": jockey_change,
                        "jockey_horse_starts": len(jockey_on_horse),
                        "stable_transfer": int(transferred),
                        "runs_since_transfer": runs_with_trainer if transferred else None,
                        # --- outcome / benchmark only (NOT features) ---
                        "pos": pos, "top3": int(bool(pos and pos <= 3)),
                        "outcome_first_call": str(row.get("running_positions") or "").split()[0] if str(row.get("running_positions") or "").split() else "",
                        "market_win_odds": _num(row.get("win_odds")),
                    }
                    if writer is None:
                        fieldnames = list(out_row)
                        writer = csv.DictWriter(handle, fieldnames=fieldnames)
                        writer.writeheader()
                    writer.writerow(out_row)
                    rows_out += 1
                    first_call = None
                    calls = str(row.get("running_positions") or "").split()
                    if calls and len(calls[0]) <= 2:
                        first_call = (_num(calls[0], 0) - 1) / max(n - 1, 1)
                    pending_updates.append((brand, Run(
                        day=day, venue=race["venue"], track=race["track"], distance=race["distance"],
                        class_level=race["class_level"], draw=int(draw) if draw else None, field=n, pos=pos,
                        pct=((pos - 1) / max(n - 1, 1)) if pos else None, lbw=_lbw(row.get("lbw")),
                        first_call_pct=first_call, carried=carried, body=body, jockey=jockey, trainer=trainer,
                        forgive=forgiveness(race["incidents"].get(brand, "")),
                    ), jockey, trainer, bool(pos and pos <= 3)))
            # Only after the whole day: same-day races never see each other.
            for brand, run, jockey, trainer, placed in pending_updates:
                horses[brand].runs.append(run)
                jockey_stats[jockey][0] += placed
                jockey_stats[jockey][1] += 1
                trainer_stats[trainer][0] += placed
                trainer_stats[trainer][1] += 1
                trainer_recent[trainer].append((day, placed))
    print(f"{len(races)} races, {rows_out} runner rows → {out}", file=sys.stderr)
    return 0


def _within_race_auc(rows: list[dict], feature: str, higher_is_better: bool) -> tuple[float | None, int]:
    by_race = defaultdict(list)
    for row in rows:
        value = row.get(feature)
        if value in (None, ""):
            continue
        by_race[row["race_id"]].append((float(value), int(row["top3"])))
    concordant = total = 0.0
    for items in by_race.values():
        pos = [v for v, y in items if y]
        neg = [v for v, y in items if not y]
        for p in pos:
            for q in neg:
                total += 1
                if p == q:
                    concordant += 0.5
                elif (p > q) == higher_is_better:
                    concordant += 1
    return (concordant / total if total else None), int(total)


def screen(path: Path) -> int:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    features = {
        "last_pct": False, "avg3_pct_raw": False, "avg3_pct_forgiven": False,
        "avg3_lbw_raw": False, "avg3_lbw_forgiven": False, "place_rate_hist": True,
        "days_since": False, "body_change": True, "carried_vs_top": True,
        "first_call_avg3": False, "same_dist_place_rate": True, "same_cd_place_rate": True,
        "class_move": True, "jockey_rate": True, "trainer_rate": True, "trainer_30d_rate": True,
        "draw_pct": False,
    }
    print(f"{'feature':24s} {'AUC':>7s} {'coverage':>9s}")
    for feature, hib in features.items():
        auc, pairs = _within_race_auc(rows, feature, hib)
        cov = sum(1 for r in rows if r.get(feature) not in (None, "")) / max(len(rows), 1)
        print(f"{feature:24s} {auc if auc is None else round(auc, 4)!s:>7s} {cov:9.1%}")
    return 0


CORE_FEATURES = ("avg3_pct_raw", "avg3_lbw_raw", "place_rate_hist", "jockey_rate",
                 "trainer_rate", "draw_pct", "same_dist_place_rate", "carried_vs_top")


def _design(rows, names):
    """Within-race standardised design; missing → race mean (0) + missing flag."""
    import numpy as np

    by_race = defaultdict(list)
    for row in rows:
        by_race[row["race_id"]].append(row)
    races = []
    for race_id, items in by_race.items():
        if sum(int(r["top3"]) for r in items) == 0 or len(items) < 4:
            continue
        cols = []
        for name in names:
            raw = []
            for r in items:
                v = r.get(name)
                try:
                    raw.append(float(v))
                except (TypeError, ValueError):
                    raw.append(math.nan)
            arr = np.array(raw, dtype=float)
            ok = ~np.isnan(arr)
            if ok.sum() >= 2 and arr[ok].std() > 0:
                z = (arr - arr[ok].mean()) / arr[ok].std()
            else:
                z = np.zeros_like(arr)
            z[~ok] = 0.0
            cols.append(z)
            cols.append((~ok).astype(float))
        x = np.vstack(cols).T
        y = np.array([int(r["top3"]) for r in items], dtype=float)
        races.append((items[0]["day"], x, y))
    return races


def _fit(races, l2=1.0, iters=400, lr=0.05):
    """Conditional (within-race softmax) logit, place = any of top-3 treated as positives."""
    import numpy as np

    k = races[0][1].shape[1]
    w = np.zeros(k)
    for _ in range(iters):
        grad = l2 * w
        for _day, x, y in races:
            s = x @ w
            p = np.exp(s - s.max())
            p /= p.sum()
            grad -= x.T @ (y / max(y.sum(), 1) - p)
        w -= lr * grad / len(races)
    return w


def _loglik(races, w):
    import numpy as np

    total = 0.0
    for _day, x, y in races:
        s = x @ w
        logp = s - (s.max() + np.log(np.exp(s - s.max()).sum()))
        total += float((logp * y).sum() / max(y.sum(), 1))
    return total / len(races)


def _auc(races, w):
    concordant = pairs = 0.0
    for _day, x, y in races:
        s = x @ w
        pos, neg = s[y == 1], s[y == 0]
        for p in pos:
            concordant += float((p > neg).sum() + 0.5 * (p == neg).sum())
            pairs += len(neg)
    return concordant / pairs if pairs else float("nan")


def incremental(path: Path, extra: list[str], split: float = 0.7, boot: int = 200) -> int:
    """Out-of-sample gain from adding features on top of the core history model."""
    import numpy as np

    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    days = sorted({r["day"] for r in rows})
    cut = days[int(len(days) * split)]
    base_names = list(CORE_FEATURES)
    results = {}
    for label, names in (("core", base_names), *[(f"core+{e}", base_names + e.split("+")) for e in extra]):
        races = _design(rows, names)
        train = [r for r in races if r[0] < cut]
        test = [r for r in races if r[0] >= cut]
        w = _fit(train)
        results[label] = (w, test, names)
    core_w, core_test, _ = results["core"]
    print(f"train < {cut} ≤ test; test races = {len(core_test)}")
    print(f"{'model':40s} {'AUC':>7s} {'ΔAUC':>8s} {'ΔLL':>9s}  95% CI(ΔLL, race bootstrap)")
    core_auc = _auc(core_test, core_w)
    rng = np.random.default_rng(20261010)
    for label, (w, test, names) in results.items():
        auc = _auc(test, w)
        per_core = np.array([_loglik([r], core_w) for r in core_test])
        per_new = np.array([_loglik([r], w) for r in test])
        diff = per_new - per_core
        boots = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(boot)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        coef = ""
        if label != "core":
            extra_idx = [2 * names.index(n) for n in names[len(CORE_FEATURES):]]
            coef = "  coef=" + ",".join(f"{w[i]:+.3f}" for i in extra_idx)
        print(f"{label:40s} {auc:7.4f} {auc - core_auc:+8.4f} {diff.mean():+9.5f}  [{lo:+.5f}, {hi:+.5f}]{coef}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="build", choices=("build", "screen", "incremental"))
    parser.add_argument("path", nargs="?")
    parser.add_argument("--out")
    parser.add_argument("--results-root")
    parser.add_argument("--extra", action="append", default=[],
                        help="feature (or a+b) to add on top of the core model")
    args = parser.parse_args(argv)
    if args.command == "screen":
        return screen(Path(args.path))
    if args.command == "incremental":
        return incremental(Path(args.path), args.extra)
    import wongchoi_paths

    root = Path(args.results_root) if args.results_root else Path(wongchoi_paths.HK_RACING) / "HKJC_Race_Results_Database"
    return build(root, Path(args.out or "hkjc_expanded_corpus.csv"))


if __name__ == "__main__":
    raise SystemExit(main())
