from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_review_clock import (
    ReviewClockError,
    ReviewEvent,
    SampleSnapshot,
    plan_reviews,
)


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def args(**changes):
    return {
        "domain": Domain.TENNIS,
        "window_start": dt("2026-08-30T00:00:00Z"),
        "now": dt("2026-08-31T00:00:00Z"),
        "ruler_digest": "a" * 64,
        "ruler_released_at": dt("2026-08-01T00:00:00Z"),
        **changes,
    }


def samples(count, *, domain=Domain.TENNIS, scope="match_winner", old=False):
    return SampleSnapshot(
        domain=domain,
        scope=scope,
        basis={Domain.AU: "settled_races", Domain.HKJC: "settled_races",
               Domain.TENNIS: "verified_pit_outcomes", Domain.NBA: "forward_settled_recommendations"}[domain],
        observed_at=dt("2026-08-29T00:00:00Z" if old else "2026-08-30T00:00:00Z"),
        evidence_digest=("b" if old else "c") * 64,
        unit_ids=frozenset(f"unit-{i}" for i in range(count)),
    )


def kinds(plan):
    return [item["kind"] for item in plan["requests"]]


def test_weekly_sydney_nine_is_stable_across_poll_and_ack():
    plan = plan_reviews(**args())
    assert kinds(plan) == ["weekly"]
    assert plan["requests"][0]["due_at"] == "2026-08-30T23:00:00+00:00"
    assert plan == plan_reviews(**args())
    later = plan_reviews(**args(now=dt("2026-08-31T03:00:00Z")))
    assert later["requests"][0]["request_id"] == plan["requests"][0]["request_id"]
    acknowledged = {plan["requests"][0]["request_id"]}
    assert not plan_reviews(**args(completed_request_ids=acknowledged))["requests"]


@pytest.mark.parametrize("before,after,due", [
    ("2026-10-04T21:59:59Z", "2026-10-04T22:00:00Z", "2026-10-04T22:00:00+00:00"),
    ("2027-04-04T22:59:59Z", "2027-04-04T23:00:00Z", "2027-04-04T23:00:00+00:00"),
])
def test_calendar_uses_sydney_dst_not_fixed_utc(before, after, due):
    options = args(window_start=dt(before), now=dt(after), ruler_released_at=dt(before))
    plan = plan_reviews(**options)
    assert kinds(plan) == ["monthly", "weekly"]
    assert {item["due_at"] for item in plan["requests"]} == {due}
    assert not plan_reviews(**{**options, "now": dt(before)})["requests"]


def test_missed_weekly_and_monthly_slots_are_caught_up_once():
    plan = plan_reviews(**args(window_start=dt("2026-08-31T00:00:00Z"), now=dt("2026-09-15T00:00:00Z")))
    assert kinds(plan).count("weekly") == 2
    assert kinds(plan).count("monthly") == 1
    assert plan["progress_only"]
    assert not plan["sample_growth_observed"]


@pytest.mark.parametrize("domain,old,new,thresholds", [
    (Domain.AU, 49, 150, [50, 100, 150]),
    (Domain.HKJC, 49, 50, [50]),
    (Domain.TENNIS, 199, 600, [200, 400, 600]),
    (Domain.NBA, 29, 230, [30, 130, 230]),
    (Domain.NBA, 30, 129, []),
])
def test_sample_thresholds_are_monitoring_not_promotion(domain, old, new, thresholds):
    scope = "match_winner" if domain is Domain.TENNIS else "all"
    previous = samples(old, domain=domain, scope=scope, old=True)
    current = samples(new, domain=domain, scope=scope)
    plan = plan_reviews(**args(domain=domain, previous_samples=(previous,), samples=(current,)))
    requests = [item for item in plan["requests"] if item["kind"] == "sample"]
    assert [item["threshold"] for item in requests] == thresholds
    assert all(item["action"] == "monitor_only" for item in requests)
    assert plan["sample_growth_observed"]
    for flag in ("rerun_scoring_allowed", "reevaluate_promotion_allowed", "model_promotion_allowed"):
        assert plan[flag] is False


def test_families_cannot_be_pooled_and_unchanged_samples_do_not_retrigger():
    previous = (samples(199, old=True), samples(199, scope="totals", old=True))
    current = (samples(199), samples(199, scope="totals"))
    plan = plan_reviews(**args(previous_samples=previous, samples=current))
    assert "sample" not in kinds(plan)
    assert plan["progress_only"]
    assert not plan["freeze_research_required"]


def test_missing_baseline_is_not_assumed_zero():
    plan = plan_reviews(**args(samples=(samples(1000),)))
    assert "sample" not in kinds(plan)
    assert "match_winner:sample_baseline_missing" in plan["findings"]


@pytest.mark.parametrize("fault", ["shrink", "replace", "missing_scope"])
def test_sample_loss_freezes_and_never_resets_monitoring_watermark(fault):
    previous = samples(199, old=True)
    current = samples(198 if fault == "shrink" else 200)
    if fault == "replace":
        current = replace(current, unit_ids=(current.unit_ids - {"unit-0"}) | {"replacement"})
    plan = plan_reviews(**args(previous_samples=(previous,), samples=() if fault == "missing_scope" else (current,)))
    assert plan["freeze_research_required"]
    assert "sample" not in kinds(plan)
    assert plan["findings"]


