# Tennis 固定 card 的 component 阻擋與場地來源

2026-11-05 Sydney。接線修正已正式發佈為 `703d3f1e73772f3975436cd53b536cdbbf3086fc`，但原合格樣本仍為 0。本記錄只診斷輸入及核實新公開來源，沒有改評分、評估規則、完整 card 合約或重新訓練候選。

## 逐筆核對原有 component 合約

固定 09:00 card 的 57 個觀測，gzip SHA256 `c52e10f46e2d0be6884b07aedf2f3a4178ea24168cdc062d581e4f0e2839a69d`。逐筆以原 snapshot、pricing 及 prediction_created_at 呼叫原 research_evidence._components。只在記憶體讀取，保存程式／彙總／hash，沒有匯出原私有價格或 raw bodies。

12 場在 forecast 時已達 start，另 45 場為賽前。45 場全未通過 component projection，其中 28 場遇 active component unresolved warnings，17 場在已登記 neutral-warning 投影後沒有可採用的有效 component。不是「每場必須十一個 component 全 active」；原合約要求完整十一個名稱及至少一個有效 active，57 場的名稱集合全部吻合。不能將低樣本 H2H 的中性 0.5 算成獨立有效訊號。

賽前 active warning 計數，surface 缺失 27、rank_seed_elo／elo_not_as_of 各 12，彼此重疊；只有 4 場有已知 surface。6 場 Challenger、4 場 Tour、27 場 ITF、8 場 UTR。component projection 本身不是整體 source-clock／raw／settlement qualification，本次沒有產生任何 qualified prediction。

此結果支持先核實場地及實際 as-of Elo。沒有以 warning 計數調權重，沒有改舊 15 個 REJECT_DEV，也沒有把較易讀的個別場次當作完整 canonical card。

程式、結果及 SHA256SUMS 存於外置研究根 `kernel-f02-rules-20261101/live-card-component-blockers-20261105/`。固定 code 為上述 703d3f1e，其 component 合約與原 card 版本相同。

## 公開賽事目錄及官方 PDF

2026-11-05T08:25:02Z 重新讀公開 [Sportsbet tennis 目錄](https://www.sportsbet.com.au/betting/tennis)，只保存 60 個 competition 名稱／ID，HTML 及價格原文不留檔。與原六場賽前 Challenger context 以完整標籤比對，Taipei 4、Costa Do Sauipe 1、Charlottesville 1。之前只有兩個城市 substring leads，今次以公開完整標籤找齊其餘四場；這仍不是來源 player alias 修復。

三份官方 ATP main-draw PDF 於 08:29 UTC 下載、逐頁 render 並目視核對，全部清楚列明當屆日期 2026-11-02 至 2026-11-08。

| 官方事件 | Sportsbet 完整 competition 標籤 | 直接可核實欄位 | PDF SHA256 |
|---|---|---|---|
| [Taipei 2278](https://www.protennislive.com/posting/2026/2278/mds.pdf) | ATP Challenger 100 Taipei | Hard、100 | f46c134c06f64aec08acb463078f2ff96688f0bcf38ed81141c15d06eff52cd5 |
| [Charlottesville 6055](https://www.protennislive.com/posting/2026/6055/mds.pdf) | ATP Challenger 75 Charlottesville | Hard、75 | f5cc1b87b354405166e8d70d24d93a77c88dc9e05b951b89df6bb8a879325f29 |
| [Costa do Sauipe 3031](https://www.protennislive.com/posting/2026/3031/mds.pdf) | ATP Challenger 125 Costa Do Sauipe | Clay、125 | fa25a03d221f21fa63631150645d7e04c3cd491a6c00890ed8059b7ba9539c4d |

Taipei 四場與 Charlottesville 一場，兩位球員完整姓名都可在相應 singles main draw 唯一找到。Costa 一場未能在完整姓名規則下證實雙方 membership，保留 unresolved；PDF 有截短姓名，不用首字母或模糊比對補上。Membership 不能代替具體當日配對與來源 actor ownership 證明。

另讀同三個事件的官方 [Taipei OOP](https://www.protennislive.com/posting/2026/2278/op.pdf)、[Charlottesville OOP](https://www.protennislive.com/posting/2026/6055/op.pdf)、[Costa OOP](https://www.protennislive.com/posting/2026/3031/op.pdf)，均列 Thursday November 05。未將任何 OOP 當成原 forecast 前已接收證據，也沒有自行替 Released 欄位加時區。這些來源均在原預測之後接收，舊預測資格繼續為 0。

## 下一步與邊界

- 三站 PDF 只直接證明 Hard／Clay，沒有確認 indoor／outdoor，不從其他同城賽事或舊年資料推斷。
- 新 curated metadata 要用明示 tour、完整 alias、當屆日期及已保存原文來源；要先處理舉辦地日期與 pipeline Sydney match_date 的時區差，不能直接把美洲 November 8 結束日當成 Sydney November 8 截止。
- 現有 outside_confirmed_metadata_dates 已會在 feature reader 擋過期 persisted curated row，必須保留及測試；沒有證據說現有這項防線失效。
- 用新來源做未來 fixture 的入庫與特徵驗收，再檢查 as-of Elo。維持原 source clock、完整 card、row-flow、eligible IDs 與 forward 要求。若另討論 capture／qualification 結構，要獨立 protocol 審查。

本次 metadata_applied=0、old_predictions_requalified=0，沒有命中率、LL／Brier 或 ROI 改善證據。官方 PDF、PNG、public competition metadata、verifier、source URL／hash 及彙總，完整保存並核實於外置研究根 `kernel-f02-rules-20261101/challenger-official-metadata-20261105/`。重新執行 archived verify.py 已逐欄重現結果。
