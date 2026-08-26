"""Factory for the four manifest-backed Wong Choi domain adapters."""

from __future__ import annotations

from pathlib import Path

from .au_adapter import AUAdapter
from .command_adapter import ManifestCommandAdapter, Runner
from .contracts import Domain
from .hkjc_adapter import HKJCAdapter
from .nba_adapter import NBAAdapter
from .tennis_adapter import TennisAdapter


ADAPTER_TYPES: dict[Domain, type[ManifestCommandAdapter]] = {
    Domain.AU: AUAdapter,
    Domain.HKJC: HKJCAdapter,
    Domain.TENNIS: TennisAdapter,
    Domain.NBA: NBAAdapter,
}


def create_adapter(
    domain: Domain | str,
    repo_root: Path,
    state_root: Path,
    *,
    runner: Runner | None = None,
) -> ManifestCommandAdapter:
    adapter_type = ADAPTER_TYPES[Domain(domain)]
    return adapter_type(repo_root, state_root, runner=runner)
