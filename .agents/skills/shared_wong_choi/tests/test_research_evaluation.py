from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PACKAGE_ROOT.parent
sys.path.insert(0, str(SKILLS_ROOT))

from shared_wong_choi.contracts import Domain
from shared_wong_choi import research_evaluation as evaluation_module
from shared_wong_choi.artifact_archive import artifact_digest
from shared_wong_choi.research_dataset import DatasetSource, SplitPolicy, StorageTier, build_dataset_snapshot
from shared_wong_choi.research_runner import (
    CommandExecution,
    CommandState,
    ResearchJob,
    ResearchRuntime,
    ResearchRunner,
    create_research_adapter,
)
from shared_wong_choi.evaluation_rulers import (
    DEFAULT_RULER_ROOT,
    load_evaluation_ruler,
)
from shared_wong_choi.research_evaluation import (
    EvaluationError,
    EvaluationObservation,
    EvaluationVerdict,
    ObservationSeries,
    evaluate_research_candidate,
    publish_evaluation_decision,
)
from shared_wong_choi.research_registry import (
    DatasetManifest,
    DatasetSplit,
    ExperimentRegistry,
    ExperimentRun,
    ExperimentRunState,
    ExperimentSpec,
    SourceWatermark,
)


SAMPLE_HASH = "3" * 64
BASELINE = "a" * 40
CANDIDATE = "b" * 40


def ruler_digest(domain: Domain) -> str:
    ruler = load_evaluation_ruler(domain)
    return hashlib.sha256((DEFAULT_RULER_ROOT / f"{ruler.ruler_id}.json").read_bytes()).hexdigest()


def experiment_spec(domain: Domain) -> ExperimentSpec:
    ruler = load_evaluation_ruler(domain)
    return ExperimentSpec(
        record_id=f"wc:{domain.value}:experiment-spec:evaluation-v1",
        domain=domain,
        created_at="2026-08-30T00:00:00+00:00",
        hypothesis="frozen evaluation fixture",
        evaluation_ruler_id=ruler.ruler_id,
        evaluation_ruler_digest=ruler_digest(domain),
        baseline_commit=BASELINE,
        candidate_commit=CANDIDATE,
        preregistered_metrics=tuple(str(metric["name"]) for metric in ruler.metrics),
        seed=int(ruler.bootstrap["seed"]),
        commands=("python3 evaluate.py --frozen",),
        protocol_artifact_digest="4" * 64,
    )


def dataset_manifest(domain: Domain, *, train: int, dev: int, terminal: int):
    return DatasetManifest(
        record_id=f"wc:{domain.value}:dataset-manifest:{SAMPLE_HASH[:24]}",
        domain=domain,
        created_at="2026-08-30T00:00:00+00:00",
        spec_id=experiment_spec(domain).record_id,
        point_in_time_cutoff="2026-08-29T23:59:00+00:00",
        sample_hash=SAMPLE_HASH,
        row_count=train + dev + terminal,
        source_watermarks=(
            SourceWatermark(
                source_id=f"{domain.value}-fixture",
                available_at="2026-08-29T00:00:00+00:00",
                content_digest="5" * 64,
            ),
        ),
        splits=(
            DatasetSplit("train", train, "6" * 64),
            DatasetSplit("dev", dev, "7" * 64),
            DatasetSplit("terminal", terminal, "8" * 64),
        ),
        artifact_digest="9" * 64,
    )


def cohort_values(domain: Domain, *, family: str = "family-a") -> dict[str, str]:
    ruler = load_evaluation_ruler(domain)
    values = {
        "field_size": "9-10",
        "venue": "fixture-venue",
        "going": "good",
        "family": family,
        "tour": "atp",
        "surface": "hard",
        "tournament_level": "tour",
        "odds_bucket": "1.50-2.00",
        "season_phase": "regular_season",
        "market_family": family,
        "injury_freshness": "fresh",
        "minutes_role": "stable",
        "blowout_risk": "low",
    }
    return {name: values[name] for name in ruler.cohorts}


def metric_values(domain: Domain, value: float = 0.0) -> dict[str, float]:
    return {str(metric["name"]): value for metric in load_evaluation_ruler(domain).metrics}


