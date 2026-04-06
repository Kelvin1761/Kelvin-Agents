"""
observation_log_manager.py — 觀察項登記簿管理器

管理 observation_log.md 嘅 CRUD 操作、去重、畢業檢查。
消除 Validator Step 4d 嘅人手檔案管理工作。

Usage:
  python observation_log_manager.py <log_path> --action list
  python observation_log_manager.py <log_path> --action add --id OBS-001 --pattern "..." --sip-direction "..." --case "R3|#5 Name|D→2nd|$22"
  python observation_log_manager.py <log_path> --action add-case --id OBS-001 --case "R5|#8 Name|C→1st|$35"
  python observation_log_manager.py <log_path> --action check-graduation
  python observation_log_manager.py <log_path> --action graduate --id OBS-001 --sip-tag "SIP-RR16"

Exit codes:
  0 = Success
  1 = Graduation candidates found
  2 = Error
"""
import sys, io, re, os, argparse
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

GRAD_THRESHOLD_CASES = 3
GRAD_THRESHOLD_HIT = 30  # percent


def parse_log(path):
    """Parse observation_log.md into structured data."""
    if not os.path.exists(path):
        return {'observations': [], 'graduated': [], 'rejected': []}

    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    observations = []
    graduated = []
    rejected = []

    current_section = 'observing'
    current_obs = None

    for line in text.split('\n'):
        if '## 🟡 觀察中' in line:
            current_section = 'observing'
            continue
        elif '## ✅ 已正式化' in line:
            current_section = 'graduated'
            continue
        elif '## ❌ 已否決' in line:
            current_section = 'rejected'
            continue

        # Parse observation header
        m = re.match(r'###\s+(OBS-\d+)[：:]\s*(.+)', line)
        if m:
            if current_obs:
                target = observations if current_section == 'observing' else graduated if current_section == 'graduated' else rejected
                target.append(current_obs)
            current_obs = {
                'id': m.group(1),
                'name': m.group(2).strip(),
                'pattern': '',
                'sip_direction': '',
                'cases': [],
                'status': current_section,
                'sip_tag': None,
            }
            continue

        if not current_obs:
            continue

        # Parse fields
        if line.strip().startswith('- **模式描述:**'):
            current_obs['pattern'] = line.split(':**', 1)[1].strip() if ':**' in line else ''
        elif line.strip().startswith('- **潛在 SIP 方向:**'):
            current_obs['sip_direction'] = line.split(':**', 1)[1].strip() if ':**' in line else ''
        elif line.strip().startswith('- **狀態:**'):
            status_text = line.split(':**', 1)[1].strip() if ':**' in line else ''
            if '已正式化' in status_text:
                m2 = re.search(r'SIP-\S+', status_text)
                if m2: current_obs['sip_tag'] = m2.group(0)
        elif '|' in line and not line.strip().startswith('|:') and not line.strip().startswith('| #'):
            # Parse case table row
            cols = [c.strip() for c in line.split('|')[1:-1]]
            if len(cols) >= 5 and cols[0].strip().isdigit():
                current_obs['cases'].append({
                    'num': int(cols[0]),
                    'date': cols[1],
                    'race': cols[2],
                    'horse': cols[3],
                    'result': cols[4],
                    'odds': cols[5] if len(cols) > 5 else '',
                })

    if current_obs:
        target = observations if current_section == 'observing' else graduated if current_section == 'graduated' else rejected
        target.append(current_obs)

    return {'observations': observations, 'graduated': graduated, 'rejected': rejected}


