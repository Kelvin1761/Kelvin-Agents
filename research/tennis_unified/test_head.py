import numpy as np

from .head import PARAMETERS, new_model, symmetric_predict


def test_head_fixed_recipe_and_swap_equivariance():
    rng = np.random.default_rng(20260826)
    x = rng.normal(size=(500, 3))
    y = (x[:, 0] + .5 * x[:, 1] ** 3 > rng.normal(size=500)).astype(int)
    model = new_model()
    assert model.get_params()['early_stopping'] is False
    assert model.get_params()['max_iter'] == PARAMETERS['max_iter'] == 200
    model.fit(np.concatenate((x, -x)), np.concatenate((y, 1 - y)), sample_weight=np.full(1000, .5))
    p = symmetric_predict(model, x)
    assert np.max(np.abs(p + symmetric_predict(model, -x) - 1)) < 1e-10
    assert np.min(p) >= .02 and np.max(p) <= .98
    assert np.std(p) > .05
