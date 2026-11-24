"""EXP-20261124-61: frozen forward test of a weekly recalibration layer on the published p_final.

The published probability p_final (MS, nba_engine:ms:a140747bfae0c724) runs low in the middle and high at
the top (EXP-20261124-70). The candidate policy is a recalibration layer refitted every week:

    logit p = a_stat + b*logit(p_final) + c*logit(m) + d*logit(m)^2,   m = 1/price_at_model
    (p_final and m clipped to [0.02, 0.98] before the logit)

Arms (all scored on the same legs; nothing here touches the engine, a bet, or a published number):
  RW   primary. Refit each week (Monday..Sunday of target_date) on every MS leg with target_date before
       that Monday, from FIT_START on. The fit for a week therefore exists before the week starts.
  R2F  the same layer with coefficients frozen below (fitted once on 2026-11-05..11-24).
  R1W  weekly refit of the plain recalibration a_stat + b*logit(p_final), to show how much is the price term.
  MKT  weekly refit of the market alone, a_stat + c*logit(m) + d*logit(m)^2: on 11-12..11-24 it matched R2
       (R2 - MKT +0.0001), i.e. p_final added nothing over a well de-vigged price. RW - MKT says whether it does.

Legs: first pre-tip `production` model_obs of each (target_date, game, player, market, line) whose
probability_model_id is MS_ID, joined to a non-void ledger settlement. 11-19 has no production run.
If a forward day carries any other probability_model_id (p_final changed, e.g. MS2 adopted) the
population stops before that day, the test is judged at once on what it has (never a PASS) and the
result says `interrupted`, so the tracker reports it instead of waiting forever.
Weeks are cut on target_date: a Monday's games are published at 21:00 on the Sunday, after every earlier
target day has finished and settled, so "target_date < Monday" is what was known when that week began.

Look (judged once, frozen): >= 14 target days and >= 10,000 legs from START on, whole days up to the day
both are reached. PASS if the day-clustered bootstrap 95% CI upper bound of mean log-loss(RW) - mean
log-loss(p_final) is below 0. 2,000 draws, seed 20261125. Secondary deltas are reported, never judged.

Pure standard library on purpose: the scheduler and dashboard interpreters are not guaranteed numpy.

usage:  python3 evaluate.py status | evaluate [--force] | dashboard
Protocol: docs/experiments/EXP-20261124-61-nba-weekly-recalibration-forward-protocol.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EXPERIMENT = "EXP-20261124-61"
TEST = "RC"
MS_ID = "nba_engine:ms:a140747bfae0c724"
FIT_START = "2026-11-05"      # first day of the MS engine
START = "2026-11-25"          # first forward target day (no ledger file existed when this was frozen)
CHECKPOINT = {"days": 14, "flagged_legs": 10000}
SEED, DRAWS = 20261125, 2000
DASHBOARD_DRAWS = 500         # the running view only; the verdict uses DRAWS
FIT_VERSION = 1               # part of the fit-cache key
STATS = ("pts", "reb", "ast", "fg3m")
CLIP = (0.02, 0.98)
L2 = 1e-3
# R2 fitted once on 2026-11-05..2026-11-24 (19 MS days, 11-19 missing) with fit() below; never moves.
LEDGER = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "ledger"
REPORTS = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports"


def _logit(p: float) -> float:
    p = min(max(p, CLIP[0]), CLIP[1])
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def _loss(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1 - p)


# ---------------------------------------------------------------- legs from the ledger
def day_legs(path: Path) -> list[dict]:
    models, settled = {}, {}
    with path.open(encoding="utf-8") as handle:
        for text in handle:
            if '"model_obs"' in text:
                try:
                    r = json.loads(text)
                except ValueError:
                    continue
                if (r.get("row_type") != "model_obs" or r.get("snapshot_role") != "production"
                        or r.get("post_tip") is True or r.get("p_final") is None):
                    continue
                k = (r["game_tag"], r["player"], r["market"], float(r["line"]))
                if k not in models or r["recorded_at"] < models[k]["recorded_at"]:
                    models[k] = r
            elif '"settlement"' in text:
                try:
                    r = json.loads(text)
                except ValueError:
                    continue
                if r.get("row_type") == "settlement":
                    settled[(r["game_tag"], r["player"], r["market"], float(r["line"]))] = r
    out = []
    for k, m in models.items():
        s = settled.get(k)
        try:
            price, pf = float(m.get("price_at_model")), float(m["p_final"])
        except (TypeError, ValueError):
            continue
        if not s or s.get("outcome") == "void" or s.get("y") not in (0, 1) or price <= 1 or m["market"] not in STATS:
            continue
        out.append({"d": path.stem, "s": m["market"], "pf": pf, "m": 1 / price, "y": int(s["y"]),
                    "id": m.get("probability_model_id")})
    return out


def legs(ledger: Path | None = None, cache_dir: Path | None = None) -> list[dict]:
    """Every leg from FIT_START on; a day is cached against its ledger file's size and mtime."""
    ledger = Path(ledger or LEDGER)
    cache_path = Path(cache_dir or REPORTS) / f"{EXPERIMENT}-legs-cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    out, fresh = [], {}
    for path in sorted(ledger.glob("????-??-??.jsonl")):
        if path.stem < FIT_START:
            continue
        st = path.stat()
        stamp = [st.st_size, st.st_mtime_ns]
        entry = cache.get(path.stem)
        if not entry or entry.get("stamp") != stamp:
            entry = {"stamp": stamp, "legs": day_legs(path)}
        fresh[path.stem] = entry
        out.extend(entry["legs"])
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(fresh), encoding="utf-8")
        except OSError:
            pass
    return out


