"""Current-main market reader isolation only; no model/weight change authority."""
import hashlib
import json

import pytest
from test_sectional_source_binding import case


def test_market_absence_is_explicit_empty_without_default_reload(tmp_path,monkeypatch):
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import market_history as market
    from hkjc_racing_engine.native_sources import JsonSource
    def forbidden(*args,**kwargs): raise AssertionError('default market cache reloaded')
    monkeypatch.setattr(market,'load_table',forbidden)
    table=auto._prepare_market_table(JsonSource(tmp_path/'missing.json',None))
    assert table=={} and market.apply({},'2026-11-08',table=table)==0


@pytest.mark.parametrize('payload',[{}, {'horses':[]},{'horses':{'A001':[['2026-10-01',0]]}},
    {'horses':{'A001':[['2026-10-02',3],['2026-10-01',3]]}}, {'horses':{'A001':[['bad',3]]}},
    {'horses':{'A001':[['2026-10-01',True]]}}, {'horses':{'A001':[['2026-10-01',10**500]]}}])
def test_bad_market_resource_rejects_before_headers_enrichment_events(tmp_path,monkeypatch,payload):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine.native_sources import JsonSource
    hk,path=case(tmp_path); table=tmp_path/'market.json'; table.write_text(json.dumps(payload))
    header=Mock(side_effect=AssertionError('headers ran')); enrich=Mock(); event=Mock()
    monkeypatch.setattr(auto,'_align_runner_headers',header); monkeypatch.setattr(auto,'_enrich_profile_history',enrich)
    with pytest.raises((ValueError,OverflowError)):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),market_source=JsonSource(table,hashlib.sha256(table.read_bytes()).hexdigest()),event_sink=event)
    header.assert_not_called(); enrich.assert_not_called(); event.assert_not_called()


def test_market_cutoff_and_shadow_propagation_reuse_unchanged_native_function(tmp_path):
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import market_history as market
    from hkjc_racing_engine.native_sources import JsonSource
    table=tmp_path/'market.json'
    data={'version':1,'horses':{'A001':[['2026-10-01',3],['2026-11-08',999]],'A002':[['2026-10-01',25]]}}
    table.write_text(json.dumps(data))
    bound=auto._prepare_market_table(JsonSource(table,hashlib.sha256(table.read_bytes()).hexdigest()))
    assert market.prev_log_odds('A001','2026-11-08',bound)==market.math.log(3)
    from copy import deepcopy
    horses={str(n):{'horse_code':'A00'+str(n),'python_auto':{'ability_score_raw':60,'shadow_profiles':{'test':{'ability_score_raw':61}}}}
            for n in (1,2)}
    expected=deepcopy(horses); actual=deepcopy(horses)
    assert market.apply(expected,'2026-11-08',table=data)==market.apply(actual,'2026-11-08',table=bound)
    assert expected==actual
    assert actual['1']['python_auto']['market_history_delta'] != 0
