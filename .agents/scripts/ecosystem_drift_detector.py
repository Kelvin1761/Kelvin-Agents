"""
ecosystem_drift_detector.py — Ecosystem 文檔 vs 實際目錄偏差偵測器

Parses ecosystem_reference.md tree structure and compares against actual filesystem.

Usage:
  python ecosystem_drift_detector.py                # Auto-detect paths
  python ecosystem_drift_detector.py --json         # JSON output

Exit codes: 0 = No drift, 1 = Drift detected, 2 = Error
"""
import sys, io, re, os, json, argparse, pathlib

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def find_workspace_root():
    """Walk up from script location to find workspace root."""
    p = pathlib.Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / '.agents').is_dir() or (parent / '.agent').is_dir():
            return parent
    return pathlib.Path.cwd()


def parse_tree_structure(reference_text):
    """Extract directory names from markdown tree structure in ecosystem_reference.md."""
    documented_dirs = set()
    # Match tree lines like: ├── agent_architect/  or  │   ├── nba_wong_choi/
    tree_pattern = re.compile(r'[│├└─\s]+(\w[\w\-\.]*)/\s*')
    for line in reference_text.split('\n'):
        m = tree_pattern.search(line)
        if m:
            dirname = m.group(1)
            # Skip non-agent dirs
            if dirname not in ('__pycache__', 'node_modules', '.git'):
                documented_dirs.add(dirname)
    return documented_dirs


def scan_actual_dirs(scan_dir, depth=2):
    """Scan actual filesystem directories up to given depth."""
    actual_dirs = set()
    base = pathlib.Path(scan_dir)
    if not base.is_dir():
        return actual_dirs
    for item in base.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name != '__pycache__':
            if item.name == "antigravity-awesome-skills":
                continue
            actual_dirs.add(item.name)
            if depth > 1:
                for sub in item.iterdir():
                    if sub.is_dir() and not sub.name.startswith('.') and sub.name != '__pycache__':
                        actual_dirs.add(sub.name)
    return actual_dirs


def scan_agent_table(reference_text):
    """Extract agent names from the markdown table in ecosystem_reference.md."""
    documented_agents = set()
    # Match table rows like: | **NBA Wong Choi** |
    table_pattern = re.compile(r'\|\s*\*\*([^*]+)\*\*\s*\|')
    for line in reference_text.split('\n'):
        m = table_pattern.search(line)
        if m:
            agent_name = m.group(1).strip()
            if agent_name and agent_name not in ('Agent', 'Name', '---'):
                documented_agents.add(agent_name)
    return documented_agents


def main():
    parser = argparse.ArgumentParser(description='Ecosystem Drift Detector')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()

    root = find_workspace_root()

    # Find ecosystem_reference.md
    ref_candidates = [
        root / '.agents' / 'skills' / 'agent_architect' / 'resources' / 'ecosystem_reference.md',
    ]
    ref_path = None
    for c in ref_candidates:
        if c.exists():
            ref_path = c
            break

    if not ref_path:
        print('Error: ecosystem_reference.md not found', file=sys.stderr)
        sys.exit(2)

    ref_text = ref_path.read_text(encoding='utf-8', errors='replace')

    # Parse documented structure
    documented_dirs = parse_tree_structure(ref_text)
    documented_agents = scan_agent_table(ref_text)

    # Scan actual filesystem
    scan_dirs = [root / '.agents' / 'skills']
    actual_dirs = set()
    for sd in scan_dirs:
        actual_dirs |= scan_actual_dirs(sd)

    # Compare
    in_fs_not_ref = actual_dirs - documented_dirs
    in_ref_not_fs = documented_dirs - actual_dirs

    # Filter out known non-agent dirs
    ignore_dirs = {'scripts', 'resources', 'examples', '__pycache__', 'desktop.ini'}
    in_fs_not_ref -= ignore_dirs
    in_ref_not_fs -= ignore_dirs

    # Count SKILL.md files for agent count
    actual_agent_count = 0
    for sd in scan_dirs:
        if sd.is_dir():
            for fpath in sd.rglob('SKILL.md'):
                if 'antigravity-awesome-skills' not in str(fpath.parent):
                    actual_agent_count += 1

    print(f"\n{'═' * 60}")
    print(f"🔍 Ecosystem Drift Report")
    print(f"   Reference: {ref_path.name}")
    print(f"   Scan: {', '.join(str(sd) for sd in scan_dirs)}")
    print(f"{'═' * 60}")

    if in_fs_not_ref:
        print(f"\n   📁 In filesystem but NOT in reference:")
        for d in sorted(in_fs_not_ref):
            print(f"      + {d}/   [NOT DOCUMENTED]")

    if in_ref_not_fs:
        print(f"\n   📄 In reference but NOT on disk:")
        for d in sorted(in_ref_not_fs):
            print(f"      - {d}/   [BROKEN REF]")

    if not in_fs_not_ref and not in_ref_not_fs:
        print(f"\n   ✅ No directory drift detected!")

    total_drift = len(in_fs_not_ref) + len(in_ref_not_fs)
    drift_level = 'NONE' if total_drift == 0 else 'LOW' if total_drift <= 2 else 'MEDIUM' if total_drift <= 5 else 'HIGH'

    print(f"\n   📊 Documented agents in table: {len(documented_agents)}")
    print(f"   📊 Actual SKILL.md files: {actual_agent_count}")
    if actual_agent_count != len(documented_agents):
        print(f"   ⚠️  Agent count mismatch: {actual_agent_count - len(documented_agents):+d}")

    print(f"\n{'═' * 60}")
    print(f"   Drift Level: {drift_level} ({total_drift} items)")
    if total_drift > 0:
        print(f"   Suggestion: Update ecosystem_reference.md")
    print(f"{'═' * 60}\n")

    if args.json:
        result = {
            'drift_level': drift_level,
            'total_drift': total_drift,
            'in_filesystem_not_reference': sorted(in_fs_not_ref),
            'in_reference_not_filesystem': sorted(in_ref_not_fs),
            'documented_agent_count': len(documented_agents),
            'actual_agent_count': actual_agent_count,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(1 if total_drift > 0 else 0)


if __name__ == '__main__':
    main()
