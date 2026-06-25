"""
Test parsers against current real analysis files.
"""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, '.')

from services.parser_au import parse_au_analysis
from services.parser_hkjc import parse_hkjc_analysis
from services.meeting_detector import discover_meetings, load_meeting_races
import config

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
import sys as _sys; _sys.path.insert(0, str(_PROJECT_ROOT))
from wongchoi_paths import HK_RACING as _HK_RACING


def test_hkjc_auto_parser():
    """Test HKJC parser with full Python Auto analysis output."""
    path = str(config.ANTIGRAVITY_ROOT / "2026-05-13_HappyValley" / "Race_9_Auto_Analysis.md")
    result = parse_hkjc_analysis(path)

    assert result is not None, "Failed to parse HKJC Auto Race 9"
    assert result.analysis_type == "auto", f"analysis_type should be auto, got {result.analysis_type}"
    assert result.top_picks, "Auto top picks table not parsed"

    first_pick = result.top_picks[0]
    print(f"\n✅ HKJC Auto Race 9: {len(result.horses)} horses parsed")
    print(f"   Top pick: No.{first_pick.horse_number} {first_pick.horse_name} ({first_pick.grade})")

    first_horse = result.horses[0]
    assert first_horse.ability_score is not None, "ability_score missing from auto parser"
    assert first_horse.confidence_score is not None, "confidence_score missing from auto parser"
    assert first_horse.risk_score is not None, "risk_score missing from auto parser"
    assert first_horse.trainer, "trainer should be present in current auto parser output"

    print(
        f"   Horse #{first_horse.horse_number} {first_horse.horse_name}: "
        f"trainer={first_horse.trainer}, 戰力={first_horse.ability_score}, "
        f"信心={first_horse.confidence_score}, 風險={first_horse.risk_score}, "
        f"狀態={first_horse.model_pick_status}"
    )

    return True


def test_hkjc_auto_archive_parser():
    """Test HKJC parser against archived Auto output in analysis archive."""
    path = _HK_RACING / "2026-05-03_ShaTin" / "Race_1_Auto_Analysis.md"
    if not path.exists():
        print("⚠️ Archived HKJC auto fixture not found, skipping")
        return True

    result = parse_hkjc_analysis(str(path))
    assert result is not None, "Failed to parse archived HKJC Auto Race 1"
    assert result.analysis_type == "auto"
    assert len(result.horses) >= 8, "Archived HKJC auto fixture parsed too few horses"

    print(f"\n✅ Archived HKJC Auto Race 1: {len(result.horses)} horses parsed")
    return True


def test_hkjc_sha_tin_loader_normalizes_meeting_venue():
    """Dashboard loader should use the meeting folder venue for HKJC races."""
    meetings = discover_meetings(str(config.ANTIGRAVITY_ROOT))
    meeting = next(
        (m for m in meetings if m.region.value == "hkjc" and m.date == "2026-05-31" and m.venue == "ShaTin"),
        None,
    )

    assert meeting is not None, "2026-05-31 ShaTin meeting should be discoverable"

    races_by_analyst = load_meeting_races(meeting)
    kelvin_races = races_by_analyst.get("Kelvin", [])

    assert kelvin_races, "Expected Kelvin races for 2026-05-31 ShaTin"
    assert all(race.venue == "沙田" for race in kelvin_races), "All loaded races should normalize to 沙田"

    return True


def test_au_auto_parser_ballarat():
    """Test AU parser against current Ballarat auto analysis output."""
    path = config.ANTIGRAVITY_ROOT / "2026-05-24 Ballarat Race 1-8" / "Race_1_Auto_Analysis.md"
    result = parse_au_analysis(str(path))

    assert result is not None, "Failed to parse AU Auto Ballarat Race 1"
    assert len(result.horses) == 11, f"Expected 11 horses, got {len(result.horses)}"
    assert result.top_picks, "AU top picks should be present"

    first_horse = result.horses[0]
    assert first_horse.core_analysis, "core_analysis missing from AU auto parser"
    assert first_horse.final_grade, "final_grade missing from AU auto parser"

    print(f"\n✅ AU Auto Ballarat Race 1: {len(result.horses)} horses parsed")
    print(
        f"   Horse #{first_horse.horse_number} {first_horse.horse_name}: "
        f"grade={first_horse.final_grade}, jockey={first_horse.jockey}, "
        f"analysis={'yes' if first_horse.core_analysis else 'no'}"
    )

    return True


