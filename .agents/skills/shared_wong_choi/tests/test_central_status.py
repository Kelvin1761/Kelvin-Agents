from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi import central_status  # noqa: E402
from shared_wong_choi.central_status import collect_status, render_telegram  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def initialise_repo(root: Path) -> None:
    remote = root.parent / "remote.git"
    git(root.parent, "init", "--bare", str(remote))
    git(root, "init")
    git(root, "config", "user.name", "Central Status Test")
    git(root, "config", "user.email", "wc@example.test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "base")
    git(root, "branch", "-M", "main")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "main")
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")


def write_au_running_manifest(state: Path, *, started_at: str) -> None:
    run_path = state / "runs" / "au" / "2026-08-26" / "evening" / "2200"
    run_path.mkdir(parents=True)
    (run_path / "attempt-1.json").write_text(
        json.dumps(
            {
                "run_id": "wc:au:run:2026-08-26:evening:2200:attempt-1",
                "state": "running",
                "mode": "evening",
                "target_date": "2026-08-26",
                "started_at": started_at,
                "completed_at": None,
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


def test_status_reports_git_runs_releases_and_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialise_repo(repo)
    state = tmp_path / "state"
    run_path = state / "runs" / "au" / "2026-08-26" / "evening" / "2200"
    run_path.mkdir(parents=True)
    (run_path / "attempt-1.json").write_text(
        json.dumps(
            {
                "run_id": "wc:au:run:2026-08-26:evening:2200:attempt-1",
                "state": "succeeded",
                "mode": "evening",
                "target_date": "2026-08-26",
                "completed_at": "2026-08-26T12:00:00+00:00",
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    releases = state / "releases"
    releases.mkdir(parents=True)
    (releases / "pending.json").write_text(
        json.dumps(
            {
                "schema_version": "wong-choi-release/v1",
                "release_id": "wc-release:abc",
                "created_at": "2026-08-26T12:30:00+00:00",
                "status": "pushed",
                "policy": {"risk": "code"},
                "commit": "abcdef123456",
                "branch": "codex/example",
                "activation": "not_started",
            }
        ),
        encoding="utf-8",
    )

    result = collect_status(
        repo,
        state,
        now=datetime(2026, 8, 26, 13, tzinfo=timezone.utc),
    )

    assert result["status"] == "attention"
    assert result["domains"]["au"]["latest_run"]["state"] == "succeeded"
    assert result["releases"]["pending_approval"][0]["commit"] == "abcdef123456"
    assert result["releases"]["origin_main"]["tracked"] is False
    assert "origin_main_without_release_manifest" in result["attention"]
    assert result["evidence"]["status"] == "ok"
    message = render_telegram(result)
    assert "AU：succeeded" in message
    assert "Release：abcdef123456 · pushed · activate not_started" in message
    assert "待批准：1 個 · Telegram /approve abcdef123456" in message
    assert "Main trail：⛔" in message


def test_origin_main_exact_release_manifest_is_tracked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialise_repo(repo)
    state = tmp_path / "state"
    releases = state / "releases"
    releases.mkdir(parents=True)
    commit = git(repo, "rev-parse", "origin/main")
    (releases / "merged.json").write_text(
        json.dumps(
            {
                "schema_version": "wong-choi-release/v1",
                "release_id": "wc-release:tracked",
                "created_at": "2026-08-26T12:30:00+00:00",
                "status": "merged",
                "policy": {"risk": "docs_tests"},
                "commit": commit,
                "branch": "codex/tracked",
                "activation": "not_started",
            }
        ),
        encoding="utf-8",
    )

    result = collect_status(
        repo,
        state,
        now=datetime(2026, 8, 26, 13, tzinfo=timezone.utc),
    )

    assert result["releases"]["origin_main"] == {
        "commit": commit,
        "tracked": True,
        "release_id": "wc-release:tracked",
        "activation": "not_started",
    }
    assert "origin_main_without_release_manifest" not in result["attention"]
    assert "Main trail：✅ tracked" in render_telegram(result)


def test_long_au_evening_run_is_visible_as_healthy_within_timeout(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialise_repo(repo)
    state = tmp_path / "state"
    write_au_running_manifest(state, started_at="2026-08-26T12:00:00+00:00")

    result = collect_status(
        repo,
        state,
        now=datetime(2026, 8, 26, 14, 30, tzinfo=timezone.utc),
    )

    run = result["domains"]["au"]["latest_run"]
    assert run["lifecycle"] == "within_timeout"
    assert run["elapsed_seconds"] == 2 * 3600 + 30 * 60
    assert run["timeout_seconds"] == 11 * 3600
    assert run["remaining_seconds"] == 8 * 3600 + 30 * 60
    assert run["deadline_at"] == "2026-08-26T23:00:00+00:00"
    assert "run_overdue:au" not in result["attention"]
    assert "⏳ AU：running 2h30m / 11h00m · 仲有 8h30m" in render_telegram(result)


def test_overdue_running_manifest_fails_visible(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialise_repo(repo)
    state = tmp_path / "state"
    write_au_running_manifest(state, started_at="2026-08-26T12:00:00+00:00")

    result = collect_status(
        repo,
        state,
        now=datetime(2026, 8, 27, 0, 30, tzinfo=timezone.utc),
    )

    run = result["domains"]["au"]["latest_run"]
    assert run["lifecycle"] == "overdue"
    assert run["elapsed_seconds"] == 12 * 3600 + 30 * 60
    assert run["remaining_seconds"] == 0
    assert "run_overdue:au" in result["attention"]
    assert "🧯 AU：running OVERDUE · 12h30m / 11h00m" in render_telegram(result)


def test_dirty_production_checkout_is_visible(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialise_repo(repo)
    production = tmp_path / "production"
    git(tmp_path, "clone", str(tmp_path / "remote.git"), str(production))
    (production / "README.md").write_text("dirty\n", encoding="utf-8")
    seen: dict[str, Path] = {}

    def fake_runtime(_roots, *, control_root, **_kwargs):
        seen["control_root"] = control_root
        return {
            "status": "attention",
            "domains": {"au": {"status": "attention"}},
            "central": {"status": "attention", "labels": []},
            "attention": ["runtime_launchd_not_aligned:au"],
        }

    monkeypatch.setattr(central_status, "collect_runtime_alignment", fake_runtime)

    result = collect_status(
        repo,
        tmp_path / "state",
        production_roots={"au": production},
        now=datetime(2026, 8, 26, 13, tzinfo=timezone.utc),
    )

    assert "production_checkout_not_clean:au" in result["attention"]
    assert result["git"]["production"]["au"]["dirty_paths"] == ("README.md",)
    assert result["git"]["production"]["au"]["release_tracked"] is False
    assert "production_commit_without_release_manifest:au" in result["attention"]
    assert "runtime_launchd_not_aligned:au" in result["attention"]
    assert seen["control_root"] == production.resolve()
    assert "Production：AU" in render_telegram(result)
    assert "Automation：AU ❌" in render_telegram(result)
