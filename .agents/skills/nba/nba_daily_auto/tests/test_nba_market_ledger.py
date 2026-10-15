"""Synthetic fixtures only: every ledger write goes to a pytest tmp_path."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_market_ledger as ledger  # noqa: E402

SYDNEY = ledger.SYDNEY
DAY = "2026-10-22"  # EARLY_REGULAR, not preseason
TAG = "BOS_LAL"
TIP = datetime(2026, 10, 22, 13, 0, tzinfo=SYDNEY)


@pytest.fixture
def root(tmp_path, monkeypatch):
    target = tmp_path / "ledger_root"
    monkeypatch.setenv(ledger.ENV_ROOT, str(target))
    return target


def _odds(folder: Path, extraction: str, prices: dict[str, str], *, tip: datetime = TIP) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Sportsbet_Odds_{TAG}.json"
    path.write_text(json.dumps({
        "source": "Sportsbet_Extractor",
        "extraction_time": extraction,
        "target_analysis_date": DAY,
        "event_start_time": tip.isoformat(),
        "player_props": {
            "points": {"Jayson Tatum": {"lines": prices}},
            "rebounds": {"Jayson Tatum": {"lines": {"8": "1.9", "8.5": "1.8"}}},
        },
    }), encoding="utf-8")
    return path


def _snapshot(folder: Path, *, role: str, created: datetime, extraction: str,
              legs: list[dict], combos: list[dict] | None = None, sidecar: bool = True,
              tamper: bool = False, prices: dict[str, str] | None = None) -> Path:
    snap = folder / "_prediction_snapshots" / created.strftime("%Y%m%d-%H%M%S-%f")
    snap.mkdir(parents=True)
    _odds(snap, extraction, prices or {"20": "1.8", "25": "3.2"})
    report = snap / f"Game_{TAG}_Full_Analysis.md"
    report.write_text("synthetic report " + role, encoding="utf-8")
    (snap / "manifest.json").write_text(json.dumps({
        "snapshot_role": role, "created_at": created.isoformat(), "model_commit": "fixture",
        "season_context": {"season_phase": "EARLY_REGULAR"},
    }), encoding="utf-8")
    if sidecar:
        sha = hashlib.sha256(report.read_bytes()).hexdigest()
        (snap / f"Game_{TAG}_Full_Analysis.md{ledger.SIDECAR_SUFFIX}").write_text(json.dumps({
            "schema_version": "nba-market-eval-legs/v1",
            "report_sha256": "tampered" if tamper else sha,
            "odds_extraction_time": extraction,
            "legs": legs, "combos": combos or [],
        }), encoding="utf-8")
    return snap


LEGS = [
    {"player": "Jayson Tatum", "team": "BOS", "market": "pts", "line": 20.0, "side": "over",
     "price": 1.8, "p_final": 0.62, "p_hit_rate_10f": 0.6, "p_ml": 0.55, "p_monte_carlo": 0.58,
     "picked": True, "picked_in": ["2"]},
    {"player": "Jayson Tatum", "team": "BOS", "market": "pts", "line": 25.0, "side": "over",
     "price": 3.2, "p_final": 0.30, "p_hit_rate_10f": 0.3, "p_ml": None, "p_monte_carlo": 0.33,
     "picked": False, "picked_in": []},
    {"player": "Bench Guy", "team": "LAL", "market": "reb", "line": 4.0, "side": "over",
     "price": 2.0, "p_final": 0.5, "p_hit_rate_10f": 0.5, "p_ml": 0.5, "p_monte_carlo": 0.5,
     "picked": False, "picked_in": []},
]
COMBO = [{
    "combo_id": "2", "product_of_leg_prices": 5.76, "naive_joint_prob": 0.186,
    "adjusted_joint_prob": 0.17, "correlation_penalty": 0.08,
    "sportsbet_sgm_price": None, "sportsbet_sgm_status": "not_scraped",
    "sim_status": "ok", "sim_model_version": "sgm-joint-sim/v1", "sim_seed": 7, "sim_n": 10000,
    "sim_joint_prob": 0.21, "sim_independent_prob": 0.2, "sim_correlation_lift": 1.05,
    "sim_scaled_joint_prob": 0.1953,
    "legs": [
        {"player": "Jayson Tatum", "market": "pts", "line": 20.0, "side": "over", "price": 1.8},
        {"player": "Jayson Tatum", "market": "pts", "line": 25.0, "side": "over", "price": 3.2},
    ],
}]


def _brief(path: Path) -> Path:
    path.write_text(json.dumps({
        "_version": "RESULTS_BRIEF_V1", "date": "2026-10-21", "total_games": 1,
        "games": [{
            "status": "Final", "away": {"team": "BOS"}, "home": {"team": "LAL"},
            "players": [
                {"name": "Jayson Tatum", "minutes": "PT36M", "pts": 27, "reb": 9, "ast": 5, "fg3m": 3},
                {"name": "Bench Guy", "minutes": "PT00M00.00S", "pts": 0, "reb": 0, "ast": 0, "fg3m": 0},
            ],
        }],
    }), encoding="utf-8")
    return path


def test_tests_cannot_reach_the_production_ledger(monkeypatch):
    monkeypatch.delenv(ledger.ENV_ROOT, raising=False)
    with pytest.raises(ledger.LedgerIsolationError):
        ledger.ledger_root()


def test_price_observations_flag_post_tip_and_dedupe(root, tmp_path):
    folder = tmp_path / "live"
    before = TIP - timedelta(hours=6)
    _odds(folder, "2026-10-21 21:00:00", {"20": "1.9"})
    assert ledger.record_prices(folder, DAY, context="t", now=before) == 2
    assert ledger.record_prices(folder, DAY, context="t", now=before) == 0  # idempotent
    _odds(folder, "2026-10-22 13:05:00", {"20": "1.5"})
    ledger.record_prices(folder, DAY, context="t", now=TIP + timedelta(minutes=6))
    rows = [r for r in ledger.read_rows(root, DAY) if r["market"] == "pts"]
    assert [(r["price"], r["post_tip"], r["late_write"]) for r in rows] == [
        (1.9, False, False), (1.5, True, True),
    ]
    # Non-milestone (x.5) lines are never evaluated, hence never recorded.
    assert all(float(r["line"]).is_integer() for r in ledger.read_rows(root, DAY))


def test_late_snapshot_write_is_flagged_and_never_counts(root, tmp_path):
    snap = _snapshot(tmp_path / "live", role="production", created=TIP - timedelta(hours=10),
                     extraction="2026-10-22 00:30:00", legs=LEGS)
    counts = ledger.record_snapshot(snap, DAY, now=TIP + timedelta(hours=1))
    assert counts["model_obs"] == 3
    rows = ledger.read_rows(root, DAY)
    assert rows and all(r["late_write"] for r in rows)
    report = ledger.evaluate(root=root)
    assert report["counts"]["legs_without_pretip_model"] == 3
    assert report["overall"]["legs"] == 0


def test_missing_or_mismatched_sidecar_is_recorded_as_missed(root, tmp_path):
    for index, kwargs in enumerate(({"sidecar": False}, {"tamper": True})):
        snap = _snapshot(tmp_path / f"live{index}", role="production",
                         created=TIP - timedelta(hours=10 - index), extraction="2026-10-22 00:30:00",
                         legs=LEGS, **kwargs)
        ledger.record_snapshot(snap, DAY, now=TIP - timedelta(hours=9))
    reasons = sorted(r["reason"] for r in ledger.read_rows(root, DAY) if r["row_type"] == "model_missing")
    assert reasons == ["sidecar_absent", "sidecar_report_mismatch"]
    assert not [r for r in ledger.read_rows(root, DAY) if r["row_type"] == "model_obs"]


def _full_day(root: Path, tmp_path: Path) -> None:
    live = tmp_path / "live"
    _odds(live, "2026-10-21 21:00:00", {"20": "2.0", "25": "3.5"})
    ledger.record_prices(live, DAY, context="warmup", now=TIP - timedelta(hours=16))
    warm = _snapshot(live, role="warmup", created=TIP - timedelta(hours=15),
                     extraction="2026-10-21 21:00:00", prices={"20": "2.0", "25": "3.5"},
                     legs=[{**leg, "p_final": 0.99} for leg in LEGS])
    ledger.record_snapshot(warm, DAY, now=TIP - timedelta(hours=15))
    prod = _snapshot(live, role="production", created=TIP - timedelta(hours=12),
                     extraction="2026-10-22 00:30:00", legs=LEGS, combos=COMBO)
    ledger.record_snapshot(prod, DAY, now=TIP - timedelta(hours=12))
    brief = _brief(tmp_path / "Results_Brief_2026-10-21.json")
    ledger.settle(DAY, brief, now=TIP + timedelta(hours=5))


def test_settlement_from_box_scores_first_write_wins(root, tmp_path):
    _full_day(root, tmp_path)
    settled = {(r["player"], r["market"], r["line"]): r["outcome"]
               for r in ledger.read_rows(root, DAY) if r["row_type"] == "settlement"}
    assert settled == {
        ("Jayson Tatum", "pts", 20.0): "hit",
        ("Jayson Tatum", "pts", 25.0): "hit",
        ("Bench Guy", "reb", 4.0): "void",
    }
    again = ledger.settle(DAY, tmp_path / "Results_Brief_2026-10-21.json")
    assert again == {"candidates": 0, "appended": 0}


def test_evaluation_metrics_clv_splits_and_sgm(root, tmp_path):
    _full_day(root, tmp_path)
    report = ledger.evaluate(root=root)
    overall = report["overall"]
    assert overall["legs"] == 3 and overall["settled"] == 2  # void excluded
    final = overall["variants"]["p_final"]
    raw = final["market_raw_close"]
    # Production snapshot (not the unpublished warm-up p=0.99) is the model of record.
    expected_model = ((0.62 - 1) ** 2 + (0.30 - 1) ** 2) / 2
    expected_market = ((1 / 1.8 - 1) ** 2 + (1 / 3.2 - 1) ** 2) / 2
    assert raw["n"] == 2
    assert math.isclose(raw["brier_model"], round(expected_model, 5))
    assert math.isclose(raw["brier_market"], round(expected_market, 5))
    assert raw["n_required_basis"]["sd_source"] == "assumed"
    assert raw["n_required"] == ledger.required_n(ledger.ASSUMED_PAIRED_SD, ledger.ASSUMED_BRIER_IMPROVEMENT)
    assert final["market_devig_close"] == {"n": 0}
    assert report["verdict_status"] == "market_not_devigged"
    clv = overall["clv_earliest_vs_close"]
    assert clv["n"] == 2
    assert math.isclose(clv["mean"], round(((2.0 / 1.8 - 1) + (3.5 / 3.2 - 1)) / 2, 5))
    assert report["by_picked"]["picked"]["legs"] == 1
    assert report["by_picked"]["not_picked"]["legs"] == 2
    assert set(report["by_market"]) == {"pts", "reb"}
    # ML is missing on the 25+ leg, so its comparison only has one leg.
    assert overall["variants"]["p_ml"]["market_raw_close"]["n"] == 1
    sgm = report["sgm"]
    assert sgm["counts"] == {"combos": 1, "settled": 1}
    assert sgm["model_adjusted"] == {"n": 1, "brier": round((0.17 - 1) ** 2, 5), "mean_p": 0.17, "realised_rate": 1.0}
    assert sgm["sportsbet_sgm_implied"]["n"] == 0
    # N1 shadow joint probabilities are logged side by side, never picked from.
    assert sgm["model_sim_joint"] == {"n": 1, "brier": round((0.21 - 1) ** 2, 5), "mean_p": 0.21, "realised_rate": 1.0}
    assert sgm["model_sim_scaled"]["mean_p"] == 0.1953
    row = next(r for r in ledger.read_rows(root, DAY)
               if r["row_type"] == "sgm_obs" and r["snapshot_role"] == "production")
    assert (row["sim_status"], row["sim_seed"], row["sim_correlation_lift"]) == ("ok", 7, 1.05)


def test_preseason_rows_are_excluded_by_default(root, tmp_path):
    _full_day(root, tmp_path)
    path = ledger.ledger_path(root, DAY)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text("".join(json.dumps({**r, "season_phase": "PRESEASON"}) + "\n" for r in rows))
    assert ledger.evaluate(root=root)["overall"]["legs"] == 0
    assert ledger.evaluate(root=root, include_preseason=True)["overall"]["legs"] == 3


def test_devig_and_power_math():
    assert math.isclose(ledger.devig_two_way_proportional(1.9, 1.9), 0.5)
    assert math.isclose(ledger.devig_two_way_proportional(1.5, 2.5), (1 / 1.5) / (1 / 1.5 + 1 / 2.5))
    assert ledger.required_n(0.05, 0.002) == math.ceil((1.96 * 0.05 / 0.002) ** 2) == 2401
    with pytest.raises(ValueError):
        ledger.required_n(0.05, 0.0)


# ── scheduler wiring ────────────────────────────────────────────────────────

import nba_daily_schedule as schedule  # noqa: E402


class _Log:
    def __init__(self) -> None:
        self.steps = []

    def step(self, name, status, **detail):
        self.steps.append((name, status, detail))


def test_odds_refresh_records_price_observations(root, tmp_path):
    folder = tmp_path / f"{DAY} NBA Analysis"

    def fake_scrape(command, **_kwargs):
        _odds(folder, "2026-10-22 00:30:00", {"20": "1.85"})
        return subprocess.CompletedProcess(command, 0, "", "")

    log = _Log()
    with mock.patch.object(schedule, "_run", side_effect=fake_scrape):
        schedule.refresh_sportsbet_odds(folder, DAY, protected_tags=set(), log=log,
                                        event_starts={TAG: TIP})
    assert ("market_ledger", "ok") in [(n, s) for n, s, _ in log.steps]
    rows = ledger.read_rows(root, DAY)
    assert {r["tip_source"] for r in rows} == {"official_schedule"}
    assert any(r["price"] == 1.85 for r in rows)


def test_ledger_failures_never_fail_the_run(tmp_path):
    log = _Log()
    schedule._market_ledger(log, "boom", lambda: 1 / 0)
    assert log.steps[-1][1] == "failed"
    schedule._settle_market_ledger(tmp_path, DAY, log)  # env unset under pytest
    assert log.steps[-1][:2] == ("market_ledger", "skipped")


def test_postgame_settlement_reports_missing_brief(root, tmp_path):
    log = _Log()
    schedule._settle_market_ledger(tmp_path, DAY, log)
    assert log.steps[-1][1] == "ok"
    assert log.steps[-1][2]["detail"]["status"] == "results_brief_missing"


def test_snapshot_copies_optional_market_sidecar(tmp_path):
    folder = tmp_path / f"{DAY} NBA Analysis"
    folder.mkdir()
    (folder / f"Sportsbet_Odds_{TAG}.json").write_text(json.dumps({"target_analysis_date": DAY}))
    (folder / f"nba_game_data_{TAG}.json").write_text("{}\n")
    (folder / f"Game_{TAG}_Full_Analysis.md").write_text("A" * 2500)
    (folder / f"Game_{TAG}_Full_Analysis.md{ledger.SIDECAR_SUFFIX}").write_text("{}")
    (folder / "NBA_All_SGM_Report.txt").write_text("SGM\n")
    (folder / "NBA_Banker_Report.txt").write_text("BANKER\n")
    snapshot = schedule.create_prediction_snapshot(folder, DAY, [TAG])
    assert (snapshot / f"Game_{TAG}_Full_Analysis.md{ledger.SIDECAR_SUFFIX}").is_file()


# ── generator sidecar ───────────────────────────────────────────────────────

def test_generator_sidecar_observes_without_changing_values():
    scripts = AUTO_DIR.parent / "nba_wong_choi" / "scripts"
    sys.path.insert(0, str(scripts))
    import generate_nba_reports as gen

    card = {
        "name": "Jayson Tatum", "team": "BOS", "category": "points",
        "line_analysis": {
            "20": {"line": 20.0, "line_display": "20+", "odds": "1.8", "det_prob": 64.0,
                   "ml_prob": 0.55, "estimated_prob": 61.0, "hit_l10": 70.0, "engine": "hybrid"},
            "25": {"line": 25.0, "line_display": "25+", "odds": "3.2", "det_prob": 30.0,
                   "ml_prob": None, "estimated_prob": 30.0, "hit_l10": 30.0, "engine": "legacy"},
        },
    }
    combo_leg = {"market_type": gen.PLAYER_MARKET, "player": "Jayson Tatum", "team": "BOS",
                 "category": "PTS", "line_val": 20.0, "odds": 1.8, "estimated_prob": 61.0,
                 "desc": "Jayson Tatum (BOS) PTS 20+"}
    capture = {
        "mc_results": [{"player": "Jayson Tatum", "team": "BOS", "category": "PTS",
                        "line_display": "20+", "mc_prob": 66.0}],
        "combos": {"1": [], "2": [combo_leg], "3": [], "X": []},
        "sgm_sim": {"2": {"sim_status": "ok", "sim_joint_prob": 0.6, "sim_correlation_lift": 1.1}},
    }
    payload = gen.build_market_eval_sidecar("report", {"extraction_time": "x"}, {}, [card], capture, "hybrid")
    by_line = {leg["line"]: leg for leg in payload["legs"]}
    assert by_line[20.0]["p_hit_rate_10f"] == 0.64
    assert by_line[20.0]["p_ml"] == 0.55
    assert by_line[20.0]["p_final"] == 0.61
    assert by_line[20.0]["p_monte_carlo"] == 0.66
    assert by_line[20.0]["picked"] is True and by_line[20.0]["picked_in"] == ["2"]
    assert by_line[25.0]["p_ml"] is None and by_line[25.0]["picked"] is False
    assert payload["combos"][0]["sportsbet_sgm_status"] == "not_scraped"
    assert payload["combos"][0]["sim_joint_prob"] == 0.6
    assert payload["combos"][0]["sim_scaled_joint_prob"] == round(0.61 * 1.1, 4)
    assert payload["report_sha256"] == hashlib.sha256(b"report").hexdigest()


# ── two-way (Over/Under) de-vig ─────────────────────────────────────────────

def test_extractor_keeps_under_only_in_the_two_way_block():
    sys.path.insert(0, str(AUTO_DIR.parent / "nba_data_extractor" / "scripts"))
    import claw_sportsbet_odds as claw

    extractor = claw.SportsbetNBAExtractor(target_date=DAY)
    cleaned = {"Points": {
        "Jayson Tatum - Points": {"Jayson Tatum Over +24.5": "1.96", "Jayson Tatum Under +24.5": "1.8"},
        "To Score 25+ Points": {"Jayson Tatum": "1.93", "Cade Cunningham": "2.4"},
    }}
    data = extractor._format_as_sportsbet("Boston Celtics At Los Angeles Lakers", "BOS", "LAL", cleaned)
    # Picks read player_props: exactly what the Over-only extractor produced.
    assert data["player_props"]["points"] == {
        "Jayson Tatum": {"lines": {"24.5": "1.96", "25": "1.93"}},
        "Cade Cunningham": {"lines": {"25": "2.4"}},
    }
    assert data["player_props_two_way"] == {
        "points": {"Jayson Tatum": {"24.5": {"over": "1.96", "under": "1.8"}}},
    }
    assert data["two_way_capture"]["ou_pairs"] == 1
    assert data["two_way_capture"]["milestone_ladders"] == "one_sided_no_devig"


def test_two_way_ou_price_devigs_the_equivalent_milestone_leg(root, tmp_path):
    _full_day(root, tmp_path)
    live = tmp_path / "ou"
    path = _odds(live, "2026-10-22 06:30:00", {"20": "1.7"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["player_props_two_way"] = {
        "points": {"Jayson Tatum": {"24.5": {"over": "1.96", "under": "1.8"}}},
        "rebounds": {"Jayson Tatum": {"8.5": {"over": "1.9"}}},  # one side only: ignored
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    ledger.record_prices(live, DAY, context="t", now=TIP - timedelta(hours=7))
    ou = [r for r in ledger.read_rows(root, DAY) if r.get("price_source") == "ou_two_way"]
    assert [(r["line"], r["ou_line"], r["price"], r["complement_price"]) for r in ou] == [
        (25.0, 24.5, 1.96, 1.8),
    ]
    # Idempotent, including the two-way row.
    assert ledger.record_prices(live, DAY, context="t", now=TIP - timedelta(hours=7)) == 0

    report = ledger.evaluate(root=root)
    final = report["overall"]["variants"]["p_final"]
    devig = final["market_devig_close"]
    expected = ledger.devig_two_way_proportional(1.96, 1.8)
    assert devig["n"] == 1
    assert math.isclose(devig["brier_market"], round((expected - 1) ** 2, 5))
    # Raw close / CLV still use the milestone price only (20+ moved to 1.7).
    assert final["market_raw_close"]["n"] == 2
    assert math.isclose(final["market_raw_close"]["brier_market"],
                        round(((1 / 1.7 - 1) ** 2 + (1 / 3.2 - 1) ** 2) / 2, 5))
    assert report["overall"]["devig_coverage"] == {
        "legs_with_two_way_price": 1, "settled_with_two_way_price": 1,
        "settled_clusters_with_two_way_price": 1,
    }
    assert report["verdict_status"] == "insufficient_n"


# ── Sportsbet SGM price capture ─────────────────────────────────────────────

def _sportsbook():
    return {
        "events": {"10809360": {"id": 10809360, "externalId": 16299472, "competitionId": 6927}},
        "competitions": {"6927": {"classId": 16, "externalId": 19476}},
        "classes": {"16": {"externalId": 16}},
        "markets": {
            "1": {"eventId": 10809360, "name": "To Score 20+ Points", "externalId": 600424697,
                  "outcomeIds": [11], "sameGameMultiEnabled": True},
            "2": {"eventId": 10809360, "name": "To Score 25+ Points", "externalId": 600424699,
                  "outcomeIds": [12]},
        },
        "outcomes": {
            "11": {"name": "Jayson Tatum", "externalId": 2862294785, "winPrice": {"num": 800, "den": 1000}},
            "12": {"name": "Jayson Tatum", "externalId": 2862294790, "winPrice": {"num": 2200, "den": 1000}},
        },
    }


def test_extractor_records_sgm_pricing_ids_without_touching_props():
    sys.path.insert(0, str(AUTO_DIR.parent / "nba_data_extractor" / "scripts"))
    import claw_sportsbet_odds as claw

    extractor = claw.SportsbetNBAExtractor(target_date=DAY)
    sportsbook = _sportsbook()
    extracted = extractor._parse_normalized_markets(sportsbook)
    plain = extractor._format_as_sportsbet("Boston Celtics At Los Angeles Lakers", "BOS", "LAL",
                                           extractor._clean_markets(extracted))
    extractor._sgm_context = extractor._sgm_pricing_context(sportsbook, 10809360)
    data = extractor._format_as_sportsbet("Boston Celtics At Los Angeles Lakers", "BOS", "LAL",
                                          extractor._clean_markets(extracted))
    assert data["player_props"] == plain["player_props"]
    assert data["sgm_pricing"]["event_external_id"] == 16299472
    assert data["sgm_pricing"]["outcomes"]["points"]["Jayson Tatum"] == {
        "20": {"market_external_id": 600424697, "outcome_external_id": 2862294785},
        "25": {"market_external_id": 600424699, "outcome_external_id": 2862294790},
    }


def test_sgm_prices_are_quoted_for_published_combos_and_used_as_reference(root, tmp_path):
    _full_day(root, tmp_path)
    prod = sorted((tmp_path / "live" / "_prediction_snapshots").iterdir())[-1]
    odds_path = prod / f"Sportsbet_Odds_{TAG}.json"
    odds = json.loads(odds_path.read_text(encoding="utf-8"))
    odds["sgm_pricing"] = {
        "class_external_id": 16, "competition_external_id": 19476, "event_external_id": 16299472,
        "outcomes": {"points": {"Jayson Tatum": {
            "20": {"market_external_id": 1, "outcome_external_id": 11},
            "25": {"market_external_id": 2, "outcome_external_id": 12},
        }}},
    }
    odds_path.write_text(json.dumps(odds), encoding="utf-8")
    bodies = []

    def fake_post(body):
        bodies.append(body)
        return 200, {"price": {"quoteId": "q1", "numerator": 9, "denominator": 2}}

    counts = ledger.record_sgm_prices(prod, DAY, now=TIP - timedelta(hours=11), post=fake_post)
    assert counts == {"ok": 1, "appended": 1}
    assert bodies == [{
        "classExternalId": 16, "competitionExternalId": 19476, "eventExternalId": 16299472,
        "outcomesExternalIds": [{"marketExternalId": 1, "outcomeExternalId": 11},
                                {"marketExternalId": 2, "outcomeExternalId": 12}],
    }]
    quote = next(r for r in ledger.read_rows(root, DAY) if r["row_type"] == "sgm_price_obs")
    assert (quote["sportsbet_sgm_price"], quote["quote_id"], quote["post_tip"]) == (5.5, "q1", False)
    sgm = ledger.evaluate(root=root)["sgm"]
    assert sgm["sportsbet_sgm_implied"]["mean_p"] == round(1 / 5.5, 4)
    assert sgm["counts"]["settled_with_sportsbet_price"] == 1


def test_sgm_price_capture_records_why_a_quote_is_missing(root, tmp_path):
    _full_day(root, tmp_path)
    prod = sorted((tmp_path / "live" / "_prediction_snapshots").iterdir())[-1]
    counts = ledger.record_sgm_prices(prod, DAY, now=TIP - timedelta(hours=11),
                                      post=lambda body: pytest.fail("no ids, no request"))
    assert counts == {"event_ids_missing": 1, "appended": 1}


def test_sgm_price_capture_never_hits_the_network_under_tests(root, tmp_path):
    with pytest.raises(ledger.LedgerIsolationError):
        ledger.record_sgm_prices(tmp_path, DAY)
