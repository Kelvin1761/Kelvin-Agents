# Wong Choi 遊戲時段排程

目標：悉尼每日 22:00–01:00 延後自動重型工作；遊戲前優先 AU／NBA／Tennis，HKJC 改到 01:15 後。

- [x] 共用安靜時段、持久 pending queue 及原始日期補跑；測試午夜、DST、重試及 idempotency。
- [x] 調整 plist、policy、NBA role／target day；測試三者一致。
- [x] 等待來源停止即時三連重跑；避免 HKJC 晚間完整抽取。
- [x] AU checkpoint 延後未開始步驟；direct auxiliary 入口套用共用閘。
- [x] 跑 targeted tests、quick／full checks，記錄限制及可部署範圍。

保留 production SHA 16c028ab86364b0b1c1348f1438e54d2244aff03；不改模型評分、不混入主 worktree 的未提交修改。
