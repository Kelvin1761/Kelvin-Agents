# AU Wong Choi Session Start Pre-flight Checklist (P28/P31)

> **目的:** 確保所有 operator(Kelvin/Heison/其他人)喺任何 AI model 上都能產出一致質素嘅分析。
> **何時使用:** 每次啟動新 session 時,將此 checklist 嘅內容包含喺你嘅第一條指令中。

---

## 🚀 Session Start Prompt Template

複製以下完整指令作為新 session 嘅第一條訊息:

```
@au wong choi, 開始分析 [VENUE] [DATE] for [ANALYST_NAME]

## 環境設定
- BATCH_SIZE: 由環境掃描決定(標準 3,安全 fallback 2)
- VERDICT 須獨立 tool call 寫入
- 所有馬匹必須完整 5-block × 13-subfield 分析(包括 D 級)

## 強制資源載入
開始前你必須讀取以下文件(缺一不可):
1. ../../au_wong_choi/SKILL.md(完整讀取)
2. ../au_horse_analyst/resources/01_system_context.md
3. ../au_horse_analyst/resources/06_templates_core.md（結構骨架）
4. ../au_horse_analyst/resources/06_templates_rules.md（Verdict 觸發規則）
5. 場地模組(按今場選 1 個)

## Pre-flight Self-Check
讀完以上文件後,你必須回覆以下 checklist(全部 ✅ 才可開始):
- [ ] SKILL.md 已讀取(確認 SIP-DA01 多角度裁決協議及 P28/P31 規則存在)
- [ ] 01_system_context.md 已讀取(確認 Anti-Laziness 規則存在)
- [ ] 06_templates_core.md 已讀取(確認骨架格式存在)
- [ ] 06_templates_rules.md 已讀取(確認 Verdict 觸發規則存在)
- [ ] 場地模組已讀取
- [ ] BATCH_SIZE 由環境掃描決定已確認
- [ ] 環境掃描結果已回報用戶

## 數據路徑
Racecard: [RACECARD_PATH]
Formguide: [FORMGUIDE_PATH]

## 分析模式
P33-WLTM 逐場手動推進協議 — 每場完成後等確認
每匹馬完整 5-block × 13-subfield 分析
Verdict 必須獨立 tool call 寫入
```

---

## ⚠️ 環境對齊規則

### 問題根源(2026-03 確認)
不同 operator 嘅環境差異會導致分析質素不一致:
1. **Output token limit 唔同** — 部分 model/API 有較低嘅 output ceiling
2. **Resource 載入唔完整** — Session recovery 時跳過 template 讀取
3. **Context window 管理唔同** — 部分 model 較早出現記憶漂移
4. **Tool call 連鎖行為唔同** — Gemini 唔會自動連鎖 tool calls(P31)

### 對齊方案
| 項目 | 統一標準 | 原因 |
|------|---------|------|
| BATCH_SIZE | **3**(標準)/ **2**(fallback) | 環境掃描決定,防止 token truncation |
| Verdict | **獨立 tool call** | 防止合併時被截斷 |
| Resource 讀取 | **4 個必讀文件** | 防止格式漂移 |
| Pre-flight check | **6 項 checklist** | 結構性證據 |
| Post-race validation | **validate_analysis.py** | 客觀品質閘門 |
| Engine adaptation | **P31 LOOP_CONTINUATION_MARKER** | 防止 Gemini 提早停機 |

### Post-Race Validation(每場必須)
每場分析完成後,Wong Choi 必須執行:
```bash
python3 .agents/scripts/completion_gate_v2.py "[ANALYSIS_FILE_PATH]" --domain au
python3 .agents/skills/au_racing/../au_wong_choi/scripts/verify_math.py "[ANALYSIS_FILE_PATH]" --fix
```
輸出 `❌ FAILED` → 必須修正再重新驗證。
輸出 `✅ PASSED` → 可以推進下一場。

---

## 🏆 Top 4 Verdict 骨架模板

Wong Choi 喺每場 VERDICT BATCH 開始前,必須注入以下骨架。LLM 只需填充 `[FILL]` 位置:

```markdown
## [第三部分] 🏆 全場最終決策

**Speed Map 回顧:** [FILL: 預期步速] | 領放群: [FILL] | 受牽制: [FILL]

**Top 4 位置精選**

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

---

**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**
🥇 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]
🥈 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]

---

**[SIP-FL03] 🎰 Exotic 組合投注池建議 (Exotic Pool Box Recommendation)**

📦 **Box Trifecta(三重彩組合)建議:**
- **核心池:** [FILL: Top 4 全部馬匹號碼及馬名]
- **擴展池(選擇性):** [FILL: B+ 級冷門馬訊號觸發者]
- **建議組合:** [FILL]

📊 **投注邏輯:**
- [FILL: 基於首選信心度嘅投注建議]

*若未觸發(有明確 S- 統治者且評級斷層明顯),輸出:`🎰 Exotic 建議:本場暫不適用`*

---

**[SIP-RR01] 📗📙 雙軌場地 Top 4(僅在場地不穩定時輸出)**

*觸發條件:場地預報處於 Good 4 和 Soft 5 之間、或降雨預報 ≥ 30%、或場地標記為 UNSTABLE*

📗 **Good 4 場地 Top 4:**
🥇 [FILL] | 🥈 [FILL] | 🥉 [FILL] | 🏅 [FILL]

📙 **Soft 5 場地 Top 4:**
🥇 [FILL] | 🥈 [FILL] | 🥉 [FILL] | 🏅 [FILL]
- **vs Good 4 差異:** [FILL]

*若場地 STABLE 且只有一種場地預測 → 省略此區塊*

---

## [第四部分] 分析陷阱

- **市場預期警告:** [FILL: 名單 + 數據漏洞理由]
- **🔄 步速逆轉保險 (Pace Flip Insurance):**
  - 若步速比預測更快 → 最受惠:[FILL] | 最受損:[FILL]
  - 若步速比預測更慢 → 最受惠:[FILL] | 最受損:[FILL]
- **整體潛在機會建議:** [FILL]

**[SIP-RR07] ⚠️ 爆冷潛力預警 (Upset Potential Warning):**
[FILL: 爆冷指數計算 → 若 ≥ 6 則觸發]

**[SIP-RR03] 🚨 大規模退出應急協議:**
[FILL: 若 Top 4 中 ≥2 退出則觸發迷你重分析]

**🚨 緊急煞車檢查 (Emergency Brake Protocol):**
- [FILL: 觸發條件檢查 — LOW CONFIDENCE / ONE-HORSE / DIFFICULT]

**📊 穩建馬外報建議 (Exotic Anchors):**
[FILL: PSI > 0.7 但 B/B+ 嘅穩定馬 → 四重彩腳]

**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):**
[FILL: 彙總全場觸發冷門馬訊號嘅馬匹,或「無冷門馬訊號」]

---

` ` `csv
Race Number,Level of Race,Distance,Jockey,Trainer,Horse Number,Horse Name,Grade
[FILL: Top 4 rows]
` ` `
```

> **嚴禁自創其他格式。** 所有 Top 4 verdict 必須使用以上骨架。
> **核心邏輯部分為 LLM 自由發揮區域** — 結構固定但核心邏輯嘅分析深度同角度由 LLM 自由發揮。
