# Tennis Wong Choi 模型審計／修正收尾 — 2026-10-26

**已修正程式及資料品質問題；未證明今輪令預測更準或更賺錢。**
本報告係 [原審計](tennis-model-review-20261026.md) 之後獲授權繼續落實嘅結果，保留原審計作歷史記錄。

## 已交付

| Release | 改動 | 狀態 |
|---|---|---|
| `007fbc628ec4ca157da68f1d9a439291901d68bf` | winner conflict 結算／證據保護、BO5 prop guard、validation fail-closed、離線賽前 corpus readers | 已合併／啟用 |
| `02b19954bf17c3dbdf18f3a94c98ac5e4c6c746e` | 跨盤發球輪轉，按上一盤 games 奇偶延續 | 已合併／啟用 |
| `6378779edfc1900dfc645fe207f1ec79cc67f201` | backtest 日期窗／settled ROI、metadata 去重、WTA totals 品質／cache 重驗及失敗 refresh 資料保留 | 已合併／啟用；生產唯讀 smoke 通過 |

證據：[第一批 correctness](tennis-correctness-fixes-20261026.md)、
[發球次序及 A/B](../experiments/EXP-20261026-05-tennis-simulator-service-order.md)、
[回測／WTA collector](tennis-backtest-window-fix-20261026.md)。

完整閘門最初一項共用 fixture 因 1 秒 cold-start timeout 失敗；只增加測試啟動時間，
保留全部 cursor／preemption 斷言，生產邏輯未改；修正後共用 1,751 項通過。
`b3e40617415a208bceff1a3cab591bfe4783b8c7` 完整 16 suites 全綠後，main 有無重疊 NBA 改動；
自動 replay 成上表 `6378779`，對新 SHA **再跑完整 16 suites** 全綠及 quick 重驗先啟用。

## 模型實驗判決

| 固定配對實驗 | 樣本 | Baseline Brier ↓ | Candidate Brier ↓ | 判決 |
|---|---|---:|---:|---|
| 新 WTA 官方 serve history 直接接線 | 114 matches／300 props | 0.264495 | 0.276047 | REJECT 接線；市場 0.246078 |
| 修正 simulator 跨盤發球 | 665 matches／1,230 props | 0.251512 | 0.251835 | 規則 correctness 修正；Δ CI 跨零，唔聲稱準確率提升 |

兩行係各自同窗比較，**唔可以跨行比較數字去推斷改善**。WTA 90 日硬截同只替換 hold-rate
亦無證明 props 改善，無接入正式定價。新 WTA source 只保留研究用途。

官方 backfill：63 tournaments、3,390 matches，新增 3,045 場有 stats；16 場無 stats，
329 場已存在，fetch errors 0。6,780 個 player-sides，2,950 份符合本次日期／品質／身份條件；
其餘包括時間證據不足、退賽、比率／exposure 不合理，唔一概當「有值就有效」。
完整 [WTA 失敗及分層結果](../experiments/EXP-20261026-04-tennis-wta-fresh-history.md)。

## 驗證及目前限制

- 最終 immutable full gate：16/16 suites；Tennis 761 tests passed；quick 全綠。
- Production scheduler code HEAD：`6378779edfc1900dfc645fe207f1ec79cc67f201`；activation 狀態已核對。
- Native source health：model serve latest `2026-05-18`，feed latest `2026-10-25`；
  collector 品質修正唔等於模型已轉用新 source。
- 目前 7 場 winner conflict 被隔離；guard 並無替人選一個來源作真相。
  同 winner 但 score 有分歧、潛在重複 identities／history，仍需獨立逐事件核實；無盲目刪資料或改舊注單。
- 歷史重播資料 exact availability 未全部證明，保留 FLAG；無 untouched holdout／CLV 優勢聲稱。
  今次不 promotion 新投注 family，不調權重、edge 或注碼門檻。

## 新增來源身份風險（未改寫歷史）

收尾唯讀檢查發現 match `21718`（composite event `185138`）目前係 2026-10-27
Hijikata／Fritz（player IDs 35／1），但 `tennismylife` result winner ID 11，唔屬於兩位參賽者。
Result created `2026-10-26T07:02:58Z`，fixture updated `07:22:17Z`；
`ingest_matches`／`ingest_odds` upsert 可以喺同 provider key 下更新參賽者。
呢個時間序及 code path 係 event identity 被替換嘅線索，**未有完整原始版本鏈，唔當根因已證實**。

現有 guard 將呢類 non-participant winner 同來源勝方衝突一齊隔離，唔結算／唔納入決策證據。
但 guard 唔會還原舊 fixture、forecast 或 odds 嘅原始身份；後續優先工作應係逐 event 核實
provider-key 重用／pair change，設計 immutable pairing version，再做獨立 migration/replay。
唔應為咗清警告而將 winner 改成現有其中一位。呢項仍屬高優先資料風險，唔聲稱全數解決。

## 下一輪可檢驗假設

以下係研究次序，唔係已證明有效嘅改善：

1. 先核實 provider-key／pairing 歷史，修正 source identity chain；唔用 disputed 結果擇參。
2. 新 source 繼續獨立保存 capture time、實際比賽時間、quality status，累積可證明 PIT 嘅新資料；
   先驗證每個市場所需嘅統計 exposure，唔以 freshness 取代品質。
3. 每個 family 分開測試簡單 candidate，dev 時間 folds 揀；固定既有 holdout 做最後一次確認。
   A1／A2／D0 已失敗，無新假設或新資料前唔反覆調窗救結果。
4. 同 corpus 比市場 Brier／log loss、校準及可取得報價；盈利／CLV 同時未過就維持 research-only。

## 重現與保存

- 研究 code：non-main branch `codex-tennis-refine-20261026`，
  WTA protocol／candidate `5900435a531bbb34b35e85fb98d66b1ede84e2de`，
  paired simulator driver `2a873f64a7150209a6346e7959d51f4d98338c72`；未部署 WTA 候選。
- 唯一 research DB：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/tennis_research.db`；
  SHA256 `a45fd7062caa31ac4afa9a4e6d5f8901044d1e3d7eb5529f883b1cc872c9cac0`。
- 完整 per-contract／bootstrap 結果同 kernel snapshot 留喺同一個外置 scratch；
  命令、code checksum、固定 seed／split 見兩份 experiment。唔搬 raw dump 入 git。
- 原 live forecasts、已保存注單／賽果無由本次審計直接重寫。所有 code／記錄已保存，工作 worktrees 交付後清理。
