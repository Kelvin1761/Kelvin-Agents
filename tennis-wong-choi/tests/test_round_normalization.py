from __future__ import annotations

import pytest
from tennis_wc.features.round_performance import normalise_round


@pytest.mark.parametrize('raw,expected',[(code,code) for code in ('F','SF','QF','R16','R32','R64','R128','QUALIFYING')]+[('Final','F'),('Semifinal','SF'),('Quarterfinal','QF')])
def test_round_normalization_is_idempotent(raw,expected):
    assert normalise_round(raw)==expected
    assert normalise_round(normalise_round(raw))==expected


def test_coded_and_named_finals_enter_the_same_performance_sample(tmp_path,monkeypatch):
    from datetime import date
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.round_performance import calculate_round_stats
    from tennis_wc.features.big_match import calculate_big_match_stats
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        for index,stage,won in ((1,'F',1),(2,'Final',0)):
            c.execute('''INSERT INTO player_match_history
                (provider_match_id,player_id,opponent_id,tour,match_date,tournament_external_id,
                 tournament_level,round,format,won,source_provider,raw_response_id,created_at,surface)
                VALUES (?,1,2,'ATP','2026-01-01','event','ATP_250',?,'BO3',?,'test',1,'2026-01-02T00:00:00Z','hard')''',
                (str(index),stage,won))
    summary=calculate_round_stats(1,'F','ATP_250','hard',date(2026,6,1),'LAST_52_WEEKS',persist=False)
    assert summary['matches']==2 and summary['win_rate']==.5
    assert calculate_big_match_stats(1,'hard',date(2026,6,1),'LAST_52_WEEKS',persist=False)['matches']==2
