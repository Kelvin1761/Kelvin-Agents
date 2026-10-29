# Tennis Toray：當屆場地資料修正

2026-10-29 Sydney；接續統一研究 F00 輸入診斷。呢次修正資料對應，**未證實準確度／ROI 改善**，亦無新訓練、改模型權重或重設 shadow。

## 問題及依據

實際名稱 `Toray Pan Pacific Open Tennis` 喺 curated resolver 同歷史 index 都回 `None`；加上 `Tournament` 後只有歷史 index 能解。Live tournament external ID `264-2026`，原 composite metadata 為 UNKNOWN／NULL。今朝保存 prediction 15853／15856 因此有 active surface Elo `missing_surface`，並套 UNKNOWN 級別既有 12% edge discount。

[WTA 官方 2026 overview](https://www.wtatennis.com/tournaments/1056/tokyo/2026)確認本屆 10 月 26 日至 11 月 1 日、WTA 500、室外硬地。今次唔按輸贏選 metadata，亦唔用其他年份文件推斷本屆。

## 修正及界線

- 加入本屆三個明確 Toray aliases、官方 URL 及日期上下界；無日期、錯年份、賽期外、ATP／泛稱 Tokyo／雙打及外圍賽尾綴不套用新 entry。
- Sportsbet fixture mapping 同正常 daily metadata backfill 傳入原 match_date。無日期嘅 caller 維持 unresolved；既有無日期限制嘅其他 curated entries 沿用原行為。
- tournament_levels 係 tournament-keyed，無獨立日期欄；因此 feature context 及 metadata audit 同樣檢查日期，防止保存過嘅本屆 row 被其他日期沿用。失效時保留 UNKNOWN／NULL 及可見 warning，唔抹走警告或放寬研究閘。
- 正常更新先建立新 curated row／原始 receipt，唔修改 composite 原 row。呢次 probe 冇寫 live DB、冇重做舊 prediction／settlement，亦冇重發正式 card。

## 同輸入敏感度檢查

唯讀 live DB 顯示本屆日期範圍內有 20 個 ACTIVE fixtures，其中 4 個喺 10 月 29 日；當朝 45 個保存 predictions 中 2 個 Toray。只將呢兩個已重現例子作 posthoc 敏感度檢查，唔將 fixture 數當新增合格樣本。

兩邊用同一 code/config 及無並行寫入嘅 DB 狀態重建；原連線一律 mode=ro／query_only，監察 data_version 前後相同。候選只在記憶代入已確認 metadata，重新計算相應 surface/level 特徵；無偽造 raw receipt（保留 missing_raw_response_id），唔當歷史完整預測或 PIT 證據。

| match ID | 原 raw P(A) | 硬地／WTA500 raw P(A) | 原選邊最終概率 | 修正後選邊最終概率 |
|---|---:|---:|---:|---:|
| 22019 | .595407900 | .625773286 | .595402 | .625773 |
| 22159 | .613688497 | .600161502 | .601941 | .600162 |

原硬地 Elo 欄實際複製 overall；修正後讀到不同硬地 rating。級別變為 WTA500 時按**既有** policy，discount 由 .12 變 0，故影響包括風險折扣，唔只係消失一個 warning。呢兩個例子無做賽果評估；概率升跌唔等於預測改善，亦唔代表全批其他輸入已合格。

## 驗證及交付

65 個相關測試通過（其中 metadata／feature builder 46 個）：日期上下界／別名、跨年／缺日期／錯 tour／其他賽事拒絕、backfill receipt 與來源、舊 row 保留、已保存 metadata 跨日期使用及 health audit 一致，原有 evidence／diagnostic tests 亦通過。Quick 通過；最終完整 suite／immutable SHA／activation 以 Central release manifest 為準。

Probe source／結果在 `/private/tmp/tennis-toray-probe.py`／`.json`，交付 checkpoint 另存原 external run 下 `toray-metadata/`；method source／結果均計 hash。無複製 1.9GB 語料。診斷 journal 上一個 release `a0fb0476` 已交付，等待下一個正常 run 驗收；本修正不令歷史 0 qualified feature projections 變成成功。

研究 15 個候選仍 REJECT_DEV；缺來源時鐘嘅 MCP／Slam 不入訓練，C14 實際結束時鐘缺口仍停止，C09 仍受合格 serve／市場合約前置條件限制。下一步按正常 run 保存嘅原樣 observations 查其餘具體來源問題，唔重試已拒絕嘅 WTA fresh-history 接線。
