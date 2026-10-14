from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

DASHBOARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD))
sys.path.insert(0, str(DASHBOARD.parent / ".agents/skills"))

import generate_static
import shared_wong_choi
sys.path.insert(0, str(Path(shared_wong_choi.__file__).resolve().parent / "tests"))

from services.research_exporter import (
    build_research_feed,
    generate_local_research_html,
    main as research_dashboard_main,
)
from test_research_presentation import receipt
from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import ResearchIndexError
from shared_wong_choi.research_registry import ExperimentDecisionState


def empty_data():
    return {"meetings": [], "races": {}, "consensus": {}, "roi": {}, "sports_history": {}}


def test_feed_is_repeatable_domain_scoped_and_retains_unknown_evidence(tmp_path):
    path = receipt(tmp_path)
    feed = build_research_feed([path], registry_root=tmp_path / "registry")
    assert feed == build_research_feed([path], registry_root=tmp_path / "registry")
    assert feed["visibility"] == "local_review_only"
    view = feed["domains"]["au"]
    assert view["verified_monitoring_samples"] is None
    assert view["live_drift"] is None and view["storage_health"] is None
    assert view["experiments"][0]["datasets"][0]["manifest_rows"] == 100
    assert view["experiments"][0]["runs"][0]["registered_decisions"][0]["report_verification"] == "not_supplied"
    assert str(tmp_path) not in json.dumps(feed)
    assert view["model_promotion_allowed"] is False


def test_explicit_review_summary_projects_liveness_without_local_paths(tmp_path):
    from test_research_presentation import liveness_review
    runtime, registry, liveness, review, receipt_path = liveness_review(tmp_path)

    feed = build_research_feed(
        [receipt_path], registry_root=registry.root,
        review_summary_paths={"au": review.report_path},
    )

    view = feed["domains"]["au"]
    assert view["process_liveness_verified"] is True
    assert view["queue_completeness_verified"] is True
    assert view["process_liveness"]["content_hash"] == liveness.content_hash
    assert view["process_liveness"]["counts"]["running_verified"] == 1
    assert str(runtime.warm_root) not in json.dumps(feed)
    assert view["model_promotion_allowed"] is False
    html = generate_local_research_html(
        [receipt_path], registry_root=registry.root,
        review_summary_paths={"au": review.report_path},
    )
    assert '"process_liveness_verified": true' in html
    assert '"running_verified": 1' in html
    assert str(runtime.warm_root) not in html


def test_explicit_review_summary_projects_storage_without_local_paths(
        tmp_path, monkeypatch):
    from test_research_presentation import storage_review

    _, registry, storage, review, receipt_path = storage_review(tmp_path, monkeypatch)
    feed = build_research_feed(
        [receipt_path], registry_root=registry.root,
        review_summary_paths={"au": review.report_path},
    )

    view = feed["domains"]["au"]
    assert view["storage_health"] == "attention"
    assert view["storage_evidence"]["content_hash"] == storage.content_hash
    assert str(tmp_path) not in json.dumps(feed)
    html = generate_local_research_html(
        [receipt_path], registry_root=registry.root,
        review_summary_paths={"au": review.report_path},
    )
    assert "儲存需留意" in html
    assert storage.content_hash in html
    assert str(tmp_path) not in html
    assert '"model_promotion_allowed": false' in html


def test_explicit_review_summary_projects_production_day_without_local_paths(tmp_path):
    from test_research_presentation import production_day_review

    evidence, review, receipt_path = production_day_review(tmp_path)
    registry = tmp_path / "registry"
    feed = build_research_feed(
        [receipt_path], registry_root=registry,
        review_summary_paths={"au": review.report_path},
    )

    view = feed["domains"]["au"]
    assert view["production_day_evidence_status"] == "verified_closed"
    assert view["production_day_evidence"]["content_hash"] == evidence.content_hash
    assert view["production_day_evidence"]["production_day"] == "2026-09-03"
    assert str(tmp_path) not in json.dumps(feed)
    html = generate_local_research_html(
        [receipt_path], registry_root=registry,
        review_summary_paths={"au": review.report_path},
    )
    assert "生產日已完整核實" in html
    assert "2026-09-03" in html
    assert str(tmp_path) not in html


def test_explicit_review_summary_projects_descriptive_drift_without_local_paths(
        tmp_path):
    from test_research_presentation import live_drift_review

    drift, review, receipt_path = live_drift_review(tmp_path)
    registry = tmp_path / "registry"
    feed = build_research_feed(
        [receipt_path], registry_root=registry,
        review_summary_paths={"au": review.report_path},
    )

    view = feed["domains"]["au"]
    assert view["live_drift_evidence_status"] == "verified_insufficient_data"
    assert view["live_drift"]["content_hash"] == drift.content_hash
    assert view["live_drift"]["current_records"] == 1
    assert view["live_drift"]["metric_drift_verified"] is False
    assert view["live_drift"]["market_drift_verified"] is False
    assert str(tmp_path) not in json.dumps(feed)
    html = generate_local_research_html(
        [receipt_path], registry_root=registry,
        review_summary_paths={"au": review.report_path},
    )
    assert "特徵 drift 證據不足" in html
    assert "模型指標／市場 drift 未核實" in html
    assert str(tmp_path) not in html


