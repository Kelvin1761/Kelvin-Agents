# AU 冷門包尾／熱門漏捉原因歸因 — 2026-08-09

## 問題

固定 805 場 current-runtime dataset 後，兩組賽後錯例係：

- 冷門包尾：Model Top 3、SP ≥ 21、實際包尾，共 32 匹；其中 30 匹 Performance
  Quality 係 missing/fallback。
- 熱門漏捉：市場頭馬實際入前三、Model 排第 5 或以下，共 81 匹；其中 73 匹
  Performance Quality 係 missing/fallback。

SP 同實際名次只喺 production rank 固定後用作錯例標籤，從來冇進入 scorer。

## 先分清相關性同原因

`missing/fallback` 高並唔等於佢直接造成錯誤。舊日期普遍使用 legacy schema，所以成功例亦
大量 fallback：

| Matched cohort | PQ fallback | 平均 coverage |
|---|---:|---:|
| 冷門 Top 3、實際包尾 | 93.8% | 82.8% |
| 冷門 Top 3、實際入前三 | 89.7% | 85.2% |
| 市場頭馬入前三、Model 第 5+ | 90.1% | 80.4% |
| 市場頭馬入前三、Model 成功入 Top 4 | 86.7% | 84.1% |

即係錯例同成功例嘅 fallback rate 只差 `+4.1pp / +3.4pp`，遠細過原本
`30/32 / 73/81` 表面比例。Performance Quality 係共同 schema 狀態，唔係單一根因。

## 反事實檢查

逐匹只將 Performance Quality 拉到場內平均、其他所有 leaf 固定：

- 冷門包尾只直接修正 8/32；
- 熱門漏捉只直接修正 3/81。

全場所有 fallback 一律改成 neutral 60：

| Cohort | Before | 原錯例修正 | 新錯例 | After |
|---|---:|---:|---:|---:|
| 冷門包尾 | 32 | 11 | 8 | 29 |
| 熱門漏捉 | 81 | 11 | 15 | 85 |

所以直接 neutralize / shrink fallback 會救一批、同時製造另一批，尤其熱門漏捉淨惡化。

## 冷門包尾真正原因

32 匹入面 Model rank 分布：rank 1 = 5、rank 2 = 9、rank 3 = 18；平均領先 rank-4 cutoff
`+2.65` score。

逐匹對 rank-4 cutoff 做 weighted matrix gap attribution：

| Dominant attribution | Cases |
|---|---:|
| Performance Quality 相對場內失真、單 leaf 已足以修正 | 8 |
| Jockey / trainer 高估 | 6 |
| Pace / performance 高估 | 5 |
| Form + consistency stability bundle 高估 | 5 |
| Class / weight 高估 | 3 |
| Race shape 高估 | 2 |
| Track 高估 | 1 |
| 其他 stability | 1 |
| Pace evidence gap | 1 |

同「同樣 SP ≥ 21、Model Top 3、但實際入前三」嘅成功冷門相比，失敗冷門場內 matrix
delta 差異係：

| Matrix | Failure minus successful cold pick |
|---|---:|
| Stability | +0.23 |
| Pace / performance | -3.06 |
| Race shape | **+2.48** |
| Jockey / trainer | -1.53 |
| Class / weight | -1.30 |
| Track | -1.97 |

結論：主要 pattern 唔係「冇 PQ 所以亂排」，而係底層 pace、場地、級數同人馬支持較弱，
但 race-shape／局勢或個別高分 matrix 仍足以推入 Top 3。PQ fallback 平均比場內高
`+7.24`，等效總分約 `+3.29`，係其中一個放大器；但只對 8 宗構成單獨充分原因。

## 熱門漏捉真正原因

81 匹入面 rank 5–6 有 48 匹，rank 7+ 有 33 匹；平均落後 rank-4 cutoff `-3.26`。

逐匹 dominant attribution：

