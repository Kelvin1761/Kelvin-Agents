"""MS vs C forward test (EXP-20261025-12): frozen config, correct pairing, fixed verdicts."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_ms_forward as f  # noqa: E402

C_ID = "calibrated:C-2026-10-22:06bc5c856a67409ff1d097ebfdc934e8b31ac1b003021068013fead9dad8e1b4"
FROZEN_SHA = "e4a1c1594e48bfcfacf7c2229259a93f5bfcfbb9bd910126e72a6fdd92f8f694"


def test_config_is_frozen():
    assert hashlib.sha256(f.CONFIG_PATH.read_bytes()).hexdigest() == FROZEN_SHA
    cfg, _ = f.load_config()
    assert cfg["comparator_probability_model_id"] == C_ID
    assert (f.HARM_CHECK_EVENTS, f.PRIMARY_EVENTS, f.FINAL_EVENTS) == (150, 400, 800)
    assert (f.SUCCESS_CI, f.BOOTSTRAP_DRAWS, f.BOOTSTRAP_SEED) == (0.975, 4000, 20261026)


def test_ms_prob_matches_formula_and_is_monotone():
    cfg, _ = f.load_config()
    c = cfg["coefficients"]["REB"]
    lg = lambda p: math.log(p / (1 - p))
    z = c["intercept"] + c["beta_market"] * lg(1 / 1.8) + c["beta_season_rate"] * lg(0.6)
    assert abs(f.ms_prob(cfg, "REB", 1.8, 0.6) - 1 / (1 + math.exp(-z))) < 1e-12
    assert f.ms_prob(cfg, "REB", 1.8, 0.7) > f.ms_prob(cfg, "REB", 1.8, 0.6)
    assert f.ms_prob(cfg, "REB", 1.5, 0.6) > f.ms_prob(cfg, "REB", 1.8, 0.6)
    assert f.ms_prob(cfg, "STL", 1.8, 0.6) is None and f.ms_prob(cfg, "PTS", 1.0, 0.6) is None


def _write(root: Path, day: str, rows: list[dict]):
    (root / "ledger").mkdir(parents=True, exist_ok=True)
    with open(root / "ledger" / f"{day}.jsonl", "a", encoding="utf-8") as h:
        for r in rows:
            h.write(json.dumps(r) + "\n")


def _model(day, tag, player, line, *, s_status="ok", s=0.6, last=None, cid=C_ID, with_s=True, p_c=0.55):
    row = {"row_type": "model_obs", "target_date": day, "game_tag": tag, "player": player, "market": "reb",
           "line": line, "side": "over", "snapshot_id": "s1", "snapshot_role": "production",
           "snapshot_created_at": f"{day}T08:00:00+00:00", "post_tip": False, "late_write": False,
           "tip_unknown": False, "season_phase": "EARLY_REGULAR", "probability_model_id": cid,
           "price_at_model": 1.8, "p_final": p_c, "picked": False}
    if with_s:
        row.update(season_rate_status=s_status, season_rate_version="nba_season_rate_S_v1",
                   season_rate_prob_S=s if s_status == "ok" else None,
                   season_rate_inputs={"last_game_date": last or "2026-10-20", "seasons": ["2026-27"]})
    return row


def _settle(day, tag, player, line, y):
    return {"row_type": "settlement", "target_date": day, "game_tag": tag, "player": player, "market": "reb",
            "line": line, "side": "over", "outcome": "hit" if y else "miss", "y": y}


def test_collect_pairs_only_eligible_legs(tmp_path):
    cfg, _ = f.load_config()
    d = "2026-10-27"
    _write(tmp_path, d, [
        _model(d, "A_B", "ok", 5.0), _settle(d, "A_B", "ok", 5.0, 1),
        _model(d, "A_B", "old", 5.0, with_s=False), _settle(d, "A_B", "old", 5.0, 1),
        _model(d, "A_B", "short", 5.0, s_status="insufficient_games"), _settle(d, "A_B", "short", 5.0, 0),
        _model(d, "A_B", "otherc", 5.0, cid="calibrated:C-other"), _settle(d, "A_B", "otherc", 5.0, 1),
        _model(d, "A_B", "open", 5.0),
    ])
    legs, counts = f.collect(tmp_path, "2026-10-26", d, cfg)
    assert [l["player"] for l in legs] == ["ok"]
    assert counts["pre_shadow_snapshot"] == 1 and counts["s_insufficient_games"] == 1
    assert counts["other_c_model"] == 1 and counts["unsettled_or_void"] == 1
    assert counts["c_legs"] == 2   # coverage denominator excludes pre-shadow and other-C legs


def _legs(n_events, per_day, gain):
    """Synthetic paired legs where MS beats C by `gain` in squared error."""
    legs = []
    for e in range(n_events):
        day = f"2026-{11 + e // (per_day * 28):02d}-{1 + (e // per_day) % 28:02d}"
        for k in range(4):
            y = (e + k) % 2
            p_c = 0.6 if y else 0.4
            legs.append({"date": day, "event": f"{day}:{e}", "player": f"p{e}{k}", "stat": "REB", "line": 5,
                         "y": y, "p_c": p_c, "p_ms": p_c + (gain if y else -gain), "p_s": 0.5,
                         "price": 1.8, "picked": False, "leak": False, "cross_season": False})
    return legs


def test_verdict_checkpoints():
    counts = lambda legs: {"c_legs": len(legs)}
    few = _legs(100, 8, 0.05)
    assert f.analyse(few, counts(few), "x")["status"] == "ACCUMULATING"
    good = _legs(400, 8, 0.05)
    r = f.analyse(good, counts(good), "x")
    assert r["look"] == "primary" and r["brier_ci975"][1] < 0
    bad = _legs(160, 8, -0.05)
    assert f.analyse(bad, counts(bad), "x")["status"] == "REJECT_HARM"
    worse = _legs(400, 8, -0.05)
    assert f.analyse(worse, counts(worse), "x")["status"] == "REJECT"


def test_guards_block_judgement():
    legs = _legs(400, 8, 0.05)
    assert f.analyse(legs, {"c_legs": len(legs) * 2}, "x")["status"] == "INVALID_DATA"   # coverage 50%
    legs[0]["leak"] = True
    assert f.analyse(legs, {"c_legs": len(legs)}, "x")["status"] == "INVALID_DATA"
    assert f.analyse([], {}, "x")["status"] == "AWAITING_DATA"


FROZEN_V2_SHA = "cbc78f1e03662d22bdd6aff39549482223ca758013189d398da54156f020f96a"


def test_v2_config_is_frozen_and_reads_v2_fields(tmp_path):
    assert hashlib.sha256(f.CONFIG_V2_PATH.read_bytes()).hexdigest() == FROZEN_V2_SHA
    cfg, _ = f.load_config(f.CONFIG_V2_PATH)
    assert cfg["season_rate_version"] == "nba_season_rate_S_v2" and cfg["comparator_probability_model_id"] == C_ID
    d = "2026-10-28"
    v2 = _model(d, "A_B", "v2ok", 5.0, with_s=False)
    v2.update(season_rate_v2_status="ok", season_rate_v2_version="nba_season_rate_S_v2", season_rate_v2_prob_S=0.6,
              season_rate_v2_inputs={"last_game_date": "2026-10-26", "seasons": ["2026-27"]})
    v1_only = _model(d, "A_B", "v1only", 5.0)          # written before the v2 shadow existed
    _write(tmp_path, d, [v2, _settle(d, "A_B", "v2ok", 5.0, 1), v1_only, _settle(d, "A_B", "v1only", 5.0, 0)])
    legs, counts = f.collect(tmp_path, "2026-10-26", d, cfg)
    assert [l["player"] for l in legs] == ["v2ok"] and counts["pre_shadow_snapshot"] == 1
    assert abs(legs[0]["p_ms"] - f.ms_prob(cfg, "REB", 1.8, 0.6)) < 1e-12
    legs1, _ = f.collect(tmp_path, "2026-10-26", d, f.load_config()[0])   # v1 untouched by v2 fields
    assert [l["player"] for l in legs1] == ["v1only"]


def test_reb3pm_subset_is_frozen_and_only_scores_its_stats(tmp_path):
    assert hashlib.sha256(f.CONFIG_V2_REB3PM_PATH.read_bytes()).hexdigest() == \
        "be37d53912d9154e1f51b9b6c5b4b0156737dfad1a78b4b2900c1193565e5c5c"
    cfg, _ = f.load_config(f.CONFIG_V2_REB3PM_PATH)
    assert cfg["stats"] == ["REB", "FG3M"] and cfg["coefficients"] == f.load_config(f.CONFIG_V2_PATH)[0]["coefficients"]
    d = "2026-10-28"
    rows = []
    for player, market in (("r", "reb"), ("t", "fg3m"), ("p", "pts")):
        m = _model(d, "A_B", player, 3.0, with_s=False)
        m.update(market=market, season_rate_v2_status="ok", season_rate_v2_version="nba_season_rate_S_v2",
                 season_rate_v2_prob_S=0.6, season_rate_v2_inputs={"last_game_date": "2026-10-26"})
        s = _settle(d, "A_B", player, 3.0, 1); s["market"] = market
        rows += [m, s]
    _write(tmp_path, d, rows)
    legs, counts = f.collect(tmp_path, "2026-10-26", d, cfg)
    assert sorted(l["stat"] for l in legs) == ["FG3M", "REB"] and counts["stat_out_of_scope"] == 1
    assert counts["c_legs"] == 2   # out-of-scope legs never dilute the coverage guard


def test_v3_config_is_frozen_and_reads_v3_fields():
    assert hashlib.sha256(f.CONFIG_V3_PATH.read_bytes()).hexdigest() == \
        "d4ff377b554367f3e9af95c12eaa54baa38d3534e374c462f8b7be4e3cfa9c8b"
    cfg, _ = f.load_config(f.CONFIG_V3_PATH)
    assert cfg["season_rate_version"] == "nba_season_rate_S_v3"
    assert cfg["season_rate_fields"]["prob"] == "season_rate_v3_prob_S" and "stats" not in cfg
