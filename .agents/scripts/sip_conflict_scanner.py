import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
sip_conflict_scanner.py — SIP 衝突掃描器

掃描所有 resource 檔案中嘅 SIP 規則，構建規則關係圖，
偵測以下衝突類型：
  1. 方向衝突：兩條 SIP 對同一維度有相反效果（加分 vs 減分）
  2. 覆蓋衝突：兩條 SIP 嘅觸發條件高度重疊但行為唔同
  3. 重複計算：同一因素被多條 SIP 重複加分/減分
  4. 死鎖風險：SIP-A 嘅豁免條件依賴 SIP-B，而 SIP-B 又依賴 SIP-A

Usage:
  python sip_conflict_scanner.py --domain au --resources-dir <path>
  python sip_conflict_scanner.py --domain hkjc --resources-dir <path>
  python sip_conflict_scanner.py --domain au --resources-dir <path> --sip-index <sip_index.md>

Exit codes:
  0 = No conflicts found
  1 = Conflicts found (review needed)
  2 = Error
"""
import sys, io, re, os, pathlib, argparse, json
from collections import defaultdict
from itertools import combinations

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ── SIP metadata extraction ──

SIP_ID_RE = re.compile(r'(SIP-[A-Za-z0-9\-]+)', re.UNICODE)

# Effect keywords — positive vs negative
POSITIVE_KEYWORDS = [
    '加成', '升級', '升半級', '升一級', '+0.5', '+1.0', '+0.25',
    '保底', '豁免', '豁免', '取消懲罰', '減半', '折扣取消',
    '保護', '專家', '加分', 'upgrade', 'bonus', 'exempt',
    '✅', '強制✅',
]

NEGATIVE_KEYWORDS = [
    '降級', '降半級', '降一級', '-0.5', '-1.0', '-1.5', '-0.25',
    '懲罰', '封頂', '處罰', '限制', '禁止', '扣分',
    '風險', '陷阱', '否決', 'downgrade', 'penalty', 'cap',
    '❌', '強制❌',
]

# Dimension keywords — what aspect does a SIP affect?
DIMENSION_KEYWORDS = {
    '場地': ['場地', '掛牌', 'soft', 'heavy', 'good', '濕地', '膠沙', 'wet', 'track condition'],
    '檔位': ['檔位', '外檔', '內檔', 'barrier', 'draw', '死檔', '外移欄'],
    'EEM': ['eem', '能量', '外疊', '消耗', '步速', 'pace', '前領', '後追', 'closer', 'leader'],
    '負重': ['負重', '磅', '輕磅', '重磅', 'weight', 'kg', '減磅'],
    '騎師': ['騎師', 'jockey', 'tier', '見習', 'apprentice'],
    '練馬師': ['練馬師', 'trainer', '馬房', '品牌', '溢價'],
    '血統': ['血統', 'sire', '種馬', '血統線'],
    '級數': ['級數', '班次', '降班', '升班', 'class', 'rating', '超班', '卡士'],
    '距離': ['距離', 'distance', '短途', '中途', '長途', '1000m', '1200m', '1400m', '1600m'],
    '評級': ['評級', 'grade', '封頂', '保底', 'cap', 'floor', '聚合', 'aggregation'],
    '連勝': ['連勝', '動力', 'momentum', 'streak'],
    '進口': ['進口', 'import', 'nz', '遠征'],
}


def classify_effect(text):
    """Classify whether a SIP rule has positive, negative, or mixed effect."""
    text_lower = text.lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in text_lower)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in text_lower)
    if pos > 0 and neg > 0:
        return 'MIXED'
    elif pos > 0:
        return 'POSITIVE'
    elif neg > 0:
        return 'NEGATIVE'
    return 'NEUTRAL'


def classify_dimensions(text):
    """Identify which dimensions a SIP affects."""
    text_lower = text.lower()
    dims = []
    for dim, keywords in DIMENSION_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            dims.append(dim)
    return dims


def extract_step(text):
    """Extract the Step reference from SIP description."""
    m = re.search(r'Step\s+(\d+[a-zA-Z.]*)', text, re.IGNORECASE)
    return m.group(1) if m else None


def extract_conditions(text):
    """Extract trigger conditions from SIP description."""
    conditions = set()
    # Look for specific condition patterns
    for pattern in [
        r'(Soft\s*\d+\+?)', r'(Good\s*\d*)', r'(Heavy\s*\d*)',
        r'(≥\d+匹)', r'(≤\d+kg)', r'(≥\d+kg)',
        r'(Tier\s*\d)', r'(T\d\s*騎師)', r'(T\d\s*練馬師)',
        r'(Barrier\s*[\d\-]+)', r'(檔≥\d+)', r'(檔≤\d+)',
        r'(≤\d+m)', r'(≥\d+m)', r'(\d{3,4}m)',
        r'(前領)', r'(後追)', r'(外疊)',
        r'(WR[≥≤]\d+%)', r'(PR[≥≤]\d+%)', r'(SP[≥≤]\$\d+)',
    ]:
        for m in re.finditer(pattern, text, re.UNICODE):
            conditions.add(m.group(1))
    return conditions


def classify_status(text):
    """Classify SIP lifecycle status from index text."""
    upper = text.upper()
    if 'DEPRECATED' in upper or '已廢棄' in text or '不得執行' in text:
        return 'DEPRECATED', True
    if 'BAKED' in upper or '✅ BAKED' in text:
        return 'BAKED', True
    if 'COMPLETE' in upper or '✅ COMPLETE' in text:
        return 'COMPLETE', True
    if 'OBSERVATION' in upper or '🟡 OBS' in text or re.search(r'\bOBS[-_]', text):
        return 'OBSERVATION', True
    if 'ACTIVE' in upper or '🟢 ACTIVE' in text:
        return 'ACTIVE', True
    return 'ACTIVE', False


def merge_status(previous, new_status, explicit):
    """Explicit lifecycle decisions win over inferred ACTIVE table rows."""
    if previous is None:
        return new_status
    if not explicit and previous.get('explicit_status'):
        return previous['status']
    if explicit:
        return new_status
    return previous['status']


def parse_sip_index(path):
    """Parse the SIP index file to extract all SIP definitions."""
    sips = {}
    if not os.path.exists(path):
        return sips

    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Parse table rows
    for line in text.split('\n'):
        if '|' not in line:
            continue
        cols = [c.strip() for c in line.split('|')]
        if len(cols) < 5:
            continue

        # Try to find SIP ID in first meaningful column
        sip_match = SIP_ID_RE.search(cols[1] if len(cols) > 1 else '')
        if not sip_match:
            continue

        sip_id = sip_match.group(1)
        # Combine all columns for description
        desc = ' '.join(cols[1:])

        status, explicit_status = classify_status(desc)

        if sip_id in sips:
            previous = sips[sip_id]
            status = merge_status(previous, status, explicit_status)
            explicit_status = previous.get('explicit_status', False) or explicit_status

        sips[sip_id] = {
            'id': sip_id,
            'description': desc,
            'effect': classify_effect(desc),
            'dimensions': classify_dimensions(desc),
            'step': extract_step(desc),
            'conditions': extract_conditions(desc),
            'status': status,
            'explicit_status': explicit_status,
        }

    return sips


def parse_resource_files(resources_dir):
    """Parse all resource files to find inline SIP rules."""
    sip_contexts = defaultdict(list)
    p = pathlib.Path(resources_dir)

    for f in p.glob('*.md'):
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()

        # Find all SIP references with surrounding context
        for m in re.finditer(r'(SIP-[A-Za-z0-9\-]+)', text):
            sip_id = m.group(1)
            # Get surrounding context (100 chars before and after)
            start = max(0, m.start() - 150)
            end = min(len(text), m.end() + 150)
            context = text[start:end]
            sip_contexts[sip_id].append({
                'file': f.name,
                'context': context.replace('\n', ' ').strip(),
            })

    return sip_contexts


def _pair_key(a, b):
    return tuple(sorted([a, b]))


def _expand_resolution_pairs(items):
    pairs = set()
    for item in items:
        if 'pair' in item:
            pairs.add(_pair_key(*item['pair']))
        elif 'sips' in item:
            for a, b in combinations(item['sips'], 2):
                pairs.add(_pair_key(a, b))
    return pairs


def load_conflict_resolutions(resources_dir):
    """Load audited conflict suppressions from resources."""
    path = pathlib.Path(resources_dir) / 'sip_conflict_resolutions.json'
    empty = {'direction': set(), 'duplicate': set()}
    if not path.exists():
        return empty

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {
        'direction': _expand_resolution_pairs(data.get('resolved_direction_conflicts', [])),
        'duplicate': _expand_resolution_pairs(data.get('resolved_duplicate_counting', [])),
    }


def filter_resolved_issues(issues, resolved_pairs):
    active = []
    suppressed = []
    for issue in issues:
        key = _pair_key(issue['sip_a'], issue['sip_b'])
        if key in resolved_pairs:
            suppressed.append(issue)
        else:
            active.append(issue)
    return active, suppressed


def detect_direction_conflicts(sips):
    """Detect SIPs that affect the same dimension in opposite directions."""
    conflicts = []
    sip_list = list(sips.values())

    for i, a in enumerate(sip_list):
        for b in sip_list[i+1:]:
            if a.get('status') != 'ACTIVE' or b.get('status') != 'ACTIVE':
                continue

            # Same dimensions?
            shared_dims = set(a['dimensions']) & set(b['dimensions'])
            if not shared_dims:
                continue

            # Opposite effects?
            if (a['effect'] == 'POSITIVE' and b['effect'] == 'NEGATIVE') or \
               (a['effect'] == 'NEGATIVE' and b['effect'] == 'POSITIVE'):
                # Check condition overlap
                cond_overlap = a['conditions'] & b['conditions']
                if cond_overlap:
                    conflicts.append({
                        'type': '🔴 方向衝突 (Direction Conflict)',
                        'sip_a': a['id'],
                        'sip_b': b['id'],
                        'shared_dims': list(shared_dims),
                        'effect_a': a['effect'],
                        'effect_b': b['effect'],
                        'overlap_conditions': list(cond_overlap),
                        'severity': 'HIGH',
                    })
                elif shared_dims:
                    conflicts.append({
                        'type': '🟡 潛在方向衝突 (Potential Direction Conflict)',
                        'sip_a': a['id'],
                        'sip_b': b['id'],
                        'shared_dims': list(shared_dims),
                        'effect_a': a['effect'],
                        'effect_b': b['effect'],
                        'overlap_conditions': [],
                        'severity': 'MEDIUM',
                    })

    return conflicts


def detect_duplicate_counting(sips):
    """Detect SIPs that may cause double-counting on the same factor."""
    duplicates = []
    sip_list = list(sips.values())

    for i, a in enumerate(sip_list):
        for b in sip_list[i+1:]:
            if a.get('status') != 'ACTIVE' or b.get('status') != 'ACTIVE':
                continue

            # Same step AND same dimension AND same effect direction
            if a['step'] and b['step'] and a['step'] == b['step']:
                shared_dims = set(a['dimensions']) & set(b['dimensions'])
                if shared_dims and a['effect'] == b['effect'] and a['effect'] != 'NEUTRAL':
                    duplicates.append({
                        'type': '🟠 重複計算風險 (Double-Counting Risk)',
                        'sip_a': a['id'],
                        'sip_b': b['id'],
                        'shared_step': a['step'],
                        'shared_dims': list(shared_dims),
                        'effect': a['effect'],
                        'severity': 'MEDIUM',
                    })

    return duplicates


def detect_cross_references(sips, contexts):
    """Detect SIPs that reference each other (potential deadlock)."""
    cross_refs = []
    for sip_id, ctxs in contexts.items():
        if sip_id not in sips:
            continue
        if sips[sip_id].get('status') != 'ACTIVE':
            continue
        for ctx in ctxs:
            # Find other SIP references in context
            other_sips = SIP_ID_RE.findall(ctx['context'])
            for other in other_sips:
                if other != sip_id and other in sips and sips[other].get('status') == 'ACTIVE':
                    # Check if the other SIP also references this one
                    if sip_id in [SIP_ID_RE.search(c['context']).group(1)
                                  for c in contexts.get(other, [])
                                  if SIP_ID_RE.search(c['context'])]:
                        cross_refs.append({
                            'type': '🔵 交叉引用 (Cross-Reference)',
                            'sip_a': sip_id,
                            'sip_b': other,
                            'severity': 'LOW',
                        })

    # Deduplicate
    seen = set()
    unique = []
    for cr in cross_refs:
        key = tuple(sorted([cr['sip_a'], cr['sip_b']]))
        if key not in seen:
            seen.add(key)
            unique.append(cr)

    return unique


def detect_deprecated_references(sips, contexts):
    """Detect references to deprecated SIPs in active resource files."""
    issues = []
    deprecated = {s['id'] for s in sips.values() if s.get('status') == 'DEPRECATED'}

    for sip_id in deprecated:
        if sip_id in contexts:
            for ctx in contexts[sip_id]:
                if ctx['file'] in {'00_sip_index.md', 'sip_changelog.md'}:
                    continue
                if 'DEPRECATED' in ctx['context'] or '已廢棄' in ctx['context']:
                    continue
                issues.append({
                    'type': '⚠️ 過時引用 (Deprecated Reference)',
                    'sip': sip_id,
                    'file': ctx['file'],
                    'severity': 'MEDIUM',
                })

    return issues


def main():
    parser = argparse.ArgumentParser(description='SIP 衝突掃描器')
    parser.add_argument('--domain', required=True, choices=['au', 'hkjc'])
    parser.add_argument('--resources-dir', required=True,
                        help='Path to analyst resources directory')
    parser.add_argument('--sip-index', help='Path to SIP index file (auto-detected if not specified)')
    parser.add_argument('--json', action='store_true', help='Output JSON format')
    args = parser.parse_args()

    if not os.path.isdir(args.resources_dir):
        print(f'Error: {args.resources_dir} not found', file=sys.stderr)
        sys.exit(2)

    # Auto-detect SIP index
    sip_index_path = args.sip_index or os.path.join(args.resources_dir, '00_sip_index.md')
    if not os.path.exists(sip_index_path):
        print(f'Warning: SIP index not found at {sip_index_path}', file=sys.stderr)

    print(f"\n{'═' * 60}")
    print(f"🔬 SIP 衝突掃描器 — {args.domain.upper()}")
    print(f"   資源目錄: {args.resources_dir}")
    print(f"{'═' * 60}")

    # Parse data
    sips = parse_sip_index(sip_index_path)
    contexts = parse_resource_files(args.resources_dir)
    resolutions = load_conflict_resolutions(args.resources_dir)

    # Also parse changelog for additional SIP metadata
    changelog_path = os.path.join(args.resources_dir, 'sip_changelog.md')
    if os.path.exists(changelog_path):
        changelog_sips = parse_sip_index(changelog_path)
        # Merge - changelog may have richer descriptions
        for sid, sdata in changelog_sips.items():
            if sid not in sips:
                sips[sid] = sdata
            else:
                # Enrich with changelog data if dimensions/conditions are richer
                if len(sdata['dimensions']) > len(sips[sid]['dimensions']):
                    sips[sid]['dimensions'] = sdata['dimensions']
                if len(sdata['conditions']) > len(sips[sid]['conditions']):
                    sips[sid]['conditions'] = sdata['conditions']

    print(f"\n   📋 已識別 SIP: {len(sips)} 個")
    status_counts = defaultdict(int)
    for sip in sips.values():
        status_counts[sip.get('status', 'ACTIVE')] += 1
    active = status_counts['ACTIVE']
    baked = status_counts['BAKED']
    observation = status_counts['OBSERVATION']
    complete = status_counts['COMPLETE']
    deprecated = status_counts['DEPRECATED']
    print(
        f"      🟢 活躍: {active} | ✅ 已 Bake: {baked} | "
        f"🟡 觀察: {observation} | ✅ 完成: {complete} | 🔴 已廢棄: {deprecated}"
    )

    # Run conflict detection
    all_issues = []

    # 1. Direction conflicts
    dir_conflicts_raw = detect_direction_conflicts(sips)
    dir_conflicts, dir_suppressed = filter_resolved_issues(
        dir_conflicts_raw, resolutions['direction']
    )
    high = sum(1 for c in dir_conflicts if c['severity'] == 'HIGH')
    med = sum(1 for c in dir_conflicts if c['severity'] == 'MEDIUM')
    print(f"\n   🔴 方向衝突: {len(dir_conflicts)} 個 (高危 {high}, 中危 {med}, 已解決 {len(dir_suppressed)})")
    for c in dir_conflicts[:5]:
        print(f"      {c['type']}")
        print(f"         {c['sip_a']} ({c['effect_a']}) ⟷ {c['sip_b']} ({c['effect_b']})")
        print(f"         共享維度: {', '.join(c['shared_dims'])}")
        if c['overlap_conditions']:
            print(f"         重疊條件: {', '.join(c['overlap_conditions'])}")

    # 2. Duplicate counting
    dup_counting_raw = detect_duplicate_counting(sips)
    dup_counting, dup_suppressed = filter_resolved_issues(
        dup_counting_raw, resolutions['duplicate']
    )
    print(f"\n   🟠 重複計算: {len(dup_counting)} 個 (已解決 {len(dup_suppressed)})")
    for d in dup_counting[:5]:
        print(f"      {d['sip_a']} + {d['sip_b']} 在 Step {d['shared_step']} 同維度 {d['effect']}")

    # 3. Cross-references
    cross = detect_cross_references(sips, contexts)
    print(f"\n   🔵 交叉引用: {len(cross)} 對")
    for cr in cross[:5]:
        print(f"      {cr['sip_a']} ⟷ {cr['sip_b']}")

    # 4. Deprecated references
    dep_refs = detect_deprecated_references(sips, contexts)
    print(f"\n   ⚠️ 過時引用: {len(dep_refs)} 個")
    for dr in dep_refs[:5]:
        print(f"      {dr['sip']} 仍被 {dr['file']} 引用")

    # Summary
    print(f"\n{'═' * 60}")
    high_risk_conflicts = [c for c in dir_conflicts if c.get('severity') == 'HIGH']
    review_signals = [c for c in dir_conflicts if c.get('severity') != 'HIGH'] + cross
    blocking_issues = high_risk_conflicts + dup_counting + dep_refs

    if not blocking_issues:
        print(f"   ✅ 冇高危方向衝突 / 重複計算 / 過時引用阻塞項")
        if review_signals:
            print(f"   ℹ️ 保留 {len(review_signals)} 項中低危/交叉引用提示，供定期人工審閱")
    else:
        print(f"   ⚠️ 發現 {len(blocking_issues)} 項阻塞問題 ({len(high_risk_conflicts)} 高危)")
        print(f"   LLM 需審閱以上衝突並判斷:")
        print(f"      • 方向衝突係有意設計（互相制衡）定係真衝突？")
        print(f"      • 重複計算係刻意疊加定係無意重複？")
        print(f"      • 過時引用需要清理定係保留作歷史參考？")
    print(f"{'═' * 60}")

    if args.json:
        print(json.dumps({
            'sip_count': len(sips),
            'active': active,
            'baked': baked,
            'observation': observation,
            'complete': complete,
            'deprecated': deprecated,
            'blocking_issues': blocking_issues,
            'review_signals': review_signals,
            'suppressed': {
                'direction_conflicts': dir_suppressed,
                'duplicate_counting': dup_suppressed,
            },
        }, ensure_ascii=False, indent=2, default=str))

    sys.exit(1 if blocking_issues else 0)


if __name__ == '__main__':
    main()
