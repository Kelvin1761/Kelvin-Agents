from __future__ import annotations

import json
import sys
from pathlib import Path

DAILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DAILY))
import au_daily_schedule as S  # noqa: E402


def setup_meeting(tmp_path):
    horses = {'1': {'horse_name': 'First (NZ)', 'jockey': 'One', 'barrier': 1},
              '2': {'horse_name': 'Second', 'jockey': 'Two', 'barrier': 2}}
    (tmp_path / 'Race_1_Logic.json').write_text(json.dumps({'race_analysis': {'going': 'Soft 5'}, 'horses': horses}))
    card = tmp_path / '08-05 Race 1 Racecard.md'
    card.write_text('1. First (NZ) (3)\nTrainer: X\n2. Second (7)\n')
    return horses, card


def test_original_draws_not_dense_scores_are_compared_to_provider(tmp_path):
    horses, _ = setup_meeting(tmp_path)
    state = S.stored_race_state(tmp_path)
    assert state[1]['barriers'] == {'1': '3', '2': '7'}
    assert state[1]['barrier_basis'] == 'original_draw'
    live = {1: {'going': 'Soft 5', 'field': ['1', '2'],
                'jockeys': {'1': 'One', '2': 'Two'}, 'barriers': {'1': '3', '2': '7'}}}
    assert S.diff_race_state(state, live) == {}
    assert json.loads((tmp_path / 'Race_1_Logic.json').read_text())['horses'] == horses
    live[1]['barriers'] = {'1': '4', '2': '8'}
    assert set(S.diff_race_state(state, live)[1]) == {'barriers'}


def test_wrong_identity_or_duplicate_cards_never_supply_draws(tmp_path):
    horses, card = setup_meeting(tmp_path)
    card.write_text('1. Wrong Horse (3)\n2. Second (7)\n')
    assert S._racecard_original_draws(tmp_path, 1, horses) is None
    assert S.stored_race_state(tmp_path)[1]['barrier_basis'] == 'logic_unverified_draw'
    card.write_text('1. First (NZ) (3)\n2. Second (7)\n')
    (tmp_path / 'other Race 1 Racecard.md').write_text(card.read_text())
    assert S._racecard_original_draws(tmp_path, 1, horses) is None


def test_missing_runner_duplicate_draw_or_duplicate_number_are_rejected(tmp_path):
    horses, card = setup_meeting(tmp_path)
    for text in ['1. First (NZ) (3)\n',
                 '1. First (NZ) (3)\n2. Second (3)\n',
                 '1. First (NZ) (3)\n1. First (NZ) (7)\n2. Second (9)\n']:
        card.write_text(text)
        assert S._racecard_original_draws(tmp_path, 1, horses) is None
