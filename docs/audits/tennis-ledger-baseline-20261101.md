# Tennis ledger 全量基線及分類更正（2026-11-01）

固定原始完整快照 SHA-256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`。依事前協議核對 13 表全部欄位及 ID 順序，保存 matches 9,974、players 25,564、一般 odds 17,283、preclose odds 552、market rows 250,982、preclose market rows 29,840、captures 714、stored closes 111,464、CLV tracker 3,828、prop tracker 27,411、prop price log 8,722、bet ledger 0，以及所引用的 raw response 9,432。原始來源無 payload archive 表，此事實保持；未知時鐘不因複製變成 PIT 合格。

證據：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/ledger-source-guard-v1/`。包含 pre-extraction.json、input-proof.json、完整基線 source、protocol、freeze 程式、native-tracker-baseline 及 clv-category-reconciliation。

## Native 基線

全部 3,828 tracker 中，866 行 market_key=match_winner，另列；2,962 行非 match-winner 全量逐行重播 `_tracker_close`。來源追蹤只在原本 SELECT odds 增加 id/preclose 投影，WHERE／ORDER 保持原樣；每行另用未修改的 connection 原生呼叫，返回值及原因完全相同。

2,196 行選中直接 Sportsbet event ID 相符來源，766 行沒有 selected snapshot；本固定快照非勝負盤分支沒有選到錯 event 的行。matched ID 不證明球員身份／PIT、766 行亦不能當已驗證。此基線未使用 outcomes／ROI，尚非候選八 arm 比較。

## 修正先前分類錯誤

之前把 `MARKET_LEG` recommendation_type 當成非 match-winner market 分類，文字有誤。保存的原始四行顯示：

| tracker ID | 原始 market_key | 舊 native close | 現候選 native close |
|---|---|---:|---:|
| 44829 | match_winner | 2.1 | None |
| 45869 | match_winner | 1.363 | None |
| 45870 | match_winner | 2.1 | None |
| 46959 | winner_related | 2.4 | 2.4 |

三個 None 原因均為 no_pre_start_match_winner_close，來自已有 source guard，未改寫歷史 tracker 或保存 CLV。第四行沒有被扣起。逐欄確認這四行與舊證據一致，沒有用較新紀錄冒充當年 lineage。

含錯誤分類的發佈候選 6e14f89507f7 已停止正式 gate（exit -15，未 stage／未發佈），更正後另行保存。之前 320442e2 全套測試通過仍有效於該 SHA，但不能當作最終更正版已部署。

## 後續

close writer 可再次把已知錯來源 materialize，仍須驗證。非 match-winner／prop price log 要完成協議的全量比較及負例測試，不能基於這次零暴露就聲稱所有來源安全；也不能再以三個勝負盤 tracker 作為非勝負盤污染證據。模型準確率及盈利仍未獲改善證據。

`input-proof.json` SHA-256：`19a8f166ad3d09a0094cc6591f4048f37af9c6561e7ae9e7fb1749567867488c`。

`native-tracker-baseline/result.json` SHA-256：`d9453aef84b7527692f00438829d9abe28d7c5f4ac2dff26ecea07ee86aebe95`。

`clv-category-reconciliation/result.json` SHA-256：`90a264a3a0e7e4563d4950879241eeda32816cd160380dc3edd0b4e8c590608d`。
