"""Compare Kelvin vs Heison analysis quality metrics for the same races"""
import sys, io, os, re, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def analyze_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Count horses
    horses = len(re.findall(r'(?:^\*\*\[?\d+\]?\s|^### \d+\s)', text, re.MULTILINE))
    
    # Count section headers per horse
    sections = {
        'situation': len(re.findall(r'情境標記|📌', text)),
        'sectional': len(re.findall(r'🔬 段速法醫|🔬 段速', text)),
        'eem': len(re.findall(r'⚡ EEM', text)),
        'forgiveness': len(re.findall(r'📋 寬恕', text)),
        'form_line': len(re.findall(r'🔗 賽績線', text)),
        'matrix': len(re.findall(r'📊 評級矩陣', text)),
        'conclusion': len(re.findall(r'💡 結論|💡 評語|💡 優勢', text)),
        'final_grade': len(re.findall(r'⭐ 最終評級', text)),
    }
    
    # CSV and top picks
    has_csv = '```csv' in text
    top_picks_match = re.search(r'Top\s*(\d)', text)
    top_n = int(top_picks_match.group(1)) if top_picks_match else 0
    
    # 核心邏輯 or 結論 in analysis blocks
    core_logic = len(re.findall(r'核心邏輯', text))
    alt_conclusion = len(re.findall(r'結論[：:]', text))
    
    # Verdict format
    verdict_emojis = len(re.findall(r'🥇|🥈|🥉|🏅', text))
    
    # Word count (rough)
    word_count = len(text)
    
    return {
        'horses': horses,
        'sections': sections,
        'has_csv': has_csv,
        'top_n': top_n,
        'core_logic': core_logic,
        'alt_conclusion': alt_conclusion,
        'verdict_emojis': verdict_emojis,
        'total_chars': word_count,
    }

kelvin_dir = pathlib.Path(r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-03-29_ShaTin (Kelvin)')
heison_dir = pathlib.Path(r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-03-29_ShaTin (Heison)')

print("=" * 80)
print(f"{'Metric':<25} {'Kelvin':<35} {'Heison':<35}")
print("=" * 80)

for race_num in range(1, 12):
    k_file = kelvin_dir / f'2026-03-29_ShaTin_Race_{race_num}_Analysis.md'
    h_file = heison_dir / f'2026-03-29_ShaTin_Race_{race_num}_Analysis.md'
    
    if not k_file.exists() or not h_file.exists():
        continue
    
    k = analyze_file(k_file)
    h = analyze_file(h_file)
    
    print(f"\n--- Race {race_num} ---")
    print(f"{'Total chars':<25} {k['total_chars']:<35} {h['total_chars']}")
    print(f"{'Horses detected':<25} {k['horses']:<35} {h['horses']}")
    print(f"{'📌 Situation tags':<25} {k['sections']['situation']:<35} {h['sections']['situation']}")
    print(f"{'🔬 Sectional':<25} {k['sections']['sectional']:<35} {h['sections']['sectional']}")
    print(f"{'⚡ EEM':<25} {k['sections']['eem']:<35} {h['sections']['eem']}")
    print(f"{'📋 Forgiveness':<25} {k['sections']['forgiveness']:<35} {h['sections']['forgiveness']}")
    print(f"{'🔗 Form Line':<25} {k['sections']['form_line']:<35} {h['sections']['form_line']}")
    print(f"{'📊 Matrix':<25} {k['sections']['matrix']:<35} {h['sections']['matrix']}")
    print(f"{'💡 Conclusion':<25} {k['sections']['conclusion']:<35} {h['sections']['conclusion']}")
    print(f"{'⭐ Final Grade':<25} {k['sections']['final_grade']:<35} {h['sections']['final_grade']}")
    print(f"{'核心邏輯 count':<25} {k['core_logic']:<35} {h['core_logic']}")
    print(f"{'結論: count':<25} {k['alt_conclusion']:<35} {h['alt_conclusion']}")
    print(f"{'CSV present':<25} {k['has_csv']:<35} {h['has_csv']}")
    print(f"{'Top N picks':<25} {k['top_n']:<35} {h['top_n']}")
    print(f"{'Verdict emojis':<25} {k['verdict_emojis']:<35} {h['verdict_emojis']}")
    
    # Quality score
    k_completeness = sum(1 for v in k['sections'].values() if v >= k['horses'] * 0.8)
    h_completeness = sum(1 for v in h['sections'].values() if v >= h['horses'] * 0.8)
    print(f"{'Completeness (of 8)':<25} {k_completeness:<35} {h_completeness}")
