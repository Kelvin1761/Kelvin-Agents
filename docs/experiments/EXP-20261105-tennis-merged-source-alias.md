# Tennis 已合併來源 alias 的正式 ID 驗證

2026-11-05 Sydney。從 origin/main `64aacf58f96daa7ffb58e5c0ff2dc10925a516d2` 開獨立 worktree。此為來源身份修復，沒有改權重、模型公式、評估規則或既有 15 個 REJECT_DEV。準確度改善目標仍未完成。

## 原因與驗證條件

部分 provider_entities 仍指向已合併舊列，舊列保留錯誤 tour。原讀取先以舊列 tour 拒收，未能到達已有正確姓名／tour 嘅正式 ID。先前隔離九筆 alias 遷移已驗證可恢復其中 11 場。本次改正常讀取及入庫入口，按每次新來源輸入重新驗證既有合併證據。

只有以下條件全部符合才可通過原 tour 衝突。來源姓名、provider entity_name、每一跳 players.name 同最新 merge log 的兩端姓名，全部須精確相同（只處理大小寫及空白）；姓名最少兩個完整 token；來源 tour 明示 ATP／WTA，最終未合併目標 tour 必須吻合。每一跳都要有對應最新合併收據及可解析時間，name alias 必須標為 merge 並指向同一已驗證路徑。缺表、缺收據、首字母、改名、錯 tour、斷鏈、循環或超過上限，一律保留拒收。沒有以模糊姓名或 Elo 深度替代這組證據。

讀取 existing_player_id 只作驗證，沒有 DML。正常 get_or_create_player 如需更新 alias，會比對舊 internal_entity_id 及 entity_name，取得寫入鎖後再次驗證完整證據。局部 savepoint 讓外層即使接住拒收例外，亦不會提交半完成 alias；外層原有交易工作保留。正常來源入庫可依已驗證 ID 寫新資料，未批量改寫現有歷史、賽果或預測。

## 固定來源及最新 DB 對照

公開 ESPN 2026-01-31 ATP／WTA 回應均已固定 SHA，涵蓋澳網 478 場單打、476 個來源 actor。原文及 hash 與先前 draw／BO5 研究相同，沒有重新下載或新增挑選 subset。現役 SQLite 用 mode=ro、query_only、100ms busy timeout、單一讀取交易及 5 秒 deadline，結束即 close；只輸出彙總及雜湊。基準以 git show 載入上述固定 commit，候選與基準讀同一個 DB snapshot。

| 檢查 | 基準 | 候選 |
|---|---:|---:|
| 身份衝突 actor | 12 | 3 |
| 至少一方衝突的來源賽事 | 17 | 6 |
| 已可解析且 ID 不變的 actor | 464 | 464 |

固定封存庫亦獨立重播，完整 SHA256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`。同一批 476 actor／478 場，該版本原衝突 13 人／18 場，候選剩 4 人／7 場，原 463 個解析 ID 不變。兩個 DB 版本恢復的九筆 alias plan SHA 均為 `770911d8a98c27521b136059f4fdaa28216005a3ccc3a76cd68f8379d0122c1d`，沒有換人或挑 subset。另直接回到封存庫逐一驗證原 13 個衝突，與記憶體結果相同。封存結果在 [frozen-result.json](patches/tennis_merged_source_alias_20261105/frozen-result.json)，live 彙總有獨立 identity projection hash，不將兩個資料狀態混用。

最初兩次封存直接重播分別在整批、32 actor 批次觸及 5 秒上限，未產生成功結果。最後在同一份 SHA 已驗證的 immutable 庫，只將身份欄位按主鍵分頁投影到記憶體，再加記憶體索引做同一組比較。每次實體庫連線維持 5 秒上限並關閉，原 DB 沒有建索引或改寫。live 仍為一次 5 秒 read transaction。沒有縮減來源 actor、原歷史 metadata 或變更評估資格。

9 個 actor 恢復讀取。另將必要 identity metadata 投影到 SQLite 記憶體，用正式 get_or_create_player 跑 9 次正常入庫。恰好 9 個 alias 指向正式 ID，9 個目標只改正常來源 metadata；舊 duplicate 列、Elo／排名數值、全部歷史投影及合併收據不變。整個交易 rollback 後五表逐列完全相同。現役資料庫寫入數為 0。這項結果不代表已回填 AO 歷史、已消除全庫身份問題或已新增合格 forward。

今早固定 57 場分析與這 9 位球員的原 ID／正式 ID 及完整姓名交集皆為 0，暫無證據這項修復會改變該 card。該 card 的 feature qualification 仍為 0，下一步需處理真正相關的來源／特徵證據。餘下三個身份衝突保留拒收，詳見外置研究目錄 espn-remaining-identity-evidence-20261105。

live 資料會持續改變，日後 default 命令遇到 beforeimage 已變會停止，不能冒充原比較。可重現的固定封存命令如下。重播程式及彙總見 [replay.py](patches/tennis_merged_source_alias_20261105/replay.py) 與 [result.json](patches/tennis_merged_source_alias_20261105/result.json)。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src python3 docs/experiments/patches/tennis_merged_source_alias_20261105/replay.py --db '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/ranking-date-contract/source.sqlite' --immutable
```

## 測試與發佈

53 個針對測試通過，覆蓋完整多跳、最新收據衝突、缺證據、首字母、完整循環、三種同期改動、外層捕捉例外的 savepoint 回退，以及真正歷史入口的雙方 ID／hold rate／勝負保存和拒收。quick 通過。完整 gate 與正式啟用以 Central immutable release manifest 為準，未確認啟用前不聲稱 production 已修復。

本次只處理來源接線，沒有模型升級或新夠 N 場判決的 forward 測試。原固定 cohort、dev／holdout、C14 workload qualification、F10 point-skill／joint-market 依賴與 Sportsbet 獨立評估保持。下一個量度重點是正常新入庫後，對真正受影響賽事檢查可用歷史與完整 feature evidence，再按原評估規則比較。
