# EXP-20260902-03 官方 Speedmap：parser 全錯、從來冇駁線，接返之後同我哋嘅圖近乎正交

- **日期**：2026-09-02
- **平台**：AU
- **假設**：Sportsbet 有冇自己嘅步速／定位預測？值唔值得攞嚟做顯示同分析？
- **搜索過嘅舊記錄**：memory `au-sportsbet-speedmap-rejected`（**排名**輸我哋自己個標籤，
  AUC 0.5204 vs 0.5395、預測定位 ρ 0.20 vs 0.49）、`au-written-field-is-not-a-filled-field`
  （`speedmaps=` 冇 caller 傳，292 行 SpeedPos 真值 0 行）。
- **改到嘅檔案**：`claw_sportsbet_form.py`（`parse_speedmap`、`get_cached`、`main`）、
  `au_daily_auto/au_daily_schedule.py`（`warm_speedmap_pages`）、
  `tests/test_odds_capture.py`、`tests/test_au_daily_schedule.py`

## 一：Sportsbet 出緊乜

`?view=Speedmap` → 版頭寫住 **`Speed Map / Predicted settling positions after start`**，
逐匹馬一個預測起步位序，另加 `Rail Position`。純賽前資料，冇洩漏。
**冇**race-level 嘅快慢判斷 —— 嗰個係我哋自己 `_classify_pace_v2` 砌嘅。

## 二：parser 喺 836/836 個 cache 頁都係錯

版面有**兩款**，舊 regex 只識一款：

```
數字先：  13  3. Smokin' Romans   12  5. Freedom Rally  …   （373 頁）
馬先：    3. Depth Of Character  10   5. Port Lockroy   9   （463 頁）
```

撞正「馬先」嗰款，`(\d+)\s+(\d+)\.\s` 會將**上一匹馬嘅行號**派畀下一匹，同時
**靜靜丟咗第一匹**（即係預測跑最尾嗰匹）。實例：

| | |
|---|---|
| 真值 | `{1:7, 2:8, 3:10, 4:5, 5:9, 6:2, 8:3, 9:6, 10:1, 11:4}` |
| 舊 parse | `{1:8, 2:9, 4:6, 5:10, 6:3, 8:4, 9:7, 10:2, 11:5}` ← 冇咗 3 號，其餘全部 +1 |

⚠️ 講清楚幅度：**佢唔會扭轉次序**（每匹平移一格，相對排序不變），所以造成嘅
唔係「方向錯」，係「每場靜靜少咗一匹馬」。單元測試一直綠，因為 fixture 只寫咗
「數字先」嗰款 —— 同 `health-gate-au-branch-was-never-run` 一樣嘅形狀。

修法：兩款都讀，再用「行號唔可以撞 + 每匹列出嘅馬都要有行號」做驗證閘，
驗唔過返空 dict（唔交半份）。**836/836 全部完整合法排列。**

## 三：由來冇駁線

`write_meeting()` 從來冇收過 `speedmaps=` —— 語料庫 **11,356 行 `SpeedPos:`，0 行有值**。
接返之後（cache-only，零額外請求）實跑 2025-08-09 Randwick 10 場：**132 行有值**。

日常抽取加咗 `warm_speedmap_pages()`：每場多攞一版 `?view=Speedmap`。
係**純加碼**步驟 —— 個站一拒絕即刻收手、單版失敗跳過、全程唔 raise、
`WC_AU_SPEEDMAP=0` 熄得。（Speedmap 只可以行真瀏覽器，curl_cffi 一定 403。）

## 四：接返之後量返 —— 兩個圖近乎正交

353 場（有 cache speedmap + 有我哋往績 + 有實際起步位）。真值嚟自「呢匹馬之後
再出賽時嘅往績行」，只做 label。

| 預測 | vs 實際起步位 Spearman ρ | 95% CI |
|---|---|---|
| Sportsbet 官方 Speedmap | +0.241 | [+0.200, +0.281] |
| 我哋近仗加權起步位 | **+0.443** | [+0.409, +0.480] |
| 配對差（Sportsbet − 我哋） | **−0.203** | [−0.261, −0.145] |
| **兩個預測之間** | **+0.005** | — |

單論準確度我哋贏，同舊結論一致。**但兩者之間 ρ = +0.005 —— 近乎完全正交。**
兩個都同真值正相關，彼此卻冇關係，即係 Sportsbet 嗰個帶住我哋冇嘅資訊。

混合（場內 z-score，`w·Sportsbet + (1−w)·我哋`），時間切分，w 只喺 dev 揀：

- dev 247 場（2025-08-02→2026-05-23）：w=0.0 → ρ +0.475；w=0.3 → **+0.509**（曲線平滑，峰喺 0.3）
- **holdout 106 場（2026-05-23→2026-08-01，冇參與揀 w）：混合 ρ +0.433 vs 單用我哋 +0.370，
  差 +0.063 CI [+0.023, +0.102]** ✅

## 檢查
- **leakage-audit**：PASS —— Speedmap 係賽前頁；真值嚟自**之後**嘅往績行，只做 label。
- **golden_scoring**：AU / HKJC 各 120 匹馬全部一致（呢個改動唔掂排名）。
- **data_contract**：PASS。`./檢查.sh` 五項全綠、九個 suite PASS（新增 3 個 speedmap 暖 cache 測試）。

## 結論

**「Sportsbet speedmap 冇用」呢個結論要分開兩半睇。** 佢做**排名**輸我哋（舊結論企得住），
但佢預測**起步位**嘅資訊同我哋近乎正交（ρ +0.005），30% 權重混合喺未碰過嘅 holdout
上贏 +0.063 ✅。之前量唔到呢樣，一半原因係個 map 由頭到尾冇入過任何檔案。

⚠️ **呢個係步速圖層嘅改善，唔係排名層嘅。** 預測起步位準咗 ≠ 預測名次準咗 ——
跑法做排名特徵今日先啱啱喺 Stage 4 v2 之下 REJECT（EXP-20260902-02）。要用落排名
必須另外過閘。

**決定**：
- `parse_speedmap` 修正 + 驗證閘 → **KEEP**（正確性，可獨立證明）
- 駁線（cache-only）+ 日常暖 cache → **KEEP**（Kelvin 2026-09-02 明確決定要抓）
- 30/70 混合做**顯示層**嘅預測起步位 → **建議採用**，但要先決定擺喺邊（Facts 步速圖定係報告）
- 混合落**排名** → **未測**，唔准就咁當通過

**commit**：未 commit

## 重跑
```bash
python3 -m pytest .agents/skills/au_racing/au_wong_choi_auto/tests/test_odds_capture.py -q
python3 -m pytest .agents/skills/au_racing/au_daily_auto/tests/test_au_daily_schedule.py -q -k Speedmap
```
