# Tennis Wong Choi 修復及審計收尾（2026-10-27）

本輪已重現嘅主要程式問題已修正及部署；**未證明預測更準或盈利增加**。未核實嘅歷史身份仍保留待查，唔當作已清晒。

## 已交付程式

- 身份／賽果修正：`41730c2f559c2a20d574eec9d37ee5cb4931d502`。
- 歷史／市場／證據修正：`063c8799e71098775c8f8284ca6dd1a7fee8cbdc`。
- 兩份 release 都有正式 `merged` 及 `activation_succeeded` 紀錄。
- 最終版本完整 **16/16 suites 通過；Tennis 858 tests passed**。保留原有閘門，無放寬 timeout、權重、注碼或 promotion 規則。

| 問題 | 而家嘅處理 |
|---|---|
| 同一 provider key 換對手／換賽事，舊預測同新資料混埋 | 賽事版本分開保存；確認錯配會隔離，唔搬舊預測去新賽事 |
| 來源勝方、分數、退賽資訊矛盾 | 保持待確認；唔自動揀一邊結算或當決策證據 |
| 後來補齊資料，令舊預測品質分改變 | 保存真正定價時嘅品質、輸入／profile 身份及報價；舊紀錄唔會補造「當時已知」證據 |
| 報價跨批次／跨莊家混合，或空 listing 留住舊價 | 以同一 capture 判斷當前可用價；空 listing 有紀錄，歷史價保留 |
| 歷史重播讀到同賽事後來先匯入嘅統計 | 共用現有時間閘及實際開賽時間；自身對賽、無效比率／計數唔入有效統計 |
| 來源重新編號，重複計場；沿用編號，統計貼錯對手 | 穩定事件身份及版本紀錄；修訂唔覆寫舊代，同一 response 自相矛盾會報錯 |
| 跨來源只因相同球員喺 ±10 日內對賽就去重 | 要有共同年份賽事 ID、圈次、賽制；保留真正再賽，矛盾勝方會報錯 |
| F／SF／QF 被轉成 UNKNOWN | 正規化可重複使用，已用重現測試及固定樣本量度影響 |
| 錯 player-total 合約、球員名稱模糊配對 | 保存原始市場合約；唔確認到 subject 或舊合約就唔當正式證據 |
| 特徵讀取暗中寫入、錯誤被吞咗仍報成功 | 唯讀組裝路徑；定價／驗證失敗會明確記錄並影響 readiness |
| 說明同真正策略條件唔一致 | 由 registry、常數及可執行條件生成策略參考，包含來源 fingerprint |

之前已部署嘅 BO5 支援閘、模擬器發球輪轉、回測日期窗及 settled ROI 修正，見 [上一輪收尾](tennis-model-refinement-closeout-20261026.md)。

## 正式資料核對

兩份外置一致性 SQLite 備份均通過 `quick_check`：身份修復前一份、歷史修復前另一份。

- Fixture `21718` 已列為 `DISPUTED`，未猜測還原舊參賽者或賽果。
- 正式歷史資料原有 **419,843 筆全部保留**；88 筆來源錯配列為 `DISPUTED`，另有 88 條 append-only 修復觀察紀錄。
- 修復後重新跑來源核對，未隔離集合已冇再出現本次已證實嘅 header／原始來源錯配；其他未知證據仍然保留。
- 即時資料與凍結樣本嘅 88 個 row IDs／錯配原因相同，但 raw capture IDs 已更新；實際採用重新核實嘅完整即時 row state，冇照搬凍結計劃。
- 舊 prop pricing receipts 仍為 0：今次冇倒填舊定價證據。新 schema、報價 capture 表及生成策略參考已核對。

備份位置及完整實際修復個案見 `tennis-live-history-repair-20261027.json`；身份修復證據另見 `tennis-live-identity-repair-20261027.json`。

原有 match、prediction、prop、CLV、result、odds、feature 同 history 筆數全部保留。冇重寫舊預測或已保存結算。觀察紀錄用實際時間建立，唔倒填成舊時已知。

## 審計結果同限制

完整凍結歷史共 **419,769 筆**。診斷辨識 177 筆額外、身份及統計一致嘅觀察；13,390 筆需待核實，包括 3,425 筆自我對賽、470 筆來源事實衝突標記、其餘未能可靠對應事件身份。呢個係保守診斷，**唔代表全部待查記錄都係錯，亦唔證明其餘全部正確**。跨來源 canonical reader 保持診斷用途，冇直接套落評分或一刀切刪資料。

固定 12 場 component check：圈次修正影響 6 場勝率，最大絕對變化 0.00563007。完整 Elo 輸入重播分開測試 self-pair／來源隔離：合併少讀 65 條有問題嘅勝方紀錄，影響傳播至 9,288 個最終 overall ratings，最大 17.569 分。呢啲係修復影響，**唔係準確率／ROI 證據**；測試冇覆蓋正式 Elo archive。

凍結 prop 樣本嘅 raw paper ROI 仍然係 **−14.58%（1,003 筆已結算）**。缺少定價時證據嘅舊紀錄改列 UNKNOWN，該次正式 ROI／reliability 可用樣本為 0；原有輸贏全數保留。唔會以呢次樣本分類改變聲稱盈利改善。

## 模型改善下一步

1. 用已部署管線持續保存可追溯嘅賽前資料、實際報價及品質；未核實嘅歷史資料唔用嚟證明新模型有效。
2. 每次只登記清楚嘅候選假設；用固定 dev 時間 folds、獨立 ablation，同 corpus 比市場 Brier／log loss、校準、可取得報價、CLV 及淨 ROI，最後先開固定 holdout。
3. 新 WTA 官方歷史直接接線已測試並否決，未部署。Elo shadow 仍須過原有前向樣本及其他門檻，唔會為咗升級而改 600-floor、時間窗或分組。
4. 有合資格 out-of-sample 證據之前，維持原有權重、注碼及 family promotion 規則。

詳細證據：[市場／定價](tennis-pricing-evidence-correctness-20261026.md)、[歷史修正](tennis-history-correctness-20261027.md)、[Elo 輸入影響](tennis-elo-integrity-impact-20261027.json)、[完整歷史診斷](tennis-canonical-full-audit-20261027.json)、[正式資料修復核對](tennis-live-history-repair-20261027.json)。
