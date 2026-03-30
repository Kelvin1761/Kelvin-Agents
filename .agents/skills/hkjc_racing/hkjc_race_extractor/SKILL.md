---
name: HKJC Race Extractor
description: This skill should be used when the user wants to "extract HKJC race data", "HKJC 提取賽事數據", "scrape HKJC racecard", "HKJC Race Extractor", "提取排位表", "提取賽績", or needs to extract comprehensive racecards and form guides from the Hong Kong Jockey Club website.
version: 1.1.0
---

# HKJC Race Extractor Skill

### 🗣️ Language Requirement
**CRITICAL**: You must communicate with the user and format ALL extracted data outputs (both Racecard and Form Guide) EXCLUSIVELY in Hong Kong style Traditional Chinese (繁體中文 - 香港本地方言及賽馬術語).

When a user asks you to extract race data and provides a Hong Kong Jockey Club (HKJC) Racecard URL, you MUST automatically extract BOTH the Racecard (排位表) AND the Form Guide (賽績指引 / 速勢能量).

### 🧰 Tools & Resources
To execute this skill effectively, you must utilize the provided scripts, examples, and resources:

1.  **`examples/`**: Refer to the example output files strictly to understand the required data formatting.
    *   View `examples/racecard_output_example.txt` for the exact Racecard format.
    *   View `examples/formguide_output_example.txt` for the exact Form Guide format. **Note: ALL past races for each horse must be extracted, not just the most recent one.**
2.  **`resources/`**: Consult the `resources/data_dictionary.txt` for definitions of specific HKJC terms and data fields.

### ⚡ Efficiency & Automation Workflow
1.  **Single URL Trigger**: The user will only provide the Racecard URL.
2.  **Auto-Navigation / Derivation**: Derive the Form Guide URL using this pattern:
    `https://racing.hkjc.com/zh-hk/local/info/speedpro/formguide?racedate=YYYY/MM/DD&Racecourse=XX&RaceNo=N`
    *Also derive the Date string (YYYYMMDD) for the Starter PDF.*
3.  **Concurrent Extraction**: Execute Python scripts for BOTH Racecard and Form Guide extraction concurrently. Execute the Starter PDF script once per meeting.
4.  **Output Location**: You must create a folder directly in the `Antigravity` directory (not inside `.agents/skills/...`) named format `[YYYY-MM-DD][Happy Valley or Sha Tin]` (e.g. `/Users/imac/Desktop/Drive/Antigravity/2026-03-04Happy Valley/`). 
5.  **Consolidated Output Format**: You must ALWAYS output the final extracted data as **`.md` files** (Markdown format, for easier downstream agent reading). When combining the data, use the following naming convention for the files within the folder:
    *   `[MM-DD] Race [StartRace-EndRace] 排位表.md` (e.g., `03-04 Race 1-9 排位表.md`)
    *   `[MM-DD] Race [StartRace-EndRace] 賽績.md` (e.g., `03-04 Race 1-9 賽績.md`)
    *   `[MM-DD] 全日出賽馬匹資料 (PDF).md` (e.g., `03-04 全日出賽馬匹資料 (PDF).md` - **Extract this ONLY ONCE per race meeting**)

6.  **🚀 高速訪問協議 (Turbo Access Protocol)**:
    一旦全日數據被合併存檔，後續任何針對單一場次的讀取請求，必須透過簡單的文字切片 (String Slicing) 或 Python 分割邏輯完成，嚴禁重複執行複雜的 Web 爬取或 Playwright 流程。

---

### ⚡ Batch Extraction (Recommended for Multi-Race Meetings)
For meetings with multiple races, use the batch extraction script to extract all races concurrently:
```bash
/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/venv/bin/python /Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts/batch_extract.py --base_url "RACECARD_URL" --races "1-9" --output_dir "/path/to/output"
```
This script:
- Extracts racecard + formguide for all specified races **concurrently** (up to 3 at a time)
- Extracts the starter PDF once automatically
- Outputs files in the correct naming format: `[MM-DD] Race X 排位表.md`, `[MM-DD] Race X 賽績.md`, `[MM-DD] 全日出賽馬匹資料 (PDF).md`

