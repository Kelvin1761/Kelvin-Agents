"""
AU Deep Parser — Parses full horse analysis from AU Racing Analysis.txt files.
Different section headers from HKJC: ⏱️/🐴/🧠/📊/💡 (5 blocks x 13 subfields).
"""
import re
import csv
import io
from pathlib import Path
from typing import Optional

from models.race import (
    HorseAnalysis, RaceAnalysis, TopPick, RatingDimension, RatingMatrix
)


# ──────────────────────────────────────────────
# Horse block splitting (AU format)
# ──────────────────────────────────────────────

# AU format: ### 【No.1】Northern Eyes（檔位：13） or  【No.1】Campaldino（檔位：7）
AU_HORSE_HEADER_RE = re.compile(
    r'^(?:###\s*)?【No\.(\d+)】\s*(.+?)(?:（|[\(])',
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
        for marker in ['🏆 Top 3', '🏆 Top 4', '## 🏆', '#### 🏆', '[第三部分]']:
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
        ['💡 核心邏輯與結論', '**💡 核心邏輯與結論', '💡 結論', '**💡 結論', '⭐ 最終評級']
    )
    if not section:
        return None
    
    dimensions = []
    dim_re = re.compile(
        r'-\s*(?:\*\*)?([^\*\[]+?)(?:\*\*)?\s*\[([^\]]+)\]:\s*`?\[?([✅➖❌])\]?`?\s*\|\s*理據:\s*`?\[?(.*?)\]?`?\s*$',
        re.MULTILINE
    )
    for m in dim_re.finditer(section):
        dimensions.append(RatingDimension(
            name=m.group(1).strip(),
            category=m.group(2).strip(),
            value=m.group(3).strip(),
            rationale=m.group(4).strip()
        ))
    
    base_re = re.search(r'(?:14\.2|基礎)\s*(?:基礎)?評級[：:]\s*\[?([A-DS][+\-]?)\]?', text)
    adj_re = re.search(r'(?:14\.2B|微調)[：:]\s*\[?(.*?)\]?\s*(?:\||$|\n)', text)
    ovr_re = re.search(r'(?:14\.3|覆蓋)[：:]\s*\[?(.*?)\]?(?:\n|$)', text)
    
    return RatingMatrix(
        dimensions=dimensions,
        base_rating=base_re.group(1) if base_re else None,
        adjustment=adj_re.group(1).strip() if adj_re else None,
        override=ovr_re.group(1).strip() if ovr_re else None,
    )


