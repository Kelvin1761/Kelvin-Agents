# Racenet workflow retired

AU Wong Choi 主流程已完全轉用 Sportsbet；Racenet transport、bulk/backfill scripts 同
safe-mode guard 已退役，唔應再啟用。

現役入口：

```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Sportsbet URL 或 meeting folder>"
```

賽前資料、騎練統計、賽果 cache 同綵衣全部由 Sportsbet pipeline 提供。舊 archive 入面
保留 `racenet_*` provenance，只用嚟正確解讀歷史逐駒 benchmark，唔會發出 Racenet 請求。