| Dominant attribution | Cases |
|---|---:|
| Form + consistency stability bundle 低估 | 25 |
| Pace / performance 低估 | 16 |
| Jockey / trainer 低估 | 15 |
| Race shape 低估 | 11 |
| Pace evidence gap | 4 |
| Jockey-horse fit evidence gap | 3 |
| Performance Quality 單 leaf 相對失真 | 3 |
| Class / weight 低估 | 2 |
| Track 低估 | 1 |
| 其他 stability | 1 |

同「市場頭馬入前三而 Model 成功放入 Top 4」相比：

| Matrix | Missed favourite minus caught favourite |
|---|---:|
| Stability | **-8.55** |
| Pace / performance | **-13.83** |
| Race shape | -5.18 |
| Jockey / trainer | -7.05 |
| Class / weight | -6.18 |
| Track | -4.83 |

呢批馬唔係單一 PQ leaf 被壓低，而係模型從多個賽前能力面都判斷偏弱。Feature 平均亦一致：

| Feature | Missed favourite | Caught favourite | Delta |
|---|---:|---:|---:|
| Form | 58.37 | 67.12 | -8.75 |
| Rating | 59.60 | 62.96 | -3.36 |
| Pace figure | 55.85 | 70.49 | -14.64 |
| Consistency | 75.10 | 84.05 | -8.95 |
| Sectional | 68.56 | 71.06 | -2.50 |
| Trial | 74.06 | 77.24 | -3.18 |

正式賽績較淺亦明顯集中：

- 0–2 場正式賽：missed 25/81 = 30.9%，caught 104/483 = 21.5%；
- 0 場正式賽：missed 9/81 = 11.1%，caught 18/483 = 3.7%；
- 平均 formal count：4.47 vs 5.29；
- Soft/Heavy：67.9% vs 57.4%。

結論：熱門漏捉主要係「少往績／條件轉變下，現有多個能力 matrix 同時睇淡，但馬匹實際已
有能力上名」。PQ fallback 平均只比場內低 `-1.74`，而且相對 neutral 仍為總分增加約
`+1.97`；所以將 73 個 fallback 視為 73 個 PQ-caused miss 係錯誤診斷。

## 第二輪：來源核對及 sample × going 交互

### Rating 唔係 parser 漏數

用 Sportsbet cache 嘅目標賽事頁逐場核對，場次由頁面內 `Venue Race N` metadata 決定，
冇再用 raceId 次序推斷：

- 熱門漏捉有 29 匹 runtime rating fallback；80/81 場頁面可讀，29 匹全部成功對名，
  但原始 overview rating **0/29** 有數值；
- 冷門包尾有 7 匹 rating fallback；32/32 場頁面可讀，7 匹全部成功對名，
  原始 overview rating同樣 **0/7** 有數值；
- 所以呢批 rating 缺口係來源本身顯示 `-`，唔係 transport／name alignment bug。

Gear change 亦冇足夠區分力：冷門包尾 4/32（12.5%）對成功冷門 5/29（17.2%）；
熱門漏捉 16/81（19.8%）對成功捕捉熱門 80/483（16.6%）。細分類亦冇一個穩定方向：
`Tongue Tie FIRST TIME`、blinkers on/off、cross-over nose band 等喺兩邊都有。

### 真正集中點係少往績 × 濕地，但仍要做因果檢查

分母只用「市場頭馬而且實際入前三」，避免將市場本身揀錯嘅馬混入：

| 正式賽樣本 | Going | Model 第5+ | Model 第1–4 | 漏捉率 |
|---|---|---:|---:|---:|
| 0–2 | Good | 2 | 32 | 5.9% |
| 0–2 | Soft | 14 | 51 | 21.5% |
| 0–2 | Heavy | 8 | 19 | 29.6% |
| 3–4 | Good | 2 | 26 | 7.1% |
| 3–4 | Soft | 21 | 72 | 22.6% |
| 3–4 | Heavy | 3 | 31 | 8.8% |
| 5+ | Good | 18 | 129 | 12.2% |
| 5+ | Soft | 6 | 85 | 6.6% |
| 5+ | Heavy | 3 | 19 | 13.6% |

合併 0–4 場：Good 漏捉 `4/62 = 6.5%`，Soft/Heavy 漏捉
`46/219 = 21.0%`。呢個交互遠強過 PQ fallback rate 差異。