def _parse_au_final_grade(text: str) -> Optional[str]:
    """Extract final grade from AU analysis."""
    patterns = [
        # ⭐ **最終評級：** `[A-]`  (bold label, backtick+bracket grade)
        r'⭐\s*\*{0,2}\s*最終評級[：:]\s*\*{0,2}\s*`?\[?([A-DS][+\-]?)\]?`?',
        # 最終評級：`A-` or 最終評級：[A-]
        r'最終評級[：:]\s*\*{0,2}\s*`?\[?([A-DS][+\-]?)\]?`?',
        # 📗 預期場地: `[Soft 6]` → 評級:`[A-]` (dual-track primary grade)
        r'📗\s*\*{0,2}\s*預期場地[：:\*]*\s*`?\[?[^]]+?\]?`?\s*→\s*評級[：:\*]*\s*`?\[?([A-DS][+\-]?)\]?`?',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def _parse_dual_track_grade(text: str) -> dict:
    """Parse 📗📙 Dual-Track Grade block from a horse analysis.
    Returns dict with alt_condition, alt_grade, grade_shift, grade_shift_reason.
    Supports multiple formats:
    - Full: 📗 預期場地： [Soft 6] → 評級：[A+] / 📙 備選場地： [Good 4] → 評級：[B+]
    - Short: 📗 Soft 6: [A+] / 📙 Good 4: [B+]
    - Inline: 📗📙 場地雙軌評級: ... 📗 **Soft 6:** `[B+]` / 📙 **Good 4:** `[B+]`
    """
    result = {}
    # Look for the dual-track block
    dt_section = _extract_section(text,
        ['📗📙 場地雙軌評級', '📗📙 **場地雙軌評級', '📗📙 Dual-Track Grade', '📗📙 **Dual-Track Grade', '📗📙 評級不變', '📗📙 **評級不變'],
        ['🐴⚡', '潛力馬訊號', 'Underhorse', '---', '\n\n[#', '\n\n###']
    )
    if not dt_section:
        return result
    
    # Format 1 (Full): 📙 備選場地： `[Soft 5]` → 評級：`[B+]` | 變化：`[↓ 降一級]`
    alt_m = re.search(
        r'📙\s*\*{0,2}備選場地[：:]\s*\*{0,2}\s*`?\[?(.+?)\]?`?\s*→\s*評級[：:]\s*`?\[?([A-DS][+\-]?)\]?`?'
        r'(?:\s*\|\s*變化[：:]\s*`?\[?(.+?)\]?`?)?',
        dt_section
    )
    if alt_m:
        result['alt_condition'] = alt_m.group(1).strip()
        result['alt_grade'] = alt_m.group(2).strip()
        if alt_m.group(3):
            result['grade_shift'] = alt_m.group(3).strip()
    
    # Format 2 (Short): 📙 **Good 4:** `[B+]` or 📙 Good 4: [B+]
    if 'alt_grade' not in result:
        # Match: 📙 **Good 4:** `[B+]` | `[↓ ...]`
        short_m = re.search(
            r'📙\s*\*{0,2}\s*([A-Za-z]+\s*\d)\s*[：:]?\*{0,2}\s*`?\[?([A-DS][+\-]?)\]?`?'
            r'(?:\s*\|?\s*`?\[?([↑↓→][^\]]*?)\]?`?)?',
            dt_section
        )
        if short_m:
            result['alt_condition'] = short_m.group(1).strip()
            result['alt_grade'] = short_m.group(2).strip()
            if short_m.group(3):
                result['grade_shift'] = short_m.group(3).strip()
            else:
                # Determine shift by comparing with primary grade
                primary_m = re.search(
                    r'📗\s*\*{0,2}\s*[A-Za-z]+\s*\d\s*[：:]?\*{0,2}\s*`?\[?([A-DS][+\-]?)\]?`?',
                    dt_section
                )
                if primary_m:
                    if primary_m.group(1).strip() == result['alt_grade']:
                        result['grade_shift'] = '→ 不變'
    
    # Format 3: 📗📙 評級不變：[A-] → [A-]
    if 'alt_grade' not in result:
        unchanged_m = re.search(r'評級不變[：:]\s*\[?([A-DS][+\-]?)\]?\s*→\s*\[?([A-DS][+\-]?)\]?', dt_section)
        if unchanged_m:
            result['alt_grade'] = unchanged_m.group(2).strip()
            result['grade_shift'] = '→ 不變'
    
    # Parse grade shift reason:
    # 場地影響理據： ...
    reason_m = re.search(r'場地影響理據[：:]\s*(.+?)(?:\n\n|📗📙 Dual|$)', dt_section, re.DOTALL)
    if reason_m:
        reason_text = reason_m.group(1).strip()
        # Clean up multi-line: take first 200 chars
        reason_text = re.sub(r'\n\s*-\s*', ' | ', reason_text)
        result['grade_shift_reason'] = reason_text[:200]
    
    return result


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
        ['💡 核心邏輯與結論', '**💡 核心邏輯與結論', '💡 結論', '**💡 結論', 'Block 5: Conclusion', 'Block 5:'],
        ['⭐ 最終評級', '---', '🐴⚡', 'Potential Horse Signals', '====']
    )
    
    advantage = None
    risk = None
    betting_verdict = None
    
    if conclusion:
        adv_m = re.search(r'(?:最大)?競爭優勢[：:]\s*(.+?)(?:\n|$)', conclusion)
        if adv_m:
            advantage = adv_m.group(1).strip()
        risk_m = re.search(r'(?:最大)?(?:失敗|風險)(?:原因)?[：:]\s*(.+?)(?:\n|$)', conclusion)
        if risk_m:
            risk = risk_m.group(1).strip()
    
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
    # Supports both English and Chinese section markers
    uh_section = _extract_section(block,
        ['Potential Horse Signals:', '🐴⚡'],
        ['====', '---', '\n\n[#', '\n\n###']
    )
    uh_triggered = False
    uh_reason = None
    uh_level = None
    
    # Chinese negative markers that indicate NO signal
    _UH_NEGATIVE_MARKERS = ['None', '無', '未觸發', '沒有', '不適用', 'N/A', 'nil']
    
    if uh_section:
        # Check if the section explicitly says "no signal" in either language
        first_line = uh_section.split('\n')[0] if uh_section else ''
        section_text = uh_section[:200]  # Check first 200 chars for negatives
        is_negative = any(marker in section_text for marker in _UH_NEGATIVE_MARKERS)
        
        if not is_negative:
            uh_triggered = True
            # Extract reason: after the colon or the whole section
            uh_reason = uh_section.split(':', 1)[-1].strip() if ':' in uh_section else uh_section
            # Clean up the reason text
            uh_reason = re.sub(r'^\s*\*{0,2}\s*', '', uh_reason).strip()
            uh_reason = re.sub(r'\*{0,2}\s*$', '', uh_reason).strip()
            
            # Detect 3-tier signal level
            if '強力觸發' in uh_section or '強烈觸發' in uh_section or '🔴' in uh_section or 'STRONG' in uh_section.upper():
                uh_level = 'strong'
            elif '中度觸發' in uh_section or '🟡' in uh_section or 'MODERATE' in uh_section.upper():
                uh_level = 'moderate'
            elif '微弱觸發' in uh_section or '🟢' in uh_section or 'LIGHT' in uh_section.upper():
                uh_level = 'light'
            else:
                uh_level = 'light'  # Default to light if triggered but no level specified
    
    # Engine type extraction from horse_profile or full block
    engine_type, engine_label, engine_summary = _extract_engine_type(block)
    
    # Dual-track grade (SIP-1)
    dual_track = _parse_dual_track_grade(block)
    
    # Extract core_logic from conclusion (blockquote format)
    core_logic = None
    if conclusion:
        # Match: > - **核心邏輯：** text... (multi-line until next > - ** or end)
        cl_m = re.search(
            r'(?:>\s*-?\s*)?\*{0,2}核心邏輯[：:]\*{0,2}\s*(.+?)'
            r'(?=(?:>\s*-?\s*)?\*{0,2}(?:最大競爭優勢|最大失敗|$))',
            conclusion, re.DOTALL
        )
        if cl_m:
            core_logic = cl_m.group(1).strip()
            # Clean markdown/blockquote artifacts
            core_logic = re.sub(r'^\s*>\s*', '', core_logic, flags=re.MULTILINE)
            core_logic = re.sub(r'\*{1,2}', '', core_logic)
            core_logic = core_logic.strip()
        
        # Fallback: if no 核心邏輯 keyword, use blockquote conclusion text directly
        if not core_logic:
            # Extract text after 💡 結論 heading, up to first - ** or ⭐ line
            fb_m = re.search(
                r'(?:💡\s*結論|結論)[\n\r]+>\s*(.+?)'
                r'(?=\n-\s*\*{2}|\n⭐|\n📗|$)',
                conclusion, re.DOTALL
            )
            if fb_m:
                core_logic = fb_m.group(1).strip()
                core_logic = re.sub(r'^\s*>\s*', '', core_logic, flags=re.MULTILINE)
                core_logic = re.sub(r'\*{1,2}', '', core_logic)
                core_logic = core_logic.strip()
            # Final fallback: grab first blockquote paragraph
            if not core_logic:
                lines = conclusion.split('\n')
                bq_lines = []
                for ln in lines:
                    stripped = ln.strip()
                    if stripped.startswith('>'):
                        bq_lines.append(re.sub(r'^>\s*', '', stripped))
                    elif bq_lines and stripped == '':
                        break  # end of first blockquote block
                    elif bq_lines:
                        break
                if bq_lines:
                    core_logic = ' '.join(bq_lines)
                    core_logic = re.sub(r'\*{1,2}', '', core_logic).strip()
    
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
        engine_type=engine_type,
        engine_type_label=engine_label,
        engine_distance_summary=engine_summary,
        rating_matrix=rating_matrix,
        final_grade=final_grade,
        alt_condition=dual_track.get('alt_condition'),
        alt_grade=dual_track.get('alt_grade'),
        grade_shift=dual_track.get('grade_shift'),
        grade_shift_reason=dual_track.get('grade_shift_reason'),
        conclusion=conclusion,
        core_logic=core_logic,
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