def series_pair(
    domain: Domain,
    *,
    dev: int,
    terminal: int,
    family: str = "family-a",
    candidate_changes: dict[str, float] | None = None,
) -> tuple[ObservationSeries, ObservationSeries, DatasetManifest]:
    train = 3
    baseline_rows = []
    candidate_rows = []
    changes = candidate_changes or {}
    layout = (
        [("train", None)] * train
        + [("dev", (index * 3 // dev) + 1) for index in range(dev)]
        + [("terminal", None)] * terminal
    )
    for index, (split, fold) in enumerate(layout):
        base_metrics = metric_values(domain)
        candidate_metrics = {name: base_metrics[name] + changes.get(name, 0.0) for name in base_metrics}
        common = {
            "row_id": f"{family}-{index:05d}",
            "event_at": (datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat(),
            "split": split,
            "fold": fold,
            "cohorts": cohort_values(domain, family=family),
        }
        baseline_rows.append(EvaluationObservation(metrics=base_metrics, **common))
        candidate_rows.append(EvaluationObservation(metrics=candidate_metrics, **common))
    dataset = dataset_manifest(domain, train=train, dev=dev, terminal=terminal)
    return (
        ObservationSeries(
            domain,
            SAMPLE_HASH,
            tuple(baseline_rows),
            dataset.record_id,
            dataset.artifact_digest,
        ),
        ObservationSeries(
            domain,
            SAMPLE_HASH,
            tuple(candidate_rows),
            dataset.record_id,
            dataset.artifact_digest,
        ),
        dataset,
    )


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_horse_known_primary_win_uses_stage4_decision(
    domain: Domain,
) -> None:
    baseline, candidate, dataset = series_pair(
        domain,
        dev=12,
        terminal=12,
        candidate_changes={"gold": 0.1},
    )

    report = evaluate_research_candidate(
        experiment_spec(domain),
        dataset,
        baseline,
        candidate,
        safety_passed=True,
    )

    assert report.verdict is EvaluationVerdict.PRIMARY_WIN
    assert report.reason == "gold_or_good_supported_gain"
    assert report.scopes[0].metrics["gold"].terminal_ci_low > 0
    assert len(report.scopes[0].metrics["gold"].fold_deltas) == 3


def test_horse_ranking_win_and_primary_regression_follow_stage4_order() -> None:
    baseline, ranking_candidate, dataset = series_pair(
        Domain.AU,
        dev=12,
        terminal=12,
        candidate_changes={
            "top3_capture_at5": 0.1,
            "ndcg_at5": 0.1,
        },
    )
    ranking = evaluate_research_candidate(
        experiment_spec(Domain.AU),
        dataset,
        baseline,
        ranking_candidate,
        safety_passed=True,
    )
    regression_candidate = ObservationSeries(
        Domain.AU,
        SAMPLE_HASH,
        tuple(
            replace(
                row,
                metrics={
                    **row.metrics,
                    "good_positional": row.metrics["good_positional"] - 0.1,
                    "top3_capture_at5": row.metrics["top3_capture_at5"] + 0.2,
                    "ndcg_at5": row.metrics["ndcg_at5"] + 0.2,
                },
            )
            for row in ranking_candidate.observations
        ),
        dataset.record_id,
        dataset.artifact_digest,
    )
    regression = evaluate_research_candidate(
        experiment_spec(Domain.AU),
        dataset,
        baseline,
        regression_candidate,
        safety_passed=True,
    )

    assert ranking.verdict is EvaluationVerdict.RANKING_WIN
    assert regression.verdict is EvaluationVerdict.REJECT
    assert regression.reason == "primary_regression"


def test_tennis_known_win_is_only_a_shadow_candidate() -> None:
    changes = {
        "brier_gain_vs_market": 0.02,
        "log_loss_gain_vs_market": 0.02,
        "calibration_error": -0.01,
        "clv": 0.01,
        "roi": 0.01,
        "coverage": 0.01,
    }
    baseline, candidate, dataset = series_pair(
        Domain.TENNIS,
        dev=300,
        terminal=300,
        family="match_winner_atp",
        candidate_changes=changes,
    )

    report = evaluate_research_candidate(
        experiment_spec(Domain.TENNIS),
        dataset,
        baseline,
        candidate,
        safety_passed=True,
    )

    assert report.verdict is EvaluationVerdict.SHADOW_CANDIDATE
    assert report.scopes[0].scope == "match_winner_atp"
    assert report.scopes[0].verdict is EvaluationVerdict.SHADOW_CANDIDATE


def test_tennis_noise_and_underpowered_family_are_inconclusive() -> None:
    baseline, same, dataset = series_pair(Domain.TENNIS, dev=300, terminal=300, family="match_winner_wta")
    noise = evaluate_research_candidate(
        experiment_spec(Domain.TENNIS),
        dataset,
        baseline,
        same,
        safety_passed=True,
    )
    small_baseline, small_candidate, small_dataset = series_pair(
        Domain.TENNIS,
        dev=20,
        terminal=20,
        family="totals",
        candidate_changes={
            "brier_gain_vs_market": 0.2,
            "log_loss_gain_vs_market": 0.2,
        },
    )
    underpowered = evaluate_research_candidate(
        experiment_spec(Domain.TENNIS),
        small_dataset,
        small_baseline,
        small_candidate,
        safety_passed=True,
    )

    assert noise.verdict is EvaluationVerdict.INCONCLUSIVE
    assert noise.reason == "primary_evidence_too_weak"
    assert underpowered.verdict is EvaluationVerdict.INCONCLUSIVE
    assert underpowered.reason == "family_below_sample_floor"


def test_tennis_primary_or_guardrail_regression_rejects() -> None:
    baseline, candidate, dataset = series_pair(
        Domain.TENNIS,
        dev=300,
        terminal=300,
        candidate_changes={
            "brier_gain_vs_market": -0.01,
            "log_loss_gain_vs_market": 0.02,
            "roi": 0.1,
        },
    )

    report = evaluate_research_candidate(
        experiment_spec(Domain.TENNIS),
        dataset,
        baseline,
        candidate,
        safety_passed=True,
    )

    assert report.verdict is EvaluationVerdict.REJECT
    assert report.reason == "primary_regression"


def test_nba_supported_gain_stays_descriptive_only() -> None:
    baseline, candidate, dataset = series_pair(
        Domain.NBA,
        dev=30,
        terminal=30,
        family="player_points",
        candidate_changes={
            "brier_gain_vs_market": 0.1,
            "log_loss_gain_vs_market": 0.1,
            "clv": 0.1,
            "roi": 0.1,
        },
    )

    report = evaluate_research_candidate(
        experiment_spec(Domain.NBA),
        dataset,
        baseline,
        candidate,
        safety_passed=True,
    )

    assert report.verdict is EvaluationVerdict.DESCRIPTIVE_ONLY
    assert report.promotion_proposal_allowed is False
    assert report.reason == "ruler_descriptive_only"


def test_nba_known_regression_is_reported_but_never_promoted() -> None:
    baseline, candidate, dataset = series_pair(
        Domain.NBA,
        dev=30,
        terminal=30,
        family="player_points",
        candidate_changes={"brier_gain_vs_market": -0.1},
    )

    report = evaluate_research_candidate(
        experiment_spec(Domain.NBA),
        dataset,
        baseline,
        candidate,
        safety_passed=True,
    )

    assert report.verdict is EvaluationVerdict.REJECT
    assert report.reason == "primary_regression"
    assert report.promotion_proposal_allowed is False


def test_single_roi_gain_cannot_promote_tennis() -> None:
    baseline, candidate, dataset = series_pair(
        Domain.TENNIS,
        dev=300,
        terminal=300,
        candidate_changes={"roi": 0.2},
    )

    report = evaluate_research_candidate(
        experiment_spec(Domain.TENNIS),
        dataset,
        baseline,
        candidate,
        safety_passed=True,
    )

    assert report.verdict is EvaluationVerdict.INCONCLUSIVE
    assert report.promotion_proposal_allowed is False


@pytest.mark.parametrize("metric", ["brier_gain_vs_market", "log_loss_gain_vs_market", "roi"])
def test_improving_but_still_negative_absolute_tennis_metric_cannot_win(metric) -> None:
    baseline, candidate, dataset = series_pair(
        Domain.TENNIS,
        dev=300,
        terminal=300,
        candidate_changes={"brier_gain_vs_market": 0.02, "log_loss_gain_vs_market": 0.02, "roi": 0.02},
    )

    def negative(series):
        return replace(
            series,
            observations=tuple(
                replace(row, metrics={**row.metrics, metric: row.metrics[metric] - 0.1}) for row in series.observations
            ),
        )

    report = evaluate_research_candidate(
        experiment_spec(Domain.TENNIS),
        dataset,
        negative(baseline),
        negative(candidate),
        safety_passed=True,
    )
    assert report.verdict is EvaluationVerdict.REJECT
    assert report.promotion_proposal_allowed is False


@pytest.mark.parametrize("mutation", ["split_time", "fold_order", "future_event"])
def test_evaluation_rejects_nonchronological_evidence_even_when_both_sides_agree(mutation) -> None:
    baseline, candidate, dataset = series_pair(Domain.AU, dev=12, terminal=12)

    def corrupt(series):
        rows = list(series.observations)
        if mutation == "split_time":
            rows[-1] = replace(rows[-1], event_at=rows[0].event_at)
        elif mutation == "future_event":
            rows[-1] = replace(rows[-1], event_at="2030-01-01T00:00:00+00:00")
        else:
            rows[3] = replace(rows[3], fold=3)
        return replace(series, observations=tuple(rows))

    with pytest.raises(EvaluationError, match="chronolog|cutoff|fold"):
        evaluate_research_candidate(
            experiment_spec(Domain.AU),
            dataset,
            corrupt(baseline),
            corrupt(candidate),
            safety_passed=True,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: replace(item, evaluation_ruler_id="au-v99"),
        lambda item: replace(item, evaluation_ruler_digest="f" * 64),
        lambda item: replace(item, preregistered_metrics=("gold",)),
    ],
)
def test_ruler_identity_and_preregistered_metrics_are_immutable(mutation) -> None:
    baseline, candidate, dataset = series_pair(Domain.AU, dev=12, terminal=12, candidate_changes={"gold": 0.1})

    with pytest.raises(EvaluationError, match="ruler|pre-registered"):
        evaluate_research_candidate(
            mutation(experiment_spec(Domain.AU)),
            dataset,
            baseline,
            candidate,
            safety_passed=True,
        )


def test_row_pairing_sample_and_safety_fail_closed() -> None:
    baseline, candidate, dataset = series_pair(Domain.AU, dev=12, terminal=12, candidate_changes={"gold": 0.1})
    changed_rows = list(candidate.observations)
    changed_rows[-1] = replace(changed_rows[-1], row_id="different")

    with pytest.raises(EvaluationError, match="paired row identity"):
        evaluate_research_candidate(
            experiment_spec(Domain.AU),
            dataset,
            baseline,
            replace(candidate, observations=tuple(changed_rows)),
            safety_passed=True,
        )
    with pytest.raises(EvaluationError, match="dataset manifest id"):
        evaluate_research_candidate(
            experiment_spec(Domain.AU),
            dataset,
            baseline,
            replace(candidate, dataset_manifest_id="wc:au:dataset-manifest:wrong"),
            safety_passed=True,
        )
    with pytest.raises(EvaluationError, match="dataset artifact digest"):
        evaluate_research_candidate(
            experiment_spec(Domain.AU),
            dataset,
            baseline,
            replace(candidate, dataset_artifact_digest="f" * 64),
            safety_passed=True,
        )
    blocked = evaluate_research_candidate(
        experiment_spec(Domain.AU),
        dataset,
        baseline,
        candidate,
        safety_passed=False,
    )
    assert blocked.verdict is EvaluationVerdict.BLOCKED
    assert blocked.reason == "research_safety_gate_failed"


def test_subgroup_harm_is_a_cohort_regression_and_bootstrap_is_reproducible() -> None:
    baseline, candidate, dataset = series_pair(Domain.AU, dev=30, terminal=30)
    baseline_rows = []
    candidate_rows = []
    for index, (baseline_row, candidate_row) in enumerate(zip(baseline.observations, candidate.observations)):
        venue = "venue-a" if index % 2 == 0 else "venue-b"
        cohorts = {**baseline_row.cohorts, "venue": venue}
        delta = -0.2 if venue == "venue-a" else 0.2
        baseline_rows.append(replace(baseline_row, cohorts=cohorts))
        candidate_rows.append(
            replace(
                candidate_row,
                cohorts=cohorts,
                metrics={**candidate_row.metrics, "gold": delta},
            )
        )
    paired_baseline = replace(baseline, observations=tuple(baseline_rows))
    paired_candidate = replace(candidate, observations=tuple(candidate_rows))

    first = evaluate_research_candidate(
        experiment_spec(Domain.AU),
        dataset,
        paired_baseline,
        paired_candidate,
        safety_passed=True,
    )
    second = evaluate_research_candidate(
        experiment_spec(Domain.AU),
        dataset,
        paired_baseline,
        paired_candidate,
        safety_passed=True,
    )

    assert first.verdict is EvaluationVerdict.REJECT
    assert first.reason == "cohort_regression"
    assert any("venue=venue-a:gold" in item for item in first.scopes[0].cohort_regressions)
    assert first.to_payload() == second.to_payload()


def test_machine_decision_report_is_append_only_shadow_proposal(
    tmp_path: Path,
) -> None:
    domain = Domain.AU
    frozen = experiment_spec(domain)
    baseline, candidate, dataset = series_pair(domain, dev=12, terminal=12, candidate_changes={"gold": 0.1})
    report = evaluate_research_candidate(frozen, dataset, baseline, candidate, safety_passed=True)
    registry = ExperimentRegistry(tmp_path / "registry")
    registry.append(frozen)
    registry.append(dataset)
    run = ExperimentRun(
        record_id="wc:au:experiment-run:evaluation-fixture",
        domain=domain,
        created_at="2026-08-31T00:00:00+00:00",
        spec_id=frozen.record_id,
        dataset_manifest_id=dataset.record_id,
        started_at="2026-08-30T23:00:00+00:00",
        completed_at="2026-08-31T00:00:00+00:00",
        state=ExperimentRunState.SUCCEEDED,
        evaluation_ruler_id=frozen.evaluation_ruler_id,
        evaluation_ruler_digest=frozen.evaluation_ruler_digest,
        baseline_commit=frozen.baseline_commit,
        candidate_commit=frozen.candidate_commit,
        seed=frozen.seed,
        commands=frozen.commands,
        metrics_digest=report.input_metrics_digest,
        artifact_digest="a" * 64,
        stdout_digest="b" * 64,
    )
    registry.append(run)

    with pytest.raises(EvaluationError, match="frozen experiment run"):
        publish_evaluation_decision(
            replace(report, ruler_digest="f" * 64),
            registry=registry,
            run_id=run.record_id,
            report_root=tmp_path / "reports",
            decided_at="2026-08-31T01:00:00+00:00",
        )

    first = publish_evaluation_decision(
        report,
        registry=registry,
        run_id=run.record_id,
        report_root=tmp_path / "reports",
        decided_at="2026-08-31T01:00:00+00:00",
    )
    second = publish_evaluation_decision(
        report,
        registry=registry,
        run_id=run.record_id,
        report_root=tmp_path / "reports",
        decided_at="2026-08-31T02:00:00+00:00",
    )

    assert first.status == "created"
    assert second.status == "duplicate"
    decision = registry.load(first.decision_id)
    assert decision["state"] == "shadow_review_proposal"
    assert decision["links"]["run_id"] == run.record_id


def runner_evidence(tmp_path, domain, *, forged_row=False):
    size = 300 if domain is Domain.TENNIS else 12
    changes = (
        {"brier_gain_vs_market": 0.02, "log_loss_gain_vs_market": 0.02}
        if domain in {Domain.TENNIS, Domain.NBA}
        else {"gold": 0.1}
    )
    baseline, candidate, _ = series_pair(domain, dev=size, terminal=size, candidate_changes=changes)
    frozen = experiment_spec(domain)
    source = tmp_path / "source.jsonl"
    source.write_text(
        "".join(
            json.dumps(
                {
                    "row_id": row.row_id,
                    "event_at": row.event_at,
                    "available_at": row.event_at,
                    "payload": {"cohorts": dict(row.cohorts), "fold": row.fold},
                }
            )
            + "\n"
            for row in baseline.observations
        ),
        encoding="utf-8",
    )
    snapshot = build_dataset_snapshot(
        frozen,
        sources=(
            DatasetSource(
                f"{domain.value}-source",
                StorageTier.HOT,
                source,
                source,
                "2026-08-29T00:00:00+00:00",
                artifact_digest(source),
            ),
        ),
        split_policy=SplitPolicy(
            baseline.observations[2].event_at, baseline.observations[2 + size].event_at, "2026-08-29T23:59:00+00:00"
        ),
        snapshot_root=tmp_path / "snapshots",
    )
    series = {}
    for role, value in (("baseline", baseline), ("candidate", candidate)):
        rows = value.observations
        if forged_row:
            rows = (*rows[:-1], replace(rows[-1], row_id="forged-but-paired"))
        series[role] = replace(
            value,
            sample_hash=snapshot.manifest.sample_hash,
            dataset_manifest_id=snapshot.manifest.record_id,
            dataset_artifact_digest=snapshot.manifest.artifact_digest,
            observations=rows,
        )

    class Executor:
        def run(self, invocation, **kwargs):
            invocation.metrics_path.write_text(json.dumps(series[invocation.role].to_payload()), encoding="utf-8")
            return CommandExecution(CommandState.SUCCEEDED, 0, "ok", "", 0.01, 0.01, 0, 1024)

    registry = ExperimentRegistry(tmp_path / "registry")
    registry.append(frozen)
    registry.append(snapshot.manifest)
    for name in ("baseline", "candidate", "warm"):
        (tmp_path / name).mkdir()
    runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=tmp_path / "warm",
        executor=Executor(),
        checkout_probe=lambda path: BASELINE if path.name == "baseline" else CANDIDATE,
        free_space_probe=lambda path: 10**9,
        clock=lambda: datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    job = ResearchJob(
        f"wc:{domain.value}:research-job:evaluation-fixture",
        domain,
        frozen.record_id,
        snapshot.path,
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    result = ResearchRunner(runtime, registry).run(job, frozen, create_research_adapter(domain))
    assert result.status == "succeeded"
    return frozen, snapshot, result, registry


@pytest.mark.parametrize("domain", list(Domain))
def test_real_runner_artifact_to_evaluation_and_decision(tmp_path, domain):
    frozen, snapshot, run, registry = runner_evidence(tmp_path, domain)
    report = evaluation_module.evaluate_run_artifact(
        frozen,
        dataset_snapshot=snapshot.path,
        run_artifact=run.artifact_path,
        run_id=run.experiment_run_id,
        registry=registry,
        safety_passed=True,
    )
    assert report.input_metrics_digest == run.reproducibility_digest
    published = publish_evaluation_decision(
        report,
        registry=registry,
        run_id=run.experiment_run_id,
        report_root=tmp_path / "reports",
        decided_at="2026-08-31T01:00:00+00:00",
    )
    assert published.status == "created"


@pytest.mark.parametrize("mutation", ["artifact", "paired_forgery"])
def test_runner_evaluation_rejects_tampering_and_paired_row_forgery(tmp_path, mutation):
    frozen, snapshot, run, registry = runner_evidence(tmp_path, Domain.AU, forged_row=mutation == "paired_forgery")
    if mutation == "artifact":
        (run.artifact_path / "metrics.json").write_text("{}", encoding="utf-8")
    with pytest.raises(EvaluationError, match="artifact|frozen dataset row"):
        evaluation_module.evaluate_run_artifact(
            frozen,
            dataset_snapshot=snapshot.path,
            run_artifact=run.artifact_path,
            run_id=run.experiment_run_id,
            registry=registry,
            safety_passed=True,
        )
