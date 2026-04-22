# Wong Choi Session Start Pre-flight Checklist (P28)

> **目的:** 確保所有 operator(Kelvin/Heison/其他人)喺任何 AI model 上都能產出一致質素嘅分析。
> **何時使用:** 每次啟動新 session 時,將此 checklist 嘅內容包含喺你嘅第一條指令中。

---

## 🚀 Session Start Prompt Template

複製以下完整指令作為新 session 嘅第一條訊息:

```
@hkjc wong choi, 開始分析 [VENUE] [DATE] for [ANALYST_NAME]

## 環境設定
- BATCH_SIZE: 由環境掃描決定(標準 3,安全 fallback 2)
- VERDICT 須獨立 tool call 寫入
- 所有馬匹必須完整 11-field 分析(包括 D 級)

## 強制資源載入
開始前你必須讀取以下文件(缺一不可):
1. hkjc_wong_choi/SKILL.md(完整讀取)
2. hkjc_horse_analyst/resources/01_system_context.md
3. hkjc_horse_analyst/resources/08_templates_core.md（每批 batch reload）
4. 場地模組(按今場選 1 個):
   - Sha Tin 草地 → 10a_track_sha_tin_turf.md
   - Happy Valley → 10b_track_happy_valley.md
   - 全天候 → 10c_track_awt.md

## Pre-flight Self-Check
讀完以上文件後,你必須回覆以下 checklist(全部 ✅ 才可開始):
- [ ] SKILL.md 已讀取(確認 P28 OUTPUT_TOKEN_SAFETY 規則存在)
- [ ] 01_system_context.md 已讀取(確認 Anti-Laziness 規則存在)
- [ ] 08_templates_core.md 已讀取（確認 11-field 骨架格式 + 🎯檔位判讀欄位存在）
- [ ] 場地模組已讀取
- [ ] BATCH_SIZE 由環境掃描決定已確認
- [ ] 環境掃描結果已回報用戶
- [ ] hkjc_standard_times.json 存在且 ≥50 entries（⚠️ 若缺失：執行 `python3 .agents/scripts/scrape_standard_times.py`）
- [ ] hkjc_draw_stats.json 存在且 races ≥1（⚠️ 若缺失：執行 `python3 .agents/scripts/scrape_draw_stats.py`）
- [ ] Facts.md 含 🎯 檔位優劣判讀 block（⚠️ 若缺失：重新執行 inject 加 --race-num 參數）

## 數據路徑
Racecard: [RACECARD_PATH]
Formguide: [FORMGUIDE_PATH]

## 分析模式
P19v2 逐場手動推進協議 — 每場完成後等確認
每匹馬完整 5-block × 13-subfield (11-field HKJC) 分析
```

---

## ⚠️ 環境對齊規則

### 問題根源(2026-03-29 確認)
不同 operator 嘅環境差異會導致分析質素不一致:
1. **Output token limit 唔同** — 部分 model/API 有較低嘅 output ceiling
2. **Resource 載入唔完整** — Session recovery 時跳過 template 讀取
3. **Context window 管理唔同** — 部分 model 較早出現記憶漂移

### 對齊方案
| 項目 | 統一標準 | 原因 |
|------|---------|------|
| BATCH_SIZE | **3**(標準)/ **2**(fallback) | 環境掃描決定,防止 token truncation |
| Verdict | **獨立 tool call** | 防止合併時被截斷 |
| Resource 讀取 | **4 個必讀文件** | 防止格式漂移 |
| Pre-flight check | **6 項 checklist** | 結構性證據 |
| Post-race validation | **validate_analysis.py** | 客觀品質閘門 |

### Post-Race Validation(每場必須)
每場分析完成後,Wong Choi 必須執行:
```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/validate_analysis.py "[ANALYSIS_FILE_PATH]"
```
Windows 或已配置 `python` launcher 嘅環境可將 `python3` 換成 `python`。
輸出 `❌ FAILED` → 必須修正再重新驗證。
輸出 `✅ PASSED` → 可以推進下一場。

---

## 🗺️ 戰場全景骨架模板 (Panorama Skeleton — Batch 1 Only)

Wong Choi 喺寫入 **Batch 1** 時,**必須先寫入以下戰場全景**,然後才寫馬匹分析。LLM 只需填充 `[FILL]` 位置:

