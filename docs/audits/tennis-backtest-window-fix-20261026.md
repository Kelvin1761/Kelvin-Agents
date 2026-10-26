# Tennis 回測報表及 WTA source 品質修正 — 2026-10-26

原審計 `a920bb29` 已證實、獨立 evaluation release；唔同 simulator candidate 合併。

- `run_backtest(start,end)` 舊版 forecast counts 有日期窗，但 nested `ledger_summary()`
  讀全期帳目。報表查六月，七月輸贏亦混入 ROI。
- 舊 ROI 分母包括 PENDING stake；而且 metadata inner join 會漏未分類比賽，
  多來源 tournament metadata 又會重複計數。
- 新版 bet ledger 按 match_date 同窗，只以 WON／LOST settled stake 計 ROI。
  全部已記錄 bets／總 stake 仍另列；無結算時 ROI 係 null。
- Metadata latest row 用 LEFT JOIN，保留未分類 forecast，每場只計一次。
- 無效 calendar 日期及反轉日期窗明確拒絕。原 counts 仍係 stored latest forecasts，包含 rebuilds；
  note 明確指出**唔係 point-in-time 策略回測證據**。
- 真實帳目／舊 forecasts／model scoring／WTA source／投注門檻都無改。
  報表嘅 global CLV／combo aggregations 不再混入指定日期窗嘅 ledger 子摘要。

Fixture：六月一注 WON（+0.9u）、一注 PENDING，七月一注 LOST；
六月正確顯示 2 bets、settled stake 1u、P/L +0.9u、ROI 90%。
加入兩份 metadata 後 forecast 數仍係 2；metadata 缺失亦保留 2；反轉日期 raises。

定向 fixture 通過；交付由 `./檢查.sh --quick`、Tennis 全套及 immutable full gate 驗證。
呢個係報表正確性修正，唔係預測準確度／策略回報改善聲稱。

## WTA collector 唔再將有值當成有效

EXP-20261026-04 已獨立發現全場 statistics 可以係 partial／不可能值，舊 collector 只要
有 serve-points 同 winner 就標 OK。新 intake 驗證非負整數 counts、分子／分母關係、
0..1 rates、全場比分與兩邊 service-game exposure；支援完整歷史 advantage sets。

- 不合理 totals 標 `INVALID_STATS`；退賽標 `PARTIAL_MATCH`；raw response 及衍生欄位保留供查。
- 舊 OK cache 會先驗證 immutable raw body；不合格會重試，唔永久跳過。
- 如果舊 raw 已遺失／不可核實，而 refresh 失敗，保留原有 values、raw pointer 同 capture 時間，
  標 `UNVERIFIED_STATS`；唔用空值抹走唯一剩低嘅資料。之後取得 valid stats 才更新。
- Summary 區分「有 stats」「有效」「invalid」「partial」；health 加 status counts，
  feed_latest 只讀 OK。原始統計可能仍有未知實際比賽日期，OK 只代表物理統計檢查，唔係 PIT 證明。
- `player_match_history` 同所有模型 readers 保持原設定，**唔會因為 intake 修好就接入新 WTA source**。
- 本次測試只寫 temp DB；無直接改 live 舊 forecasts、注單、賽果。修正會喺之後正常 ingest 時驗證／重試舊 source cache。

Fixture 包括 0..1 rates 但只有半場 exposure、負數衍生 counts、first-serve-in 超過總 points、
aces 超過 serve points、legacy 假 OK 重試、退賽與 9-7 歷史 advantage set。

合併已啟用嘅 simulator 修正之後，Tennis **761 passed（17.42s）**，final quick 全綠；
再由本次獨立 evaluation release 跑完整 immutable gate。原模型／實驗判決規則未改。

## 完整閘門重驗

第一次 immutable full gate 15/16 suites 通過，Tennis 761 passed。共用 research cursor
fixture 喺外置碟 cold imports 未到 ready marker 已觸發 1 秒 timeout；原測試獨立重跑通過。
只將該 fixture timeout 改為 10 秒，保留 ready、TIMED_OUT／PREEMPTED、cursor 不前進全部斷言；
生產 supervision 及模型判決規則無改。修正後重跑兩個分支、quick 同完整 release gate。
