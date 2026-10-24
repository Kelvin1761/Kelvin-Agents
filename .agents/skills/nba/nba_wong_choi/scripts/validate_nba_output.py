#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if __name__ == '__main__' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
validate_nba_output.py — NBA Wong Choi Post-Generation Firewall V2

This script MUST be executed on every Game_*_Full_Analysis.md BEFORE it is
accepted as a valid output. It catches the following failure modes:

  FW-01: Placeholder player names ("Player A", "Player B", etc.)
  FW-02: Fake sequential L10 data ([1,2,3,4,5,6,7,8,9,10])
  FW-03: Missing markdown tables (no "|" separated rows)
  FW-04: Repeated sentence padding (same sentence ≥3 times)
  FW-05: Missing SGM/Combo sections
  FW-06: No real player names found (cross-checked with odds JSON)
  FW-07: File too small (<3000 bytes = BLOCK, <5000 = WARN)
  FW-08: Missing odds format (@X.XX not found ≥3 times)
  FW-09: Missing strategy metadata (season_phase, L10_ORDER)
  FW-10: Under recommendations detected
  FW-11: Combo gates (odds floor, negative EV/Edge legs)
  FW-12: Missing engine version markers (MC_MODEL_VERSION, 引擎版本)

Usage:
  python validate_nba_output.py <analysis_file.md> [--odds <Sportsbet_Odds_*.json>]
  python validate_nba_output.py <directory>  # validates all Game_*_Full_Analysis.md

