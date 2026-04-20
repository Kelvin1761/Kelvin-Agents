#!/usr/bin/env python3
"""
mc_audit.py — Monte Carlo Quality Dashboard V2
===============================================
Enhanced per-meeting MC quality audit with:
- Auto-discovery of meeting directories
- HKJC benchmark comparison
- Health score per race + per meeting
- Actionable alerts for out-of-range metrics
- JSON report output for tracking

Usage:
  python3 mc_audit.py                         # Scan all meetings
  python3 mc_audit.py 2026-04-19_ShaTin       # Scan specific meeting
  python3 mc_audit.py --report audit.json      # Save JSON report
"""
import json, glob, os, sys, math, argparse


# ============================================================
# HKJC Benchmarks (based on historical data)
# ============================================================
BENCHMARKS = {
    'top1_range': (15.0, 35.0),      # Favourite win%
    'top4_range': (45.0, 65.0),      # Top4 combined win%
    'bottom_half_range': (12.0, 30.0), # Bottom 50% combined
    'entropy_range': (0.75, 0.95),    # Normalized Shannon entropy
    'gini_range': (0.15, 0.45),       # Gini coefficient
    'hhi_max': 2000,                  # HHI threshold
    'last_horse_min': 0.5,            # Last horse should have some chance
}


def calc_race_stats(data: dict) -> dict:
    """Calculate quality metrics for a single race MC result."""
    results = data.get('results', {})
    n_horses = data.get('horses_count', 0)
    distance = data.get('distance', 0)
    is_straight = data.get('is_straight_course', False)
    engine = data.get('engine_version', '?')

    sorted_r = sorted(results.items(), key=lambda x: x[1]['win_pct'], reverse=True)
    if not sorted_r or n_horses < 3:
        return {}

    top1_win = sorted_r[0][1]['win_pct']
    top2_win = sum(x[1]['win_pct'] for x in sorted_r[:2])
    top3_win = sum(x[1]['win_pct'] for x in sorted_r[:3])
    top4_win = sum(x[1]['win_pct'] for x in sorted_r[:4])
    bottom_half_win = sum(x[1]['win_pct'] for x in sorted_r[n_horses // 2:])
    last_win = sorted_r[-1][1]['win_pct']

    # Normalized Shannon entropy
    probs = [x[1]['win_pct'] / 100.0 for x in sorted_r if x[1]['win_pct'] > 0]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(n_horses) if n_horses > 0 else 1
    norm_entropy = entropy / max_entropy if max_entropy > 0 else 0

    # HHI (Herfindahl-Hirschman Index)
    hhi = sum((p * 100) ** 2 for p in probs)

    # Gini coefficient
    win_pcts = [x[1]['win_pct'] for x in sorted_r]
    n = len(win_pcts)
    mean_val = sum(win_pcts) / n if n > 0 else 1
    gini_num = sum(abs(win_pcts[i] - win_pcts[j]) for i in range(n) for j in range(n))
    gini = gini_num / (2 * n * n * mean_val) if mean_val > 0 else 0

    # Health score (0-100): measures how well-calibrated the distribution is
    health = 100
    alerts = []

    # Check top1
    t1_lo, t1_hi = BENCHMARKS['top1_range']
    if top1_win > t1_hi:
        health -= min(20, (top1_win - t1_hi) * 2)
        alerts.append(f'Top1 過高 ({top1_win:.1f}% > {t1_hi}%)')
    elif top1_win < t1_lo:
        health -= min(10, (t1_lo - top1_win))
        alerts.append(f'Top1 過低 ({top1_win:.1f}% < {t1_lo}%)')

    # Check top4
    t4_lo, t4_hi = BENCHMARKS['top4_range']
    if top4_win > t4_hi:
        health -= min(30, (top4_win - t4_hi) * 1.5)
        alerts.append(f'Top4 集中 ({top4_win:.1f}% > {t4_hi}%)')
    elif top4_win < t4_lo:
        health -= min(15, (t4_lo - top4_win))

    # Check entropy
    e_lo, e_hi = BENCHMARKS['entropy_range']
    if norm_entropy < e_lo:
        health -= min(20, (e_lo - norm_entropy) * 50)
        alerts.append(f'Entropy 過低 ({norm_entropy:.2f} < {e_lo})')

    # Check bottom half
    bh_lo, bh_hi = BENCHMARKS['bottom_half_range']
    if bottom_half_win < bh_lo:
        health -= min(15, (bh_lo - bottom_half_win))
        alerts.append(f'Bottom50 機會不足 ({bottom_half_win:.1f}% < {bh_lo}%)')

    # Check last horse
    if last_win < BENCHMARKS['last_horse_min']:
        health -= 5
        alerts.append(f'尾馬勝率異常低 ({last_win:.1f}%)')

    health = max(0, min(100, health))

    return {
        'n_horses': n_horses,
        'distance': distance,
        'is_straight': is_straight,
        'engine': engine,
        'top1': round(top1_win, 1),
        'top2': round(top2_win, 1),
        'top3': round(top3_win, 1),
        'top4': round(top4_win, 1),
        'bottom_half': round(bottom_half_win, 1),
        'last': round(last_win, 1),
        'entropy': round(norm_entropy, 3),
        'gini': round(gini, 3),
        'hhi': round(hhi, 1),
        'health': round(health),
        'alerts': alerts,
        'top1_name': sorted_r[0][0] if sorted_r else '?',
    }


def auto_discover_meetings(base_dir: str = '.') -> list:
    """Find all meeting directories containing MC result files."""
    meetings = []
    for item in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, item)
        if os.path.isdir(path):
            mc_files = glob.glob(os.path.join(path, 'Race_*_MC_Results.json'))
            if mc_files:
                meetings.append(item)
    return meetings


def grade_health(health: int) -> str:
    """Convert health score to emoji grade."""
    if health >= 90:
        return '🟢 A+'
    elif health >= 80:
        return '🟢 A'
    elif health >= 70:
        return '🟡 B'
    elif health >= 55:
        return '🟠 C'
    else:
        return '🔴 D'


def audit_meeting(meeting_dir: str) -> dict:
    """Run full audit on a single meeting directory."""
    files = sorted(glob.glob(os.path.join(meeting_dir, 'Race_*_MC_Results.json')))
    if not files:
        return {'meeting': meeting_dir, 'races': [], 'summary': {}}

    race_stats = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        stats = calc_race_stats(data)
        if not stats:
            continue

        race_name = os.path.basename(f).replace('_MC_Results.json', '')
        stats['race'] = race_name
        stats['file'] = f
        race_stats.append(stats)

    if not race_stats:
        return {'meeting': meeting_dir, 'races': [], 'summary': {}}

    # Calculate meeting averages
    n = len(race_stats)
    summary = {
        'total_races': n,
        'avg_top1': round(sum(s['top1'] for s in race_stats) / n, 1),
        'avg_top4': round(sum(s['top4'] for s in race_stats) / n, 1),
        'avg_bottom_half': round(sum(s['bottom_half'] for s in race_stats) / n, 1),
        'avg_entropy': round(sum(s['entropy'] for s in race_stats) / n, 3),
        'avg_gini': round(sum(s['gini'] for s in race_stats) / n, 3),
        'avg_health': round(sum(s['health'] for s in race_stats) / n),
        'min_health': min(s['health'] for s in race_stats),
        'max_health': max(s['health'] for s in race_stats),
        'problem_races': sum(1 for s in race_stats if s['health'] < 70),
    }
    summary['grade'] = grade_health(summary['avg_health'])

    return {
        'meeting': meeting_dir,
        'races': race_stats,
        'summary': summary,
    }


def print_meeting_report(audit: dict):
    """Print formatted audit report for a meeting."""
    meeting = audit['meeting']
    races = audit['races']
    summary = audit['summary']

    if not races:
        print(f"\n⚠️ {meeting}: 無 MC 結果文件")
        return

    sep = "═" * 68
    print(f"\n{sep}")
    print(f"  📊 MC 品質儀表板 — {meeting}")
    print(f"  引擎: {races[0].get('engine', '?')} | 場次: {summary['total_races']}")
    print(f"{sep}\n")

    # Header
    print(f"{'Race':<10} {'H':>3} {'Dist':>5} {'Top1%':>6} {'Top4%':>6} "
          f"{'Bot50%':>7} {'Entropy':>8} {'Health':>7} {'Grade':<8} {'Alert'}")
    print("─" * 90)

    for s in races:
        grade = grade_health(s['health'])
        alert_str = ' | '.join(s['alerts'][:2]) if s['alerts'] else '—'
        straight = 'S' if s['is_straight'] else ''
        print(f"{s['race']:<10} {s['n_horses']:>3} {s['distance']:>4}{straight} "
              f"{s['top1']:>5.1f}% {s['top4']:>5.1f}% {s['bottom_half']:>6.1f}% "
              f"{s['entropy']:>7.3f} {s['health']:>6} {grade:<8} {alert_str}")

    # Meeting summary
    print(f"\n{'─' * 90}")
    print(f"  📈 會議平均:")
    print(f"     Top1={summary['avg_top1']:.1f}% | Top4={summary['avg_top4']:.1f}% | "
          f"Bot50={summary['avg_bottom_half']:.1f}%")
    print(f"     Entropy={summary['avg_entropy']:.3f} | Gini={summary['avg_gini']:.3f} | "
          f"Health={summary['avg_health']} {summary['grade']}")

    if summary['problem_races'] > 0:
        print(f"     ⚠️ {summary['problem_races']}/{summary['total_races']} 場次低於健康閾值 (< 70)")

    # Benchmark comparison
    print(f"\n  📋 HKJC Benchmark:")
    t4 = summary['avg_top4']
    t4_lo, t4_hi = BENCHMARKS['top4_range']
    if t4_lo <= t4 <= t4_hi:
        print(f"     ✅ Top4 {t4:.1f}% 在目標範圍內 ({t4_lo}-{t4_hi}%)")
    elif t4 > t4_hi:
        print(f"     ❌ Top4 {t4:.1f}% 過度集中 (目標 {t4_lo}-{t4_hi}%)")
    else:
        print(f"     ⚠️ Top4 {t4:.1f}% 偏低 (目標 {t4_lo}-{t4_hi}%)")

    e = summary['avg_entropy']
    e_lo, e_hi = BENCHMARKS['entropy_range']
    if e_lo <= e <= e_hi:
        print(f"     ✅ Entropy {e:.3f} 在目標範圍內 ({e_lo}-{e_hi})")
    elif e < e_lo:
        print(f"     ❌ Entropy {e:.3f} 過低 — 概率分佈過度集中 (目標 {e_lo}-{e_hi})")
    else:
        print(f"     ⚠️ Entropy {e:.3f} 偏高 — 區分度不足 (目標 {e_lo}-{e_hi})")


def main():
    parser = argparse.ArgumentParser(description='MC Quality Dashboard V2')
    parser.add_argument('meeting', nargs='?', help='Specific meeting directory to audit')
    parser.add_argument('--report', help='Save JSON audit report to this path')
    parser.add_argument('--all', action='store_true', help='Scan all meetings')
    args = parser.parse_args()

    if args.meeting:
        meetings = [args.meeting]
    else:
        meetings = auto_discover_meetings()
        if not meetings:
            print("❌ 無法找到任何含 MC 結果嘅賽日目錄")
            sys.exit(1)

    all_audits = []
    for m in meetings:
        audit = audit_meeting(m)
        print_meeting_report(audit)
        all_audits.append(audit)

    # Cross-meeting comparison (if multiple)
    if len(all_audits) > 1:
        print(f"\n{'═' * 68}")
        print(f"  📊 跨賽日比較")
        print(f"{'═' * 68}")
        for a in all_audits:
            s = a.get('summary', {})
            if s:
                print(f"  {a['meeting']:<35} Health={s.get('avg_health', '?'):>3} "
                      f"{s.get('grade', '?'):<8} "
                      f"Top4={s.get('avg_top4', 0):.1f}% "
                      f"Entropy={s.get('avg_entropy', 0):.3f}")

    # Save report
    if args.report:
        report = {
            'meetings': [{
                'name': a['meeting'],
                'summary': a['summary'],
                'races': a['races'],
            } for a in all_audits]
        }
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 審計報告已儲存至: {args.report}")


if __name__ == '__main__':
    main()
