# NBA Wong Choi Readiness Audit — 2026-08-26

## Decision

NBA automation 嘅 code／operations layer 已達 pre-season ready，但未可以稱為 production-proven。原因唔係仲有已知 critical code bug，而係 repo 暫時冇 2026-27 live prediction + settled archive，可供 forward QA 同模型表現判決。

## Fixed in this audit

| Area | Before | Resolution |
|---|---|---|
| Sydney schedule date | ESPN 前一日同當日 events 直接 union，可混入下一個 Sydney calendar day | 共用 `nba_schedule.py` 將 UTC event time 轉 Australia/Sydney，再做 exact-date filter |
| Schedule completeness | 少咗官方比賽仍可建立 immutable snapshot | ESPN official tags 同 verified Sportsbet tags 必須一對一；missing／unexpected 一律 temporary failure |
| 2026-27 season | October 2026 可被 2025-26 config 誤判為 playoffs；roster/H2H hardcode 舊季 | 更新 season calendar；加入 date-derived nba_api season/current+previous season |
| Sportsbet contract | schema 仍驗舊 `line/odds` shape，live Claw 寫 `lines` map | schema 對齊 live output；strict mode；schema 缺失／損壞 fail closed；全 array validation |
| ML loading | predictor project root 多上一層，manual run 靜默 fallback legacy | 四個 NBA ML scripts project root 修正；X+ hit 判定全部改為 `>=` |
| Team tags | Sportsbet 用 `WSH`，結果用 `WAS` | canonical abbreviation layer；legacy WSH 仍可於 reflector/result match |
| Postgame verification | 同姓球員可錯配；DNP 計 miss；全未核實仍可 archive；合法全日 NO BET 永遠留喺 live folder | exact-name-first；ambiguous surname fail；DNP void；`unverified=0` 先 archive；只容許 Dashboard 明確驗證嘅 NO BET 以 0 legs 歸檔 |
| Dashboard settlement | DNP 可當 lost；void combo odds處理不明 | single DNP proposal = void；含 void leg 嘅 SGM 不自動 proposal，留 warning 人手處理 |
| Compile-only | 編譯後編輯可繞過 report firewall，而且失敗仍 exit 0 | compile-only 不 crawl；重新驗證所有 reports；失敗 exit 1、禁止 deploy |
| Runtime safety | subprocess 可能用錯 Python／無 timeout | 使用 `sys.executable`；orchestrator child process 加 timeout |
| Season lifecycle | Off-season 手動分類可變 MID_SEASON；preseason 混入 EARLY_SEASON | 六階段 public classifier；POSTSEASON subtype；preseason shadow-only／NO BET；舊 strategy phase 只留作 scoring compatibility |

## Verification

- NBA pipeline integration checks：75 passed。
- NBA scheduler checks：17 passed。
- NBA reflector safety checks：5 passed。
- Dashboard DNP regression：passed。
- `./檢查.sh --quick`：passed。
- End-to-end 六階段報告生成＋firewall：passed。
- Full repo gate：all suites passed（NBA pytest suite 32 passed）。
- Live off-season health：ESPN reachable、0 games、`OFF_SEASON`／`dormant`。

## Remaining gates / risks

1. 冇 historical NBA analysis archive，因此今次冇足夠 evidence 判斷 ROI、Brier、calibration、drawdown 或「模型改善」。
2. 第一份完整 prediction snapshot 會保持 immutable；21:00 成功後，00:30／06:30 目前唔會 refresh 到更接近開賽嘅 odds／injury state。要喺開季前定案 warm-up vs final snapshot policy。
3. Scheduler 目前只於 startup 補昨日 postgame；多日離線 backlog 未獲授權自動逐日 archive／deploy／發 Telegram。
4. 2027 playoffs start 以 Play-In 4 月 16 日完結後翌日作 operational inference；NBA 發佈更精確 postseason dates 時要更新 config。

## Stage decision

保持 Stage 4A。第一個 2026-27 live pregame 及 postgame gate 通過，再 revisit roadmap 同決定係咪進入 Stage 4B Evidence Core。
