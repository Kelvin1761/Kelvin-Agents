"""
agent_health_scanner.py — Agent Health Check 自動掃描器

Automated structural/quality checks for Antigravity agents.
LLM handles judgment-based checks (Blueprint coverage, logic quality).

Usage:
  python agent_health_scanner.py                          # Scan all (Tier 1 + 2)
  python agent_health_scanner.py --tier 1                 # Tier 1 only (.agents/skills/)
  python agent_health_scanner.py --target nba/nba_analyst # Specific agent
  python agent_health_scanner.py --list-all               # List all agents (for Mode A Phase 3)
  python agent_health_scanner.py --json                   # JSON output
  python agent_health_scanner.py --fix-suggestions        # Include fix suggestions

Exit codes: 0 = Pass, 1 = Warnings, 2 = Critical
"""
import sys, io, re, os, json, argparse, pathlib

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TIER1_DIR = '.agents/skills'
TIER2_DIR = '.agent/skills'
LINE_LIMIT = 200
BANNED_TOOLS = ['write_to_file', 'browser_subagent']
HARDCODED_PATHS = ['/Users/', '/tmp/', '/home/', 'C:\\Users\\']
OS_SPECIFIC_PATTERNS = ['cat <<EOF', 'cat <<\'EOF\'', 'heredoc', '#!/bin/bash']
STALE_DAYS = 180


def find_workspace_root():
    """Walk up from script location to find workspace root."""
    p = pathlib.Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / '.agents').is_dir() or (parent / '.agent').is_dir():
            return parent
    return pathlib.Path.cwd()


def parse_frontmatter(text):
    """Extract YAML-like frontmatter from markdown."""
    fm = {}
    if not text.startswith('---'):
        return fm, ['Missing YAML frontmatter (must start with ---)']
    issues = []
    end = text.find('---', 3)
    if end == -1:
        return fm, ['Frontmatter not closed (missing second ---)']
    raw = text[3:end].strip()
    for line in raw.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        if ':' in line:
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip()
    if 'name' not in fm:
        issues.append('Frontmatter missing "name" field')
    if 'description' not in fm:
        issues.append('Frontmatter missing "description" field')
    if 'version' not in fm:
        issues.append('Frontmatter missing "version" field')
    return fm, issues


