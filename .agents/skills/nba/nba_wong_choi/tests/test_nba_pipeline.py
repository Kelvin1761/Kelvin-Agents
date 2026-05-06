#!/usr/bin/env python3
"""
test_nba_pipeline.py — NBA Wong Choi Integration Test Suite

Tests the full pipeline components against fixture data:
  1. JSON Schema validation (extractor + sportsbet)
  2. Season phase detection
  3. Math engine (EV, Monte Carlo)
  4. Validator firewall

Usage:
  python test_nba_pipeline.py              # Run all tests
  python test_nba_pipeline.py --verbose    # Verbose output

Exit code 0 = all pass, 1 = any fail
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Path Setup ──────────────────────────────────────────────────────────
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(TEST_DIR, "fixtures")
SCRIPTS_DIR = os.path.join(TEST_DIR, "..", "scripts")
RESOURCES_DIR = os.path.join(TEST_DIR, "..", "resources")

sys.path.insert(0, SCRIPTS_DIR)

# ─── Test Framework ─────────────────────────────────────────────────────
PASS = 0
FAIL = 0
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        if VERBOSE:
            print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")
        if detail:
            print(f"     → {detail}")


def section(name):
    print(f"\n{'─'*50}")
    print(f"📋 {name}")
    print(f"{'─'*50}")


# ─── Test 1: Schema Validation ──────────────────────────────────────────

def test_schema_validation():
    section("Schema Validation")
    
    from validate_json_schema import load_and_validate
    
    # 1a: Valid extractor JSON should pass
    result = load_and_validate(
        os.path.join(FIXTURES_DIR, "valid_game.json"),
        "extractor_schema.json"
    )
    test("valid_game.json passes extractor schema", result["passed"],
         f"Errors: {result['errors'][:3]}")
    
    # 1b: Valid sportsbet JSON should pass
    result = load_and_validate(
        os.path.join(FIXTURES_DIR, "valid_sportsbet.json"),
        "sportsbet_schema.json"
    )
    test("valid_sportsbet.json passes sportsbet schema", result["passed"],
         f"Errors: {result['errors'][:3]}")
    
    # 1c: Playoff fixture should pass
    result = load_and_validate(
        os.path.join(FIXTURES_DIR, "playoff_game.json"),
        "extractor_schema.json"
    )
    test("playoff_game.json passes extractor schema", result["passed"],
         f"Errors: {result['errors'][:3]}")
    
    # 1d: Missing L10 should have warnings but still pass (gamelog is nullable)
    result = load_and_validate(
        os.path.join(FIXTURES_DIR, "missing_l10.json"),
        "extractor_schema.json"
    )
    test("missing_l10.json validates (nullable gamelog)", result["passed"],
         f"Errors: {result['errors'][:3]}")
    
    # 1e: Non-existent file should fail
    result = load_and_validate(
        os.path.join(FIXTURES_DIR, "nonexistent.json"),
        "extractor_schema.json"
    )
    test("nonexistent.json fails validation", not result["passed"])
    
    # 1f: Invalid JSON content
    import tempfile
    bad_json = os.path.join(TEST_DIR, "_test_bad.json")
    with open(bad_json, 'w') as f:
        f.write("{invalid json content")
    result = load_and_validate(bad_json, "extractor_schema.json")
    test("malformed JSON fails validation", not result["passed"])
    os.remove(bad_json)


# ─── Test 2: Season Phase Detection ─────────────────────────────────────

def test_season_phase():
    section("Season Phase Detection (Config-Driven)")
    
    from generate_nba_reports import detect_season_phase
    
    cases = [
        ("2025-10-25", None, "EARLY_SEASON"),
        ("2025-11-10", None, "EARLY_SEASON"),
        ("2025-11-16", None, "MID_SEASON"),
        ("2025-12-25", None, "MID_SEASON"),
        ("2026-01-15", None, "MID_SEASON"),
        ("2026-03-25", None, "LATE_REGULAR"),
        ("2026-04-10", None, "LATE_REGULAR"),
        ("2026-04-15", None, "PLAY_IN"),
        ("2026-04-20", None, "PLAYOFFS"),
        ("2026-05-15", None, "PLAYOFFS"),
        ("2026-06-10", None, "PLAYOFFS"),
    ]
    
    for date_str, meta, expected in cases:
        result = detect_season_phase(date_str, meta)
        test(f"{date_str} → {expected}", result == expected,
             f"got {result}")
    
    # Test metadata override
    meta_playoff = {"season_phase": "PLAYOFFS"}
    result = detect_season_phase("2025-12-25", meta_playoff)
    test("metadata override: PLAYOFFS", result == "PLAYOFFS")
    
    meta_text = {"season_type": "Playoff Game"}
    result = detect_season_phase("2026-01-01", meta_text)
    test("metadata text detection: PLAYOFFS", result == "PLAYOFFS")


# ─── Test 3: Math Engine ────────────────────────────────────────────────

def test_math_engine():
    section("Math Engine (EV + Stats)")
    
    from nba_math_engine import ev_decimal, compute_stats, grade_cov, compute_hit_rate
    
    # EV decimal: p=0.70, odds=1.60 → EV = 0.70*1.60-1 = 0.12
    result = ev_decimal(70, 1.60)
    test("ev_decimal(70, 1.60) ≈ 12.0%", abs(result - 12.0) < 0.1,
         f"got {result}")
    
    # EV decimal: p=0.50, odds=2.00 → EV = 0 (fair bet)
    result = ev_decimal(50, 2.00)
    test("ev_decimal(50, 2.00) ≈ 0%", abs(result) < 0.1,
         f"got {result}")
    
    # EV decimal: p=0.30, odds=2.00 → EV = -40% (bad bet)
    result = ev_decimal(30, 2.00)
    test("ev_decimal(30, 2.00) < 0 (negative EV)", result < 0,
         f"got {result}")
    
    # compute_stats: basic statistical validation
    avg, med, sd, cov = compute_stats([28, 31, 25, 33, 29, 27, 30, 26, 34, 28])
    test("compute_stats avg ≈ 29.1", abs(avg - 29.1) < 0.1,
         f"got avg={avg}")
    test("compute_stats sd > 0", sd > 0, f"got sd={sd}")
    test("compute_stats cov > 0", cov > 0, f"got cov={cov}")
    
    # grade_cov
    test("grade_cov(0.10) = 穩定機器", "穩定" in grade_cov(0.10))
    test("grade_cov(0.40) = 神經刀", "神經刀" in grade_cov(0.40))
    
    # compute_hit_rate: Sportsbet >=
    pct, count, misses = compute_hit_rate([28, 31, 25, 33, 29], 28.0, True)
    test("hit_rate([28,31,25,33,29], 28) ≥ 60%",
         pct >= 60.0, f"got {pct}% ({count})")


# ─── Test 4: Monte Carlo ────────────────────────────────────────────────

def test_monte_carlo():
    section("Monte Carlo V2 (Seed Reproducibility)")
    
    from monte_carlo_nba import monte_carlo_player_prop, confidence_multiplier
    
    # Same seed should produce same result
    r1 = monte_carlo_player_prop(
        avg=25.0, sd=5.0, line=24.0, n=1000,
        category="PTS", seed=42
    )
    r2 = monte_carlo_player_prop(
        avg=25.0, sd=5.0, line=24.0, n=1000,
        category="PTS", seed=42
    )
    test("seed reproducibility (same seed → same result)",
         r1["mc_prob"] == r2["mc_prob"],
         f"r1={r1['mc_prob']}, r2={r2['mc_prob']}")
    
    # Different seed should (very likely) produce different result
    r3 = monte_carlo_player_prop(
        avg=25.0, sd=5.0, line=24.0, n=1000,
        category="PTS", seed=99
    )
    test("different seed → different result",
         r1["mc_prob"] != r3["mc_prob"],
         f"seed42={r1['mc_prob']}, seed99={r3['mc_prob']}")
    
    # Prob should be roughly 50-65% for line slightly below avg
    test("PTS avg=25 line=24 → prob ~35-75%",
         35 <= r1["mc_prob"] <= 75,
         f"mc_prob={r1['mc_prob']}")
    
    # 3PM should use beta-binomial (discrete)
    r_3pm = monte_carlo_player_prop(
        avg=3.0, sd=1.5, line=2.0, n=1000,
        category="3PM", seed=42
    )
    test("3PM uses beta-binomial model",
         0 <= r_3pm["mc_prob"] <= 90,
         f"mc_prob={r_3pm['mc_prob']}")
    
    # confidence_multiplier: low CoV → 1.0, high → penalized
    test("confidence_multiplier(0.10) = 1.0",
         confidence_multiplier(0.10) == 1.0)
    test("confidence_multiplier(0.40) < 1.0",
         confidence_multiplier(0.40) < 1.0,
         f"got {confidence_multiplier(0.40)}")


# ─── Test 5: Fixture Data Integrity ─────────────────────────────────────

def test_fixture_integrity():
    section("Fixture Data Integrity")
    
    # Load valid_game fixture
    with open(os.path.join(FIXTURES_DIR, "valid_game.json"), 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    test("valid_game has meta.game", "game" in data.get("meta", {}))
    test("valid_game has meta.season_phase", "season_phase" in data.get("meta", {}))
    test("valid_game has 2 teams in players", len(data.get("players", {})) == 2)
    
    # Check L10 data integrity
    for team, players in data.get("players", {}).items():
        for p in players:
            gl = p.get("gamelog", {})
            if gl and gl.get("PTS"):
                pts = gl["PTS"]
                test(f"{p['name']} has 10 PTS values", len(pts) == 10,
                     f"got {len(pts)}")
                test(f"{p['name']} PTS values are realistic",
                     all(0 <= v <= 80 for v in pts),
                     f"values: {pts}")
                # Check no sequential fake data
                diffs = [pts[i+1] - pts[i] for i in range(len(pts)-1)]
                is_sequential = all(d == diffs[0] for d in diffs) and diffs[0] != 0
                test(f"{p['name']} PTS not sequential", not is_sequential)
    
    # Load playoff fixture
    with open(os.path.join(FIXTURES_DIR, "playoff_game.json"), 'r', encoding='utf-8') as f:
        playoff = json.load(f)
    
    test("playoff_game season_phase is PLAYOFFS",
         playoff["meta"]["season_phase"] == "PLAYOFFS")
    
    # Tatum should have playoff games in L10
    tatum = playoff["players"]["BOS"][0]
    test("Tatum has playoff_games_in_l10",
         tatum["gamelog"].get("playoff_games_in_l10", 0) > 0)


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("🏀 NBA Wong Choi Pipeline — Integration Test Suite")
    print("=" * 60)
    
    test_schema_validation()
    test_season_phase()
    test_math_engine()
    test_monte_carlo()
    test_fixture_integrity()
    
    print(f"\n{'='*60}")
    print(f"📊 RESULTS: {PASS} passed, {FAIL} failed ({PASS+FAIL} total)")
    
    if FAIL == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {FAIL} TESTS FAILED")
    print(f"{'='*60}\n")
    
    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()