但相關性唔等於現行 `wet_unverified_pen` 直接造成。只將 Soft 7+/Heavy、濕地零出賽馬
由「未經驗證 −6.4」回復中性，404 匹受影響；canonical gate 結果係：

- development Top-5 AUC `−0.00010`；terminal `−0.00024`，CI 跨零；
- 原有熱門漏捉修正 **0**，新增 **1**；冷門包尾完全不變；
- Good / Pass 各跌 0.12pp。

大部分淺往績漏捉其實發生喺 Soft 5/6，本來已經冇 `wet_unverified_pen`；濕地 overlay 對
零濕地樣本亦會 shrink 到 neutral。故此問題唔係一行罰分寫反，而係濕地環境下，淺往績馬
嘅現有公開能力證據判別力不足。

### 冷門亦唔係「形勢一項單獨推上去」

將 race-shape 排除後，32 匹冷門包尾全部仍有最少 2 個其他 ability matrix 高過場內平均：
2 個支持有 9 匹、3 個有 10 匹、4 個有 11 匹、5 個有 2 匹。即係簡單加一個
「形勢要另一項確認」gate 唔會命中真正問題，亦解釋點解之前 slot rerank 方向唔合適。

## 可再利用資料：優先次序

現有 cache 可安全重用嘅 rating、gear、sire、winning time、opponent follow-up 已逐項核對／
shadow test；rating 冇來源值，gear 冇穩定方向，其餘候選未過 canonical gate。下一批真正
可能補到「淺往績 × 濕地」嘅唔係再調同一堆 matrix 權重，而係新增 point-in-time 能力證據：

1. 由今日開始 versioned 保存 trainer / jockey profile 嘅 going、distance、barrier、field-size
   同 monthly trend snapshot；現時頁面會滾動更新，禁止倒填歷史；
2. 保存每次 trial / jump-out 嘅實際時間、同組對手及場地狀況，而唔只係名次；
3. 保存賽前 trackwork / gear announcement 嘅 captured-at snapshot，日後先驗證「首次配備」
   係咪只對特定類型／馬齡有效；
4. 如果要用 pedigree，應做「父系 × going × age / first-start」嘅 point-in-time prior；已有
   泛用 sire prior 全體 A/B 係負，唔應直接加入現役分。

未有呢類新增證據之前，強行將淺往績濕地馬加分，只會將市場已知但模型未知嘅成功例同大量
真正未成熟馬一齊推高。

### 已再驗證、仍然唔應上線嘅兩個結構候選

**正向 PQ fallback reliability cap**：只處理 5+ 場正式往績、PQ fallback 高過場均嘅馬，
將超額收一半。Development Top-5 AUC `+0.00058`，但 terminal `+0.00159` 嘅
95% CI 係 `[-0.00104, +0.00443]`，證明唔到改善；全體 Gold `+0.62pp`、Pass
`+0.87pp`，但 Good `-0.12pp`、Champion `-0.50pp`。冷門 32→31、熱門 81→79，
仍然係 trade-off，唔升級。

**Point-in-time sire wet prior**：按日期分組，當日所有賽事先取舊 state，成日完結後先更新，
杜絕 same-day／future leakage；只用喺 wet、正式往績 0–4 場。Development 上先驗本身
AUC `0.5253`（4,168 對），93.4% runner 有 prior-date 覆蓋；但加返現役模型時 scale
5/10/20 全負，scale 30 只係 `+0.00015`，方向唔單調兼近噪音，所以冇開 terminal。
泛用／濕地專用兩條 sire 路線均不足以升級。

## 第三輪：修正真正嘅歷史資料 transport gap

其後核對 live parser、Logic 同舊 archive，確認 current Sportsbet complete-form parser 已經會
保存 margin、prize、starters，同可以正常建立 primary `performance_quality_raw`；但舊 archive
Logic 從未用呢批 point-in-time complete-form 資料重建，所以 canonical 805 場仍沿用
consistency fallback。呢個係歷史資料 transport/backfill 缺口，唔係要用 SP 或賽果調分。

