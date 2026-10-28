"""Pre-registered exact-DP/Monte-Carlo parity, independent of match outcomes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.stats import beta

from research.tennis_unified.kernel import match_probability, tiebreak_probability
from research.tennis_unified.warehouse import digest, write_new

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tennis-wong-choi/src'))
from tennis_wc.props.match_simulator import simulate_match


def interval(wins, trials, alpha):
    return [float(beta.ppf(alpha/2, wins, trials-wins+1)) if wins else 0.,
            float(beta.ppf(1-alpha/2, wins+1, trials-wins)) if wins < trials else 1.]


def point_simulation(p_a, p_b, first_a, target, trials, seed):
    # Independent direct state walk; no exact-oracle/closed-tail calls.
    rng = np.random.default_rng(seed)
    a, b = np.zeros(trials, dtype=np.int32), np.zeros(trials, dtype=np.int32)
    active = np.ones(trials, dtype=bool)
    for point in range(10000):
        ids = np.flatnonzero(active)
        if not len(ids):
            return int(np.sum(a > b))
        # Generate explicit ITF 1,2,2,... serving blocks, independently of the
        # oracle's modulo-four expression.
        server = first_a if point == 0 or ((point-1)//2) % 2 == 1 else not first_a
        probability = p_a if server else 1-p_b
        won_a = rng.random(len(ids)) < probability
        a[ids] += won_a
        b[ids] += ~won_a
        active = ~((np.maximum(a, b) >= target) & (np.abs(a-b) >= 2))
    raise ValueError('point simulation did not terminate; never discard unfinished trials')


def run(protocol: Path, output: Path):
    spec = json.loads(protocol.read_text())
    output.mkdir(exist_ok=False)
    write_new(output / 'protocol_lock.json', {
        'locked_at': datetime.now(timezone.utc).isoformat(), 'protocol': spec,
        'protocol_sha256': digest(protocol), 'implementation_sha256': digest(Path(__file__)),
        'oracle_sha256': digest(Path(__file__).with_name('kernel.py')),
        'legacy_simulator_sha256': digest(ROOT / 'tennis-wong-choi/src/tennis_wc/props/match_simulator.py')})
    count = len(spec['legacy_hold_pairs'])*len(spec['best_of']) + len(spec['point_pairs'])*len(spec['tiebreak_targets'])*len(spec['first_server_a'])
    alpha, trials = spec['family_alpha']/count, spec['trials_per_case']
    cases = []
    for hold_a, hold_b in spec['legacy_hold_pairs']:
        for best_of in spec['best_of']:
            clock = time.monotonic()
            expected = match_probability(hold_a, hold_b, best_of=best_of)
            distribution = simulate_match(hold_a, hold_b, best_of=best_of, trials=trials,
                                          seed=spec['seed']+len(cases), dispersion=0.)
            wins = sum(a > b for a, b in zip(distribution.sets_a, distribution.sets_b))
            low, high = interval(wins, trials, alpha)
            cases.append({'kind': 'legacy_fixed_hold', 'hold_a': hold_a, 'hold_b': hold_b,
                          'best_of': best_of, 'expected_dp': expected, 'observed_mc': wins/trials,
                          'simultaneous_interval': [low, high], 'pass': low <= expected <= high,
                          'elapsed_seconds': time.monotonic()-clock})
            print(json.dumps(cases[-1]), flush=True)
    for p_a, p_b in spec['point_pairs']:
        for target in spec['tiebreak_targets']:
            for first_a in spec['first_server_a']:
                clock = time.monotonic()
                expected = tiebreak_probability(p_a, p_b, first_a=first_a, target=target)
                wins = point_simulation(p_a, p_b, first_a, target, trials, spec['seed']+len(cases))
                low, high = interval(wins, trials, alpha)
                cases.append({'kind': 'iid_point_tiebreak', 'p_a': p_a, 'p_b': p_b,
                              'target': target, 'first_a': first_a, 'expected_dp': expected,
                              'observed_mc': wins/trials, 'simultaneous_interval': [low, high],
                              'pass': low <= expected <= high, 'elapsed_seconds': time.monotonic()-clock})
                print(json.dumps(cases[-1]), flush=True)
    result = {'cases': cases, 'all_pass': all(case['pass'] for case in cases),
              'total_cases': count, 'trials_per_case': trials, 'family_alpha': spec['family_alpha'],
              'promotion_eligible': False, 'qualification': spec['scope'],
              'known_contract_gaps': ['Legacy simulator has no point-level or year-specific tiebreak input.',
                                      'Tournament/year rule mapping is not established by this synthetic audit.']}
    write_new(output / 'kernel_results.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.protocol, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
    raise SystemExit(0 if result['all_pass'] else 1)


if __name__ == '__main__':
    main()
