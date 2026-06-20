"""
AU Deep Parser — Parses full horse analysis from AU Racing Analysis.txt files.
Different section headers from HKJC: ⏱️/🐴/🧠/📊/💡 (5 blocks x 13 subfields).
"""
import re
import csv
import io
from pathlib import Path
from typing import Optional


def _parse_data_readout(block: str) -> Optional[list]:
    """Parse the '📊 數據判讀' markdown block into structured rows for the UI.
    Each line: '- <band> **<label>**<value> — <trend>（<reason>）'."""
    section_m = re.search(r'數據判讀\s*\n+(.*?)(?:\n#### |\n## |\Z)', block, re.DOTALL)
    if not section_m:
        return None
    rows = []
    for line in section_m.group(1).splitlines():
        line = line.strip()
        m = re.match(r'^-\s*(✅|➖|⚠️)\s*\*\*(.+?)\*\*\s*(.*)$', line)
        if not m:
            continue
        band, label, rest = m.group(1), m.group(2).strip(), m.group(3).strip()
        reason = ''
        rm = re.search(r'（(.+?)）\s*$', rest)
        if rm:
            reason = rm.group(1).strip()
            rest = rest[:rm.start()].strip()
        value, trend = rest, ''
        if '—' in rest:
            value, trend = [p.strip() for p in rest.split('—', 1)]
        rows.append({'band': band, 'label': label, 'value': value, 'trend': trend, 'reason': reason})
    return rows or None

from models.race import (
    HorseAnalysis, RaceAnalysis, TopPick, MonteCarloPick, RatingDimension, RatingMatrix
)


# ──────────────────────────────────────────────
# Horse block splitting (AU format)
# ──────────────────────────────────────────────

# AU formats:
#   ### 【No.1】Northern Eyes（檔位：13）        — old, name followed by （
#   ### 【No.1】 Exit Fee | 騎師: … | 檔位: 4   — Auto report, name followed by |
AU_HORSE_HEADER_RE = re.compile(
    r'^(?:#+\s*)?【No\.(\d+)】\s*(.+?)(?=\s*(?:\||（|\(|$))',
    re.MULTILINE
)

# AU actual format in files: [#1] NORTHERN EYES (Barrier 13)
AU_HORSE_BRACKET_RE = re.compile(
    r'^\[#(\d{1,2})\]\s+([A-Z][A-Z\s\'-]+?)(?:\s*\(Barrier|\s*$)',
    re.MULTILINE
)

# Fallback: **[1] HorseName** | Jockey | Weight | Barrier
AU_HORSE_HEADER_ALT_RE = re.compile(
    r'^\*\*\[?(\d{1,2})\]?\s+(.+?)\*\*\s*\|',
    re.MULTILINE
)


def _split_au_horse_blocks(text: str) -> list[tuple[int, str, str]]:
    """Split AU analysis text into individual horse blocks."""
    # Try patterns in order of specificity
    patterns = [
        AU_HORSE_HEADER_RE,
        AU_HORSE_BRACKET_RE,
        AU_HORSE_HEADER_ALT_RE,
    ]
    matches = []
    for pattern in patterns:
        matches = list(pattern.finditer(text))
        if len(matches) >= 2:
            break
    if not matches:
        return []
    
    blocks = []
    for i, match in enumerate(matches):
        horse_num = int(match.group(1))
        horse_name = match.group(2).strip().rstrip('*').strip()
        
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        
        # Stop at Part 3 (Verdict) if it appears
        block_text = text[start:end]
        for marker in ['🏆 Top 3', '🏆 Top 4', '## 🏆', '#### 🏆']:
            idx = block_text.find(marker)
            if idx > 0:
                block_text = block_text[:idx]
                break
        
        blocks.append((horse_num, horse_name, block_text.strip()))
    
    return blocks


# ──────────────────────────────────────────────
# Section extraction helpers  
# ──────────────────────────────────────────────

# Engine type mapping for label extraction
ENGINE_LABELS = {
    'A': '前領均速型',
    'B': '末段爆發型',
    'C': '持續衝刺型',
    'A/B': '混合型',
    'B/C': '混合型',
    'A/C': '混合型',
}