# ---------------------------------------------------------------- the layer
def features(leg: dict, form: str) -> list[float]:
    x = [1.0 if leg["s"] == s else 0.0 for s in STATS]
    if form == "MKT":
        lm = _logit(leg["m"])
        return x + [lm, lm * lm]
    x += [_logit(leg["pf"])]
    if form == "R2":
        lm = _logit(leg["m"])
        x += [lm, lm * lm]
    return x


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit(train: list[dict], form: str) -> list[float]:
    """L2-penalised logistic regression by Newton; starts at the identity (weight 1 on column 4)."""
    k = len(features({"s": STATS[0], "pf": 0.5, "m": 0.5}, form))
    w = [0.0] * k
    w[4] = 1.0
    if not train:  # nothing to learn from: the identity (p_final, or the raw market for MKT)
        return w
    X = [features(r, form) for r in train]
    y = [r["y"] for r in train]
    for _ in range(50):
        g = [-L2 * v for v in w]
        H = [[L2 if i == j else 0.0 for j in range(k)] for i in range(k)]
        for x, yy in zip(X, y):
            p = _sigmoid(sum(a * b for a, b in zip(x, w)))
            q = p * (1 - p)
            for i in range(k):
                g[i] += (yy - p) * x[i]
                xi = x[i] * q
                if xi:
                    row = H[i]
                    for j in range(k):
                        row[j] += xi * x[j]
        step = _solve(H, g)
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return w


def predict(leg: dict, w: list[float], form: str) -> float:
    return _sigmoid(sum(a * b for a, b in zip(features(leg, form), w)))


def monday(day: str) -> str:
    d = date.fromisoformat(day)
    return (d - timedelta(days=d.weekday())).isoformat()


# ---------------------------------------------------------------- forward population
def forward(rows: list[dict]) -> tuple[list[dict], str | None]:
    """Forward legs (START on, MS only) and the first day a different model id appeared, if any."""
    other = sorted({r["d"] for r in rows if r["d"] >= START and r["id"] != MS_ID})
    stop = other[0] if other else None
    return [r for r in rows if r["d"] >= START and r["id"] == MS_ID and (stop is None or r["d"] < stop)], stop


