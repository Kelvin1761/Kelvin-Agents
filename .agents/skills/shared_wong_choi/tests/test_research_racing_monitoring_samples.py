import json
from datetime import timedelta

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_settlement_for_event
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_racing_monitoring_samples import (
    inspect_racing_monitoring_samples,
    monitoring_sample_snapshot,
    verify_racing_monitoring_sample_report,
)
from test_research_au_feature_provenance import (
    AS_OF as AU_PREDICTED_AT,
    EVENT as AU_EVENT,
    fixture as au_feature_fixture,
)
from test_research_hkjc_feature_provenance import (
    AS_OF as HKJC_PREDICTED_AT,
    EVENT as HKJC_EVENT,
    fixture as hkjc_feature_fixture,
)


def _au_source(tmp_path, *, feature_mode="valid", label=True):
    evidence = au_feature_fixture(tmp_path, feature_mode)
    meeting = tmp_path / "hot" / AU_EVENT
    result = meeting / "Race_Results_Reflector.md"
    result.write_text(
        "# Results\n\n## Race 1\n"
        "1st: #7 Fast Horse SP$3.00\n"
        "2nd: #4 Second Horse (0.20L) SP$4.00\n"
        "3rd: #2 Third Horse (0.50L) SP$5.00\n",
        encoding="utf-8",
    )
    rendered = meeting / f"{AU_EVENT}_Reflector_Report.md"
    rendered.write_text("# AU reflector\n", encoding="utf-8")
    record_settlement_for_event(
        domain=Domain.AU,
        event_id=AU_EVENT,
        evidence_root=evidence,
        summary={"meeting": AU_EVENT},
        artifacts=[rendered, result] if label else [rendered],
        settled_at=AU_PREDICTED_AT + timedelta(hours=1),
        required=True,
    )
    return evidence, AU_PREDICTED_AT + timedelta(hours=2), result


def _hkjc_source(tmp_path, *, feature_mode="valid", label=True):
    evidence, snapshot = hkjc_feature_fixture(tmp_path, feature_mode)
    meeting = snapshot.parents[1]
    result = meeting / "full_day_results.json"
    result.write_text(json.dumps({
        "1": {"venue": "ST", "results": [
            {"pos": "1", "horse_no": 7, "horse_name": "快馬", "lbw": "-", "win_odds": 3.0},
            {"pos": "2", "horse_no": 4, "horse_name": "第二馬", "lbw": "0.2", "win_odds": 4.0},
            {"pos": "3", "horse_no": 2, "horse_name": "第三馬", "lbw": "0.5", "win_odds": 5.0},
        ]},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    rendered = meeting / "HKJC_Reflection_Report.md"
    rendered.write_text("# HKJC reflector\n", encoding="utf-8")
    record_settlement_for_event(
        domain=Domain.HKJC,
        event_id=HKJC_EVENT,
        evidence_root=evidence,
        summary={"meeting": meeting.name},
        artifacts=[rendered, result] if label else [rendered],
        settled_at=HKJC_PREDICTED_AT + timedelta(hours=10),
        required=True,
    )
    return evidence, HKJC_PREDICTED_AT + timedelta(hours=12), result


@pytest.mark.parametrize(
    ("domain", "source"),
    [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)],
)
def test_verified_label_and_feature_provenance_make_one_settled_race_sample(
        tmp_path, domain, source):
    evidence, as_of, _result = source(tmp_path)
    report = inspect_racing_monitoring_samples(
        root=evidence, domain=domain, as_of=as_of,
    )
    snapshot = monitoring_sample_snapshot(report)

    assert report["qualified_races"] == 1
    assert report["candidate_settlements"] == 1
    assert report["blocked_settlements"] == 0
    assert snapshot.domain is domain
    assert snapshot.scope == "all"
    assert snapshot.basis == "settled_races"
    assert snapshot.evidence_digest == report["content_hash"]
    assert snapshot.unit_ids == frozenset({report["units"][0]["unit_id"]})
    assert report["model_promotion_allowed"] is False
    assert report["terminal_labels_emitted"] is False


@pytest.mark.parametrize(
    ("domain", "source", "change"),
    [
        (Domain.AU, _au_source, {"feature_mode": "legacy"}),
        (Domain.HKJC, _hkjc_source, {"feature_mode": "legacy"}),
        (Domain.AU, _au_source, {"label": False}),
        (Domain.HKJC, _hkjc_source, {"label": False}),
    ],
)
def test_missing_feature_or_label_never_becomes_a_sample(tmp_path, domain, source, change):
    evidence, as_of, _result = source(tmp_path, **change)
    report = inspect_racing_monitoring_samples(
        root=evidence, domain=domain, as_of=as_of,
    )

    assert report["qualified_races"] == 0
    assert report["blocked_settlements"] == 1
    assert report["units"] == []
    assert monitoring_sample_snapshot(report).unit_ids == frozenset()


@pytest.mark.parametrize(
    ("domain", "source"),
    [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)],
)
def test_parent_verifier_rebuilds_from_sources_and_rejects_rehashed_unit(
        tmp_path, domain, source):
    evidence, as_of, _result = source(tmp_path)
    report = inspect_racing_monitoring_samples(root=evidence, domain=domain, as_of=as_of)
    report["units"][0]["unit_id"] += ":forged"
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})

    with pytest.raises((ValueError, RuntimeError)):
        verify_racing_monitoring_sample_report(
            report, root=evidence, domain=domain, as_of=as_of,
        )


def test_snapshot_conversion_cannot_skip_source_reverification(tmp_path):
    evidence, as_of, _result = _au_source(tmp_path)
    report = inspect_racing_monitoring_samples(
        root=evidence, domain=Domain.AU, as_of=as_of,
    )
    report["units"][0]["event_id"] = "forged-but-shaped"
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})

    with pytest.raises((ValueError, RuntimeError)):
        monitoring_sample_snapshot(report)


@pytest.mark.parametrize(
    ("domain", "source"),
    [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)],
)
def test_mutated_hash_pinned_result_is_rejected_not_dropped(tmp_path, domain, source):
    evidence, as_of, result = source(tmp_path)
    result.write_text("mutated after settlement\n", encoding="utf-8")

    with pytest.raises((ValueError, RuntimeError)):
        inspect_racing_monitoring_samples(root=evidence, domain=domain, as_of=as_of)


def test_only_au_and_hkjc_are_accepted(tmp_path):
    with pytest.raises((ValueError, RuntimeError)):
        inspect_racing_monitoring_samples(
            root=tmp_path, domain=Domain.TENNIS,
            as_of=AU_PREDICTED_AT,
        )
