"""
Test parsers against current real analysis files.
"""
import sys
from pathlib import Path

sys.path.insert(0, '.')

from services.parser_hkjc import parse_hkjc_analysis
from services.meeting_detector import discover_meetings
import config


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
    path = config.ANTIGRAVITY_ROOT / "Archive_Race_Analysis" / "2026-05-03_ShaTin" / "Race_1_Auto_Analysis.md"
    if not path.exists():
        print("⚠️ Archived HKJC auto fixture not found, skipping")
        return True

    result = parse_hkjc_analysis(str(path))
    assert result is not None, "Failed to parse archived HKJC Auto Race 1"
    assert result.analysis_type == "auto"
    assert len(result.horses) >= 8, "Archived HKJC auto fixture parsed too few horses"

    print(f"\n✅ Archived HKJC Auto Race 1: {len(result.horses)} horses parsed")
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
    total = 3
    
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
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'=' * 60}")