def write_log(path, data):
    """Write structured data back to observation_log.md."""
    today = datetime.now().strftime('%Y-%m-%d')
    total = len(data['observations']) + len(data['graduated']) + len(data['rejected'])

    lines = [
        '# 觀察項登記簿 (Observation Log)',
        f'> 最後更新: {today} | 累計觀察項: {total}',
        '',
    ]

    def write_section(items, header):
        lines.append(f'## {header}')
        lines.append('')
        for obs in items:
            lines.append(f"### {obs['id']}: {obs['name']}")
            lines.append(f"- **模式描述:** {obs['pattern']}")
            lines.append(f"- **潛在 SIP 方向:** {obs['sip_direction']}")
            lines.append('- **案例:**')
            lines.append('  | # | 日期 | 場次 | 馬匹 | 評級→實際 | 起步價 |')
            lines.append('  |:--|:---|:---|:---|:---|:---|')
            for c in obs['cases']:
                lines.append(f"  | {c['num']} | {c['date']} | {c['race']} | {c['horse']} | {c['result']} | {c['odds']} |")
            n = len(obs['cases'])
            status = '🟡 觀察中'
            if obs.get('sip_tag'):
                status = f"✅ 已正式化 — {obs['sip_tag']}"
            elif obs['status'] == 'rejected':
                status = '❌ 已否決'
            elif n >= GRAD_THRESHOLD_CASES:
                status = '🟢 可提出SIP'
            lines.append(f"- **累計案例:** {n} | **畢業門檻:** ≥{GRAD_THRESHOLD_CASES} 案例 + ≥{GRAD_THRESHOLD_HIT}% 命中")
            lines.append(f"- **狀態:** {status}")
            lines.append('')

    write_section(data['observations'], '🟡 觀察中')
    write_section(data['graduated'], '✅ 已正式化')
    write_section(data['rejected'], '❌ 已否決')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def check_dedup(existing_obs, new_pattern):
    """Check if new pattern overlaps with existing observations."""
    new_words = set(re.findall(r'[\w\u4e00-\u9fff]+', new_pattern.lower()))
    for obs in existing_obs:
        ex_words = set(re.findall(r'[\w\u4e00-\u9fff]+', obs['pattern'].lower()))
        if not new_words or not ex_words:
            continue
        overlap = len(new_words & ex_words) / max(len(new_words), len(ex_words))
        if overlap >= 0.7:
            return obs['id'], overlap
    return None, 0


