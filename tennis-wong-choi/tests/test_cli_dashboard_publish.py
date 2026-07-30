from __future__ import annotations

from argparse import Namespace


def _ready_payload() -> dict:
    return {
        "matches_analysed": 40,
        "valid_feature_snapshots": 40,
        "odds_coverage": {"fixtures": 60, "priced_matches": 40},
        "source_errors": [],
    }


def test_ready_manual_run_uses_pipeline_owned_dashboard_deploy(tmp_path, monkeypatch):
    from tennis_wc import cli

    calls = []
    monkeypatch.setattr(cli, "analysis_output_dir", lambda _: tmp_path)

    def fake_deploy(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(cli, "run_post_success_cloudflare_deploy", fake_deploy)
    payload = _ready_payload()

    cli._publish_daily_dashboard(
        Namespace(date="2026-07-29", skip_cloudflare_deploy=False),
        payload,
    )

    assert payload["readiness"]["status"] == "ready"
    assert payload["cloudflare_deploy"] == {
        "attempted": True,
        "status": "deployed",
    }
    assert calls == [
        {
            "source": "Tennis Wong Choi",
            "target_dir": tmp_path,
            "skip": False,
            "allow_failure": False,
        }
    ]


def test_incomplete_run_blocks_dashboard_without_calling_deploy(monkeypatch):
    from tennis_wc import cli

    monkeypatch.setattr(
        cli,
        "run_post_success_cloudflare_deploy",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("incomplete analysis must not deploy")
        ),
    )
    payload = _ready_payload()
    payload["odds_coverage"] = {"fixtures": 100, "priced_matches": 2}

    cli._publish_daily_dashboard(
        Namespace(date="2026-07-29", skip_cloudflare_deploy=False),
        payload,
    )

    assert payload["readiness"]["status"] == "incomplete"
    assert payload["cloudflare_deploy"] == {
        "attempted": False,
        "status": "blocked_by_completeness_gate",
    }


def test_skip_flag_keeps_ready_run_local(tmp_path, monkeypatch):
    from tennis_wc import cli

    calls = []
    monkeypatch.setattr(cli, "analysis_output_dir", lambda _: tmp_path)

    def fake_deploy(**kwargs):
        calls.append(kwargs)
        return False

    monkeypatch.setattr(cli, "run_post_success_cloudflare_deploy", fake_deploy)
    payload = _ready_payload()

    cli._publish_daily_dashboard(
        Namespace(date="2026-07-29", skip_cloudflare_deploy=True),
        payload,
    )

    assert payload["readiness"]["status"] == "ready"
    assert payload["cloudflare_deploy"] == {
        "attempted": False,
        "status": "skipped",
    }
    assert calls[0]["skip"] is True
