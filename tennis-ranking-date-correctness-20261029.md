# Tennis 排名日期正確性修正

目標：阻止要求分析日冒充來源排名日期，並保住可核對嘅舊資料及其他有效來源；準確率增益須另有樣本外證據。

- [x] 凍結一次完整 native DB；記 baseline `501867847af0`、一致 backup、完整 table counts／SHA，之後兩邊只讀同一來源。
- [x] 核對 UTS 真正日期端點與日期參數；新 ATP／WTA parsers 拒絕無日期／未來日期，保留日期依據。
- [x] 入庫驗實際 source date；日期失敗保存原樣來源及明確錯誤，safe cache 不得返回已知錯標 UTS。
- [x] 共用排名讀取守則：current_rank 及 opponent rank buckets 均驗 calendar／UTS 日期；有效替代來源繼續可用，mutable rank／同來源 seed 不能繞過攔截；刷新排名保留真正 Elo。
- [x] current_rank provenance 指向所選排名 raw／日期；現有七日 stale ranking 警告亦檢查實際 current_rank，唔改門檻。
- [x] 固定語料逐項量 normalization／UTS guard／組合對排名及對手 bucket 輸入的影響，保存全部 row-flow 與缺值；不以重建輸入冒充原預測或 PIT accuracy。
- [x] 完整官方 PDF native 入庫重現、真 SQLite 正反例、全部 Tennis tests、quick 及 immutable full gate；exact-scope 保存／啟用後核對實際 imports、排程及 shadow registry。正式完整閘 Tennis 973 passed；合併／啟用 SHA `4fe5e17064afb293fa7db5655b7c57aafcf18113`；六個身份衝突依然留置、來源報 partial。

既有原文、排名歷史、預測及 settlement 不覆寫；新來源捕獲唔提升舊資料嘅可知時間。15 個 REJECT_DEV 同 frozen ruler 保持不變。
