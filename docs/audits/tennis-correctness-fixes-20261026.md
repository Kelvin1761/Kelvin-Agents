# Tennis 審計後正確性修正 — 2026-10-26

授權：用戶審計後要求繼續修正及 refine。基準 `3dc209bf4561eee6890c0a0ce35dd59865efbb7f`。

## 已修正

- 離線 match corpus 每場只讀第一個有效賽前 forecast、首個有效賽前 odds；
  有異議／不完整／退賽結果唔作校準證據。模型量度用已保存嘅 Elo backbone，
  唔用今日歷史重建過去 prediction。
- Validation SQL 失敗會輸出 critical failure；報告檢查本身失敗亦有明確警告，
  唔會靜靜當「零問題」。舊 schema 缺 canonical identity 欄位仍可檢查。
- 同一 match 多來源 winner 相反、或者 winner 唔係兩位參賽者：
  pending prop／match／CLV／combo 暫停新結算；唔按 provider 優先序揀一個贏家。
  已保存結算保留作核對；ROI、校準、scorecard、CLV decision evidence 排除爭議 fixture。
- ATP Grand Slam main draw 係 BO5，現有 BO3 prop math 明確停止定價及記錄，
  報告顯示原因；WTA 同 qualifying 仍係 BO3。未知 tour 嘅 Slam fixture 亦停止。

呢批係資料／程式正確性修正，**唔聲稱提高準確率或回報**。
prop families 嘅正式 eligibility、權重、Kelly／edge 門檻維持現有設定。
WTA 新 serve-history 研究獨立見 EXP-20261026-04，未接入正式 pricing。

## 驗證及邊界

- 原審計修正基礎：Tennis 729 tests；今次新增 fixture 覆蓋 BO5 不進入 simulator／tracker、
  qualifying BO3、爭議結果 pending→來源一致先結算、舊帳不覆寫、爭議證據排除、
  combo leg unresolved、報告檢查失敗可見。
- `./檢查.sh --quick` 已過；完整 repo gate 交由發佈前 `./檢查.sh` 同 immutable release gate。
- 未對 live DB 改 winner、刪歷史、重寫舊 prediction 或標記為賽前資料。
- 不同來源 score 有分歧但 winner 一致，仍需獨立 score reconciliation；今次 guard
  只處理 winner conflict／invalid participant，唔聲稱解決所有結果品質問題。
- 新 WTA backfill 只存外置碟研究 DB，唔會混入 `player_match_history` 重複計算勝負。

完整原審計：[tennis-model-review-20261026.md](tennis-model-review-20261026.md)。
