#!/usr/bin/env python3
"""
generate_skeleton.py — AU Wong Choi Protocol Analysis Skeleton Generator
Generates a complete, gate-compliant analysis skeleton from Racecard.md.

Usage:
    python3 generate_skeleton.py <Racecard.md> --condition "Soft 6" [--output <output.md>]

The skeleton contains:
  - Part 1: 戰場全景 (pre-filled race metadata)
  - Part 2: All horse sections with P37 fact anchors + 11 emoji tags + {{LLM_FILL}} placeholders
  - Part 3: Verdict scaffold (ranking placeholders)
  - Part 4: Analysis traps scaffold
  - Part 5: CSV scaffold

Batch sizing: 3 horses per batch, in racecard order.
"""
import re
import sys
import math
import argparse
from pathlib import Path


# ──────────────────────────────────────────────
# Racecard Parser (reused from inject_fact_anchors.py)
# ──────────────────────────────────────────────

def parse_last10(last10_str: str) -> list[int]:
    """Decode Last 10 string into list of finishing positions (newest first)."""
    positions = []
    for ch in last10_str:
        if ch == 'x':
            continue
        elif ch == '0':
            positions.append(10)
        elif ch.isdigit():
            positions.append(int(ch))
    return positions


def parse_racecard(filepath: str) -> tuple[dict, list[dict]]:
    """Parse Racecard.md and return (race_metadata, horses_list)."""
    text = Path(filepath).read_text(encoding='utf-8')

    # Extract race number
    race_num_match = re.search(r'RACE\s+(\d+)', text)
    race_num = int(race_num_match.group(1)) if race_num_match else 0

    # Extract track info
    track_match = re.search(r'Track:\s*(.+?)\s*\|', text)
    track_name = track_match.group(1).strip() if track_match else 'Unknown'

    # Extract rail info
    rail_match = re.search(r'Rail:\s*(.+?)$', text, re.MULTILINE)
    rail_info = rail_match.group(1).strip() if rail_match else 'Unknown'

    race_meta = {
        'race_num': race_num,
        'track': track_name,
        'rail': rail_info,
    }

    # Parse horses
    horses = []
    horse_pattern = re.compile(
        r'^(\d+)\.\s+(.+?)\s*\((\d+)\)\s*$', re.MULTILINE
    )
    matches = list(horse_pattern.finditer(text))

    for i, match in enumerate(matches):
        horse_num = int(match.group(1))
        horse_name = match.group(2).strip()
        barrier = int(match.group(3))

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        # Skip scratched
        if 'Scratched' in block or 'status:Scratched' in block:
            continue

        # Trainer
        trainer_match = re.search(r'Trainer:\s*(.+?)\s*\|', block)
        trainer = trainer_match.group(1).strip() if trainer_match else 'Unknown'

        # Jockey
        jockey_match = re.search(r'Jockey:\s*(.+?)\s*\|', block)
        jockey = jockey_match.group(1).strip() if jockey_match else 'Unknown'

        # Weight
        weight_match = re.search(r'Weight:\s*(\S+)', block)
        weight = weight_match.group(1).strip() if weight_match else 'N/A'
        # Normalize: ensure 'kg' suffix
        if weight != 'N/A' and not weight.endswith('kg'):
            weight = weight + 'kg'

        # Rating
        rating_match = re.search(r'Rating:\s*(\d+)', block)
        rating = int(rating_match.group(1)) if rating_match else 0

        # Age
        age_match = re.search(r'Age:\s*(\d+)', block)
        age = int(age_match.group(1)) if age_match else 0

        # Career
        career_match = re.search(r'Career:\s*(\S+)', block)
        career = career_match.group(1) if career_match else 'N/A'

        # Last 10
        last10_match = re.search(r'Last 10:\s*(\S+)', block)
        last10_raw = last10_match.group(1) if last10_match else 'None'

        # Last race
        last_match = re.search(
            r'Last:\s*(\d+)/(\d+)\s+(\S+)\s+(.+?)$', block, re.MULTILINE
        )
        if last_match:
            last_finish = int(last_match.group(1))
            last_field = int(last_match.group(2))
            last_dist = last_match.group(3).strip()
            last_venue = last_match.group(4).strip()
        else:
            last_finish = None
            last_field = None
            last_dist = 'N/A'
            last_venue = 'N/A'

        decoded = parse_last10(last10_raw) if last10_raw != 'None' else []

        horses.append({
            'num': horse_num, 'name': horse_name, 'barrier': barrier,
            'trainer': trainer, 'jockey': jockey, 'weight': weight,
            'rating': rating, 'age': age,
            'career': career, 'last10_raw': last10_raw,
            'last_finish': last_finish, 'last_field': last_field,
            'last_dist': last_dist, 'last_venue': last_venue,
            'decoded': decoded,
        })

    return race_meta, horses


