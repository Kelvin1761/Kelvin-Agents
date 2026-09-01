"""Catalog-aware NBA settled-day folder discovery for full-history ML work."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = PROJECT_ROOT / ".agents" / "skills"
for value in (PROJECT_ROOT, SKILLS_ROOT):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from shared_wong_choi.corpus_catalog import merged_directory_corpus  # noqa: E402
from wongchoi_paths import NBA_ANALYSIS  # noqa: E402


def nba_archive_folders() -> list[tuple[str, Path]]:
    """HOT + verified WARM day folders, deduplicated by the original day name."""
    return merged_directory_corpus(
        NBA_ANALYSIS,
        domain="nba",
        artifact_classes=("settled-day", "analysis-day"),
    )
