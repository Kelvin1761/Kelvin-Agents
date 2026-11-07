# EXP-20261107-02 — Sol vs Wong Choi，Flemington 2026-11-07

## 揭盲前固定

用戶指定今日全日 9 場，要求 Sol 獨立分析、保留分析紀錄，之後比較 Wong Choi 與賽果，找盲點。
本研究保存可審核的理由摘要、證據、假設、取捨與信心，不保存逐字私有內部思考過程。

- Baseline source commit：`6525f23eb`。同日真實賽前 snapshot 的 Wong Choi 原排序，不以今日重評取代。
- Sol：`gpt-6.1-sol`，fresh context，不承接 parent 對話。單次全日分析，輸出一經 hash 鎖定不可改選。
- Sol 只讀 `inputs/R1.md` 至 `inputs/R9.md` 及這份 protocol，不讀原始資料目錄、manifest recommendations、Logic、Facts、CSV、reflector、結果或網頁。
- 輸入：最後一份全日第一場之前的不可變 snapshot；18 個 card/guide 檔逐一校對 manifest hash。全部往績日期 < 2026-11-07。
- 保留歷史名次、輸距、時間、獎金、騎練、負磅、檔、裝備、試閘、原始備註；移除目前與歷史賠率、ROI、Fav、裝飾連結。沒有以結果選擇往績。
- 尚未看今日賽果。parent 查看 snapshot manifest 時意外接觸 Wong Choi 推薦，故選擇由無 parent history 的 Sol 完成獨立排序，不能稱 parent 也對 WC 完全盲。
- 這是 retrospective input-blind review，不是當時發出的預測。無法排除 LLM 既有知識或馬名辨認；9 場單日不作統計優越性結論、不調模型參數。

## Sol 必交

每場所有 active runner 各有 evidence-backed assessment、支持點、反證／風險、來源行號。
每場完整排序、固定 top4 / top2、信心（low/medium/high）、步速情境、主要假設、可能改變排序的缺失資訊、資料異常。允許缺資料時低信心，仍交一個固定排序供比較。
禁止憑空補 Stewards、時間、負磅、trial margin；0.00 或缺資料不得當成真實齊頭或未受阻。
不要模仿 Wong Choi 的權重，不知道其排名就明說；不可用或查今日結果，不准結果後修改初選。

## 揭盲比較

所有九場 Sol JSON/MD 完成、欄位與 runner IDs 驗證及 SHA256 lock 後，才讀今日結果與 snapshot WC CSV/Logic。
晚退馬對兩方相同處理：先完整保留原選擇，另在實際出賽馬集合上刪除 non-starters 後按原順序比較，標示 late scratches。
逐場報兩方 top4、實際前三、winner rank、top4 捕捉數、canonical Gold / Good positional / Pass / champion，並報 agreement。
Gold=實際前三全在 top4；Good=首兩揀都前三；Pass=首三揀至少兩匹前三；champion=首選頭馬。
不報 ROI：本輪沒有預先定義投注法或可用的賽前價格。

逐個 divergence 分：來源未提供／已在輸入但模型未表示／已有 feature 但被其他分數抵消／LLM 判錯／偶然結果／未能驗證。
任何「模型盲點」須指出具體證據及現役 code 路徑；勝出一場不是因果證據，LLM 亦要做失手檢討。
最後列可重現的後續假設，禁止用這九場擇參或直接加分。沒有模型 promotion，沒有新 forward test 自動開啟。