def scan_agent(skill_path, tier=1, fix_suggestions=False):
    """Scan a single agent SKILL.md and return findings."""
    findings = []
    skill_file = skill_path / 'SKILL.md'
    if not skill_file.exists():
        findings.append({'check': 'A-EXISTS', 'rating': '❌', 'confidence': 95,
                         'note': f'SKILL.md not found at {skill_path}'})
        return findings

    text = skill_file.read_text(encoding='utf-8', errors='replace')
    lines = text.split('\n')
    line_count = len(lines)

    # --- A. Structural Compliance ---
    fm, fm_issues = parse_frontmatter(text)
    if not fm_issues:
        findings.append({'check': 'A-FRONTMATTER', 'rating': '✅', 'confidence': 100,
                         'note': f'name={fm.get("name","")}, version={fm.get("version","")}'})
    else:
        for issue in fm_issues:
            findings.append({'check': 'A-FRONTMATTER', 'rating': '❌', 'confidence': 90,
                             'note': issue})

    if line_count <= LINE_LIMIT:
        findings.append({'check': 'A-LINES', 'rating': '✅', 'confidence': 100,
                         'note': f'{line_count} lines (limit: {LINE_LIMIT})'})
    else:
        findings.append({'check': 'A-LINES', 'rating': '❌', 'confidence': 85,
                         'note': f'{line_count} lines EXCEEDS limit of {LINE_LIMIT}',
                         'fix': 'Move templates/examples to resources/' if fix_suggestions else None})

    # --- B. Quality Baseline ---
    # Banned tools
    for tool in BANNED_TOOLS:
        occurrences = [i+1 for i, l in enumerate(lines) if tool in l and 'ban' not in l.lower() and 'prohibit' not in l.lower() and '❌' not in l and '嚴禁' not in l]
        if occurrences:
            findings.append({'check': 'B-BANNED-TOOL', 'rating': '❌', 'confidence': 80,
                             'note': f'Uses banned tool `{tool}` at lines {occurrences[:3]}',
                             'fix': f'Replace {tool} with safe alternatives' if fix_suggestions else None})

    # Failure protocol
    has_failure = any(kw in text for kw in ['失敗', 'failure', 'Failure', 'error handling', 'Error Handling', '熔斷'])
    if has_failure:
        findings.append({'check': 'B-FAILURE', 'rating': '✅', 'confidence': 70,
                         'note': 'Failure handling protocol detected'})
    elif tier == 1:
        findings.append({'check': 'B-FAILURE', 'rating': '⚠️', 'confidence': 55,
                         'note': 'No failure handling protocol found'})

    # Resource references check
    resource_dir = skill_path / 'resources'
    ref_pattern = re.compile(r'`resources/([^`]+)`|resources/(\S+\.md)')
    referenced = set()
    for m in ref_pattern.finditer(text):
        ref_name = m.group(1) or m.group(2)
        # Skip example references (preceded by e.g., for example, etc.)
        ctx_start = max(0, m.start() - 80)
        context = text[ctx_start:m.start()].lower()
        if any(ex in context for ex in ['e.g.', 'for example', 'example:', 'such as']):
            continue
        referenced.add(ref_name)
    if resource_dir.is_dir() and referenced:
        for ref in referenced:
            ref_clean = ref.rstrip(')')
            if not (resource_dir / ref_clean).exists():
                findings.append({'check': 'C-RESOURCE-REF', 'rating': '❌', 'confidence': 85,
                                 'note': f'References `resources/{ref_clean}` but file not found'})

    # Script references check
    script_pattern = re.compile(r'`scripts/([^`]+)`|scripts/(\S+\.py)')
    script_refs = set()
    for m in script_pattern.finditer(text):
        script_refs.add(m.group(1) or m.group(2))
    scripts_dir = skill_path / 'scripts'
    for ref in script_refs:
        ref_clean = ref.rstrip(')')
        if scripts_dir.is_dir() and not (scripts_dir / ref_clean).exists():
            findings.append({'check': 'C-SCRIPT-REF', 'rating': '⚠️', 'confidence': 60,
                             'note': f'References `scripts/{ref_clean}` but file not found'})

    # --- D. Anti-Pattern Scan (Tier 1 only) ---
    if tier == 1:
        # Hardcoded paths
        for hp in HARDCODED_PATHS:
            path_lines = [i+1 for i, l in enumerate(lines) if hp in l and 'anti-pattern' not in l.lower() and '❌' not in l]
            if path_lines:
                findings.append({'check': 'E-HARDCODED-PATH', 'rating': '❌', 'confidence': 90,
                                 'note': f'Hardcoded path `{hp}` at lines {path_lines[:3]}',
                                 'fix': 'Use relative paths from workspace root' if fix_suggestions else None})

        # OS-specific patterns
        for osp in OS_SPECIFIC_PATTERNS:
            osp_lines = [i+1 for i, l in enumerate(lines) if osp in l and 'anti-pattern' not in l.lower() and '❌' not in l and 'avoid' not in l.lower()]
            if osp_lines:
                findings.append({'check': 'E-OS-SPECIFIC', 'rating': '⚠️', 'confidence': 65,
                                 'note': f'OS-specific syntax `{osp}` at lines {osp_lines[:3]}'})

        # TODO/FIXME markers
        todo_lines = [i+1 for i, l in enumerate(lines) if any(m in l.upper() for m in ['TODO', 'FIXME', 'HACK', '待更新'])]
        if todo_lines:
            findings.append({'check': 'D-TODO', 'rating': '⚠️', 'confidence': 45,
                             'note': f'TODO/FIXME markers at lines {todo_lines[:5]}'})

        # Stale file check
        try:
            from datetime import datetime
            mtime = datetime.fromtimestamp(skill_file.stat().st_mtime)
            age = (datetime.now() - mtime).days
            if age > STALE_DAYS:
                findings.append({'check': 'D-STALE', 'rating': '⚠️', 'confidence': 40,
                                 'note': f'SKILL.md last modified {age} days ago'})
        except Exception:
            pass

    # Filter out None fixes
    for f in findings:
        if 'fix' in f and f['fix'] is None:
            del f['fix']

    return findings


def calculate_score(findings):
    """Calculate health score from findings."""
    if not findings:
        return 100, 'A'
    total = len(findings)
    passed = sum(1 for f in findings if f['rating'] == '✅')
    score = round(passed / total * 100) if total > 0 else 100
    if score >= 90: grade = 'A'
    elif score >= 70: grade = 'B'
    elif score >= 50: grade = 'C'
    else: grade = 'D'
    return score, grade


def discover_agents(root, tier1_dir, tier2_dir, target=None, tier_filter=None):
    """Discover all agent directories."""
    agents = []
    dirs_to_scan = []
    if tier_filter is None or tier_filter == 1:
        t1 = root / tier1_dir
        if t1.is_dir():
            dirs_to_scan.append((t1, 1))
    if tier_filter is None or tier_filter == 2:
        t2 = root / tier2_dir
        if t2.is_dir():
            dirs_to_scan.append((t2, 2))

    for base_dir, tier in dirs_to_scan:
        for skill_md in sorted(base_dir.rglob('SKILL.md')):
            rel = skill_md.parent.relative_to(base_dir)
            rel_str = str(rel).replace('\\', '/')
            if target and target not in rel_str:
                continue
            agents.append({'path': skill_md.parent, 'rel': rel_str, 'tier': tier, 'base': base_dir})
    return agents


