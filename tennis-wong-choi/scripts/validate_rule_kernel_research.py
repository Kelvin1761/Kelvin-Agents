"""Execute the locked F02 grid; no database, odds, production imports or fitting.

Run from tennis-wong-choi with PYTHONPATH=src. MC has its own score/service
transitions. It does not draw from the DP terminal distribution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import resource
import sys
import time

import numpy as np
import scipy
from scipy.stats import beta

from tennis_wc.research_kernel.reference import hold_probability, tiebreak_probability
from tennis_wc.research_kernel.rule_kernel import SetRule, match_win_probability, set_law

RULES = [SetRule(6, 7), SetRule(6, 10), SetRule(12, 7), SetRule(None, None)]
POINTS = [.45, .60, .75]
ORDINARY = SetRule(6, 7)


def cases():
    for p in POINTS:
        yield {"kind": "game", "p_a": p}
    for a, b, target, first in itertools.product(POINTS, POINTS, [7, 10], [True, False]):
        yield dict(kind="tb", p_a=a, p_b=b, target=target, first_a=first)
    for a, b, rule, first in itertools.product(POINTS, POINTS, range(4), [True, False]):
        yield dict(kind="set", p_a=a, p_b=b, rule=rule, first_a=first)
    for a, b, rule, first, best_of in itertools.product(POINTS, POINTS, range(4), [True, False], [3, 5]):
        yield dict(kind="match", p_a=a, p_b=b, rule=rule, first_a=first, best_of=best_of)


def oracle(case):
    a = case["p_a"]
    if case["kind"] == "game":
        return hold_probability(a)
    b, first = case["p_b"], case["first_a"]
    if case["kind"] == "tb":
        p = tiebreak_probability(a, b, first_a=first, target=case["target"])
        complement = tiebreak_probability(b, a, first_a=not first, target=case["target"])
    elif case["kind"] == "set":
        law = set_law(a, b, first_a=first, rule=RULES[case["rule"]])
        swapped = set_law(b, a, first_a=not first, rule=RULES[case["rule"]])
        assert abs(law.total_mass()-1) <= 1e-8
        p = sum(m for (winner, _), m in law.winner_server_masses().items() if winner)
        complement = sum(m for (winner, _), m in swapped.winner_server_masses().items() if winner)
    else:
        kwargs = dict(best_of=case["best_of"], deciding_rule=RULES[case["rule"]], ordinary_rule=ORDINARY)
        p = match_win_probability(a, b, first_a=first, **kwargs)
        complement = match_win_probability(b, a, first_a=not first, **kwargs)
    assert abs(p+complement-1) <= 1e-8
    assert 0 <= p <= 1
    return p


def point_race(rng, probabilities, *, first=None, target):
    """Independent point MC for standard service games or tie-breaks."""
    a = np.zeros(len(probabilities), dtype=np.int64)
    b = np.zeros_like(a)
    active = np.arange(len(a))
    step = 0
    while len(active):
        if first is None:
            chance = probabilities[active]
        else:
            # First point, then alternating blocks of two service points.
            serving_a = first[active] ^ bool(((step+1)//2) % 2)
            chance = np.where(serving_a, probabilities[active, 0], 1-probabilities[active, 1])
        won = rng.random(len(active)) < chance
        a[active] += won
        b[active] += ~won
        finished = (np.maximum(a[active], b[active]) >= target) & (np.abs(a[active]-b[active]) >= 2)
        active = active[~finished]
        step += 1
    return a > b


def mc_set(rng, p_a, p_b, first, rule):
    a = np.zeros(len(first), dtype=np.int64)
    b = np.zeros_like(a)
    server = first.copy()
    active = np.arange(len(first))
    h_a, h_b = hold_probability(p_a), hold_probability(p_b)
    while len(active):
        if rule.trigger_games is not None:
            at_tb = (a[active] == rule.trigger_games) & (b[active] == rule.trigger_games)
            selected = active[at_tb]
            if len(selected):
                points = np.tile([p_a, p_b], (len(selected), 1))
                won = point_race(rng, points, first=server[selected], target=rule.target_points)
                a[selected] += won
                b[selected] += ~won
                server[selected] = ~server[selected]
            active = active[~at_tb]
        if not len(active):
            break
        held = rng.random(len(active)) < np.where(server[active], h_a, h_b)
        won = held == server[active]
        a[active] += won
        b[active] += ~won
        server[active] = ~server[active]
        terminal = (np.maximum(a[active], b[active]) >= 6) & (np.abs(a[active]-b[active]) >= 2)
        active = active[~terminal]
    assert np.all(a != b)
    return a > b, server


def mc_match(rng, p_a, p_b, first, rule, best_of):
    a = np.zeros(len(first), dtype=np.int64)
    b = np.zeros_like(a)
    server = first.copy()
    active = np.arange(len(first))
    need = best_of//2+1
    while len(active):
        deciding = (a[active] == need-1) & (b[active] == need-1)
        for final, set_rule in [(False, ORDINARY), (True, rule)]:
            selected = active[deciding == final]
            if not len(selected):
                continue
            won, next_server = mc_set(rng, p_a, p_b, server[selected], set_rule)
            a[selected] += won
            b[selected] += ~won
            server[selected] = next_server
        active = active[(a[active] < need) & (b[active] < need)]
    assert np.all((a == need) ^ (b == need))
    return a > b


def mc_wins(case, rng, n):
    if case["kind"] == "game":
        return int(point_race(rng, np.full(n, case["p_a"]), target=4).sum())
    first = np.full(n, case["first_a"], dtype=bool)
    if case["kind"] == "tb":
        return int(point_race(rng, np.tile([case["p_a"], case["p_b"]], (n, 1)),
                              first=first, target=case["target"]).sum())
    if case["kind"] == "set":
        return int(mc_set(rng, case["p_a"], case["p_b"], first, RULES[case["rule"]])[0].sum())
    return int(mc_match(rng, case["p_a"], case["p_b"], first,
                        RULES[case["rule"]], case["best_of"]).sum())


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--mode", choices=["dp", "mc"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    grid = list(cases())
    assert len(grid) == 255
    root = Path(__file__).resolve().parents[1]
    sources = [Path(__file__).resolve(), *sorted((root/"src/tennis_wc/research_kernel").glob("*.py"))]
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    metadata = dict(started_utc=datetime.now(timezone.utc).isoformat(), argv=sys.argv,
                    python=sys.version, platform=platform.platform(), numpy=np.__version__, scipy=scipy.__version__,
                    source_sha256=hashes, seed=20260826, batch_size=10000, trials_per_case=100000,
                    family_alpha=.01, comparisons=255,
                    protocol_sha256="3b75b151e0e9ef981418fe215f2067b6feb5592f7432339642a5dc353eb168d2",
                    rng_policy="single numpy default_rng stream; canonical case order, then ten sequential batches",
                    grid_sha256=hashlib.sha256(json.dumps(grid, sort_keys=True).encode()).hexdigest())
    (args.output/"metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
    rng = np.random.default_rng(20260826)
    results = []
    with (args.output/"cases.jsonl").open("w") as stream:
        for i, case in enumerate(grid):
            started = time.perf_counter()
            row = dict(case_id=i, case=case)
            try:
                p = oracle(case)
                row.update(dp_probability=p, invariants_pass=True)
                if args.mode == "mc":
                    k = sum(mc_wins(case, rng, 10000) for _ in range(10))
                    alpha = .01/255
                    lo = 0.0 if k == 0 else float(beta.ppf(alpha/2, k, 100000-k+1))
                    hi = 1.0 if k == 100000 else float(beta.ppf(1-alpha/2, k+1, 100000-k))
                    row.update(wins=k, trials=100000, interval=[lo, hi], mc_pass=lo <= p <= hi)
            except (ValueError, ArithmeticError, AssertionError) as exc:
                row.update(invariants_pass=False, error=f"{type(exc).__name__}: {exc}")
            row["seconds"] = time.perf_counter()-started
            row["process_peak_rss"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            results.append(row)
            stream.write(json.dumps(row)+"\n")
            stream.flush()
            if (i+1) % 10 == 0:
                print(f"{args.mode}: {i+1}/255", flush=True)
    report = dict(mode=args.mode, cases=255, results=results,
                  source_unchanged=all(hashlib.sha256(path.read_bytes()).hexdigest() == hashes[str(path.relative_to(root))] for path in sources),
                  all_invariants_pass=all(r["invariants_pass"] for r in results),
                  all_mc_pass=all(r.get("mc_pass", False) for r in results) if args.mode == "mc" else None,
                  rss_units="bytes" if sys.platform == "darwin" else "KiB",
                  qualification="SYNTHETIC_CORRECTNESS_ONLY", production_changed=False)
    (args.output/"result.json").write_text(json.dumps(report, indent=2)+"\n")
    print("DONE", report["all_invariants_pass"], report["all_mc_pass"], flush=True)


if __name__ == "__main__":
    main()
