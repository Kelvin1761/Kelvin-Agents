"""Deterministic path-based policy for Wong Choi releases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Iterable


class ReleaseRisk(str, Enum):
    DOCS_TESTS = "docs_tests"
    CODE = "code"
    MODEL = "model"
    EVALUATION = "evaluation"
    AUTOMATION = "automation"
    DEPLOYMENT = "deployment"


@dataclass(frozen=True)
class ReleasePolicy:
    risk: ReleaseRisk
    check: str
    auto_push: bool
    auto_merge: bool
    auto_activate: bool
    reasons: tuple[str, ...]


_MODEL_MARKERS = (
    "/scoring.py",
    "/features/",
    "matrix_mapper.py",
    "predictor.py",
    "model.py",
    "weights",
)
_EVALUATION_MARKERS = (
    "docs/model-evaluation-contract.md",
    "/eval.py",
    "_eval.py",
    "backtest",
    "golden_scoring",
    "data_contract.py",
    "evaluation_ruler",
)
_AUTOMATION_MARKERS = (
    "/daily_auto/",
    "daily_schedule.py",
    "/launchd/",
    ".github/workflows/",
)
_DEPLOYMENT_MARKERS = (
    "deploy.sh",
    "deployment_verify.py",
    "cloudflare_deploy_hook.py",
)

_PRODUCTION_RUNTIME_INSTALLER = (
    ".agents/skills/central_wong_choi/install_production_runtime.sh"
)
_APPROVED_ACTIVATION_INSTALLERS = frozenset(
    {
        _PRODUCTION_RUNTIME_INSTALLER,
    }
)


def _normalise(path: str) -> str:
    raw = path.replace("\\", "/")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"release path must be repo-relative: {path!r}")
    value = candidate.as_posix()
    if value.startswith("./"):
        value = value[2:]
    if not value or value == ".":
        raise ValueError(f"release path must be repo-relative: {path!r}")
    return value


def _is_docs_or_tests(path: str) -> bool:
    return (
        path.startswith("docs/")
        or path.endswith(".md")
        or "/tests/" in f"/{path}"
        or path.startswith("tests/")
        or path.endswith("_test.py")
        or path.startswith("Wong Choi 模型說明/")
    )


def classify_release(paths: Iterable[str]) -> ReleasePolicy:
    normalised = tuple(dict.fromkeys(_normalise(path) for path in paths))
    if not normalised:
        raise ValueError("release scope must contain at least one path")

    matches: dict[ReleaseRisk, list[str]] = {risk: [] for risk in ReleaseRisk}
    for path in normalised:
        lowered = path.lower()
        if path == "docs/model-evaluation-contract.md":
            matches[ReleaseRisk.EVALUATION].append(path)
        elif _is_docs_or_tests(path):
            matches[ReleaseRisk.DOCS_TESTS].append(path)
        elif any(marker in lowered for marker in _DEPLOYMENT_MARKERS):
            matches[ReleaseRisk.DEPLOYMENT].append(path)
        elif any(marker in lowered for marker in _EVALUATION_MARKERS):
            matches[ReleaseRisk.EVALUATION].append(path)
        elif any(marker in lowered for marker in _AUTOMATION_MARKERS):
            matches[ReleaseRisk.AUTOMATION].append(path)
        elif any(marker in lowered for marker in _MODEL_MARKERS):
            matches[ReleaseRisk.MODEL].append(path)
        else:
            matches[ReleaseRisk.CODE].append(path)

    if matches[ReleaseRisk.EVALUATION] and matches[ReleaseRisk.MODEL]:
        raise ValueError(
            "evaluation ruler and candidate model must use a separate release"
        )

    precedence = (
        ReleaseRisk.DEPLOYMENT,
        ReleaseRisk.EVALUATION,
        ReleaseRisk.MODEL,
        ReleaseRisk.AUTOMATION,
        ReleaseRisk.CODE,
        ReleaseRisk.DOCS_TESTS,
    )
    risk = next(item for item in precedence if matches[item])
    reasons = tuple(f"{item.value}:{path}" for item in precedence for path in matches[item])
    safe = risk is ReleaseRisk.DOCS_TESTS
    return ReleasePolicy(
        risk=risk,
        check="quick" if safe else "full",
        auto_push=True,
        auto_merge=safe,
        auto_activate=False,
        reasons=reasons,
    )


def activation_plan(paths: Iterable[str]) -> dict:
    """Infer runtime targets without guessing checkout locations or credentials."""
    normalised = tuple(dict.fromkeys(_normalise(path) for path in paths))
    domains: set[str] = set()
    dashboard = False
    manual_reasons: list[str] = []
    installers: list[str] = []
    unified_runtime = _PRODUCTION_RUNTIME_INSTALLER in normalised
    for path in normalised:
        if _is_docs_or_tests(path):
            continue
        lowered = path.lower()
        if ".agents/skills/au_racing/" in lowered:
            domains.add("au")
        if ".agents/skills/hkjc_racing/" in lowered:
            domains.add("hkjc")
        if lowered.startswith("tennis-wong-choi/"):
            domains.add("tennis")
        if ".agents/skills/nba/" in lowered:
            domains.add("nba")
        if any(
            marker in lowered
            for marker in (
                ".agents/skills/shared_wong_choi/",
                ".agents/skills/shared_racing/",
            )
        ):
            domains.update(("au", "hkjc", "tennis", "nba"))
        if ".agents/skills/central_wong_choi/" in lowered:
            domains.add("au")
        if path == _PRODUCTION_RUNTIME_INSTALLER:
            domains.update(("au", "hkjc", "tennis", "nba"))
        if lowered.startswith("horse_racing_dashboard/") or lowered == "deploy.sh":
            dashboard = True
        if path in _APPROVED_ACTIVATION_INSTALLERS:
            if not unified_runtime or path == _PRODUCTION_RUNTIME_INSTALLER:
                installers.append(path)
        elif "install_macos_launchd.sh" in lowered or lowered.endswith(".plist"):
            # A plist belonging to an allowlisted installer is data consumed by
            # that installer, not a second manual action.
            consumed_by_unified = unified_runtime and path.startswith(
                (
                    ".agents/skills/central_wong_choi/",
                    ".agents/skills/hkjc_racing/hkjc_daily_auto/",
                    ".agents/skills/nba/nba_daily_auto/",
                    "tennis-wong-choi/",
                )
            )
            if not consumed_by_unified and not (
                path.startswith(".agents/skills/central_wong_choi/launchd/")
                and ".agents/skills/central_wong_choi/install_macos_launchd.sh"
                in normalised
            ):
                manual_reasons.append(f"launchd_install:{path}")
    return {
        "production_sync_domains": sorted(domains),
        "dashboard_deploy": dashboard,
        "installers": sorted(installers),
        "manual_required": bool(manual_reasons),
        "manual_reasons": manual_reasons,
    }