def test_proposal_is_not_a_dashboard_promotion_or_betting_action(tmp_path):
    path = receipt(tmp_path, state=ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL)
    feed = build_research_feed([path], registry_root=tmp_path / "registry")
    choice = feed["domains"]["au"]["experiments"][0]["runs"][0]["registered_decisions"][0]
    assert choice["next_human_action"] == "verify_evidence_then_shadow_review"
    assert feed["read_only"] is True


@pytest.mark.parametrize("fault", ["wrong_registry", "duplicate", "corrupt"])
def test_feed_rejects_ambiguous_or_invalid_evidence(tmp_path, fault):
    path = receipt(tmp_path)
    registry = tmp_path / "registry"
    paths = [path]
    if fault == "wrong_registry":
        registry = tmp_path / "other"
    elif fault == "duplicate":
        paths *= 2
    else:
        path.write_text(path.read_text().replace('"model_promotion_allowed":false', '"model_promotion_allowed":true'))
    with pytest.raises((ResearchIndexError, ValueError)):
        build_research_feed(paths, registry_root=registry)


def test_normal_public_generation_never_carries_cached_private_research(tmp_path):
    data = {**empty_data(), "research_feed": {"secret": "PRIVATE_RESEARCH_MARKER"}}
    with patch.object(generate_static, "build_multisport_feed", return_value={"sports": {}}):
        html = generate_static.generate_html(data)
    assert "PRIVATE_RESEARCH_MARKER" not in html
    assert "research_feed" not in data
    assert "const RESEARCH_DATA = null;" in html
    assert 'const DEFAULT_WORKSPACE = "horses";' in html


def test_local_view_does_not_scan_live_sports_or_emit_source_paths(tmp_path):
    path = receipt(tmp_path, domain=Domain.TENNIS)
    with patch.object(generate_static, "build_multisport_feed", side_effect=AssertionError("must not read live sports")):
        html = generate_local_research_html([path], registry_root=tmp_path / "registry")
    assert "wong-choi-research-dashboard/v1" in html
    assert str(tmp_path) not in html
    assert "pace feature improves" in html
    assert '"read_only": true' in html


def test_script_embedding_cannot_be_escaped_by_research_strings(tmp_path, monkeypatch):
    import services.research_exporter as exporter
    attack = "</script><img src=x onerror=alert(1)>\u2028&"
    monkeypatch.setattr(exporter, "build_research_feed", lambda *a, **k: {"text": attack})
    html = generate_local_research_html([], registry_root=tmp_path)
    assert attack not in html
    assert "\\u003c/script\\u003e" in html
    assert "\\u2028" in html


def test_template_markers_inside_verified_data_are_not_replaced(tmp_path, monkeypatch):
    import services.research_exporter as exporter
    marker = "__GENERATED_TIME__"
    monkeypatch.setattr(exporter, "build_research_feed", lambda *a, **k: {"text": marker})
    html = generate_local_research_html([], registry_root=tmp_path)
    assert '"text": "__GENERATED_TIME__"' in html


def test_feed_size_limit_is_explicit_not_silent_truncation(tmp_path, monkeypatch):
    import services.research_exporter as exporter
    path = receipt(tmp_path)
    monkeypatch.setattr(exporter, "MAX_FEED_BYTES", 100)
    with pytest.raises(ValueError, match="display budget"):
        build_research_feed([path], registry_root=tmp_path / "registry")


def test_feed_rejects_receipt_replacement_between_verified_reads(tmp_path, monkeypatch):
    import services.research_exporter as exporter
    path = receipt(tmp_path)
    original = exporter.prepare_review_presentation
    def changed(path, **kwargs):
        result = original(path, **kwargs)
        result["projection"]["receipt_hash"] = "e" * 64
        return result
    monkeypatch.setattr(exporter, "prepare_review_presentation", changed)
    with pytest.raises(ValueError, match="changed"):
        build_research_feed([path], registry_root=tmp_path / "registry")


def test_selection_order_does_not_change_feed_and_never_writes(tmp_path, monkeypatch):
    au = receipt(tmp_path)
    tennis = receipt(tmp_path, domain=Domain.TENNIS)
    def forbidden(*args, **kwargs):
        raise AssertionError("no writes or networking")
    import socket
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    expected = build_research_feed([au, tennis], registry_root=tmp_path / "registry")
    assert expected == build_research_feed([tennis, au], registry_root=tmp_path / "registry")
    assert set(expected["domains"]) == {"au", "tennis"}


