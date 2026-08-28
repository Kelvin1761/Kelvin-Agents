from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.artifact_archive import archive_copy  # noqa: E402
from shared_wong_choi.corpus_catalog import (  # noqa: E402
    CorpusCatalogError,
    catalog_meeting_locations,
    resolve_catalog_artifacts,
)


def _archive(tmp_path: Path):
    hot = tmp_path / "AU_Racing"
    source = hot / "2026-08-28 Geelong Race 1-9"
    source.mkdir(parents=True)
    (source / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    warm = tmp_path / "warm"
    warm.mkdir()
    result = archive_copy(
        source,
        warm_root=warm,
        catalog_root=tmp_path / "catalog",
        domain="au",
        artifact_class="settled-meeting",
        allowed_roots=[hot],
    )
    return source, Path(result["destination"]), tmp_path / "catalog"


def test_resolver_prefers_verified_hot_and_reports_degraded_warm(tmp_path: Path) -> None:
    source, warm, catalog = _archive(tmp_path)
    (warm / "Race_1_Logic.json").write_text("corrupt\n", encoding="utf-8")

    report = resolve_catalog_artifacts(catalog_root=catalog, domain="au")

    assert report["status"] == "ok"
    assert report["degraded_artifacts"] == 1
    assert report["artifacts"][0]["resolved"] == str(source)


def test_empty_catalog_does_not_claim_verified_archive_coverage(tmp_path: Path) -> None:
    report = resolve_catalog_artifacts(
        catalog_root=tmp_path / "catalog", domain="nba"
    )

    assert report["status"] == "hot_only_unregistered"
    assert report["known_artifacts"] == 0


def test_resolver_uses_warm_after_hot_retention_cutover(tmp_path: Path) -> None:
    source, warm, catalog = _archive(tmp_path)
    source.rename(source.with_name("source-removed-by-approved-test"))

    locations = catalog_meeting_locations(catalog_root=catalog, domain="au")

    assert locations == [("2026-08-28 Geelong Race 1-9", warm)]


def test_resolver_fails_closed_when_all_known_copies_are_unavailable(
    tmp_path: Path,
) -> None:
    source, warm, catalog = _archive(tmp_path)
    source.rename(source.with_name("hot-offline"))
    warm.rename(warm.with_name("warm-offline"))

    with pytest.raises(CorpusCatalogError, match="full-history corpus unavailable"):
        resolve_catalog_artifacts(catalog_root=catalog, domain="au")

    report = resolve_catalog_artifacts(
        catalog_root=catalog, domain="au", strict=False
    )
    assert report["status"] == "blocked"
    assert report["unavailable_artifacts"] == 1


def test_au_meeting_reader_merges_hot_and_catalog_warm_then_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    scripts = PACKAGE_ROOT.parent / "shared_racing" / "scripts"
    sys.path.insert(0, str(scripts))
    import corpus_paths

    control = tmp_path / "control"
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(control))
    hot = tmp_path / "AU_Racing"
    current = hot / "2026-08-29 Randwick Race 1-10"
    current.mkdir(parents=True)
    (current / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    archived = hot / "2026-08-28 Geelong Race 1-9"
    archived.mkdir()
    (archived / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    warm = tmp_path / "warm"
    warm.mkdir()
    result = archive_copy(
        archived,
        warm_root=warm,
        catalog_root=control / "storage" / "catalog",
        domain="au",
        artifact_class="settled-meeting",
        allowed_roots=[hot],
    )
    archived.rename(hot / "approved-source-removal-simulation")

    meetings = corpus_paths.meeting_dirs(hot)

    assert [path.name for path in meetings] == [
        "2026-08-29 Randwick Race 1-10",
        "2026-08-28 Geelong Race 1-9",
    ]
    Path(result["destination"]).rename(warm / "offline-simulation")
    with pytest.raises(CorpusCatalogError, match="full-history corpus unavailable"):
        corpus_paths.meeting_dirs(hot)


def test_hkjc_full_history_reader_merges_catalog_without_duplicate_meetings(
    tmp_path: Path, monkeypatch
) -> None:
    reflector_scripts = (
        PACKAGE_ROOT.parent / "hkjc_racing" / "hkjc_reflector" / "scripts"
    )
    sys.path.insert(0, str(reflector_scripts))
    import review_auto_weighting as review

    hot = tmp_path / "HK_Racing"
    hot_meeting = hot / "2026-08-28_ShaTin"
    hot_meeting.mkdir(parents=True)
    (hot_meeting / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    warm_duplicate = tmp_path / "warm" / "2026-08-28_ShaTin"
    warm_duplicate.mkdir(parents=True)
    (warm_duplicate / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    warm_only = tmp_path / "warm" / "2026-08-27_HappyValley"
    warm_only.mkdir()
    (warm_only / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        review,
        "catalog_meeting_locations",
        lambda **_kwargs: [
            ("2026-08-28_ShaTin", warm_duplicate),
            ("2026-08-27_HappyValley", warm_only),
        ],
    )

    meetings = review.hk_meeting_dirs([hot])

    assert meetings == [warm_only, hot_meeting]
