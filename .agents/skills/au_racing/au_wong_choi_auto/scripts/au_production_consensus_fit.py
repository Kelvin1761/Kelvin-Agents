"""Internal six-coefficient consensus fitter for complete-day AU OOS production.

The OOS producer supplies only prior-day, audited training inputs/labels. This
module verifies projection/label bindings; it does not certify historical PIT.
No CLI, holdout reader or global objective state is provided.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import random
import statistics
import sys

from au_prediction_intake import content_hash, _require
from au_serve_training_projection import replay_projection
from au_racing_engine.scoring import MATRIX_WEIGHTS
sys.path.insert(0, str(Path(__file__).resolve().parent.parents[2] / 'shared_racing'))
from eval_metrics import race_metrics, summarize_races


def _day_folds(records, folds=5):
    days=sorted({r['date'] for r in records})
    _require(len(days)>=folds, 'consensus_insufficient_training_days')
    edges=[len(days)*i//folds for i in range(folds+1)]
    return [[r for r in records if r['date'] in set(days[edges[i]:edges[i+1]])]
            for i in range(folds)]


def _objective(records, weights):
    metrics=[]
    for record in records:
        projection=record['input']['training_projection']
        picks=replay_projection(projection, weights)['ranking']
        positions=record['labels']
        metrics.append(race_metrics(picks, {n for n,p in positions.items() if p<=3},
                                    actual_pos=positions, field_size=len(positions)))
    summary=summarize_races(metrics)
    return (sum(summary['rates'][k] for k in ('gold','good_positional','pass'))
            +summary['top3_precision'])/4


def _consensus_search(records, baseline, *, seed, budget):
    """Search kernel; all settings are fixed by the public registered adapter."""
    folds=_day_folds(records)
    base=_objective(records,baseline)
    fold_base=[_objective(f,baseline) for f in folds]
    baseline={k:baseline[k] for k in MATRIX_WEIGHTS}
    dims=tuple(baseline);total=sum(baseline.values());rng=random.Random(seed)
    gated=[]
    def accepted(weights):
        return (_objective(records,weights)>base and
                all(_objective(f,weights)>=b for f,b in zip(folds,fold_base)))
    for i in range(budget):
        alpha=[1.0 if i%2==0 else max(baseline[d]*25, .35) for d in dims]
        values=[rng.gammavariate(a,1) for a in alpha]
        weights={d:total*v/sum(values) for d,v in zip(dims,values)}
        if accepted(weights):gated.append(weights)
    if not gated:return None
    medians={d:statistics.median(w[d] for w in gated) for d in dims}
    weights={d:total*v/sum(medians.values()) for d,v in medians.items()}
    # A median is itself a new vector; never presume it inherits each arm's gate.
    return {'matrix_weights':weights} if accepted(weights) else None


def fit_production_coefficients(prefix, profile):
    """fit(prefix, profile) callback for au_oos_predictions.produce_walk_forward.

    Require this algorithm specification verbatim in the preregistered profile.
    A None return means the producer emits registered baseline fallback for every
    race that day. A failed integrity check raises; it never becomes fallback.
    """
    spec=profile.get('fit_spec',{})
    _require(spec.get('algorithm')=='au-production-day-consensus/v1' and
             spec.get('search_budget')==3000 and spec.get('folds')==5 and
             spec.get('objective')=='place' and spec.get('minimum_nonnegative_folds')==5 and
             spec.get('median_recheck') is True and type(spec.get('seed')) is int,
             'consensus_algorithm_not_registered')
    baseline=spec.get('baseline_weights',{})
    _require(baseline==dict(MATRIX_WEIGHTS), 'consensus_locked_baseline_changed')
    _require(bool(prefix), 'consensus_empty_training_prefix')
    before=content_hash(prefix);ids=set()
    for record in prefix:
        _require(record['race_id'] not in ids, 'consensus_duplicate_training_race')
        ids.add(record['race_id'])
        _require(record['date']>='2026-08-05', 'consensus_outside_clean_window')
        projection=record['input'].get('training_projection',{})
        _require(record['input'].get('training_projection_hash')==content_hash(projection),
                 'consensus_projection_hash_changed')
        positions=record['labels'];roster=projection['runner_ids']
        _require(record.get('labels_hash')==content_hash(positions), 'consensus_labels_hash_changed')
        _require(set(positions)==set(roster) and
                 all(type(p) is int and 1<=p<=len(roster) for p in positions.values()) and
                 1 in positions.values() and sum(p<=3 for p in positions.values())>=3,
                 'consensus_incomplete_labels')
        replay_projection(projection, baseline)
    result=_consensus_search(deepcopy(prefix),baseline,seed=spec['seed'],budget=3000)
    _require(content_hash(prefix)==before, 'consensus_input_mutated')
    return result
