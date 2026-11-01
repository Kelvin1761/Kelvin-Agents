# EXP-20261101-29：歷史 observation 時鐘與固定身份修補重播

狀態：**研究時鐘投影器及全量診斷完成；未改現役 reader／模型，未證明準確度改善。** 接續 [EXP-28](EXP-20261101-28-tennis-memory-identity-split.md)的反例，沿用原 frozen DB／ruler，不改歷史切窗、不重開 15 個 REJECT_DEV。

## 實作界線

新增 `tennis-wong-choi/src/tennis_wc/research_history_clock.py`。`select_recorded_history` 只讀 caller 提供的 observation payload，嚴格要求 `observed_at < cutoff`，不從今日可變 history 補欄位，亦不拿 match_date／created_at 冒充當時發布時鐘。

- CREATED 可提供當時記錄的 after-image；LEGACY_CAPTURE、SUPERSEDED、HOLD 的 before-image 不倒填為較早已知狀態。
- repair 的 BEFORE／LINKED／RESTORED 等中間記錄暫扣，完整雙側 APPLIED／ROLLED_BACK receipt 才一次供應四個狀態。整批時鐘或 payload 不合格時不輸出半批。
- rollback 恢復舊 created_at 不會恢復舊可用時鐘；恢復後的狀態從 rollback observation 才已記錄。
- 未知事件種類、缺／無 timezone／倒退時鐘、矛盾 CREATED、缺 after-image、inactive、self-pair 及非 cutoff 日之前的比賽均明列 held。不同時區正規化後比較，等於 cutoff 亦排除。

輸出資格固定為 **`LAST_RECORDED_STATE_NOT_RUNTIME_PARITY`**。它只重播已記錄狀態，不認證 source publication、人物身份、完整特徵／prediction lineage，亦不宣稱今日 DB 值就是過去 runtime 用值。沒有 observations 的歷史行不因「比賽已經好耐」而自動安全；audits 的 held 數目也不能當模型特徵或新的選樣條件。

| 欄位 | cutoff 前可得證據 | 本輪判斷 |
|---|---|---|
| observed_at／after-image | timezone 有效且嚴格早於 cutoff 的已記錄 payload | recorded-state 層通過；不等於 source publication 或 runtime parity |
| match_date／created_at | 只能檢查日期及邏輯一致性 | 用來冒充早年身份可用性會洩漏；本輪不這樣推論 |
| player_id／opponent_id | 只取當時 after-image；不套今日 canonical mapping | clock 層可重播，獨立人物身份仍 FLAG |
| hold_rate 等 rates | 只使用 payload 實際存在值 | 缺值不補；未因此完成來源／main-tour 資格 |
| opponent_elo | 原 recorded value；132 行與可變表不同 | 不採今日 drift 值；原值是否當場前計算仍 FLAG |
| point exposure／未記錄欄位 | 此投影器沒有來源證明 | 保留缺失，不能補今日值或宣稱 serve 候選已齊 |

## 完整 frozen 範圍結果

以原 DB SHA `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`，先重驗完整 hash，再讀全部 **424,823 history IDs／6,515 observations**，沒有縮細語料或只測有利案例。observation 類型為 CREATED 4,980、LEGACY_CAPTURE 1,447、LEGACY_SOURCE_CONTEXT_HOLD 88；最早記錄為 2026-10-26，無從認證更早年份的完整當時狀態。

| cutoff（UTC） | recorded ACTIVE | before-image／pending held | 無 cutoff 前 after-image | 有 hold_rate |
|---|---:|---:|---:|---:|
| 2025-01-01 00:00 | 0 | 0 | 424823 | 0 |
| 2026-10-28 00:00 | 2442 | 1535 | 420846 | 130 |
| 2026-11-01 00:00 | 4980 | 1535 | 418308 | 130 |