# ──────────────────────────────────────────────
# Fact Anchor Block Generator
# ──────────────────────────────────────────────

def generate_fact_anchor(h: dict) -> str:
    """Generate the P37 fact anchor block for a horse."""
    lines = [
        f"- **📌 Racecard 事實錨點 (由 Wong Choi 預填,嚴禁修改):**",
        f"  - Last 10 String: `{h['last10_raw']}`",
    ]
    if h['last_finish'] is not None:
        lines.append(
            f"  - 上仗結果: {h['last_finish']}/{h['last_field']}"
            f" @ {h['last_venue']} {h['last_dist']}"
        )
    else:
        lines.append(f"  - 上仗結果: N/A (初出馬)")

    lines.append(f"  - Career: {h['career']}")

    if h['decoded']:
        pos_str = '-'.join(str(p) for p in h['decoded'])
        lines.append(f"  - 近績序列解讀: `{pos_str}` (最新→最舊, 已跳過 trials)")

    if h['decoded'] and h['last_finish'] is not None:
        if h['decoded'][0] != h['last_finish']:
            lines.append(
                f"  - ⚠️ ALERT: Last 10 首位 ({h['decoded'][0]})"
                f" ≠ Last race finish ({h['last_finish']})"
            )
    return '\n'.join(lines)


# ──────────────────────────────────────────────
# Horse Analysis Section Generator
# ──────────────────────────────────────────────

def generate_horse_section(h: dict) -> str:
    """Generate the full analysis section skeleton for one horse."""
    anchor = generate_fact_anchor(h)

    return f"""### 【No.{h['num']}】{h['name']}(檔位:{h['barrier']}) | 騎師:{h['jockey']} / 練馬師:{h['trainer']} | 負重:{h['weight']} | 評分:{h['rating']}
**📌 情境標記:** `[{{{{LLM_FILL: 情境A-大優 / 情境B-有瑕疵 / 情境C-正路 / 情境D-默認}}}}]`
{anchor}

#### ⏱️ 近績解構與法醫視角
- **近績序列:** `{'-'.join(str(p) for p in h['decoded']) if h['decoded'] else '{{LLM_FILL}}'}` | **狀態週期:** `[{{{{LLM_FILL: First-up / Second-up / Third-up / Deep Prep}}}}]`
- **統計數據:** 季內 ({{{{LLM_FILL: W-P-S-U}}}})
**關鍵場次法醫:**
- [上仗]:名次 {h['last_finish'] if h['last_finish'] else '{{LLM_FILL}}'} | 班次落差 [{{{{LLM_FILL}}}}] | 段速質量 [{{{{LLM_FILL}}}}] | 競賽報告 [{{{{LLM_FILL}}}}]
- **趨勢總評:** [Momentum_Score: {{{{LLM_FILL}}}}]

#### 🐴 馬匹剖析
- **班次負重:** [Rating Trajectory; {{{{LLM_FILL}}}}]
- **引擎距離:** [{{{{LLM_FILL: Type A/B/C + 距離適性}}}}]
- **步態場地:** [{{{{LLM_FILL}}}}]
- **配備意圖:** [{{{{LLM_FILL}}}}]
- **人馬組合:** [{{{{LLM_FILL}}}}]

#### 🔬 段速法醫
- **原始 L600/L400:** {{{{LLM_FILL}}}} | **修正因素:** {{{{LLM_FILL}}}} | **修正判斷:** {{{{LLM_FILL}}}}
- **所示趨勢(近 3 仗):** `[{{{{LLM_FILL}}}}]`
- **賽績含金量:** {{{{LLM_FILL}}}}

#### ⚡ EEM 能量
- **上仗走位:** {{{{LLM_FILL}}}}
- **累積消耗:** `[{{{{LLM_FILL: 無 / 輕微 / 中等 / 嚴重}}}}]`
- **總評:** {{{{LLM_FILL}}}}

#### 📋 寬恕檔案
- **因素:** {{{{LLM_FILL}}}}
- **結論:** `[{{{{LLM_FILL: 可作準 / 不完全可作準 / 不可作準 / 無須寬恕}}}}]`

#### 🔗 賽績線
- **對手表現:** {{{{LLM_FILL}}}}
- **結論:** `[{{{{LLM_FILL: 強組 / 中等組 / 弱組 / N/A}}}}]`

#### 🧭 陣型預判
- 預計守位 (800m 處):{{{{LLM_FILL}}}},形勢 `[{{{{LLM_FILL: 極利 / 大優 / 一般 / 陷阱 / 劣勢}}}}]`

#### ⚠️ 風險儀表板
- 重大風險:`[{{{{LLM_FILL}}}}]` | 穩定指數:`[{{{{LLM_FILL}}}}/10]`

#### 📊 評級矩陣
- **狀態與穩定性** [核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **段速與引擎** [核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **EEM與形勢** [半核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **騎練訊號** [半核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **級數與負重** [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **場地適性** [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **賽績線** [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **裝備與距離** [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- **🔢 矩陣算術:** 核心✅={{{{LLM_FILL}}}} | 半核心✅={{{{LLM_FILL}}}} | 輔助✅={{{{LLM_FILL}}}} | 總❌={{{{LLM_FILL}}}} | 核心❌={{{{LLM_FILL: 有/無}}}} → 查表命中行={{{{LLM_FILL}}}}
- **基礎評級:** `[{{{{LLM_FILL}}}}]` | **規則**: `[{{{{LLM_FILL}}}}]`
- **微調:** `[{{{{LLM_FILL}}}}]`
- **覆蓋規則:** `[{{{{LLM_FILL}}}}]`

#### 💡 結論
> - **核心邏輯:** {{{{LLM_FILL: 2-3 句話，引用 ≥3 數據點}}}}
> - **最大競爭優勢:** {{{{LLM_FILL}}}}
> - **最大失敗原因:** {{{{LLM_FILL}}}}

⭐ **最終評級:** `[{{{{LLM_FILL}}}}]`
"""


