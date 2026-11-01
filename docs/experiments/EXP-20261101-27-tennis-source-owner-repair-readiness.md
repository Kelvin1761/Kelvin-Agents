# EXP-20261101-27：球員歸屬修補前置核對及雙側 upsert 重播

狀態：**診斷完成，修補未實施，未證明準確度改善。** 接續 [EXP-26](EXP-20261101-26-tennis-source-owner-identity-audit.md)，不重新訓練、不修改 live DB、不更改原有資格旗標或判決規則。

## 1. 現行資料範圍

固定沿用上一輪預先選定的 reader 案例 1180、2110，擴至當前所有 canonical descendants：1180、2110、2711、4457、18527。2026-11-01 09:14:14 UTC，以唯讀 transaction 擷取這些 ID 參與的全部 history、相關 provider mappings、players 及 merge receipts；transaction 約 0.819 秒，關閉 live 連線後再處理。

共 **628 行**，624 ACTIVE、1 DISPUTED、3 SUPERSEDED。後續離線逐欄比較既有 frozen DB：

| 比較 | 行數／結果 |
|---|---|
| 全欄與 frozen 相同 | 432 |
| frozen 已有，但 opponent_elo 不同 | 192；其餘欄位相同 |
| frozen 沒有的新增行 | 4；保留未審核，不倒填舊 source-owner 結論 |

上一輪完整 ownership inventory 能對上其中 520 行：386 全欄相同、134 只有 opponent_elo 改動；另外 108 行未有該輪 public-source ownership 審核（包括上述 4 行新增）。**「未有舊審核」不同於「新加入 live DB」。** 本次不將 192 個 Elo 更新視為歸屬修正或合格歷史特徵，也沒有檢驗其歷史發布時鐘。

既有 raw-name 證據顯示，1180 群組混有 Stefan Kozlov、Toby Samuel、Cannon Kingsley、Alex Marti Pujolras 等 own-player 標籤；2110 群組混有 Christian Sigsgaard、Jumpei Yamasaki。每行雙方的出現次數不是獨立賽事數。這些標籤沿用已驗 hash 的 frozen raw evidence；本輪沒有重新下載全部 live raw body，也沒有將所有名稱差異判為不同人物。

## 2. 修補 API 的具體障礙

在 `:memory:` SQLite 複製原 schema 及固定來源行，直接呼叫現有 `upsert_history_observation`。不更改它的程式，亦不向 live DB 呼叫任何寫入操作。

第一個重播使用 history 24211，其原始 source reference 為 `ATP-2021-M-DC-2021-WG2-M-THA-DEN-01-1-winner`。把 player_id 由 2110 假設改為現有 exact-name leaf 19626（Christian Sigsgaard、ATP），其餘來源事實保留。**19626 僅是重播目標，不是已獨立認證可直接遷移的 target。**

現有 upsert 新增一行，但原行保持 ACTIVE，新行的 supersedes_history_id 為空；沒有替舊行建立退役 observation。原因是 prior 查詢包含新 player_id，而 canonical event key 也包含球員 pair，不能自行找到舊身份 generation。

再以同 source provider、raw_response_id、source reference 的兩個相反視角（24211、24212）重播，先驗證兩行 reciprocal player/opponent 及相反 won：

| 指標 | 結果 |
|---|---|
| 更新前 ACTIVE 行 | 2 |
| 兩個視角各自改正 ID 後 ACTIVE 行 | **4** |
| 原兩行退役 | 否 |
| 原兩行新增 observation receipt | 否 |
| 新兩行 supersedes_history_id | 都為空 |

所以 **「用正確 ID 重入兩次」仍不是修補**。這是現有 ingestion API 面對身份遷移的限制，不代表一般同身份 source 更新都壞，也不證明這次假設 target 已合格。未以這個重播當預測 A/B。

## 3. 下一步實作必須滿足的合約

修補器必須與一般 ingestion 分開，先產生不可變 proposal，預設 dry-run；不能整體 rename／merge 混合群組。

1. **逐來源證明身份。** 固定 provider namespace、external player ID、raw body hash、雙方角色及來源 reference；核實 target 及 alias／DOB 等佐證。名稱相同、當前 mapping 或 merge chain 收斂，都不足以自動批准。未確定來源留置，不猜 target。
2. **完整雙側 closure。** 在單一來源回應內核對 reciprocal rows、來源 winner／loser 及 event identity。ordinal reference 不可跨回應當永久 match ID；缺側、多側、衝突、self-pair、cycle 都停止該 proposal。
3. **先查 collision。** 列出 target 已有 source-local unique key、canonical_event_key、跨來源候選重複及相關 fixtures／aliases／merge pointers；無證據不得去重或整批搬動。四個 frozen 後新增行必須先另取 raw 證據，不混用舊結論。
4. **原子遷移及觀察時鐘。** apply 前重驗每個受影響 row／mapping 的確切 before-image；在同一 transaction 保存舊 payload observation、明確退役兩個舊視角、新建兩個正確 generation 及 supersedes 關係。記錄實際修正 observed_at，不倒填為原本已知；保留舊 immutable prediction／ledger／raw receipts。
5. **可回退及冪等。** proposal 綁資料 hash 和 code SHA，重跑不得再加 generation；concurrent change、來源 hash 變動或 collision 均停止。rollback 亦須檢查 after-image，不覆蓋其他 session 的寫入，且不能刪 append-only observations。
6. **驗證先於部署。** 在小型隔離 DB 驗雙側修補、同名不同人、合法 alias、既有正確副本、未知 tour、ordinal 改動、缺側、並發失效及 rollback；實際 proposal 的全範圍 before/after 核對通過後，才考慮 live apply。後續用相同語料及固定 ruler 做 baseline/candidate 比較，才判斷準確度；不重開 15 個 REJECT_DEV 或更改 holdout。

內置碟約 6.3GiB，未達大型實驗 10GB 門檻。本輪只有串流核對、小型 metadata 及記憶體重播，輸出在已掛載外置碟，沒有 DB 副本或新 fit。後續可先完成隔離修補器與來源證明；大型準確度實驗須待空間足夠。

## 4. 證據與重播限制

根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `owner-repair-readiness-v1/`：執行前 protocol、source.py、628 行 live capture、單側 upsert probe 及 result。固定 frozen DB SHA 與 EXP-26 相同，先驗完整 hash。
- `owner-repair-pair-probe-v2/`：不再打開 live DB，驗 capture hash、全欄差異、固定雙側 before/after 及 observations；含 protocol、source.py、result 及 artifact-manifest。
- `owner-repair-pair-probe-v1/`：保留第一次失敗的 source/protocol；原先錯誤假設所有 current 行在 frozen 都存在，assert 失敗後停止。v2 明列 4 行新增且未審核，沒有縮細 capture 或刪除失敗證據。

原執行使用 repo 根目錄及 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python <script>`；兩份 script 原為 `/private/tmp/tennis-owner-repair-readiness-20261101.py`、`/private/tmp/tennis-owner-repair-pair-probe-20261101.py`，各成功輸出內另存當時 source.py。重播須改為新輸出目錄；v2 使用已保存 capture，不把新 live 狀態當作舊結果。單側／雙側 probe 共用現有 upsert，只證明它的行為，不是獨立身份 oracle 或準確度測試。