每列保留完整 row-flow，ACTIVE＋各 held 總和均為 424823。11-01 的 recorded snapshots 是 TennisExplorer 3296、composite 1552、TML 132。僅 130 個非空 hold_rate，全部 ATP Challenger：72 個 own-player IDs，4 人有 ≥5 行，最多 5 行；**不是原計劃 main-tour ATP／WTA 的合格 serve 候選，不能因 Challenger 有資料就換研究範圍。** snapshots 不含的 rate／count 不從今日 history 補成值。

以上只是 after-image coverage，不是所有 raw source 的可重播上限。缺 observation 不等於原始資料不存在；從原始 response 的實際擷取時鐘另行重播 parser／身份／Elo，需要獨立資格及 parity 驗證，本輪沒有把這條路宣判不可行或直接當安全。

另比較 4980 個 recorded snapshot 與同一 frozen DB 的 current 欄位，發現 **132 行 opponent_elo 不同**；其餘所記錄 snapshot 欄位無差異。投影器保留原 recorded value，不拿更新後 Elo 填回。這是可變值差異證據，未判斷所有 Elo 值的生成方式、確切更新時間或任何歷史 prediction 實際使用情況。

## 原反例及 rollback

固定 EXP-28 同一來源 pair 24211／24212、同一假設 target 19626、同一 proposal hash，在 `:memory:` 再次 apply／rollback。proposal 與前件逐欄相同，不改 target 或挑另一個案例救結果。

| 讀取 | 結果 |
|---|---|
| 現役 reader 的 EXP-28 反例 | 以 2025 cutoff 可讀入本輪新建的 2021 行 |
| 新 projector：2025 cutoff，apply 後及 rollback 後 | **0 行** |
| 新 projector：apply observation 之後 | 2 個新 ACTIVE snapshots |
| 新 projector：rollback observation 之後 | 2 個 restored ACTIVE snapshots，可用時鐘為 rollback，沒有倒填 |

「observation 之後」使用該 receipt 時鐘加一秒的機制檢查，不是實際賽前 prediction、可執行投注或新 forward。來源 external ID 的獨立身份、mapping／fixture closure 未因此合格，現役 13 日 guard 未改。

## 驗證及下一步

28 個新增時鐘反例測試通過；連同先前修補器共 56 targeted tests 通過。涵蓋嚴格 cutoff／timezone、未來資料不改較早 rows、缺欄位不補今日值、before-image／pending hold、雙側 apply／rollback 時鐘、整批失敗原子性、錯 ID／日期／時鐘、矛盾 CREATED、未知種類、source-reference after-image 及 eligibility。`./檢查.sh --quick` 已通過。

本輪開工時內置 free 約16GiB，之前 <10GB 的大型實驗空間限制已解除；這不解除資料資格閘。本輪沒有新 fit／大型 DB 副本、沒有修改 native prediction 或 live DB。下一步要為未來輸入建立可核對的當下完整 snapshot／source receipts，補獨立身份與 prediction lineage；不能將它倒填成舊年份的觀察。main-tour serve 證據不足仍保持不足，不把 130 行 Challenger 當作原研究已準備好。

## 證據

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/recorded-history-clock-v1/`，保存執行前 protocol、source.py、完整 final-row-flow、recorded snapshots、固定 split observations、result、兩個 module 當時 source 及 artifact-manifest。

原命令：repo 根目錄，`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python /private/tmp/tennis-recorded-history-clock-20261101.py`。重播須改成新輸出目錄；全程 frozen DB 以 ro/immutable 開啟，未打開 live DB。投影器的合成測試及原生 observation 重播不是獨立人物／模型準確度 oracle，qualified forward 數目沒有因此增加。

完整 `./檢查.sh` 已通過（all suites、1630 秒、Tennis 1121 passed）。今輪程式／測試／筆記按未完成研究規則保存分支 `codex-tennis-point-input-delivery-20261101`，未 merge／activate。quick、full 及原生重播 log 原位 `/private/tmp/tennis-history-clock-quick-20261101.log`、`tennis-history-clock-full-20261101.log`、`tennis-recorded-history-clock-20261101.log`，另存外置證據根 `recorded-history-clock-verification-v1/` 並核對 hash。
