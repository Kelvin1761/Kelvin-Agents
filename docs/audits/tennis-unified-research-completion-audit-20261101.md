# 統一 Tennis 研究計劃逐項驗收（2026-11-01）

**未完成整體目標，未證實準確度改善。** 本文按原計劃要求核對完成證據，沒有改判決規則。候選被拒絕、輸入暫停及工程正確性各自記錄，不能當成已提升模型。

本輪重新驗證五組 artifact manifests 全部 32 個檔案 SHA：feature development、head development、market development、MCP、Slam v4。沒有重新訓練、載入外來 pickle、使用 holdout 或重算實驗判決。證據目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/plan-completion-audit-20261101/`，含完整已驗證路徑/hash 清單、原生結果摘錄及 audit 程式。

## 原計劃九項驗收

| 項目 | 現有直接證據 | 判斷／未完成部分 |
|---|---|---|
| 1 baseline/runtime/ruler | run_manifest、preflight_lock；來源04469fba、排名6b01f07f已部署；研究resolver37df3367完整gate／runtime已核對 | 研究基準有保存；工程／研究工具發佈與 model promotion 分開，不能將現在程式冒充每份舊預測版本 |
| 2 完整語料及分流 | warehouse 全表凍結／row-flow；多 book 11,725 matches／23,393 book rows；後續來源及身份審計 | SEEN_DEV，歷史來源發布時鐘及個別身份仍未證實；不是全量 PIT-qualified corpus |
| 3 完整 baseline／簡單控制 | saved prediction/component replay；head matched-control independent replay PASS | 現有 artifacts 可重現計算；歷史 15,896 prediction 缺所檢查的精確 feature/market 連結，不能稱完整 B_live 歷史重建 |
| 4 MCP/PBP 及 kernel | MCP／49站Slam採v4；新kernel255個DP/MC比較；2011–24 resolver110支援／2取消及1980接線比較 | 原固定窗training eligibility仍0；Sackmann/TML及WTA補充raw點數盤點不能代替歷史PIT資格；現役pricing仍未接研究kernel |
| 5 有限單項實驗 | 五段 dev、13,274 matches，10 個 feature 候選均 REJECT_DEV；去水市場另三個 REJECT_DEV | 有全部失敗結果；workload 因 input qualification 停止，不能補假 minutes/hours 或改窗救回 |
| 6 同特徵 heads／市場增量 | HGB vs matched logistic REJECT_DEV；offset 對市場 REJECT_DEV、對 tennis-only ADVANCE_DEV_ONLY | offset 整體仍 REJECT_DEV。沒有同時通過必要控制的候選，不啟動救援組合或重調已見 holdout |
| 7 joint props | F02 合格 serve/exposure 及市場/settlement 合約是依賴 | 未開始／依賴未齊。不能以 winner 一個 marginal 推論 joint props 已識別或合格 |
| 8 新 forward | 最新 native feature provenance 129 records、127 完整 bundle，qualified predictions 0 | 未開始合格新候選。33 個單筆 diagnostic projector 通過，不等於原整批 canonical card 合格或 untouched 樣本 |
| 9 最後 promotion 覆核 | 15 個 candidate 決定已逐項再驗；source fixes 的獨立 gate／manifest | 無合格 model candidate，沒有 accuracy promotion；工程 source fixes 不能代替比較 LL/Brier／新 forward |

## C01–C17 當前去向

外部項目筆記的集中清單保留的是比較當時狀態，下面是對照原始成果的最新狀態。

| ID | 批次 | 已核對去向 |
|---|---|---|
| C01 | F09 | offset 整體 REJECT_DEV；不能只引用勝 tennis-only 的一項對照 |
| C02 | F03 | power／Shin／inner-selected devig 三個候選 REJECT_DEV |
| C03 | F04 | surface_dynamic REJECT_DEV；既有 frozen shadow 不因本批而換模型 |
| C04 | F00 | 已盤點／部分來源修正交付；EXP-26全量owner檢查另找2153原LINKED標籤衝突，reader probe可讀入衝突記錄。完整identity/clock/lineage未齊，未repair或當作實際bet污染證據 |
| C05 | 去重 | 保留舊重複／失敗設計排除，沒有重開救援 arm |
| C06 | F05 | R/E/S/RE/RS/ES/RES 七個候選全部 REJECT_DEV |
| C07 | F01 | MCP 品質／來源盤點完成；原固定窗 publication clock 未證實、training eligible 0，不自動接 feature |
| C08 | F02 | 舊22 case只驗同一hold-ratio近似；新明示規則kernel固定255個DP/MC比較通過（EXP-22）；2011–24 resolver有110支援／2取消拒絕、1980接線比較通過（EXP-23）。10513條舊Slam只驗metadata規則路由，未接現役，point skill／fixture合約及正式整合仍未齊 |
| C09 | F10 | 暫停，沒有合格 serve/exposure 候選及完整 joint-market 合約 |
| C10 | F00/F03/F09 | 多 book 歷史訓練／開發 ROI 研究已做；不挑最有利 book、不當 Sportsbet 可執行收益 |
| C11 | F09 | HGB 對固定同特徵 logistic REJECT_DEV |
| C12 | F06 | strength REJECT_DEV |
| C13 | F09 | offset 條件對照完成；對市場不過，不以係數或單項勝出升級 |
| C14 | F07 | STOP_INPUT_QUALIFICATION_C14；合格 rest control、minutes14d、sets/hours 均 0；缺實際完成時間、近期時間窗及發布時計 |
| C15 | F08 | h2h_residual 對必要控制未全過，REJECT_DEV |
| C16 | F01 | 兩種 PBP schema、同源去重及 Slam v4 品質已盤點；原固定窗 publication clock 未證實、training eligible 0 |
| C17 | F00–F09 | 五段時間／match-group、artifact hashes／independent replays 有保存；SEEN_DEV，不是新的 untouched 或完整 ROI lineage |

十五個 REJECT_DEV = 10 feature arms + HGB + 三個去水 arms + offset。不是十五個比較統統負：offset_vs_tennis 是 ADVANCE_DEV_ONLY，但 offset_vs_market 不過，整體不得升級。也不是把未能跑的 workload 或 joint props 算進十五個已跑候選。

## 下一個可驗證步驟

1. 排名警告歸屬正式gate已通過，6b01f07f已部署；26,272 玩家選取值/ID/date不變及259保留輸入配對定價／decision/stake不變。其source receipt/date正確性不等於所有player identity或完整預測可用性已認證。
2. F02 kernel255個DP/MC比較及resolver110支援／2取消、1980接線比較已過，研究工具37df3367已同步，pricing仍用原kernel。EXP-24/25證明原始point denominators並非完全缺失：WTA302核實sides、public history145539通過raw連結；仍缺跨source去重、精確可用性與完整forecast-time capture，不能直接改訓練資格或接正式模型。內置free低於10GB，暫停新大型實驗。
3. 在保持 frozen ruler 下繼續改善有直接原始證據的輸入／捕捉缺口。不得用改樣本窗、忽略 warning、選出已看結果的33行或移除低質 forecast 來製造 forward。
   EXP-26已將原3729個ID旗標分開：live2849結構收斂但部分UNKNOWN tour、880未解釋（856 ACTIVE）；全量點數可連結不保證owner正確。下一步先核對provider-ID及alias來源，提出可rollback的source-owned修補；不能盲目跟隨當前mapping或直接merge／rename。大型A/B仍等free≥10GB，未量準確度。
   [EXP-27](../experiments/EXP-20261101-27-tennis-source-owner-repair-readiness.md)另固定capture兩組current cluster共628行；624有frozen對照（192僅opponent_elo變動）、4新增未審。雙側記憶體重播證明普通upsert留下2→4 ACTIVE，故先實作獨立、可rollback的雙側generation遷移及collision／source-ID資格檢查，不能直接重入live資料。
4. 所有允許單項已被拒絕或依賴不足時，誠實保留拒絕／不確定；要達成實際準確率改善，仍需可重現、有來源資格及獨立比較證據，本文不將「研究已有結果」改寫為「模型已改善」。

逐項核對 `result.json` SHA-256：`09c183cd969bcd155f98e7a7f306f8bd44201629e3dfef4daf3e04bf270d07da`。

亦直接核對現役 `props/match_simulator.py`：simulate_match 只收 hold_a/hold_b、best_of、trials、seed、dispersion；6–6 使用 hold_a/(hold_a+hold_b) 選 tie-break winner，無 tournament/year 或 point-level tie-break 參數。現役檔案 SHA-256：`f2527c25c83be89c56ba0640a544345462fb8985a84dc0ad148a50940ee17e21`。