def main():
    parser = argparse.ArgumentParser(description='觀察項登記簿管理器')
    parser.add_argument('log_path', help='Path to observation_log.md')
    parser.add_argument('--action', required=True,
                        choices=['list', 'add', 'add-case', 'check-graduation', 'graduate', 'reject'])
    parser.add_argument('--id', help='Observation ID (e.g., OBS-001)')
    parser.add_argument('--pattern', help='Pattern description (for add)')
    parser.add_argument('--sip-direction', help='Potential SIP direction (for add)')
    parser.add_argument('--case', help='Case data: "date|race|horse|result|odds" (for add/add-case)')
    parser.add_argument('--sip-tag', help='SIP tag for graduation (e.g., SIP-RR16)')
    parser.add_argument('--name', help='Observation name (for add)')
    args = parser.parse_args()

    data = parse_log(args.log_path)

    if args.action == 'list':
        print(f"\n📋 觀察項登記簿: {args.log_path}")
        print(f"   🟡 觀察中: {len(data['observations'])}")
        for obs in data['observations']:
            grad = '🟢 可畢業' if len(obs['cases']) >= GRAD_THRESHOLD_CASES else ''
            print(f"      {obs['id']}: {obs['name']} ({len(obs['cases'])} 案例) {grad}")
        print(f"   ✅ 已正式化: {len(data['graduated'])}")
        print(f"   ❌ 已否決: {len(data['rejected'])}")

    elif args.action == 'add':
        if not args.pattern:
            print('Error: --pattern required for add', file=sys.stderr)
            sys.exit(2)

        # Dedup check
        dup_id, overlap = check_dedup(data['observations'], args.pattern)
        if dup_id:
            print(f'⚠️ 重複偵測: 同 {dup_id} 有 {overlap:.0%} 重疊。建議用 --action add-case --id {dup_id} 代替。')
            sys.exit(1)

        # Generate next ID
        all_ids = [o['id'] for o in data['observations'] + data['graduated'] + data['rejected']]
        max_num = max([int(re.search(r'\d+', i).group()) for i in all_ids] or [0])
        new_id = args.id or f'OBS-{max_num + 1:03d}'
        today = datetime.now().strftime('%Y-%m-%d')

        new_obs = {
            'id': new_id,
            'name': args.name or args.pattern[:30],
            'pattern': args.pattern,
            'sip_direction': args.sip_direction or '',
            'cases': [],
            'status': 'observing',
            'sip_tag': None,
        }

        if args.case:
            parts = args.case.split('|')
            new_obs['cases'].append({
                'num': 1,
                'date': parts[0] if len(parts) > 0 else today,
                'race': parts[1] if len(parts) > 1 else '',
                'horse': parts[2] if len(parts) > 2 else '',
                'result': parts[3] if len(parts) > 3 else '',
                'odds': parts[4] if len(parts) > 4 else '',
            })

        data['observations'].append(new_obs)
        write_log(args.log_path, data)
        print(f'✅ 新增觀察項 {new_id}: {new_obs["name"]}')

    elif args.action == 'add-case':
        if not args.id or not args.case:
            print('Error: --id and --case required for add-case', file=sys.stderr)
            sys.exit(2)

        target = next((o for o in data['observations'] if o['id'] == args.id), None)
        if not target:
            print(f'Error: {args.id} not found in observing section', file=sys.stderr)
            sys.exit(2)

        parts = args.case.split('|')
        today = datetime.now().strftime('%Y-%m-%d')
        target['cases'].append({
            'num': len(target['cases']) + 1,
            'date': parts[0] if len(parts) > 0 else today,
            'race': parts[1] if len(parts) > 1 else '',
            'horse': parts[2] if len(parts) > 2 else '',
            'result': parts[3] if len(parts) > 3 else '',
            'odds': parts[4] if len(parts) > 4 else '',
        })

        write_log(args.log_path, data)
        n = len(target['cases'])
        grad = f' → 🟢 可畢業為正式 SIP!' if n >= GRAD_THRESHOLD_CASES else ''
        print(f"✅ 案例已加入 {args.id} (累計 {n} 個){grad}")

    elif args.action == 'check-graduation':
        candidates = [o for o in data['observations'] if len(o['cases']) >= GRAD_THRESHOLD_CASES]
        if candidates:
            print(f'\n🟢 可畢業觀察項 ({len(candidates)}):')
            for c in candidates:
                print(f'   {c["id"]}: {c["name"]} ({len(c["cases"])} 案例)')
                print(f'      → 建議升級為正式 SIP')
            sys.exit(1)  # Signal: graduation candidates found
        else:
            print('✅ 冇觀察項達到畢業門檻。')
            sys.exit(0)

    elif args.action == 'graduate':
        if not args.id:
            print('Error: --id required for graduate', file=sys.stderr)
            sys.exit(2)
        target = next((o for o in data['observations'] if o['id'] == args.id), None)
        if not target:
            print(f'Error: {args.id} not found', file=sys.stderr)
            sys.exit(2)
        target['sip_tag'] = args.sip_tag or 'SIP-PENDING'
        target['status'] = 'graduated'
        data['observations'].remove(target)
        data['graduated'].append(target)
        write_log(args.log_path, data)
        print(f'✅ {args.id} 已畢業為正式 SIP ({target["sip_tag"]})')

    elif args.action == 'reject':
        if not args.id:
            print('Error: --id required for reject', file=sys.stderr)
            sys.exit(2)
        target = next((o for o in data['observations'] if o['id'] == args.id), None)
        if not target:
            print(f'Error: {args.id} not found', file=sys.stderr)
            sys.exit(2)
        target['status'] = 'rejected'
        data['observations'].remove(target)
        data['rejected'].append(target)
        write_log(args.log_path, data)
        print(f'❌ {args.id} 已否決')

    sys.exit(0)


if __name__ == '__main__':
    main()
