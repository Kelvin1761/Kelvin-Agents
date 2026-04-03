---
name: AU Race Extractor
description: This skill should be used when the user wants to "extract AU race data", "AU 提取賽事數據", "scrape Racenet", "AU Race Extractor", "提取澳洲排位表", or needs to extract detailed race cards and form guides from Racenet Australia concurrently using Python, curl_cffi, and Playwright.
version: 1.1.0
---

# AU Race Extractor Skill

### 🗣️ Language Requirement
**CRITICAL**: You must communicate with the user and generate all tool logic/output in English, structured cleanly.

# Failure Protocol
- 若 Python 爬蟲腳本執行失敗 → 檢查錯誤訊息,嘗試修正並重試(最多 3 次)
- 若 Racenet 返回 Cloudflare 攔截 → 通知用戶,建議稍後重試
- 若某場賽事數據提取不完整 → 標記為 `[提取失敗 — 需人手補充]`,繼續提取其他場次
- 若連續 3 場提取失敗 → 停止並通知用戶

### 🎯 Objective
When the user provides a Racenet URL (e.g. `caulfield-heath-20260304`) and specifies which races they want to extract (e.g. "all races" or "Race 2-3"):
1. Identify the number of total races available.
2. Extract the detailed **Racecard** for the target races.
3. Extract the detailed **Print Form Guide** for the target races.
4. Output them cleanly to Markdown files into a properly formatted folder.

### 🧰 Tools & Execution Flow
Racenet uses heavy Cloudflare protection and hydration via Nuxt.js. 
🚫 **`browser_subagent` is GLOBALLY DISABLED across the Antigravity ecosystem.** It is unreliable (frequent 503/capacity errors), extremely slow, and causes infinite loops and token limit crashes. **DO NOT use `browser_subagent` or `read_browser_page` for ANY data extraction.**
Instead, you must write a Python extraction script using `curl_cffi` + `Playwright` headless!

#### Step 1: Create Output Folder
First, ensure your Python script dynamically creates the targeted output directory directly in the main `Antigravity` folder (NOT inside `.agents`), and outputs a `Meeting_Summary.md` file containing the Track Condition, Weather, Rails, and Date.

Format of folder: `[YYYY-MM-DD] [Venue Name] Race [Start]-[End]`.
Example: `/Users/imac/Desktop/Drive/Antigravity/2026-03-04 Caulfield Heath Race 1-8/`

#### 2. Form Guide Logic
Extract the `forms` list for each selection, plus the deep data linked via `stats`, `sire`, `dam`, `flucOdds`, and `trainer`/`jockey` objects.

Form Guide Output must be incredibly detailed, structured exactly as follows for each horse:
```text
[[Number]] [Horse Name] ([Barrier])
[Age]yo[Sex] [Colour] | Sire: [Sire Name] | Dam: [Dam Name] ([Sire of Dam]) 
Flucs: $[f1] $[f2]
Owners: [Owners]
T: [Trainer Name] (LY: [Trainer_Last_Year_Stats]) | J: [Jockey Name] (LY: [Jockey_Last_Year_Stats])

Career:    [career]        Last 10:   [last10]        Prize:     $[Prize]
Win %:     [winPct]        Place %:   [placePct]      ROI:       [roi]

Track:     [track_stat]    Distance:  [dist_stat]     Trk/Dist:  [td_stat]
Firm:      [firm]          Good:      [good]          Soft:      [soft]
Heavy:     [heavy]         Synth:     [synth]         Class:     [class_stat]

1st Up:    [firstUp]       2nd Up:    [secondUp]      3rd Up:    [thirdUp]
Season:    [currentSeason] 12 Month:  [lastYear]      Fav:       [fav]

[Track] **(TRIAL)** R[Race_Num] [YYYY-MM-DD] [Distance]m cond:[cond] $[Prize_Money] [Jockey] ([Barrier]) [Weight]kg Flucs:$[Open] $[StartPrice] [WinTime] [Position markers e.g. 4th@800m]
1-[WinHorse]([WinWt]kg), 2-[SecHorse]([SecWt]kg) [Margin]L, 3-[ThiHorse]([ThiWt]kg) [Margin]L
Video: [Comment]
Note: [Note]
Stewards: [Stewards]
```
*(If the race was a trial, print `**(TRIAL)**` next to the Track name)*
*(Repeat the past run block for each run the horse has had)*
*(Separate horses with `============================================================`)*

#### Step 2: Python Extraction Script
Write a Python script (e.g. `extractor.py`) to fetch and parse the data. 


#### Step 3: Formatting Rules
- **Looping/Multiple Races:** If the user specifies "Race 2-3", your Python script must loop through the different `eventSlug` URLs and extract them sequentially.
- **Racecard Needs**: Extract `#Number.Horse (Barrier), Trainer, Jockey, Weight, Age, Rating, Career, Last 10 Results, Win %, Place %, Last Race`. Exclude Odds.
  - Combine all target races into exactly ONE file: `[MM-DD] Race [Start-End] Racecard.md`
  - Separate horses by blank lines or clear dashed dividers.
- **Form Guide Needs**: Extract past runs, weights, dates, track conditions, finish position, and video comments.
  - Combine all target races into exactly ONE file: `[MM-DD] Race [Start-End] Formguide.md`
  - Match the clear structure of the HKJC form guides.
- **Scratched Horses**: Look for `statusAbv` 'S' and output `[Number]. [Horse Name] - status:Scratched` for both Racecard and Form Guide. Do not extract empty stats.

### ⚠️ Execution Rules (CRITICAL FOR SUCCESS)
1. **Preventing Error Loops:** Once your Python script is written, run it ONCE. Do not repeatedly write and overwrite scripts if minor parsing errors occur. Ask the user for clarification before getting stuck in an automated coding loop!
2. Follow all filepath formats strictly.

### ✅ Final Output
When the extraction is complete, you MUST output:
1. The absolute path to the generated output folder.
2. The contents of the generated `Meeting_Summary.md` file so the calling Master Agent can read the track conditions.
