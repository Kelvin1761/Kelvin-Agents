#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
validate_nba_output.py — NBA Wong Choi Post-Generation Firewall

This script MUST be executed on every Game_*_Full_Analysis.md BEFORE it is
accepted as a valid output. It catches the following failure modes:

  FW-01: Placeholder player names ("Player A", "Player B", etc.)
  FW-02: Fake sequential L10 data ([1,2,3,4,5,6,7,8,9,10])
  FW-03: Missing markdown tables (no "|" separated rows)
  FW-04: Repeated sentence padding (same sentence ≥3 times)
  FW-05: Missing SGM/Combo sections
  FW-06: No real player names found (cross-checked with odds JSON)
  FW-07: File too small (< 5000 bytes → likely truncated or padded)
  FW-08: Missing odds format (@X.XX not found ≥3 times)

Usage:
  python validate_nba_output.py <analysis_file.md> [--odds <Sportsbet_Odds_*.json>]
  python validate_nba_output.py <directory>  # validates all Game_*_Full_Analysis.md

Exit code 0 = all PASS, 1 = any BLOCK/FAIL
"""

import io
import re
import json
import glob
import argparse
import collections

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ─── Constants ───────────────────────────────────────────────────────────

PLACEHOLDER_NAMES = [
    "Player A", "Player B", "Player C", "Player D", "Player E",
    "Player X", "Player Y", "Player Z",
    "球員 A", "球員 B", "球員 C",
]

# Sequential integers that indicate fake L10 data
FAKE_L10_PATTERNS = [
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    [10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
    [1, 2, 3, 4, 5],
    [5, 4, 3, 2, 1],
]

# Minimum file size in bytes for a valid single-game analysis
MIN_FILE_SIZE = 5000

# Minimum number of markdown table rows (lines containing |)
MIN_TABLE_ROWS = 3

# Minimum occurrences of @X.XX odds format
MIN_ODDS_OCCURRENCES = 3

# Maximum allowed repetitions of any single sentence
MAX_SENTENCE_REPEATS = 3

# Required section markers (at least one must be present)
REQUIRED_SECTIONS = [
    "SGM Parlay",
    "組合結算",
    "組合 1",
    "🛡️",
    "穩膽",
    "Combo",
]

# Whitelist patterns: legitimate structural repetitions in Python-generated skeletons
PADDING_WHITELIST = [
    "Sportsbet SGM",           # Disclaimer appears per-combo
    "Sportsbet 顯示為準",     # Disclaimer
    "Python 選擇此 Leg",      # Per-leg explanation marker
    "Python 自動核心邏輯",    # Per-leg marker
    "📊 組合結算",            # Section header per-combo
    "USG%",                    # Stats table field (repeats per player)
    "Final Adjusted",          # 8-Factor per-leg marker
    "Base Rate",               # Math engine marker
    "數理引擎",               # Template section header
    "邏輯引擎",               # Template section header
    "盤口對照表",             # Template section header
    "賠率相乘",               # Combo calc (repeats per combo)
    "(10/10)",                 # Hit rate display
    "走勢",                    # 8-Factor adjustment line fragments
    "波動",                    # 8-Factor adjustment line fragments
    "安全墊",                  # 8-Factor adjustment line fragments
    "8-Factor",                # Math engine version marker
    "10-Factor",               # Math engine version marker
]


# ─── Validation Functions ────────────────────────────────────────────────

def check_fw01_placeholder_names(content: str) -> list:
    """FW-01: Detect placeholder player names."""
    issues = []
    for name in PLACEHOLDER_NAMES:
        count = content.count(name)
        if count > 0:
            issues.append(f"FW-01 ❌ BLOCK: 發現 placeholder 球員名 '{name}' ({count} 次)")
    return issues


def check_fw02_fake_l10(content: str) -> list:
    """FW-02: Detect fake sequential L10 data arrays."""
    issues = []
    # Find all array-like patterns [x, y, z, ...]
    array_re = re.compile(r'\[(\d+(?:\s*,\s*\d+){3,})\]')
    matches = array_re.findall(content)

    for match in matches:
        try:
            nums = [int(x.strip()) for x in match.split(',')]
            for fake in FAKE_L10_PATTERNS:
                if nums == fake:
                    issues.append(
                        f"FW-02 ❌ BLOCK: 發現假 L10 數據 {nums} — 呢個係連續整數序列，唔係真實比賽數據"
                    )
                    break
            # Also check if it's ANY perfectly sequential pattern
            if len(nums) >= 5:
                diffs = [nums[i+1] - nums[i] for i in range(len(nums)-1)]
                if all(d == diffs[0] for d in diffs) and diffs[0] != 0:
                    if nums not in FAKE_L10_PATTERNS:  # avoid duplicate
                        issues.append(
                            f"FW-02 ❌ BLOCK: 發現等差數列 L10 數據 {nums} (公差={diffs[0]}) — 疑似假數據"
                        )
        except (ValueError, IndexError):
            continue

    return issues


def check_fw03_markdown_tables(content: str) -> list:
    """FW-03: Require markdown tables in the output."""
    issues = []
    table_rows = [line for line in content.split('\n')
                  if '|' in line and line.strip().startswith('|')]
    if len(table_rows) < MIN_TABLE_ROWS:
        issues.append(
            f"FW-03 ❌ BLOCK: 只搵到 {len(table_rows)} 行 markdown table（要求 ≥{MIN_TABLE_ROWS}）"
            "— 正常報告至少有賠率對照表"
        )
    return issues


def check_fw04_padding(content: str) -> list:
    """FW-04: Detect repeated sentence padding (same sentence appearing 4+ times).
    
    Only flags sentences that are:
    - Longer than 30 characters (to avoid matching short structural fragments)
    - Not in the whitelist of legitimate repeating patterns
    """
    issues = []

    # Split content into sentences (Chinese + English)
    sentences = re.split(r'[。\.\!\？\?！]', content)
    # Only consider meaningful sentences (>30 chars to avoid table fragments / short markers)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    # Count occurrences
    counter = collections.Counter(sentences)
    for sentence, count in counter.most_common(10):
        if count >= MAX_SENTENCE_REPEATS + 1:
            # Check whitelist: if the sentence contains any whitelisted pattern, skip it
            is_whitelisted = any(wl in sentence for wl in PADDING_WHITELIST)
            if is_whitelisted:
                continue
            
            preview = sentence[:60] + "..." if len(sentence) > 60 else sentence
            issues.append(
                f"FW-04 ❌ BLOCK: 句子重複 {count} 次 (上限 {MAX_SENTENCE_REPEATS}): "
                f"「{preview}」"
            )

    return issues


def check_fw05_required_sections(content: str) -> list:
    """FW-05: Require key SGM/Combo sections."""
    issues = []
    found_any = False
    for marker in REQUIRED_SECTIONS:
        if marker in content:
            found_any = True
            break

    if not found_any:
        issues.append(
            f"FW-05 ❌ BLOCK: 搵唔到任何 SGM/組合區塊標記 "
            f"(需要至少包含: {', '.join(REQUIRED_SECTIONS[:3])})"
        )
    return issues


def check_fw06_real_players(content: str, odds_json_path: str = None) -> list:
    """FW-06: Verify real player names exist (cross-check with odds JSON if provided)."""
    issues = []

    if odds_json_path and os.path.exists(odds_json_path):
        try:
            with open(odds_json_path, 'r', encoding='utf-8') as f:
                odds_data = json.load(f)

            # Extract all player names from odds JSON
            real_players = set()
            props = odds_data.get("player_props", {})
            for category in props.values():
                if isinstance(category, dict):
                    for player_name in category.keys():
                        real_players.add(player_name)

            if real_players:
                found_players = 0
                for player in real_players:
                    # Check last name match (more tolerant)
                    last_name = player.split()[-1]
                    if last_name in content:
                        found_players += 1

                if found_players < 3:
                    issues.append(
                        f"FW-06 ❌ BLOCK: 只搵到 {found_players} 個真實球員名 "
                        f"(要求 ≥3，odds JSON 有 {len(real_players)} 個球員)"
                    )
        except (json.JSONDecodeError, KeyError):
            pass

    return issues


def check_fw07_file_size(content: str, filepath: str) -> list:
    """FW-07: Check minimum file size."""
    issues = []
    size = len(content.encode('utf-8'))
    if size < MIN_FILE_SIZE:
        issues.append(
            f"FW-07 ⚠️ WARN: 檔案大小 {size} bytes < {MIN_FILE_SIZE} bytes — "
            f"疑似截斷或灌水 ({filepath})"
        )
    return issues


def check_fw08_odds_format(content: str) -> list:
    """FW-08: Require @X.XX odds format occurrences."""
    issues = []
    odds_matches = re.findall(r'@\d+\.\d+', content)
    if len(odds_matches) < MIN_ODDS_OCCURRENCES:
        issues.append(
            f"FW-08 ❌ BLOCK: 只搵到 {len(odds_matches)} 個 @X.XX 賠率格式 "
            f"(要求 ≥{MIN_ODDS_OCCURRENCES}) — 正常報告至少有 3 個組合嘅賠率"
        )
    return issues


def check_fw09_strategy_metadata(content: str) -> list:
    """FW-09: Require current NBA strategy metadata."""
    issues = []
    phase_match = re.search(r'season_phase\*\*:\s*(EARLY_SEASON|MID_SEASON|LATE_REGULAR|PLAY_IN|PLAYOFFS)', content)
    if not phase_match:
        phase_match = re.search(r'season_phase:\s*\*\*(EARLY_SEASON|MID_SEASON|LATE_REGULAR|PLAY_IN|PLAYOFFS)\*\*', content)
    if not phase_match:
        issues.append(
            "FW-09 ❌ BLOCK: 缺少 season_phase metadata "
            "(EARLY_SEASON/MID_SEASON/LATE_REGULAR/PLAY_IN/PLAYOFFS)"
        )
    if "L10_ORDER" not in content or "newest_first" not in content:
        issues.append("FW-09 ❌ BLOCK: 缺少 L10_ORDER:newest_first metadata")
    if "SPORTSBET_MILESTONE_OVER_ONLY" not in content:
        issues.append("FW-09 ❌ BLOCK: 缺少 SPORTSBET_MILESTONE_OVER_ONLY 策略標記")
    return issues


def check_fw10_over_only(content: str) -> list:
    """FW-10: Block Under recommendations in the Sportsbet milestone strategy."""
    issues = []
    banned_patterns = [
        r'\bTotal\s+U\d',
        r'\bUnder\b',
        r'買\s*Under',
        r'推介\s*Under',
    ]
    for pattern in banned_patterns:
        if re.search(pattern, content, flags=re.IGNORECASE):
            issues.append(
                f"FW-10 ❌ BLOCK: 發現 Under/Total U 推介痕跡 ({pattern}) — "
                "NBA v1 只允許 Sportsbet milestone Over X+"
            )
            break
    return issues


def check_fw11_combo_gates(content: str) -> list:
    """FW-11: Enforce positive-EV combo gates in generated sections."""
    issues = []
    floors = {
        "組合 1": 2.0,
        "組合 2": 3.0,
        "組合 3": 8.0,
    }
    for combo_name, floor in floors.items():
        match = re.search(rf'### .*{combo_name}.*?組合賠率 @(\d+(?:\.\d+)?)', content)
        if match and float(match.group(1)) < floor:
            issues.append(
                f"FW-11 ❌ BLOCK: {combo_name} 組合賠率 @{match.group(1)} < {floor}x 門檻"
            )

    leg_rows = [line for line in content.splitlines() if line.strip().startswith("| 🧩")]
    for line in leg_rows:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6:
            edge_cell = cells[5]
            if re.search(r'(^|[^+])-+\d+(?:\.\d+)?%', edge_cell):
                issues.append(f"FW-11 ❌ BLOCK: 組合 Leg 含負 EV：{line[:160]}")
                break
    return issues


# ─── Main Validation Runner ─────────────────────────────────────────────

def validate_file(filepath: str, odds_json_path: str = None) -> dict:
    """Run all validation checks on a single file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    all_issues = []
    all_issues.extend(check_fw01_placeholder_names(content))
    all_issues.extend(check_fw02_fake_l10(content))
    all_issues.extend(check_fw03_markdown_tables(content))
    all_issues.extend(check_fw04_padding(content))
    all_issues.extend(check_fw05_required_sections(content))
    all_issues.extend(check_fw06_real_players(content, odds_json_path))
    all_issues.extend(check_fw07_file_size(content, filepath))
    all_issues.extend(check_fw08_odds_format(content))
    all_issues.extend(check_fw09_strategy_metadata(content))
    all_issues.extend(check_fw10_over_only(content))
    all_issues.extend(check_fw11_combo_gates(content))

    blocks = [i for i in all_issues if "BLOCK" in i]
    warns = [i for i in all_issues if "WARN" in i]

    return {
        "file": filepath,
        "passed": len(blocks) == 0,
        "blocks": blocks,
        "warnings": warns,
        "total_issues": len(all_issues),
    }


