# EXP-20261104-03：缺 Elo 目標的 tour 接線診斷

2026-11-04 Sydney（實際capture為2026-11-03T15:48–15:51 UTC）；固定原39人，不按賽果選樣。只讀現在的primary DB，沒有資料修正／模型改動／資格回填。

players.tour 39人均 UNKNOWN；92筆現有 matches 記錄涵蓋這批ID。21位有唯一 ATP 或 WTA stored tour、18位無已知 stored tour；未見同一人同時兩種已知 tour。這是 current lineage 診斷，並非原預測當時已知，也不能把共用playerID視為獨立身份證據。

交叉既有全32 public profile／全39 target盤點：10位有唯一來源全名token吻合，且來源sex與現時唯一stored match tour一致；13位有來源全名吻合但沒有已知stored tour；16位沒有來源全名吻合。10位仍只係候選線索，原source-spec判準用原target tour，不能將這次推導代入舊判準，不能報新qualified ownership或forward。

兩個資料流值得分開核實：`entity_mapping.get_or_create_player` 保留source-owned provider mapping，但既有player更新未必補tour；`sportsbet_competition_meta` 對未確認標題只認特定prefix，其他會UNKNOWN。這只是靜態程式路徑；未逐筆證明39人由哪條路徑造成，不能認定root cause或直接修。

下一步先在記憶體核對同一批原target的provider namespace、原文是否明示tour、實際name與mapping beforeimage及取得時間。只輸出IDs/hash/counts/flags，不輸出私人fixture／價格payload。來源不明就維持UNKNOWN；若取得後來獨立證據，只可建立當時起可用的新binding，不能倒填舊決策。全39人、雙側來源、原時間窗及15 REJECT維持。

SQLite使用mode=ro、query_only、100ms busy timeout及5秒progress deadline；實測約0.062秒。研究輸出（程式、protocol、result、notes）只含aggregate counts、公眾playerID及研究程式，不含私人賠率／投注／fixture資料。現時只為尋找資料bug，未量準確度或ROI。

補充 current receipt 檢查：39人source_provider均Sportsbet、39份reference均指向存在的receipt（只有2份unique body）。124,820 bytes在記憶體檢視，38位exact完整名字在normalized list出現，但均沒有已知tour；1位receipt非list而未判定。不是原book HTML，也不能把normalized缺值推斷成網站沒有性別資料。原body／fixture不輸出，只有公開playerID、hash、counts及flags；未證明39人root cause或過往availability。

## 靜態路徑的界線

`entity_mapping.get_or_create_player`的provider已存在分支會寫入傳入tour，其他canonical繼承分支另有更新欄位。不能只因目前UNKNOWN便認定程式漏更新，也不能直接COALESCE舊stored tour。這次只指出核對路徑，尚未逐筆證明root cause。

## 封存與重現

`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/target-tour-lineage-v1-20261104/`，13檔／49346 bytes，manifest SHA256 `5ec869e99c224353be5f8c0345d41eabaeaa7518cb80bca51b76b735f3deefc6`。本次capture `2026-11-03T23:49:41.619797+00:00` 重新逐檔核hash仍一致，亦見[交付補證](../audits/tennis-source-classification-release-20261104.md)的captured_at。

所有run／crosscheck／source_flags／receipt_tour程式、執行前protocol、結果及notes皆保留。重跑只可寫全新輸出目錄並記下當時capture／hash；current DB會隨排程改變，不能覆寫本包或當成原預測前證據。原39人／40sides、整批card資格、時間切分、十五個REJECT_DEV及tennis-v1均不變。尚未證實分析準確度或ROI提升。
