# Wong Choi 操作員指南 (Operator Guide)
**版本：** 1.0 | **日期：** 2026-03-25 | **適用：** AU Wong Choi + HKJC Wong Choi

---

## 5 條黃金法則

### 1. 版本同步
- 每次開新 session 確認 SKILL.md 係最新版
- 驗證方法：第一場分析輸出應有「冷門馬訊號」而非「潛力馬訊號」
- 若見到「潛力馬」= 舊版，需開新 session

### 2. Session 分割（每 4 場）
- Wong Choi 會喺 Race 4 完成後硬性停止
- 開新 chat 輸入 `@wong_choi 繼續分析 [URL]`
- Session Recovery 會自動讀取 `_session_state.md` 恢復進度
- **唔好嘗試一個 session 做超過 4 場**

### 3. 提取與分析分離
- 唔好喺同一個 session 做大量數據提取 + 分析
- 最佳做法：提取全日數據 → 確認完成 → 開始分析
- 提取完成後如果 context 已重，建議開新 session 再分析

### 4. 唔好干擾流程
- 分析進行中避免發多餘訊息（每個訊息都佔 context）
- 批次之間唔需要手動確認（半自動模式會處理）
- 有問題先等合規結果出嚟再反映

### 5. 檢查輸出
- 每場完成後掃一眼合規結果（會自動顯示 3 秒）
- 確認馬匹數量正確
- 若見到 `⚠️ CONTEXT_PRESSURE_WARNING` = 即刻開新 session

---

## Context Pressure 處理

Wong Choi 偵測到 context 壓力時會主動通知：
```
⚠️ 偵測到 context window 壓力。建議開新 chat 繼續：
輸入 '@wong_choi 繼續分析 [URL]' 即可自動恢復進度。
```

**你需要做嘅：**
1. 開新 chat
2. 輸入 `@wong_choi 繼續分析 [原始 URL]`
3. Wong Choi 會自動偵測已完成場次並從下一場繼續

---

## Troubleshooting

| 問題 | 解決方法 |
|------|----------|
| 分析到一半 crash | 開新 session，`@wong_choi 繼續`，Session Recovery 自動偵測 |
| 馬匹數量少咗 | Context window 壓力。即刻開新 session |
| 賽績數據錯 | 確認用最新版 SKILL.md + 開新 session |
| 合規一直 FAILED | 熔斷機制會喺重試 1 次後停低。可以選擇跳過 |
| Dashboard 搵唔到分析 | 確認檔案係 `.md` 格式，放喺正確資料夾 |

---

## Heison 特別注意
- 確認分析輸出用「冷門馬訊號」而非「潛力馬訊號」
- 若係後者 = 用緊舊版 SKILL.md
- 修復：開新 session 重新觸發 Wong Choi skill
