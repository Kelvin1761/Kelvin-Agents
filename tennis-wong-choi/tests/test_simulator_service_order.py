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


@pytest.mark.parametrize('sets_a,sets_b,expected_a,expected_b',[
    (2,0,1.,0.), (2,1,1.,1.), (1,2,1.,1.), (0,2,0.,1.),
    (3,0,1.,0.), (3,1,1.,1.), (3,2,1.,1.), (2,3,1.,1.), (0,3,0.,1.),
])
def test_winning_a_set_includes_the_player_who_loses_the_match(
    sets_a,sets_b,expected_a,expected_b,
):
    distribution=model.MatchDistribution(
        trials=1,games_a=[0],games_b=[0],sets_a=[sets_a],
        first_set_a=[1],sets_b=[sets_b],
        first_set_games_a=[0],first_set_games_b=[0],
    )
    assert distribution.player_wins_a_set('a')==expected_a
    assert distribution.player_wins_a_set('b')==expected_b
