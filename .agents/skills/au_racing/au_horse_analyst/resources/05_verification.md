
## 基本結構自檢(精簡版 — 完整審核由 Python Completion Gate 執行)

> **注意:** 完整嘅品質審核、SIP 合規驗證同自我改善機制已由 V8/V11 Orchestrator + `completion_gate_v2.py` 吸收。舊式合規 skill 已退役，呢個文件只保留 Analyst 自保檢查。


### 每匹 / 每批次結尾必檢(3 項)
- [ ] 每匹馬都包含 9 個可見 section（⏱️📋🐴🔗🧭⚠️📊💡⭐）及段速/形勢與走位 語義錨點?
- [ ] 每匹馬 ≥ 300 字?(S/A ≥500, B ≥350, C/D ≥300)
- [ ] 批次完成自檢行已輸出?(`✅ 批次完成`)

### 全場結尾必檢(2 項)
- [ ] 所有馬號齊全?冇遺漏任何馬匹?**[SIP-R14-7]** Top 5 + 頂級馬房/騎師座騎不可跳過
- [ ] CSV 輸出格式正確?

> ⚠️ **CRITICAL**:呢個只係基本自保。Wong Choi 會喺每場分析完成後由 Orchestrator **強制執行** `.agents/scripts/completion_gate_v2.py --domain au`。Analyst 通過基本自檢 ≠ 通過 Python 合規閘門。