# ──────────────────────────────────────────────
# Part 1: Battlefield Panorama
# ──────────────────────────────────────────────

def generate_part1(race_meta: dict, horses: list, condition: str) -> str:
    """Generate Part 1 戰場全景."""
    horse_list = ', '.join(f"{h['name']} ({h['barrier']})" for h in horses)

    return f"""# {race_meta.get('meeting_name', 'Race Meeting')} Race {race_meta['race_num']} 分析

## [第一部分] 🗺️ 戰場全景
| 項目 | 內容 |
|:---|:---|
| 賽事格局 | {{{{LLM_FILL: 短途/中距離 班次賽/讓磅賽}}}} |
| **賽事類型** | **`[STANDARD RACE 標準彎道賽]`** |
| 天氣 / 場地 | {condition} |
| 跑道偏差 | {{{{LLM_FILL}}}} |
| 步速預測 | {{{{LLM_FILL: Suicidal/Fast/Moderate/Crawl + 領放馬}}}} |
| 戰術節點 | {{{{LLM_FILL}}}} |

**📍 Speed Map (速度地圖):**
- 領放群:{{{{LLM_FILL}}}}
- 前中段:{{{{LLM_FILL}}}}
- 中後段:{{{{LLM_FILL}}}}
- 後上群:{{{{LLM_FILL}}}}

---

## [第二部分] 🔬 深度顯微鏡
"""


# ──────────────────────────────────────────────
# Part 3-5: Verdict, Traps, CSV
# ──────────────────────────────────────────────