@pytest.mark.parametrize("fault", ["history_is_forward", "raw_rows_are_pit", "wrong_domain", "duplicate_scope", "future", "backdated", "bad_digest", "bad_unit"])
def test_sample_inputs_fail_closed(fault):
    current = samples(200)
    previous = samples(199, old=True)
    if fault == "history_is_forward":
        current = replace(current, domain=Domain.NBA, scope="all", basis="historical_results")
    elif fault == "raw_rows_are_pit":
        current = replace(current, basis="dataset_row_count")
    elif fault == "wrong_domain":
        current = samples(200, domain=Domain.AU, scope="all")
    elif fault == "future":
        current = replace(current, observed_at=dt("2027-01-01T00:00:00Z"))
    elif fault == "backdated":
        current = replace(current, observed_at=dt("2026-08-28T00:00:00Z"))
    elif fault == "bad_digest":
        current = replace(current, evidence_digest="trust-me")
    elif fault == "bad_unit":
        current = replace(current, unit_ids=frozenset({""}))
    items = (current, current) if fault == "duplicate_scope" else (current,)
    with pytest.raises(ReviewClockError):
        plan_reviews(**args(previous_samples=(previous,), samples=items))


def test_run_and_daily_reviews_require_events_not_a_midnight_guess():
    assert "daily" not in kinds(plan_reviews(**args()))
    events = tuple(ReviewEvent(kind, kind + "-1", dt("2026-08-30T02:00:00Z"), "d" * 64)
                   for kind in ("run_preflight", "run_postflight", "production_day_closed"))
    plan = plan_reviews(**args(events=events))
    assert set(kinds(plan)) == {"run_preflight", "run_postflight", "daily", "weekly"}
    assert all(item["action"] in {"check_only", "monitor_only"} for item in plan["requests"])


def test_incident_and_overdue_ruler_freeze_persist_after_digest_ack():
    incident = ReviewEvent("incident", "feed-leakage-1", dt("2026-08-29T00:00:00Z"), "d" * 64)
    options = args(ruler_released_at=dt("2026-05-01T00:00:00Z"), events=(incident,))
    plan = plan_reviews(**options)
    assert {"incident", "ruler_90_day"}.issubset(kinds(plan))
    assert plan["freeze_research_required"]
    acknowledged = {item["request_id"] for item in plan["requests"]}
    replay = plan_reviews(**options, completed_request_ids=acknowledged)
    assert not replay["requests"]
    assert replay["freeze_research_required"]
    assert replay["human_review_required"]


def test_event_replays_dedup_but_conflicting_identity_fails():
    event = ReviewEvent("run_postflight", "run-1", dt("2026-08-30T02:00:00Z"), "d" * 64)
    assert kinds(plan_reviews(**args(events=(event, event)))).count("run_postflight") == 1
    with pytest.raises(ReviewClockError, match="conflict"):
        plan_reviews(**args(events=(event, replace(event, evidence_digest="e" * 64))))


@pytest.mark.parametrize("changes", [
    {"now": dt("2026-08-29T00:00:00Z")},
    {"now": datetime(2026, 8, 31)},
    {"window_start": dt("2020-01-01T00:00:00Z")},
    {"ruler_released_at": dt("2027-01-01T00:00:00Z")},
    {"ruler_digest": "latest"},
])
def test_invalid_clock_or_ruler_input_is_not_silently_normalized(changes):
    with pytest.raises(ReviewClockError):
        plan_reviews(**args(**changes))


def test_input_order_does_not_change_replay_hash():
    previous = (samples(199, old=True), samples(199, scope="totals", old=True))
    current = (samples(200), samples(200, scope="totals"))
    plan = plan_reviews(**args(previous_samples=previous, samples=current))
    assert plan == plan_reviews(**args(previous_samples=previous[::-1], samples=current[::-1]))


def test_cross_midnight_production_closures_keep_distinct_logical_days():
    completed = dt("2026-08-31T15:00:00Z")  # 1 September Sydney
    events = (
        ReviewEvent("production_day_closed", "august-backlog", completed, "d" * 64, production_day=date(2026, 8, 31)),
        ReviewEvent("production_day_closed", "september-no-events", completed, "e" * 64, production_day=date(2026, 9, 1)),
    )
    plan = plan_reviews(**args(now=completed, events=events))
    daily = [item for item in plan["requests"] if item["kind"] == "daily"]
    assert {item["slot"] for item in daily} == {"2026-08-31", "2026-09-01"}
    assert len({item["request_id"] for item in daily}) == 2
    assert {item["due_at"] for item in daily} == {completed.isoformat()}


@pytest.mark.parametrize("kind,logical_day", [
    ("run_postflight", date(2026, 8, 30)),
    ("production_day_closed", date(2026, 9, 1)),
    ("production_day_closed", "2026-08-30"),
    ("production_day_closed", dt("2026-08-30T00:00:00Z")),
])
def test_production_day_metadata_cannot_be_future_or_attached_to_other_event(kind, logical_day):
    event = ReviewEvent(kind, "invalid-day", dt("2026-08-30T12:00:00Z"), "d" * 64, production_day=logical_day)
    with pytest.raises(ReviewClockError):
        plan_reviews(**args(events=(event,)))
