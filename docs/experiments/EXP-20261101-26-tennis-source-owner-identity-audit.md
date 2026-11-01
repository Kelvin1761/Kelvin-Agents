# EXP-20261101-26：來源球員歸屬、canonical chain及現有reader診斷

狀態：完成唯讀診斷及離線重播，確認現有serve-profile reader可接受來源標籤不一致的記錄；未修mapping／history／模型，未重判訓練資格，未證明準確度或投注改善。

## 1. 先釐清3729個舊ID旗標

[EXP-25](EXP-20261101-25-tennis-public-point-input-inventory.md)的provider-ID conflict是保守檢查，不等於3729條都是錯人物。沿用完整3729個history ids、凍結DB SHA `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`及原始body hashes；另外短transaction讀取live相同ids、players、provider links及merge receipts，關閉連線後離線分類。

| snapshot | terminal收斂且現有name/tour policy通過 | 未能解釋 |
|---|---:|---:|
| frozen | 2825 | 904 |
| live（08:12:51 UTC） | 2849 | 880 |

live 880中856 ACTIVE、24 DISPUTED；2849中2847 ACTIVE、2 DISPUTED。3729條所選identity／source-link欄位與凍結版本全相同，並非我們修改history產生改善。live metadata讀取transaction約0.344秒，沒有長時間持有DELETE-journal讀鎖。

**2849不是合格訓練數。** 現有`_identity_agrees`接受UNKNOWN tour、部分first-name initial及middle-name omission；其中1517條至少一邊terminal tour仍UNKNOWN。merge-chain收斂亦未證明歷史時刻已知merge或獨立人物身份。本次沒有把EXP-25原旗標改成PASS。

live每個row兩個side合計7458：4800直接ID相同、1751經chain收斂、108 terminal name/tour不一致、799 terminal IDs不同。799再分：654個stored owner符合raw name/tour但當前mapped owner不符；102個兩邊名稱policy都符但IDs不同；17個兩邊均不符；26個stored不符而mapped符合。**不能盲目將history改成當前provider mapping，也不能將同名IDs直接merge。**

## 2. 擴至原完整160900條，避免只用小範圍推論

因為直接ID相同亦可能有source-name不一致，另用相同凍結DB／player graph掃描全部160900個public-history sides。結果是既有policy下的**標籤診斷**，不是所有名字變體都已證實屬不同人；合法改名／alias仍須來源證據。

| EXP-25原狀態 | explicit terminal tours且policy符合 | policy符合但有UNKNOWN terminal tour | source-name／terminal標籤衝突 | source identity不可讀 |
|---|---:|---:|---:|---:|
| LINKED_POINT_COUNTS | 143385 | 1 | 2153 | 0 |
| HELD | 12364 | 1506 | 500 | 991 |

全部2653個label-conflict rows中2629 ACTIVE；provider分布Sackmann688、TML1965。這解釋為何145539個raw點數連結不能當作已認證球員歸屬／訓練集。原160900行、held及兩側角色均保留，沒有按模型勝負／ROI挑樣本或自動剔除資料。

## 3. 現有reader的具體讀取路徑

取前述診斷最早出現的兩個具名案例，固定呼叫既有`serve_return_profile`：as_of_date=`2026-11-01`、surface=None、start_time=`2026-11-01T00:00:00Z`。這是**現在執行的假設性reader probe**，不是那個歷史時刻的immutable prediction，也不是實際投注證據。

| live entity（08:31:17 UTC） | profile rows | is_usable | 與凍結來源欄位相同、但own-player標籤不一致 |
|---|---:|---|---:|
| 1180，Toby Samuel，ATP，無parent | 25 | true | 7；原raw player label為Stefan Kozlov |
| 2110，Jumpei Yamasaki，UNKNOWN，無parent | 4 | false | 3；原raw player label為Christian Sigsgaard |

第一個案例的history ids：3138356、3138333、3682470、2630456、1480572、1480557、537316。比較了provider/raw id/source ref、player/opponent/tour/date、hold及三項serve/return rates等選定欄位，均與已有凍結來源證據一致。**沒有宣稱重新驗了live raw body全文**，亦沒有聲稱實際card／bet用過這組profile。第二案例的profile本來已被最少樣本量閘擋住；兩個案例均未核對實際card／bet。

probe只讀transaction約0.024秒；所用reader source與已安裝runtime逐byte相同，SHA `908247c0b56abbe8651eeef0e4bd4c0a0f9660cdd2a5835e0fb60df64adac2f3`。原始碼policy固定66d42bc6，沒有更改評分／缺失處理／下注規則。

## 4. 獨立來源及修正界線

歷史raw中Stefan為Sackmann111578／TML KE64，Christian為Sackmann144841／TML SY00。ATP可讀頁佐證[Toby Samuel的S0TM頁](https://www.atptour.com/en/players/-/s0tm/overview)及[Christian Sigsgaard的SY00頁](https://www.atptour.com/es/players/christian-sigsgaard/sy00/overview)。Stefan KE64、Jumpei Y235有官方索引資料，但部分直接頁403／cache miss；GitHub connector讀players CSV亦404。這些失敗保留為限制，不等於來源不存在，也不冒充已取得完整player registry或DOB證明。

尚未做任何rename、merge、split、quarantine或live DB修補。下一步要獨立核對provider namespace＋external player ID、canonical target及alias／DOB等證據，尤其一個entity已混有兩種raw player labels時，不能靠整體rename／merge修好。任何修補方案須保留雙側event事實、檢查已有正確副本及canonical_event_key衝突、保存source clock／observations及rollback，才做同語料baseline/candidate影響比較。

內置碟本輪約5–6.3GiB，低於大型實驗10GB要求；沒有新fit／大型副本或模型A/B。診斷讀取與小型metadata／串流結果全部在外置碟，不刪其他session暫存。舊15個REJECT_DEV、historical publication FLAG、F10依賴及forward資格不變；source-owner label問題必須先解釋，不能先調權重。

## 5. 重播及證據

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

| 子目錄 | 保留內容／manifest SHA-256 |
|---|---|
| identity-triage-v1 | protocol、原始source、完整rows、frozen/live小型metadata、result；`1db46953273b6ac22cf405ad0894183984f5f99a9d97b53114c6f607b287ad69` |
| identity-triage-replay-v1 | 不開live DB，用已存metadata重播3729×2=7458個row projections，全與原件相同；固定identity/name policy source；`ac8a4c56661646f8114bb9c750a648d9eb96bb2d53d8be507f132e011b6d7126` |
| history-owner-inventory-v1 | 全160900條ownership rows、source、protocol、result及固定首10個例；`4406c10230f0232e312fb99ae428c72ee853b65d2678c071275c57e93a757773` |
| owner-reader-probe-v1 | reader參數、兩個profile及各history選定欄位對照、source、result；`fae42b78cda5d4d32f82d1d663910b2ab40b2b37c49f04ab5e051dbf734389f3` |

原執行：repo根目錄，`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python <script>`；四份script原位於`/private/tmp/tennis-point-identity-triage-20261101.py`、`tennis-identity-triage-replay-20261101.py`、`tennis-history-owner-inventory-20261101.py`、`tennis-owner-reader-probe-20261101.py`，均另存各目錄source.py。重新capture要改成全新輸出目錄；live之後會變，不能期待重讀live得到舊結果。驗舊結果應使用離線replay及保存的metadata，不倒填新觀察。replay沿用原分類函式，只驗可重現性，不能當新增獨立oracle或人物身份／準確度證明。
