# Tennis 凍結 observation 資格及阻擋原因（2026-11-01）

## 現役及核對範圍

來源讀取器修正 `04469fba1627391d76a27e7f26b30a9f31dc22a8` 已正式 full gate 通過（817.1s）、合併及 Tennis activation 成功；runtime `/Users/imac/wongchoi-scheduler` HEAD 逐一核對相同。這不是模型準確率改善或投注 family promotion。完整 release manifest：`/Users/imac/WongChoiData/WongChoiControl/releases/wc-release%3A04469fba1627%3A2026-11-01T013715.460604_0000.json`；activation event 在同 release ID 的 `release-events/`。

使用未修改的 `inspect_tennis_feature_provenance` 及其 native verifier，as-of `2026-11-01T01:34:34.589926+00:00`，遍歷全部 canonical Tennis prediction records，不按結果或日期挑選。證據目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/frozen-bundle-audit-20261101/`。

129 個 record：127 個 bundle 完整性通過、2 個未通過。127 個全缺合格 feature artifact，verified prediction 仍為 0。完整性通過不代表輸入或時鐘已合格；不由 DB 相近時間的 snapshot 補造。

## 原始診斷逐筆 probe

全部 129 個 record 均有去向：119 個無 diagnostic、8 個保存 diagnostic、2 個 bundle 未驗證。8 個中包含兩份空 observation 診斷；原始 259 observations 全數逐筆處理。原始 compressed diagnostics、status、manifest 逐一保存，解壓受 128MiB 上限約束。第一次程式在未驗證 record 的空 snapshot_root 出錯，完整 failure 保存在 `diagnostic-probe/`；修正後的完整盤點在 `diagnostic-probe-v2/`。

使用原本 capture cutoff、完整原樣 snapshot/pricing/raw rows，對每一 observation 單獨呼叫現有 `build_prediction_artifacts`：

| 單筆 probe 結果 | 數量 |
|---|---:|
| native projector 接受 | 33 |
| active component 有 unresolved warning，首先拒絕 | 156 |
| incomplete component set，首先拒絕 | 57 |
| player_a.current_rank 未驗證，首先拒絕 | 13 |

這是診斷 probe，不是合格 canonical evidence。原本整批 card 仍不符合合約，33 行不能當正式 forward 樣本；舊 observations 已被查看，亦不能事後變成 untouched。沒有修改 canonical bundle、資格規則、完整 ID 集合要求、holdout 或 frozen tennis-v1。

錯誤列示是每行遇到的第一個 native failure，不是全部根因。另盤點原樣 active component warnings：surface_elo_edge/missing_surface 出現 150 次；surface 和 overall Elo 的 elo_not_as_of、rank_seed_elo 各 47 次，可能互相重疊。H2H 的低樣本 neutral warning亦可存在，但不能把它一概當作 native 拒絕原因。缺場地的 context 多見 ITF／UTR；只要單項 warning 消失，不能保證其餘輸入已合格。

## 對下一步的影響

原始 feature/input 保存已能解釋部分證據缺口，不能直接推論模型表現或替候選放行。需分開處理：

1. 核對 upcoming fixture 的實際 tour／賽事／場地來源；只有當屆、來源可追溯且決策前取得的 metadata 才可供新預測用。不能用城市常識、往年場地或賽後資料補原始快照。
2. 有 rank-seed／非 as-of Elo 的紀錄，先核對歷史和 canonical identity，不能將 seed 當有完整比賽來源的 rating；也不能單靠移除 warning 字串提高資格。
3. 排名來源日期未知或 fallback 未驗證，保留未驗證；不能以今天取得的榜單回填成過去已知。
4. 全量診斷支持另行預先登記輸入修正／消融，沒有證明移除 surface Elo、改權重或更換 head 有益。原十五個 REJECT_DEV 判決不變。
5. 若未來要調整整批與逐筆的 evidence contract，屬獨立治理／判決規則改動，必須先單獨論證；本輪不藉此追認 33 行或改動任何 ruler。

其他現役四線 run health、Dashboard/D1 及 storage freshness 不由本輪 provenance report 重新認證；正式 activation 只宣告已驗證的 Tennis code alignment。

`feature-provenance-report.json` SHA-256：`2c9f3bab808fdc46b52117db6d76b79e8a63dc22732f55fb7e1c8852b0d999b3`。

`diagnostic-probe-v2/protocol.json` SHA-256：`8ec24cc57956cca7e1b33c6cd99163dcecccee6f021b54dab6d3d214a3dde0a3`。

`diagnostic-probe-v2/result.json` SHA-256：`fa592c35ab0bf93236164bd09b547586a7e99d0bdea23db6d78b0c30294d99c3`。

`diagnostic-probe-v2/all-observation-probes.jsonl` SHA-256：`0f178e1c9036ea00f7caef98aa056217c1b75584afcfb2b3afe382a1d81140e1`。
