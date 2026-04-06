#!/usr/bin/env python3
"""
generate_skeleton_hkjc.py — HKJC Wong Choi Protocol Analysis Skeleton Generator
Generates a complete, gate-compliant analysis skeleton from HKJC 排位表.md.

Usage:
    python3 generate_skeleton_hkjc.py <排位表.md> [--output <output.md>]

The skeleton contains:
  - Part 1: 🗺️ 戰場全景 (table + Speed Map + 步速瀑布推演)
  - Part 2: All horse sections with 11 emoji tags + {{LLM_FILL}} placeholders
  - Part 3: Verdict scaffold (Top 4 ranking)
  - Part 4: Blind Spots scaffold
  - Part 5: CSV Metadata scaffold

This script reads the HKJC Chinese racecard format:
  馬號: 1
  馬名: 榮利雙收
  賽績: 6/6/3/1/6/4
  負磅: 135
  騎師: 班德禮
  檔位: 5
  練馬師: 大衛希斯
  評分: 59
  ...
"""
import re
import sys
import argparse
from pathlib import Path


# ──────────────────────────────────────────────
# HKJC Racecard Parser
# ──────────────────────────────────────────────

def parse_hkjc_racecard(filepath: str) -> tuple[dict, list[dict]]:
    """Parse HKJC 排位表.md and return (race_metadata, horses_list)."""
    text = Path(filepath).read_text(encoding='utf-8')

    # --- Race metadata ---
    race_meta = {}

    def extract(key):
        m = re.search(rf'^{key}:\s*(.+)$', text, re.MULTILINE)
        return m.group(1).strip() if m else ''

    race_meta['場次'] = extract('場次')
    race_meta['賽事名稱'] = extract('賽事名稱')
    race_meta['日期'] = extract('日期')
    race_meta['地點'] = extract('地點')
    race_meta['場地'] = extract('場地')
    race_meta['賽道'] = extract('賽道')
    race_meta['路程'] = extract('路程')
    race_meta['評分'] = extract('評分')
    race_meta['班次'] = extract('班次')
    race_meta['獎金'] = extract('獎金')

    # Derive race number
    race_num_match = re.search(r'第(\d+)場', race_meta['場次'])
    race_meta['race_num'] = int(race_num_match.group(1)) if race_num_match else 0

    # --- Horses ---
    horses = []

    # Split into horse blocks by "馬號:" markers
    horse_blocks = re.split(r'(?=^馬號:\s*\d+)', text, flags=re.MULTILINE)

    for block in horse_blocks:
        num_match = re.match(r'^馬號:\s*(\d+)', block)
        if not num_match:
            continue

        def block_extract(key):
            m = re.search(rf'^{key}:\s*(.+)$', block, re.MULTILINE)
            return m.group(1).strip() if m else ''

        horse = {}
        horse['num'] = int(num_match.group(1))
        horse['name'] = block_extract('馬名')
        horse['form'] = block_extract('賽績')
        horse['weight'] = int(block_extract('負磅') or '0')
        horse['jockey'] = block_extract('騎師')
        horse['barrier'] = int(block_extract('檔位') or '0')
        horse['trainer'] = block_extract('練馬師')
        horse['rating'] = int(block_extract('評分') or '0')
        horse['rating_change'] = block_extract('評分+/-')
        horse['age'] = int(block_extract('馬齡') or '0')
        horse['days_since'] = block_extract('上賽距今日數')
        raw_gear = block_extract('配備')
        # Guard against empty gear or accidental match of next field
        if raw_gear and not raw_gear.startswith('父系') and not raw_gear.startswith('母系'):
            horse['gear'] = raw_gear
        else:
            horse['gear'] = ''
        horse['body_weight'] = block_extract('排位體重')

        horses.append(horse)

    return race_meta, horses


# ──────────────────────────────────────────────
# Part 1: 戰場全景 (Battlefield Panorama)
# ──────────────────────────────────────────────

