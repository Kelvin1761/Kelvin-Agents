#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys, re, json, os, argparse, io
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
create_hkjc_logic_skeleton.py — V9 Python-Native Skeleton Generator (V4.2 Schema)

Extracts factual data from HKJC Facts.md for a SINGLE horse and
pre-fills Logic.json. LLM only needs to fill [FILL] analysis fields.

Usage:
  python3 create_hkjc_logic_skeleton.py <facts_path> <race_num> <horse_num>
"""

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# V4.2: Import schema version constants
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkjc_schema import HKJC_SCHEMA_VERSION, HKJC_PLATFORM


def extract_race_header(facts_content):
    """Extract race-level info (venue, distance, class) from Facts.md header."""
    result = {}
    m = re.search(r'場地:\s*(.+?)\s*\|', facts_content)
    if m: result['venue'] = m.group(1).strip()
    m = re.search(r'距離:\s*(.+?)\s*\|', facts_content)
    if m: result['distance'] = m.group(1).strip()
    m = re.search(r'班次:\s*(.+?)(?:\n|$)', facts_content)
    if m: result['race_class'] = m.group(1).strip()
    return result


def extract_horse_block(facts_content, horse_num):
    """Extract the text block for a single horse from Facts.md."""
    pattern = rf'### 馬號 {horse_num} — '
    match = re.search(pattern, facts_content)
    if not match:
        return None

    start = match.start()
    # Find next horse header or end of file
    next_match = re.search(r'### 馬號 \d+ — ', facts_content[match.end():])
    if next_match:
        end = match.end() + next_match.start()
    else:
        end = len(facts_content)

    return facts_content[start:end]


def parse_horse_header(block):
    """Extract name, jockey, trainer, weight, barrier from header line."""
    m = re.search(
        r'### 馬號 (\d+) — (.+?) \| 騎師:\s*(.+?)(?: \| 練馬師:\s*(.+?))? \| 負磅:\s*(\d+) \| 檔位:\s*(\d+)',
        block
    )
    if not m:
        return {}
    return {
        'num': int(m.group(1)),
        'name': m.group(2).strip(),
        'jockey': m.group(3).strip(),
        'trainer': m.group(4).strip() if m.group(4) else '',
        'weight': int(m.group(5)),
        'barrier': int(m.group(6)),
    }


def _is_invalid_horse_name(name):
    clean = str(name or '').strip()
    return not clean or clean in {"?", "未知", "Unknown"} or clean.isdigit()


def validate_parsed_horse_header(data: dict, requested_horse_num: int) -> None:
    errors = []
    if not data:
        errors.append("parse_horse_header returned empty data")
    if data.get("num") != requested_horse_num:
        errors.append(f"horse number mismatch: requested {requested_horse_num}, parsed {data.get('num')}")
    if _is_invalid_horse_name(data.get("name")):
        errors.append(f"invalid horse_name: {data.get('name')!r}")
    try:
        if int(data.get("barrier", 0) or 0) <= 0:
            errors.append(f"invalid barrier: {data.get('barrier')!r}")
    except (TypeError, ValueError):
        errors.append(f"invalid barrier: {data.get('barrier')!r}")
    try:
        if int(data.get("weight", 0) or 0) <= 0:
            errors.append(f"invalid weight: {data.get('weight')!r}")
    except (TypeError, ValueError):
        errors.append(f"invalid weight: {data.get('weight')!r}")
    if errors:
        raise ValueError("; ".join(errors))


def parse_summary(block):
    """Extract last_6, days_since_last, season stats, wins, starts."""
    result = {}
    m = re.search(r'\*\*近六場:\*\*\s*(.+?)\s*\(', block)
    if not m:
        m = re.search(r'\*\*近六場:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m:
        result['last_6'] = m.group(1).strip()

    m = re.search(r'\*\*休後復出:\*\*\s*(\d+)', block)
    if m:
        result['days_since_last'] = int(m.group(1))
    else:
        result['days_since_last'] = 0

    m = re.search(r'\*\*統計:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m:
        result['season_stats'] = m.group(1).strip()
    
    # Extract wins/starts from career line: 生涯：N: W-P-S
    m = re.search(r'生涯：\s*(\d+)\s*[::∶]\s*(\d+)', block)
    if m:
        result['starts'] = int(m.group(1))
        result['wins'] = int(m.group(2))
    else:
        # Fallback: try 總場次 / 總勝
        m = re.search(r'(\d+)\s*戰\s*(\d+)\s*勝', block)
        if m:
            result['starts'] = int(m.group(1))
            result['wins'] = int(m.group(2))

    # Fallback 2: Count race table rows for starts, "| 1 |" finishes for wins
    if 'starts' not in result:
        # Count data rows in race tables (lines starting with "| N |" where N is a digit)
        table_rows = re.findall(r'^\|\s*\d+\s*\|', block, re.MULTILINE)
        if table_rows:
            result['starts'] = len(table_rows)
            # Count wins: finish position column (9th column, index 8 after split)
            wins = 0
            for line in block.split('\n'):
                if line.strip().startswith('|') and '|' in line:
                    cols = [c.strip() for c in line.split('|')]
                    # cols: ['', rownum, date, venue, dist, class, barrier, jockey, weight, finish, ...]
                    if len(cols) >= 10:
                        try:
                            if int(cols[1]) >= 1 and cols[9].strip() == '1':
                                wins += 1
                        except (ValueError, IndexError):
                            pass
            result['wins'] = wins

    # Fallback 3: Parse season_stats "(W-P-S-L)" for season wins
    if 'starts' not in result:
        ss = result.get('season_stats', '')
        m_ss = re.search(r'季內\s*\((\d+)-(\d+)-(\d+)-(\d+)\)', ss)
        if m_ss:
            w, p, s, l = int(m_ss.group(1)), int(m_ss.group(2)), int(m_ss.group(3)), int(m_ss.group(4))
            result['starts'] = w + p + s + l
            result['wins'] = w
    
    # Extract Last 10 recent form
    m = re.search(r'Last 10.*?[::∶]\s*`?([^`\n]+)`?', block)
    if m:
        result['recent_form'] = m.group(1).strip()
    
    # Extract track/surface records
    m = re.search(r'好地[::∶]\s*([^\|\n]+)', block)
    if m:
        result['good_record'] = m.group(1).strip()
    m = re.search(r'軟地[::∶]\s*([^\|\n]+)', block)
    if m:
        result['soft_record'] = m.group(1).strip()
    m = re.search(r'同場[::∶]\s*([^\|\n]+)', block)
    if m:
        result['course_record'] = m.group(1).strip()

    return result


def parse_recent_race(block):
    """Extract L400, position, consumption etc. from the MOST RECENT race row."""
    # Find the main race table (完整賽績檔案)
    table_start = re.search(r'完整賽績檔案.*?\n(\|[^\n]+\n\|[-\| ]+\n)', block, re.DOTALL)
    if not table_start:
        return {}

    # Get first data row after table header
    remaining = block[table_start.end():]
    first_line = remaining.split('\n')[0]
    if not first_line.startswith('|'):
        return {}

    cols = [c.strip() for c in first_line.split('|')]
    # Table format after split with leading |:
    # cols[0]='', cols[1]='1', cols[2]='22/03/2026', ..., cols[12]='22.59'(L400), cols[15]='6-7-5'(沿途位)

    result = {}
    if len(cols) >= 16:
        result['last_date'] = cols[2] if len(cols) > 2 else ''
        result['last_venue'] = cols[3] if len(cols) > 3 else ''
        result['last_distance'] = cols[4] if len(cols) > 4 else ''
        result['last_finish'] = cols[9] if len(cols) > 9 else ''
        result['last_margin'] = cols[10] if len(cols) > 10 else ''
        result['last_energy'] = cols[11] if len(cols) > 11 else ''
        result['raw_L400'] = cols[12] if len(cols) > 12 else ''
        result['last_xw'] = cols[13] if len(cols) > 13 else ''
        result['last_consumption'] = cols[14] if len(cols) > 14 else ''
        result['last_run_position'] = cols[15] if len(cols) > 15 else ''
    return result


def parse_trends(block):
    """Extract trend summaries from the statistics section."""
    result = {}

    m = re.search(r'L400:\s*(.+?)$', block, re.MULTILINE)
    if m: result['l400_trend'] = m.group(1).strip()

    m = re.search(r'能量:\s*(.+?)$', block, re.MULTILINE)
    if m: result['energy_trend'] = m.group(1).strip()

    m = re.search(r'引擎[:：]\s*(.+?)$', block, re.MULTILINE)
    if m: result['engine'] = m.group(1).strip()

    m = re.search(r'跑法[:：]\s*(.+?)$', block, re.MULTILINE)
    if m: result['running_style'] = m.group(1).strip()

    m = re.search(r'最佳距離:\s*(.+?)$', block, re.MULTILINE)
    if m: result['best_distance'] = m.group(1).strip()

    m = re.search(r'\*\*頭馬距離趨勢:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['margin_trend'] = m.group(1).strip()

    m = re.search(r'\*\*體重趨勢:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['weight_trend'] = m.group(1).strip()

    m = re.search(r'\*\*配備變動:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['gear'] = m.group(1).strip()

    m = re.search(r'\*\*評分變動:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['rating_trend'] = m.group(1).strip()

    m = re.search(r'走位 PI:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['position_pi'] = m.group(1).strip()

    m = re.search(r'\*\*綜合評估:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['formline_strength'] = m.group(1).strip()

    return result


import hashlib
import time
import secrets


# ── V4.2 Enrichment Parsers ──────────────────────────────────────────

def parse_medical_flags(block):
    """Scan race comments for medical events (口內有血, 喘鳴症, etc.)."""
    med_keywords = ['口內有血', '喘鳴症', '流鼻血', '傷患', '跛行', '呼吸問題', '受傷']
    flags = []
    # Look at each race's comment section
    lines = block.split('\n')
    for i, line in enumerate(lines):
        for kw in med_keywords:
            if kw in line:
                # Try to find which race this belongs to
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                race_num = None
                # Look backwards for race number context
                for j in range(i, max(0, i-5), -1):
                    rm = re.search(r'第(\d+)仗', lines[j])
                    if rm:
                        race_num = int(rm.group(1))
                        break
                flags.append({
                    'keyword': kw,
                    'race_num': race_num,
                    'date': date_match.group(1) if date_match else None,
                    'context': line.strip()[:80]
                })
    return flags


def parse_finish_time_summary(block):
    """Extract finish time deviation trend from Facts.md block."""
    result = {'deviation_raw': '', 'level': '', 'quality': '', 'full_block': '',
              'adj_deviation': '', 'adj_level': ''}
    m = re.search(r'完成時間偏差趨勢.*?\n(.*?)(?=\n\n|\n###|\n---|\Z)', block, re.DOTALL)
    if m:
        ft_block = m.group(0).strip()
        result['full_block'] = ft_block
        # Extract deviation sequence
        dm = re.search(r'偏差[::]\s*(.+?)(?:\s*→\s*趨勢|$)', ft_block)
        if dm:
            result['deviation_raw'] = dm.group(1).strip()
        # Extract level
        lm = re.search(r'水平[::]\s*(.+?)$', ft_block, re.MULTILINE)
        if lm:
            result['level'] = lm.group(1).strip()
        # Extract quality
        qm = re.search(r'含金量[::]\s*(.+?)$', ft_block, re.MULTILINE)
        if qm:
            result['quality'] = qm.group(1).strip()
        # V5.1: Extract pace-adjusted deviation
        am = re.search(r'步速修正偏差[::]\s*(.+?)$', ft_block, re.MULTILINE)
        if am:
            result['adj_deviation'] = am.group(1).strip()
        alm = re.search(r'修正水平[::]\s*(.+?)$', ft_block, re.MULTILINE)
        if alm:
            result['adj_level'] = alm.group(1).strip()
    return result


def parse_jockey_combo(block):
    """Extract jockey-horse combo stats from Facts.md block. V5.1."""
    result = {'current_jockey': '', 'combo_table': '', 'jockey_history': '', 'full_block': ''}
    m = re.search(r'人馬組合統計.*?\n(.*?)(?=\n\n📊|\n\n###|\n\n---|\n===|\Z)', block, re.DOTALL)
    if m:
        jc_block = m.group(0).strip()
        result['full_block'] = jc_block
        jm = re.search(r'今場騎師[::]\s*(.+?)$', jc_block, re.MULTILINE)
        if jm:
            result['current_jockey'] = jm.group(1).strip()
        tm = re.search(r'(騎師×此馬.*?\|.*?\n(?:\s*\|.*\n)*)', jc_block, re.DOTALL)
        if tm:
            result['combo_table'] = tm.group(1).strip()
        hm = re.search(r'(近6場騎師歷史.*?\n(?:\s*\|.*\n)*)', jc_block, re.DOTALL)
        if hm:
            result['jockey_history'] = hm.group(1).strip()
    return result


def parse_recent_6_detail(block):
    """Extract recent 6 race details with class, position, margin for stability."""
    results = []
    # Find the race results table (完整賽績檔案)
    table_match = re.search(r'完整賽績檔案.*?\n(\|[^\n]+\n\|[-| ]+\n)', block, re.DOTALL)
    if not table_match:
        return results
    remaining = block[table_match.end():]
    for line in remaining.split('\n')[:6]:
        if not line.strip().startswith('|'):
            break
        cols = [c.strip() for c in line.split('|')]
        if len(cols) >= 10:
            try:
                int(cols[1])  # Verify row number
            except (ValueError, IndexError):
                continue
            results.append({
                'race_num': cols[1],
                'date': cols[2] if len(cols) > 2 else '',
                'venue': cols[3] if len(cols) > 3 else '',
                'distance': cols[4] if len(cols) > 4 else '',
                'race_class': cols[5] if len(cols) > 5 else '',
                'finish': cols[9] if len(cols) > 9 else '',
                'margin': cols[10] if len(cols) > 10 else '',
            })
    return results


def parse_recent_position_detail(block, limit=5):
    """Extract recent positional evidence for race_shape scoring."""
    results = []
    table_match = re.search(r'完整賽績檔案.*?\n(\|[^\n]+\n\|[-| ]+\n)', block, re.DOTALL)
    if not table_match:
        return results
    remaining = block[table_match.end():]
    for line in remaining.split('\n'):
        if len(results) >= limit:
            break
        if not line.strip().startswith('|'):
            if results:
                break
            continue
        cols = [c.strip() for c in line.split('|')]
        if len(cols) < 16:
            continue
        try:
            int(cols[1])
        except (ValueError, IndexError):
            continue
        results.append({
            'race_num': cols[1],
            'date': cols[2] if len(cols) > 2 else '',
            'venue': cols[3] if len(cols) > 3 else '',
            'distance': cols[4] if len(cols) > 4 else '',
            'barrier': cols[6] if len(cols) > 6 else '',
            'finish': cols[9] if len(cols) > 9 else '',
            'margin': cols[10] if len(cols) > 10 else '',
            'l400': cols[12] if len(cols) > 12 else '',
            'xw': cols[13] if len(cols) > 13 else '',
            'consumption': cols[14] if len(cols) > 14 else '',
            'run_position': cols[15] if len(cols) > 15 else '',
        })
    return results


def parse_all_draw_history(block):
    """Extract barrier + finish + XW from ALL race tables in the horse block.

    Scans both '完整賽績檔案' and '較舊歷史賽績' tables to build a
    comprehensive draw-to-result dataset for the horse's entire career.
    Returns list of dicts with 'barrier', 'finish', 'xw' keys.
    """
    results = []
    for line in block.split('\n'):
        if not line.strip().startswith('|'):
            continue
        cols = [c.strip() for c in line.split('|')]
        if len(cols) < 16:
            continue
        try:
            int(cols[1])
        except (ValueError, IndexError):
            continue
        barrier_str = cols[6] if len(cols) > 6 else ''
        finish_str = cols[9] if len(cols) > 9 else ''
        xw_str = cols[13] if len(cols) > 13 else ''
        try:
            barrier = int(barrier_str)
            finish = int(finish_str)
        except (ValueError, TypeError):
            continue
        if barrier <= 0 or finish <= 0:
            continue
        results.append({
            'barrier': barrier,
            'finish': finish,
            'xw': xw_str,
        })
    return results


def parse_venue_transfer(block):
    """Extract venue transfer info from block."""
    m = re.search(r'場地轉換[::]\s*(.+?)$', block, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return '未知'


def parse_distance_fitness(block, today_distance=None):
    """Extract distance fitness data."""
    result = {'same_distance': '', 'best_distance': '', 'today_vs_best': ''}
    m = re.search(r'同程[::]\s*(.+?)(?:\||$)', block)
    if m:
        result['same_distance'] = m.group(1).strip()
    m = re.search(r'最佳距離[::]\s*(.+?)$', block, re.MULTILINE)
    if m:
        result['best_distance'] = m.group(1).strip()
    return result


def load_trackwork_for_horse(facts_path, race_num, horse_num):
    """Load pre-digested trackwork JSON for this race/horse if available."""
    facts_dir = Path(facts_path).parent
    candidates = sorted(facts_dir.glob(f"* Race {race_num} 晨操.json"))
    if not candidates:
        return {
            "status": "missing",
            "mode": "insufficient_data",
            "confidence": "low",
            "summary": {},
            "stability_digest": {
                "career_category": "insufficient_data",
                "data_status": "missing",
                "window_days": 21,
                "workout_load_21d": {
                    "active_days": 0, "blank_days": 21, "gallops": 0,
                    "trials": 0, "trotting": 0, "swimming": 0,
                    "aqua_walker": 0, "treadmill": 0,
                },
                "workout_intensity_trend": "unknown",
                "body_weight_delta_lbs": None,
                "maintenance_score": None,
                "readiness_score": None,
                "pattern_replay_score": None,
                "stability_positive_flags": [],
                "stability_risk_flags": [],
                "llm_stability_instruction": "晨操資料未能提取；不可憑空推斷晨操狀態。",
            },
            "flags": [],
        }
    try:
        with open(candidates[0], "r", encoding="utf-8") as f:
            payload = json.load(f)
        horse_payload = payload.get("horses", {}).get(str(horse_num))
        if not horse_payload:
            return {
                "status": "missing",
                "mode": "insufficient_data",
                "confidence": "low",
                "summary": {},
                "stability_digest": {
                    "career_category": "insufficient_data",
                    "data_status": "missing",
                    "window_days": payload.get("window_days", 21),
                    "workout_load_21d": {
                        "active_days": 0, "blank_days": payload.get("window_days", 21),
                        "gallops": 0, "trials": 0, "trotting": 0, "swimming": 0,
                        "aqua_walker": 0, "treadmill": 0,
                    },
                    "workout_intensity_trend": "unknown",
                    "body_weight_delta_lbs": None,
                    "maintenance_score": None,
                    "readiness_score": None,
                    "pattern_replay_score": None,
                    "stability_positive_flags": [],
                    "stability_risk_flags": [],
                    "llm_stability_instruction": "此馬沒有晨操 digest；不可憑空推斷。",
                },
                "flags": [],
            }
        return horse_payload
    except Exception as exc:
        return {
            "status": "failed",
            "mode": "insufficient_data",
            "confidence": "low",
            "summary": {},
            "stability_digest": {
                "career_category": "insufficient_data",
                "data_status": "failed",
                "window_days": 21,
                "workout_load_21d": {
                    "active_days": 0, "blank_days": 21, "gallops": 0,
                    "trials": 0, "trotting": 0, "swimming": 0,
                    "aqua_walker": 0, "treadmill": 0,
                },
                "workout_intensity_trend": "unknown",
                "body_weight_delta_lbs": None,
                "maintenance_score": None,
                "readiness_score": None,
                "pattern_replay_score": None,
                "stability_positive_flags": [],
                "stability_risk_flags": [],
                "llm_stability_instruction": f"晨操 digest 讀取失敗：{exc}",
            },
            "flags": [],
        }


def _parse_finish_numbers(last_6):
    nums = []
    for token in re.findall(r'\d+', str(last_6 or '')):
        try:
            nums.append(int(token))
        except ValueError:
            pass
    return nums[:6]


def normalize_trackwork_category(trackwork, data, is_debut):
    """Route trackwork digest to the right analytical category."""
    tw = json.loads(json.dumps(trackwork, ensure_ascii=False))
    digest = tw.setdefault("stability_digest", {})
    if not isinstance(digest, dict):
        digest = {}
        tw["stability_digest"] = digest

    finishes = _parse_finish_numbers(data.get("last_6", ""))
    recent_poor = bool(finishes[:3]) and all(x >= 6 for x in finishes[:3])
    wins = int(data.get("wins", 0) or 0)
    score = digest.get("pattern_replay_score")
    try:
        pattern_score = int(score) if score is not None else 0
    except (TypeError, ValueError):
        pattern_score = 0

    if is_debut:
        category = "debut_pressure"
        digest["llm_stability_instruction"] = (
            "初出馬 stability 預設 ➖，但可用備戰穩定性判斷；"
            "操練連貫、試閘次數、readiness、體重/健康可支持 ✅，"
            "操練中斷、trial反覆、健康風險可支持 ❌。"
        )
    elif recent_poor and wins > 0 and pattern_score >= 60:
        category = "pattern_replay"
        flags = digest.setdefault("stability_positive_flags", [])
        if pattern_score >= 70 and "TW_WIN_PATTERN_REPLAY" not in flags:
            flags.append("TW_WIN_PATTERN_REPLAY")
        digest["llm_stability_instruction"] = (
            "近績差馬要將晨操視為翻案入口；若 pattern_replay_score 高，"
            "stability 不可單憑近績死扣，需與晨操復刻/加壓訊號 50/50 判讀。"
        )
    elif digest.get("data_status") == "ok":
        category = "status_continuity"
        digest["llm_stability_instruction"] = (
            "正式賽績與晨操 digest 50/50 判讀；晨操反映今次賽前狀態與部署意圖。"
        )
    else:
        category = digest.get("career_category", "insufficient_data")

    digest["career_category"] = category
    tw["mode"] = category
    return tw


def normalize_person_name(value):
    value = str(value or '').strip()
    value = re.sub(r'\s+', '', value)
    return re.sub(r"[\s·・.\-']", "", value).lower()


def hydrate_trackwork_jockey_involvement(trackwork, race_jockey):
    """Repair legacy trackwork payloads where race-day jockey was not passed to digest."""
    if not isinstance(trackwork, dict):
        return trackwork
    jockey_key = normalize_person_name(race_jockey)
    if not jockey_key:
        return trackwork
    tw = json.loads(json.dumps(trackwork, ensure_ascii=False))
    summary = tw.setdefault("summary", {})
    if summary.get("race_jockey_involved"):
        return tw
    entries = tw.get("entries", []) or []
    involved = any(
        jockey_key in normalize_person_name(e.get("rider", ""))
        or jockey_key in normalize_person_name(e.get("details", ""))
        for e in entries
        if isinstance(e, dict)
    )
    if not involved:
        return tw
    summary["race_jockey_involved"] = True
    digest = tw.setdefault("stability_digest", {})
    flags = list(digest.get("stability_positive_flags", []) or [])
    if "賽日騎師有參與操練" not in flags:
        flags.append("賽日騎師有參與操練")
    digest["stability_positive_flags"] = flags
    return tw


def format_trackwork_line(trackwork):
    digest = trackwork.get("stability_digest", {}) if isinstance(trackwork, dict) else {}
    load = digest.get("workout_load_21d", {}) if isinstance(digest, dict) else {}
    positives = "、".join(digest.get("stability_positive_flags", []) or []) or "無"
    risks = "、".join(digest.get("stability_risk_flags", []) or []) or "無"
    status_zh = {'ok': '已提取', 'partial': '部分提取', 'missing': '缺資料', 'failed': '提取失敗'}.get(str(trackwork.get('status', 'missing')), str(trackwork.get('status', 'missing')))
    mode_zh = {
        'status_continuity': '狀態延續',
        'pattern_replay': '翻案復刻',
        'debut_pressure': '初出備戰',
        'insufficient_data': '資料不足',
    }.get(str(digest.get('career_category', 'insufficient_data')), str(digest.get('career_category', 'insufficient_data')))
    trend_zh = {'improving': '加強中', 'stable': '穩定', 'easing': '放緩', 'interrupted': '中斷', 'unknown': '未明'}.get(str(digest.get('workout_intensity_trend', 'unknown')), str(digest.get('workout_intensity_trend', 'unknown')))
    return (
        f"晨操資料{status_zh}，分類為「{mode_zh}」。近{digest.get('window_days', 21)}日"
        f"快操{load.get('gallops', 0)}課、試閘{load.get('trials', 0)}課、"
        f"踱步{load.get('trotting', 0)}課、游水{load.get('swimming', 0)}課，"
        f"空白日{load.get('blank_days', 0)}日；操練趨勢{trend_zh}。"
        f"維持分{digest.get('maintenance_score')}、備戰分{digest.get('readiness_score')}、"
        f"復刻分{digest.get('pattern_replay_score')}。正面訊號：{positives}；風險訊號：{risks}。"
        f"判讀指令：{digest.get('llm_stability_instruction', '')}"
    )


def format_trackwork_trainer_line(trackwork):
    summary = trackwork.get("summary", {}) if isinstance(trackwork, dict) else {}
    digest = trackwork.get("stability_digest", {}) if isinstance(trackwork, dict) else {}
    # Build rider role text (filter 未標明)
    roles = summary.get("rider_role_counts", {})
    named_roles = {k: v for k, v in roles.items() if k != "未標明"} if roles else {}
    rider_text = "、".join(f"{k}{v}次" for k, v in named_roles.items()) if named_roles else "未標明"
    race_jockey_text = "有" if summary.get("race_jockey_involved") else "沒有"
    gear = "、".join(summary.get("gear_training", []) or []) or "無"
    flags = "、".join(digest.get("stability_positive_flags", []) or []) or "無"
    trial_signal = summary.get('trial_sectional_signal', 'unknown')
    trial_signal_zh = {'strong': '強', 'medium': '中等', 'weak': '弱', 'unknown': '未明'}.get(str(trial_signal), str(trial_signal))
    return (
        f"賽日騎師{race_jockey_text}直接參與操練；操練者身份：{rider_text}。"
        f"操練配備：{gear}；"
        f"試閘段速訊號{trial_signal_zh}；備戰分{digest.get('readiness_score')}。"
        f"部署正面旗標：{flags}"
    )


def format_trackwork_health_line(trackwork):
    digest = trackwork.get("stability_digest", {}) if isinstance(trackwork, dict) else {}
    load = digest.get("workout_load_21d", {}) if isinstance(digest, dict) else {}
    return (
        f"active_days={load.get('active_days', 0)}, blank_days={load.get('blank_days', 0)}, "
        f"swimming={load.get('swimming', 0)}, aqua_walker={load.get('aqua_walker', 0)}, "
        f"risk_flags={digest.get('stability_risk_flags', [])}"
    )


def load_racecard_horse_block(facts_path, race_num, horse_num):
    """Load the horse-specific block from the racecard (排位表.md) file.

    The racecard contains sire/dam data that is absent from Facts.md for
    debut horses.  Returns the text block for the requested horse number,
    or '' if the file is not found.
    """
    facts_dir = Path(facts_path).parent
    candidates = sorted(facts_dir.glob(f"*Race {race_num} 排位表.md"))
    if not candidates:
        return ''
    try:
        with open(candidates[0], 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return ''
    # Split by horse number headers ("馬號: N")
    blocks = re.split(r'(?=馬號[:：]\s*\d+)', content)
    horse_str = str(horse_num)
    for blk in blocks:
        m = re.match(r'馬號[:：]\s*(\d+)', blk)
        if m and m.group(1) == horse_str:
            return blk
    return ''


def parse_debut_sire_profile(block, today_distance=None, racecard_block=''):
    """Extract a small debut pedigree profile.

    Searches *block* (Facts.md) first, then falls back to *racecard_block*
    (排位表.md) which always contains 父系/母系 for every horse.
    """
    profile = {
        "status": "missing",
        "sire": "",
        "dam": "",
        "distance_hint": "unknown",
        "precocity_hint": "unknown",
        "llm_instruction": (
            "初出馬必須補充 Sire 早熟度、Sire AWD/距離投射及母系早熟資料；"
            "若 Facts.md 無血統資料，請讀 05b_debut_guide.md 後標記資料缺口，"
            "不可憑空將 sectional 判為 ✅。"
        ),
    }
    # Search both blocks: Facts.md first, then racecard fallback
    combined_block = (block or '') + '\n' + (racecard_block or '')
    if not combined_block.strip():
        return profile
    sire_patterns = [
        r'父[:：]\s*([^|\n]+)',
        r'Sire[:：]\s*([^|\n]+)',
        r'父系[:：]\s*([^|\n]+)',
    ]
    dam_patterns = [
        r'母[:：]\s*([^|\n]+)',
        r'Dam[:：]\s*([^|\n]+)',
        r'母系[:：]\s*([^|\n]+)',
    ]
    for pat in sire_patterns:
        m = re.search(pat, combined_block, re.IGNORECASE)
        if m:
            profile["sire"] = m.group(1).strip()
            break
    for pat in dam_patterns:
        m = re.search(pat, combined_block, re.IGNORECASE)
        if m:
            profile["dam"] = m.group(1).strip()
            break
    if profile["sire"] or profile["dam"]:
        profile["status"] = "found"
        profile["llm_instruction"] = (
            f"以 Sire={profile['sire'] or 'N/A'} / Dam={profile['dam'] or 'N/A'} "
            f"評估早熟度與今仗 {today_distance or '目標路程'} 適性；"
            "sectional 可用血統距離投射 + 試閘速度/末段姿態 + 晨操 readiness 作替代證據。"
        )
    return profile


def build_debut_trial_profile(trackwork):
    """Summarize trial/readiness evidence for debut matrix routing."""
    digest = trackwork.get("stability_digest", {}) if isinstance(trackwork, dict) else {}
    load = digest.get("workout_load_21d", {}) if isinstance(digest, dict) else {}
    summary = trackwork.get("summary", {}) if isinstance(trackwork, dict) else {}
    flags = list(digest.get("stability_positive_flags", []) or [])
    readiness = digest.get("readiness_score")
    trial_times = summary.get("trial_times", []) if isinstance(summary, dict) else []
    trials = load.get("trials", 0)
    signal = summary.get("trial_sectional_signal", "unknown") if isinstance(summary, dict) else "unknown"
    return {
        "status": trackwork.get("status", "missing") if isinstance(trackwork, dict) else "missing",
        "trials_21d": trials,
        "trial_times": trial_times,
        "trial_sectional_signal": signal,
        "readiness_score": readiness,
        "positive_flags": flags,
        "llm_instruction": (
            "初出馬 trial/readiness 是 sectional 或 trainer_signal 替代證據；"
            "若 trials_21d=0 且無 trial_times，sectional 最高通常 ➖，除非 Sire + trainer evidence 極強。"
        ),
    }


def build_debut_readiness_flags(trackwork):
    digest = trackwork.get("stability_digest", {}) if isinstance(trackwork, dict) else {}
    summary = trackwork.get("summary", {}) if isinstance(trackwork, dict) else {}
    flags = list(digest.get("stability_positive_flags", []) or [])
    if summary.get("race_jockey_involved"):
        flags.append("RACE_JOCKEY_WORK_INVOLVED")
    readiness = digest.get("readiness_score")
    try:
        readiness_num = int(readiness) if readiness is not None else 0
    except (TypeError, ValueError):
        readiness_num = 0
    if readiness_num >= 80:
        flags.append("HIGH_READINESS_SCORE")
    return sorted(set(flags))


def _build_core_logic_scaffold(data):
    """V11: Build data-prompted natural prose scaffold for core_logic.
    Injects actual horse metrics into a guided prompt that produces
    ~100 words of flowing analysis WITHOUT visible tags.
    """
    name = data.get('name', '未知')
    last_6 = data.get('last_6', 'N/A')
    barrier = data.get('barrier', 'N/A')
    weight = data.get('weight', 'N/A')
    raw_l400 = data.get('raw_L400', 'N/A')
    engine = data.get('engine', 'N/A')
    running_style = data.get('running_style', 'N/A')
    days_since = data.get('days_since_last', 0)
    last_xw = data.get('last_xw', 'N/A')
    last_consumption = data.get('last_consumption', 'N/A')
    jockey = data.get('jockey', 'N/A')
    season_stats = data.get('season_stats', 'N/A')
    margin_trend = data.get('margin_trend', 'N/A')
    l400_trend = data.get('l400_trend', 'N/A')
    rating_trend = data.get('rating_trend', 'N/A')

    scaffold = (
        f"[FILL — 根據以下數據寫約100字流暢廣東話分析，"
        f"必須涵蓋：近態趨勢、檔位形勢、段速能力、整體前景。"
        f"唔好用 tag/標籤，直接寫自然段落；不得以 race-level speed_map 作核心論點。]\n"
        f"數據：{name} "
        f"近6仗={last_6}, "
        f"檔位={barrier}, "
        f"負磅={weight}磅, "
        f"L400={raw_l400}, "
        f"L400趨勢={l400_trend}, "
        f"引擎={engine}, "
        f"跑法={running_style}, "
        f"休賽={days_since}日, "
        f"走位={last_xw}, "
        f"消耗={last_consumption}, "
        f"騎師={jockey}, "
        f"季績={season_stats}, "
        f"頭馬距離趨勢={margin_trend}, "
        f"評分趨勢={rating_trend}"
    )
    return scaffold


def _load_draw_stats_json():
    """Load and cache draw stats JSON."""
    try:
        json_path = Path(__file__).parent.parent.parent.parent.parent / 'scripts' / 'hkjc_draw_stats.json'
        json_path = json_path.resolve()
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_draw_verdict_str(barrier, race_num=0):
    """Get draw verdict string for skeleton pre-fill from hkjc_draw_stats.json.
    Display order: 上名率(place) → 入Q率(quinella) → 勝率(win) — Top 3 priority.
    """
    ds = _load_draw_stats_json()
    if not ds or 'races' not in ds:
        return '數據不可用'
    barrier_int = int(barrier) if str(barrier).isdigit() else 0
    for race in ds.get('races', []):
        if race.get('race') == race_num:
            for d in race.get('draws', []):
                if d.get('draw') == barrier_int:
                    return f"{d['verdict']} (上名{d.get('place_pct','?')}%/入Q{d.get('quinella_pct','?')}%/勝{d['win_pct']}%)"
            # Race found but barrier not in data (e.g. barrier 13-14)
            return f'⚠️檔位{barrier_int}超出檔位統計數據範圍(最大檔{max(d["draw"] for d in race["draws"])})'
    # Race not found (e.g. race 10-11)
    return f'⚠️第{race_num}場無檔位統計數據'


def _get_full_draw_table(race_num=0):
    """Get the complete draw stats table for a race, formatted for LLM reasoning.
    Column order: 上名率 → 入Q率 → 勝率 (Top 3 priority).
    """
    ds = _load_draw_stats_json()
    if not ds or 'races' not in ds:
        return ''
    for race in ds.get('races', []):
        if race.get('race') == race_num:
            draws = race.get('draws', [])
            if not draws:
                return ''
            lines = [f'全場檔位統計 (第{race_num}場 {race.get("distance","?")}m {race.get("surface","?")}):',
                     '| 檔位 | 出賽 | 上名% | 入Q% | 勝率% | 判定 |',
                     '|------|------|-------|------|-------|------|']
            for d in sorted(draws, key=lambda x: x['draw']):
                lines.append(
                    f"| {d['draw']} | {d.get('starts','?')} | {d.get('place_pct','?')} | "
                    f"{d.get('quinella_pct','?')} | {d['win_pct']} | {d['verdict']} |")
            avg_place = race.get('avg_place_pct', '?')
            avg_win = race.get('avg_win_pct', '?')
            lines.append(f'平均上名率: {avg_place}% | 平均勝率: {avg_win}%')
            return '\n  '.join(lines)
    return f'⚠️第{race_num}場無檔位統計數據'


def compute_draw_position_fit(position_detail: list, today_barrier: int = 0,
                              full_draw_history: list = None) -> str:
    """Compute draw-to-position fit: does today's barrier match the horse's
    proven inner/outer preference?

    1. Groups recent races by XW into 內疊 (1-2W) vs 外疊 (3W+)
    2. Compares average finishing positions for each group
    3. Uses full_draw_history (all career races) for barrier-based stats
    4. Cross-references with today's barrier to flag match/mismatch

    Returns a multi-part digest for skeleton injection.
    """
    inner_finishes = []   # avg_wide <= 2.0
    outer_finishes = []   # avg_wide > 2.0

    # Use ALL races with XW data (recent + older)
    all_xw_sources = list(position_detail)
    if full_draw_history:
        for r in full_draw_history:
            xw_str = r.get('xw', '')
            if xw_str:
                all_xw_sources.append(r)

    # Deduplicate (position_detail races might overlap with full_draw_history)
    seen = set()
    for r in all_xw_sources:
        xw_str = r.get('xw', '')
        finish_str = str(r.get('finish', ''))
        barrier_str = str(r.get('barrier', ''))
        key = f"{barrier_str}_{finish_str}_{xw_str}"
        if key in seen or not xw_str or not finish_str:
            continue
        seen.add(key)
        try:
            finish = int(finish_str)
        except (ValueError, TypeError):
            continue
        wides = [int(x) for x in re.findall(r'(\d+)W', xw_str)]
        if not wides:
            continue
        avg_w = sum(wides) / len(wides)
        if avg_w <= 2.0:
            inner_finishes.append(finish)
        else:
            outer_finishes.append(finish)

    if not inner_finishes and not outer_finishes:
        return '走位數據不足'

    # Horse's personal draw history stats (barrier-based) — from ALL career races
    draw_inner_finishes = []  # barrier 1-4
    draw_mid_finishes = []    # barrier 5-8
    draw_outer_finishes = []  # barrier 9+
    history_source = full_draw_history if full_draw_history else position_detail
    for r in history_source:
        try:
            b = int(r.get('barrier', 0))
            f = int(r.get('finish', 0))
        except (ValueError, TypeError):
            continue
        if b <= 0 or f <= 0:
            continue
        if b <= 4:
            draw_inner_finishes.append(f)
        elif b <= 8:
            draw_mid_finishes.append(f)
        else:
            draw_outer_finishes.append(f)

    # Build stats
    parts = []
    if inner_finishes:
        avg_in = sum(inner_finishes) / len(inner_finishes)
        top3_in = sum(1 for f in inner_finishes if f <= 3)
        parts.append(f"走內(1-2W):{len(inner_finishes)}場 平均名次{avg_in:.1f} 上名{top3_in}次")
    if outer_finishes:
        avg_out = sum(outer_finishes) / len(outer_finishes)
        top3_out = sum(1 for f in outer_finishes if f <= 3)
        parts.append(f"走外(3W+):{len(outer_finishes)}場 平均名次{avg_out:.1f} 上名{top3_out}次")

    # Determine preference
    pref = 'neutral'  # inner / outer / neutral
    if inner_finishes and outer_finishes:
        avg_in = sum(inner_finishes) / len(inner_finishes)
        avg_out = sum(outer_finishes) / len(outer_finishes)
        diff = avg_out - avg_in
        if diff >= 2.0:
            pref = 'inner'
            parts.append('偏好: 明顯走內有利')
        elif diff >= 1.0:
            pref = 'inner'
            parts.append('偏好: 輕微走內有利')
        elif diff <= -2.0:
            pref = 'outer'
            parts.append('偏好: 明顯走外有利')
        elif diff <= -1.0:
            pref = 'outer'
            parts.append('偏好: 輕微走外有利')
        else:
            parts.append('偏好: 內外均可')
    elif inner_finishes:
        parts.append('偏好: 僅有走內數據')
    else:
        parts.append('偏好: 僅有走外數據')

    # Horse's personal draw history (3-way: inner/mid/outer)
    draw_parts = []
    if draw_inner_finishes:
        di_top3 = sum(1 for f in draw_inner_finishes if f <= 3)
        di_rate = di_top3 / len(draw_inner_finishes) * 100
        draw_parts.append(f"內檔(1-4)上名率{di_rate:.0f}%({di_top3}/{len(draw_inner_finishes)})")
    if draw_mid_finishes:
        dm_top3 = sum(1 for f in draw_mid_finishes if f <= 3)
        dm_rate = dm_top3 / len(draw_mid_finishes) * 100
        draw_parts.append(f"中檔(5-8)上名率{dm_rate:.0f}%({dm_top3}/{len(draw_mid_finishes)})")
    if draw_outer_finishes:
        do_top3 = sum(1 for f in draw_outer_finishes if f <= 3)
        do_rate = do_top3 / len(draw_outer_finishes) * 100
        draw_parts.append(f"外檔(9+)上名率{do_rate:.0f}%({do_top3}/{len(draw_outer_finishes)})")
    if draw_parts:
        parts.append('歷史檔位: ' + ' vs '.join(draw_parts))

    # Cross-reference with today's barrier
    if today_barrier > 0:
        is_inner_draw = today_barrier <= 4
        is_outer_draw = today_barrier >= 9
        is_mid_draw = 5 <= today_barrier <= 8

        if pref == 'inner':
            if is_inner_draw:
                parts.append(f'今仗檔{today_barrier}=內檔 → ✅匹配走內偏好')
            elif is_outer_draw:
                parts.append(f'今仗檔{today_barrier}=外檔 → ❌錯配! 偏好走內但被迫走外')
            else:
                parts.append(f'今仗檔{today_barrier}=中檔 → ⚠️需主動切入內疊')
        elif pref == 'outer':
            if is_outer_draw:
                parts.append(f'今仗檔{today_barrier}=外檔 → ✅匹配走外偏好')
            elif is_inner_draw:
                parts.append(f'今仗檔{today_barrier}=內檔 → ⚠️偏好走外但起步在內')
            else:
                parts.append(f'今仗檔{today_barrier}=中檔 → ➖中性')
        else:
            if is_inner_draw:
                parts.append(f'今仗檔{today_barrier}=內檔 → 內外均可，無特別影響')
            elif is_outer_draw:
                parts.append(f'今仗檔{today_barrier}=外檔 → 內外均可，無特別影響')
            else:
                parts.append(f'今仗檔{today_barrier}=中檔 → 內外均可，無特別影響')

    return ' | '.join(parts)


def compute_track_bias_from_draws(race_num: int) -> str:
    """Compute track bias (inner vs outer draw advantage) from draw stats.

    Compares average place_pct of low draws (1-4) vs high draws (9+).
    Returns a one-line bias indicator.
    """
    ds = _load_draw_stats_json()
    if not ds or 'races' not in ds:
        return '場地偏差數據不可用'
    for race in ds.get('races', []):
        if race.get('race') == race_num:
            draws = race.get('draws', [])
            if not draws:
                return ''
            inner = [d for d in draws if d['draw'] <= 4 and d.get('starts', 0) >= 10]
            outer = [d for d in draws if d['draw'] >= 9 and d.get('starts', 0) >= 10]
            if not inner or not outer:
                return '場地偏差樣本不足'
            avg_inner_place = sum(d.get('place_pct', 0) for d in inner) / len(inner)
            avg_outer_place = sum(d.get('place_pct', 0) for d in outer) / len(outer)
            diff = avg_inner_place - avg_outer_place
            inner_str = f"內檔(1-4)上名率{avg_inner_place:.1f}%"
            outer_str = f"外檔(9+)上名率{avg_outer_place:.1f}%"
            if diff >= 10:
                bias = '→ 明顯偏內 ⚠️外檔不利'
            elif diff >= 5:
                bias = '→ 輕微偏內'
            elif diff <= -10:
                bias = '→ 明顯偏外 ⚠️內檔不利'
            elif diff <= -5:
                bias = '→ 輕微偏外'
            else:
                bias = '→ 均勻無偏差'
            return f"{inner_str} vs {outer_str} {bias}"
    return f'⚠️第{race_num}場無場地偏差數據'

def build_skeleton(data, race_num=0, horse_block='', trackwork=None, facts_path=''):
    """Build JSON skeleton: real data pre-filled, analysis fields as [FILL].
    V4.2: Data-anchored reasoning with enrichment parsers.
    """
    name = data.get('name', '未知')
    raw_l400 = data.get('raw_L400', 'N/A')
    last_pos = data.get('last_run_position', 'N/A')
    last_6 = data.get('last_6', 'N/A')
    days_since = data.get('days_since_last', 0)
    season_stats = data.get('season_stats', 'N/A')
    margin_trend = data.get('margin_trend', 'N/A')
    weight_trend = data.get('weight_trend', 'N/A')
    gear = data.get('gear', 'N/A')
    rating_trend = data.get('rating_trend', 'N/A')
    l400_trend = data.get('l400_trend', 'N/A')
    energy_trend = data.get('energy_trend', 'N/A')
    engine = data.get('engine', 'N/A')
    running_style = data.get('running_style', 'N/A')
    best_dist = data.get('best_distance', 'N/A')
    barrier = data.get('barrier', 'N/A')
    weight = data.get('weight', 'N/A')
    jockey = data.get('jockey', 'N/A')
    trainer = data.get('trainer', 'N/A')
    last_xw = data.get('last_xw', 'N/A')
    last_consumption = data.get('last_consumption', 'N/A')
    last_finish = data.get('last_finish', 'N/A')
    last_margin_val = data.get('last_margin', 'N/A')
    good_rec = data.get('good_record', 'N/A')
    course_rec = data.get('course_record', 'N/A')
    position_pi = data.get('position_pi', 'N/A')
    formline_str = data.get('formline_strength', 'N/A')
    wins = data.get('wins', 0)
    starts = data.get('starts', 0)

    draw_verdict_str = _get_draw_verdict_str(barrier, race_num)
    nonce = 'SKEL_' + hashlib.md5(f"{name}_{time.time()}".encode('utf-8')).hexdigest()

    # ── V4.2 Enrichment ──
    med_flags = parse_medical_flags(horse_block) if horse_block else []
    med_str = '; '.join([f"第{f['race_num']}仗({f['date']}): ⚠️ {f['keyword']}" for f in med_flags]) if med_flags else '✅ 無醫療事故記錄'
    finish_time = parse_finish_time_summary(horse_block) if horse_block else {}
    ft_str = finish_time.get('full_block', '偏差趨勢未找到')
    ft_adj_str = finish_time.get('adj_deviation', '')
    ft_adj_level = finish_time.get('adj_level', '')
    recent_6 = parse_recent_6_detail(horse_block) if horse_block else []
    position_detail = parse_recent_position_detail(horse_block, limit=5) if horse_block else []
    vt_str = parse_venue_transfer(horse_block) if horse_block else '未知'
    jockey_combo = parse_jockey_combo(horse_block) if horse_block else {}

    # Format recent 6 with class
    r6_parts = []
    for r in recent_6:
        r6_parts.append(f"第{r['race_num']}仗({r['date']} {r['race_class']}): {r['finish']}名 {r['margin']}")
    r6_str = ' | '.join(r6_parts) if r6_parts else last_6
    pos_parts = []
    for r in position_detail:
        pos_parts.append(
            f"第{r['race_num']}仗({r['date']} {r['venue']} {r['distance']}): "
            f"沿途位={r['run_position']}, XW={r['xw']}, 消耗={r['consumption']}, "
            f"名次={r['finish']}, 距離={r['margin']}"
        )
    position_window_str = ' | '.join(pos_parts) if pos_parts else f"上仗走位={last_pos}, XW={last_xw}, 消耗={last_consumption}"

    # ── Trackwork pre-digest ──
    raw_trackwork = trackwork or {}

    # ── Debut/Import detection ──
    # V9.1 FIX: Only tag DEBUT if horse has 0 actual starts.
    # '新馬' can appear as race class name (e.g. 第五班新馬), NOT horse status.
    is_import = '自購馬' in horse_block or '海外賠馬' in horse_block
    hk_starts_m = re.search(r'港賽\s*(\d+)', horse_block)
    hk_starts = int(hk_starts_m.group(1)) if hk_starts_m else starts
    text_hints_debut = '新馬' in horse_block or '首出' in horse_block or '(無往績記錄)' in horse_block
    # Hard guard: a horse with actual starts > 0 is NEVER a debut
    is_debut = text_hints_debut and hk_starts == 0 and starts == 0
    if is_debut and is_import:
        career_tag = 'IMPORTED_DEBUT'
    elif is_debut:
        career_tag = 'DEBUT'
    elif hk_starts <= 5:
        career_tag = 'EARLY_CAREER'
    else:
        career_tag = 'ESTABLISHED'
    career_stage_label = '初出馬' if is_debut else (f'香港第{hk_starts + 1}場' if hk_starts <= 5 else '')
    debut_stability_note = (
        "[初出馬模板: 必讀 05b_debut_guide.md；stability 預設 ➖，但可按備戰穩定性評分。"
        "✅ 必須引用操練連貫、試閘次數、readiness、體重/健康等 evidence；"
        "❌ 必須引用操練中斷、trial反覆、健康/體重風險。不可將『無正式賽績』本身當 ❌。]\n"
        if is_debut else ""
    )
    debut_sectional_note = (
        "[初出馬模板: 必讀 05b_debut_guide.md；無正式 L400/EEM 時，段速質量改用 Sire 早熟度/Sire AWD 距離投射、"
        "試閘速度/末段姿態/催策程度、晨操 readiness 作替代證據；缺 Sire 或 trial/trackwork evidence 時不可憑空 ✅。]\n"
        if is_debut else ""
    )
    debut_shape_note = (
        "[初出馬模板: 形勢與走位只用檔位數據、今日預計位置、試閘跑法/出閘反應；不可引入 race-level speed_map 作此維度加減分。]\n"
        if is_debut else ""
    )
    debut_trainer_note = (
        "[初出馬模板: 騎練訊號為核心證據；操練加壓、賽日騎師親操、兩次或以上試閘、配備意圖、練馬師初出 KPI 可支持 ✅；"
        "有強訊號時不可只寫『待正式賽績驗證』。]\n"
        if is_debut else ""
    )
    debut_health_note = (
        "[初出馬模板: 馬匹健康/新鮮感不因無往績自動 ✅；以晨操連貫性、體重、試閘恢復與場地新鮮感判斷。]\n"
        if is_debut else ""
    )
    debut_formline_note = (
        "[初出馬模板: 賽績線強制 N/A/不計入，不可當 ❌；試閘對手只可低信心背景參考。]\n"
        if is_debut else ""
    )
    debut_class_note = (
        "[初出馬模板: 面對全新馬可 ➖；面對有經驗且有勝績對手通常 ❌，除非試閘+騎練部署屬極強。]\n"
        if is_debut else ""
    )
    debut_core_logic = (
        "[FILL — 初出馬專用格式，約100字流暢廣東話分析。必須涵蓋：(1) 無正式賽績，不可用正常近績模板；"
        "(2) Sire 早熟/距離適性、試閘/晨操/騎練部署係主要證據；(3) 檔位與初出適應風險。"
        "(4) 評級仍用 7 維矩陣 ✅ counts，但初出馬 final rating 最高 A。]"
        if is_debut else _build_core_logic_scaffold(data)
    )
    raw_trackwork = normalize_trackwork_category(raw_trackwork, {**data, 'wins': wins, 'starts': starts}, is_debut)
    raw_trackwork = hydrate_trackwork_jockey_involvement(raw_trackwork, jockey)
    tw_line = format_trackwork_line(raw_trackwork)
    tw_trainer_line = format_trackwork_trainer_line(raw_trackwork)
    tw_health_line = format_trackwork_health_line(raw_trackwork)
    # Load racecard block for sire/dam fallback (排位表.md always has bloodline data)
    racecard_block = ''
    if is_debut and facts_path:
        racecard_block = load_racecard_horse_block(facts_path, race_num, data.get('num', 0))
    debut_sire_profile = parse_debut_sire_profile(horse_block, data.get('distance', None), racecard_block=racecard_block) if is_debut else {}
    debut_trial_profile = build_debut_trial_profile(raw_trackwork) if is_debut else {}
    debut_readiness_flags = build_debut_readiness_flags(raw_trackwork) if is_debut else []
    debut_sire_line = f"[初出 Sire profile: {json.dumps(debut_sire_profile, ensure_ascii=False)}]\n" if is_debut else ""
    debut_trial_line = f"[初出 trial/readiness profile: {json.dumps(debut_trial_profile, ensure_ascii=False)}]\n" if is_debut else ""

    # ── Build data-anchored reasoning ──
    r_stability = (
        f"[Resource Check: 05_forensic_analysis.md / 穩定性+醫療事故作廢規則]\n"
        f"[近6場數據(含班次): {r6_str}]\n"
        f"[季內={season_stats}, 頭馬距離趨勢={margin_trend}]\n"
        f"[生涯標記: {career_tag}; 香港正式賽事場次={hk_starts}; {career_stage_label or '標準馬'}]\n"
        f"{debut_stability_note}"
        f"[晨操 digest: {tw_line}]\n"
        f"[晨操判讀規則: 正式賽績與晨操 50/50；近績差馬若有 pattern_replay_score/TW_WIN_PATTERN_REPLAY，不可單憑近績死扣]\n"
        f"[📂 必須閱讀 Facts.md「📋 完整賽績檔案」全部賽事記錄，唔淮得淨督近6場 — 需要綜合全部賽績判斷穩定性趨勢]\n"
        f"[🏥 健康掃描(作廢用): {med_str}]\n"
        f"[📎 必讀: 05_forensic_analysis.md (穩定性計算 + 醫療事故自動作廢規則 — 有醫療事故嘅場次需從穩定性計算中排除)]\n"
        f"→ [判讀: FILL]"
    )
    r_sectional = (
        f"[Resource Check: 03_engine_pace_context.md + 04_engine_corrections.md + 05_forensic_analysis.md / 引擎+段速修正+法醫作廢]\n"
        f"[引擎(速度分佈): {engine} | 最佳{best_dist}]\n"
        f"[上仗L400={raw_l400}, L400趨勢={l400_trend}, 能量趨勢={energy_trend}]\n"
        f"{debut_sectional_note}"
        f"{debut_sire_line}"
        f"{debut_trial_line}"
        f"[📂 必須閱讀 Facts.md「📋 完整賽績檔案」全部段速/消耗/走位數據，綜合判斷段速趨勢而唔淮淨督近6場]\n"
        f"[📊 必須閱讀「全段速剖面」(S1-S4/S5) — 分析各分段速度形態(均速型/漸進加速/快開慢收)同趨勢]\n"
        f"[📉 完成時間偏差: {ft_str}]\n"
        f"[🔧 步速修正偏差: {ft_adj_str if ft_adj_str else 'N/A'} | 修正水平: {ft_adj_level if ft_adj_level else 'N/A'}]\n"
        f"[💡 判讀指引: 原始偏差受步速影響，步速修正偏差更能反映馬匹真實速度水平。如標記[極慢/偏慢]，原始偏差有被誇大嘅可能]\n"
        f"[🏥 健康掃描(作廢用): {med_str}]\n"
        f"[📎 必讀: 03_engine_pace_context.md + 04_engine_corrections.md + 05_forensic_analysis.md (段速法醫 + 醫療事故作廢)]\n"
        f"→ [判讀: FILL]"
    )
    full_draw_table = _get_full_draw_table(race_num)
    barrier_int = int(barrier) if str(barrier).isdigit() else 0
    full_draw_hist = parse_all_draw_history(horse_block) if horse_block else []
    draw_pos_fit = compute_draw_position_fit(position_detail, barrier_int, full_draw_hist)
    track_bias = compute_track_bias_from_draws(race_num)
    r_race_shape = (
        f"[Resource Check: 05_forensic_analysis.md / 檔位數據 + 今日預計走位 + 近3-5仗走位消耗]\n"
        f"[近3-5仗走位窗口: {position_window_str}]\n"
        f"[檔位={barrier} ({draw_verdict_str}), 跑法={running_style}, 走位PI={position_pi}]\n"
        f"[🔄 檔位-走位匹配度: {draw_pos_fit}]\n"
        f"[🏟️ 場地偏差: {track_bias}]\n"
        f"[📊 {full_draw_table}]\n"
        f"{debut_shape_note}"
        f"[評分限制: matrix.race_shape 只可用檔位、今日位置、近仗走位消耗/受阻、場地偏差與檔位統計作 ✅/❌ 理由]\n"
        f"[📎 必讀: 05_forensic_analysis.md]\n"
        f"→ [判讀: FILL]"
    )
    jc_full = jockey_combo.get('full_block', '')
    r_trainer = (
        f"[Resource Check: 07b_trainer_signals.md + 07c_jockey_profiles.md / 騎練部署+人馬配搭]\n"
        f"[騎師={jockey}, 練馬師={trainer}]\n"
        f"[配備變動: {gear}]\n"
        f"{debut_trainer_note}"
        f"[晨操部署: {tw_trainer_line}]\n"
        f"[🏇 人馬組合統計: {jc_full if jc_full else '未找到'}]\n"
        f"[📎 必讀: 07b_trainer_signals.md + 07c_jockey_profiles.md — 比較今場騎師 vs 前任騎師嘅配搭勝率/位率/平均名次，換騎效應是正面定負面？]\n"
        f"→ [判讀: FILL]"
    )
    r_health = (
        f"[Resource Check: 05_forensic_analysis.md + 10a/10b/10c_track_*.md / 健康+場地新鮮感]\n"
        f"[休賽: {days_since}日, 體重趨勢: {weight_trend}]\n"
        f"[晨操健康: {tw_health_line}]\n"
        f"{debut_health_note}"
        f"[🏥 健康掃描: {med_str}]\n"
        f"[📎 健康評估規則: 有健康事故+復原證据(前3名/段速佳)=已復原(➖/✅); "
        f"有事故+未復原=風險(❌); 無事故=正常(✅)]\n"
        f"→ [判讀: FILL]"
    )
    r_formline = (
        f"[Resource Check: Facts.md 賽績線表格 + 05_forensic_analysis.md / 對手後續強度]\n"
        f"[賽績線強度={formline_str}]\n"
        f"[上仗名次={last_finish}, 距離差={last_margin_val}]\n"
        f"{debut_formline_note}"
        f"[📎 必讀: 05_forensic_analysis.md (賽績線)]\n"
        f"→ [判讀: FILL]"
    )
    r_class = (
        f"[Resource Check: 06_rating_engine.md / 級數優勢+負重互斥規則]\n"
        f"[{starts}戰{wins}勝, 評分趨勢={rating_trend}, 負磅={weight}]\n"
        f"[場地轉換: {vt_str}]\n"
        f"{debut_class_note}"
        f"[📎 必讀: 06_rating_engine.md + 場地模組 10a/10b/10c]\n"
        f"→ [判讀: FILL]"
    )

    def matrix_dim(score_hint, reasoning, rule_prefix):
        return {
            'score': score_hint,
            'confidence': '[FILL: High/Medium/Low/Unknown]',
            'trigger_rule': f'[FILL: {rule_prefix}_...]',
            'trigger_evidence': [
                '[FILL: concrete evidence 1]',
                '[FILL: concrete evidence 2]',
            ],
            'disqualifiers': [],
            'reasoning': reasoning,
        }

    # ── V10: Build trackwork instruction for LLM ──
    tw_digest = raw_trackwork.get('stability_digest', {}) if isinstance(raw_trackwork, dict) else {}
    tw_instruction = tw_digest.get('llm_stability_instruction', '')

    return {
        # ===== LOCKED DATA (Python pre-filled, LLM must NOT modify) =====
        '_locked': True,
        '_validation_nonce': nonce,
        'horse_name': name,
        'jockey': data.get('jockey', ''),
        'trainer': data.get('trainer', ''),
        'weight': data.get('weight', 0),
        'barrier': data.get('barrier', 0),
        'last_6_finishes': last_6,
        'days_since_last': days_since,
        'season_stats': season_stats,
        'trackwork': raw_trackwork,
        'career_tag': career_tag,
        'career_race_starts': hk_starts,
        'career_stage_label': career_stage_label,
        'debut_sire_profile': debut_sire_profile,
        'debut_trial_profile': debut_trial_profile,
        'debut_readiness_flags': debut_readiness_flags,

        # ===== V10: PYTHON-GUARANTEED DATA (compile template reads these directly) =====
        # LLM MUST NOT modify _data. Compile template renders ALL data from here.
        # LLM only needs to read WorkCard, analyze, then fill score + → [判讀: ...] text.
        '_data': {
            # ── 狀態與穩定性 (stability) ──
            'recent_6_detail': r6_str,
            'season_stats_line': season_stats,
            'margin_trend': margin_trend,
            'career_tag': career_tag,
            'career_stage_label': career_stage_label or '標準馬',
            'hk_starts': hk_starts,
            'trackwork_digest': tw_line,
            'trackwork_instruction': tw_instruction,
            'medical_flags': med_str,

            # ── 段速質量 (sectional) ──
            'engine_type': engine,
            'best_distance': best_dist,
            'raw_l400': raw_l400,
            'l400_trend': l400_trend,
            'energy_trend': energy_trend,
            'finish_time_block': ft_str,
            'finish_time_adj': ft_adj_str,
            'finish_time_adj_level': ft_adj_level,

            # ── 形勢與走位 (race_shape) ──
            'position_window': position_window_str,
            'draw_verdict': draw_verdict_str,
            'running_style': running_style,
            'position_pi': position_pi,
            'draw_position_fit': draw_pos_fit,
            'track_bias': track_bias,
            'full_draw_table': full_draw_table,

            # ── 騎練訊號 (trainer_signal) ──
            'jockey_name': jockey,
            'trainer_name': trainer,
            'gear_change': gear,
            'trackwork_trainer': tw_trainer_line,
            'jockey_combo_block': jc_full,

            # ── 馬匹健康 (horse_health) ──
            'days_since_last': days_since,
            'weight_trend': weight_trend,
            'trackwork_health': tw_health_line,

            # ── 賽績線 (form_line) ──
            'formline_strength': formline_str,
            'last_finish': last_finish,
            'last_margin': last_margin_val,

            # ── 級數優勢 (class_advantage) ──
            'total_starts': starts,
            'total_wins': wins,
            'rating_trend': rating_trend,
            'weight_carried': weight,
            'venue_transfer': vt_str,
        },

        # ===== ANALYSIS FIELDS (V10: LLM only fills score + judgment) =====

        'race_forgiveness': '[FILL — JSON Array 格式]',

        'matrix': {
            'stability':          matrix_dim('[FILL: ✅✅/✅/➖/❌/❌❌]', r_stability, 'STAB'),
            'sectional':          matrix_dim('[FILL: ✅✅/✅/➖/❌/❌❌]', r_sectional, 'SEC'),
            'race_shape':         matrix_dim('[FILL: ✅✅/✅/➖/❌/❌❌]', r_race_shape, 'SHAPE'),
            'trainer_signal':     matrix_dim('[FILL: ✅✅/✅/➖/❌/❌❌]', r_trainer, 'TS'),
            'horse_health':       matrix_dim('[FILL: ✅/➖/❌]', r_health, 'HEALTH'),
            'form_line':          matrix_dim('➖' if is_debut else '[FILL: ✅/➖/❌]', r_formline, 'FL'),
            'class_advantage':    matrix_dim('[FILL: ✅/➖/❌]', r_class, 'CLASS'),
        },

        'interaction_matrix': {
            'SYN': '[FILL or 無]',
            'CON': '[FILL or 無]',
            'CONTRA': '[FILL or 無]',
        },

        'base_rating': '[AUTO]',
        'fine_tune': {'direction': '[FILL: +/-/無]', 'trigger': '[FILL]', 'channel_a': '[FILL]', 'channel_b': '[FILL]'},
        'override': {'rule': '[FILL]'},
        'final_rating': '[AUTO]',
        'core_logic': debut_core_logic,
        'advantages': '[FILL]',
        'disadvantages': '[FILL]',
        'evidence_step_0_14': '[FILL]',
        'underhorse': {'triggered': False, 'condition': '', 'reason': ''},
        
        # ===== AUTO-ENRICHMENT (V3: auto-filled from Facts.md) =====
        'wins': wins,
        'starts': starts,
        'recent_form': data.get('recent_form', ''),
        'good_record': good_rec,
        'soft_record': data.get('soft_record', ''),
        'course_record': course_rec,
        'engine_type': engine,
        'running_style': running_style,
        'best_distance': best_dist,
        'formline_strength': formline_str,
        'is_debut': is_debut,
        'debut_runner': is_debut,
        'debut_trial_signal': '[FILL: weak/medium/strong/extreme]' if is_debut else '',
        'is_import': is_import,
        'hk_starts': hk_starts,
    }


def main():
    parser = argparse.ArgumentParser(description='HKJC V9 Skeleton Generator')
    parser.add_argument('facts_path', help='Path to Facts.md')
    parser.add_argument('race_num', type=int, help='Race number')
    parser.add_argument('horse_num', type=int, help='Horse number to extract')
    parser.add_argument('--output', help='Output Logic.json path')
    args = parser.parse_args()

    # Read Facts.md
    with open(args.facts_path, 'r', encoding='utf-8') as f:
        facts_content = f.read()

    # Extract horse block
    block = extract_horse_block(facts_content, args.horse_num)
    if not block:
        print(f'❌ 找不到馬號 {args.horse_num} 的數據', file=sys.stderr)
        sys.exit(1)

    # Parse all data
    header = parse_horse_header(block)
    try:
        validate_parsed_horse_header(header, args.horse_num)
    except ValueError as exc:
        print(f'❌ 馬號 {args.horse_num} 標題驗證失敗: {exc}', file=sys.stderr)
        sys.exit(1)
        
    summary = parse_summary(block)
    recent = parse_recent_race(block)
    trends = parse_trends(block)
    horse_data = {**header, **summary, **recent, **trends}

    # Build skeleton
    trackwork = load_trackwork_for_horse(args.facts_path, args.race_num, args.horse_num)
    skeleton = build_skeleton(horse_data, race_num=args.race_num, horse_block=block, trackwork=trackwork, facts_path=args.facts_path)

    # Determine output path
    json_path = args.output or os.path.join(
        os.path.dirname(args.facts_path),
        f'Race_{args.race_num}_Logic.json'
    )

    # Load existing JSON or create new
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
    else:
        # Extract race header for new JSON
        race_header = extract_race_header(facts_content)
        logic_data = {
            'schema_version': HKJC_SCHEMA_VERSION,
            'platform': HKJC_PLATFORM,
            'race_analysis': {
                'race_number': args.race_num,
                'race_class': race_header.get('race_class', ''),
                'distance': race_header.get('distance', ''),
                'venue': race_header.get('venue', ''),
                'speed_map': {},
            },
            'horses': {},
        }

    # Ensure horses dict
    if 'horses' not in logic_data:
        logic_data['horses'] = {}

    horse_key = str(args.horse_num)

    # Skip if horse already fully analyzed (no [FILL] remaining)
    existing = logic_data['horses'].get(horse_key, {})
    if existing and '[FILL]' not in json.dumps(existing):
        print(f'✅ 馬號 {args.horse_num}（{header.get("name", "")}）已完成分析，跳過。')
        sys.exit(0)

    # Write skeleton
    logic_data['horses'][horse_key] = skeleton

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(logic_data, f, ensure_ascii=False, indent=2)

    name = header.get('name', '?')
    print(f'✅ 已為馬號 {args.horse_num}（{name}）建立 JSON 骨架')
    print(f'   → L400: {recent.get("raw_L400", "N/A")}')
    print(f'   → 沿途位: {recent.get("last_run_position", "N/A")}')
    print(f'   → 消耗: {recent.get("last_consumption", "N/A")}')
    print(f'   → 檔位: {header.get("barrier", "N/A")} | 負磅: {header.get("weight", "N/A")}')


if __name__ == '__main__':
    main()
