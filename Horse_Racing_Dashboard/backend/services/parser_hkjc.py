"""
HKJC Deep Parser — Parses full horse analysis from Analysis.txt files.
Supports both Kelvin format (with CSV block) and Heison format (without CSV block).
"""
import re
import csv
import io
from pathlib import Path
from typing import Optional

from models.race import (
    HorseAnalysis, RaceAnalysis, TopPick, MonteCarloPick, RatingDimension, RatingMatrix
)
from services.parser_au import _parse_monte_carlo_table


# ──────────────────────────────────────────────
# Horse block splitting
# ──────────────────────────────────────────────

# Kelvin format: **[1] 機械之星** or horsename with bracket number
# Heison format: **1 機械之星** or just number + name bold
HORSE_HEADER_RE = re.compile(
    r'^\*{0,2}(?:\[?(\d{1,2})\]?\s+(.+?))\*{0,2}\s*\|',
    re.MULTILINE
)

# Alternative: capture "### 【No.X】HorseName" (AU format but also seen in some HKJC)
HORSE_HEADER_ALT_RE = re.compile(
    r'^###\s*【No\.(\d+)】\s*(.+?)(?:（|[\(])', re.MULTILINE
)

# Happy Valley Kelvin format: **【No.1】 鄉村樂韻** | 騎師:... (no ### prefix)
HORSE_HEADER_HKJC_NO_RE = re.compile(
    r'^\*{0,2}【No\.(\d+)】\s*(.+?)\*{0,2}\s*\|',
    re.MULTILINE
)

# Heison simple: **1 光年魅力** | 
HORSE_HEADER_HEISON_RE = re.compile(
    r'^\*\*(\d{1,2})\s+(.+?)\*\*\s*\|', re.MULTILINE
)

# Heison markdown heading: ### 1 部族高手 | 周俊樂(-2) | ...
HORSE_HEADER_HEISON_MD_RE = re.compile(
    r'^###\s+(\d{1,2})\s+(.+?)\s*\|', re.MULTILINE
)

# Kelvin bracketed: **[1] 機械之星**
HORSE_HEADER_KELVIN_RE = re.compile(
    r'^\*\*\[(\d{1,2})\]\s+(.+?)\*\*', re.MULTILINE
)


def _split_into_horse_blocks(text: str) -> list[tuple[int, str, str]]:
    """Split analysis text into individual horse blocks.
    Returns list of (horse_number, horse_name, block_text)."""

    # Normalize fused separators: "---**3 Name**" → newline + "**3 Name**"
    # Some Heison files omit the newline between --- and the next horse header
    text = re.sub(r'---(\*\*\d{1,2}\s+)', r'---\n\1', text)

    # Try different header patterns — priority order matters
    patterns = [
        HORSE_HEADER_HEISON_MD_RE,
        HORSE_HEADER_HKJC_NO_RE,   # HV format: **【No.X】 Name** |
        HORSE_HEADER_HEISON_RE,
        HORSE_HEADER_KELVIN_RE,
        HORSE_HEADER_ALT_RE,
        HORSE_HEADER_RE,
    ]
    
    matches = []
    for pattern in patterns:
        matches = list(pattern.finditer(text))
        if len(matches) >= 2:  # Need at least 2 horses to validate pattern
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
        verdict_markers = ['#### [第三部分]', '## [第三部分]', '🏆 Top 4', '🏆 Top 3']
        block_text = text[start:end]
        for marker in verdict_markers:
            idx = block_text.find(marker)
            if idx > 0:
                block_text = block_text[:idx]
                break
        
        blocks.append((horse_num, horse_name, block_text.strip()))
    
    return blocks


# ──────────────────────────────────────────────
# Section extraction
# ──────────────────────────────────────────────

# Engine type mapping for HKJC label extraction
ENGINE_LABELS = {
    'A': '前領均速型',
    'B': '末段爆發型',
    'C': '持續衝刺型',
    'A/B': '混合型',
    'B/C': '混合型',
    'A/C': '混合型',
}