def generate_part1(race_meta: dict, horses: list) -> str:
    """Generate Part 1 🗺️ 戰場全景 in the Race 1 gold-standard table format."""
    date = race_meta.get('日期', '{{LLM_FILL}}')
    venue = race_meta.get('地點', '快活谷')
    distance = race_meta.get('路程', '{{LLM_FILL}}')
    track = race_meta.get('賽道', '{{LLM_FILL}}')
    class_info = race_meta.get('班次', '{{LLM_FILL}}')
    race_num = race_meta.get('race_num', 0)

    # Build horse list for Speed Map placeholder
    horse_entries = ', '.join(
        f"#{h['num']}({h['barrier']})" for h in horses
    )

    return f"""# {date} {venue} Race {race_num} 分析

---

## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | {class_info} / {distance} / {venue} |
| **賽事類型** | **`[草地]`** |
| 跑道偏差 | {{{{LLM_FILL: C+3 賽道特性描述}}}} |
| 步速預測 | {{{{LLM_FILL: Suicidal / Fast / Genuine-to-Fast / Normal-to-Fast / Slow-to-Normal / Crawl}}}} |
| 戰術節點 | {{{{LLM_FILL: 描述哪些馬匹會爭奪前列、步速結構對後上馬的影響}}}} |

**📍 Speed Map (速度地圖):**
- 領放群: {{{{LLM_FILL: #X(檔位), #Y(檔位)}}}}
- 前中段: {{{{LLM_FILL}}}}
- 中後段: {{{{LLM_FILL}}}}
- 後上群: {{{{LLM_FILL}}}}

**🏃 步速瀑布推演 (Step 0 結論):**
- 領放馬: {{{{LLM_FILL: #X 馬名, #Y 馬名}}}} | 搶位數量: {{{{LLM_FILL}}}}
- 預計步速: {{{{LLM_FILL}}}} | 崩潰點: {{{{LLM_FILL: Xm / 唔會崩潰}}}}
- 偏差方向: {{{{LLM_FILL}}}}
- 受惠: {{{{LLM_FILL}}}} | 受損: {{{{LLM_FILL}}}}

---

"""


# ──────────────────────────────────────────────
# Part 2: Horse Analysis Section
# ──────────────────────────────────────────────

