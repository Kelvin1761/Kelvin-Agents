"""Set-outcome distribution model + Set Betting pricing/settlement."""


def test_outcome_distribution_orientation_and_sanity():
    from tennis_wc.model.sets import outcome_distribution

    d = outcome_distribution(0.75)
    assert abs(sum(d[k] for k in ("a20", "a21", "b21", "b20")) - 1.0) < 0.02
    assert d["a20"] > d["a21"] > d["b21"]          # favourite most likely 2-0
    assert d["a_set1"] > 0.6                       # favourite takes set 1 more often
    mirror = outcome_distribution(0.25)
    assert abs(mirror["b20"] - d["a20"]) < 1e-9    # symmetric orientation
    assert abs(mirror["a_set1"] - (1 - d["a_set1"])) < 1e-9