def find_odds_json(analysis_path: str) -> str:
    """Try to find corresponding Sportsbet odds JSON for an analysis file."""
    dirname = os.path.dirname(analysis_path)
    basename = os.path.basename(analysis_path)

    # Extract game tag: Game_GSW_LAC_Full_Analysis.md → GSW_LAC
    match = re.search(r'Game_([A-Z]+_[A-Z]+)', basename)
    if match:
        tag = match.group(1)
        odds_path = os.path.join(dirname, f"Sportsbet_Odds_{tag}.json")
        if os.path.exists(odds_path):
            return odds_path
    return None


def print_report(result: dict):
    """Print validation report for a single file."""
    fname = os.path.basename(result["file"])
    status = "✅ PASS" if result["passed"] else "❌ BLOCKED"

    print(f"\n{'=' * 65}")
    print(f"🔒 validate_nba_output.py — {fname}")
    print(f"   Status: {status}")
    print(f"   Issues: {result['total_issues']} "
          f"({len(result['blocks'])} blocks, {len(result['warnings'])} warnings)")

    for issue in result["blocks"]:
        print(f"   {issue}")
    for issue in result["warnings"]:
        print(f"   {issue}")

    print(f"{'=' * 65}")


def main():
    parser = argparse.ArgumentParser(
        description="NBA Wong Choi Post-Generation Firewall — "
                    "validates analysis output before acceptance"
    )
    parser.add_argument("path", help="Analysis .md file or directory")
    parser.add_argument("--odds", default=None,
                        help="Path to Sportsbet_Odds_*.json for cross-validation")
    args = parser.parse_args()

    path = args.path
    files_to_check = []

    if os.path.isfile(path):
        files_to_check = [path]
    elif os.path.isdir(path):
        files_to_check = sorted(glob.glob(os.path.join(path, "Game_*_Full_Analysis.md")))
    else:
        print(f"❌ Path not found: {path}")
        sys.exit(2)

    if not files_to_check:
        print(f"⚠️ No Game_*_Full_Analysis.md files found in {path}")
        sys.exit(2)

    any_blocked = False
    total_blocks = 0
    total_warns = 0

    for fpath in files_to_check:
        # Auto-detect odds JSON if not provided
        odds_path = args.odds or find_odds_json(fpath)
        result = validate_file(fpath, odds_path)
        print_report(result)

        if not result["passed"]:
            any_blocked = True
        total_blocks += len(result["blocks"])
        total_warns += len(result["warnings"])

    print(f"\n{'=' * 65}")
    print(f"📊 FIREWALL SUMMARY: {len(files_to_check)} files checked, "
          f"{total_blocks} blocks, {total_warns} warnings")
    if any_blocked:
        print("🚨 VERDICT: ❌ BLOCKED — 存在不合格報告，禁止進入下游管線！")
    else:
        print("✅ VERDICT: ALL PASS — 所有報告通過防火牆檢查。")
    print(f"{'=' * 65}\n")

    sys.exit(1 if any_blocked else 0)


if __name__ == "__main__":
    main()
