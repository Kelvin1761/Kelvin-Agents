from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.deployment_verify import verify_deployment  # noqa: E402


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture_checkout(root: Path, *, wrapper: str = "same") -> None:
    _write(root, ".agents/skills/shared_wong_choi/contracts.py", "contract\n")
    _write(
        root,
        ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh",
        wrapper,
    )


def test_aligned_checkout_is_safe_to_activate(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _fixture_checkout(source)
    _fixture_checkout(target)
    result = verify_deployment(source, target, "au")
    assert result["status"] == "aligned"
    assert result["safe_to_activate"] is True
    assert result["counts"] == {"aligned": 2}


def test_missing_package_and_different_wrapper_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _fixture_checkout(source)
    _write(
        target,
        ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh",
        "old",
    )
    result = verify_deployment(source, target, "au")
    assert result["status"] == "out_of_sync"
    assert result["safe_to_activate"] is False
    assert result["counts"] == {"target_missing": 1, "different": 1}
