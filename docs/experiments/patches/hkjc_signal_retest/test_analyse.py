import json

import numpy as np
import pytest

import analyse


def test_alignment_centering_and_walk_forward(tmp_path):
    rows = []
    off = []
    for year in (2019, 2020, 2021):
        horses = [dict(n=i, raw=float(i * 2), pos=i) for i in range(1, 6)]
        rows.append(dict(meeting=str(year), race=1, date=f'{year}-09-01', horses=horses))
        off.append(dict(meeting=str(year), race=1, date=f'{year}-09-01',
                        horses=[dict(h, raw=h['raw'] - h['n'] ** 2) for h in reversed(horses)]))
    for name, data in (('base', rows), ('off', off)):
        (tmp_path / name).write_text(''.join(json.dumps(r) + '\n' for r in data))
    rows = analyse.load(tmp_path / 'base')
    features = analyse.contributions(rows, analyse.load(tmp_path / 'off'))
    np.testing.assert_allclose(features[0], np.array([1, 4, 9, 16, 25]) - 11)
    assert all(abs(f.mean()) < 1e-12 for f in features)
    betas = analyse.fit_betas(rows, features)
    altered = json.loads(json.dumps(rows))
    altered[1]['horses'][0]['pos'] = 5
    assert analyse.fit_betas(altered, features)[2020] == pytest.approx(betas[2020])
    beta_2021 = analyse.fit_betas(altered, features)[2021]
    altered[2]['horses'][0]['pos'] = 5
    assert analyse.fit_betas(altered, features)[2021] == pytest.approx(beta_2021)
    result = analyse.rescale(rows, features, betas)
    assert result[0] == rows[0]
    assert result[1]['picks'] == [h['n'] for h in sorted(
        result[1]['horses'], key=lambda h: -h['raw'])]
    off[0]['horses'].pop()
    with pytest.raises(ValueError, match='horse mismatch'):
        analyse.contributions(rows, off)


def test_summary_parse():
    text = '\n'.join(f'{label} value [1,2]' for label in analyse.LABELS)
    parsed = analyse.parse_compare(text)
    assert len(parsed) == 5
    assert 'Good value [1,2]' in analyse.summary_cell(parsed)
    with pytest.raises(ValueError):
        analyse.parse_compare('Good missing others')
