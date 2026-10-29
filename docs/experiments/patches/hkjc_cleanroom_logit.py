#!/usr/bin/env python3
"""EXP-20261029-21 — clean-room HKJC model: results database + conditional logit.

No hand-tuned rules, no Logic.json, no engine code. Every feature is rebuilt
from `full_day_results.json` using only races strictly before the race day.
Walk-forward: each evaluation day is predicted by a fit on earlier days only.

Output is one JSON line per race in the same shape as `hkjc_eval_harness.py run`
so the two can be judged with `hkjc_eval_harness.py compare`.

    PYTHONDONTWRITEBYTECODE=1 python3 hkjc_cleanroom_logit.py --baseline base.jsonl --out cand.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
for path in (REPO, SCRIPTS, REPO / ".agents/skills/shared_racing"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hkjc_expanded_corpus import BRAND_RE, _lbw, _num, _race_meta  # noqa: E402

TRAIN_FROM = "2024-12-01"
L2 = 1.0
FEATURES = ("avg3_pct", "avg3_lbw", "last_pct", "place_rate", "jockey_rate", "trainer_rate",
            "draw_pct", "draw_pct_hv", "carried_vs_top", "same_dist_rate", "first_call_avg3",
            "log_days_since", "log_starts", "class_move")
POS_RE = re.compile(r"(\d+)(?:\s+平頭馬)?")
NO_START = ("W",)          # WV / WV-A / WX / WX-A / WXNR: withdrawn, never left the gates


def _eb(hits, n, prior, k):
    return (hits + k * prior) / (n + k)


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
            starters = []
            for row in race.get("results") or []:
                code = str(row.get("pos") or "").strip()
                brand = BRAND_RE.search(str(row.get("horse_name") or ""))
                if not code or code.startswith(NO_START) or not brand:
                    continue
                match = POS_RE.fullmatch(code)
                starters.append({"row": row, "brand": brand.group(1),
                                 "pos": int(match.group(1)) if match else None})   # None = PU/UR/FE/DNF/DISQ
            if len(starters) < 4:
                continue
            races.append({"day": day, "race_no": int(race.get("race_no") or key),
                          "venue": str(race.get("venue") or ""), **_race_meta(race), "starters": starters})
    races.sort(key=lambda r: (r["day"], r["race_no"]))
    return races


def build_features(races: list[dict]) -> dict:
    """{(day, race_no): {"rows": [(horse_no, feature dict, top3)], ...}} — point in time."""
    hist = defaultdict(list)                    # brand -> [run dict]
    jockey = defaultdict(lambda: [0, 0])
    trainer = defaultdict(lambda: [0, 0])
    by_day = defaultdict(list)
    for race in races:
        by_day[race["day"]].append(race)
    out = {}
    for day in sorted(by_day):
        updates = []
        for race in by_day[day]:
            n = len(race["starters"])
            carried_all = [_num(s["row"].get("actual_wt")) for s in race["starters"]]
            top = max([c for c in carried_all if c] or [0]) or None
            hv = race["venue"].startswith("跑馬地")
            rows = []
            for s in race["starters"]:
                row, brand, pos = s["row"], s["brand"], s["pos"]
                h = hist[brand]
                last = h[-1] if h else None
                prev3 = h[-3:]
                pcts = [r["pct"] for r in prev3 if r["pct"] is not None]
                lbws = [r["lbw"] for r in prev3 if r["lbw"] is not None]
                calls = [r["call"] for r in prev3 if r["call"] is not None]
                same = [r for r in h if r["distance"] and r["distance"] == race["distance"]]
                jk = str(row.get("jockey") or "").strip()
                tr = str(row.get("trainer") or "").strip()
                draw = _num(row.get("draw"))
                draw_pct = (draw - 1) / max(n - 1, 1) if draw else None
                carried = _num(row.get("actual_wt"))
                f = {
                    "avg3_pct": sum(pcts) / len(pcts) if pcts else None,
                    "avg3_lbw": sum(lbws) / len(lbws) if lbws else None,
                    "last_pct": last["pct"] if last else None,
                    "place_rate": _eb(sum(r["top3"] for r in h), len(h), 0.25, 3) if h else None,
                    "jockey_rate": _eb(*jockey[jk], 0.25, 20),
                    "trainer_rate": _eb(*trainer[tr], 0.25, 20),
                    "draw_pct": draw_pct,
                    "draw_pct_hv": draw_pct * hv if draw_pct is not None else None,
                    "carried_vs_top": carried - top if carried and top else None,
                    "same_dist_rate": _eb(sum(r["top3"] for r in same), len(same), 0.25, 3) if same else None,
                    "first_call_avg3": sum(calls) / len(calls) if calls else None,
                    "log_days_since": math.log(max((date.fromisoformat(day) - date.fromisoformat(last["day"])).days, 1)) if last else None,
                    "log_starts": math.log1p(len(h)),
                    "class_move": (race["class_level"] - last["class_level"])
                    if race["class_level"] is not None and last and last["class_level"] is not None else None,
                }
                top3 = int(bool(pos and pos <= 3))
                rows.append((int(_num(row.get("horse_no"), 0)), f, top3))
                call_tokens = str(row.get("running_positions") or "").split()
                call = (_num(call_tokens[0], 0) - 1) / max(n - 1, 1) if call_tokens and call_tokens[0].isdigit() else None
                updates.append((brand, jk, tr, {
                    "day": day, "distance": race["distance"], "class_level": race["class_level"],
                    "pct": (pos - 1) / max(n - 1, 1) if pos else 1.0,     # DNF = last
                    "lbw": _lbw(row.get("lbw")) if pos else None, "call": call, "top3": top3,
                }))
            out[(day, race["race_no"])] = {"day": day, "rows": rows}
        for brand, jk, tr, run in updates:          # same-day races never see each other
            hist[brand].append(run)
            jockey[jk][0] += run["top3"]; jockey[jk][1] += 1
            trainer[tr][0] += run["top3"]; trainer[tr][1] += 1
    return out


def design(rows) -> np.ndarray:
    cols = []
    for name in FEATURES:
        arr = np.array([math.nan if r[1][name] is None else float(r[1][name]) for r in rows])
        ok = ~np.isnan(arr)
        z = np.zeros_like(arr)
        if ok.sum() >= 2 and arr[ok].std() > 0:
            z[ok] = (arr[ok] - arr[ok].mean()) / arr[ok].std()
        cols += [z, (~ok).astype(float)]
    return np.vstack(cols).T


def pack(races: list[dict]):
    hmax = max(len(r["rows"]) for r in races)
    k = 2 * len(FEATURES)
    X = np.zeros((len(races), hmax, k)); M = np.zeros((len(races), hmax), bool); Y = np.zeros((len(races), hmax))
    for i, race in enumerate(races):
        h = len(race["rows"])
        X[i, :h] = race["X"]; M[i, :h] = True
        y = np.array([r[2] for r in race["rows"]], float)
        Y[i, :h] = y / y.sum()
    return X, M, Y


def fit(X, M, Y, w0):
    def objective(w):
        s = np.where(M, X @ w, -np.inf)
        smax = s.max(axis=1, keepdims=True)
        e = np.where(M, np.exp(s - smax), 0.0)
        z = e.sum(axis=1, keepdims=True)
        logp = np.where(M, s - smax - np.log(z), 0.0)
        p = e / z
        nll = -(Y * logp).sum() + 0.5 * L2 * w @ w
        grad = -np.einsum("rh,rhk->k", Y - p, X) + L2 * w
        return nll, grad
    return minimize(objective, w0, jac=True, method="L-BFGS-B").x


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", required=True, help="hkjc_eval_harness run output (defines races + candidate sets)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--results-root")
    parser.add_argument("--weights-out", help="optional: per-day fitted coefficients (diagnostics)")
    args = parser.parse_args(argv)

    import wongchoi_paths
    from eval_metrics import race_metrics
    from hkjc_eval_harness import RANKING_METRICS

    root = Path(args.results_root) if args.results_root else Path(wongchoi_paths.HK_RACING) / "HKJC_Race_Results_Database"
    feats = build_features(load_races(root))
    train_pool = []
    for key, race in feats.items():
        if race["day"] >= TRAIN_FROM and sum(r[2] for r in race["rows"]) > 0:
            race["X"] = design(race["rows"])
            train_pool.append(race)
    train_pool.sort(key=lambda r: r["day"])

    base = [json.loads(line) for line in Path(args.baseline).read_text(encoding="utf-8").splitlines()]
    base = [b for b in base if "error" not in b]
    w = np.zeros(2 * len(FEATURES))
    weights_log, out_rows, missing = [], [], 0
    for day in sorted({b["date"] for b in base}):
        train = [r for r in train_pool if r["day"] < day]
        w = fit(*pack(train), w)
        weights_log.append({"day": day, "train_races": len(train), "w": dict(zip(FEATURES, w[0::2].round(4).tolist()))})
        for b in (b for b in base if b["date"] == day):
            race = feats.get((day, b["race"]))
            if race is None:
                missing += 1
                continue
            score = dict(zip((r[0] for r in race["rows"]), design(race["rows"]) @ w))
            unscored = [n for n in b["picks"] if n not in score]
            if unscored:
                print(f"  {b['meeting']} R{b['race']}: unscored {unscored}", file=sys.stderr)
            picks = sorted(b["picks"], key=lambda n: (-score.get(n, -1e9), n))
            out_rows.append((b, picks))
        print(f"{day}: train={len(train)}", file=sys.stderr)

    # Actual finishing positions via the same loader the harness uses.
    import rescore_backtest
    from hkjc_eval_harness import _default_root
    meeting_root = _default_root()
    cache = {}
    with open(args.out, "w", encoding="utf-8") as handle:
        for b, picks in out_rows:
            if b["meeting"] not in cache:
                cache[b["meeting"]] = rescore_backtest.load_results(rescore_backtest.find_results_json(meeting_root / b["meeting"]))
            positions = cache[b["meeting"]][b["race"]]
            m = race_metrics(picks, [h for h, p in positions.items() if p <= 3], actual_pos=positions)
            m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
            row = {k: b[k] for k in ("date", "meeting", "race", "venue", "awt", "distance", "field", "meeting_dead_fields")}
            row.update(arm="cleanroom_logit", picks=picks,
                       **{k: m.get(k) for k in ("gold", "gold_strict", "good_positional", "champion", *RANKING_METRICS)})
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    if args.weights_out:
        Path(args.weights_out).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in weights_log) + "\n", encoding="utf-8")
    print(f"wrote {len(out_rows)} races, {missing} baseline races missing from results DB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