def generate_verdict_scaffold(race_meta: dict) -> str:
    """Generate Part 3-5 verdict scaffold."""
    return f"""---

## [第三部分] 🏆 全場最終決策

**Speed Map 回顧:** {{{{LLM_FILL}}}} | 領放群: {{{{LLM_FILL}}}} | 受牽制: {{{{LLM_FILL}}}}

**Top 4 位置精選**

🥇 **第一選**
- **馬號及馬名:** {{{{LLM_FILL}}}}
- **評級與✅數量:** `[{{{{LLM_FILL}}}}]` | ✅ {{{{LLM_FILL}}}}
- **核心理據:** {{{{LLM_FILL}}}}
- **最大風險:** {{{{LLM_FILL}}}}

🥈 **第二選**
- **馬號及馬名:** {{{{LLM_FILL}}}}
- **評級與✅數量:** `[{{{{LLM_FILL}}}}]` | ✅ {{{{LLM_FILL}}}}
- **核心理據:** {{{{LLM_FILL}}}}
- **最大風險:** {{{{LLM_FILL}}}}

🥉 **第三選**
- **馬號及馬名:** {{{{LLM_FILL}}}}
- **評級與✅數量:** `[{{{{LLM_FILL}}}}]` | ✅ {{{{LLM_FILL}}}}
- **核心理據:** {{{{LLM_FILL}}}}
- **最大風險:** {{{{LLM_FILL}}}}

🏅 **第四選**
- **馬號及馬名:** {{{{LLM_FILL}}}}
- **評級與✅數量:** `[{{{{LLM_FILL}}}}]` | ✅ {{{{LLM_FILL}}}}
- **核心理據:** {{{{LLM_FILL}}}}
- **最大風險:** {{{{LLM_FILL}}}}

---

**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**
🥇 {{{{LLM_FILL}}}}:`[{{{{LLM_FILL: 🟢極高 / 🟢高 / 🟡中 / 🔴低}}}}]` — 最大威脅: {{{{LLM_FILL}}}}
🥈 {{{{LLM_FILL}}}}:`[{{{{LLM_FILL: 🟢極高 / 🟢高 / 🟡中 / 🔴低}}}}]` — 最大威脅: {{{{LLM_FILL}}}}

---

🎰 Exotic 建議:{{{{LLM_FILL}}}}

---

## [第四部分] 分析陷阱

- **市場預期警告:** {{{{LLM_FILL}}}}
- **🔄 步速逆轉保險 (Pace Flip Insurance):**
  - 若步速比預測更快 → Top 4 中最受惠:`{{{{LLM_FILL}}}}` | 最受損:`{{{{LLM_FILL}}}}`
  - 若步速比預測更慢 → Top 4 中最受惠:`{{{{LLM_FILL}}}}` | 最受損:`{{{{LLM_FILL}}}}`
- **整體潛在機會建議:** {{{{LLM_FILL}}}}

---

## [第五部分] 📊 數據庫匯出 (CSV)

```csv
race_id,horse_number,horse_name,win_odds,place_odds,verdict,risk_level
{{{{LLM_FILL: 由 compute_rating_matrix.py 自動生成}}}}
```
"""


# ──────────────────────────────────────────────
# Main Assembly
# ──────────────────────────────────────────────

def generate_skeleton(racecard_path: str, condition: str, meeting_name: str = None) -> str:
    """Generate the complete analysis skeleton."""
    race_meta, horses = parse_racecard(racecard_path)

    if meeting_name:
        race_meta['meeting_name'] = meeting_name
    else:
        # Try to infer from folder name
        parent = Path(racecard_path).parent.name
        race_date_match = re.search(r'(\d{2}-\d{2})', Path(racecard_path).name)
        date_str = race_date_match.group(1) if race_date_match else ''
        # Try extracting venue from parent folder
        venue_match = re.search(r'\d{4}-\d{2}-\d{2}\s+(.+?)(?:\s+Race|\s*$)', parent)
        if venue_match:
            race_meta['meeting_name'] = f"2026-{date_str.replace('-', '-')} {venue_match.group(1)}"
        else:
            race_meta['meeting_name'] = parent

    if not horses:
        return "❌ No active horses found in Racecard."

    # Build output
    output = []

    # Part 1
    output.append(generate_part1(race_meta, horses, condition))

    # Part 2: Horse sections in batches of 3
    batch_size = 3
    num_batches = math.ceil(len(horses) / batch_size)

    for batch_idx in range(num_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(horses))
        batch_horses = horses[batch_start:batch_end]
        batch_nums = ', '.join(str(h['num']) for h in batch_horses)

        output.append(f"### [Batch {batch_idx + 1}] (Horses {batch_nums})\n")

        for h in batch_horses:
            output.append(generate_horse_section(h))
            output.append("")  # blank line

    # Part 3-5
    output.append(generate_verdict_scaffold(race_meta))

    return '\n'.join(output)


def main():
    parser = argparse.ArgumentParser(
        description="AU Wong Choi Protocol — Analysis Skeleton Generator"
    )
    parser.add_argument("racecard", type=str, help="Path to Racecard.md")
    parser.add_argument("--condition", type=str, required=True,
                        help="Track condition (e.g., 'Soft 6', 'Good 4')")
    parser.add_argument("--meeting", type=str, default=None,
                        help="Meeting name (e.g., '2026-04-06 Rosehill Gardens')")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: stdout)")
    args = parser.parse_args()

    if not Path(args.racecard).exists():
        print(f"❌ File not found: {args.racecard}")
        sys.exit(1)

    skeleton = generate_skeleton(args.racecard, args.condition, args.meeting)

    if args.output:
        Path(args.output).write_text(skeleton, encoding='utf-8')
        print(f"✅ Skeleton generated: {args.output}")
        # Count horses and placeholders
        horse_count = skeleton.count('【No.')
        placeholder_count = skeleton.count('{{LLM_FILL')
        print(f"   📊 {horse_count} horses | {placeholder_count} placeholders to fill")
    else:
        print(skeleton)


if __name__ == '__main__':
    main()