def generate_horse_section(h: dict) -> str:
    """Generate the full analysis section skeleton for one HKJC horse."""
    form = h.get('form', '')
    days = h.get('days_since', '{{LLM_FILL}}')
    gear = h.get('gear', '')

    return f"""**{h['num']} {h['name']}** | {h['jockey']} | {h['trainer']} | {h['weight']} | {h['barrier']}
**📌 情境標記:** `[{{{{LLM_FILL: 情境A-大優 / 情境B-有瑕疵 / 情境C-正路 / 情境D-默認}}}}]`

**賽績總結:**
- **近六場:** {form}
- **休後復出:** {days} 日
- **統計:** 季內 ({{{{LLM_FILL: W-P-S-U}}}}) | 同程 ({{{{LLM_FILL}}}}) | 同場同程 ({{{{LLM_FILL}}}})

**近六場关键走勢:**
- **逆境表現:** {{{{LLM_FILL}}}}
- **際遇分析:** {{{{LLM_FILL}}}}

**馬匹分析:**
- **走勢趨勢 (Step 10.3+):** {{{{LLM_FILL}}}}
- **隱藏賽績 (Step 6+12):** {{{{LLM_FILL}}}}
- **贏馬回落風險 / 穩定性 (Step 5):** {{{{LLM_FILL}}}} 穩定性:近 10 仗入三甲比例=`[{{{{LLM_FILL}}}}]` | 排名=`[{{{{LLM_FILL}}}}]` | 波動=`[{{{{LLM_FILL}}}}]`
- **級數評估 (Step 8.1):** {{{{LLM_FILL}}}}
- **路程場地適性 (Step 2):** {{{{LLM_FILL}}}}
- **引擎距離 (Step 2.6):** `引擎距離:Type [{{{{LLM_FILL: A/B/C/D}}}}] ({{{{LLM_FILL}}}}) | 最佳 [{{{{LLM_FILL}}}}] | 今仗[{{{{LLM_FILL}}}}] = [{{{{LLM_FILL}}}}] [{{{{LLM_FILL: ✅/⚠️/❌}}}}]`
- **配備變動 (Step 6):** {gear if gear else '{{{{LLM_FILL}}}}'} → {{{{LLM_FILL}}}}
- **部署與練馬師訊號 (Step 8.2):** {{{{LLM_FILL}}}} `[{{{{LLM_FILL}}}}]`
- **人馬/騎練配搭 (Step 2.5):** 適配度=`[{{{{LLM_FILL: HIGH/MED/LOW}}}}]` | 組合上名率=`[{{{{LLM_FILL}}}}%]`
- **步速段速 (Step 0+10):** 本場`[{{{{LLM_FILL}}}}]` → {{{{LLM_FILL}}}}
- **競賽事件 / 馬匹特性:** {{{{LLM_FILL}}}}

**🔬 段速法醫 (Step 10):**
- **原始 L600/L400:** {{{{LLM_FILL}}}} | **修正因素:** {{{{LLM_FILL}}}} | **修正判斷:** {{{{LLM_FILL}}}}
- **所示趨勢(近 3 仗):** `[{{{{LLM_FILL}}}}]`

**⚡ EEM 能量 (Step 11):**
- **上仗走位:** {{{{LLM_FILL}}}}
- **累積消耗:** `[{{{{LLM_FILL: 無 / 輕微 / 中等 / 嚴重}}}}]`
- **總評:** {{{{LLM_FILL}}}}

**📋 寬恕檔案 (Step 12):**
- **因素:** {{{{LLM_FILL}}}}
- **結論:** `[{{{{LLM_FILL: 可作準 / 不完全可作準 / 不可作準}}}}]`

**🔗 賽績線 (Step 13):**
- **對手表現:** {{{{LLM_FILL}}}}
- **結論:** `[{{{{LLM_FILL: 強組 / 中等組 / 弱組 / N/A}}}}]`

**📊 評級矩陣 (Step 14):**
- 穩定性 [核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 段速質量 [核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- EEM 潛力 [半核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 練馬師訊號 [半核心]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 情境適配 [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 路程/新鮮度 [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 賽績線 [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 級數優勢 [輔助]: `[{{{{LLM_FILL: ✅/➖/❌}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`
- 寬恕加分: `[{{{{LLM_FILL}}}}]` | 理據: `[{{{{LLM_FILL}}}}]`

**🔢 矩陣算術:** 核心✅={{{{LLM_FILL}}}} | 半核心✅={{{{LLM_FILL}}}} | 輔助✅={{{{LLM_FILL}}}} | 總❌={{{{LLM_FILL}}}} | 核心❌={{{{LLM_FILL: 有/無}}}} → 查表命中行={{{{LLM_FILL}}}}
**14.2 基礎評級:** `[{{{{LLM_FILL}}}}]` | `[{{{{LLM_FILL}}}}]`
**14.2B 微調:** `[{{{{LLM_FILL}}}}]` | `[{{{{LLM_FILL}}}}]`
**14.3 覆蓋:** `[{{{{LLM_FILL}}}}]`

**💡 結論與評語 (Conclusion & Analyst View):**
- **核心邏輯:** {{{{LLM_FILL: 2-3 句話，引用 ≥3 數據點}}}}
- **最大競爭優勢:** {{{{LLM_FILL}}}}
- **最大失敗風險:** {{{{LLM_FILL}}}}

**⭐ 最終評級:** `[{{{{LLM_FILL}}}}]`
🐴⚡ **冷門馬訊號 (Underhorse Signal):** `[{{{{LLM_FILL: 觸發/未觸發}}}}]`
"""


# ──────────────────────────────────────────────
# Part 3-5: Verdict, Blind Spots, CSV
# ──────────────────────────────────────────────