Exit code 0 = all PASS, 1 = any BLOCK/FAIL, 2 = warnings only (no blocks)
"""

import io
import re
import json
import glob
import argparse
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nba_identity import player_name_key

if __name__ == '__main__' and sys.stdout.encoding != 'utf-8' and hasattr(sys.stdout, 'buffer'):
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
    "Half-Kelly",             # Per-combo sizing formula
    "獨立單腿價格乘積",       # Per-combo reference price
    "Sportsbet SGM",           # Disclaimer appears per-combo
    "Sportsbet 顯示為準",     # Disclaimer
    "；真實樣本",             # Per-player provenance line (資料來源：… ；真實樣本 N 場；截止 …).
                               # Opening night every player shares one fallback sample, so it repeats.
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
    # A decimal point is not a sentence end: splitting "命中率 **81.0%**" at the
    # "." turned every 81.x% hit rate into the same "sentence" and blocked
    # whole preseason days (2026-10-11 SAS_PHX, 2026-10-12 CHI_DEN).
    sentences = re.split(r'[。\!\？\?！]|\.(?!\d)|(?<!\d)\.', content)
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
    """Cross-check full player identities; shadow reports must cover actual available history."""
    if not odds_json_path or not os.path.exists(odds_json_path):
        return []
    try:
        with open(odds_json_path, 'r', encoding='utf-8') as f:
            odds_data = json.load(f)
        real_players = {
            name for category in odds_data.get("player_props", {}).values()
            if isinstance(category, dict) for name in category
        }
        if not real_players:
            return ["FW-06 ❌ BLOCK: 冇真實球員盤口，唔可以當完整球員分析。"]
        # Injury/news mentions are not player analysis. Require a rendered card.
        headings = [player_name_key(name) for name in re.findall(r"^#### (.+?) \(#", content, re.MULTILINE)]
        eligible = {player_name_key(name) for name in real_players}
        required = 3
        extractor_path = Path(odds_json_path).with_name(Path(odds_json_path).name.replace('Sportsbet_Odds_', 'nba_game_data_'))
        if extractor_path.is_file():
            data = json.loads(extractor_path.read_text(encoding='utf-8'))
            meta = data.get('meta') or {}
            if meta.get('season_phase') == 'PRESEASON' and meta.get('automation_mode') == 'shadow':
                if 'NO BET — PRESEASON SHADOW ONLY' not in content:
                    return ["FW-06 ❌ BLOCK: preseason 報告缺少強制 shadow NO BET 標示。"]
                available = {
                    player_name_key(p.get('name', ''))
                    for players in data.get('players', {}).values() for p in players
                    if (p.get('gamelog') or {}).get('PTS')
                }
                eligible &= available
                if not eligible:
                    return ["FW-06 ❌ BLOCK: shadow 冇任何可驗證球員歷史，唔可以當完成。"]
                # All available priced players must be analyzed. Missing rookie
                # history is an explicit exclusion, never a fabricated L10.
                required = len(eligible)
        found = len(eligible & set(headings))
        if found < required:
            return [f"FW-06 ❌ BLOCK: 只搵到 {found} 個有盤口嘅真實球員分析 (要求 ≥{required})"]
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"FW-06 ❌ BLOCK: 球員資料無法驗證: {exc}"]


def check_fw07_file_size(content: str, filepath: str) -> list:
    """FW-07: Check minimum file size. <3000 = BLOCK, <5000 = WARN."""
    issues = []
    size = len(content.encode('utf-8'))
    if size < 3000:
        issues.append(
            f"FW-07 ❌ BLOCK: 檔案大小 {size} bytes < 3000 bytes — "
            f"嚴重截斷或缺少內容 ({filepath})"
        )
    elif size < MIN_FILE_SIZE:
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
    allowed_phases = (
        r'OFF_SEASON|PRESEASON|EARLY_REGULAR|REGULAR_SEASON|LATE_REGULAR|POSTSEASON|'
        r'EARLY_SEASON|MID_SEASON|PLAY_IN|PLAYOFFS'
    )
    phase_match = re.search(rf'season_phase\*\*:\s*({allowed_phases})', content)
    if not phase_match:
        phase_match = re.search(rf'season_phase:\s*\*\*({allowed_phases})\*\*', content)
    if not phase_match:
        issues.append(
            "FW-09 ❌ BLOCK: 缺少 season_phase metadata "
            "(OFF_SEASON/PRESEASON/EARLY_REGULAR/REGULAR_SEASON/"
            "LATE_REGULAR/POSTSEASON)"
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
            # Check edge column (index 5)
            edge_cell = cells[5]
            if re.search(r'(^|[^+])-+\d+(?:\.\d+)?%', edge_cell):
                issues.append(f"FW-11 ❌ BLOCK: 組合 Leg 含負 Edge：{line[:160]}")
                break
        # Also check EV% column (index 6) if present
        if len(cells) >= 7:
            ev_cell = cells[6]
            ev_match = re.search(r'(-\d+(?:\.\d+)?)%', ev_cell)
            if ev_match:
                ev_val = float(ev_match.group(1))
                if ev_val < -10:
                    issues.append(f"FW-11 ❌ BLOCK: 組合 Leg EV% 極差 ({ev_val}%)：{line[:160]}")
                    break

    for match in re.finditer(r'\*\*Combo EV%\*\*:\s*([+-]?\d+(?:\.\d+)?)%', content):
        combo_ev = float(match.group(1))
        if combo_ev <= 0:
            issues.append(
                f"FW-11 ❌ BLOCK: 正式組合含非正 Combo EV% ({combo_ev}%) — "
                "negative/zero EV combo 必須 hard block 或改為觀望"
            )
            break

    for match in re.finditer(r'\*\*🎯 Kelly 注碼建議\*\*:\s*(\d+(?:\.\d+)?)% bankroll', content):
        kelly_pct = float(match.group(1))
        if kelly_pct <= 0:
            issues.append(
                "FW-11 ❌ BLOCK: 正式組合 Kelly = 0% — "
                "zero Kelly combo 不可作正式 SGM 推薦"
            )
            break
    return issues


def check_fw12_engine_markers(content: str) -> list:
    """FW-12: Require engine version markers from Python pipeline."""
    issues = []
    if "引擎版本" not in content:
        issues.append(
            "FW-12 ❌ BLOCK: 缺少 '引擎版本' 標記 — 報告可能未經 Python pipeline 生成"
        )
    has_mc = "MC_MODEL_VERSION" in content or "mc_model_version" in content
    has_v_marker = "V8" in content or "V3" in content or "EV Quant" in content
    if not has_mc and not has_v_marker:
        issues.append(
            "FW-12 ⚠️ WARN: 缺少 MC_MODEL_VERSION 或引擎版本標記 — 建議檢查 pipeline 完整性"
        )
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
    all_issues.extend(check_fw12_engine_markers(content))
    all_issues.extend(check_fw13_sgm_quotes(content, filepath, odds_json_path))
    all_issues.extend(check_fw14_availability(content, filepath))

    blocks = [i for i in all_issues if "BLOCK" in i]
    warns = [i for i in all_issues if "WARN" in i]

    return {
        "file": filepath,
        "passed": len(blocks) == 0,
        "blocks": blocks,
        "warnings": warns,
        "total_issues": len(all_issues),
    }


def check_fw13_sgm_quotes(content, filepath, odds_json_path, *, now=None):
    """A formal combo must have a fresh, event/legs-bound quote in its sidecar."""
    import hashlib
    import math
    from nba_sgm_quote import quote_valid
    headings = list(re.finditer(r'^### .*?組合\s+(\d+|X).*?組合賠率\s*@\s*(\d+(?:\.\d+)?)', content, re.MULTILINE))
    if not headings:
        return []
    try:
        sidecar = json.loads(Path(str(filepath) + '.market_legs.json').read_text())
        odds = json.loads(Path(odds_json_path).read_text())
        if sidecar['report_sha256'] != hashlib.sha256(content.encode()).hexdigest():
            raise ValueError('report hash mismatch')
        combos = {str(row['combo_id']): row for row in sidecar['combos']}
        if len(combos) != len(headings):
            raise ValueError('combo count mismatch')
        for index, heading in enumerate(headings):
            key, header_price = heading.groups()
            row = combos[key]
            quote = row['sgm_quote']
            if not quote_valid(quote, odds, row['legs'], now=now):
                raise ValueError('quote missing, expired or binding mismatch')
            price = quote['decimal_odds']
            probability = row['adjusted_joint_prob']
            section = content[heading.end():headings[index+1].start() if index+1 < len(headings) else len(content)]
            table = [line for line in section.splitlines() if line.strip().startswith('| 🧩')]
            if len(table) != len(row['legs']):
                raise ValueError('report/sidecar leg count mismatch')
            for line, leg in zip(table, row['legs']):
                cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
                if cells[1] != leg['desc'] or float(cells[2].lstrip('@')) != leg['price']:
                    raise ValueError('report/sidecar leg mismatch')
            naive = math.prod(leg['p_final'] for leg in row['legs'])
            penalty = row['correlation_penalty']
            if (not math.isclose(float(header_price), price, rel_tol=1e-10)
                    or row['sportsbet_sgm_price'] != price
                    or not math.isfinite(probability) or not 0 < probability < 1
                    or not 0 <= penalty <= .30
                    or not math.isclose(probability, naive * (1-penalty), abs_tol=1e-10)
                    or probability * price <= 1):
                raise ValueError('price/probability/EV mismatch')
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        return [f'FW-13 ❌ BLOCK: SGM quote verification failed ({exc})']
    return []


def check_fw14_availability(content,filepath,*,now=None):
    """Other-domain dashboard rebuilds must honor the same source-data gate."""
    if not re.search(r'^### .*?組合\s+(?:\d+|X).*?組合賠率\s*@',content,re.MULTILINE):
        return []
    from nba_availability import availability_current
    from nba_data_contract import statistics_current
    import hashlib
    try:
        sidecar=json.loads(Path(str(filepath)+'.market_legs.json').read_text())
        packet=sidecar.get('availability') or {}
        meta=packet.get('meta') or {}
        if (sidecar.get('report_sha256')!=hashlib.sha256(content.encode()).hexdigest()
                or not availability_current(packet,now=now)
                or not statistics_current(meta)):
            raise ValueError('stale/unverified availability or statistics source')
        rosters=meta['availability']['rosters']
        for combo in sidecar.get('combos') or []:
            for leg in combo['legs']:
                if player_name_key(leg['player']) not in {player_name_key(name) for name in rosters[leg['team']]}:
                    raise ValueError('recommended player not on verified team roster')
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        return [f'FW-14 ❌ BLOCK: source availability verification failed ({exc})']
    return []


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

    sys.exit(1 if any_blocked else (2 if total_warns > 0 else 0))


if __name__ == "__main__":
    main()
