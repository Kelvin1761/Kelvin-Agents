import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys, io, re, os, pathlib, argparse
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
validator_scope_analyzer.py — 驗證範圍分析器

自動匹配 SIP 範圍標籤同賽事條件，判斷邊場需要全盲測、邊場可以跳過。
消除 Validator Step 1.5 嘅機械性匹配工作。

Usage:
  python validator_scope_analyzer.py <analysis_dir> --sip-changelog <sip_file_or_text>
  python validator_scope_analyzer.py <analysis_dir> --sip-text "SIP-RR15: ... [SCOPE: UNIVERSAL]"

Exit codes:
  0 = Success
  2 = Error
"""

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ── SIP scope tag patterns ──
SCOPE_RE = re.compile(r'\[SCOPE:\s*(\w+)(?::\s*(.+?))?\]', re.IGNORECASE)
SIP_ENTRY_RE = re.compile(r'(SIP-\S+)[：:]\s*(.+?)(?:\n|$)', re.UNICODE)

# ── Race condition extraction ──
RACE_HEADER_RE = re.compile(
    r'(?:Race|第)\s*(\d+)',
    re.IGNORECASE
)
DISTANCE_RE = re.compile(r'(\d{3,4})m\b')
TRACK_RE = re.compile(r'(?:Track|場地|賽場)[：:]\s*(.+?)(?:\s*[|\n]|$)', re.IGNORECASE)
GOING_RE = re.compile(r'(?:Going|掛牌|場地狀態)[：:]\s*(.+?)(?:\s*[|\n]|$)', re.IGNORECASE)


def parse_sip_changelog(text):
    """Parse SIP changelog entries with scope tags."""
    sips = []
    entries = SIP_ENTRY_RE.findall(text)
    
    if not entries:
        # Try line-by-line parsing
        for line in text.strip().split('\n'):
            line = line.strip().lstrip('-').strip()
            m = re.match(r'(SIP-\S+)[：:\s]+(.+)', line)
            if m:
                entries.append((m.group(1), m.group(2)))

    for sip_id, desc in entries:
        scopes = SCOPE_RE.findall(desc)
        if not scopes:
            # Default: if no scope tag, treat as UNIVERSAL
            scopes = [('UNIVERSAL', '')]

        sips.append({
            'id': sip_id,
            'desc': desc.strip(),
            'scopes': [{'type': s[0].upper(), 'value': s[1].strip()} for s in scopes],
        })

    return sips


def extract_race_conditions(analysis_dir):
    """Extract race conditions from analysis files."""
    races = {}
    p = pathlib.Path(analysis_dir)
    files = sorted(p.glob('*Analysis*.md')) or sorted(p.glob('*analysis*.md'))
    
    # Also check skeleton/racecard files
    rc_files = sorted(p.glob('*Skeleton*.md')) + sorted(p.glob('*Racecard*.md')) + sorted(p.glob('*排位表*.md'))
    
    all_files = list(files) + list(rc_files)
    
    for af in all_files:
        m = re.search(r'[Rr]ace[_\s]*(\d+)', af.name)
        if not m: continue
        rn = int(m.group(1))
        if rn in races: continue  # Already extracted
        
        with open(af, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Extract distance
        dist_m = DISTANCE_RE.search(text)
        distance = int(dist_m.group(1)) if dist_m else None
        
        # Extract track/venue
        track_m = TRACK_RE.search(text)
        track = track_m.group(1).strip() if track_m else None
        
        # Extract going/condition
        going_m = GOING_RE.search(text)
        going = going_m.group(1).strip() if going_m else None
        
        # Try to detect race type from content
        is_straight = bool(re.search(r'(?:直線|Straight|直路賽)', text, re.IGNORECASE))
        
        races[rn] = {
            'distance': distance,
            'track': track,
            'going': going,
            'is_straight': is_straight,
        }
    
    return races


def match_scope(sip_scope, race_conditions):
    """Check if a SIP scope matches race conditions."""
    scope_type = sip_scope['type']
    scope_value = sip_scope['value']
    
    if scope_type == 'UNIVERSAL':
        return True, '影響所有場次'
    
    if scope_type == 'DISTANCE':
        if not race_conditions.get('distance'):
            return False, '未能取得距離數據'
        # Parse distance range (e.g., "1200-1400" or "1200")
        range_m = re.match(r'(\d+)(?:\s*-\s*(\d+))?', scope_value)
        if range_m:
            low = int(range_m.group(1))
            high = int(range_m.group(2)) if range_m.group(2) else low
            d = race_conditions['distance']
            if low <= d <= high:
                return True, f'距離 {d}m 在 SIP 範圍 {low}-{high}m 內'
            else:
                return False, f'距離 {d}m 不在 SIP 範圍 {low}-{high}m 內'
    
    if scope_type == 'TRACK':
        if not race_conditions.get('track'):
            return True, '未能確定場地，保守列入'
        if scope_value.lower() in race_conditions['track'].lower():
            return True, f'場地匹配: {race_conditions["track"]}'
        else:
            return False, f'場地不匹配: {race_conditions["track"]} ≠ {scope_value}'
    
    if scope_type == 'CONDITION':
        if not race_conditions.get('going'):
            return True, '未能確定掛牌，保守列入'
        if scope_value.lower() in race_conditions['going'].lower():
            return True, f'掛牌匹配: {race_conditions["going"]}'
        else:
            return False, f'掛牌不匹配: {race_conditions["going"]} ≠ {scope_value}'
    
    if scope_type == 'STRAIGHT':
        if race_conditions.get('is_straight'):
            return True, '本場為直線衝刺賽'
        else:
            return False, '本場非直線衝刺賽'
    
    # Unknown scope type — be conservative, include
    return True, f'未知 scope 類型 {scope_type}，保守列入'


def analyze_scope(sips, races):
    """Determine which races need full blind test."""
    full_test = {}   # race_num -> [reasons]
    skip = {}        # race_num -> [reasons]
    
    for rn, conditions in sorted(races.items()):
        reasons_in = []
        reasons_out = []
        
        for sip in sips:
            for scope in sip['scopes']:
                matched, reason = match_scope(scope, conditions)
                if matched:
                    reasons_in.append(f"{sip['id']}: {reason}")
                else:
                    reasons_out.append(f"{sip['id']}: {reason}")
        
        if reasons_in:
            full_test[rn] = reasons_in
        else:
            skip[rn] = reasons_out if reasons_out else ['所有 SIP 均不涉及本場條件']
    
    return full_test, skip


def main():
    parser = argparse.ArgumentParser(description='驗證範圍分析器')
    parser.add_argument('analysis_dir', help='Directory containing analysis/racecard files')
    parser.add_argument('--sip-changelog', help='Path to SIP changelog file')
    parser.add_argument('--sip-text', help='SIP changelog as inline text')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()

    if not os.path.isdir(args.analysis_dir):
        print(f'Error: {args.analysis_dir} not found', file=sys.stderr)
        sys.exit(2)

    # Get SIP changelog
    if args.sip_changelog:
        with open(args.sip_changelog, 'r', encoding='utf-8') as f:
            sip_text = f.read()
    elif args.sip_text:
        sip_text = args.sip_text
    else:
        print('Error: --sip-changelog or --sip-text required', file=sys.stderr)
        sys.exit(2)

    sips = parse_sip_changelog(sip_text)
    if not sips:
        print('Warning: No SIP entries found. All races will be marked for full test.', file=sys.stderr)
        sips = [{'id': 'DEFAULT', 'desc': 'No SIP found', 'scopes': [{'type': 'UNIVERSAL', 'value': ''}]}]

    races = extract_race_conditions(args.analysis_dir)
    if not races:
        print('Error: No race data found in analysis directory', file=sys.stderr)
        sys.exit(2)

    full_test, skip = analyze_scope(sips, races)

    if args.json:
        import json
        print(json.dumps({'full_test': full_test, 'skip': skip}, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'═' * 55}")
        print(f"🔬 SIP 驗證範圍分析")
        print(f"   SIP 數量: {len(sips)} | 場次: {len(races)}")
        print(f"{'═' * 55}")
        
        print(f"\n📋 全盲測場次（完整 Step 2-5）: {len(full_test)} 場")
        for rn in sorted(full_test.keys()):
            print(f"   Race {rn}:")
            for r in full_test[rn]:
                print(f"      → {r}")
        
        print(f"\n⏭️  跳過場次（SIP 無關聯）: {len(skip)} 場")
        for rn in sorted(skip.keys()):
            print(f"   Race {rn}:")
            for r in skip[rn]:
                print(f"      → {r}")
        
        print(f"\n{'═' * 55}")

    sys.exit(0)


if __name__ == '__main__':
    main()
