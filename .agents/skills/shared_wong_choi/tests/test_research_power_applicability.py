import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_power_applicability import (
    inspect_power_applicability,
    verify_power_applicability_report,
)


RULER_ROOT = Path(__file__).resolve().parents[1] / "resources" / "evaluation_rulers"


def ruler_digest(domain):
    return hashlib.sha256((RULER_ROOT / f"{domain}-v{'2' if domain in {'au', 'hkjc'} else '1'}.json").read_bytes()).hexdigest()


def profile(domain="au", *, fault=None):
    if domain in {"au", "hkjc"}:
        families = {
            "gold": "binary_rate_difference",
            "good_positional": "binary_rate_difference",
            "top3_capture_at5": "bounded_ranking_difference",
            "mean_top3_model_rank": "ordinal_rank_difference",
            "competitive_recall_at5": "bounded_ranking_difference",
            "ndcg_at5": "bounded_ranking_difference",
            "top5_pairwise_auc": "bounded_ranking_difference",
        }
    else:
        families = {
            "brier_gain_vs_market": "paired_loss_difference",
            "log_loss_gain_vs_market": "paired_loss_difference",
        }
    version = "2" if domain in {"au", "hkjc"} else "1"
    unit = {"au": "race", "hkjc": "race", "tennis": "match", "nba": "game"}[domain]
    payload = {
        "schema_version": "wong-choi-power-profile/v1",
        "profile_id": f"wc:{domain}:power-profile:test-v1",
        "domain": domain,
        "status": "frozen",
        "ruler_id": f"{domain}-v{version}",
        "ruler_sha256": ruler_digest(domain),
        "authority": "docs/audits/POWER_PROFILE_REVIEW.md",
        "method": "paired_t_design",
        "target": 0.8,
        "min_dev_units": 50,
        "unit": unit,
        "assumptions": {
            "independent_units": True,
            "paired_observations": True,
            "dev_only_variance": True,
            "terminal_size_design": True,
        },
        "metrics": {
            name: {
                "analysis_family": family,
                "minimum_effect": 0.02,
                "sd_floor": 0.05,
                "rationale": f"pre-registered material change for {name}",
            }
            for name, family in families.items()
        },
    }
    if fault == "ruler_hash":
        payload["ruler_sha256"] = "f" * 64
    elif fault == "metric_set":
        del payload["metrics"]["gold"]
    elif fault == "family":
        payload["metrics"]["gold"]["analysis_family"] = "paired_loss_difference"
    elif fault == "assumption":
        payload["assumptions"]["independent_units"] = False
    return payload


def write_profile(root, payload):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{payload['domain']}-power-v1.json").write_text(json.dumps(payload) + "\n")


def test_missing_profiles_fail_closed_for_all_frozen_rulers(tmp_path):
    report = inspect_power_applicability(ruler_root=RULER_ROOT, profile_root=tmp_path)
    assert report["domains_seen"] == 4
    assert report["profiles_verified"] == 0
    assert report["power_applicability_verified"] is False
    assert report["model_promotion_allowed"] is False
    assert {row["domain"] for row in report["records"]} == {item.value for item in Domain}
    assert all(row["blockers"] == ["power_profile_missing"] for row in report["records"])


@pytest.mark.parametrize("domain", [item.value for item in Domain])
def test_hash_bound_profile_can_verify_one_domain_without_granting_promotion(tmp_path, domain):
    write_profile(tmp_path, profile(domain))
    report = inspect_power_applicability(ruler_root=RULER_ROOT, profile_root=tmp_path)
    selected = next(row for row in report["records"] if row["domain"] == domain)
    assert selected["power_profile_verified"] is True
    assert selected["eligible_metrics"] == (7 if domain in {"au", "hkjc"} else 2)
    assert selected["blockers"] == []
    assert report["profiles_verified"] == 1
    assert report["power_applicability_verified"] is False
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize(
    ("fault", "blocker"),
    [
        ("ruler_hash", "power_profile_ruler_mismatch"),
        ("metric_set", "power_profile_metric_mismatch"),
        ("family", "power_profile_family_incompatible"),
        ("assumption", "power_profile_assumptions_unverified"),
    ],
)
def test_invalid_profile_is_inventory_not_power_authority(tmp_path, fault, blocker):
    write_profile(tmp_path, profile(fault=fault))
    report = inspect_power_applicability(ruler_root=RULER_ROOT, profile_root=tmp_path)
    au = next(row for row in report["records"] if row["domain"] == "au")
    assert au["power_profile_verified"] is False
    assert blocker in au["blockers"]


def test_verifier_rejects_forged_power_authority(tmp_path):
    report = inspect_power_applicability(ruler_root=RULER_ROOT, profile_root=tmp_path)
    report["power_applicability_verified"] = True
    report["content_hash"] = _hash({key: value for key, value in report.items() if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_power_applicability_report(report, ruler_root=RULER_ROOT, profile_root=tmp_path)
