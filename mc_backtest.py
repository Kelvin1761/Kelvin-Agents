#!/usr/bin/env python3
"""
mc_backtest.py — Historical Backtest for MC Simulator V2/V3
Compares MC predictions against actual race results across all archived meetings.

Usage:
  python3 mc_backtest.py                    # Run backtest on all available data
  python3 mc_backtest.py --re-simulate      # Re-run MC with current engine before comparing
"""
import os, sys, re, json, glob, argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Result Parsers
# ============================================================

def parse_hkjc_result(filepath):
    """Parse HKJC result .md file. Returns ordered list of (horse_name, horse_num, finish_pos, odds)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    results = []
    # Match table rows: | 名次 | 馬號 | 馬名 | ... | 賠率 |
    for line in content.split('\n'):
        line = line.strip()
        if not line.startswith('|'):
            continue
        cols = [c.strip() for c in line.split('|')]
        if len(cols) < 5:
            continue
        try:
            finish = int(cols[1])
            horse_num = int(cols[2])
            horse_name = cols[3].split('(')[0].strip()  # Remove code like (J058)
            odds = None
            try:
                odds = float(cols[-2])
            except (ValueError, IndexError):
                pass
            results.append({
                'finish': finish,
                'horse_num': horse_num,
                'horse_name': horse_name,
                'odds': odds,
            })
        except (ValueError, IndexError):
            continue
    
    return sorted(results, key=lambda x: x['finish'])


def parse_au_result(filepath):
    """Parse AU result .txt file. Returns ordered list of results."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    results = []
    # Format: [1] 5. Compensation (3)
    #         J: Rachel King | T: Bjorn Baker | Wt: 58.5kg | SP: $3.1
    for m in re.finditer(r'\[(\d+)\]\s+(\d+)\.\s+(.+?)\s*\((\d+)\)', content):
        finish = int(m.group(1))
        horse_num = int(m.group(2))
        horse_name = m.group(3).strip()
        barrier = int(m.group(4))
        
        # Try to get SP odds from next line
        odds = None
        sp_match = re.search(rf'\[{finish}\].*?SP:\s*\$?([\d.]+)', content[m.start():m.start()+300])
        if sp_match:
            try:
                odds = float(sp_match.group(1))
            except ValueError:
                pass
        
        results.append({
            'finish': finish,
            'horse_num': horse_num,
            'horse_name': horse_name,
            'odds': odds,
        })
    
    return sorted(results, key=lambda x: x['finish'])


# ============================================================
# MC Result Loader
# ============================================================

