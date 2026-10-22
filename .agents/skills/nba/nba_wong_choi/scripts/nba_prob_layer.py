"""Calibrated milestone-leg probability (EXP-20261022-03, candidate C).

Replaces the 10-factor engine's final probability for player milestone legs. The old
engine was 13.6pp over-confident in the p>=0.8 zone on an independent holdout (slope
0.52); this layer is anchored on the bookmaker's own price and uses L10 only as a small
correction. Coefficients live in resources/nba_prob_layer.json (set "enabled": false to
fall back to the legacy engine, or env NBA_WC_PROB_LAYER=0).
"""
import json
import math
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "nba_prob_layer.json")
_CACHE = {}


def load_config(path=None):
    path = path or _CONFIG_PATH
    if path not in _CACHE:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                _CACHE[path] = json.load(handle)
        except (OSError, ValueError):
            _CACHE[path] = None
    return _CACHE[path]


def enabled(config=None):
    if os.environ.get("NBA_WC_PROB_LAYER", "").strip().lower() in {"0", "false", "off"}:
        return False
    config = config if config is not None else load_config()
    return bool(config and config.get("enabled"))


def _logit(p):
    return math.log(p / (1.0 - p))


def calibrated_prob(stat_key, odds, hit_l10_pct, config=None):
    """Return the calibrated hit probability in percent, or None when the layer
    cannot score this leg (disabled, unknown stat, missing/invalid price or hit rate)."""
    config = config if config is not None else load_config()
    if not enabled(config):
        return None
    intercept = (config.get("intercepts") or {}).get(stat_key)
    try:
        odds = float(odds)
        hit = float(hit_l10_pct) / 100.0
    except (TypeError, ValueError):
        return None
    if intercept is None or odds <= 1.0 or math.isnan(hit):
        return None
    m_lo, m_hi = config["clip_market"]
    h_lo, h_hi = config["clip_l10"]
    market = min(max(1.0 / odds, m_lo), m_hi)
    l10 = min(max(hit, h_lo), h_hi)
    z = intercept + config["beta_market"] * _logit(market) + config["gamma_l10"] * _logit(l10)
    return round(100.0 / (1.0 + math.exp(-z)), 1)