def _extract_engine_type_hkjc(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract engine type from HKJC horse analysis block.
    
    Supports:
    1. New format (future): 引擎距離：Type A (前領均速型) | ...
    2. Current format: 路程場地適性 section mentioning 引擎/前領/後追 patterns
    
    Returns: (engine_type, engine_type_label, engine_distance_summary)
    """
    # Try new explicit format first (for future analyses)
    m = re.search(
        r'引擎距離[：:]\s*\*{0,2}\s*(Type\s*([A-C](?:/[A-C])?)\s*(?:\(([^)]+)\))?[！!]?)\*{0,2}[。.]?\s*(.+?)(?:\n|$)',
        text
    )
    if m:
        type_code = m.group(2).strip()
        desc = m.group(3)
        full_line = m.group(0).strip()
        
        label = None
        if desc:
            cn_m = re.search(r'([\u4e00-\u9fff/]+型)', desc)
            if cn_m:
                label = cn_m.group(1)
            else:
                label = desc.strip()
        if not label:
            label = ENGINE_LABELS.get(type_code, type_code)
        
        engine_type = f'Type {type_code}'
        summary = full_line.replace('- **引擎距離：** ', '').replace('- **引擎距離：**', '').strip()
        return engine_type, label, summary
    
    # Fallback: infer from existing 馬匹分析 or 馬匹特性 section
    # Look for running style keywords
    style_section = text[:3000]  # Check first part of analysis
    
    # Pattern: 前領/居前/放頭 = Type A; 後上/後追/後段 = Type B
    front_keywords = ['前領型', '放頭馬', '居前型', '均速型', '前速型']
    back_keywords = ['後上型', '後追型', '爆發型', '後段追近', '末段爆發']
    
    front_count = sum(1 for kw in front_keywords if kw in style_section)
    back_count = sum(1 for kw in back_keywords if kw in style_section)
    
    if front_count > 0 and back_count == 0:
        return 'Type A', '前領均速型', None
    elif back_count > 0 and front_count == 0:
        return 'Type B', '末段爆發型', None
    elif front_count > 0 and back_count > 0:
        return 'Type A/B', '混合型', None
    
    return None, None, None

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
    
    # Find end
    if end_markers:
        end_pos = len(text)
        for marker in end_markers:
            pos = text.find(marker, start_pos + len(start_markers[0]))
            if 0 < pos < end_pos:
                end_pos = pos
        return text[start_pos:end_pos].strip()
    
    return text[start_pos:].strip()


def _extract_between(text: str, start: str, end: str) -> Optional[str]:
    """Extract text between two strings."""
    s = text.find(start)
    if s < 0:
        return None
    s += len(start)
    e = text.find(end, s)
    if e < 0:
        return text[s:].strip()
    return text[s:e].strip()


# ──────────────────────────────────────────────
# Horse analysis parsing
# ──────────────────────────────────────────────

def _strip_label(val: str) -> str:
    """Strip common Chinese prefix labels from header fields.
    e.g. '騎師:奧爾民' -> '奧爾民', '負磅:135' -> '135', '檔位:5' -> '5'
    """
    return re.sub(r'^(?:騎師|練馬師|負磅|檔位|Jockey|Trainer|Weight|Barrier)[：:]\s*', '', val).strip()


def _parse_jockey_trainer_weight_barrier(header_line: str) -> dict:
    """Parse header info like: **1 光年魅力** | 麥文堅 | 游達榮 | 135 | 10
    Or without Trainer: **1 千杯敬典** | 潘明輝 | 135 | 9
    Or Heison MD: ### 1 部族高手 | 周俊樂(-2) | 廖康銘 | 135磅 | 檔5
    Or HV format: **【No.1】 鄉村樂韻** | 騎師:奧爾民 | 練馬師:蔡約翰 | 負磅:135 | 檔位:5"""
    parts = [p.strip() for p in header_line.split('|')]
    result = {}
    if len(parts) < 2:
        return result

    raw_jockey = re.sub(r'\([^)]*\)', '', parts[1]).strip()  # strip (a-2) etc.
    result['jockey'] = _strip_label(raw_jockey)
    
    idx = 2
    # If the next part is not numeric (e.g. not '135'), it must be the Trainer
    # Handle HV prefix: "練馬師:蔡約翰" → "蔡約翰"
    raw_part = _strip_label(parts[idx]) if idx < len(parts) else ''
    part_stripped = re.sub(r'[磅kg]', '', raw_part).strip()
    if idx < len(parts) and not part_stripped.isdigit() and not part_stripped.replace('.', '', 1).isdigit():
        result['trainer'] = re.sub(r'\([^)]*\)', '', raw_part).strip()  # strip (C Fownes) etc.
        idx += 1
        
    if idx < len(parts):
        # Strip Chinese prefix + '磅' suffix: "負磅:135" → "135", "135磅" → "135"
        weight_raw = _strip_label(parts[idx])
        weight_val = re.sub(r'[磅kg]', '', weight_raw).strip()
        # Handle "實際129磅" or "實際" prefix
        weight_val = re.sub(r'實際\s*', '', weight_val).strip()
        result['weight'] = weight_val
        idx += 1
        
    if idx < len(parts):
        try:
            # Strip '檔位:' / '檔' prefix: "檔位:5" → "5", "檔5" → "5"
            barrier_raw = _strip_label(parts[idx])
            barrier_str = re.sub(r'[檔位]', '', barrier_raw).strip()
            result['barrier'] = int(barrier_str)
        except ValueError:
            pass
            
    return result


def _parse_rating_matrix(text: str) -> Optional[RatingMatrix]:
    """Parse the 📊 評級矩陣 section."""
    section = _extract_section(text, 
        ['**📊 評級矩陣', '📊 評級矩陣', '#### 📊 評級矩陣'],
        ['**14.2', '**💡', '💡 結論', '💡 評語', '⭐ 最終評級']
    )
    if not section:
        return None
    
    dimensions = []
    # Match formats:
    # Kelvin:  - 穩定性 [核心]: ❌ | 理據: 0/4三甲全差
    # Heison:  - 穩定性[核心]: ❌ | 近10仗0次入三甲，穩定性極低
    # Both: backticks and brackets around values are optional
    dim_re = re.compile(
        r'-\s*(.+?)\s*\[(\w+)\]:\s*`?\[?([✅➖❌])\]?`?\s*\|\s*(?:理據:\s*)?`?\[?(.*?)\]?`?\s*$',
        re.MULTILINE
    )
    for m in dim_re.finditer(section):
        dimensions.append(RatingDimension(
            name=m.group(1).strip(),
            category=m.group(2).strip(),
            value=m.group(3).strip(),
            rationale=m.group(4).strip()
        ))
    
    # Extract base rating
    base_re = re.search(r'14\.2\s*基礎評級[：:]\s*\[?([A-DS][+\-]?)\]?', text)
    adj_re = re.search(r'14\.2B\s*微調[：:]\s*\[?(.*?)\]?\s*\|', text)
    ovr_re = re.search(r'14\.3\s*覆蓋[：:]\s*\[?(.*?)\]?(?:\n|$)', text)
    
    return RatingMatrix(
        dimensions=dimensions,
        base_rating=base_re.group(1) if base_re else None,
        adjustment=adj_re.group(1).strip() if adj_re else None,
        override=ovr_re.group(1).strip() if ovr_re else None,
    )


def _parse_final_grade(text: str) -> Optional[str]:
    """Extract ⭐ 最終評級 value."""
    # Try multiple patterns
    patterns = [
        r'⭐\s*最終評級[：:]\s*\[?`?\[?([A-DS][+\-]?)\]?`?\]?',
        r'\*\*⭐\s*最終評級[：:]\*\*\s*\[?`?\[?([A-DS][+\-]?)\]?`?\]?',
        r'最終評級[：:]\s*`?\[?([A-DS][+\-]?)\]?`?',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def _parse_underhorse(text: str) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Parse 🐴⚡ 冷門馬訊號 / 潛力馬訊號.
    Returns: (triggered, condition, reason, level)
    Level: 'light' (🟢/微弱), 'moderate' (🟡/中度), 'strong' (🔴/強力), or None
    """
    section = _extract_section(text, ['🐴⚡', '冷門馬訊號', '潛力馬訊號'])
    if not section:
        return False, None, None, None
    
    if '未觸發' in section:
        return False, None, None, None
    
    triggered = '觸發' in section
    condition = None
    reason = None
    level = None
    
    # Detect 3-tier signal level
    if '強力觸發' in section or '🔴' in section:
        level = 'strong'
    elif '中度觸發' in section or '🟡' in section:
        level = 'moderate'
    elif '微弱觸發' in section or '輕微觸發' in section or '🟢' in section:
        level = 'light'
    elif triggered:
        level = 'light'  # Default to light if triggered but no level specified
    
    cond_m = re.search(r'受惠條件[：:]\s*(.+)', section)
    if cond_m:
        condition = cond_m.group(1).strip()
    
    reason_m = re.search(r'理由[：:]\s*(.+)', section)
    if reason_m:
        reason = reason_m.group(1).strip()
    
    # Heison inline format: [觸發] | [reason text]
    if triggered and not reason:
        inline_m = re.search(r'\[觸發\]\s*\|\s*\[(.+?)\]', section)
        if inline_m:
            reason = inline_m.group(1).strip()
    
    return triggered, condition, reason, level


def _parse_situation_tag(text: str) -> Optional[str]:
    """Parse 📌 情境標記."""
    # Kelvin format: 情境標記：`[情境A-升級]`
    m = re.search(r'情境標記[：:]\s*`?\[?(情境[A-D][^\]`]*)\]?`?', text)
    if m:
        return m.group(1).strip()
    # Heison format: **📌** `[情境D-默認]`  or  📌 `[情境C-正路]`
    m2 = re.search(r'`\[(情境[A-D][^\]`]*)\]`', text)
    if m2:
        return m2.group(1).strip()
    return None


def parse_horse_block(horse_num: int, horse_name: str, block: str) -> HorseAnalysis:
    """Parse a single horse analysis block into structured data."""
    
    # Header info
    first_line = block.split('\n')[0]
    header_info = _parse_jockey_trainer_weight_barrier(first_line)
    
    # Situation tag
    situation = _parse_situation_tag(block)
    
    # Recent form
    form_m = re.search(r'近六場[：:]\s*\*?\*?`?(.+?)`?\*?\*?\s*(?:\*\*)?(?:\(|$|\n)', block)
    recent_form = form_m.group(1).strip() if form_m else None
    
    # Form cycle
    cycle_m = re.search(r'狀態週期[：:]\s*`?(.+?)`?\s*(?:\n|$)', block)
    form_cycle = cycle_m.group(1).strip() if cycle_m else None
    
    # Statistics
    stats_m = re.search(r'統計[：:]\s*(.+?)(?:\n|$)', block)
    statistics = stats_m.group(1).strip() if stats_m else None
    
    # Key runs (逆境表現 + 際遇分析)
    key_runs = []
    adversity = _extract_section(block, ['逆境表現'], ['際遇分析', '馬匹分析', '🔬', '🐴'])
    if adversity:
        key_runs.append(adversity)
    experience = _extract_section(block, ['際遇分析'], ['馬匹分析', '🔬', '🐴', '📊'])
    if experience:
        key_runs.append(experience)
    
    # Trend summary
    trend_m = re.search(r'趨勢總評[：:]\s*(.+?)(?:\n\n|\n(?=\*\*)|$)', block, re.DOTALL)
    trend_summary = trend_m.group(1).strip() if trend_m else None
    
    # HKJC sections with emoji markers
    speed_forensics = _extract_section(block,
        ['🔬 段速法醫', '**🔬 段速法醫'],
        ['⚡ EEM', '**⚡ EEM', '📋', '📊', '💡']
    )
    
    eem_energy = _extract_section(block,
        ['⚡ EEM', '**⚡ EEM'],
        ['📋 寬恕', '**📋 寬恕', '🔗', '📊', '💡']
    )
    
    forgiveness = _extract_section(block,
        ['📋 寬恕', '**📋 寬恕'],
        ['🔗 賽績', '**🔗 賽績', '📊', '💡']
    )
    
    form_line = _extract_section(block,
        ['🔗 賽績線', '**🔗 賽績線'],
        ['📊 評級', '**📊 評級', '💡']
    )
    
    # Rating matrix
    rating_matrix = _parse_rating_matrix(block)
    
    # Final grade
    final_grade = _parse_final_grade(block)
    
    # Conclusion
    conclusion_section = _extract_section(block,
        ['💡 結論', '💡 評語', '**💡 結論', '**💡 評語', '💡 優勢', '**💡 優勢'],
        ['⭐ 最終評級', '🐴⚡ 冷門馬', '🐴⚡ 潛力馬', '---']
    )
    
    advantage = None
    risk = None
    core_logic = None
    if conclusion_section:
        # Try multiple patterns for core logic
        logic_m = re.search(r'(?:核心邏輯|結論)[：:]\s*\*{0,2}\s*(.+?)(?:\n|$)', conclusion_section)
        if logic_m:
            core_logic = logic_m.group(1).strip()
        adv_m = re.search(r'(?:最大)?競爭優勢[：:]\s*(.+?)(?:\n|$)', conclusion_section)
        if adv_m:
            advantage = adv_m.group(1).strip()
        risk_m = re.search(r'(?:最大)?(?:失敗|風險)(?:原因|風險)?[：:]\s*(.+?)(?:\n|$)', conclusion_section)
        if risk_m:
            risk = risk_m.group(1).strip()
    
    # Underhorse signal
    uh_triggered, uh_condition, uh_reason, uh_level = _parse_underhorse(block)
    
    # Engine type extraction
    engine_type, engine_label, engine_summary = _extract_engine_type_hkjc(block)
    
    return HorseAnalysis(
        horse_number=horse_num,
        horse_name=horse_name,
        jockey=header_info.get('jockey'),
        trainer=header_info.get('trainer'),
        weight=header_info.get('weight'),
        barrier=header_info.get('barrier'),
        situation_tag=situation,
        recent_form=recent_form,
        form_cycle=form_cycle,
        statistics=statistics,
        key_runs=key_runs if key_runs else None,
        trend_summary=trend_summary,
        speed_forensics=speed_forensics,
        eem_energy=eem_energy,
        forgiveness_file=forgiveness,
        form_line=form_line,
        engine_type=engine_type,
        engine_type_label=engine_label,
        engine_distance_summary=engine_summary,
        rating_matrix=rating_matrix,
        final_grade=final_grade,
        conclusion=conclusion_section,
        core_logic=core_logic,
        advantage=advantage,
        risk=risk,
        underhorse_triggered=uh_triggered,
        underhorse_level=uh_level,
        underhorse_condition=uh_condition,
        underhorse_reason=uh_reason,
        raw_text=block,
    )


# ──────────────────────────────────────────────
# Top 4 extraction
# ──────────────────────────────────────────────

def _parse_csv_block(text: str, race_number: int = 0) -> list[TopPick]:
    """Parse the CSV data block at end of analysis (primary method).
    Supports two CSV layouts:
    Layout A (English): Race, Distance, Jockey, Trainer, Number, Name, Rating
    Layout B (Chinese): 馬號, 馬名, 騎師, 練馬師, 檔位, 負磅, 評級, 預測排名, 核心論點
    """
    csv_match = re.search(r'```csv\s*\n(.+?)```', text, re.DOTALL)
    if not csv_match:
        return []
    
    picks = []
    csv_text = csv_match.group(1).strip()
    lines = csv_text.strip().split('\n')
    
    # Detect header and column layout
    first = lines[0]
    first_lower = first.lower()
    has_header = ('race' in first_lower or 'horse' in first_lower or 
                  'number' in first_lower or '馬號' in first or 
                  '馬名' in first or 'Race' in first or 'Name' in first)
    
    # Detect layout from header or first data line
    is_chinese_layout = '馬號' in first or '馬名' in first
    if not is_chinese_layout and has_header:
        # English header — check if Number column is at index 4
        is_chinese_layout = False
    elif not has_header:
        # No header — detect from first data line
        parts = [p.strip() for p in lines[0].split(',')]
        # If first field is a small number (horse number) and second contains Chinese, it's Chinese layout
        if parts and parts[0].isdigit() and len(parts) >= 7:
            try:
                num = int(parts[0])
                if num <= 20:  # Horse numbers are typically 1-14
                    is_chinese_layout = True
            except ValueError:
                pass
    
    data_lines = lines[1:] if has_header else lines
    
    # Limit to reasonable number of top picks (max 4)
    MAX_PICKS = 4
    
    for rank, line in enumerate(data_lines, 1):
        if rank > MAX_PICKS:
            break
        parts = [p.strip() for p in line.split(',')]
        try:
            if is_chinese_layout and len(parts) >= 3:
                # Layout B: 馬號(0), 馬名(1), ..., 評級(6)
                horse_num = int(parts[0])
                horse_name = parts[1].strip()
                grade = parts[6].strip() if len(parts) > 6 else (parts[2].strip() if len(parts) > 2 else None)
            elif len(parts) >= 6:
                # Layout A: Race(0), Distance(1), Jockey(2), Trainer(3), Number(4), Name(5), Rating(6)
                horse_num = int(parts[4])
                horse_name = parts[5].strip()
                grade = parts[6].strip() if len(parts) > 6 else None
            else:
                continue
            
            picks.append(TopPick(
                rank=rank,
                horse_number=horse_num,
                horse_name=horse_name,
                grade=grade,
            ))
        except (ValueError, IndexError):
            continue
    # Validate picks: reject if horse numbers are 0 or names lack Chinese chars
    # (indicates CSV was a performance table, not a top picks table)
    import re as _re
    valid_picks = [p for p in picks if p.horse_number > 0 and _re.search(r'[\u4e00-\u9fff]', p.horse_name)]
    return valid_picks if len(valid_picks) >= len(picks) * 0.5 else []


def _parse_verdict_top_picks(text: str) -> list[TopPick]:
    """Parse Top 4/Top 3 from verdict section (fallback method).
    Supports multiple Heison formats:
    Format A:
        🥇 **第一選**
        - **馬號及馬名：** 13 時時歡聞
        - **評級與✅數量：** [A+] | ✅ 7
    Format B (inline with em-dash):
        **🥇 第一選 — 11 劍無情 (S-)**
    Format C (table):
        | 11 | 劍無情 | **S-** | reason |
    """
    picks = []
    
    # --- Format B: Inline with em-dash
    # **🥇 第一選 — 11 劍無情 (S-)** or 🥇 第一選 — 11 劍無情 (S-)
    inline_re = re.compile(
        r'(?:🥇|🥈|🥉|🏅)\s*(?:\*\*)?第([一二三四])選\s*(?:—|-|–)\s*(\d+)\s+(.+?)\s*[（(]([A-DS][+\-]?(?:\(⚠️[^)]*\))?)\s*[）)]',
    )
    inline_matches = list(inline_re.finditer(text))
    rank_map = {'一': 1, '二': 2, '三': 3, '四': 4}
    
    if inline_matches:
        for m in inline_matches:
            rank = rank_map.get(m.group(1), 0)
            grade = m.group(4).strip()
            # Clean grade: remove ⚠️ annotations
            grade_clean = re.sub(r'[⚠️()]', '', grade).strip()
            if rank:
                picks.append(TopPick(
                    rank=rank,
                    horse_number=int(m.group(2)),
                    horse_name=m.group(3).strip().rstrip('*'),
                    grade=grade_clean if grade_clean else grade,
                ))
        if picks:
            return picks
    
    # --- Format A: Block with 第X選 header + 馬號及馬名
    pick_headers = re.finditer(
        r'(?:🥇|🥈|🥉|🏅)\s*\*\*第([一二三四])選\*\*',
        text
    )
    
    headers = list(pick_headers)
    
    for i, hdr in enumerate(headers):
        rank = rank_map.get(hdr.group(1), 0)
        start = hdr.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        
        # Extract horse number and name — handles: "3 皇龍飛將", "[3] 皇龍飛將"
        name_m = re.search(
            r'馬號及馬名[:：]\s*(?:\*\*)?\s*\[?(\d+)\]?\s+(.+?)(?:\*\*)?\s*$',
            block, re.MULTILINE
        )
        if not name_m:
            # Alternate: without bold, with optional brackets
            name_m = re.search(r'\[?(\d+)\]?\s+([\u4e00-\u9fff\w]+)', block)
        
        # Extract grade — supports [A+] (brackets), `A+` (backticks), and bare A+ after 評級
        grade_m = re.search(r'(?:\[|`)([A-DS][+\-]?)(?:\]|`)', block)
        if not grade_m:
            # Fallback: bare grade after 評級 keyword, e.g. "評級與✅數量：** A+ | ✅"
            grade_m = re.search(r'評級[^:：]*[:：]\s*(?:\*\*)?\s*([A-DS][+\-]?)(?:\s|\|)', block)
        
        # Extract checkmarks count
        check_m = re.search(r'✅\s*(\d+)', block)
        
        if name_m:
            picks.append(TopPick(
                rank=rank,
                horse_number=int(name_m.group(1)),
                horse_name=name_m.group(2).strip(),
                grade=grade_m.group(1) if grade_m else None,
                checkmarks=int(check_m.group(1)) if check_m else None,
            ))
    
    return picks


# ──────────────────────────────────────────────
# Race-level parsing
# ──────────────────────────────────────────────

def _parse_race_header(text: str) -> dict:
    """Parse race specifications from Part 1."""
    info = {}
    
    # Race number
    race_m = re.search(r'第(\d+)場', text)
    if race_m:
        info['race_number'] = int(race_m.group(1))
    
    # Distance  
    dist_m = re.search(r'(\d{3,4})(?:米|m)', text)
    if dist_m:
        info['distance'] = dist_m.group(1) + 'm'
    
    # Class
    class_m = re.search(r'(第[一二三四五]班|[一二三四五]班)', text)
    if class_m:
        info['race_class'] = class_m.group(1)
    
    # Track
    track_m = re.search(r'(草地|全天候|泥地)\s*(?:-\s*)?[「"]?([A-C])[」"]?\s*賽道', text)
    if track_m:
        info['track'] = f"{track_m.group(1)} {track_m.group(2)} 賽道"
    
    # Venue
    venue_m = re.search(r'(沙田|跑馬地)', text)
    if venue_m:
        info['venue'] = venue_m.group(1)
    
    # Race name — try explicit 賽事名稱 first
    name_m = re.search(r'賽事名稱[：:]\s*\*{0,2}(.+?)\*{0,2}\s*(?:\n|$)', text)
    if name_m:
        info['race_name'] = name_m.group(1).strip()
    else:
        # Fallback: extract from 賽事規格 line — race name is typically the last segment
        # Format: 第1場 / 第五班 / 2200米 / 草地 B 賽道 / 跑馬地 / 屯門讓賽
        spec_m = re.search(r'賽事規格[：:]\s*\*{0,2}(.+?)(?:\n|$)', text)
        if spec_m:
            segments = [s.strip() for s in spec_m.group(1).split('/')]
            # Race name is after venue (沙田/跑馬地) — take remaining segments
            venue_idx = None
            for i, seg in enumerate(segments):
                if '沙田' in seg or '跑馬地' in seg:
                    venue_idx = i
                    break
            if venue_idx is not None and venue_idx + 1 < len(segments):
                race_name = ' '.join(segments[venue_idx + 1:]).strip().strip('*')
                if race_name and not re.match(r'^第\d+場$', race_name):
                    info['race_name'] = race_name
    
    # Pace prediction — try backtick-delimited first, then generic
    pace_m = re.search(r'步速預測[：:]\s*\*{0,2}\s*`([^`]+)`', text)
    if not pace_m:
        pace_m = re.search(r'步速預測[：:]\s*\*{0,2}\s*(.+?)\s*(?:\n|$)', text)
    if pace_m:
        val = pace_m.group(1).strip().strip('*').strip('`').strip()
        if val and val != '*':
            info['pace_prediction'] = val
    
    return info


def parse_hkjc_analysis(filepath: str) -> Optional[RaceAnalysis]:
    """Parse a complete HKJC Analysis.txt file into structured data.
    
    Supports:
    - Kelvin format (with CSV block, detailed 11-field analysis)
    - Heison format (without CSV block, variable depth)
    """
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
    
    # Extract race number from filename
    race_num_m = re.search(r'Race[_\s]+(\d+)', path.name)
    race_number = int(race_num_m.group(1)) if race_num_m else 0
    
    # Parse Part 1 header
    header_info = _parse_race_header(text)
    if not race_number and 'race_number' in header_info:
        race_number = header_info['race_number']
    
    # Extract Part 1 (battlefield overview)
    part1 = _extract_section(text, 
        ['[第一部分]', '## [第一部分]', '#### [第一部分]'],
        ['[第二部分]', '## [第二部分]', '#### [第二部分]']
    )
    
    # Extract Part 3 (verdict) - Handle dynamic batch numbers (can be Part 3, 5, 7, etc.)
    part3 = _extract_section(text,
        ['最終結論 (The Verdict)', '最終結論', '賽事總結與預期崩潰點', '[第三部分]', '## [第三部分]', '#### [第三部分]'],
        ['分析盲區', '[第四部分]', '## [第四部分]', '#### [第四部分]', '```csv', '🔒 COMPLIANCE', '🐴⚡ 冷門馬總計']
    )
    
    # Extract Part 4 (blind spots)
    part4 = _extract_section(text,
        ['分析盲區', '[第四部分]', '## [第四部分]', '#### [第四部分]'],
        ['```csv', '🔒 COMPLIANCE', '📂 分析檔案更新完成', '---']
    )
    
    # Parse individual horses
    horse_blocks = _split_into_horse_blocks(text)
    horses = []
    for h_num, h_name, h_block in horse_blocks:
        horse = parse_horse_block(h_num, h_name, h_block)
        horses.append(horse)
    
    # Parse Top picks — try CSV block first, then verdict section, then full text fallback
    top_picks = _parse_csv_block(text, race_number)
    if not top_picks and part3:
        top_picks = _parse_verdict_top_picks(part3)
    if not top_picks:
        # Fallback: parse full text (handles cases where part3 extraction is too narrow)
        top_picks = _parse_verdict_top_picks(text)
    
    # Confidence
    conf_m = re.search(r'信心指數[：:]\s*\[?(.+?)\]?(?:\n|$)', text)
    confidence = conf_m.group(1).strip() if conf_m else None
    
    # Key variable
    key_m = re.search(r'關鍵變數[：:]\s*(.+?)(?:\n|$)', text)
    key_variable = key_m.group(1).strip() if key_m else None
    
    # Pace flip
    pace_flip = _extract_section(text,
        ['步速逆轉保險', '步速逆轉'],
        ['緊急煞車', '---', '[第四部分]']
    )
    
    # Underhorse signals summary
    uh_summary = _extract_section(text,
        ['冷門馬總計', '潛力馬總計', 'Underhorse Signal Summary'],
        ['```csv', '🔒', '---']
    )
    uh_signals = None
    if uh_summary:
        uh_signals = [line.strip() for line in uh_summary.split('\n') 
                      if line.strip().startswith('- 🐴⚡')]
    
    # Monte Carlo simulation table (HKJC format uses #### 📊 Monte Carlo 概率模擬)
    monte_carlo = _parse_monte_carlo_table(text)
    
    return RaceAnalysis(
        race_number=race_number,
        distance=header_info.get('distance'),
        race_class=header_info.get('race_class'),
        track=header_info.get('track'),
        venue=header_info.get('venue'),
        race_name=header_info.get('race_name'),
        pace_prediction=header_info.get('pace_prediction'),
        horses=horses,
        top_picks=top_picks,
        confidence=confidence,
        key_variable=key_variable,
        pace_flip=pace_flip,
        underhorse_signals=uh_signals,
        battlefield_overview=part1,
        verdict_text=part3,
        blind_spots=part4,
        monte_carlo_simulation=monte_carlo if monte_carlo else None,
    )
