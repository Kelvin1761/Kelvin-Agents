# AU 場次清單分級 + 「即將開跑」時間線（2026-10-31）

## 點解要改

2026-10-31 星期六有 16 個 AU 場次，首頁係 16 張一模一樣嘅卡，冇按時間排、冇分級。
揀咗場次之後，race board 喺手機要碌過全部卡（大約 4 個 mon）先見到。

## 而家點樣

- **賽事 tab（賽前投注用，保留原本流程）**：每個場次一行，分「⭐ 釘選／都會／省級／鄉鎮」，
  組內按首場開跑時間排。場次多過 8 個時，鄉鎮組預設收埋。揀場次之後會自動碌去 race board；
  每格 race tile 都有開跑時間。
- **⏱ 即將開跑 tab（只喺澳洲出現）**：全日每場按開跑時間排，顯示倒數、級別、首選同次選。
  已開跑同取消嘅場預設收埋。可以用級別或者釘選篩選；`?sport=au&view=timeline` 可以直接打開。
- 釘選、收埋同篩選都記喺瀏覽器 localStorage，只係方便用，冇儲去伺服器。
- **開跑緩衝**：澳洲賽事好多時遲 1–2 分鐘先開跑，所以一場會留喺「即將開跑」直至開跑時間過後
  1 分鐘（`RACE_START_GRACE_SECONDS`）。場次清單嘅「下一場」同 race 卡嘅「已開跑」用同一條規則。
- **時間線投注卡**：每一場都直接顯示首選同次選嘅投注卡，同分析頁嘅投注面板係同一套卡，狀態亦同步。
  投注狀態按場次讀寫（`betStateMap`），所以喺時間線幫第二個場次落注，唔會寫錯去當前揀中嘅場次。
  賠率輸入格嘅 name 包埋場次，避免兩個場地嘅 R1 #2 撞名。
- **投注卡**：維持原版一行一張（試過兩張並排，電腦同手機都太迫，已經放棄）。已投注嘅卡改成固定兩行：
  第一行係「已投 @賠率」加「改賠率／退出」，第二行係「名次 1 2 3 X」，字體大細統一。
- **HKJC 開跑時間**：直接讀馬會排位表（`… Race N 排位表.md`）入面嘅 `日期:` 同 `時間:`，當香港時間。
  HKJC 流程已經會抽排位表，所以**唔使加請求，亦完全唔掂 Sportsbet**（`_read_hkjc_racecard_times`）。
  HKJC race board 用香港時間，AU 用悉尼時間；兩邊都喺開跑前一個鐘內顯示倒數，過咗開跑時間
  1 分鐘之後變淡。HKJC 唔做「即將開跑」模式。
- **HKJC 同 AU 共用**：race board 改用 `renderRaceCard`，每格只有兩行，第一行場號同時間，
  第二行距離同馬匹數。班次名放喺 tooltip；落咗注會喺右上角顯示一粒綠點。
  分析頁嘅投注面板亦搬咗去分析內容之前。

## 數據點樣嚟

| 資料 | 來源 | 幾時更新 |
|---|---|---|
| AU 每場開跑時間、取消咗邊幾場 | Sportsbet AllRacing。排程本身已經會抓，**冇加任何請求** | 晚更分析時寫入；早更補完當日場次時會重寫，所以改咗時間會跟到 |
| HKJC 每場開跑時間 | 馬會排位表嘅 `時間:`（HKJC 流程已經抽咗） | 每次重抽排位表 |
| 都會／省級／鄉鎮、州份 | `Horse_Racing_Dashboard/backend/services/au_venue_tiers.json`，一次性整理嘅各州官方定義 | 人手；改咗官方分類先需要更新 |

- 排程：`au_daily_schedule.au_race_start_times()` 同 `record_race_start_times()` →
  每個場次 folder 寫一個 `Race_Start_Times.json`，格式係 `{races: {"1": epoch}, abandoned: [..]}`。
- Dashboard：`generate_static._attach_au_meeting_context()` 喺讀完 cache **之後**先貼上去
  （同賽道幾何一樣），所以改開跑時間唔會觸發重新 parse 分析。
- 呢份分級表**只係用嚟顯示**。評分引擎用嘅係 `au_track_geometry.json` 入面逐個賽日嘅
  Racing Australia「Meeting Type」，兩樣唔互相讀。

## 分級來源同未核實嘅部份

- NSW：Racing NSW 都會 4 個（ATC），省級 5 個（PRANSW）。
- VIC：Racing Victoria 2023 年見習騎師分級。Ballarat、Pakenham 只計**草地**跑道先算省級，
  人造跑道算鄉鎮。
- SA：Racing SA Local Rules。Port Lincoln、Mount Gambier 由 2026/27 季起改為鄉鎮。
- QLD：Eagle Farm、Doomben 係都會；SEQ 省級會所係 Gold Coast、Sunshine Coast、Ipswich、Toowoomba。
- **未核實**：WA 嘅省級名單（搵唔到 RWWA 逐個場地列出，用咗 Racing Australia Meeting Type）、
  TAS 嘅 Devonport、ACT 嘅 Canberra。
