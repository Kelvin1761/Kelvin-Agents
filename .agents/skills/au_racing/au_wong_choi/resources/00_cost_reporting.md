
> **設計理念:** 受 ECC `cost-aware-llm-pipeline` 啟發。追蹤每次分析 session 嘅 token 消耗同成本估算。

完成 Step 7 後，執行 session 成本追蹤：
```bash
python .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain au --batch-size {BATCH_SIZE}
```
喺聊天中簡要匯報成本摘要（3 行以內）。此步驟失敗唔影響任何結果。

