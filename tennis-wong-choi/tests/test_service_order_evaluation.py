"""A kernel comparison cannot silently change contracts or quote/outcome evidence."""
import importlib.util
from pathlib import Path
import sys

import pytest

from test_wta_history_evaluation import study


def test_kernel_comparison_is_paired_on_quote_outcome_and_contract(monkeypatch):
    monkeypatch.setitem(sys.modules,'evaluate_wta_history',study)
    spec=importlib.util.spec_from_file_location('order_study',
        Path(__file__).parents[1]/'scripts'/'evaluate_service_order.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base={'contract':[1,'player_games',1,10.5],'cluster':1,'quote_id':2,'date':'2026-09-01',
          'surface':'hard','tour':'WTA','family':'player_games','won':1,'market':.5,'odds':2,
          'exposure':1,'losses':{'A0':study.binomial_losses(.5,1,1),
                               'market':study.binomial_losses(.5,1,1)},'probabilities':{'A0':.5}}
    candidate={**base,'probabilities':{'A0':.8},
               'losses':{**base['losses'],'A0':study.binomial_losses(.8,1,1)}}
    result=module.compare([base],[candidate])
    assert result['all']['matches']==1
    assert result['all']['arms']['candidate']['brier']==pytest.approx(.04)
    assert result['all']['arms']['candidate']['brier_delta_baseline_ci95']==pytest.approx([-.21,-.21])
    with pytest.raises(ValueError,match='immutable quote'):
        module.compare([base],[{**candidate,'quote_id':3}])
    with pytest.raises(ValueError,match='coverage'):
        module.compare([base],[])
