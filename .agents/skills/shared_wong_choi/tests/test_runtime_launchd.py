from __future__ import annotations

import plistlib
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

import shared_wong_choi.runtime_launchd as runtime_launchd  # noqa: E402
from shared_wong_choi.runtime_launchd import (  # noqa: E402
    CENTRAL_LABELS,
    DOMAIN_LABELS,
    collect_runtime_alignment,
)


def _write_plist(path: Path, arguments: list[str], working: str | None = None) -> None:
    payload = {"Label": path.stem, "ProgramArguments": arguments}
    if working:
        payload["WorkingDirectory"] = working
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def _aligned_fixture(agents: Path, root: Path) -> None:
    for labels in (*DOMAIN_LABELS.values(), CENTRAL_LABELS):
        for label, relatives in labels.items():
            _write_plist(
                agents / f"{label}.plist",
                [str(root / relative) for relative in relatives],
            )


def test_runtime_alignment_requires_every_label_on_production_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "production"
    agents = tmp_path / "LaunchAgents"
    _aligned_fixture(agents, root)

    result = collect_runtime_alignment(
        {name: root for name in DOMAIN_LABELS},
        control_root=root,
        launch_agents_root=agents,
        probe_loaded=False,
    )

    assert result["status"] == "aligned"
    assert all(item["status"] == "aligned" for item in result["domains"].values())
    assert result["central"]["status"] == "aligned"


def test_runtime_alignment_exposes_primary_repo_and_missing_labels(
    tmp_path: Path,
) -> None:
    root = tmp_path / "production"
    primary = tmp_path / "primary"
    agents = tmp_path / "LaunchAgents"
    _aligned_fixture(agents, root)
    label = "com.antigravity.nba-wong-choi.health"
    _write_plist(
        agents / f"{label}.plist",
        [
            str(
                primary
                / ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh"
            )
        ],
    )
    (agents / "com.antigravity.tennis-wong-choi.card.plist").unlink()

    result = collect_runtime_alignment(
        {name: root for name in DOMAIN_LABELS},
        control_root=root,
        launch_agents_root=agents,
        probe_loaded=False,
    )

    assert result["status"] == "attention"
    assert result["domains"]["nba"]["status"] == "attention"
    nba = result["domains"]["nba"]["labels"]
    assert next(item for item in nba if item["label"] == label)["status"] == (
        "misaligned"
    )
    assert result["domains"]["tennis"]["status"] == "attention"
    assert "runtime_launchd_not_aligned:nba" in result["attention"]
    assert "runtime_launchd_not_aligned:tennis" in result["attention"]


def test_invalid_installed_plist_is_reported_instead_of_crashing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "production"
    agents = tmp_path / "LaunchAgents"
    _aligned_fixture(agents, root)
    label = "com.antigravity.au-wong-choi.bot"
    (agents / f"{label}.plist").write_text("<plist><broken&></plist>")

    result = collect_runtime_alignment(
        {name: root for name in DOMAIN_LABELS},
        control_root=root,
        launch_agents_root=agents,
        probe_loaded=False,
    )

    entry = next(
        item
        for item in result["domains"]["au"]["labels"]
        if item["label"] == label
    )
    assert entry["status"] == "invalid"
    assert entry["error"].startswith("ExpatError:")


def test_only_explicit_handoff_bot_may_be_transiently_unloaded(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "production"
    agents = tmp_path / "LaunchAgents"
    _aligned_fixture(agents, root)
    bot = "com.antigravity.au-wong-choi.bot"
    monkeypatch.setattr(runtime_launchd, "_loaded", lambda label: label != bot)

    strict = collect_runtime_alignment(
        {name: root for name in DOMAIN_LABELS},
        control_root=root,
        launch_agents_root=agents,
    )
    handoff = collect_runtime_alignment(
        {name: root for name in DOMAIN_LABELS},
        control_root=root,
        launch_agents_root=agents,
        allow_unloaded_labels=frozenset({bot}),
    )

    assert strict["status"] == "attention"
    assert handoff["status"] == "aligned"
    entry = next(
        item for item in handoff["domains"]["au"]["labels"] if item["label"] == bot
    )
    assert entry["loaded"] is False
    assert entry["unloaded_allowed"] is True
