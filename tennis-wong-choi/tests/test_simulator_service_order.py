"""ITF Rules 14 and 5(b): service order continues across set boundaries."""
import pytest

from tennis_wc.props import match_simulator as model


@pytest.mark.parametrize('first_score,second_server',[
    ((6,4),True),((6,3),False),((7,6),False),
    ((7,5),True),((6,0),True),((6,1),False),
])
def test_next_set_server_follows_games_played(monkeypatch,first_score,second_server):
    scores=iter([first_score,(6,3)])
    observed=[]

    def controlled(rng,a,b,a_first):
        observed.append(a_first)
        return next(scores)

    monkeypatch.setattr(model,'_play_set',controlled)
    model.simulate_match(.7,.7,trials=1)
    assert observed==[True,second_server]


def test_service_rotation_carries_through_three_sets(monkeypatch):
    scores=iter([(4,6),(6,3),(6,4)])
    observed=[]

    def controlled(rng,a,b,a_first):
        observed.append(a_first)
        return next(scores)

    monkeypatch.setattr(model,'_play_set',controlled)
    model.simulate_match(.7,.7,trials=1)
    assert observed==[True,True,False]
