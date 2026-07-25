# 旺財 Horses / NBA / Tennis Dashboard 實施計劃

## 目標

沿用現有 `wongchoi-dashboard.pages.dev`，以頂部 `🏇 Horses / 🏀 NBA / 🎾 Tennis` segmented switch 切換三個獨立頁面；每個頁面都由 Wong Choi 正式輸出載入建議，並可用最少步驟完成「閱讀 → 記錄落注 → 結算 → ROI 檢討」。

## 已完成嘅 Horses 穩定性修正

- [x] 已匯入 ROI ledger 改為權威資料；本機投注面板只負責落注流程，唔再覆蓋已匯入賽果。
- [x] ROI `PATCH` 編輯會按名次及賠率重新計算 `status / payout / net_profit`。
- [x] ROI `DELETE` 以 tombstone 隱藏記錄，避免舊 static snapshot 喺下次 deploy 復活。
- [x] ROI 每條已匯入記錄加入「編輯／刪除」，並完成桌面、390px 手機及 API regression tests。

## 2026-07-25 Prototype 已落地

- [x] 現有 static dashboard header 已加入 `🏇 Horses / 🏀 NBA / 🎾 Tennis` switch；Horses 原有賽事及 ROI route 保持不變。
- [x] 加入 versioned `sports_history` snapshot，先用 repo 內 4 個 NBA Reflector 案例及 4 個已結算 Tennis 案例驗證閱讀層次。
- [x] NBA 無保存原始賠率嘅案例一律顯示「原始賠率未存檔」，投注表單要求人手輸入實際 odds，無製造測試賠率。
- [x] Tennis 卡片並列 model probability、market fair probability、edge、EV、實際結果、主要風險及 provenance；combo 顯示逐腳結果。
- [x] NBA／Tennis 各自有「歷史分析／我的投注／ROI」；Bet Slip 支援新增、編輯、刪除、pending/won/lost/void 同 bookmaker/note。
- [x] 新增 Cloudflare KV prototype endpoint `/api/sports-bets`；create 時凍結 `analysis_snapshot`，其後改結果唔會被新分析覆寫。
- [x] API／render／ROI regression tests 35/35 通過；另有 Python exporter contract tests 4/4，static build 同桌面瀏覽器新增 → 編輯 → ROI flow 已驗證。
- [x] URL state 已支援 `?sport=horses|nba|tennis`；重載及分享連結會保留 sport。
- [x] Tennis 正式 exporter 已直接讀 `tennis_wc.db` 嘅合資格 `BET` 建議及 `combo_tracker`，組合注逐腳可編輯並保存。
- [x] NBA 正式 exporter 只接受已通過標記檢查嘅 `Sportsbet_Odds_*.json` + `Game_*_Full_Analysis.md`；repo 無正式當日 artifact 時會回傳 `unavailable/blocked`，絕不將 fixture 當 live 建議。
- [ ] Release B 程式未上 production；NBA 完整 singles/banker/parlay exporter、D1 audit ledger、自動結算同真正 390px browser visual pass 仍按下方工作包逐步完成。

## 2026-07-25 Release B 工程狀態

- [x] 新增 `schema_version=2` multi-sport feed、`analysis_run_id`、生成時間、來源檔、validation status、warnings 同穩定 recommendation ID。
- [x] Static build 會自動生成 NBA／Tennis live feed；合資格 live feed 取代歷史 fixture，缺資料時保留清楚 fallback／warning。
- [x] Tennis 實際 build 驗證到 4 個 2026-07-25 建議：2 個 singles、1 個 single-leg combo、1 個 2-leg combo。
- [x] Desktop browser 驗證 Tennis live feed、2-leg 編輯／儲存、NBA fallback 同 URL 切換。
- [ ] 未 deploy；現時 production 網址仍維持原版本。

## 目標資料流

```text
HKJC/AU orchestrator ─┐
NBA orchestrator ─────┼─> Python dashboard exporters ─> sport snapshots
Tennis CLI/SQLite ────┘                                 │
                                                       ▼
Wong Choi Dashboard ──> 統一 Bet Slip ──> D1 Ledger ──> 結算 / ROI / CLV
```

瀏覽器唔應該自行解析長篇 Markdown。每條 pipeline 要輸出版本化、可驗證嘅 JSON companion artifact；Markdown 保留俾「詳細分析」閱讀。

## 9 個可交付工作包

- [x] 1. 建立多運動 shell：喺現有 header 加 `Horses / NBA / Tennis` switch，URL 保存 `?sport=horses|nba|tennis`，手機版固定顯示三個 44px touch targets；保留 Horses 現有賽事及 ROI 功能。→ 已通過 URL state unit test及 desktop browser 驗收；390px 實機 visual pass 留喺工作包 9。

- [x] 2. 定義共用 snapshot contract：已加入 `schema_version`、`analysis_run_id`、`generated_at`、`sport`、`recommendations`、`source_files`、`validation_status`；每個 recommendation 使用來源 row／game combo key 建立穩定 ID。→ Contract tests 已拒絕缺 live odds、重複 ID 及未通過 validator 嘅輸出；獨立 `events` collection 視實際 NBA singles exporter 需要再補。

