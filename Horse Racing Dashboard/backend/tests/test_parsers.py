"""
Test parsers against real analysis files.
"""
import sys
sys.path.insert(0, '.')

from services.parser_hkjc import parse_hkjc_analysis
from services.parser_au import parse_au_analysis
from services.meeting_detector import discover_meetings, load_meeting_races
import config

def test_kelvin_parser():
    """Test HKJC parser with Kelvin's Race 1 file."""
    path = str(config.ANTIGRAVITY_ROOT / "2026-03-22_ShaTin (Kelvin)" / "2026-03-22_ShaTin_Race_1_Analysis.txt")
    result = parse_hkjc_analysis(path)
    
    assert result is not None, "Failed to parse Kelvin Race 1"
    assert result.race_number == 1, f"Race number should be 1, got {result.race_number}"
    
    print(f"✅ Kelvin Race 1: {len(result.horses)} horses parsed")
    print(f"   Top picks: {len(result.top_picks)} (via CSV block: {bool(result.top_picks)})")
    
    for pick in result.top_picks:
        print(f"   #{pick.rank}: No.{pick.horse_number} {pick.horse_name} ({pick.grade})")
    
    # Check horse details
    for horse in result.horses[:3]:
        print(f"\n   Horse #{horse.horse_number} {horse.horse_name}:")
        print(f"     Jockey: {horse.jockey}, Trainer: {horse.trainer}")
        print(f"     Grade: {horse.final_grade}")
        print(f"     Speed forensics: {'✅' if horse.speed_forensics else '❌'}")
        print(f"     EEM energy: {'✅' if horse.eem_energy else '❌'}")
        print(f"     Forgiveness: {'✅' if horse.forgiveness_file else '❌'}")
        print(f"     Form line: {'✅' if horse.form_line else '❌'}")
        print(f"     Rating matrix: {'✅' if horse.rating_matrix else '❌'}")
        if horse.rating_matrix:
            print(f"     Dimensions: {len(horse.rating_matrix.dimensions)}")
        print(f"     Conclusion: {'✅' if horse.conclusion else '❌'}")
        print(f"     Underhorse: {'✅ triggered' if horse.underhorse_triggered else '❌ not triggered'}")
    
    return True


def test_heison_parser():
    """Test HKJC parser with Heison's Race 10 file."""
    path = str(config.ANTIGRAVITY_ROOT / "2026-03-22_ShaTin" / "Heison_2026-03-22_ShaTin_Race_10_Analysis.txt")
    result = parse_hkjc_analysis(path)
    
    assert result is not None, "Failed to parse Heison Race 10"
    
    print(f"\n✅ Heison Race 10: {len(result.horses)} horses parsed")
    print(f"   Top picks: {len(result.top_picks)} (CSV fallback to verdict)")
    
    for pick in result.top_picks:
        print(f"   #{pick.rank}: No.{pick.horse_number} {pick.horse_name} ({pick.grade})")
    
    for horse in result.horses[:3]:
        print(f"\n   Horse #{horse.horse_number} {horse.horse_name}:")
        print(f"     Grade: {horse.final_grade}")
        print(f"     Speed forensics: {'✅' if horse.speed_forensics else '❌'}")
        print(f"     EEM energy: {'✅' if horse.eem_energy else '❌'}")
        print(f"     Conclusion: {'✅' if horse.conclusion else '❌'}")
    
    return True


def test_au_parser():
    """Test AU parser with Rosehill Race 1 file."""
    path = str(config.ANTIGRAVITY_ROOT / "2026-03-21 Rosehill Gardens Race 1-10" / "Race Analysis" / "03-21 Rosehill Gardens Race 1 Analysis.txt")
    
    # Try alternate location
    from pathlib import Path
    if not Path(path).exists():
        # Search for actual file
        folder = config.ANTIGRAVITY_ROOT / "2026-03-21 Rosehill Gardens Race 1-10"
        candidates = list(folder.glob("**/*Race*1*Analysis.txt"))
        if candidates:
            path = str(candidates[0])
            print(f"   Found AU file at: {path}")
        else:
            print("⚠️ AU test file not found, skipping")
            return True
    
    result = parse_au_analysis(path)
    assert result is not None, "Failed to parse AU Race 1"
    
    print(f"\n✅ AU Rosehill Race 1: {len(result.horses)} horses parsed")
    print(f"   Top picks: {len(result.top_picks)}")
    
    for pick in result.top_picks:
        print(f"   #{pick.rank}: No.{pick.horse_number} {pick.horse_name} ({pick.grade})")
    
    for horse in result.horses[:3]:
        print(f"\n   Horse #{horse.horse_number} {horse.horse_name}:")
        print(f"     Jockey: {horse.jockey}")
        print(f"     Grade: {horse.final_grade}")
        print(f"     Horse profile: {'✅' if horse.horse_profile else '❌'}")
        print(f"     Core analysis: {'✅' if horse.core_analysis else '❌'}")
        print(f"     Conclusion: {'✅' if horse.conclusion else '❌'}")
    
    return True


def test_meeting_detector():
    """Test meeting discovery."""
    meetings = discover_meetings()
    
    hkjc = [m for m in meetings if m.region.value == 'hkjc']
    au = [m for m in meetings if m.region.value == 'au']
    
    print(f"\n✅ Meeting Detector: {len(meetings)} total ({len(hkjc)} HKJC, {len(au)} AU)")
    
    for m in meetings[:5]:
        analysts = ', '.join(a.value for a in m.analysts)
        print(f"   {m.date} {m.venue} ({m.region.value}) — analysts: {analysts}")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🏇 Racing Dashboard Parser Tests")
    print("=" * 60)
    
    passed = 0
    total = 4
    
    try:
        if test_kelvin_parser():
            passed += 1
    except Exception as e:
        print(f"❌ Kelvin test failed: {e}")
    
    try:
        if test_heison_parser():
            passed += 1
    except Exception as e:
        print(f"❌ Heison test failed: {e}")
    
    try:
        if test_au_parser():
            passed += 1
    except Exception as e:
        print(f"❌ AU test failed: {e}")
    
    try:
        if test_meeting_detector():
            passed += 1
    except Exception as e:
        print(f"❌ Meeting detector test failed: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'=' * 60}")