# Matches multiple formats of dual-scenario Top 4 headers:
# Format 1: 📗 **[Good 4] Top 4：**  or  📙 **[Soft 5] Top 4：**
# Format 2: 📗 **[預期場地] Top 4：** or 📙 **[備選場地] Top 4：**
# Format 3: 📗 **預期場地 (Soft 6) Top 4:** or 📙 **備選場地 (Good 4) Top 4:**
# Format 4: 📗 **Soft 6 場地 Top 4:** (Race 3 style, no brackets)
SCENARIO_HEADER_RE = re.compile(
    r'(?:📗|📙)\s*\*{0,2}\[?'
    r'(?:'
    r'([A-Za-z]+\s*\d)'
    r'|([\u4e00-\u9fff]+)(?:\s*[（(]([A-Za-z]+\s*\d)[）)])?'
    r')\]?\s*(?:場地)?\s*Top\s*4[：:]\*{0,2}',
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
    # Normalize Chinese labels to English conditions
    LABEL_MAP = {'預期場地': 'Soft 6', '備選場地': 'Good 4'}
    for i, header in enumerate(headers):
        # Priority: group(3) = parenthesized condition e.g. 'Soft 6', group(1) = English label, group(2) = Chinese label
        label = (header.group(3) or header.group(1) or header.group(2) or '').strip()
        # Normalize Chinese labels
        if label in LABEL_MAP:
            label = LABEL_MAP[label]
        # Block runs from this header to next header (or end)
        block_start = header.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[block_start:block_end]
        
        picks = _parse_au_verdict_picks(block)
        if not picks:
            picks = _parse_au_csv_block(block)
            
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
    """Parse CSV data block. Supports multiple column name variants."""
    csv_match = re.search(r'```csv\s*\n(.+?)```', text, re.DOTALL)
    if not csv_match:
        return []
    
    picks = []
    csv_text = csv_match.group(1).strip()
    reader = csv.DictReader(io.StringIO(csv_text), skipinitialspace=True)
    rows = []
    for row in reader:
        try:
            horse_num_str = (row.get('Horse_Num') or row.get('Horse_Number')
                            or row.get('Horse Number') or row.get('Horse_No')
                            or row.get('Horse No.') or '0')
            horse_number = int(horse_num_str)
            horse_name = (row.get('Horse_Name') or row.get('Horse Name') or '').strip()
            grade = (row.get('P19_Rating') or row.get('Rating_Grade')
                     or row.get('Grade') or '').strip()
            p19_rank_str = row.get('P19_Rank', '0')
            try:
                p19_rank = int(p19_rank_str)
            except (ValueError, TypeError):
                p19_rank = 0
            # Skip invalid rows with missing essential data
            if not horse_number or not horse_name:
                continue
            rows.append((p19_rank, horse_number, horse_name, grade))
        except (ValueError, KeyError):
            continue
    
    # Sort by P19_Rank if present, otherwise keep CSV order
    if any(r[0] > 0 for r in rows):
        rows.sort(key=lambda r: r[0])
    
    for rank, (_, horse_number, horse_name, grade) in enumerate(rows, 1):
        picks.append(TopPick(
            rank=rank,
            horse_number=horse_number,
            horse_name=horse_name,
            grade=grade,
        ))
    return picks


def _parse_au_verdict_picks(text: str) -> list[TopPick]:
    """Parse Top 3/4 from verdict section."""
    picks = []
    medals = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    rank_labels = {1: '🥇', 2: '🥈', 3: '🥉', 4: '🏅'}
    
    # --- Format 5: Inline colon: 🥇 **第一選**：**[3] The Next Episode**
    inline_colon_re = re.compile(
        r'(🥇|🥈|🥉|🏅)\s*\*{0,2}第[一二三四][名選]\*{0,2}[：:]\s*\*{0,2}\[?(\d+)\]?\s+(.+?)\*{0,2}\s*$',
        re.MULTILINE
    )
    for m in inline_colon_re.finditer(text):
        medal_str = m.group(1)
        horse_num = int(m.group(2))
        horse_name = m.group(3).strip().rstrip('*').strip()
        # Look for grade in the following lines
        block_start = m.end()
        block_end = text.find('\n\n', block_start)
        if block_end < 0:
            block_end = len(text)
        sub = text[block_start:block_end]
        # Match: `[A-]` or `[Soft 6: A]` (dual-track format — take first grade)
        grade_m = re.search(r'`\[?(?:[A-Za-z]+\s*\d\s*:\s*)?([A-DS][+\-]?)\]?`', sub)
        picks.append(TopPick(
            rank=medals[medal_str],
            rank_label=medal_str,
            horse_number=horse_num,
            horse_name=horse_name,
            grade=grade_m.group(1) if grade_m else None,
        ))
    if picks:
        return picks
    
    # --- Format 4: Horizontal pipe-separated: 🥇 [1] Maluku | 🥈 [6] Beverly Hills
    for line in text.split('\n'):
        if '|' in line and sum(1 for m in medals if m in line) >= 2:
            chunks = line.split('|')
            for chunk in chunks:
                match = re.search(r'(🥇|🥈|🥉|🏅)\s*\[?(\d+)\]?\s+([A-Za-z][A-Za-z\s\'-]*)', chunk)
                if match:
                    medal_str, num, name = match.groups()
                    grade_m = re.search(r'\(\s*([A-DS][+\-]?)\s*\)', chunk)
                    picks.append(TopPick(
                        rank=medals[medal_str],
                        rank_label=medal_str,
                        horse_number=int(num),
                        horse_name=name.strip(),
                        grade=grade_m.group(1) if grade_m else None,
                    ))
            if picks:
                return picks

    # --- Format 2: Markdown table rows like | 🥇 | 1 | Campaldino | A+ |
    table_pattern = re.compile(r'\|\s*(🥇|🥈|🥉|🏅)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([A-DS][+\-]?)\s*\|')
    for medal_str, num, name, grade in table_pattern.findall(text):
        if medal_str in medals:
            picks.append(TopPick(
                rank=medals[medal_str],
                rank_label=medal_str,
                horse_number=int(num),
                horse_name=name.strip(),
                grade=grade.strip(),
            ))
    if picks:
        return picks
        
    # --- Format 3: Inline like "🥇 第一名：#2 Skyhook（A-）"
    inline_pattern = re.compile(r'(🥇|🥈|🥉|🏅)\s*\**第[一二三四][名選][：:]\s*\**\s*\[?#?(\d+)\]?\s+([^(*（]+?)\s*[（(]([A-DS][+\-]?(?:\s*Place)?)[）)]')
    for medal_str, num, name, grade in inline_pattern.findall(text):
        if medal_str in medals:
            picks.append(TopPick(
                rank=medals[medal_str],
                rank_label=medal_str,
                horse_number=int(num),
                horse_name=name.strip(),
                grade=grade.strip(),
            ))
    if picks:
        return picks

    # --- Format 1: Block format with 🥇 **第一選** ... 馬號及馬名：8 My Phar Lady
    medal_positions = {}
    for medal, rank in medals.items():
        found = False
        for m in re.finditer(medal, text):
            # Safe extraction avoiding inline text prompt injection mentions
            start = m.start()
            if start > 0 and text[start-1] in '「["\'『':
                continue
            line_start = text.rfind('\n', 0, start)
            if start - line_start < 50:
                medal_positions[medal] = start
                found = True
                break
                
    for medal, rank in medals.items():
        if medal not in medal_positions:
            continue
        idx = medal_positions[medal]
        end_idx = len(text)
        for other_medal, other_idx in medal_positions.items():
            if other_medal != medal and idx < other_idx < end_idx:
                end_idx = other_idx
                
        block = text[idx:end_idx]
        
        hn_m = re.search(r'馬號[及與]?馬名[：:]\s*\*{0,2}\s*\[?(\d+)\]?\s+(.+?)(?:\n|$)', block)
        if not hn_m:
            hn_m = re.search(r'\[?(\d+)\]?\s+([A-Z][A-Za-z\s\'-]+?)(?:\n|$)', block)
        if not hn_m:
            continue
            
        # Avoid matching grade inside the format instructions
        # "必須嚴格按照最終評級的高低進行排名：`S > S- > ... > D`"
        grade_m = None
        for m in re.finditer(r'(?:評級|Grade)[^：:]*[：:]\s*\*{0,2}\s*`?\[?([A-DS][+\-]?)\]?`?', block):
            line_start = block.rfind('\n', 0, m.start())
            if '排名' not in block[line_start:m.start()]:
                grade_m = m
                break
                
        grade = grade_m.group(1) if grade_m else None
        
        picks.append(TopPick(
            rank=rank,
            rank_label=medal,
            horse_number=int(hn_m.group(1)),
            horse_name=hn_m.group(2).strip().rstrip('*').strip(),
            grade=grade,
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
        info['race_class'] = format_m.group(1).replace('級別', '').strip()
        info['distance'] = format_m.group(2).strip() + 'm'
    else:
        # Check | 賽事格局 | BM78 級別 / 1400m / Warwick Farm |
        format_alt = re.search(r'\|\s*賽事格局\s*\|\s*([^/]+?)\s*/\s*(\d{3,4})\s*m\s*/', text)
        if format_alt:
            info['race_class'] = format_alt.group(1).replace('級別', '').replace('讓磅賽', '').strip()
            info['distance'] = format_alt.group(2).strip() + 'm'
        else:
            class_m = re.search(r'(?:Class|Grade|Group)\s*[：:]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
            if not class_m:
                class_m = re.search(r'(BM\d+|G[123]|Listed|Maiden|CL\d|Open|Benchmark)', text, re.IGNORECASE)
            if class_m:
                info['race_class'] = class_m.group(1).replace('級別', '').strip() if class_m else None
        
    # Extract race name from AU "Race: Venue Race N" line
    race_name_m = re.search(r'Race:\s*(.+?)\s*$', text[:500], re.MULTILINE)
    if not race_name_m:
        # Fallback for MD header: # Race 1 — 1300m | Midway BM72 Handicap | Rosehill Gardens
        race_name_m = re.search(r'^#\s*Race\s*\d+\s*(?:—|-|\|)[^\|]+\|\s*([^\|]+)\s*\|', text, re.MULTILINE)
    if race_name_m:
        info['race_name'] = race_name_m.group(1).strip()
    
    going_m = re.search(r'(?:預測掛牌|場地掛牌|Track Condition|Going|天氣\s*/\s*場地)[：:]?\s*(?:\|\s*)?([^|\n]+)', text, re.IGNORECASE)
    if going_m:
        info['going'] = going_m.group(1).replace('*', '').strip()
    
    return info


def _parse_monte_carlo_table(text: str) -> list[dict]:
    """
    Parse Monte Carlo simulation results table from analysis markdown.
    Supports both V2 format (MC排名|馬號|馬名|MC勝率|預測賠率|法證排名|差異)
    and V1 format (排名|馬名|勝出率|Top 3率|Top 4率|平均名次|同Top4吻合).
    Returns list of dicts.
    """
    results = []
    
    # V2 format: MC排名 | 馬號 | 馬名 | MC 勝率 | 預測賠率 | 法證排名 | 差異
    v2_header = re.search(r'\|\s*MC排名\s*\|.*?馬號.*?馬名.*?MC\s*勝率.*?預測賠率.*?法證排名.*?差異\s*\|', text)
    if v2_header:
        # Find all table rows after header
        header_end = v2_header.end()
        remaining = text[header_end:]
        # Skip separator line
        lines = remaining.split('\n')
        for line in lines:
            line = line.strip()
            if not line.startswith('|') or line.startswith('|--') or line.startswith('|-'):
                if line.startswith('|--') or line.startswith('|-'):
                    continue
                if not line.startswith('|'):
                    break
                continue
            cols = [c.strip() for c in line.split('|')]
            cols = [c for c in cols if c]  # Remove empty first/last
            if len(cols) >= 7:
                try:
                    # Parse MC rank (may contain emoji)
                    mc_rank_str = re.sub(r'[^\d]', '', cols[0]) or '0'
                    mc_rank = int(mc_rank_str) if mc_rank_str else 0
                    horse_num = int(cols[1])
                    horse_name = cols[2].strip('*').strip()
                    win_prob_str = re.search(r'([\d.]+)%', cols[3])
                    win_prob = float(win_prob_str.group(1)) if win_prob_str else 0
                    odds_str = re.search(r'\$?([\d.]+)', cols[4])
                    predicted_odds = float(odds_str.group(1)) if odds_str else 0
                    orig_rank_str = re.search(r'#(\d+)', cols[5])
                    original_rank = int(orig_rank_str.group(1)) if orig_rank_str else None
                    agreement = cols[6].strip()
                    
                    results.append({
                        'mc_rank': mc_rank,
                        'horse_num': horse_num,
                        'name': horse_name,
                        'win_prob': win_prob,
                        'predicted_odds': predicted_odds,
                        'original_rank': original_rank,
                        'agreement': agreement,
                    })
                except (ValueError, IndexError):
                    continue
        return results
    
    # V1 format: | 排名 | 馬名 | 勝出率 | Top 3 率 | ...
    v1_header = re.search(r'\|\s*排名\s*\|.*?馬名.*?勝出率', text)
    if v1_header:
        header_end = v1_header.end()
        remaining = text[header_end:]
        lines = remaining.split('\n')
        rank_idx = 0
        for line in lines:
            line = line.strip()
            if not line.startswith('|'):
                break
            if line.startswith('|--') or line.startswith('|-'):
                continue
            cols = [c.strip() for c in line.split('|')]
            cols = [c for c in cols if c]
            if len(cols) >= 3:
                try:
                    rank_idx += 1
                    horse_name = cols[1].strip()
                    win_prob_str = re.search(r'([\d.]+)%', cols[2])
                    win_prob = float(win_prob_str.group(1)) if win_prob_str else 0
                    results.append({
                        'mc_rank': rank_idx,
                        'horse_num': 0,  # V1 doesn't always have horse_num
                        'name': horse_name,
                        'win_prob': win_prob,
                        'predicted_odds': round(100 / win_prob, 2) if win_prob > 0 else 0,
                        'original_rank': None,
                        'agreement': '',
                    })
                except (ValueError, IndexError):
                    continue
    
    return results


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
    
    # Allow underscore or space
    race_num_m = re.search(r'Race[_\s]*(\d+)', path.name, re.IGNORECASE)
    race_number = int(race_num_m.group(1)) if race_num_m else 0
    
    header_info = _parse_au_race_header(text)
    if not race_number and 'race_number' in header_info:
        race_number = header_info['race_number']
    
    # Clean race_name: strip ** markdown emphasis
    if header_info.get('race_name'):
        header_info['race_name'] = re.sub(r'\*{1,2}', '', header_info['race_name']).strip()
    
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
    
    # Extract Part 1 (battlefield overview / 戰場全景)
    # Multiple format variants exist across races:
    #   R1/R2/R4/R7/R8: "## [第一部分] 🗺️ 戰場全景" or "## [第一部分] 賽事環境與 Speed Map 預判"
    #   R3: "### 🌍 戰場全景 (Course & Environment)"
    #   R5/R6: "## 🗺️ 戰場全景"
    part1 = _extract_section(text,
        ['🗺️ 戰場全景', '🌍 戰場全景', '戰場全景', '賽事環境與 Speed Map 預判', '賽事環境'],
        ['[第二部分]', '## [第二部分]', '🐴 馬匹矩陣', '🐎 馬匹深度',
         '🔬 深度顯微鏡', '【No.', '[#1]', '[#2]', '[#3]']
    )
    
    # Extract pace prediction from battlefield overview table or standalone
    pace_prediction = None
    if part1:
        # Match: | 步速預期 (預判) | 快速 | or just 步速預判：快
        pace_m = re.search(r'步速預[判期][^\n]*?[：|]\s*([^\n|]+)', part1)
        if pace_m:
            pace_prediction = pace_m.group(1).strip()
        else:
            # Maybe it's just "Speed Map 預判："
            pace_m = re.search(r'Speed Map 預判[：:]\s*([^\n|]+)', part1)
            if pace_m:
                pace_prediction = pace_m.group(1).strip()
    
    # Top picks
    verdict = _extract_section(text,
        ['🏆 全場最終決策', '🏆 Top 3', '🏆 Top 4', '[第三部分]',
         'Top 4 位置精選', 'Top 3 位置精選', 'Top 4 精選排名', '精選排名'],
        ['[第四部分]', '🔒 COMPLIANCE', '```csv']
    )
    
    top_picks = []
    if verdict:
        top_picks = _parse_au_verdict_picks(verdict)
    
    # Fallback to after horses
    if not top_picks and last_horse_end > 0:
        after_horses = text[last_horse_end:]
        top_picks = _parse_au_verdict_picks(after_horses)
        
    if not top_picks:
        # Fallback to CSV block, limited to Top 4 and only if they look somewhat valid
        csv_picks = _parse_au_csv_block(text)
        if csv_picks:
            # If the CSV has > 4, try sorting by rank/grade or take first 4
            top_picks = csv_picks[:4]
    
    # SIP-RR01: Dual-scenario Top 4 (Good 4 / Soft 5 blocks)
    after_horses_text = text[last_horse_end:] if last_horse_end > 0 else text
    scenario_top_picks = _parse_au_scenario_top_picks(after_horses_text)
    
    # Determine dual-track status from horse data or scenario picks
    is_dual_track = scenario_top_picks is not None or any(
        h.alt_grade is not None for h in horses
    )
    primary_condition = None
    alt_condition = None
    alt_top_picks_list = []
    
    if is_dual_track:
        # Extract conditions from first horse with dual data
        for h in horses:
            if h.alt_condition:
                alt_condition = h.alt_condition
                break
        # Primary = going from race header
        primary_condition = header_info.get('going')
        
        # Build alt_top_picks: prefer scenario_top_picks from verdict, fallback to auto-sort
        if scenario_top_picks:
            # Find the alt scenario (non-primary) picks
            for label, picks in scenario_top_picks.items():
                # The alt scenario is the one that doesn't match primary_condition
                primary_trimmed = (primary_condition or '').split('(')[0].split('（')[0].strip()
                if primary_trimmed and label.strip().lower() != primary_trimmed.lower():
                    alt_top_picks_list = picks
                    if not alt_condition:
                        alt_condition = label
                    break
        
        # Fallback: auto-generate from horse alt_grades if no scenario picks found
        if not alt_top_picks_list:
            grade_order = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-']
            horses_with_alt = [(h, grade_order.index(h.alt_grade) if h.alt_grade in grade_order else 99) for h in horses if h.alt_grade]
            horses_with_alt.sort(key=lambda x: x[1])
            for rank, (h, _) in enumerate(horses_with_alt[:4], 1):
                alt_top_picks_list.append(TopPick(
                    rank=rank,
                    horse_number=h.horse_number,
                    horse_name=h.horse_name,
                    grade=h.alt_grade,
                ))
    
    # Back-fill missing grades from horse data
    horse_map = {h.horse_number: h for h in horses}
    for pick in top_picks:
        if not pick.grade and pick.horse_number in horse_map:
            pick.grade = horse_map[pick.horse_number].final_grade
    for pick in alt_top_picks_list:
        if not pick.grade and pick.horse_number in horse_map:
            pick.grade = horse_map[pick.horse_number].alt_grade or horse_map[pick.horse_number].final_grade

    # ──────────────────────────────────────────────
    # SIP-CSV: Parse trailing CSV data block for grades & missing horses
    # Format: race_id,horse_no,horse_name,rating,gear,grade_soft,grade_good,jockey,trainer,weight
    # ──────────────────────────────────────────────
    csv_data_match = re.search(r'```(?:csv|data)?\s*\n(race_id.+?)```', text, re.DOTALL)
    if csv_data_match:
        csv_text = csv_data_match.group(1).strip()
        reader = csv.DictReader(io.StringIO(csv_text), skipinitialspace=True)
        csv_horses = {}
        for row in reader:
            try:
                h_num = int(row.get('horse_no', 0))
                if h_num == 0:
                    continue
                h_name = (row.get('horse_name') or '').strip()
                g_soft = (row.get('grade_soft') or '').strip()
                g_good = (row.get('grade_good') or '').strip()
                jockey = (row.get('jockey') or '').strip()
                trainer = (row.get('trainer') or '').strip()
                weight_str = (row.get('weight') or '').strip()
                csv_horses[h_num] = {
                    'name': h_name, 'grade_soft': g_soft, 'grade_good': g_good,
                    'jockey': jockey, 'trainer': trainer, 'weight': weight_str,
                }
            except (ValueError, KeyError):
                continue

        # Determine which grade column is primary  
        primary_trimmed = (primary_condition or '').replace('*', '').strip().lower()
        use_soft_as_primary = 'soft' in primary_trimmed or not primary_trimmed

        # Back-fill grades for existing horses
        for h in horses:
            if h.horse_number in csv_horses:
                cd = csv_horses[h.horse_number]
                if not h.final_grade:
                    h.final_grade = cd['grade_soft'] if use_soft_as_primary else cd['grade_good']
                if not h.alt_grade:
                    h.alt_grade = cd['grade_good'] if use_soft_as_primary else cd['grade_soft']
                if not h.jockey and cd['jockey']:
                    h.jockey = cd['jockey']
                if not h.trainer and cd['trainer']:
                    h.trainer = cd['trainer']
                if not h.weight and cd['weight']:
                    h.weight = cd['weight'] + 'kg'

        # Create missing horses from CSV (e.g., horse 12 in R6 with no analysis header)
        for h_num, cd in csv_horses.items():
            if h_num not in horse_map:
                missing_horse = HorseAnalysis(
                    horse_number=h_num,
                    horse_name=cd['name'],
                    jockey=cd['jockey'] or None,
                    trainer=cd['trainer'] or None,
                    weight=(cd['weight'] + 'kg') if cd['weight'] else None,
                    final_grade=cd['grade_soft'] if use_soft_as_primary else cd['grade_good'],
                    alt_grade=cd['grade_good'] if use_soft_as_primary else cd['grade_soft'],
                    alt_condition=alt_condition,
                )
                horses.append(missing_horse)
                horse_map[h_num] = missing_horse

        # Re-backfill pick grades from updated horse data
        for pick in top_picks:
            if not pick.grade and pick.horse_number in horse_map:
                pick.grade = horse_map[pick.horse_number].final_grade
        for pick in alt_top_picks_list:
            if not pick.grade and pick.horse_number in horse_map:
                pick.grade = horse_map[pick.horse_number].alt_grade or horse_map[pick.horse_number].final_grade
        if scenario_top_picks:
            for label, picks in scenario_top_picks.items():
                primary_trimmed_lbl = (primary_condition or '').replace('*', '').strip().lower()
                is_alt = primary_condition and label.strip().lower() != primary_trimmed_lbl
                for pick in picks:
                    if not pick.grade and pick.horse_number in horse_map:
                        h = horse_map[pick.horse_number]
                        pick.grade = (h.alt_grade if is_alt else h.final_grade) or h.final_grade

    # Create stub horses for any picks that have no horse entry at all
    # (e.g., R7 horse #4 Overpass — in picks but no analysis block and no CSV)
    pick_horse_info = {}  # {horse_number: (name, grade)} — prefer entries with grades
    for pick in top_picks + alt_top_picks_list:
        if pick.horse_number not in pick_horse_info or (pick.grade and not pick_horse_info[pick.horse_number][1]):
            pick_horse_info[pick.horse_number] = (pick.horse_name, pick.grade)
    if scenario_top_picks:
        for label, picks in scenario_top_picks.items():
            for pick in picks:
                if pick.horse_number not in pick_horse_info or (pick.grade and not pick_horse_info[pick.horse_number][1]):
                    pick_horse_info[pick.horse_number] = (pick.horse_name, pick.grade)
    
    for h_num, (h_name, h_grade) in pick_horse_info.items():
        if h_num not in horse_map:
            stub = HorseAnalysis(
                horse_number=h_num,
                horse_name=h_name,
                final_grade=h_grade,
                alt_condition=alt_condition,
            )
            horses.append(stub)
            horse_map[h_num] = stub

    # Extract Part 1 (battlefield overview / 戰場全景)
    # Multiple format variants exist across races:
    #   R1/R2/R4/R7/R8: "## [第一部分] 🗺️ 戰場全景"
    #   R3: "### 🌍 戰場全景 (Course & Environment)" (no [第一部分], different emoji)
    #   R5/R6: "## 🗺️ 戰場全景" (separate from [第一部分] pre-flight)
    part1 = _extract_section(text,
        ['🗺️ 戰場全景', '🌍 戰場全景', '戰場全景'],
        ['[第二部分]', '## [第二部分]', '🐴 馬匹矩陣', '🐎 馬匹深度',
         '🔬 深度顯微鏡', '【No.', '[#1]', '[#2]', '[#3]']
    )
    
    # Also extract pace prediction from table format if it wasn't found above
    if not pace_prediction:
        pace_m = re.search(r'步速預測\s*\|\s*(.+?)(?:\s*\||\s*$)', text)
        if pace_m:
            pace_prediction = pace_m.group(1).strip()
        else:
            pace_m2 = re.search(r'步速預測[：:]\s*(.+?)(?:\n|$)', text)
            if pace_m2:
                pace_prediction = pace_m2.group(1).strip()
    
    # Extract speed map
    speed_map = _extract_section(text,
        ['📍 Speed Map', '速度地圖'],
        ['---', '## [第二部分]', '🐴 馬匹矩陣']
    )
    
    # Parse Monte Carlo simulation results (V2)
    monte_carlo_results = _parse_monte_carlo_table(text) or None
    
    return RaceAnalysis(
        race_number=race_number,
        distance=header_info.get('distance'),
        race_class=header_info.get('race_class'),
        going=header_info.get('going'),
        race_name=header_info.get('race_name'),
        horses=horses,
        top_picks=top_picks,
        scenario_top_picks=scenario_top_picks,
        primary_condition=primary_condition,
        alt_condition=alt_condition,
        is_dual_track=is_dual_track,
        alt_top_picks=alt_top_picks_list if is_dual_track else [],
        monte_carlo_results=monte_carlo_results,
        battlefield_overview=part1,
        pace_prediction=pace_prediction,
        speed_map=speed_map,
    )