修正採用單一路徑：

1. sidecar 每個歷史 run 必須嚴格早於目標 meeting date；
2. 每場最少 3 匹有完整 digest、而且場內有變異，先建立 field-relative PQ；
3. 只填冇 primary `performance_quality_raw` 嘅舊馬；live／primary evidence 永遠優先；
4. reconstructed evidence 只以 10% reliability 融入 consistency anchor，明確保留 secondary
   provenance，唔當成原日 captured Facts；
5. backfill dry-run 為預設、原子寫檔、可重跑 idempotent，亦可只移除新增嘅 5 個欄位 rollback。

Archive 實際 backfill：124 個 meeting、1,064 個 Logic、9,496 匹馬；7,811 匹成功恢復、
844 個 Logic 有改動。重跑 dry-run 顯示 7,811 個 `already_current`、0 個檔案再改，證明冇漂移。

### Authoritative 805 場重建結果

舊、新 dataset 逐場逐馬完全對齊：805 場、8,249 匹。結果 CSV 必須用更新至
2026-08-07 嘅 9,275-row point-in-time merge；archive root 內舊 CSV 只更新至 2026-07-08，
只會對齊 710 場，唔可攞嚟做版本比較。

| 指標 | 修正前 | 修正後 | Delta |
|---|---:|---:|---:|
| Gold | 16.77% | 16.89% | +0.12pp |
| Gold strict | 6.58% | 6.34% | -0.25pp |
| Good（頭兩揀都上名） | 25.71% | 25.71% | 0.00pp |
| Pass | 47.20% | 46.96% | -0.25pp |
| Champion | 25.22% | 25.09% | -0.12pp |
| Winner@3 | 56.27% | 56.89% | +0.62pp |
| Winner@5 | 75.53% | 75.65% | +0.12pp |
| Top-3 precision | 47.70% | 47.87% | +0.17pp |
| Top-5 AUC（全 archive） | 0.69294 | 0.69485 | +0.00191 |

Canonical promotion gate：

- development Top-5 AUC `+0.0009`；
- untouched terminal Top-5 AUC `+0.0048`，按場 paired bootstrap 95% CI
  `[+0.0013, +0.0093]`；
- terminal 全場 AUC `+0.0024`，95% CI `[+0.0002, +0.0047]`；
- development 五個 whole-date folds 有 4/5 正向、餘下一個持平。

錯例亦係淨改善，而唔係淨係移走 fallback label：

| Cohort | 錯例 Before → After | PQ fallback Before → After |
|---|---:|---:|
| 冷門包尾 | 32 → 30 | 30 → 9 |
| 熱門漏捉 | 81 → 78 | 73 → 17 |

所以今次可以升級：佢修正大部分可恢復嘅歷史 PQ schema 缺口，兩組目標 failure 都下降，
而且 untouched terminal 嘅主要統計閘顯著為正。Gold strict／Pass 各少 2 場同 Champion 少
1 場屬幅度參考，已如實保留；下一輪唔應為補返呢幾場而做 slot-specific 微調。

## 對剩餘下一步嘅約束

原因未確認前做過嘅 neutral shrink、完整賽績直接 blend、winning-time、父系先驗同
consensus fusion 都有「救舊錯例但製造更多新錯例」現象，唔應上 production。

完成 transport recovery 後，剩餘解法仍必須分開兩個問題：

1. 冷門：唔用 slot gate；針對 5+ 場樣本入面 PQ 相對失真／pace 高估做 provenance-aware
   calibration，但必須同成功冷門一齊驗證；
2. 熱門：重點係新增淺往績濕地嘅 point-in-time 能力證據；現有矩陣內部換權同
   `wet_unverified` 中性化都冇提供有效解法；
3. 任何候選都要報原錯例修正數、同時新增錯例數，禁止只展示「救到幾匹」。

可重跑 audit：

- `scripts/au_failure_cause_attribution.py`
- `scripts/au_backfill_sportsbet_performance_quality.py`

完整逐匹 JSON / Markdown 預設輸出到 `/private/tmp/au_failure_cause_attribution.*`。