def test_au_meeting_loader_ballarat():
    """Test meeting loader returns horse counts for AU meetings used by dashboard."""
    meetings = discover_meetings(str(config.ANTIGRAVITY_ROOT))
    meeting = next(
        (m for m in meetings if m.region.value == "au" and m.date == "2026-05-24" and m.venue == "Ballarat"),
        None,
    )

    assert meeting is not None, "Ballarat meeting should be discoverable"

    races_by_analyst = load_meeting_races(meeting)
    kelvin_races = races_by_analyst.get("Kelvin", [])
    race_1 = next((race for race in kelvin_races if race.race_number == 1), None)

    assert race_1 is not None, "Ballarat Race 1 should load through meeting loader"
    assert len(race_1.horses) == 11, f"Dashboard loader expected 11 horses, got {len(race_1.horses)}"

    print(f"   Dashboard loader Ballarat Race 1 horses: {len(race_1.horses)}")
    return True


def test_au_parser_accepts_mixed_case_bracket_headers(tmp_path):
    """Bracket-style AU files can use mixed-case horse names."""
    sample = textwrap.dedent(
        """
        Race 1 - Example Stakes
        [#1] Tron Bolt (Barrier 6)
        Trainer: Chris Waller
        Jockey: James McDonald
        Weight: 58kg
        Block 3: Core Analysis
        Handles tempo.

        [#2] Silent Impact (Barrier 3)
        Trainer: Ciaron Maher
        Jockey: Ethan Brown
        Weight: 56kg
        Block 3: Core Analysis
        Maps well.

        🏆 Top 4
        1. #1 Tron Bolt
        2. #2 Silent Impact
        """
    ).strip()
    path = tmp_path / "Race_1_Auto_Analysis.md"
    path.write_text(sample, encoding="utf-8")

    result = parse_au_analysis(str(path))

    assert result is not None, "Failed to parse mixed-case AU bracket format"
    assert result.analysis_type == "auto"
    assert len(result.horses) == 2, f"Expected 2 horses, got {len(result.horses)}"
    assert result.horses[0].horse_name == "Tron Bolt"

    return True


def test_meeting_detector():
    """Test meeting discovery."""
    meetings = discover_meetings()
    
    hkjc = [m for m in meetings if m.region.value == 'hkjc']
    
    print(f"\n✅ Meeting Detector: {len(meetings)} total ({len(hkjc)} HKJC)")
    
    for m in meetings[:5]:
        analysts = ', '.join(a.value for a in m.analysts)
        print(f"   {m.date} {m.venue} ({m.region.value}) — analysts: {analysts}")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🏇 Racing Dashboard Parser Tests")
    print("=" * 60)
    
    passed = 0
    total = 7
    
    try:
        if test_meeting_detector():
            passed += 1
    except Exception as e:
        print(f"❌ Meeting detector test failed: {e}")

    try:
        if test_hkjc_auto_parser():
            passed += 1
    except Exception as e:
        print(f"❌ HKJC Auto parser test failed: {e}")

    try:
        if test_hkjc_auto_archive_parser():
            passed += 1
    except Exception as e:
        print(f"❌ Archived HKJC Auto parser test failed: {e}")

    try:
        if test_hkjc_sha_tin_loader_normalizes_meeting_venue():
            passed += 1
    except Exception as e:
        print(f"❌ HKJC Sha Tin venue test failed: {e}")

    try:
        if test_au_auto_parser_ballarat():
            passed += 1
    except Exception as e:
        print(f"❌ AU Auto parser test failed: {e}")

    try:
        if test_au_meeting_loader_ballarat():
            passed += 1
    except Exception as e:
        print(f"❌ AU meeting loader test failed: {e}")

    try:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmpdir:
            if test_au_parser_accepts_mixed_case_bracket_headers(Path(tmpdir)):
                passed += 1
    except Exception as e:
        print(f"❌ AU mixed-case bracket parser test failed: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'=' * 60}")