```markdown
# {DATE} {VENUE} Race {N} 分析

---

## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | [FILL: 班次 / 路程 / 場地] |
| **賽事類型** | **`[草地]`** |
| 跑道偏差 | [FILL: 賽道特性描述 — C / C+3 / B+2 等] |
| 步速預測 | [FILL: Suicidal / Fast / Genuine-to-Fast / Normal-to-Fast / Slow-to-Normal / Crawl] |
| 戰術節點 | [FILL: 描述哪些馬匹會爭奪前列、步速結構對後上馬的影響] |

**📍 Speed Map (速度地圖):**
- 領放群: [FILL: #X 馬名(檔位)]
- 前中段: [FILL]
- 中後段: [FILL]
- 後上群: [FILL]

**🏃 步速瀑布推演 (Step 0 結論):**
- 領放馬: [FILL: #X 馬名] | 搶位數量: [FILL]
- 預計步速: [FILL] | 崩潰點: [FILL: Xm / 唔會崩潰]
- 偏差方向: [FILL]
- 受惠: [FILL] | 受損: [FILL]

---

## [第二部分] 馬匹深度剖析 (Horse-by-Horse Forensic)

```

> **⚠️ 嚴禁跳過 Part 1 直接寫馬匹分析！** Batch 1 必須包含完整嘅戰場全景。

---

## 🏆 Top 4 Verdict 骨架模板

Wong Choi 喺每場 VERDICT BATCH 開始前,必須注入以下骨架。

> **首選方案：** 使用 `compute_rating_matrix_hkjc.py` 嘅 `generate_verdict()` 自動生成（包含 Python 預填嘅馬號/馬名/評級 + Emergency Brake 自動檢查）。LLM 只需填充 `{{LLM_FILL}}` 標記。
> **備用方案：** 若未使用 Python 計算，則手動填充以下 `[FILL]` 標記。LLM 只需填充 `[FILL]` 位置:

```markdown
#### [第三部分] 最終預測 (The Verdict)

- **跑道形勢:** [FILL]
- **信心指數:** `[FILL: 極高/高/中高/中/低]`
- **關鍵變數:** [FILL]

**🏆 Top 4 位置精選**

🥇 **第一選**
- **馬號及馬名:** [FILL]
- **評級與✅數量:** `[FILL]` | ✅ [FILL]
- **核心理據:** [FILL]
- **最大風險:** [FILL]

🥈 **第二選**
- **馬號及馬名:** [FILL]
- **評級與✅數量:** `[FILL]` | ✅ [FILL]
- **核心理據:** [FILL]
- **最大風險:** [FILL]

🥉 **第三選**
- **馬號及馬名:** [FILL]
- **評級與✅數量:** `[FILL]` | ✅ [FILL]
- **核心理據:** [FILL]
- **最大風險:** [FILL]

🏅 **第四選**
- **馬號及馬名:** [FILL]
- **評級與✅數量:** `[FILL]` | ✅ [FILL]
- **核心理據:** [FILL]
- **最大風險:** [FILL]

**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**
🥇 [FILL]:`[🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]
🥈 [FILL]:`[🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]

**🔄 步速逆轉保險 (Pace Flip Insurance):**
- 若步速比預測更快 → 最受惠:[FILL] | 最受損:[FILL]
- 若步速比預測更慢 → 最受惠:[FILL] | 最受損:[FILL]

**🚨 緊急煞車檢查 (Emergency Brake Protocol):**
- [FILL: 觸發條件檢查]

---

#### [第四部分] 分析盲區

**1. 段速含金量:** [FILL]
**2. 風險管理:** [FILL]
**3. 試閘與預期假象:** [FILL]
**4. 特定與場地風險:** [FILL]
**5. 步速情境分支:**
- 快步速:最利 → [FILL];最不利 → [FILL]
- 慢步速:最利 → [FILL];最不利 → [FILL]
**6. 🎯 步速崩潰冷門 (Pace Collapse Dark Horse):** [FILL]
**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):** [FILL]

---

` ` `csv
Race Number,Distance,Jockey,Trainer,Horse Number,Horse Name,Grade
[FILL: Top 4 rows]
` ` `
```

> **嚴禁自創其他格式。** 所有 Top 4 verdict 必須使用以上骨架。
> **核心邏輯部分為 LLM 自由發揮區域** — 結構固定但核心邏輯嘅分析深度同角度由 LLM 自由發揮。
