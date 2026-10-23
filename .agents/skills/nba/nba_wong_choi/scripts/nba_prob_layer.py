"""Calibrated milestone-leg probability (EXP-20261022-03, candidate C).

Replaces the 10-factor engine's final probability for player milestone legs. The old
engine was 13.6pp over-confident in the p>=0.8 zone on an independent holdout (slope
0.52); this layer is anchored on the bookmaker's own price and uses L10 only as a small
correction. Coefficients live in resources/nba_prob_layer.json (set "enabled": false to
fall back to the legacy engine, or env NBA_WC_PROB_LAYER=0).
"""
import json
import hashlib
import math
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "nba_prob_layer.json")
_CACHE = {}


class ProbabilityConfigError(ValueError):
    """An intended live probability model is unavailable or invalid."""


def validate_config(config):
    if not isinstance(config, dict) or not isinstance(config.get("enabled"), bool):
        raise ProbabilityConfigError("probability config needs a boolean enabled field")
    if not config["enabled"]:
        return config
    if not isinstance(config.get("version"), str) or not config["version"].strip():
        raise ProbabilityConfigError("probability config version is missing")
    intercepts = config.get("intercepts")
    if not isinstance(intercepts, dict) or set(intercepts) != {"PTS", "REB", "AST", "FG3M"}:
        raise ProbabilityConfigError("probability intercepts must cover PTS/REB/AST/FG3M")
    numbers = list(intercepts.values()) + [config.get("beta_market"), config.get("gamma_l10")]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in numbers):
        raise ProbabilityConfigError("probability coefficients must be finite numbers")
    for name in ("clip_market", "clip_l10"):
        clip = config.get(name)
        if (not isinstance(clip, (tuple, list)) or len(clip) != 2
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in clip)
                or not 0 < clip[0] < clip[1] < 1):
            raise ProbabilityConfigError(f"{name} must satisfy 0 < low < high < 1")
    return config


def load_config(path=None):
    path = path or _CONFIG_PATH
    if path not in _CACHE:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (OSError, ValueError) as exc:
            raise ProbabilityConfigError(f"cannot load probability config {path}: {exc}") from exc
        _CACHE[path] = validate_config(config)
    return _CACHE[path]


def enabled(config=None):
    if os.environ.get("NBA_WC_PROB_LAYER", "").strip().lower() in {"0", "false", "off"}:
        return False
    config = config if config is not None else load_config()
    return validate_config(config)["enabled"]


def probability_model_id(config=None):
    """Identity of the actual formula/coefficients; descriptive notes do not affect it."""
    if not enabled(config):
        return None
    config = config if config is not None else load_config()
    fields = ("version", "intercepts", "beta_market", "gamma_l10", "clip_market", "clip_l10")
    raw = json.dumps({name: config[name] for name in fields}, sort_keys=True, allow_nan=False).encode()
    return f"calibrated:{config['version']}:{hashlib.sha256(raw).hexdigest()}"


def _logit(p):
    return math.log(p / (1.0 - p))


def calibrated_prob(stat_key, odds, hit_l10_pct, config=None):
    """Return the calibrated hit probability in percent, or None when the layer
    cannot score this leg (disabled, unknown stat, missing/invalid price or hit rate)."""
    if not enabled(config):
        return None
    config = config if config is not None else load_config()
    intercept = (config.get("intercepts") or {}).get(stat_key)
    try:
        odds = float(odds)
        hit = float(hit_l10_pct) / 100.0
    except (TypeError, ValueError):
        return None
    if intercept is None or not math.isfinite(odds) or odds <= 1.0 or not math.isfinite(hit) or not 0 <= hit <= 1:
        return None
    m_lo, m_hi = config["clip_market"]
    h_lo, h_hi = config["clip_l10"]
    market = min(max(1.0 / odds, m_lo), m_hi)
    l10 = min(max(hit, h_lo), h_hi)
    z = intercept + config["beta_market"] * _logit(market) + config["gamma_l10"] * _logit(l10)
    prob = 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))
    return round(100.0 * prob, 1)
