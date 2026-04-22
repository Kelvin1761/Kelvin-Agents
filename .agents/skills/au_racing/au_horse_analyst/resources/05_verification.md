
## 基本結構自檢(精簡版 — 完整審核由 Python Completion Gate 執行)

> **注意:** 完整嘅品質審核、SIP 合規驗證同自我改善機制已由 V8/V11 Orchestrator + `completion_gate_v2.py` 吸收。舊式合規 skill 已退役，呢個文件只保留 Analyst 自保檢查。

### 🚨 [SIP-SL03] 退出馬強制驗證 (Scratching Verification — 最高優先級)
> **此檢查必須在任何 Top 4 精選輸出之前執行。未通過驗證嘅 Verdict 視為無效。**

**前置防線(分析開始前):**
- [ ] 從 Racenet/Racing.com 擷取最新 Racecard 數據,確認出賽名單
- [ ] 剔除所有已退出馬匹 (SCR/SCRATCHED),喺分析文件頂部標記退出名單
- [ ] 若退出馬已完成分析 → 標記為 `[SCR — 已退出,分析作廢]`,嚴禁納入排序

**最終防線(Verdict 輸出前):**
- [ ] **逐一核實** Top 4 精選中嘅每匹馬匹是否仍然出賽(非 SCR 狀態)
- [ ] 若任何精選馬已退出 → **立即觸發重排**:從已完成分析嘅馬匹中按評級選出替補
- [ ] 若 Top 4 中 ≥2 匹退出 → 同時觸發 [SIP-RR03] 大規模退出應急協議

**數據源:**
- 首選: Racenet 官方 Racecard (`racenet.com.au/form-guide/[venue]`)
- 備選: Racing.com Acceptances / Tab.com.au 即時出賽名單
- 最後更新時間必須記錄在報告中

> ⚠️ **邏輯基礎:** 2026-04-06 Sandown Lakeside 覆盤中,R2 #5 Cardamom (A 級) 同 R3 #10 Delta Sky (A 級) 兩匹已退出嘅馬被選入 Top 3 精選,直接導致兩場 0 命中。呢個係引擎工作流程中最基礎嘅數據完整性問題。

### 每匹 / 每批次結尾必檢(3 項)
- [ ] 每匹馬都包含 9 個可見 section（⏱️📋🐴🔗🧭⚠️📊💡⭐）及段速/EEM 語義錨點?
- [ ] 每匹馬 ≥ 300 字?(S/A ≥500, B ≥350, C/D ≥300)
- [ ] 批次完成自檢行已輸出?(`✅ 批次完成`)

### 全場結尾必檢(2 項)
- [ ] 所有馬號齊全?冇遺漏任何馬匹?**[SIP-R14-7]** Top 5 + 頂級馬房/騎師座騎不可跳過
- [ ] CSV 輸出格式正確?

> ⚠️ **CRITICAL**:呢個只係基本自保。Wong Choi 會喺每場分析完成後由 Orchestrator **強制執行** `.agents/scripts/completion_gate_v2.py --domain au`。Analyst 通過基本自檢 ≠ 通過 Python 合規閘門。