def score(rows: list[dict], fwd: list[dict], cache: dict | None = None) -> list[dict]:
    """Attach every arm's probability to each forward leg.

    `cache` (optional, mutated) maps a hash of a week's training legs to its fitted weights, so the
    dashboard does not refit every week on every export; the hash changes if any training leg does."""
    history = [r for r in rows if r["id"] == MS_ID and r["d"] >= FIT_START]
    weeks = {}
    out = []
    for leg in fwd:
        wk = monday(leg["d"])
        if wk not in weeks:
            train = [r for r in history if r["d"] < wk]
            digest = hashlib.sha256(json.dumps([FIT_VERSION, L2, wk, train], sort_keys=True).encode()).hexdigest()
            if cache is not None and digest in cache:
                weeks[wk] = cache[digest]
            else:
                weeks[wk] = {"R2": fit(train, "R2"), "R1": fit(train, "R1"), "MKT": fit(train, "MKT"),
                             "n_train": len(train)}
                if cache is not None:
                    cache[digest] = weeks[wk]
        w = weeks[wk]
        out.append({**leg, "rw": predict(leg, w["R2"], "R2"), "r1w": predict(leg, w["R1"], "R1"),
                    "mkt": predict(leg, w["MKT"], "MKT"),
                    "r2f": predict(leg, FROZEN_R2F, "R2")})
    return out


def _cut(fwd: list[dict]) -> tuple[list[dict], bool]:
    """Whole days up to the first day where both checkpoints are reached."""
    by = defaultdict(list)
    for r in fwd:
        by[r["d"]].append(r)
    taken, n = [], 0
    for i, d in enumerate(sorted(by)):
        taken += by[d]
        n += len(by[d])
        if i + 1 >= CHECKPOINT["days"] and n >= CHECKPOINT["flagged_legs"]:
            return taken, True
    return taken, False


def _boot(rows: list[dict], key: str, draws: int = DRAWS) -> tuple[float, float, float]:
    by = defaultdict(list)
    for r in rows:
        by[r["d"]].append(_loss(r[key], r["y"]) - _loss(r["pf"], r["y"]))
    days = sorted(by)
    rnd = random.Random(SEED)
    vals = []
    for _ in range(draws):
        pick = [x for d in (rnd.choice(days) for _ in days) for x in by[d]]
        vals.append(sum(pick) / len(pick))
    vals.sort()
    flat = [x for d in days for x in by[d]]
    return sum(flat) / len(flat), vals[int(0.025 * draws)], vals[int(0.975 * draws) - 1]


def calibration(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .9), (.9, 1.01)):
        g = [r for r in rows if lo <= r["pf"] < hi]
        if g:
            mean = lambda k: sum(r[k] for r in g) / len(g)  # noqa: E731
            out.append({"bucket": [lo, min(hi, 1.0)], "n": len(g), "actual": mean("y"),
                        "p_final": mean("pf"), "rw": mean("rw"), "mkt": mean("mkt")})
    return out


# ---------------------------------------------------------------- tracker API
def status(ledger=None, analysis=None, *, rows: list[dict] | None = None) -> dict:
    rows = legs(ledger) if rows is None else rows
    fwd, stop = forward(rows)
    taken, ready = _cut(fwd)
    return {TEST: {"days": len({r["d"] for r in fwd}), "flagged_legs": len(fwd),
                   "checkpoint": dict(CHECKPOINT), "ready": ready or (stop is not None and bool(fwd)),
                   "complete": ready, "interrupted": stop}}


