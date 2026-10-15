"""corpus_exclusions + corpus_paths：明文排除名單同賽後抽偵測（EXP-20261015-04）。

排除一定要喺 code 入面、可審閱；唔可以靠搬檔入 Archive/（Archive/ 本身係語料）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import corpus_exclusions as ce  # noqa: E402
import corpus_paths as cp  # noqa: E402

DECIDED_2026_10_15 = {
    "2026-08-12 Bendigo Race 1-8",
    "2026-08-12 Canterbury Race 1-7",
    "2026-08-12 Devonport Race 1-8",
    "2026-08-12 Eagle Farm Race 1-8",
    "2026-08-12 Pinjarra Scarpside Race 1-8",
    "2026-09-09 Randwick-Kensington Race 1-7",
    "2026-10-11 Seymour Race 1-10",
}


def _summary(dropped: int | None, races: int = 8, pit: tuple[str, int] | None = None) -> str:
    text = f"# X 2026-08-12\n\n{races} races extracted from Sportsbet.\n"
    if dropped is not None:
        text += f"Form runs kept: 500; dropped as on/after 2026-08-12: {dropped}\n"
    text += "Jockey/trainer LY tokens filled: 1; missing: 0\n"
    if pit:
        text += (f"Point-in-time mode: {pit[0]}; races with page stats recomputed "
                 f"from as-of rows and LY from pre-2026-08-12 snapshots: {pit[1]}\n")
    return text


def _meeting(base: Path, name: str, summary: str | None, races: int = 2) -> Path:
    d = base / name
    d.mkdir(parents=True)
    for n in range(1, races + 1):
        (d / f"Race_{n}_Logic.json").write_text("{}", encoding="utf-8")
    if summary is not None:
        (d / "Meeting_Summary.md").write_text(summary, encoding="utf-8")
    return d


# ── 偵測器 ─────────────────────────────────────────────────────────────────

def test_detector_pre_race_page_is_clean(tmp_path):
    d = _meeting(tmp_path, "2026-08-20 A Race 1-8", _summary(0))
    assert ce.detect_post_race_extraction(d)["status"] == ce.STATUS_CLEAN


def test_detector_dropped_rows_mean_post_race(tmp_path):
    d = _meeting(tmp_path, "2026-08-12 A Race 1-8", _summary(63))
    r = ce.detect_post_race_extraction(d)
    assert r["status"] == ce.STATUS_POST_RACE
    assert r["dropped"] == 63 and r["races"] == 8


def test_detector_pit_recompute_of_every_race_is_not_a_leak(tmp_path):
    d = _meeting(tmp_path, "2026-08-12 A Race 1-8", _summary(63, pit=("historical", 8)))
    assert ce.detect_post_race_extraction(d)["status"] == ce.STATUS_PIT_FIXED


def test_detector_partial_pit_recompute_still_leaks(tmp_path):
    d = _meeting(tmp_path, "2026-08-12 A Race 1-8", _summary(63, pit=("live", 0)))
    assert ce.detect_post_race_extraction(d)["status"] == ce.STATUS_POST_RACE


def test_detector_cannot_judge_without_summary_line(tmp_path):
    # 舊 extractor（Racenet 年代）冇呢行 —— 判唔到就係 unknown，唔准當 clean。
    a = _meeting(tmp_path, "2026-05-01 A Race 1-8", None)
    b = _meeting(tmp_path, "2026-05-02 B Race 1-8", "# B\n\nsomething else\n")
    assert ce.detect_post_race_extraction(a)["status"] == ce.STATUS_UNKNOWN
    assert ce.detect_post_race_extraction(b)["status"] == ce.STATUS_UNKNOWN


def test_scan_flags_unlisted_post_race_meeting(tmp_path):
    listed = _meeting(tmp_path, "2026-08-12 A Race 1-8", _summary(10))
    new = _meeting(tmp_path, "2026-11-01 B Race 1-8", _summary(4))
    clean = _meeting(tmp_path, "2026-11-02 C Race 1-8", _summary(0))
    exclusions = {listed.name: {"reason": ce.REASON_POST_RACE}, "gone": {"reason": "x"}}
    report = ce.scan([listed, new, clean], exclusions)
    assert [r["meeting"] for r in report["unlisted"]] == [new.name]
    assert report["listed_missing"] == ["gone"]
    assert report["counts"] == {ce.STATUS_POST_RACE: 2, ce.STATUS_CLEAN: 1}


# ── 名單本身 ───────────────────────────────────────────────────────────────

def test_repo_exclusion_list_holds_the_decided_meetings():
    exclusions = ce.load_exclusions("au")
    assert DECIDED_2026_10_15 <= set(exclusions)
    for name in DECIDED_2026_10_15:
        assert exclusions[name]["reason"] == ce.REASON_POST_RACE
        assert exclusions[name]["detected_by"] == "EXP-20261015-04"


def test_exclusion_entries_must_carry_reason_and_source(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text(json.dumps({"meetings": [{"meeting": "2026-01-01 A"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        ce.load_exclusions(path=bad)


# ── corpus_paths 套用 ──────────────────────────────────────────────────────

@pytest.fixture
def au_root(tmp_path, monkeypatch):
    root = tmp_path / "AU_Racing"
    _meeting(root, "2026-09-01 Keep Race 1-8", _summary(0))
    _meeting(root / "Archive", "2026-08-12 Leak Race 1-8", _summary(30), races=3)
    _meeting(root / "Archive", "2026-08-13 Keep2 Race 1-8", _summary(0))
    ex = tmp_path / "ex.json"
    ex.write_text(json.dumps({"meetings": [{
        "meeting": "2026-08-12 Leak Race 1-8", "reason": ce.REASON_POST_RACE,
        "detected_by": "TEST"}]}), encoding="utf-8")
    monkeypatch.setitem(ce.EXCLUSIONS_PATH, "au", ex)
    monkeypatch.setattr(cp, "_au_catalog_meetings", lambda root: [])
    return root


def test_meeting_dirs_skips_listed_meeting_even_inside_archive(au_root, capsys):
    names = [p.name for p in cp.meeting_dirs(au_root)]
    assert names == ["2026-09-01 Keep Race 1-8", "2026-08-13 Keep2 Race 1-8"]
    assert cp.last_exclusion_report["excluded"] == ["2026-08-12 Leak Race 1-8"]
    assert cp.last_exclusion_report["reasons"] == {ce.REASON_POST_RACE: 1}
    assert "語料排除 1 個場次" in capsys.readouterr().err


def test_logic_files_skips_listed_meeting(au_root):
    files = cp.logic_files(au_root)
    assert len(files) == 4
    assert not any("Leak" in f for f in files)
    assert len(cp.logic_files(au_root, include_excluded=True)) == 7


def test_include_excluded_returns_everything(au_root):
    assert len(cp.meeting_dirs(au_root, include_excluded=True)) == 3


def test_exclusions_do_not_apply_to_other_platforms(tmp_path, monkeypatch):
    root = tmp_path / "HKJC_Racing"
    _meeting(root, "2026-08-12 Leak Race 1-8", _summary(30))
    monkeypatch.setattr(ce, "load_exclusions",
                        lambda *a, **k: {"2026-08-12 Leak Race 1-8": {"reason": "x"}})
    assert [p.name for p in cp.meeting_dirs(root)] == ["2026-08-12 Leak Race 1-8"]
