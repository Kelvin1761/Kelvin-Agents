# EXP-20261015-07 — 用戶要求先啟用逐駒全程情境速度

用戶2026-10-15明確要求：`implement first and update dashboard? we do more experiments later`。
今次交付只啟用EXP-20261015-04嘅全程A方法，保留既有六場試閘門檻及fitness／preparation；
唔加入EXP-05/06嘅頭段、自適應L600或用力分配修正。基準／rollback SHA `7a962be5`。
既有資料、HKJC模型同D1帳目不改。Central標準四線程式同步授權沿用。

## 固定部署參數同證據界線

原逐窗OOS驗證：1493場／41日，Gold288→289、Good393→396、Pass749→752。
嗰個結果來自每窗只用之前資料嘅訓練共識，唔係一個固定倍數。
沿原規則，用截至2026-10-14全部2496場做最後部署refit，合格正gain為[1,2]，
取中位數**1.5**；唔係睇過舊窗後手揀一個最大值。固定1.5版本同一舊窗回看係
Gold289、Good394、Pass752，即+1／+1／+3；呢個係重訓後回看，唔係新盲測。
統計不確定性、原歷史來源發布／capture缺口仍在，冇聲稱PRIMARY_WIN／RANKING_WIN。
啟用係按用戶接受小幅點估計、先實作之要求，唔係改判決規則或者包裝成已證實改善。
未改 `docs/model-evaluation-contract.md`，亦冇自動搜尋更多cutoff／gain。

正式`context_lookup`對原研究71日逐項重播，5431筆有配對馬匹往績全部一致，
最大raw差2.35e−13，場內signal差<1e−9。計法沿用field median、prior-date-only
Huber/ridge場地／途程／地況／精確rating／移欄標準，class nuisance評分時移除，
historical trackday variant排除本場。最近六條可匹配正式賽，90日half-life、途程及
地況權重，場內z之後先按sum(w)/(sum(w)+3)收縮；最後加1.5倍到已四捨五入基礎戰力。
唔用頭馬／margin代理，唔用race-header FinishTime，唔用試閘。

## 來源可用性、快取同重播

正式資料位置：AU data-root上一層嘅`AU_Racing_Time_Evidence/latest.json`；
可由`WC_AU_TIME_BUNDLE`明確指定。初始5256場／49613匹次，706來源meeting，
保留一個CSV-only來源同原研究metadata。初始events SHA256：
`634ac636e92521dcaf84bf62525b276e679320db52e5db9f8c751d2e85dfade7`。
2026-10-15T07:01:09.250846+00:00完成正式capture，**valid_from2026-10-16**。

- 新來源透過full AU→Auto CLI嘅`--refresh-time-data`更新，來源URL、hash及capture記錄。
- 整場先準備時間欄位，之後先逐馬評分；不覆寫原分段、試閘或既有矩陣權重。
- 來源event日必須早於target日；capture必須早於prediction timestamp，亦唔准用
  target日之後先捕捉嘅資料回填舊賽日。
- 新快照不可改寫，後續快照gzip壓縮以控制磁碟增長；latest atomic更新。
  既有已評分Logic保留bundle_file，重播選返原不可改寫快照，唔換成較新來源。
- 單匹冇可配對逐駒時間＝raw缺值／貢獻0，唔代表慢。10/16起整份cache missing
  會fail closed，避免全部中性但照發布。來源hash損壞會fail closed。
- source refresh失敗可用仍有效嘅已capture快取並顯示警告，唔虛構新時間。
- 缺日期／formguide保留明確status；未知／重複馬匹配對唔估。

此套future capture同原歷史backtest availability FLAG分開記，唔以新capture冒充
舊來源曾喺歷史下注時可用。資料是位置追蹤分段；官方PDF交叉核對見EXP-06研究分支。
來源只涵蓋RQ，冇證據嘅跨州馬自然中性。

## Dashboard 同模型說明

- 評分JSON／CSV明列`full_time_speed_feature`，重播eval／matrix-refit同驗證器一併跟新公式。
- Markdown獨立「逐駒全程速度」章，列情境指數（par100）、最近一仗完整時間／途程／km/h、
  仗數、證據權重及實際貢獻。km/h不當跨途程直接比較尺。
- report嵌入captured metadata，dashboard只讀當時已評分數值，不重算模型。
- Race頁分開新模型覆蓋率同舊發布版本；已發布5meeting／39場snapshot保留。
  build前後1379個rank／ability／grade／top-picks欄位逐個相同。
- AU PI保持剔除，原L600正式賽證據仍保留；HKJC不受AU顯示政策影響。
- 模型說明由生成器更新，fingerprint加入full_time_speed.py；舊golden純矩陣120案例
  保留作known-good基準。已執行--record檢查，但唔將新抽樣覆蓋舊baseline。
- AU data_contract重校準2000場／19759匹馬；並非用欄位健康或失手體檢去調參。

## 驗證／部署

新增11項AU runtime測試、2項dashboard metadata測試；受影響PF／score API加新測試
123項通過（之後新增immutable replay／cache fail-closed測試亦過）。JS71項通過。
完整repo gate由Central exact-scope release再跑；最終結果、immutable SHA、四線同步
及Cloudflare activation以release manifest／events為準。

以複製嘅Ipswich R2歷史輸入做明確標示demonstration（假設日期10/16，非live prediction）：
6/6馬有覆蓋，實際貢獻+0.3726、+0.2880、+0.6147、−1.0601、−0.1759、−0.0809；
完整engine→Markdown→dashboard parser全部6匹成功，沒有更改原場次或封存預測。

重現／證據artifact：
`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-fulltime-implementation/`。
包括原source seed、hash、原研究轉換比較、provision、cache refresh、示範及dashboard preservation proof。
後續研究先凍結新假設，再用未睇過嘅新賽日驗證；今次唔做更多模型搜尋。