def load_mc_results(filepath):
    """Load MC results JSON and extract top4 + win probabilities."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return {
        'top4': data.get('top4_matrix', []),
        'top6': data.get('top6_matrix', []),
        'win_probs': data.get('win_probabilities', {}),
        'results': data.get('results', {}),
        'concordance': data.get('concordance', {}),
        'engine_version': data.get('engine_version', 'unknown'),
    }


# ============================================================
# Scoring
# ============================================================

def score_race(mc_data, actual_results, logic_data=None):
    """Score a single race: MC predictions vs actual results."""
    if not actual_results or not mc_data.get('top4'):
        return None
    
    mc_top4 = mc_data['top4']
    mc_top6 = mc_data.get('top6', mc_top4)
    
    # Get actual top 4 names
    actual_top4_names = [r['horse_name'] for r in actual_results[:4]]
    actual_winner = actual_results[0]['horse_name'] if actual_results else None
    actual_top3_names = [r['horse_name'] for r in actual_results[:3]]
    
    # Also check Logic verdict top4
    logic_top4 = []
    if logic_data:
        verdict = logic_data.get('race_analysis', {}).get('verdict', {})
        if isinstance(verdict, dict):
            for h in verdict.get('top4', []):
                logic_top4.append(h.get('horse_name', ''))
    
    # Scoring metrics
    score = {
        # Winner prediction
        'mc_top1_is_winner': actual_winner in mc_top4[:1],
        'mc_top2_has_winner': actual_winner in mc_top4[:2],
        'mc_top4_has_winner': actual_winner in mc_top4,
        'mc_top6_has_winner': actual_winner in mc_top6,
        
        # Top 3 overlap
        'mc_top4_in_actual_top3': len(set(mc_top4) & set(actual_top3_names)),
        'mc_top4_in_actual_top4': len(set(mc_top4) & set(actual_top4_names)),
        
        # Gold standard: MC top4 == actual top4 (any order)
        'gold_standard': set(mc_top4) == set(actual_top4_names),
        
        # Exacta: MC #1 and #2 match actual 1-2
        'exacta': mc_top4[:2] == actual_top4_names[:2] if len(mc_top4) >= 2 else False,
        
        # MC top pick probability
        'mc_top1_win_prob': mc_data['win_probs'].get(mc_top4[0], 0) if mc_top4 else 0,
        
        # Actual winner's MC probability
        'actual_winner_mc_prob': mc_data['win_probs'].get(actual_winner, 0) if actual_winner else 0,
        
        # Winner's odds (for value analysis)
        'winner_odds': actual_results[0].get('odds') if actual_results else None,
        
        # Concordance
        'concordance_level': mc_data.get('concordance', {}).get('concordance_level', 'N/A'),
        
        # Details
        'mc_top4': mc_top4,
        'actual_top4': actual_top4_names,
        'actual_winner': actual_winner,
        'logic_top4': logic_top4,
    }
    
    # Logic verdict scoring (if available)
    if logic_top4:
        score['logic_top4_has_winner'] = actual_winner in logic_top4
        score['logic_top4_in_actual_top4'] = len(set(logic_top4) & set(actual_top4_names))
    
    return score


# ============================================================
# Meeting Scanner
# ============================================================

def find_backtest_meetings(base_dir):
    """Scan for meetings with both MC results and actual results."""
    meetings = []
    
    # Check all directories
    search_dirs = []
    archive_dir = os.path.join(base_dir, 'Archive_Race_Analysis')
    if os.path.isdir(archive_dir):
        search_dirs.extend([os.path.join(archive_dir, d) for d in os.listdir(archive_dir) 
                           if os.path.isdir(os.path.join(archive_dir, d))])
    
    # Active directories
    for d in os.listdir(base_dir):
        full = os.path.join(base_dir, d)
        if os.path.isdir(full) and re.match(r'2026-\d{2}-\d{2}', d):
            search_dirs.append(full)
    
    for meeting_dir in sorted(search_dirs):
        mc_files = glob.glob(os.path.join(meeting_dir, 'Race_*_MC_Results.json'))
        
        # Find result files (HKJC .md or AU .txt)
        result_files_md = glob.glob(os.path.join(meeting_dir, '*_Race_*_Results.md'))
        result_files_txt = glob.glob(os.path.join(meeting_dir, '*Race*Result*.txt'))
        
        if not mc_files:
            continue
        
        # Determine platform
        is_hkjc = bool(result_files_md) or any(k in os.path.basename(meeting_dir).lower() for k in ('shatin', 'sha_tin', 'happyvalley', 'happy_valley', '沙田', '跑馬地'))
        
        result_files = result_files_md if result_files_md else result_files_txt
        if not result_files:
            continue
        
        # Match MC results to actual results by race number
        races = []
        for mc_file in sorted(mc_files):
            mc_match = re.search(r'Race_(\d+)_MC_Results', os.path.basename(mc_file))
            if not mc_match:
                continue
            race_num = int(mc_match.group(1))
            
            # Find matching result file
            matched_result = None
            for rf in result_files:
                if re.search(rf'Race[_ ]{race_num}[_ ]Result', os.path.basename(rf)):
                    matched_result = rf
                    break
                # Also try non-standard naming
                if re.search(rf'Race_{race_num}_Results', os.path.basename(rf)):
                    matched_result = rf
                    break
            
            # Find Logic.json
            logic_file = os.path.join(meeting_dir, f'Race_{race_num}_Logic.json')
            
            if matched_result:
                races.append({
                    'race_num': race_num,
                    'mc_file': mc_file,
                    'result_file': matched_result,
                    'logic_file': logic_file if os.path.exists(logic_file) else None,
                    'platform': 'hkjc' if is_hkjc else 'au',
                })
        
        if races:
            meetings.append({
                'name': os.path.basename(meeting_dir),
                'dir': meeting_dir,
                'races': races,
                'platform': 'hkjc' if is_hkjc else 'au',
            })
    
    return meetings


# ============================================================
# Main Backtest
# ============================================================

def run_backtest(base_dir, re_simulate=False):
    """Run full backtest across all available meetings."""
    meetings = find_backtest_meetings(base_dir)
    
    if not meetings:
        print("❌ 無法找到同時有 MC Results 同實際賽果嘅賽事目錄")
        return
    
    all_scores = []
    meeting_summaries = []
    
    print(f"\n{'═' * 80}")
    print(f"📊 MC HISTORICAL BACKTEST")
    print(f"{'═' * 80}")
    print(f"找到 {len(meetings)} 個賽日，共 {sum(len(m['races']) for m in meetings)} 場賽事\n")
    
    for meeting in meetings:
        m_scores = []
        print(f"\n{'─' * 60}")
        print(f"🏇 {meeting['name']} ({meeting['platform'].upper()}) — {len(meeting['races'])} 場")
        print(f"{'─' * 60}")
        
        for race in meeting['races']:
            # Load MC results
            mc_data = load_mc_results(race['mc_file'])
            
            # Parse actual results
            if race['platform'] == 'hkjc':
                actual = parse_hkjc_result(race['result_file'])
            else:
                actual = parse_au_result(race['result_file'])
            
            if not actual:
                print(f"  Race {race['race_num']}: ⚠️ 無法解析賽果")
                continue
            
            # Load logic data if available
            logic_data = None
            if race.get('logic_file'):
                try:
                    with open(race['logic_file'], 'r', encoding='utf-8') as f:
                        logic_data = json.load(f)
                except Exception:
                    pass
            
            # Re-simulate if requested
            if re_simulate and race.get('logic_file'):
                try:
                    from mc_simulator import process_race
                    new_mc = process_race(race['logic_file'], platform=race['platform'])
                    mc_data = {
                        'top4': new_mc.get('top4_matrix', []),
                        'top6': new_mc.get('top6_matrix', []),
                        'win_probs': new_mc.get('win_probabilities', {}),
                        'results': new_mc.get('results', {}),
                        'concordance': new_mc.get('concordance', {}),
                        'engine_version': new_mc.get('engine_version', 'v3_resim'),
                    }
                except Exception as e:
                    print(f"  Race {race['race_num']}: ⚠️ Re-simulation failed: {e}")
            
            # Score
            score = score_race(mc_data, actual, logic_data)
            if score:
                score['race_num'] = race['race_num']
                score['meeting'] = meeting['name']
                score['platform'] = race['platform']
                m_scores.append(score)
                all_scores.append(score)
                
                # Print race result
                winner_hit = "✅" if score['mc_top4_has_winner'] else "❌"
                overlap = score['mc_top4_in_actual_top4']
                winner = score['actual_winner']
                odds_str = f"${score['winner_odds']}" if score['winner_odds'] else "?"
                mc_prob = f"{score['actual_winner_mc_prob']:.1f}%" if score['actual_winner_mc_prob'] else "?"
                
                print(f"  Race {race['race_num']:2d}: {winner_hit} 冠軍={winner:12s} (賠率{odds_str:>6}) "
                      f"| MC概率={mc_prob:>5} | Top4重疊={overlap}/4 | "
                      f"MC={score['mc_top4']}")
        
        if m_scores:
            # Meeting summary
            total = len(m_scores)
            w_hit = sum(1 for s in m_scores if s['mc_top4_has_winner'])
            w_top2 = sum(1 for s in m_scores if s['mc_top2_has_winner'])
            avg_overlap = sum(s['mc_top4_in_actual_top4'] for s in m_scores) / total
            gold = sum(1 for s in m_scores if s['gold_standard'])
            
            summary = {
                'name': meeting['name'],
                'total': total,
                'winner_in_top4': w_hit,
                'winner_in_top2': w_top2,
                'avg_overlap': avg_overlap,
                'gold_standard': gold,
            }
            meeting_summaries.append(summary)
            
            print(f"\n  📊 小結: 冠軍命中={w_hit}/{total} ({w_hit/total*100:.0f}%) | "
                  f"Top4平均重疊={avg_overlap:.1f} | 金標準={gold}/{total}")
    
    # ── Grand Summary ──
    if all_scores:
        print(f"\n{'═' * 80}")
        print(f"📊 GRAND SUMMARY — {len(all_scores)} 場賽事")
        print(f"{'═' * 80}")
        
        total = len(all_scores)
        
        metrics = {
            'MC Top1 = 冠軍': sum(1 for s in all_scores if s['mc_top1_is_winner']),
            'MC Top2 含冠軍': sum(1 for s in all_scores if s['mc_top2_has_winner']),
            'MC Top4 含冠軍': sum(1 for s in all_scores if s['mc_top4_has_winner']),
            'MC Top6 含冠軍': sum(1 for s in all_scores if s['mc_top6_has_winner']),
            '金標準(Top4全中)': sum(1 for s in all_scores if s['gold_standard']),
            'Exacta(1-2全中)': sum(1 for s in all_scores if s['exacta']),
        }
        
        print(f"\n{'指標':25s} {'命中':>5} {'總場':>5} {'命中率':>8} {'基線':>8}")
        print(f"{'─' * 55}")
        baselines = {
            'MC Top1 = 冠軍': '~7%',
            'MC Top2 含冠軍': '~14%',
            'MC Top4 含冠軍': '~29%',
            'MC Top6 含冠軍': '~43%',
            '金標準(Top4全中)': '~0.1%',
            'Exacta(1-2全中)': '~0.5%',
        }
        for label, count in metrics.items():
            rate = count / total * 100
            baseline = baselines.get(label, '?')
            print(f"  {label:23s} {count:5d} {total:5d} {rate:7.1f}% {baseline:>8}")
        
        # Average overlap
        avg_overlap = sum(s['mc_top4_in_actual_top4'] for s in all_scores) / total
        avg_top3 = sum(s['mc_top4_in_actual_top3'] for s in all_scores) / total
        print(f"\n  MC Top4 vs 實際Top4 平均重疊: {avg_overlap:.2f}/4")
        print(f"  MC Top4 vs 實際Top3 平均重疊: {avg_top3:.2f}/3")
        
        # Winner probability analysis
        winner_probs = [s['actual_winner_mc_prob'] for s in all_scores if s['actual_winner_mc_prob']]
        if winner_probs:
            avg_prob = sum(winner_probs) / len(winner_probs)
            print(f"\n  冠軍嘅平均 MC 概率: {avg_prob:.1f}%")
        
        # By platform
        for platform in ['hkjc', 'au']:
            p_scores = [s for s in all_scores if s['platform'] == platform]
            if p_scores:
                p_total = len(p_scores)
                p_hit = sum(1 for s in p_scores if s['mc_top4_has_winner'])
                p_overlap = sum(s['mc_top4_in_actual_top4'] for s in p_scores) / p_total
                print(f"\n  [{platform.upper()}] {p_total} 場: 冠軍命中={p_hit}/{p_total} ({p_hit/p_total*100:.0f}%) | 平均重疊={p_overlap:.2f}")
        
        # Odds calibration: did we pick value winners?
        value_wins = [s for s in all_scores if s['mc_top4_has_winner'] and s.get('winner_odds') and s['winner_odds'] >= 5]
        longshot_wins = [s for s in all_scores if s['mc_top4_has_winner'] and s.get('winner_odds') and s['winner_odds'] >= 10]
        print(f"\n  MC Top4 命中 ≥$5 冠軍: {len(value_wins)}")
        print(f"  MC Top4 命中 ≥$10 冷門: {len(longshot_wins)}")
        
        print(f"\n{'═' * 80}")
        
        # Save results
        output = {
            'backtest_date': __import__('datetime').datetime.now().isoformat(),
            'total_races': total,
            'meetings': meeting_summaries,
            'grand_metrics': {k: {'count': v, 'rate': round(v/total*100, 1)} for k, v in metrics.items()},
            'avg_top4_overlap': round(avg_overlap, 2),
            'per_race': [{
                'meeting': s['meeting'], 'race': s['race_num'],
                'mc_top4': s['mc_top4'], 'actual_top4': s['actual_top4'],
                'winner_in_mc_top4': s['mc_top4_has_winner'],
                'overlap': s['mc_top4_in_actual_top4'],
                'winner_mc_prob': s.get('actual_winner_mc_prob'),
                'winner_odds': s.get('winner_odds'),
            } for s in all_scores],
        }
        
        out_path = os.path.join(base_dir, 'mc_backtest_results.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n💾 結果已儲存: {out_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MC Historical Backtest')
    parser.add_argument('--re-simulate', action='store_true', help='Re-run MC with current engine')
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    run_backtest(base_dir, re_simulate=args.re_simulate)