def generate_verdict_scaffold(horses: list) -> str:
    """Generate Part 3-5 verdict scaffold in HKJC format."""

    # CSV scaffold rows
    csv_rows = []
    for h in horses:
        csv_rows.append(
            f"#{h['num']},{h['name']},{h['jockey']}/{h['trainer']},"
            f"{h['barrier']},100,{{{{LLM_FILL}}}},{{{{LLM_FILL}}}},{{{{LLM_FILL}}}},"
            f"{{{{LLM_FILL}}}},{{{{LLM_FILL}}}},{{{{LLM_FILL}}}}"
        )
    csv_block = '\n'.join(csv_rows)

    return f"""## [第三部分] 最終預測 (Verdict)

### 🏆 Top 4 評級與選馬

- **🥇 第一選**
  - **馬號及馬名:** {{{{LLM_FILL}}}}
  - **評級與✅數量:** {{{{LLM_FILL}}}} | [{{{{LLM_FILL}}}}✅]
  - **核心理據:** {{{{LLM_FILL}}}}
  - **最大風險:** {{{{LLM_FILL}}}}

- **🥈 第二選**
  - **馬號及馬名:** {{{{LLM_FILL}}}}
  - **評級與✅數量:** {{{{LLM_FILL}}}} | [{{{{LLM_FILL}}}}✅]
  - **核心理據:** {{{{LLM_FILL}}}}
  - **最大風險:** {{{{LLM_FILL}}}}

- **🥉 第三選**
  - **馬號及馬名:** {{{{LLM_FILL}}}}
  - **評級與✅數量:** {{{{LLM_FILL}}}} | [{{{{LLM_FILL}}}}✅]
  - **核心理據:** {{{{LLM_FILL}}}}
  - **最大風險:** {{{{LLM_FILL}}}}

- **🏅 第四選**
  - **馬號及馬名:** {{{{LLM_FILL}}}}
  - **評級與✅數量:** {{{{LLM_FILL}}}} | [{{{{LLM_FILL}}}}✅]
  - **核心理據:** {{{{LLM_FILL}}}}
  - **最大風險:** {{{{LLM_FILL}}}}

### 📊 Top 2 入三甲信心度
- **信心指數:** [{{{{LLM_FILL: High / Medium / Low}}}}]
- **理據:** {{{{LLM_FILL}}}}

---

## [第四部分] 分析盲區 (Blind Spots) 與防守策略

- **賽道/步速偏差風險 (P25 追蹤):** {{{{LLM_FILL}}}}
- **步速逆轉保險:** {{{{LLM_FILL}}}}
- **初出/不明朗因素:** {{{{LLM_FILL}}}}

---

## [第五部分] 系統驗證與日誌 (Metadata)

```csv
馬號,馬名,練騎,檔位,總分,✅數量,長度,核心邏輯字數,基礎評級,⭐最終評級,冷門馬訊號
{csv_block}
```

✅ [AUTO-CHECK P34] `🥇 **第一選**` 已出現
✅ [AUTO-CHECK P34] Top 2 入三甲信心度 已包含
✅ [AUTO-CHECK P34] 步速逆轉保險 已包含
"""


# ──────────────────────────────────────────────
# Main Assembly
# ──────────────────────────────────────────────

def generate_skeleton(racecard_path: str) -> str:
    """Generate the complete HKJC analysis skeleton."""
    race_meta, horses = parse_hkjc_racecard(racecard_path)

    if not horses:
        return "❌ No horses found in 排位表."

    output = []

    # Part 1: Battlefield Panorama
    output.append(generate_part1(race_meta, horses))

    # Part 2: Horse sections
    output.append("## [第二部分] 馬匹深度剖析 (Horse-by-Horse Forensic)\n")

    for h in horses:
        output.append(generate_horse_section(h))
        output.append("\n---\n")

    # Part 3-5: Verdict + Blind Spots + CSV
    output.append(generate_verdict_scaffold(horses))

    return '\n'.join(output)


def main():
    parser = argparse.ArgumentParser(
        description="HKJC Wong Choi Protocol — Analysis Skeleton Generator"
    )
    parser.add_argument("racecard", type=str, help="Path to HKJC 排位表.md")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: stdout)")
    args = parser.parse_args()

    if not Path(args.racecard).exists():
        print(f"❌ File not found: {args.racecard}")
        sys.exit(1)

    skeleton = generate_skeleton(args.racecard)

    if args.output:
        Path(args.output).write_text(skeleton, encoding='utf-8')
        horse_count = skeleton.count('**📌 情境標記')
        placeholder_count = skeleton.count('{{LLM_FILL')
        print(f"✅ HKJC Skeleton generated: {args.output}")
        print(f"   📊 {horse_count} horses | {placeholder_count} placeholders to fill")
        print(f"   🗺️ Panorama: table + Speed Map + 步速瀑布推演 (locked)")
        print(f"   📋 Per-horse: 11 emoji tags (📌🔬⚡📋🔗📊💡⭐ + 賽績+走勢+分析)")
        print(f"   🏆 Verdict: Top 4 + Blind Spots + CSV")
    else:
        print(skeleton)


if __name__ == '__main__':
    main()
