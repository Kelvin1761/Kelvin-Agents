# NBA SGM 發布修正（2026-10-24）

目標：修復實際 pipeline 阻塞，驗證未開賽真實賽事可以產生 SGM 並喺 dashboard 顯示；唔調模型、唔放寬正 EV／真價／賽前來源安全閘。

已重現：今日 12 場均有報告，部分 sidecar 有真價 SGM，但 warning exit 2 被 run_script 當失敗；新 renderer 冇 MC_MODEL_VERSION 標記引起 FW-12 warning。refresh_availability 以 fetch 前嘅 now 驗 fetch 後 timestamp，會誤判 future。逐場深度抽取超過 5 分鐘 quote TTL，舊 quote 失效。

- [x] 加回準確 MC 版本；只容許 validator documented warning exit 2，真 block／extractor exit 2 保持失敗。
- [x] 刷新以完成時間核對時效；請求期間開賽亦拒絕，保留原檔。
- [x] 深度抽取與最後發佈快刷分開；發佈時驗證有效來源／報價，唔延長 quote TTL。
- [x] 已驗證 immutable 賽前 snapshot 可保留分析卡；過期價／過期來源明標 analysis-only、禁止投注，冇 snapshot proof 不能繞過 firewall。
- [ ] 真實未開賽賽事端到端＋Python／Node regression；檢查公開 NBA dashboard。
- [ ] quick／完整 gate、exact-scope 保存部署、核對生產、清理 worktree。

研究及驗證輸出先放 /private/tmp；若超過 1GB 先確認外置碟並改用既定 scratch。今日已開賽資料只讀診斷，唔補造 immutable 預測。


## 修正及測試紀錄（發佈前）

另外修正單場 refresh 驗證／編譯掃入已開賽或未完成報告，以及匯總將三個空白分析欄目誤報為三個 SGM。只有有真實組合報價嘅欄目計入 SGM 數目。

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=Horse_Racing_Dashboard python3 -m pytest .agents/skills/nba/nba_daily_auto/tests Horse_Racing_Dashboard/tests -q`：438 passed。
- `node --test Horse_Racing_Dashboard/tests/test_static_template.mjs`：84 passed。
- `./檢查.sh --quick`：通過。
- 真實 BKN_CLE（2026-10-25）正式 orchestrator：exit 0，防火牆零 block、零 warning；三個空白欄目均為 NO BET，唔當正面 SGM 發佈證據。MIL_PHI 未開球員市場，exit 75 保留重試。
- GSW_PHX／HOU_ATL 正式賽前來源驗證進行中。此刻只可稱工程修正已驗證；真正有價 SGM、公開頁面、完整 release gate／activation 證據要等完成後核實，唔預先聲稱成功。

所有 regression 都維持 300 秒 quote TTL、30 分鐘 availability 時限、真實 SGM 價、正 EV 同開賽前閘。快照分析重驗完整 firewall 喺原本 snapshot 時間嘅 verdict，四份檔案全數驗 SHA256／size；只限 production／final_refresh、指定日期、開賽前、非 blocked 場次。保留原始 joint probability／EV，決策固定 OBSERVE，唔產生 banker 或投注表格。

多場 refresh 額外驗證：scheduler 完成逐場重跑後以 `--compile-only --games <本次成功場次>` 合併一次；已開賽場次唔會掃入，合併驗證失敗仍停止發佈。已加成功／失敗回歸測試。

零組合情況另外明示「日期＋冇合格建議／分析已完成」，避免成功 NO BET 同 pipeline 壞咗都只見歷史案例。
