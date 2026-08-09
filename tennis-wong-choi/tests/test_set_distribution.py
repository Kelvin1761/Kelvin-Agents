"""Set-outcome distribution model + Set Betting pricing/settlement."""


def test_outcome_distribution_orientation_and_sanity():
    from tennis_wc.modelling.set_distribution import outcome_distribution

    d = outcome_distribution(0.75)
    assert abs(sum(d[k] for k in ("a20", "a21", "b21", "b20")) - 1.0) < 0.02
    assert d["a20"] > d["a21"] > d["b21"]          # favourite most likely 2-0
    assert d["a_set1"] > 0.6                       # favourite takes set 1 more often
    mirror = outcome_distribution(0.25)
    assert abs(mirror["b20"] - d["a20"]) < 1e-9    # symmetric orientation
    assert abs(mirror["a_set1"] - (1 - d["a_set1"])) < 1e-9


def test_three_sets_far_below_old_heuristic_for_coinflips():
    from tennis_wc.modelling.set_distribution import three_sets_probability

    # Empirical reality: ~38% three-setters for a coin flip (old heuristic said 62%).
    assert 0.30 < three_sets_probability(0.5) < 0.45


def test_win_at_least_one_set_bounds():
    from tennis_wc.modelling.set_distribution import win_at_least_one_set_probability

    strong = win_at_least_one_set_probability(0.85)
    weak = win_at_least_one_set_probability(0.15)
    assert strong > 0.85 and weak < 0.65 and strong > weak


def test_set_score_probability():
    from tennis_wc.modelling.set_distribution import set_score_probability

    assert set_score_probability(0.8, 0) > set_score_probability(0.8, 1)
    assert set_score_probability(0.8, 2) is None   # BO5 not supported


def test_settle_set_betting():
    from tennis_wc.betting.ledger import _settle_set_betting

    score = {"player_a_sets": 2, "player_b_sets": 1}
    row = {"selection_name": "Iga Swiatek 2-1", "player_a_name": "Iga Swiatek", "player_b_name": "Aryna Sabalenka"}
    assert _settle_set_betting(row, score) is True
    row["selection_name"] = "Iga Swiatek 2-0"
    assert _settle_set_betting(row, score) is False
    row["selection_name"] = "Aryna Sabalenka 2-1"
    assert _settle_set_betting(row, score) is False
    # BO5 / junk selections are not gradeable
    assert _settle_set_betting({"selection_name": "Iga Swiatek 3-1", "player_a_name": "Iga Swiatek", "player_b_name": "X"}, score) is None
    assert _settle_set_betting(row, {"player_a_sets": 3, "player_b_sets": 1}) is None


def test_set_betting_pricing_only_full_match_rows():
    from tennis_wc.reports.daily_report import _set_betting_probability

    base = {"player_a_name": "Iga Swiatek", "player_b_name": "Aryna Sabalenka"}
    priced = _set_betting_probability({**base, "market_name": "Set Betting", "selection_name": "Iga Swiatek 2-0"}, 0.75, 0.25)
    assert priced is not None and 0.4 < priced["probability"] < 0.6
    # dog 2-0 must be much less likely
    dog = _set_betting_probability({**base, "market_name": "Set Betting", "selection_name": "Aryna Sabalenka 2-0"}, 0.75, 0.25)
    assert dog is not None and dog["probability"] < 0.25
    # per-set correct-score rows sharing the key stay unpriced
    assert _set_betting_probability({**base, "market_name": "Correct Score 1st Set", "selection_name": "6-4"}, 0.75, 0.25) is None
    # BO5 selections stay unpriced
    assert _set_betting_probability({**base, "market_name": "Set Betting", "selection_name": "Iga Swiatek 3-0"}, 0.75, 0.25) is None