def _extract_engine_type(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract engine type, label, and full summary from horse analysis block.
    Returns: (engine_type, engine_type_label, engine_distance_summary)
    """
    # Match: 引擎距離：Type A (Grinder/前領均速型)。Sire ...
    # Match: 引擎距離：Type A/B 混合。...
    # Match: 引擎距離：**Type A (領放型)！**
    m = re.search(
        r'引擎距離[：:]\s*\*{0,2}\s*(Type\s*([A-C](?:/[A-C])?)\s*(?:\(([^)]+)\))?[！!]?)\*{0,2}[。.]?\s*(.+?)(?:\n|$)',
        text
    )
    if not m:
        return None, None, None
    
    full_match = m.group(0).strip()
    type_code = m.group(2).strip()  # e.g. 'A', 'B', 'A/B'
    desc = m.group(3)  # e.g. 'Grinder/前領均速型' or '後追型'
    remaining = m.group(4).strip() if m.group(4) else ''
    
    # Determine label from description or fallback to mapping
    label = None
    if desc:
        # Extract Chinese label if present (e.g. 'Grinder/前領均速型' → '前領均速型')
        cn_m = re.search(r'([\u4e00-\u9fff][\u4e00-\u9fff/]*型)', desc)
        if cn_m:
            label = cn_m.group(1)
        else:
            label = desc.strip()
    
    if not label:
        label = ENGINE_LABELS.get(type_code, type_code)
    
    engine_type = f'Type {type_code}'
    # Build summary: engine type + key distance info (clean markdown)
    summary = full_match.replace('- **引擎距離：** ', '').replace('- **引擎距離：**', '').strip()
    summary = re.sub(r'\*{1,2}', '', summary).strip()  # Remove all markdown bold
    summary = re.sub(r'^引擎距離[：:]\s*', '', summary).strip()  # Remove prefix
    if not summary:
        summary = engine_type
    
    return engine_type, label, summary

def _extract_section(text: str, start_markers: list[str],
                     end_markers: Optional[list[str]] = None) -> Optional[str]:
    """Extract a section between start and end markers."""
    start_pos = -1
    for marker in start_markers:
        pos = text.find(marker)
        if pos >= 0:
            start_pos = pos
            break
    if start_pos < 0:
        return None
    if end_markers:
        end_pos = len(text)
        for marker in end_markers:
            pos = text.find(marker, start_pos + 10)
            if 0 < pos < end_pos:
                end_pos = pos
        return text[start_pos:end_pos].strip()
    return text[start_pos:].strip()


# ──────────────────────────────────────────────
# AU Horse analysis parsing
# ──────────────────────────────────────────────

def _parse_au_header(header_line: str, block: str) -> dict:
    """Parse AU header info. Supports both:
    - ### 【No.1】Northern Eyes（檔位：13） | 騎師：Anna Roper
    - [#1] NORTHERN EYES (Barrier 13) + Block 2: Horse Profile lines
    """
    result = {}
    
    # Extract jockey: 騎師：Name or Jockey: Name
    jockey_m = re.search(r'(?:騎師|Jockey)[：:]\s*(.+?)(?:\s*/\s*|\s*\||\s*$|\n)', block[:800])
    if jockey_m:
        result['jockey'] = jockey_m.group(1).strip()
    
    # Extract trainer: 練馬師：Name or Trainer: Name
    trainer_m = re.search(r'(?:練馬師|Trainer)[：:]\s*(.+?)(?:\s*\||\s*$|\n)', block[:800])
    if trainer_m:
        result['trainer'] = trainer_m.group(1).strip()
    
    # Extract weight: 負重：58kg or Weight: 58kg
    weight_m = re.search(r'(?:負重|Weight)[：:]\s*(.+?)(?:\s*\||\s*$|\n)', block[:800])
    if weight_m:
        result['weight'] = weight_m.group(1).strip()
    
    # Extract barrier: 檔位：13 or (Barrier 13) or Bar X
    barrier_m = re.search(r'(?:檔位|Barrier|Bar)[：:\s]\s*(\d+)', block[:800])
    if barrier_m:
        result['barrier'] = int(barrier_m.group(1))
    
    return result


def _parse_au_rating_matrix(text: str) -> Optional[RatingMatrix]:
    """Parse AU 📊 評級矩陣 (8 dimensions)."""
    section = _extract_section(text,
        ['📊 評級矩陣', '**📊 評級矩陣'],
        ['💡 結論', '**💡 結論', '⭐ 最終評級']
    )
    if not section:
        return None
    
    dimensions = []
    # Support both: [✅] and `✅` and `✅✅` wrapped values
    dim_re = re.compile(
        r'-\s*\*{0,2}(.+?)\*{0,2}\s*\[(\w+)\]:\s*[\[`]?(✅✅|✅|➖|❌❌|❌)[\]`]?\s*\|\s*理據[：:]\s*[\[`]?(.*?)[\]`]?\s*$',
        re.MULTILINE
    )
    for m in dim_re.finditer(section):
        dimensions.append(RatingDimension(
            name=m.group(1).strip().strip('*'),
            category=m.group(2).strip(),
            value=m.group(3).strip(),
            rationale=m.group(4).strip()
        ))
    
    base_re = re.search(r'(?:14\.2|基礎)\s*(?:基礎)?評級[：:]\s*[\[`]?([A-DS][+\-]?)[\]`]?', text)
    adj_re = re.search(r'(?:14\.2B|微調)[：:]\s*[\[`]?(.*?)[\]`]?\s*(?:\||$|\n)', text)
    ovr_re = re.search(r'(?:14\.3|覆蓋)[：:]\s*[\[`]?(.*?)[\]`]?(?:\n|$)', text)
    
    return RatingMatrix(
        dimensions=dimensions,
        base_rating=base_re.group(1) if base_re else None,
        adjustment=adj_re.group(1).strip() if adj_re else None,
        override=ovr_re.group(1).strip() if ovr_re else None,
    )


def _parse_au_final_grade(text: str) -> Optional[str]:
    """Extract final grade from AU analysis."""
    patterns = [
        r'⭐\s*最終評級[：:]\s*\[?`?([A-DS][+\-]?)\]?`?',
        r'\*\*⭐\s*最終評級[：:]\*\*\s*\[?`?([A-DS][+\-]?)\]?`?',
        r'最終評級[：:]\s*`?([A-DS][+\-]?)`?',
        # AU header format: ### 【No.1】Lafite ... | 評級: A
        r'評級[：:]\s*`?([A-DS][+\-]?)`?',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def parse_au_horse_block(horse_num: int, horse_name: str, block: str) -> HorseAnalysis:
    """Parse a single AU horse analysis block.
    Supports both:
    - Emoji format: ⏱️ 近績解構 / 🐴 馬匹剖析 / 🧠 核心分析 / 📊 評級矩陣 / 💡 結論
    - Block format: Block 1: Recent Form / Block 2: Horse Profile / Block 3: Core Analysis / Block 4: Rating Matrix / Block 5: Conclusion
    """
    
    header_info = _parse_au_header(block.split('\n')[0], block)
    
    # Try emoji format first, fallback to Block format
    recent_performance = _extract_section(block,
        ['⏱️ 近績解構', '**⏱️ 近績解構', 'Block 1: Recent Form', 'Block 1:'],
        ['🐴 馬匹剖析', '**🐴 馬匹剖析', 'Block 2:', '\n\n[#']
    )
    
    horse_profile = _extract_section(block,
        ['🐴 馬匹剖析', '**🐴 馬匹剖析', 'Block 2: Horse Profile', 'Block 2:'],
        ['🧠 核心分析', '**🧠 核心分析', 'Block 3:', '\n\n[#']
    )
    
    core_analysis = _extract_section(block,
        ['🧠 核心分析推演', '**🧠 核心分析推演', '🧠 核心分析', 'Block 3: Core Analysis', 'Block 3:'],
        ['📊 評級矩陣', '**📊 評級矩陣', 'Block 4:', '\n\n[#']
    )
    
    # Rating matrix — try emoji format first then Block 4
    rating_matrix = _parse_au_rating_matrix(block)
    
    # Final grade — try emoji format then "Overall Rating: X"
    final_grade = _parse_au_final_grade(block)
    if not final_grade:
        grade_m = re.search(r'Overall Rating:\s*([A-DS][+\-]?)', block)
        if grade_m:
            final_grade = grade_m.group(1)
    
    # Conclusion — try emoji format then Block 5
    conclusion = _extract_section(block,
        ['💡 結論', '**💡 結論', 'Block 5: Conclusion', 'Block 5:'],
        ['⭐ 最終評級', '---', '🐴⚡', 'Potential Horse Signals', '====']
    )
    
    advantage = None
    risk = None
    betting_verdict = None
    core_logic = None

    # Extract core_logic from 核心邏輯 pattern anywhere in block
    # Supports: > - **核心邏輯:** text  AND  **核心邏輯:** text
    cl_m = re.search(r'\*{0,2}核心邏輯\*{0,2}[：:]\s*\*{0,2}\s*(.+?)(?:\n|$)', block)
    if cl_m:
        core_logic = cl_m.group(1).strip().rstrip('*').strip()

    # Extract advantage: from 📌 情境標記 or 優勢 or 競爭優勢
    if conclusion:
        adv_m = re.search(r'(?:最大)?競爭優勢[：:]\s*(.+?)(?:\n|$)', conclusion)
        if adv_m:
            advantage = adv_m.group(1).strip()
        risk_m = re.search(r'(?:最大)?(?:失敗|風險)(?:原因)?[：:]\s*(.+?)(?:\n|$)', conclusion)
        if risk_m:
            risk = risk_m.group(1).strip()
    
    # AU-specific: extract advantage from 情境標記 if not found
    if not advantage:
        tag_m = re.search(r'📌\s*情境標記[：:]\s*`?(.+?)`?\s*(?:\n|$)', block)
        if tag_m:
            advantage = tag_m.group(1).strip()
    
    # AU-specific: extract risk from 風險儀表板
    if not risk:
        risk_m = re.search(r'(?:⚠️\s*)?(?:重大)?風險[：:]\s*\*{0,2}(.+?)(?:\n|$)', block)
        if risk_m:
            risk = risk_m.group(1).strip().rstrip('*').strip()

    # Betting verdict from Block 4
    verdict_m = re.search(r'Betting Verdict:\s*(.+?)(?:\n|$)', block)
    if verdict_m:
        betting_verdict = verdict_m.group(1).strip()

    
    # Recent form — try Chinese format then "Run String:"
    form_m = re.search(r'近績序列[：:]\s*`?(.+?)`?\s*(?:\*\*)?(?:\n|$)', block)
    if not form_m:
        form_m = re.search(r'Run String:\s*(.+?)(?:\n|$)', block)
    recent_form = form_m.group(1).strip() if form_m else None
    
    # Extract jockey from Block 2 if not found in header
    if not header_info.get('jockey'):
        jockey_m = re.search(r'Jockey:\s*(.+?)(?:\s*\(|$|\n)', block)
        if jockey_m:
            header_info['jockey'] = jockey_m.group(1).strip()
    
    # Extract trainer from Block 2 if not found cleanly
    trainer_m = re.search(r'Trainer:\s*(.+?)(?:\s*\(|$|\n)', block)
    if trainer_m:
        header_info['trainer'] = trainer_m.group(1).strip()
    
    # Potential horse signals (with 3-tier level detection)
    uh_section = _extract_section(block,
        ['Potential Horse Signals:', '🐴⚡'],
        ['====', '---', '\n\n[#']
    )
    uh_triggered = False
    uh_reason = None
    uh_level = None
    # Check for negative indicators: 未觸發, None, not triggered
    _uh_negative = ['未觸發', 'None positive', 'None', '沒有觸發', 'not triggered', 'No signal']
    _uh_is_negative = uh_section and any(neg in uh_section for neg in _uh_negative)
    if uh_section and not _uh_is_negative:
        uh_triggered = True
        uh_reason = uh_section.split(':', 1)[-1].strip() if ':' in uh_section else uh_section
        # Detect 3-tier signal level
        if '強力觸發' in uh_section or '🔴' in uh_section or 'STRONG' in uh_section.upper():
            uh_level = 'strong'
        elif '中度觸發' in uh_section or '🟡' in uh_section or 'MODERATE' in uh_section.upper():
            uh_level = 'moderate'
        elif '微弱觸發' in uh_section or '🟢' in uh_section or 'LIGHT' in uh_section.upper():
            uh_level = 'light'
        else:
            uh_level = 'light'  # Default to light if triggered but no level specified
    
    # Engine type extraction from horse_profile or full block
    engine_type, engine_label, engine_summary = _extract_engine_type(block)
    
    return HorseAnalysis(
        horse_number=horse_num,
        horse_name=horse_name,
        jockey=header_info.get('jockey'),
        trainer=header_info.get('trainer'),
        weight=header_info.get('weight'),
        barrier=header_info.get('barrier'),
        recent_form=recent_form,
        horse_profile=horse_profile,
        core_analysis=core_analysis,
        core_logic=core_logic,
        data_readout=_parse_data_readout(block),
        engine_type=engine_type,
        engine_type_label=engine_label,
        engine_distance_summary=engine_summary,
        rating_matrix=rating_matrix,
        final_grade=final_grade,
        conclusion=conclusion,
        advantage=advantage or betting_verdict,
        risk=risk,
        underhorse_triggered=uh_triggered,
        underhorse_level=uh_level,
        underhorse_reason=uh_reason,
        raw_text=block,
    )


# ──────────────────────────────────────────────
# SIP-RR01: Dual-scenario Top 4 extraction
# ──────────────────────────────────────────────

# Matches: 📗 **Good 4 場地 Top 4：**  or  📙 **Soft 5 場地 Top 4：**
SCENARIO_HEADER_RE = re.compile(
    r'(?:📗|📙)\s*\*{0,2}([A-Za-z ]+\d)\s*(?:場地)?\s*Top\s*4[：:]\*{0,2}',
    re.IGNORECASE
)


def _parse_au_scenario_top_picks(text: str) -> Optional[dict]:
    """Parse SIP-RR01 dual-scenario Top 4 blocks from AU verdict section.
    
    Returns dict like {"Good 4": [TopPick, ...], "Soft 5": [TopPick, ...]},
    or None if no dual-scenario blocks found.
    """
    headers = list(SCENARIO_HEADER_RE.finditer(text))
    if len(headers) < 2:
        return None
    
    scenarios = {}
    for i, header in enumerate(headers):
        label = header.group(1).strip()  # e.g. "Good 4", "Soft 5"
        # Block runs from this header to next header (or end)
        block_start = header.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[block_start:block_end]
        
        picks = _parse_au_verdict_picks(block)
        # Tag each pick with its scenario label
        for pick in picks:
            pick.scenario = label
        if picks:
            scenarios[label] = picks
    
    return scenarios if scenarios else None


# ──────────────────────────────────────────────
# Top 3 extraction (AU uses Top 3 not Top 4)
# ──────────────────────────────────────────────

def _parse_au_csv_block(text: str) -> list[TopPick]:
    """Parse CSV data block."""
    csv_match = re.search(r'```csv\s*\n(.+?)```', text, re.DOTALL)
    if not csv_match:
        return []
    
    picks = []
    csv_text = csv_match.group(1).strip()
    reader = csv.DictReader(io.StringIO(csv_text))
    for rank, row in enumerate(reader, 1):
        try:
            horse_number = int(row.get('Horse Number', 0))
            horse_name = row.get('Horse Name', '').strip()
            # Skip invalid rows with missing essential data
            if not horse_number or not horse_name:
                continue
            picks.append(TopPick(
                rank=rank,
                horse_number=horse_number,
                horse_name=horse_name,
                grade=row.get('Grade', '').strip(),
            ))
        except (ValueError, KeyError):
            continue
    return picks


def _parse_au_verdict_picks(text: str) -> list[TopPick]:
    """Parse Top 3/4 from verdict section.
    Handles 3 AU formats:
    1) Block: 🥇 **第一選** ... 馬號及馬名：8 My Phar Lady ... 評級：`A`
    2) Table: | 🥇 | 1 | Campaldino | A+ | 8 | ...
    3) Inline: 🥇 第一名：#2 Skyhook（A-）
    """
    picks = []
    medals = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    rank_labels = {1: '🥇', 2: '🥈', 3: '🥉', 4: '🏅'}
    
    # --- Format 2: Markdown table rows like | 🥇 | 1 | Campaldino | A+ | 8 | ... |
    table_pattern = re.compile(r'\|\s*(🥇|🥈|🥉|🏅)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([A-DS][+\-]?)\s*\|')
    table_matches = table_pattern.findall(text)
    if table_matches:
        for medal_str, num, name, grade in table_matches:
            rank = medals.get(medal_str, 0)
            if rank:
                picks.append(TopPick(
                    rank=rank,
                    rank_label=rank_labels.get(rank, ''),
                    horse_number=int(num),
                    horse_name=name.strip(),
                    grade=grade.strip(),
                ))
        if picks:
            return picks
    
    # --- Format 3: Inline like "🥇 第一名：#2 Skyhook（A-）"
    inline_pattern = re.compile(r'(🥇|🥈|🥉|🏅)\s*第[一二三四]名[：:]\s*#?(\d+)\s+(.+?)[（(]([A-DS][+\-]?(?:\s*Place)?)[）)]')
    inline_matches = inline_pattern.findall(text)
    if inline_matches:
        for medal_str, num, name, grade in inline_matches:
            rank = medals.get(medal_str, 0)
            if rank:
                picks.append(TopPick(
                    rank=rank,
                    rank_label=rank_labels.get(rank, ''),
                    horse_number=int(num),
                    horse_name=name.strip(),
                    grade=grade.strip(),
                ))
        if picks:
            return picks
    
    # --- Format 1: Block format with 🥇 **第一選** ... 馬號及馬名：8 My Phar Lady
    for medal, rank in medals.items():
        idx = text.find(medal)
        if idx < 0:
            continue
        # Get block up to next medal or 500 chars
        end_idx = len(text)
        for other_medal in medals:
            if other_medal == medal:
                continue
            other_idx = text.find(other_medal, idx + 1)
            if 0 < other_idx < end_idx:
                end_idx = other_idx
        block = text[idx:end_idx]
        
        # Extract horse number and name:
        # Supports: "馬號及馬名：8 My Phar Lady", "馬號及馬名：[8] Peyton", "**馬號及馬名:** [8] Peyton"
        hn_m = re.search(r'馬號[及與]?馬名[：:][^\n]*?\[?(\d+)\]?\s+([A-Za-z\u4e00-\u9fff][^\n*]+?)(?:\n|$)', block)
        if not hn_m:
            # English: "8 My Phar Lady" at start of a line
            hn_m = re.search(r'^(\d+)\s+([A-Z][A-Za-z \'-]+?)(?:\n|$)', block, re.MULTILINE)
        if not hn_m:
            continue

        # Extract grade: "`[S+]`", "`A`", "Grade: A", "評級：A"
        grade_m = re.search(r'(?:評級|Grade)[^：:]*[：:]\s*\*{0,2}\s*`?\[?([A-DS][+\-]?)\]?`?', block)
        grade = grade_m.group(1) if grade_m else None

        picks.append(TopPick(
            rank=rank,
            horse_number=int(hn_m.group(1)),
            horse_name=hn_m.group(2).strip().rstrip('*').strip(),
            grade=grade,
        ))
    
    return picks


# ──────────────────────────────────────────────
# Monte Carlo simulation table parser (AU + HKJC)
# ──────────────────────────────────────────────

def _parse_monte_carlo_table(text: str) -> list['MonteCarloPick']:
    """Parse MC table from both AU format (## [第四點五部分]) and HKJC format (#### 📊 Monte Carlo).
    
    Uses header-based column detection to handle multiple table layouts:
    - Old format (no place odds): icon | hnum | name | win% | odds | top3% | top4% | frank | diverg
    - V2 format (with place odds): icon | hnum | name | win% | odds | top3% | place_odds | top4% | frank | diverg
    - HKJC core format: icon | name | win% | CI | odds | top3% | place_odds | top4% | avg_rank | match
    """
    picks = []
    
    # Find MC section — try AU header first, then HKJC header
    mc_section = _extract_section(text,
        ['## [第四點五部分]', '#### 📊 Monte Carlo', '#### 📊 Monte Carlo 概率模擬'],
        ['## [第五部分]', '---\n## ', '\n---\n---']
    )
    if not mc_section:
        return []
    
    lines = mc_section.split('\n')
    
    # Step 1: Find header row and build column map
    col_map = {}
    header_line_idx = -1
    
    # Keywords that identify each column type
    _COL_DETECT = {
        'rank':       ['MC排名', '排名'],
        'hnum':       ['馬號'],
        'name':       ['馬名'],
        'win':        ['勝出', 'MC 勝率'],
        'ci':         ['CI', '95%'],
        'win_odds':   ['MC獨贏', '預測賠率', '獨贏'],
        'top3':       ['三甲', 'Top 3'],
        'place_odds': ['MC位置', '位置賠率'],
        'top4':       ['四甲', 'Top 4'],
        'avg_rank':   ['平均名次', '名次'],
        'frank':      ['法證', '法醫'],
        'match':      ['吻合', '差異'],
    }
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        cells = [c.strip() for c in stripped.split('|')]
        cells = [c for c in cells if c]
        
        # Check if this looks like a header row (contains known keywords)
        header_keywords_found = sum(
            1 for cell in cells
            for col_keys in _COL_DETECT.values()
            for kw in col_keys
            if kw in cell
        )
        if header_keywords_found >= 2:
            header_line_idx = i
            for j, cell in enumerate(cells):
                for col_name, keywords in _COL_DETECT.items():
                    if col_name in col_map:
                        continue  # Already assigned — don't overwrite
                    if any(kw in cell for kw in keywords):
                        col_map[col_name] = j
                        break
            break
    
    if header_line_idx < 0:
        return []
    
    # Step 2: Parse data rows
    for line in lines[header_line_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith('|') or not stripped.endswith('|'):
            continue
        # Skip separator rows
        if '---' in stripped and not any(c.isalpha() for c in stripped.replace('|', '')):
            continue
        
        cells = [c.strip() for c in stripped.split('|')]
        cells = [c for c in cells if c]
        
        if len(cells) < 3:
            continue
        
        def get_cell(key):
            idx = col_map.get(key)
            if idx is not None and idx < len(cells):
                return cells[idx]
            return None
        
        # Horse name
        name = get_cell('name')
        if not name:
            # Fallback: assume column 1 or 2 is name
            name = cells[2] if len(cells) > 2 and col_map.get('hnum') is not None else cells[1] if len(cells) > 1 else None
        if not name or '---' in name or '馬名' in name:
            continue
        
        # Win percentage
        win_str = get_cell('win') or ''
        win_m = re.search(r'([\d.]+)', win_str)
        if not win_m:
            continue
        try:
            win_pct = float(win_m.group(1))
        except ValueError:
            continue
        
        # Horse number
        hnum = get_cell('hnum')
        if hnum in ('—', '-', '', None):
            hnum = None
        
        # Win odds
        odds_str = get_cell('win_odds')
        
        # Place odds (V2 only)
        place_odds_str = get_cell('place_odds')
        
        # Top 3%
        top3_str = get_cell('top3') or ''
        top3_m = re.search(r'([\d.]+)', top3_str)
        top3 = float(top3_m.group(1)) if top3_m else None
        
        # Top 4%
        top4_str = get_cell('top4') or ''
        top4_m = re.search(r'([\d.]+)', top4_str)
        top4 = float(top4_m.group(1)) if top4_m else None
        
        # Forensic rank
        frank = get_cell('frank')
        
        # Divergence / match
        diverg = get_cell('match')
        
        picks.append(MonteCarloPick(
            mc_rank=len(picks) + 1,
            horse_number=hnum,
            horse_name=name,
            win_pct=win_pct,
            predicted_odds=odds_str.strip() if odds_str else None,
            predicted_place_odds=place_odds_str.strip() if place_odds_str else None,
            top3_pct=top3,
            top4_pct=top4,
            forensic_rank=frank.strip() if frank else None,
            divergence=diverg.strip() if diverg else None,
        ))
    
    return picks


def parse_mc_results_json(filepath: str) -> list['MonteCarloPick']:
    """Parse a standalone Race_N_MC_Results.json file produced by mc_simulator.py.
    
    The JSON has a 'results' dict keyed by horse name, each with:
      win_pct, top3_pct, top4_pct, avg_rank, ci_95, predicted_win_odds, predicted_place_odds
    
    Also reads 'power_index_breakdown' for forensic rank info and 'concordance' for divergence.
    """
    import json as _json
    path = Path(filepath)
    if not path.exists():
        return []
    
    try:
        data = _json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return []
    
    results = data.get('results', {})
    pi_breakdown = data.get('power_index_breakdown', {})
    concordance = data.get('concordance', {})
    logic_top4 = concordance.get('logic_top4', [])
    mc_top4 = concordance.get('mc_top4', [])
    
    if not results:
        return []
    
    # Sort by win_pct descending
    sorted_horses = sorted(results.items(), key=lambda x: x[1].get('win_pct', 0), reverse=True)
    
    picks = []
    for rank, (horse_name, stats) in enumerate(sorted_horses, 1):
        win_pct = stats.get('win_pct', 0)
        top3_pct = stats.get('top3_pct', 0)
        top4_pct = stats.get('top4_pct', 0)
        avg_rank = stats.get('avg_rank', 0)
        
        # Predicted odds — format as "$X.X" for display
        win_odds = stats.get('predicted_win_odds', 0)
        place_odds = stats.get('predicted_place_odds', 0)
        odds_str = f"${win_odds:.1f}" if win_odds and win_odds < 9999 else None
        place_str = f"${place_odds:.1f}" if place_odds and place_odds < 9999 else None
        
        # Forensic rank — derive from logic_top4 position
        forensic_rank = None
        if horse_name in logic_top4:
            f_pos = logic_top4.index(horse_name) + 1
            icons = {1: '🥇', 2: '🥈', 3: '🥉', 4: '🏅'}
            forensic_rank = f"{icons.get(f_pos, '')} #{f_pos}"
        
        # Divergence — compare MC rank vs forensic rank
        divergence = None
        if horse_name in mc_top4 and horse_name in logic_top4:
            mc_pos = mc_top4.index(horse_name) + 1
            f_pos = logic_top4.index(horse_name) + 1
            diff = f_pos - mc_pos
            if diff == 0:
                divergence = "✅ 一致"
            elif diff > 0:
                divergence = f"❌ ⬆️{diff}"
            else:
                divergence = f"❌ ⬇️{abs(diff)}"
        elif horse_name in mc_top4 and horse_name not in logic_top4:
            divergence = "❌ MC Only"
        elif horse_name not in mc_top4 and horse_name in logic_top4:
            divergence = "❌ Logic Only"
        
        # Try to find horse number from pi_breakdown (not always available)
        horse_number = None
        
        picks.append(MonteCarloPick(
            mc_rank=rank,
            horse_number=horse_number,
            horse_name=horse_name,
            win_pct=win_pct,
            predicted_odds=odds_str,
            predicted_place_odds=place_str,
            top3_pct=top3_pct,
            top4_pct=top4_pct,
            forensic_rank=forensic_rank,
            divergence=divergence,
        ))
    
    return picks


# ──────────────────────────────────────────────
# Full race parse
# ──────────────────────────────────────────────

def _parse_au_race_header(text: str) -> dict:
    """Parse AU race specs."""
    info = {}
    
    race_m = re.search(r'Race\s+(\d+)', text, re.IGNORECASE)
    if race_m:
        info['race_number'] = int(race_m.group(1))
    
    dist_m = re.search(r'(\d{3,4})\s*m', text)
    if dist_m:
        info['distance'] = dist_m.group(1) + 'm'
    
    # Try table format first: | 賽事格局 | BM72 讓磅賽 / 1300m / Rosehill Gardens / Soft 6 |
    format_m = re.search(r'\|\s*賽事格局\s*\|\s*([^/]+?)(?:\s*讓磅賽|\s*平磅賽)?\s*/\s*(\d{3,4})\s*m\s*/', text)
    if format_m:
        info['race_class'] = format_m.group(1).strip()
        info['distance'] = format_m.group(2).strip() + 'm'
    else:
        class_m = re.search(r'(?:Class|Grade|Group)\s*[：:]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if not class_m:
            class_m = re.search(r'(BM\d+|G[123]|Listed|Maiden|CL\d|Open|Benchmark)', text, re.IGNORECASE)
        if class_m:
            info['race_class'] = class_m.group(1).strip() if class_m else None
        
    # Extract race name from AU "Race: Venue Race N" line
    race_name_m = re.search(r'Race:\s*(.+?)\s*$', text[:500], re.MULTILINE)
    if not race_name_m:
        # Fallback for MD header: # Race 1 — 1300m | Midway BM72 Handicap | Rosehill Gardens
        race_name_m = re.search(r'^#\s*Race\s*\d+\s*(?:—|-|\|)[^\|]+\|\s*([^\|]+)\s*\|', text, re.MULTILINE)
    if race_name_m:
        info['race_name'] = race_name_m.group(1).strip()
    
    going_m = re.search(r'(?:預測掛牌|Track Condition|Going)[：:]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if going_m:
        info['going'] = going_m.group(1).strip()
    
    return info


def parse_au_analysis(filepath: str) -> Optional[RaceAnalysis]:
    """Parse a complete AU Racing Analysis.txt file."""
    path = Path(filepath)
    if not path.exists():
        return None
    
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding='utf-8-sig')
        except Exception:
            return None
    
    race_num_m = re.search(r'Race\s+(\d+)', path.name, re.IGNORECASE)
    race_number = int(race_num_m.group(1)) if race_num_m else 0
    
    header_info = _parse_au_race_header(text)
    if not race_number and 'race_number' in header_info:
        race_number = header_info['race_number']
    
    # Parse horse blocks
    horse_blocks = _split_au_horse_blocks(text)
    horses = []
    last_horse_end = 0
    for h_num, h_name, h_block in horse_blocks:
        horse = parse_au_horse_block(h_num, h_name, h_block)
        horse.raw_text = h_block.strip()  # Store full analysis text
        horses.append(horse)
        # Track where in the original text the last horse block ends
        idx = text.rfind(h_block[:50])
        if idx >= 0:
            last_horse_end = max(last_horse_end, idx + len(h_block))
    
    # Top picks
    top_picks = _parse_au_csv_block(text)
    if not top_picks:
        verdict = _extract_section(text,
            ['🏆 全場最終決策', '🏆 Top 3', '🏆 Top 4', '[第三部分]',
             'Top 4 位置精選', 'Top 3 位置精選', 'Top 4 精選排名', '精選排名'],
            ['[第四部分]', '🔒 COMPLIANCE', '```csv']
        )
        if verdict:
            top_picks = _parse_au_verdict_picks(verdict)
        # Fallback: search text AFTER the last horse block only
        if not top_picks and last_horse_end > 0:
            after_horses = text[last_horse_end:]
            top_picks = _parse_au_verdict_picks(after_horses)
    
    # SIP-RR01: Dual-scenario Top 4 (Good 4 / Soft 5 blocks)
    after_horses_text = text[last_horse_end:] if last_horse_end > 0 else text
    scenario_top_picks = _parse_au_scenario_top_picks(after_horses_text)

    # Monte Carlo simulation table
    monte_carlo = _parse_monte_carlo_table(text)

    # Battlefield overview (戰場全景) — AU format: ## [第一部分] 🗺️ 戰場全景
    battlefield = _extract_section(text,
        ['## [第一部分]', '[第一部分]', '🗺️ 戰場全景', '## 第一部分'],
        ['## [第二部分]', '###', '\n\n---\n', '#### ']
    )

    return RaceAnalysis(
        race_number=race_number,
        distance=header_info.get('distance'),
        race_class=header_info.get('race_class'),
        going=header_info.get('going'),
        race_name=header_info.get('race_name'),
        horses=horses,
        top_picks=top_picks,
        scenario_top_picks=scenario_top_picks,
        monte_carlo_simulation=monte_carlo if monte_carlo else None,
        battlefield_overview=battlefield,
    )