- [ ] 3. 建 NBA exporter：第一段已完成正式 artifact pairing、報告標記驗證、SGM 組合賠率及 legs 解析；缺 Sportsbet JSON 會整場 blocked。下一段補 `nba_game_data` singles、Banker、跨場 Parlay、模型概率／edge／L10 詳情。→ 驗收：同一場重跑只更新同一 `analysis_run_id/event_id`，畫面數字同正式報告一致。

- [ ] 4. 建 Tennis exporter：`market_predictions decision=BET`、pricing、minimum odds、confidence、risk、provenance 及 `combo_tracker` 已接通；下一段補 Daily Report tier 排序、surface/tour、WATCHLIST 同可摺疊 `NO_BET`。→ 驗收：live feed 目前只展示合資格 BET／combo rows，無用 mock provider 資料。

- [x] 5. 建統一 Bet Slip prototype：NBA/Tennis 建議可一鍵預填 selection、market、分析 odds、stake、bookmaker 及備註；支援 single/combo，每隻 leg 可修改及保存，原始 `analysis_snapshot` 保持 immutable。→ 正式跨裝置 ledger/audit 會由工作包 6 將 KV prototype 升級至 D1。

- [ ] 6. 將正式投注帳簿放入 Cloudflare D1：新增 `analysis_runs`、`recommendations`、`bets`、`bet_legs`、`settlements`、`audit_log`；`bets` 保存 sport、bet_type、odds_taken、stake、status、payout、profit、source recommendation；所有 create/update/delete 使用 idempotency key、`updated_at` 及 audit trail。現有 `WC_STATE` KV 暫時保留做 Horses panel sync，再以一次性 migration 將 ROI ledger 搬入 D1。→ 驗收：跨裝置一致、重複 submit 唔會產生重複注、任何編輯都有前後值可追查。

- [ ] 7. 建結算流程：Horses 保留手動名次及 scratch；NBA 由 reflector results/PBP 對 player props、SGM legs 結算；Tennis 接駁現有 `settle-bets` 及 match results。所有自動結算先顯示 source/time，允許人工 override，但 override 必須留 audit reason。→ 驗收：single、multi-leg win/loss/void/partial-void 都有 fixtures，重跑 settlement 結果保持一致。

- [ ] 8. 建各 sport 閱讀與 ROI 頁：每頁有「今日建議／我的投注／ROI」三層；Horses 保留 HKJC/AU breakdown；NBA 加 market/player/team/SGM vs single；Tennis 加 tour/surface/market/tier/CLV。全站另有 Portfolio view 顯示總 bankroll、按 sport P&L、pending exposure、日／月曲線。→ 驗收：所有總數可由 ledger rows 重算，pending 唔計入 realised P&L，void stake 唔計 loss。

- [ ] 9. 最終驗證及 rollout：API unit tests、exporter contract tests、ROI calculation fixtures、Playwright desktop/mobile E2E、accessibility audit；先上 read-only NBA/Tennis，再開 Bet Slip，再啟用 D1 settlement，最後 migration Horses ROI。每階段保留 feature flag 同 KV export backup。→ 驗收：舊 Horses URL/資料無回歸、三個 post-success pipeline 能自動更新同一 Pages project、production smoke test 全部通過。

## 建議頁面結構

| Sport | 第一屏 | 第二層 | 投注記錄重點 |
|---|---|---|---|
| Horses | 賽馬日、場次、Top 2 候選 | 馬匹完整分析、投注面板 | 馬場／場次／馬號／位置賠率／名次 |
| NBA | Banker、Best SGM、Cross-game Parlay | Game → prop cards → Full Analysis | player／market／line／O-U／SGM legs |
| Tennis | 穩膽、價值注、高賠細注 | Match → pricing/factors/provenance | player／market／surface／combo legs／CLV |

## 上線次序

1. **Release A（已完成程式）**：Horses ROI 穩定、編輯、刪除。
2. **Release B（最低風險）**：加入 sport switch，同 domain 上線 read-only NBA/Tennis。
3. **Release C（最有即時價值）**：統一 Bet Slip + D1 ledger + 手動結算。
4. **Release D（自動化）**：NBA/Tennis 自動結算、CLV、Portfolio ROI。
5. **Release E（收尾）**：Horses KV ROI migration、audit/backup、舊資料核對。

## 完成定義

- 三個 sport 都可以喺分析完成後自動出現喺同一 domain。
- 建議數字有來源、版本及 validator 狀態，Dashboard 唔自行發明或重算模型數據。
- 每一注都可以新增、編輯、刪除、結算及追蹤修改歷史。
- 同一注喺任何裝置顯示相同結果；重載、重新 deploy 或舊 snapshot 都唔會令賽果消失／改變。
- Portfolio、各 sport ROI 同底層 ledger 可逐行對數。