def list_all_agents(agents):
    """List all agents with name/description for Mode A Phase 3 matching."""
    print(f"\n{'═' * 60}")
    print(f"📋 Agent Registry — {len(agents)} agents")
    print(f"{'═' * 60}\n")
    print(f"{'Agent':<40} {'Tier':<6} {'Version':<10}")
    print(f"{'─' * 40} {'─' * 5} {'─' * 9}")
    for a in agents:
        skill_file = a['path'] / 'SKILL.md'
        if skill_file.exists():
            text = skill_file.read_text(encoding='utf-8', errors='replace')
            fm, _ = parse_frontmatter(text)
            name = fm.get('name', a['rel'])
            version = fm.get('version', '?')
            print(f"{a['rel']:<40} T{a['tier']:<5} {version:<10}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Agent Health Scanner — Antigravity Ecosystem')
    parser.add_argument('--tier', type=int, choices=[1, 2], help='Scan tier: 1=custom, 2=AG Kit')
    parser.add_argument('--target', '-t', help='Scan specific agent (e.g., nba/nba_analyst)')
    parser.add_argument('--list-all', action='store_true', help='List all agents for Phase 3 matching')
    parser.add_argument('--json', action='store_true', help='JSON output')
    parser.add_argument('--fix-suggestions', action='store_true', help='Include fix suggestions')
    args = parser.parse_args()

    root = find_workspace_root()
    agents = discover_agents(root, TIER1_DIR, TIER2_DIR, target=args.target, tier_filter=args.tier)

    if not agents:
        print('No agents found. Check workspace root.', file=sys.stderr)
        sys.exit(2)

    if args.list_all:
        list_all_agents(agents)
        sys.exit(0)

    print(f"\n{'═' * 60}")
    print(f"🔬 Agent Health Scan — {len(agents)} agents found")
    print(f"   Workspace: {root}")
    print(f"{'═' * 60}")

    all_results = {}
    total_critical = 0
    total_warnings = 0

    for a in agents:
        findings = scan_agent(a['path'], tier=a['tier'], fix_suggestions=args.fix_suggestions)
        score, grade = calculate_score(findings)
        criticals = sum(1 for f in findings if f['rating'] == '❌')
        warnings = sum(1 for f in findings if f['rating'] == '⚠️')
        total_critical += criticals
        total_warnings += warnings

        icon = '✅' if grade in ('A', 'B') else '⚠️' if grade == 'C' else '❌'
        tier_tag = f'[T{a["tier"]}]'
        detail = ''
        if criticals: detail += f' [{criticals} critical]'
        if warnings: detail += f' [{warnings} warnings]'

        print(f"\n   {icon} {a['rel']:<35} {tier_tag} Score: {score}% ({grade}){detail}")

        # Show critical findings inline
        for f in findings:
            if f['rating'] == '❌' and f.get('confidence', 0) >= 30:
                fix_hint = f" → {f['fix']}" if 'fix' in f else ''
                print(f"      ❌ [{f['confidence']}] {f['check']}: {f['note']}{fix_hint}")

        all_results[a['rel']] = {
            'score': score, 'grade': grade, 'tier': a['tier'],
            'findings': findings, 'criticals': criticals, 'warnings': warnings
        }

    # Summary
    agents_ok = sum(1 for r in all_results.values() if r['grade'] in ('A', 'B'))
    print(f"\n{'═' * 60}")
    print(f"   📊 Overall: {agents_ok}/{len(agents)} agents at B+ or above")
    if total_critical:
        print(f"   🔴 {total_critical} critical issues across {sum(1 for r in all_results.values() if r['criticals'] > 0)} agents")
    if total_warnings:
        print(f"   🟡 {total_warnings} warnings")
    print(f"   LLM judgment needed: Blueprint coverage (§F)")
    print(f"{'═' * 60}\n")

    if args.json:
        # Sanitize paths for JSON
        for k, v in all_results.items():
            for f in v.get('findings', []):
                if 'fix' not in f:
                    f['fix'] = None
        print(json.dumps(all_results, ensure_ascii=False, indent=2, default=str))

    sys.exit(2 if total_critical > 0 else 1 if total_warnings > 0 else 0)


if __name__ == '__main__':
    main()
