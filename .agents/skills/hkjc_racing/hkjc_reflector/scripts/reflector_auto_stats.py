import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
reflector_auto_stats.py — Wong Choi 覆盤自動化命中率統計

自動比對 Analysis.md (預測) 同 Results (賽果)，
計算 Reflector Step 4a 所需嘅全部命中率指標。

Usage:
  python reflector_auto_stats.py <analysis_dir> <results_file>
  python reflector_auto_stats.py <analysis_dir> <results_file> --json

Supports both AU and HKJC formats.

Exit codes:
  0 = Success
  1 = Below target thresholds
  2 = File not found
"""
import sys, io, re, json, os, pathlib, argparse, csv
from dataclasses import dataclass, field, asdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Regex patterns
# ──────────────────────────────────────────────

# Top 3/4 picks from Verdict section
# Matches: 🥇 #4 Don Valiente  or  🥇 **#4 Don Valiente**
PICK_RE = re.compile(
    r'([🥇🥈🥉🏅])\s*\*?\*?\s*#?(\d+)\s+(.+?)(?:\*\*|\s*[—\-|])',
    re.UNICODE
)

# Alternative pick format: 1. #4 Name or Pick 1: #4 Name
PICK_ALT_RE = re.compile(
    r'(?:Top\s*|Pick\s*)(\d+)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[—\-|（(]|$)',
    re.UNICODE | re.MULTILINE
)

AUTO_PICK_RE = re.compile(
    r'\*\*第\s*([1-4])\s*選\*\*.*?'
    r'\*\*馬號及馬名:\*\*\s*\[(\d+)\]\s*([^\n]+)',
    re.UNICODE | re.DOTALL
)

# Final grade line to get horse number → grade mapping
GRADE_RE = re.compile(
    r'⭐\s*\*?\*?最終評級[：:]?\*?\*?\s*[`\s\[]*([SABCDF][+\-]?)',
    re.UNICODE
)

# Horse header to get horse number
HORSE_HEADER_RE = re.compile(
    r'(?:'
    r'###?\s*【No\.?\s*(\d+)】'
    r'|'
    r'\*\*【No\.?\s*(\d+)】'
    r'|'
    r'\*\*\[?\s*(\d+)\]?\s+'
    r'|'
    r'###\s+(\d+)\s+'
    r')',
    re.MULTILINE
)

# Results patterns — AU format (from extract_race_result.py output)
# Matches: 1st: #4 Name (Jockey) — or variations
RESULT_RE = re.compile(
    r'(?:(\d+)(?:st|nd|rd|th)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|'
    r'(?:第(\d+)名[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))',
    re.UNICODE | re.MULTILINE
)

# Results table format: | 1 | #4 | Name | ...
RESULT_TABLE_RE = re.compile(
    r'\|\s*(\d+)\s*\|\s*#?(\d+)\s*\|\s*(.+?)\s*\|',
    re.UNICODE
)


@dataclass
class RaceStats:
    race_num: int
    # Predictions
    top_picks: list = field(default_factory=list)  # [(rank, horse_num, name), ...]
    horse_grades: dict = field(default_factory=dict)  # {horse_num: grade}
    # Actual results
    actual_top3: list = field(default_factory=list)  # [(pos, horse_num, name), ...]
    # Computed stats
    gold_standard: bool = False  # Top 3 picks ALL in actual top 3
    good_result: bool = False    # Top 1 + Top 2 both in actual top 3
    min_threshold: bool = False  # ≥2 of Top 3 picks in actual top 3
    single_hit: bool = False     # ≥1 of Top 3 picks in actual top 3
    champion_hit: bool = False   # Top 1 pick = actual 1st
    top3_has_champ: bool = False # Any of Top 3 picks = actual 1st
    pick34_beat_12: bool = False # Pick 3/4 actual rank better than Pick 1/2
    # False positive/negative
    false_positives: list = field(default_factory=list)
    false_negatives: list = field(default_factory=list)


def parse_picks_from_analysis(text: str) -> list:
    """Extract Top 3/4 picks from analysis verdict section."""
    picks = []
    
    # Try emoji-based picks first (🥇🥈🥉🏅)
    emoji_map = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    for match in PICK_RE.finditer(text):
        emoji = match.group(1)
        rank = emoji_map.get(emoji, len(picks) + 1)
        num = int(match.group(2))
        name = match.group(3).strip().rstrip('*').strip()
        picks.append((rank, num, name))
    
    if not picks:
        # HKJC Auto report format:
        # **第1選**
        # - **馬號及馬名:** [7] 極速神影
        for match in AUTO_PICK_RE.finditer(text):
            rank = int(match.group(1))
            num = int(match.group(2))
            name = match.group(3).strip()
            picks.append((rank, num, name))

    if not picks:
        # Try alternative format
        for match in PICK_ALT_RE.finditer(text):
            rank = int(match.group(1))
            num = int(match.group(2))
            name = match.group(3).strip()
            picks.append((rank, num, name))
    
    # Sort by rank and deduplicate
    picks.sort(key=lambda x: x[0])
    seen = set()
    unique = []
    for p in picks:
        if p[1] not in seen:
            seen.add(p[1])
            unique.append(p)
    
    return unique[:4]  # Top 4 max


def parse_grades(text: str) -> dict:
    """Extract horse_number → grade mapping from analysis."""
    grades = {}
    horses = list(HORSE_HEADER_RE.finditer(text))
    
    for i, h in enumerate(horses):
        num = h.group(1) or h.group(2) or h.group(3) or h.group(4)
        if not num:
            continue
        num = int(num)
        
        # Get text block for this horse
        start = h.start()
        end = horses[i + 1].start() if i + 1 < len(horses) else len(text)
        block = text[start:end]
        
        grade_match = GRADE_RE.search(block)
        if grade_match:
            grades[num] = grade_match.group(1)
    
    return grades


def parse_results(text: str) -> list:
    """Extract actual race results (top 3 finishers)."""
    results = []
    
    # Try standard format
    for match in RESULT_RE.finditer(text):
        pos = match.group(1) or match.group(4)
        num = match.group(2) or match.group(5)
        name = match.group(3) or match.group(6)
        if pos and num:
            results.append((int(pos), int(num), name.strip() if name else ''))
    
    if not results:
        # Try table format
        for match in RESULT_TABLE_RE.finditer(text):
            pos = int(match.group(1))
            num = int(match.group(2))
            name = match.group(3).strip()
            if pos <= 4:
                results.append((pos, num, name))
    
    deduped = {}
    for pos, num, name in results:
        deduped.setdefault(pos, (pos, num, name))
    results = sorted(deduped.values(), key=lambda x: x[0])
    return results[:4]  # Top 4


def parse_results_file(results_file: str) -> dict:
    """Parse HKJC/AU results from extractor JSON or Markdown/text."""
    path = pathlib.Path(results_file)
    if path.suffix.lower() == ".json":
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        race_results = {}
        if isinstance(data.get("results"), dict):
            for race_key, rows_data in data["results"].items():
                try:
                    race_num = int(race_key)
                except (TypeError, ValueError):
                    continue
                rows = []
                for item in rows_data:
                    try:
                        pos = int(item.get("finish_position"))
                        num = int(item.get("competitor_number"))
                    except (TypeError, ValueError):
                        continue
                    if pos <= 0 or item.get("is_scratched"):
                        continue
                    rows.append((pos, num, str(item.get("horse_name", "")).strip()))
                rows.sort(key=lambda x: x[0])
                if rows:
                    race_results[race_num] = rows[:4]
            if race_results:
                return race_results

        for race_key, race_data in data.items():
            try:
                race_num = int(race_key)
            except (TypeError, ValueError):
                continue
            rows = []
            for item in race_data.get("results", []):
                try:
                    pos = int(item.get("pos"))
                    num = int(item.get("horse_no"))
                except (TypeError, ValueError):
                    continue
                rows.append((pos, num, str(item.get("horse_name", "")).strip()))
            rows.sort(key=lambda x: x[0])
            if rows:
                race_results[race_num] = rows[:4]
        return race_results

    with open(path, 'r', encoding='utf-8') as f:
        results_text = f.read()

    race_results = {}
    current_race = None
    current_lines = []
    header_re = re.compile(r'^##\s*(?:第\s*)?(\d+)\s*場|^##\s*Race\s*(\d+)', re.UNICODE)

    def flush_section():
        if current_race is None:
            return
        res = parse_results('\n'.join(current_lines))
        if res:
            race_results[current_race] = res

    for line in results_text.splitlines():
        match = header_re.search(line)
        if match:
            flush_section()
            current_race = int(match.group(1) or match.group(2))
            current_lines = []
            continue
        if current_race is not None:
            current_lines.append(line)
    flush_section()

    if not race_results:
        all_results = parse_results(results_text)
        if all_results:
            race_results[1] = all_results
    return race_results


def parse_results_json(results_file: str) -> dict:
    """Backward-compatible helper for AU review scripts."""
    return parse_results_file(results_file)


def load_auto_scoring_predictions(analysis_dir: str) -> dict:
    """Read meeting-level or per-race auto scoring CSV predictions."""
    root = pathlib.Path(analysis_dir)
    csv_paths = []
    for candidate in (root / "HKJC_Auto_Scoring.csv", root / "Meeting_Auto_Scoring.csv"):
        if candidate.is_file():
            csv_paths.append(candidate)
    if not csv_paths:
        csv_paths = sorted(root.glob("Race_*_Auto_Scoring.csv"))
    if not csv_paths:
        return {}

    by_race = {}
    for csv_path in csv_paths:
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                try:
                    race_num = int(float(row.get("race_number", "")))
                    horse_num = int(float(row.get("horse_number", "")))
                except ValueError:
                    continue
                name = row.get("horse_name", "").strip()
                grade = row.get("grade", "").strip()
                try:
                    rank = int(float(row.get("rank", "")))
                except ValueError:
                    rank = 999
                try:
                    ability = float(row.get("rank_score", row.get("ability_score", 0)) or 0)
                except ValueError:
                    ability = 0.0
                by_race.setdefault(race_num, []).append({
                    "rank": rank,
                    "horse_num": horse_num,
                    "name": name,
                    "grade": grade,
                    "ability": ability,
                })

    predictions = {}
    for race_num, rows in by_race.items():
        rows.sort(key=lambda item: (item["rank"], -item["ability"], item["horse_num"]))
        picks = [
            (idx + 1, item["horse_num"], item["name"])
            for idx, item in enumerate(rows[:4])
        ]
        grades = {item["horse_num"]: item["grade"] for item in rows if item["grade"]}
        predictions[race_num] = {"picks": picks, "grades": grades}
    return predictions


def compute_race_stats(picks: list, results: list, grades: dict) -> RaceStats:
    """Compute all hit rate metrics for a single race."""
    stats = RaceStats(race_num=0)
    stats.top_picks = picks
    stats.actual_top3 = results[:3]
    stats.horse_grades = grades
    
    if not picks or not results:
        return stats
    
    actual_top3_nums = {r[1] for r in results[:3]}
    actual_1st = results[0][1] if results else None
    
    pick_nums = [p[1] for p in picks]
    
    # Count how many of top 3 picks are in actual top 3
    hits_in_top3 = sum(1 for p in pick_nums[:3] if p in actual_top3_nums)
    
    stats.gold_standard = hits_in_top3 == 3
    stats.good_result = (len(pick_nums) >= 2 and 
                         pick_nums[0] in actual_top3_nums and 
                         pick_nums[1] in actual_top3_nums)
    stats.min_threshold = hits_in_top3 >= 2
    stats.single_hit = hits_in_top3 >= 1
    stats.champion_hit = (pick_nums[0] == actual_1st) if pick_nums else False
    stats.top3_has_champ = actual_1st in set(pick_nums[:3])
    
    # Pick 3/4 beat Pick 1/2 analysis
    if len(picks) >= 3:
        # Get actual positions for each pick
        actual_pos = {}
        for pos, num, _ in results:
            actual_pos[num] = pos
        
        pick1_pos = actual_pos.get(pick_nums[0], 99)
        pick2_pos = actual_pos.get(pick_nums[1], 99) if len(pick_nums) > 1 else 99
        pick3_pos = actual_pos.get(pick_nums[2], 99) if len(pick_nums) > 2 else 99
        pick4_pos = actual_pos.get(pick_nums[3], 99) if len(pick_nums) > 3 else 99
        
        best_12 = min(pick1_pos, pick2_pos)
        best_34 = min(pick3_pos, pick4_pos)
        stats.pick34_beat_12 = best_34 < best_12
    
    # False Positives: A or above but not in top 3
    for pick in picks[:3]:
        rank, num, name = pick
        grade = grades.get(num, '')
        if grade in ('S', 'S-', 'A+', 'A') and num not in actual_top3_nums:
            actual_finish = next((r[0] for r in results if r[1] == num), '?')
            stats.false_positives.append({
                'horse_num': num, 'name': name, 'grade': grade,
                'actual_pos': actual_finish
            })
    
    # False Negatives: B or below but in top 3
    for pos, num, name in results[:3]:
        grade = grades.get(num, '')
        if grade and grade not in ('S', 'S-', 'A+', 'A', 'A-'):
            if num not in set(p[1] for p in picks[:3]):
                stats.false_negatives.append({
                    'horse_num': num, 'name': name, 'grade': grade,
                    'actual_pos': pos
                })
    
    return stats


def find_analysis_files(analysis_dir: str) -> list:
    """Find all analysis .md files in directory."""
    p = pathlib.Path(analysis_dir)
    files = sorted(p.glob('*Analysis*.md'))
    if not files:
        files = sorted(p.glob('*analysis*.md'))
    return files


def extract_race_num(filename: str) -> int:
    """Extract race number from filename."""
    match = re.search(r'[Rr]ace[_\s]*(\d+)', filename)
    if match:
        return int(match.group(1))
    match = re.search(r'(\d+)', filename)
    return int(match.group(1)) if match else 0


def run_stats(analysis_dir: str, results_file: str) -> dict:
    """Run full statistics computation."""
    race_results = parse_results_file(results_file)
    csv_predictions = load_auto_scoring_predictions(analysis_dir)

    # Parse each analysis file
    analysis_files = [] if csv_predictions else find_analysis_files(analysis_dir)
    all_stats = []

    if csv_predictions:
        prediction_items = sorted(csv_predictions.items())
    else:
        prediction_items = []
        for af in analysis_files:
            race_num = extract_race_num(af.name)
            with open(af, 'r', encoding='utf-8') as f:
                analysis_text = f.read()
            picks = parse_picks_from_analysis(analysis_text)
            if picks:
                prediction_items.append((race_num, {
                    "picks": picks,
                    "grades": parse_grades(analysis_text),
                }))

    for race_num, prediction in prediction_items:
        picks = prediction["picks"]
        grades = prediction["grades"]
        results = race_results.get(race_num, [])
        stats = compute_race_stats(picks, results, grades)
        stats.race_num = race_num
        all_stats.append(stats)
    
    # Aggregate
    total = len(all_stats)
    if total == 0:
        return {'error': 'No races with picks found', 'races': []}
    
    gold_count = sum(1 for s in all_stats if s.gold_standard)
    good_count = sum(1 for s in all_stats if s.good_result)
    min_count = sum(1 for s in all_stats if s.min_threshold)
    single_count = sum(1 for s in all_stats if s.single_hit)
    champ_count = sum(1 for s in all_stats if s.champion_hit)
    top3_champ = sum(1 for s in all_stats if s.top3_has_champ)
    order_issues = sum(1 for s in all_stats if s.pick34_beat_12)
    
    all_fp = []
    all_fn = []
    for s in all_stats:
        for fp in s.false_positives:
            fp['race'] = s.race_num
            all_fp.append(fp)
        for fn in s.false_negatives:
            fn['race'] = s.race_num
            all_fn.append(fn)
    
    summary = {
        'total_races': total,
        'position_hit_rates': {
            'gold_standard': {'count': gold_count, 'rate': round(gold_count/total*100, 1), 'target': 30},
            'good_result': {'count': good_count, 'rate': round(good_count/total*100, 1), 'target': 40},
            'min_threshold': {'count': min_count, 'rate': round(min_count/total*100, 1), 'target': 60},
            'single_hit': {'count': single_count, 'rate': round(single_count/total*100, 1), 'target': 80},
        },
        'champion_hit_rates': {
            'top1_champion': {'count': champ_count, 'rate': round(champ_count/total*100, 1)},
            'top3_has_champion': {'count': top3_champ, 'rate': round(top3_champ/total*100, 1)},
        },
        'ranking_order': {
            'pick34_beat_12': {'count': order_issues, 'rate': round(order_issues/total*100, 1), 'target_max': 30},
        },
        'false_positives': all_fp,
        'false_negatives': all_fn,
    }
    
    return {
        'summary': summary,
        'races': [asdict(s) for s in all_stats],
    }


def print_report(report: dict):
    """Print formatted stats report."""
    s = report['summary']
    t = s['total_races']
    
    print(f"\n{'=' * 65}")
    print(f"📊 reflector_auto_stats.py — 覆盤命中率自動統計")
    print(f"   場次: {t}")
    print(f"\n   🔴 位置命中率 (最重要 KPI)")
    
    for key, label in [
        ('gold_standard', '🏆 黃金標準 (Top3 全入前三)'),
        ('good_result', '✅ 良好結果 (Top1+2 同入前三)'),
        ('min_threshold', '⚠️ 最低門檻 (Top3 中≥2入前三)'),
        ('single_hit', '📍 單入位率 (Top3 中≥1入前三)'),
    ]:
        d = s['position_hit_rates'][key]
        target = d.get('target', '')
        hit = '✅' if target and d['rate'] >= target else '❌' if target else ''
        print(f"   {label}: {d['count']}/{t} ({d['rate']}%) "
              f"{'[目標≥'+str(target)+'%] '+hit if target else ''}")
    
    print(f"\n   冠軍命中率（次要）")
    ch = s['champion_hit_rates']
    print(f"   Top 1 命中率: {ch['top1_champion']['count']}/{t} ({ch['top1_champion']['rate']}%)")
    print(f"   Top 3 含冠軍: {ch['top3_has_champion']['count']}/{t} ({ch['top3_has_champion']['rate']}%)")
    
    ro = s['ranking_order']['pick34_beat_12']
    order_ok = '✅' if ro['rate'] <= ro['target_max'] else '❌'
    print(f"\n   排名順序偏差 (Pick3/4 超越 Pick1/2): {ro['count']}/{t} "
          f"({ro['rate']}%) [目標≤{ro['target_max']}%] {order_ok}")
    
    if s['false_positives']:
        print(f"\n   🔴 False Positives ({len(s['false_positives'])})")
        for fp in s['false_positives']:
            print(f"      R{fp['race']} #{fp['horse_num']} {fp.get('name','')} "
                  f"[{fp['grade']}] → 實際第{fp['actual_pos']}名")
    
    if s['false_negatives']:
        print(f"\n   🟢 False Negatives ({len(s['false_negatives'])})")
        for fn in s['false_negatives']:
            print(f"      R{fn['race']} #{fn['horse_num']} {fn.get('name','')} "
                  f"[{fn['grade']}] → 實際第{fn['actual_pos']}名")
    
    print(f"\n{'=' * 65}")


def main():
    parser = argparse.ArgumentParser(
        description='Wong Choi 覆盤命中率自動統計'
    )
    parser.add_argument('analysis_dir', help='Directory containing Analysis.md files')
    parser.add_argument('results_file', help='Race results file (.md or .txt)')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()
    
    if not os.path.isdir(args.analysis_dir):
        print(f'Error: {args.analysis_dir} is not a directory')
        sys.exit(2)
    if not os.path.isfile(args.results_file):
        print(f'Error: {args.results_file} not found')
        sys.exit(2)
    
    report = run_stats(args.analysis_dir, args.results_file)
    
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if 'error' in report:
            print(f"Error: {report['error']}")
            sys.exit(2)
        print_report(report)
    
    # Exit 1 if below minimum threshold target
    if report.get('summary', {}).get('position_hit_rates', {}).get('min_threshold', {}).get('rate', 0) < 60:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
