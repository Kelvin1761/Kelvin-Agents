import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_weight_walkforward as wf


def fixture():
    races = []
    for day in range(28):
        date = f'2026-08-{day + 1:02d}'
        rows = [{'n': n, 'name': str(n), 'pos': n, 'features': {}, 'wet': 0,
                 'ability': 60, 'sp': float(n + 1)} for n in range(1, 7)]
        races.append({'date': date, 'meeting': 'A', 'race': 1, 'field': 6, 'rows': rows})
    return SimpleNamespace(races=races, dim_matrix=lambda: None)


def test_strict_earlier_and_fallback():
    seen = []
    def fit(ds, mx, base, end, seed, draws, folds):
        seen.append([r['date'] for r in ds.races[:end]])
        assert (seed, draws, folds) == (20260826, 400, 4)
        return None, 0
    windows, predictions = wf.predict(fixture(), fit)
    for dates, window in zip(seen, windows):
        assert max(dates) < min(window['prediction_dates'])
        assert window['fallback']
    assert all(row['ability_baseline'] == row['ability_candidate']
               for race in predictions for row in race['rows'])


def test_aa_reject():
    _, predictions = wf.predict(fixture(), lambda ds, mx, base, end, seed, draws, folds: (dict(base), 1))
    assert wf.judge(predictions, leakage_audit_passed=True)['verdict'] == 'REJECT'