### ⚡ Single-Race Extraction (Manual / Fallback)

### 1. Starter PDF Extraction (出賽馬匹全日資料)
For every new race meeting, you must extract general data spanning all races from the official PDF. Include this file alongside the racecard and formguide data.

#### Extraction Method: Python Script
Execute the specialized Python extraction script to download and parse the PDF. Pass the date in `YYYYMMDD` format:
```bash
/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/venv/bin/python /Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts/extract_starter_pdf.py "YYYYMMDD" > "starter_pdf_data.md"
```
Append this raw output directly into `[MM-DD] 全日出賽馬匹資料 (PDF).md`.

---

### 2. Racecard Extraction (排位表)
When extracting from the Racecard, ensure the output format strictly matches `examples/racecard_output_example.txt`.

#### 第一部分：賽事資料 (Race Info)
[場次] - [賽事名稱] [日期], [星期], [地點], [時間]
[場地], [賽道], [路程]
獎金: [獎金金額], 評分: [評分範圍], [班次]

#### 第二部分：馬匹資料 (Horse Info)
For every horse, you MUST output the data as explicit key-value pairs. Reference `examples/racecard_output_example.txt` for the exact string format.

#### Extraction Method: Python Script
Execute the specialized Python extraction script included in this skill's folder:
```bash
/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/venv/bin/python /Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts/extract_racecard.py "YOUR_RACECARD_URL_HERE" > "racecard_data.md"
```
This script bypasses rendering and extracts hidden fields automatically.

---

### 3. Form Guide / Speedpro Extraction (賽績指引 / 速勢能量)

> 🚫 **ABSOLUTE BAN: `browser_subagent` is GLOBALLY DISABLED across the Antigravity ecosystem.** It is unreliable (frequent 503/capacity errors), extremely slow, and causes infinite loops. **DO NOT use `browser_subagent` or `read_browser_page` for ANY data extraction.** The Form Guide page is extremely large (~8000px tall, 12 horses × 4-8 past races each with 11 data columns) — always use the Python scripts below.

#### Extraction Method: Headless Playwright & BeautifulSoup Script
To handle the massive data density of the Form Guide, we use a programmatic bridge script instead of LLM visual context.

**Step 1: Use the dedicated Python script**
Execute the specialized Python Playwright extraction script included in this skill's folder using the local virtual environment:
```bash
/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/venv/bin/python /Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts/extract_formguide_playwright.py "YOUR_FORMGUIDE_URL_HERE" > "racedata.md"
```
This script handles the React hydration via headless Chromium and parses the output perfectly via BeautifulSoup without hitting any token limits.

**Step 2: Append and Format**
The script will automatically output the text in the correct format matching `examples/formguide_output_example.txt`. Just append the data directly to your combined final document.

#### Data Fields Per Horse

For each horse, extract from the **green header row**:
- 馬號, 馬名, 檔位, 騎師, 負磅, 排位體重

For each horse's **past race rows** (ALL rows, typically 4-8 per horse), extract:
- 出賽日期, 日數, 跑道/路程/場地, 檔位, 馬匹體重, 負磅, 騎師, 名次/出馬, 能量數值, 分段時間 (3-4 major segments only, ignore small sub-splits), 賽事短評

#### Output Format
Format each horse following `examples/formguide_output_example.txt`:
- Horse header fields as key-value pairs
- Under `往績紀錄:`, list EVERY past race as an indexed sub-entry `[1]`, `[2]`, etc.
- Each sub-entry must include ALL the race fields on a single line separated by `|`

*Constraints*: Format in plain text only. DO NOT summarize or omit any horse's past performance records. Only capture the 3 to 4 major segments for sectional times (ignore the sub-split pairs in small text beneath).
