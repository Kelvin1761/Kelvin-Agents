import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Horse_Racing_Dashboard/backend'))
sys.path.insert(0,str(ROOT/'.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from services.parser_au import _parse_au_race_header  # noqa: E402
from au_racing_engine.renderer import _panorama  # noqa: E402

@pytest.mark.parametrize('going',['Good 4','Soft 5','Heavy 8','Synthetic'])
def test_renderer_and_parser_share_explicit_going(going):
    text=_panorama({'race_number':1,'distance':'1300m','going':going},{'confidence_tier':'clear','radar_size':4,'ranking':[]},{})
    assert f'| 場地狀況 | {going} |' in text
    assert _parse_au_race_header(text)['going']==going

def test_explicit_current_going_wins_over_historical_detail():
    assert _parse_au_race_header('| 場地狀況 | Heavy 8 |\nGoing: Good 4\n')['going']=='Heavy 8'
    assert 'going' not in _parse_au_race_header('| 場地狀況 | — |\nGoing: Good 4\n')

@pytest.mark.parametrize('line',['Going: Soft 5','Track Condition: Heavy 8','預測掛牌：Good 4'])
def test_legacy_headers_still_parse(line):
    assert _parse_au_race_header(line)['going']==line.replace('：',':').split(':',1)[1].strip()
