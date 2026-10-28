# NBA 全面修正執行計劃

目標：完成 2026-10-23 審核 F04–F12，連同驗證、保存及生產接通，唔以縮細範圍代替完成。
起點：`2a6695e9`；分支 `codex-nba-audit-fixes-20261023`。F01–F03 已發佈。

- [x] F04：分離歷史 cache 與即時傷停／陣容刷新；回歸及真實來源 smoke 通過；已發佈 `0bffbeb6`。
- [x] F05：已接通發佈前真實 SGM quote、同 event／腿 hash、5 分鐘到期、真實價 EV／Kelly／dashboard／凍結價 ROI；價格反轉及端到端測試通過。已發佈 `1fa3e4fa`（完整 gate、NBA 對齊、dashboard 部署成功）；唔聲稱歷史盈利提升。
- [x] F06：v2 共用特徵／真對手、訓練窗 Pipeline、日期／事件切分、Final／US 日標籤、source hash／CSV 防串改、strict backtest 已完成及實測。8,286 labeled rows；新 RF 輸 C，不晉升。完整閘／合併／生產核對完成。
- [x] F07：大勝 breakdown 已傳到候選；9-arm／50 captures 固定重播完成，C 機率及組合零變化；source→candidate→correlation integration 通過。完整閘／合併／生產核對完成。
- [x] F08：傷停 funding／復出刷新／身份匹配、己隊 pace、MC scoring-unit 換算接通；single／full-minus 消融全部完成，MC ΔBrier CI 跨零，冇改善聲稱。完整閘／合併／生產核對完成。
- [x] F09：官方 PerGame／Totals 同截點 576 人核對，20 attempts 覆蓋 0→523；Totals／unit／GP／canonical team、statistics cache contract 2 及失敗重試已接通。完整閘／合併／生產核對完成。
- [x] F10：機率／sidecar／ledger 接通係數身份，先選實際最新快照再分組；合成及真實 ledger 唯讀核對通過；已發佈 `0bffbeb6`。
- [x] F11：selector／description 共用 frozen policy，實際 fallback tag 經 quote 保留；2–4 腿／CoV／3.0x 目標如實、取消固定 Low Risk／額外 units，C 來源同 10F 診斷分開。完整閘／合併／生產核對完成。
- [x] F12：缺檔／損壞／非法設定阻擋 CLI；disabled 明示、恢復重試及獨立公式測試通過；已發佈 `0bffbeb6`。

所有改動先量基準；預測改動保留 rollback、固定語料／時間窗、按日比較、獨立特徵驗證。大於 1GB 輸出只用已掛載外置碟。
每批跑 NBA 專項、`./檢查.sh --quick`、完整 `./檢查.sh`，經 exact-scope 保存；剩餘問題逐項留證據及狀態，全部完成前 goal 保持 active。

Central 分開交付要求：統計 cache 合約常數先獨立發佈，再交付 runtime／serving 修正，最後交付 backtest CLI 及其邊界測試；唔繞過 evaluation／model 分開規則。完成狀態以各批 immutable manifest 及最終 completion audit 為準。

完成核對：最後 code release `81b5c6428223e6a52368cb106628298abf242774`，完整閘 735.978 秒通過、NBA 459 tests、生產 22 個 runtime 檔案一致，13 份研究證據 hash 一致。F09 新抽取來源閘亦已補強。詳見 `docs/audits/nba-audit-remediation-completion-2026-10-24.md` 及機器核對 JSON。原審核 F01–F12 本輪全部完成；RF 不晉升，冇預測／盈利改善聲稱。
