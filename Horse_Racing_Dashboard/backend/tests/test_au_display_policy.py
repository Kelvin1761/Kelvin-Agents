from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from services.au_display_policy import apply_au_display_policy, without_pi  # noqa: E402


def test_mixed_verdict_retains_l600_and_drops_only_the_pi_sentence():
    source = ('  - **判讀：** 往績末段環境快過場均。'
              '只係往績快、PI 升位平平，唔可以當自己快。'
              '速度背景信心：強（L600 3場）。\n'
              '  - **數據：** L600 -0.40s\n'
              '    - 近段 PI 走勢: PI 1, 3, 2\n'
              '    - 試閘交代: 3次\n')
    result = without_pi(source)
    assert 'PI' not in result
    assert '往績末段環境快過場均' in result
    assert 'L600 -0.40s' in result and 'L600 3場' in result
    assert '試閘交代: 3次' in result


def test_pi_subsection_and_table_column_do_not_leave_orphan_values():
    source = ('#### 段速\n- **位置增益（PI）:**\n  - 1→3→2\n'
              '- **L400:** 23.8s\n\n'
              '| 日期 | PI | L600 |\n|---|---|---|\n'
              '| 10/10 | +3 | 35.2 |\n')
    result = without_pi(source)
    assert 'PI' not in result and '1→3→2' not in result
    assert '| 日期 | L600 |' in result
    assert '| 10/10 | 35.2 |' in result
    assert 'L400' in result


def test_au_only_cleanup_preserves_identity_scores_and_hkjc_pi():
    horse = {'horse_number': 1, 'horse_name': 'Spice', 'ability_score': 78.3,
             'rank': 1, 'final_grade': 'A',
             'raw_text': '#### 分析\n- 近段 PI: +3\n- L600: 35.2s',
             'data_readout': [{'label': '位置增益（PI）', 'value': '+3'},
                              {'label': 'L600', 'value': '35.2s'}],
             'dimension_details': [{'name': '速度考驗背景', 'score': 71.,
                                    'weight': .12, 'evidence': ['近段 PI +3', 'L600 35.2s']}]}
    payload = {'meetings': [{'date': '2026-10-15', 'venue': 'Test', 'region': 'au'},
                            {'date': '2026-10-18', 'venue': 'ShaTin', 'region': 'hkjc'}],
               'races': {key: {'races_by_analyst': {'auto': [{'horses': [deepcopy(horse)]}]}}
                         for key in ['2026-10-15|Test', '2026-10-18|ShaTin']}}
    hk_before = deepcopy(payload['races']['2026-10-18|ShaTin'])
    apply_au_display_policy(payload)
    au = payload['races']['2026-10-15|Test']['races_by_analyst']['auto'][0]['horses'][0]
    assert au['horse_name'] == 'Spice'
    assert (au['ability_score'], au['rank'], au['final_grade']) == (78.3, 1, 'A')
    assert au['data_readout'] == [{'label': 'L600', 'value': '35.2s'}]
    assert au['dimension_details'][0]['score'] == 71.
    assert au['dimension_details'][0]['evidence'] == ['L600 35.2s']
    assert 'PI' not in au['raw_text']
    assert payload['races']['2026-10-18|ShaTin'] == hk_before
    before_second_pass = deepcopy(payload)
    assert apply_au_display_policy(payload) == before_second_pass


def test_legacy_uppercase_and_nested_region_are_explicit_au_but_unknown_is_not():
    def entry(region=None):
        return {'meeting': {'region': region}, 'races_by_analyst': {
            'auto': [{'horses': [{'raw_text': '近段 PI +3'}]}]}}
    payload = {'meetings': [{'date': '2026-10-15', 'venue': 'Test', 'region': 'AU'}],
               'races': {'2026-10-15|Test': entry(), 'nested': entry('AU'),
                         'unknown': entry()}}
    apply_au_display_policy(payload)
    for key in ['2026-10-15|Test', 'nested']:
        assert payload['races'][key]['races_by_analyst']['auto'][0]['horses'][0]['raw_text'] == ''
    assert payload['races']['unknown']['races_by_analyst']['auto'][0]['horses'][0]['raw_text'] == '近段 PI +3'