def judge(rows: list[dict]) -> dict:
    fwd, stop = forward(rows)
    taken, ready = _cut(fwd)
    scored = score(rows, taken)
    mean = lambda k: sum(_loss(r[k], r["y"]) for r in scored) / len(scored)  # noqa: E731
    d, lo, hi = _boot(scored, "rw")
    sec = {name: dict(zip(("delta", "lo", "hi"), _boot(scored, key))) for name, key in (("r2f", "r2f"), ("r1w", "r1w"), ("mkt", "mkt"))}
    sec["rw_minus_mkt"] = dict(zip(("delta", "lo", "hi"), _boot([{**r, "pf": r["mkt"]} for r in scored], "rw")))
    per_stat = {}
    for s in STATS:
        g = [r for r in scored if r["s"] == s]
        if g:
            per_stat[s] = dict(zip(("delta", "lo", "hi"), _boot(g, "rw")), n=len(g))
    return {"experiment": EXPERIMENT, "test": TEST, "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "n_legs": len(scored), "days": len({r["d"] for r in scored}), "complete": ready, "interrupted": stop,
            "logloss": {"pub": mean("pf"), "rw": mean("rw"), "r2f": mean("r2f"), "r1w": mean("r1w"), "mkt": mean("mkt")},
            "primary_delta": d, "ci95": [lo, hi], "pass": ready and hi < 0,
            "secondary": sec, "per_stat": per_stat, "calibration": calibration(scored)}


def evaluate(ledger=None, analysis=None, out_dir: Path | None = None, *, force=False, only=None,
             rows: list[dict] | None = None) -> dict:
    out_dir = Path(out_dir or REPORTS)
    if only and only != TEST:
        return {}
    path = out_dir / f"{EXPERIMENT}-{TEST}-result.json"
    if path.is_file() and not force:
        return {TEST: json.loads(path.read_text(encoding="utf-8"))}
    rows = legs(ledger) if rows is None else rows
    if not status(rows=rows)[TEST]["ready"]:
        return {TEST: {"status": "not_ready", **status(rows=rows)[TEST]}}
    result = judge(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return {TEST: result}


def dashboard(ledger=None, cache_dir=None, *, rows: list[dict] | None = None) -> dict:
    """Running view for the dashboard: progress, calibration on forward legs so far, running delta.
    The running delta is shown for transparency only; the verdict is the frozen look above."""
    rows = legs(ledger, cache_dir) if rows is None else rows
    fwd, stop = forward(rows)
    st = status(rows=rows)[TEST]
    out = {"experiment": EXPERIMENT, "start": START, "progress": st, "interrupted": stop}
    if fwd:
        path = Path(cache_dir or REPORTS) / f"{EXPERIMENT}-fit-cache.json"
        try:
            cache = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        before = len(cache)
        scored = score(rows, fwd, cache)
        if len(cache) != before:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(cache), encoding="utf-8")
            except OSError:
                pass
        d, lo, hi = _boot(scored, "rw", DASHBOARD_DRAWS)
        out.update(n_legs=len(scored), days=len({r["d"] for r in scored}), running_delta=d, running_ci95=[lo, hi],
                   calibration=calibration(scored))
    return out


# R2 fitted once on 2026-11-05..2026-11-24 (21,894 MS legs, 11-19 has no production run) by `freeze`;
# matches numpy to 6 dp. Order: a_pts, a_reb, a_ast, a_fg3m, b (p_final), c (market), d (market^2).
FROZEN_R2F: list[float] = [-0.130982, -0.190218, -0.132677, -0.021445, 0.028416, 0.94972, -0.059996]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("status", "evaluate", "dashboard", "freeze"))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.mode == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    elif a.mode == "evaluate":
        print(json.dumps(evaluate(force=a.force), ensure_ascii=False, indent=1))
    elif a.mode == "dashboard":
        print(json.dumps(dashboard(), ensure_ascii=False, indent=1))
    else:  # one-off: print the R2F coefficients fitted on FIT_START..2026-11-24
        train = [r for r in legs() if r["id"] == MS_ID and FIT_START <= r["d"] <= "2026-11-24"]
        print(len(train), [round(v, 6) for v in fit(train, "R2")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