def test_real_report_ci_survives_projection_without_safety_artifact_paths(tmp_path, monkeypatch):
    from test_research_index import NOW, clock_args
    from test_research_postflight import evidence_fixture
    from shared_wong_choi.research_index import record_review
    from shared_wong_choi.research_review_clock import plan_reviews
    import shared_wong_choi.research_evaluation as evaluation
    experiment, arguments = evidence_fixture(tmp_path, use_harness=True)
    report = evaluation.evaluate_run_artifact(experiment, **arguments)
    publication = evaluation.publish_evaluation_decision(
        report, registry=arguments["registry"], run_id=arguments["run_id"],
        report_root=tmp_path / "reports", decided_at=NOW.isoformat(),
        verification=evaluation.EvaluationVerification(experiment, arguments["dataset_snapshot"],
                                                       arguments["run_artifact"], arguments["evidence"]),
    )
    clock = {**clock_args(), "ruler_digest": experiment.evaluation_ruler_digest}
    review = record_review(root=tmp_path / "reviews", registry_root=arguments["registry"].root,
                          clock_inputs=clock, request_id=plan_reviews(**clock)["requests"][0]["request_id"],
                          report_paths={publication.decision_id: publication.report_path})
    def forbidden(*args, **kwargs):
        raise AssertionError("export must not re-evaluate")
    monkeypatch.setattr(evaluation, "evaluate_run_artifact", forbidden)
    feed = build_research_feed([review["path"]], registry_root=arguments["registry"].root)
    projected = feed["domains"]["au"]["experiments"][0]["runs"][0]["registered_decisions"][0]["report"]
    assert set(projected) == {"content_hash", "scopes"}
    assert projected["scopes"] == report.to_payload()["scopes"]
    assert str(tmp_path) not in json.dumps(projected)


def test_local_cli_creates_private_dashboard_once_without_public_generation(tmp_path):
    receipt_path = receipt(tmp_path)
    output = tmp_path / "private-research.html"

    with patch.object(
            generate_static, "build_multisport_feed",
            side_effect=AssertionError("local research must not build public sports feed")):
        assert research_dashboard_main([
            "--registry-root", str((tmp_path / "registry").resolve()),
            "--receipt", str(receipt_path.resolve()),
            "--output", str(output.resolve()),
        ]) == 0

    assert output.stat().st_mode & 0o777 == 0o600
    html = output.read_text(encoding="utf-8")
    assert "wong-choi-research-dashboard/v1" in html
    assert 'visibility\": \"local_review_only' in html
    assert 'const DEFAULT_WORKSPACE = "research";' in html
    assert str(tmp_path) not in html
    with pytest.raises(FileExistsError):
        research_dashboard_main([
            "--registry-root", str((tmp_path / "registry").resolve()),
            "--receipt", str(receipt_path.resolve()),
            "--output", str(output.resolve()),
        ])


@pytest.mark.parametrize(
    ("flag", "relative"),
    [
        ("--registry-root", "registry"),
        ("--receipt", "receipt.json"),
        ("--output", "output.html"),
    ],
)
def test_local_cli_requires_absolute_paths(tmp_path, flag, relative):
    receipt_path = receipt(tmp_path)
    arguments = [
        "--registry-root", str((tmp_path / "registry").resolve()),
        "--receipt", str(receipt_path.resolve()),
        "--output", str((tmp_path / "private-research.html").resolve()),
    ]
    arguments[arguments.index(flag) + 1] = relative
    with pytest.raises(ValueError, match="absolute"):
        research_dashboard_main(arguments)


def test_local_cli_rejects_symlinked_output_parent(tmp_path):
    receipt_path = receipt(tmp_path)
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        research_dashboard_main([
            "--registry-root", str((tmp_path / "registry").resolve()),
            "--receipt", str(receipt_path.resolve()),
            "--output", str(linked_parent / "private-research.html"),
        ])
    assert not (real_parent / "private-research.html").exists()


def test_module_cli_honours_explicit_stage5_package_path(tmp_path):
    receipt_path = receipt(tmp_path)
    output = tmp_path / "subprocess-private-research.html"
    skills_root = Path(shared_wong_choi.__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((
        str(skills_root),
        str(DASHBOARD / "backend"),
    ))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.research_exporter",
            "--registry-root", str((tmp_path / "registry").resolve()),
            "--receipt", str(receipt_path.resolve()),
            "--output", str(output.resolve()),
        ],
        cwd=DASHBOARD.parent,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert 'const DEFAULT_WORKSPACE = "research";' in output.read_text(encoding="utf-8")
