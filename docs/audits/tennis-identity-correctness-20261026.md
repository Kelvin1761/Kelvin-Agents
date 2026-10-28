# Tennis 身份、賽果及觀測時鐘修正（2026-10-26）

用戶授權：先修所有可確認 bug，之後先做模型改善。本批屬可獨立證明嘅正確性修正，
**唔係已證明嘅準確度／盈利改善，未完成餘下 bug 清單前唔進行模型 promotion**。

## 已重現及修正

1. **Provider event key 重用會覆寫參賽者**：live match `21718`，composite `185138`：
   raw `24636`（10-25 07:28:37Z）係 Tsitsipas／Fritz，raw `24756`（10-26 07:22:17Z）
   係 Hijikata／Fritz，舊 Tsitsipas 賽果留喺同一個 mutable row。
   新 writer 將舊 row 保存為 SUPERSEDED generation，保留原本 pairing／日期同 child records，
   新 pair 建新 match ID；舊 event key 以 retired suffix 保存，current generation 用原 provider key。
   已完賽同 pair 喺新日期／賽事重用 key 亦分版本；只係來源倒轉順序則保留既有 a/b 意義。
2. **球員 alias 可以改名覆蓋另一個人**：現有 provider player key 轉成不相容姓名／tour 明確拒絕，
   保留原人同 history。唔用同姓同首字母將兩個完整不同名當同一人；拒絕有 log 同 raw evidence。
3. **Odds 只靠 event ID 接線**：daily／event／preclose 都核對兩位球員；不符時保留 raw、
   標記既有 fixture DISPUTED，唔將新 pairing 價格寫落舊 fixture。名稱候選多於一場會拒絕，
   唔隨意揀第一行。真正 live rows 無兩位姓名亦拒絕；靜態 mock provider 保留明確 fixture-key 測試路徑。
4. **賽事下架會刪歷史**：舊 daily pruning 刪 odds_snapshots／market_odds_snapshots／market_predictions。
   改為 NOT_LISTED 狀態，保留原價同 forecast；pair 再次被來源列出可恢復 ACTIVE。
   SUPERSEDED／DISPUTED／NOT_LISTED 都唔進入本日定價、推薦及 coverage 分母。
   不再喺每次 ingest 自動改寫所有舊 selection sides。
5. **只檢查勝方共識，唔檢查比分**：新增 overlapping games／sets／aces／DF／首盤等逐盤事實比對。
   缺欄位唔當矛盾；同勝方但不同比分、單來源完整盤數同勝方相反、壞 JSON 都暫停結算／排除決策證據。
   唔代來源揀一份比分，亦唔重寫已保存舊注單。
6. **mutable result.created_at 無法重建知識時鐘**：新增 append-only result_observations，
   INSERT／有內容變化 UPDATE／DELETE 由 DB triggers 保存狀態、真實觀測時間及 pairing。
   重複同結果只改 created_at 唔會抹走原先 observation。遷移舊資料標 LEGACY_SEED，
   只代表遷移時已知，唔回填假「當年觀測時間」。歷史 calibration 用 cutoff 前實際觀測狀態；
   因而某些舊窗可能不足資料，應明確回報不足，唔補造樣本。
7. **開始時間後補／改動可改寫 forecast 分類**：新 prediction JSON 保存當時 pairing／日期／start clock；
   讀新 forecast 用保存嘅 clock，未知 clock 唔借後來資料補成賽前。inactive／錯參賽者唔可存新 prediction。
   舊 forecast 無呢份 evidence 仍屬 legacy 限制，冇重寫原 JSON。
8. **字串比較時間會錯排 timezone／fractional seconds**：PIT classifier 同 tracker SQL 改比較時刻；
   壞日期／無 timezone 無法證明賽前，標不可核實。
9. **查詢缺索引**：init migration 加 predictions(match_id,id)／odds_snapshots(match_id,id)，
   與新觀測表索引；無改評分權重或概率公式。

10. **API odds identity／event refresh**：API normalizer 無輸出姓名，event refresh 又用 game ID
    當 odds-data ID，並傳空 team_names，不能產生已核實 pair。改由唯一 fixture metadata 取正確
    odds-data ID，同時保存原姓名；無唯一 metadata 明確失敗。timestamp 記真正觀測時刻，
    書商原 last_updated 保留 source_updated_at／raw，唔當成我們當時已看過。
    三項新測試喺舊版 3 failed／8 passed，再修正。

## Legacy identity 處理

`PYTHONPATH=src python scripts/audit_fixture_identity.py --db <DB> --output <report.json>` 預設唯讀。
掃描仍保存嘅 raw fixture 版本，只喺 pair／side order 已變且已有更早 artifacts 才列可疑鏈，
已由新 generation writer 建立嘅 match 唔誤當 legacy mutation。

10-26 live 唯讀掃描：12,450 個 raw fixture rows，3,807 個仍有 raw 嘅 keys；
唯一有 surviving proof 同 prior artifacts 嘅 legacy case 係 `21718`。
呢個係**存活證據覆蓋**，唔係「其餘全部乾淨」—— 過往 raw retention 已令部分版本不可還原。

`--apply --backup-dir <外置碟目錄>` 先做 SQLite 一致備份及 quick_check，
再按 exact row state（包括 updated_at）核對；過期 plan 失敗，唔猜舊身份、唔移動舊 forecasts／注單。
只標 DISPUTED 並保存 before／reason。大型 DB 備份要求真正 mounted 外置碟。

首次 full gate 喺測試途中主動中止（exit -15，未 stage／commit），因為補查 API 路徑
發現上述相容問題；唔係 gate 通過或測試 skip。補好 provider 後從最新 main 重新完整驗證。

## 驗證及尚餘工作

- 三項 fixture bug 先喺原版重現：3 failed；修後通過，另加 event／preclose、alias、下架、
  source ambiguity、legacy quarantine stale-plan、forecast freeze、比分共識同 immutable labels 測試。
- 發佈前本地 Tennis **790 passed（33.15s）**；quick 全綠。immutable full gate 最終結果見 release log；發佈前須全綠。
- 下一批仍要處理：forecast quality／serve sample IDs freeze；match-feature history 知識時鐘；
  來源重複／越界值；舊錯標 player-total evidence；本日 scoped integrity 接 readiness。
  會改特徵／可靠度權重嘅修正要做固定語料 A/B，唔混入今批聲稱已改善模型。
- 正式啟用後再以已備份 exact plan 處理 live legacy case，並核對 runtime SHA／migration／觀測時鐘。
