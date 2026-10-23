#!/usr/bin/env python3
"""NBA fit layer (candidate A of EXP-20261021-05) — reference implementation, SHADOW use only.

Probability that a player reaches milestone `N+` (stat >= N):
  mu      = max(0.05, season_stat_total / season_minutes_total * prior10_mean_min)
  p_count = P(X >= N), X ~ NegBin (PTS, alpha from the model file) or Poisson (REB/AST/FG3M)
  p       = sigmoid(a_s + b_s * logit(clip(p_count, 0.01, 0.99))), clipped to [0.01, 0.99]

Point-in-time contract (caller): season_stat_total, season_minutes_total and prior10_mean_min must use
only games of the SAME season played STRICTLY BEFORE the game date, counting only games with MIN > 0;
prior10_mean_min = mean MIN of the last 10 such games (>= 10 prior games, prior-10 mean MIN >= 20 is
the validated population).

Runtime needs only the standard library (math, json, hashlib) — no scipy/numpy — so it runs under the
scheduler's /usr/bin/python3 3.9. The coefficient file is pinned by sha256: on a missing file or a
hash mismatch the loader returns (None, reason) and callers must leave the shadow field empty.
"""
import hashlib
import json
import math
import os

MODEL_ID = "nba_fit_layer_A_v1"
MODEL_FILENAME = "nba_fit_layer_A_v1.json"
EXPECTED_SHA256 = "7e74022cc7dfa37938dc3046b665d17af4c6279ab64f720fc5ae5af65227e56f"
DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", MODEL_FILENAME)
CLIP_LO, CLIP_HI = 0.01, 0.99
STAT_ALIASES = {"PTS": "PTS", "POINTS": "PTS", "REB": "REB", "REBOUNDS": "REB", "AST": "AST", "ASSISTS": "AST",
                "FG3M": "FG3M", "3PM": "FG3M", "THREES": "FG3M", "THREES_MADE": "FG3M"}

_CACHE = {}


def load_model(path=None, expected_sha256=EXPECTED_SHA256):
    """Return (model_dict, None) or (None, reason). Never raises."""
    path = os.path.abspath(path or DEFAULT_MODEL_PATH)
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        return None, f"model file unreadable: {path} ({exc.__class__.__name__})"
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        return None, f"sha256 mismatch: expected {expected_sha256[:12]}…, got {digest[:12]}…"
    try:
        model = json.loads(raw.decode("utf-8"))
        if model.get("model_id") != MODEL_ID:
            return None, f"unexpected model_id {model.get('model_id')!r}"
        for s in ("PTS", "REB", "AST", "FG3M"):
            model["count_model"][s]["alpha"], model["recalibration"][s]["a"], model["recalibration"][s]["b"]
    except (ValueError, KeyError, TypeError) as exc:
        return None, f"model file malformed: {exc.__class__.__name__}"
    return model, None


def default_model():
    if "m" not in _CACHE:
        _CACHE["m"] = load_model()
    return _CACHE["m"]


def _sf(n, mu, alpha):
    """P(X >= n) for integer n >= 1 via the pmf recursion (exact up to float rounding)."""
    if alpha > 0:
        r = 1.0 / alpha
        p = 1.0 / (1.0 + alpha * mu)
        q = 1.0 - p
        pmf = math.exp(r * math.log(p))
        step = lambda k: (r + k) / (k + 1.0) * q
    else:
        pmf = math.exp(-mu)
        step = lambda k: mu / (k + 1.0)
    cdf = 0.0
    for k in range(n):               # sum pmf(0..n-1)
        cdf += pmf
        pmf *= step(k)
    return min(1.0, max(0.0, 1.0 - cdf))


def _clip(p):
    return min(CLIP_HI, max(CLIP_LO, p))


def fit_prob_A(stat, line, season_stat_total, season_minutes_total, prior10_mean_min, model=None):
    """Return (probability, None) or (None, reason)."""
    if model is None:
        model, reason = default_model()
        if model is None:
            return None, reason
    s = STAT_ALIASES.get(str(stat).upper())
    if s is None:
        return None, f"unsupported stat {stat!r}"
    try:
        n = int(line)
        if n != line or n < 1:
            return None, f"line must be an integer >= 1, got {line!r}"
        tot, mins, m10 = float(season_stat_total), float(season_minutes_total), float(prior10_mean_min)
    except (TypeError, ValueError):
        return None, "non-numeric input"
    if not (math.isfinite(tot) and math.isfinite(mins) and math.isfinite(m10)) or mins <= 0 or m10 <= 0 or tot < 0:
        return None, "invalid season totals or prior-10 minutes"
    mu = max(0.05, tot / mins * m10)
    p_count = _clip(_sf(n, mu, float(model["count_model"][s]["alpha"])))
    z = math.log(p_count / (1.0 - p_count))
    rc = model["recalibration"][s]
    p = 1.0 / (1.0 + math.exp(-(rc["a"] + rc["b"] * z)))
    return _clip(p), None


def p_fit_A(stat, line, season_stat_total, season_minutes_total, prior10_mean_min, model=None):
    """Probability in [0.01, 0.99], or None when the model file fails verification / inputs invalid."""
    return fit_prob_A(stat, line, season_stat_total, season_minutes_total, prior10_mean_min, model)[0]
