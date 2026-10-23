"""An explicit live-ML request cannot silently become legacy or unapproved ML."""
import json
from pathlib import Path
import sys

import pytest

NBA=Path(__file__).resolve().parents[2];REPO=NBA.parents[2]
sys.path.insert(0,str(NBA/'nba_wong_choi/scripts'));sys.path.insert(0,str(REPO/'.agents/scripts/nba_ml'))
import generate_nba_reports as reports
import nba_ml_predictor


@pytest.mark.parametrize('engine,adjust',[('ml','0'),('hybrid','1')])
@pytest.mark.parametrize('missing',[False,True])
def test_explicit_live_ml_needs_approved_artifact_and_never_falls_back(tmp_path,monkeypatch,engine,adjust,missing):
    odds=tmp_path/'odds.json';odds.write_text(json.dumps({'player_props':{}}))
    stats=tmp_path/'stats.json';stats.write_text(json.dumps({'meta':{'date':'2026-10-24T23:00Z','away':{'abbr':'BOS'},'home':{'abbr':'LAL'}},'players':{}}))
    output=tmp_path/'report.md'
    class Unapproved:
        deployment_eligible=False
        feature_names=['x']
        def __init__(self):
            if missing:raise FileNotFoundError('synthetic missing artifact')
    monkeypatch.setattr(nba_ml_predictor,'MLPropPredictor',Unapproved)
    monkeypatch.setenv('NBA_HYBRID_ML_ADJUST_ENABLED',adjust)
    monkeypatch.setattr(sys,'argv',['generate','--sportsbet',str(odds),'--extractor',str(stats),'--output',str(output),'--engine',engine])
    with pytest.raises(reports.MLModelUnavailable):reports.main()
    assert not output.exists()
