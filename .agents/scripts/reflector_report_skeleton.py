import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
reflector_report_skeleton.py — 覆盤報告骨架自動生成器

自動生成覆盤報告嘅完整框架，預填所有機械性數據，
LLM 只需要填入 {{LLM_FILL}} 標記嘅定性分析欄位。

Usage:
  python reflector_report_skeleton.py <analysis_dir> <results_file> --domain au|hkjc
  python reflector_report_skeleton.py <analysis_dir> <results_file> --domain au --output <path>

Supports both AU and HKJC formats via --domain flag.

Exit codes:
  0 = Success
  1 = Partial (some races missing data)
  2 = Fatal error (file not found / no data)
"""
import sys, io, re, json, os, pathlib, argparse
from dataclasses import dataclass, field
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Shared regex patterns (from reflector_auto_stats.py)
# ──────────────────────────────────────────────

PICK_RE = re.compile(
    r'([🥇🥈🥉🏅])\s*\*?\*?\s*(?:\*\*)?(?:第[一二三四]選\*\*\s*\n-\s*\*\*馬號及馬名[：:]\*\*\s*)?#?\[?(\d+)\]?\s+(.+?)(?:\*\*|\s*[—\-|]|$)',
    re.UNICODE
)
PICK_ALT_RE = re.compile(
    r'(?:Top\s*|Pick\s*)(\d+)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[—\-|（(]|$)',
    re.UNICODE | re.MULTILINE
)
GRADE_RE = re.compile(
    r'⭐\s*\*?\*?最終評級[：:]?\*?\*?\s*[`\s\[]*([SABCDF][+\-]?)',
    re.UNICODE
)
HORSE_HEADER_RE = re.compile(
    r'(?:'
    r'###?\s*【No\.?\s*(\d+)】'
    r'|'
    r'\*\*\[?\s*(\d+)\]?\s+'
    r'|'
    r'###\s+(\d+)\s+'
    r')',
    re.MULTILINE
)
RESULT_RE = re.compile(
    r'(?:(\d+)(?:st|nd|rd|th)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|'
    r'(?:第(\d+)名[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|'
    r'(?:\[(\d+)\]\s+(\d+)\.\s+(.+?)(?:\s*[\(（]|$))',
    re.UNICODE | re.MULTILINE
)
RESULT_TABLE_RE = re.compile(
    r'\|\s*(\d+)\s*\|\s*#?(\d+)\s*\|\s*(.+?)\s*\|',
    re.UNICODE
)

# ──────────────────────────────────────────────
# Data parsing (reused from auto_stats)
# ──────────────────────────────────────────────

def parse_picks(text):
    picks = []
    emoji_map = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    for m in PICK_RE.finditer(text):
        rank = emoji_map.get(m.group(1), len(picks) + 1)
        picks.append((rank, int(m.group(2)), m.group(3).strip().rstrip('*').strip()))
    if not picks:
        for m in PICK_ALT_RE.finditer(text):
            picks.append((int(m.group(1)), int(m.group(2)), m.group(3).strip()))
    picks.sort(key=lambda x: x[0])
    seen = set()
    return [p for p in picks if p[1] not in seen and not seen.add(p[1])][:4]


def parse_grades(text):
    grades = {}
    horses = list(HORSE_HEADER_RE.finditer(text))
    for i, h in enumerate(horses):
        num = h.group(1) or h.group(2) or h.group(3)
        if not num: continue
        num = int(num)
        start = h.start()
        end = horses[i+1].start() if i+1 < len(horses) else len(text)
        gm = GRADE_RE.search(text[start:end])
        if gm: grades[num] = gm.group(1)
    return grades


def parse_results(text):
    results = []
    for m in RESULT_RE.finditer(text):
        pos = m.group(1) or m.group(4) or m.group(7)
        num = m.group(2) or m.group(5) or m.group(8)
        name = m.group(3) or m.group(6) or m.group(9)
        if pos and num:
            results.append((int(pos), int(num), (name or '').strip()))
    if not results:
        for m in RESULT_TABLE_RE.finditer(text):
            if int(m.group(1)) <= 4:
                results.append((int(m.group(1)), int(m.group(2)), m.group(3).strip()))
    results.sort(key=lambda x: x[0])
    return results[:4]


def find_analysis_files(d):
    p = pathlib.Path(d)
    files = sorted(p.glob('*Analysis*.md'))
    return files or sorted(p.glob('*analysis*.md'))


def extract_race_num(fn):
    m = re.search(r'[Rr]ace[_\s]*(\d+)', fn)
    if m: return int(m.group(1))
    m = re.search(r'(\d+)', fn)
    return int(m.group(1)) if m else 0


def split_results_by_race(text):
    race_results = {}
    sections = re.split(r'(?:##?\s*(?:Race|第)\s*(\d+)|Race:\s*(\d+))', text)
    if len(sections) <= 1:
        r = parse_results(text)
        if r: race_results[1] = r
    else:
        cur = None
        for s in sections:
            if s is None:
                continue
            if s.strip().isdigit():
                cur = int(s.strip())
            elif cur is not None:
                r = parse_results(s)
                if r: race_results[cur] = r
    return race_results


# ──────────────────────────────────────────────
# Hit rate computation
# ──────────────────────────────────────────────

def compute_hits(picks, results):
    if not picks or not results:
        return {}
    actual_top3 = {r[1] for r in results[:3]}
    actual_1st = results[0][1]
    pnums = [p[1] for p in picks]
    hits = sum(1 for p in pnums[:3] if p in actual_top3)

    # Actual position lookup
    apos = {num: pos for pos, num, _ in results}
    for num in pnums:
        if num not in apos:
            apos[num] = 99

    p34_beat = False
    if len(pnums) >= 3:
        best12 = min(apos.get(pnums[0], 99), apos.get(pnums[1], 99) if len(pnums) > 1 else 99)
        best34 = min(apos.get(pnums[2], 99), apos.get(pnums[3], 99) if len(pnums) > 3 else 99)
        p34_beat = best34 < best12

    return {
        'gold': hits == 3,
        'good': len(pnums) >= 2 and pnums[0] in actual_top3 and pnums[1] in actual_top3,
        'min': hits >= 2,
        'single': hits >= 1,
        'champ': pnums[0] == actual_1st,
        'top3_champ': actual_1st in set(pnums[:3]),
        'p34_beat': p34_beat,
        'hits_count': hits,
    }


# ──────────────────────────────────────────────
# Skeleton generation
# ──────────────────────────────────────────────

def generate_skeleton(analysis_dir, results_file, domain, venue=None, date_str=None):
    # Auto-detect venue/date from directory name if not provided
    dir_name = pathlib.Path(analysis_dir).name
    if not date_str:
        dm = re.search(r'(\d{4}-\d{2}-\d{2})', dir_name)
        date_str = dm.group(1) if dm else datetime.now().strftime('%Y-%m-%d')
    if not venue:
        # Try to extract venue from dir name (after date)
        vm = re.search(r'\d{4}-\d{2}-\d{2}\s+(.+?)(?:\s+Race|\s*$)', dir_name)
        venue = vm.group(1).strip() if vm else 'Unknown'

    # Read results
    with open(results_file, 'r', encoding='utf-8') as f:
        results_text = f.read()
    race_results = split_results_by_race(results_text)

    # Read analyses
    analysis_files = find_analysis_files(analysis_dir)
    races_data = []

    for af in analysis_files:
        rn = extract_race_num(af.name)
        with open(af, 'r', encoding='utf-8') as f:
            atxt = f.read()
        picks = parse_picks(atxt)
        grades = parse_grades(atxt)
        res = race_results.get(rn, [])
        hits = compute_hits(picks, res) if res else {}

        # Determine status
        if not res:
            status = '⏳ 賽果待入'
        elif hits.get('gold'):
            status = '✅ 🏆 黃金標準'
        elif hits.get('good'):
            status = '✅ 良好結果'
        elif hits.get('min'):
            status = '⚠️ 最低門檻'
        elif hits.get('single'):
            status = '❌ 失誤（單入位）'
        else:
            status = '❌ 完全失誤'

        # False positives/negatives
        fp_list = []
        fn_list = []
        actual_top3_nums = {r[1] for r in res[:3]} if res else set()
        for p in picks[:3]:
            g = grades.get(p[1], '')
            if g in ('S', 'S-', 'A+', 'A') and p[1] not in actual_top3_nums and res:
                actual_fin = next((r[0] for r in res if r[1] == p[1]), '?')
                fp_list.append((rn, p[1], p[2], g, actual_fin))
        if res:
            for pos, num, name in res[:3]:
                g = grades.get(num, '')
                if g and g not in ('S', 'S-', 'A+', 'A', 'A-'):
                    if num not in {p[1] for p in picks[:3]}:
                        fn_list.append((rn, num, name, g, pos))

        races_data.append({
            'num': rn,
            'picks': picks,
            'grades': grades,
            'results': res,
            'hits': hits,
            'status': status,
            'fp': fp_list,
            'fn': fn_list,
        })

    # Aggregations
    total = len(races_data)
    races_with_results = [r for r in races_data if r['results']]
    tr = len(races_with_results)
    
    if tr > 0:
        gold_c = sum(1 for r in races_with_results if r['hits'].get('gold'))
        good_c = sum(1 for r in races_with_results if r['hits'].get('good'))
        min_c = sum(1 for r in races_with_results if r['hits'].get('min'))
        single_c = sum(1 for r in races_with_results if r['hits'].get('single'))
        champ_c = sum(1 for r in races_with_results if r['hits'].get('champ'))
        top3ch_c = sum(1 for r in races_with_results if r['hits'].get('top3_champ'))
        p34_c = sum(1 for r in races_with_results if r['hits'].get('p34_beat'))
    else:
        gold_c = good_c = min_c = single_c = champ_c = top3ch_c = p34_c = 0

    all_fp = [fp for r in races_data for fp in r['fp']]
    all_fn = [fn for r in races_data for fn in r['fn']]

    # ── Build skeleton markdown ──
    top_picks_label = "Top 3" if domain == 'au' else "Top 4"
    
    lines = []
    lines.append(f"# 🔍 {'AU' if domain == 'au' else 'HKJC'} 賽後覆盤報告")
    lines.append(f"**日期:** {date_str} | **馬場:** {venue} | **場次:** {total}")
    if domain == 'au':
        lines.append(f"**預測掛牌:** {{{{LLM_FILL}}}} | **實際掛牌:** {{{{LLM_FILL}}}}")
    lines.append("")

    # ── Hit rates ──
    lines.append("## 📊 整體命中率")
    lines.append("")
    lines.append("### 🔴 位置命中率（最重要 KPI）")
    lines.append("| 指標 | 數值 | 目標 | 達標? |")
    lines.append("|:---|:---|:---|:---|")
    
    def pct(n, d): return f"{round(n/d*100, 1)}%" if d > 0 else "N/A"
    def hit_icon(n, d, tgt): return '✅' if d > 0 and (n/d*100) >= tgt else '❌'
    
    lines.append(f"| 🏆 黃金標準率 (Top3 全入前三) | {gold_c}/{tr} ({pct(gold_c, tr)}) | ≥30% | {hit_icon(gold_c, tr, 30)} |")
    lines.append(f"| ✅ 良好結果率 (Top1+2 同入前三) | {good_c}/{tr} ({pct(good_c, tr)}) | ≥40% | {hit_icon(good_c, tr, 40)} |")
    lines.append(f"| ⚠️ 最低門檻率 (Top3 中≥2入前三) | {min_c}/{tr} ({pct(min_c, tr)}) | ≥60% | {hit_icon(min_c, tr, 60)} |")
    lines.append(f"| 📍 單入位率 (Top3 中≥1入前三) | {single_c}/{tr} ({pct(single_c, tr)}) | ≥80% | {hit_icon(single_c, tr, 80)} |")
    lines.append("")
    lines.append("### 冠軍命中率（次要）")
    lines.append("| 指標 | 數值 |")
    lines.append("|:---|:---|")
    lines.append(f"| Top 1 命中率 | {champ_c}/{tr} ({pct(champ_c, tr)}) |")
    lines.append(f"| {top_picks_label} 含冠軍率 | {top3ch_c}/{tr} ({pct(top3ch_c, tr)}) |")
    lines.append(f"| A級以上平均名次 | {{{{LLM_FILL}}}} |")
    lines.append(f"| B級以下平均名次 | {{{{LLM_FILL}}}} |")
    if domain == 'au':
        lines.append(f"| 場地預測準確度 | {{{{LLM_FILL}}}} |")
    lines.append("")
    
    # Ranking order
    lines.append(f"### 排名順序分析")
    lines.append(f"- Pick 3/4 超越 Pick 1/2: **{p34_c}/{tr} ({pct(p34_c, tr)})** [目標≤30%] {hit_icon(tr - p34_c, tr, 70) if tr > 0 else '?'}")
    lines.append("")

    # ── Per-race summary ──
    lines.append("## 📋 逐場覆盤摘要")
    lines.append("")
    for rd in races_data:
        lines.append(f"### 第 {rd['num']} 場 — {rd['status']}")
        if domain == 'hkjc':
            lines.append(f"**賽事規格:** {{{{LLM_FILL}}}}")
        else:
            lines.append(f"**賽事規格:** {{{{LLM_FILL}}}} [距離 / 班次 / 場地]")
        
        if rd['results']:
            res_str = ', '.join([f"#{r[1]} {r[2]}" for r in rd['results'][:3]])
            lines.append(f"**實際前三名:** {res_str}")
        else:
            lines.append(f"**實際前三名:** ⏳ 待入")
        
        if rd['picks']:
            picks_str = ', '.join([f"#{p[1]} {p[2]}" for p in rd['picks'][:3]])
            lines.append(f"**預測 {top_picks_label}:** {picks_str}")
        else:
            lines.append(f"**預測 {top_picks_label}:** ⚠ 無法解析")
        
        lines.append(f"**關鍵偏差:** {{{{LLM_FILL}}}}")
        lines.append(f"**偏差類型:** {{{{LLM_FILL}}}} [步速誤判 / EEM偏差 / 練馬師訊號遺漏 / 騎師變陣 / 場地偏差 / 寬恕錯誤 / 負重誤判]")
        lines.append("")

    # ── False Positives ──
    lines.append("## 🔴 False Positives (看高但大敗)")
    lines.append("| 場次 | 馬匹 | 預測評級 | 實際名次 | 失誤根因 |")
    lines.append("|:---|:---|:---|:---|:---|")
    if all_fp:
        for fp in all_fp:
            lines.append(f"| R{fp[0]} | #{fp[1]} {fp[2]} | {fp[3]} | 第{fp[4]}名 | {{{{LLM_FILL}}}} |")
    else:
        lines.append("| — | 無 False Positive | — | — | — |")
    lines.append("")

    # ── False Negatives ──
    lines.append("## 🟢 False Negatives (看低但勝出/上名)")
    lines.append("| 場次 | 馬匹 | 預測評級 | 實際名次 | 遺漏因素 |")
    lines.append("|:---|:---|:---|:---|:---|")
    if all_fn:
        for fn in all_fn:
            lines.append(f"| R{fn[0]} | #{fn[1]} {fn[2]} | {fn[3]} | 第{fn[4]}名 | {{{{LLM_FILL}}}} |")
    else:
        lines.append("| — | 無 False Negative | — | — | — |")
    lines.append("")

    # ── Weather (AU only) ──
    if domain == 'au':
        lines.append("## 🌤️ 場地預測覆盤")
        lines.append("- **Weather Prediction 預測:** {{LLM_FILL}}")
        lines.append("- **實際最終掛牌:** {{LLM_FILL}}")
        lines.append("- **偏差分析:** {{LLM_FILL}}")
        lines.append("- **對分析的影響:** {{LLM_FILL}}")
        lines.append("")

    # ── SIP section ──
    lines.append("## 🧠 系統性改善建議 (Systemic Improvement Proposals)")
    lines.append("")
    lines.append(f"### SIP-{date_str.replace('-','')}-01: {{{{LLM_FILL}}}}")
    lines.append("- **問題:** {{LLM_FILL}}")
    lines.append("- **證據:** {{LLM_FILL}}")
    lines.append(f"- **目標檔案:** {{{{LLM_FILL}}}}")
    lines.append("")
    lines.append("**🧠 修正方案探索（AG Kit Brainstorming — 自動觸發）:**")
    lines.append("")
    lines.append("| 方案 | 修改內容 | ✅ Pros | ❌ Cons | 📊 Effort |")
    lines.append("|:---|:---|:---|:---|:---|")
    lines.append("| A | {{LLM_FILL}} | {{LLM_FILL}} | {{LLM_FILL}} | {{LLM_FILL}} |")
    lines.append("| B | {{LLM_FILL}} | {{LLM_FILL}} | {{LLM_FILL}} | {{LLM_FILL}} |")
    lines.append("")
    lines.append("**💡 Recommendation:** {{LLM_FILL}}")
    lines.append("- **影響範圍:** {{LLM_FILL}}")
    lines.append("")

    # ── Narrative Post-Mortem ──
    lines.append("## 🎭 敘事覆盤 (Narrative Post-Mortem)")
    lines.append("")
    if domain == 'hkjc':
        lines.append("| 場次 | 馬匹 | 預測評級 | 實際名次 | 沿途走位 | 分段時間摘要 | 競賽事件報告 | 裁定 | 證據 |")
        lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|:---|")
    else:
        lines.append("| 場次 | 馬匹 | 預測評級 | 實際名次 | 沿途走勢摘要 | Stewards' Report | 裁定 | 證據 |")
        lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|")
    
    # Pre-fill rows for failed picks
    for rd in races_data:
        if not rd['results']: continue
        actual_top3_nums = {r[1] for r in rd['results'][:3]}
        for p in rd['picks'][:3]:
            if p[1] not in actual_top3_nums:
                g = rd['grades'].get(p[1], '?')
                apos = next((r[0] for r in rd['results'] if r[1] == p[1]), '?')
                if domain == 'hkjc':
                    lines.append(f"| R{rd['num']} | #{p[1]} {p[2]} | {g} | {apos} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} |")
                else:
                    lines.append(f"| R{rd['num']} | #{p[1]} {p[2]} | {g} | {apos} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} |")
    
    lines.append("")
    lines.append("### 裁定統計")
    lines.append("- 🟢 可寬恕 (Bad Luck): {{LLM_FILL}} 匹")
    lines.append("- 🔴 邏輯錯誤 (Bad Logic): {{LLM_FILL}} 匹 → 對應 SIP: {{LLM_FILL}}")
    lines.append("- 🟡 可避免陷阱 (Avoidable Trap): {{LLM_FILL}} 匹 → 對應 SIP: {{LLM_FILL}}")
    lines.append("")

    # ── Non-systemic ──
    lines.append("## ⚠️ 單場特殊因素 (Non-Systemic, 僅供記錄)")
    lines.append("- {{LLM_FILL}}")
    lines.append("")

    # ── Engine Health Scan ──
    lines.append("## 🔬 引擎健康掃描結果 (Engine Health Scan)")
    lines.append("")
    lines.append("| 檢查維度 | 判定 | 簡述 |")
    lines.append("|:---|:---|:---|")
    for dim in ['4d-1 過時邏輯', '4d-2 斷裂邏輯', '4d-3 缺失規則', '4d-4 數據更新', '4d-5 規則校準', '4d-6 輸出品質']:
        lines.append(f"| {dim} | {{{{LLM_FILL}}}} | {{{{LLM_FILL}}}} |")
    lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='覆盤報告骨架自動生成器')
    parser.add_argument('analysis_dir', help='Directory containing Analysis.md files')
    parser.add_argument('results_file', help='Race results file')
    parser.add_argument('--domain', required=True, choices=['au', 'hkjc'], help='Domain: au or hkjc')
    parser.add_argument('--venue', help='Venue name (auto-detected from dir if omitted)')
    parser.add_argument('--date', help='Date YYYY-MM-DD (auto-detected from dir if omitted)')
    parser.add_argument('--output', help='Output file path (default: stdout)')
    args = parser.parse_args()

    if not os.path.isdir(args.analysis_dir):
        print(f'Error: {args.analysis_dir} is not a directory', file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(args.results_file):
        print(f'Error: {args.results_file} not found', file=sys.stderr)
        sys.exit(2)

    skeleton = generate_skeleton(
        args.analysis_dir, args.results_file,
        args.domain, args.venue, args.date
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(skeleton)
        print(f'✅ 覆盤報告骨架已生成: {args.output}')
        print(f'   {{{{LLM_FILL}}}} 標記數量: {skeleton.count("{{LLM_FILL}}")}')
    else:
        print(skeleton)

    sys.exit(0)


if __name__ == '__main__':
    main()
