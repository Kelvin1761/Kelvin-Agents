# HKJC starter PDF 降做軟閘＋fsc 海外往績後備（2026-11-03）

## 目標

穩定性：全日出賽馬匹資料 PDF（`{YYYYMMDD}_starter_all_chi.pdf`）一日攞唔到，唔可以再
卡死成個場次；PDF 喺度嘅時候排名一定唔可以郁。

以前 `batch_extract` 個發佈閘係 `ready = pdf_ok and 排位表齊 and 賽績齊`。2026-09-06 沙田
22 次 run 有 20 次卡喺 PDF。PDF 喺評分入面嘅**唯一**用途係自購馬嘅海外往績
（`parse_pdf_overseas_races` → Facts 🌍 表 → `parse_overseas_races_table` →
`pdf_overseas_races` → form／速度替代／海外騎練層級）。官方傷患記錄都係嚟自佢，但
`OFFICIAL_INJURY_SCORING = "off"`，只係顯示。

## 改咗乜

| 檔 | 改動 |
|---|---|
| `.agents/scripts/hkjc_overseas_formsheet.py`（新） | 下載／cache／解析每匹自購馬嘅 fsc「來港前賽績記錄」PDF，砌返 `parse_pdf_overseas_races` 同一個 dict shape |
| `.agents/scripts/inject_hkjc_fact_anchors.py` | `overseas_source_mode`：PDF 有海外節 → 用 PDF（主來源，行為不變）；冇 → 逐匹 fsc；寫 `Overseas_Fallback_R{n}.json` sidecar |
| `.agents/skills/hkjc_racing/hkjc_race_extractor/scripts/batch_extract.py` | `ready = 排位表齊 and 賽績齊`；PDF 失敗記 `starter_pdf_soft_fail`／`starter_pdf_gate: "soft"` |
| `.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py` | readiness digest：軟閘 PDF 失敗顯示 ⚠️ 同「唔阻塞」；舊硬閘 readiness 照講卡住 |
| `.agents/skills/shared_racing/scripts/racing_data_health.py` | Data_Health warning：`STARTER_PDF_MISSING`、`OVERSEAS_FORM_FALLBACK`／`OVERSEAS_FORM_MISSING`（唔攔 deploy） |

fsc URL：`https://racing.hkjc.com/general/-/media/Sites/JCRW/pp_formsheet/ch/fsc_{烙號}.pdf`
（烙號要補零，`L31` 404、`L031` 得；只有中文）。Cache：`<HK 資料根>/_overseas_formsheet_cache/`
（PDF＋抽出嘅全文永久 cache；404 記 `.missing`，7 日後先再試）。

開關：`WC_HKJC_FSC_FALLBACK=0` 關；預設只對 `FSC_FALLBACK_SINCE = 2026-11-03` 或之後嘅賽日開
（舊場次重跑 Facts 唔會無端多咗海外往績、唔郁舊 baseline）；`force` 任何賽日都開（對照用）。

## 對齊 starter PDF 嘅規則（全部由數據量出嚟）

1. **邊啲馬有表**：PDF 標題寫「24/25, 25/26 & 26/27 PPs」。烙號字母＝入口季度（J=23/24、
   K=24/25、L=25/26、M=26/27）：2026-05～07 PDF 只有 J/K/L，09-06 換季 J 全部消失、10-19
   開始有 M。fallback 只俾最近三季字母嘅馬。
2. **最近 10 仗、舊→新**：`features/form.py` 按 list 次序俾權重，次序一定要一樣；冇名次
   （UR／DNF「- / 5」）嗰仗都計入 10 仗，但同 PDF parser 一樣唔收。
3. **一級／二級／三級 → G1／G2／G3，表列 → L**：引擎海外加分只認 `G1`／`1級` 子字串。
4. 場地：好地 G、好地至快地 GF、好地至軟地 GS、好地至黏地 GY、黏地 Y、軟地 S、爛地 SH
   （法國 VS）、大爛地 H、沙地 Sand；`膠沙地 (Polytrack)`→Polytrack、冇括號→Synthetic
   （英愛四條已知 AW 跑道對返 Polytrack／Tapeta）。表面規則同 PDF parser 一樣。
5. 勝負距離：`1.6馬位`→`1.6L`、馬頭 Hd、短馬頭 SH、馬頸 Nk、馬鼻 Nose、長馬頭 LHd、
   長馬頸 LNk、平頭 DH；負磅去走「(+1)/(-7)」見習減磅；斷行嘅場地／方向／配備由續行補返。

## 對照 1：逐欄（fsc rows vs starter PDF rows）

語料：2026-05-24 → 2026-11-04 全部 32 個有海外節嘅場次（2026-05-24 之前個 PDF 係截斷版，
冇海外節）。

| | 數 |
|---|---|
| 場次 | 32 |
| 匹次（PDF 有列）／唯一馬 | 1,426 ／ 390 |
| fsc 攞到（`ok`） | 1,426 ／ 1,426 |
| 評分欄位逐欄完全一致嘅匹次 | **1,410（98.9%）** |
| PDF rows ／ fsc rows | 6,427 ／ 6,436 |

比較欄位：Date、Distance、Surface、Placing、Field_Size、Weight、Finish_Time_Raw、Margin、
Going、Direction、Region、級別（引擎同款 G1/G2/G3 子字串）。

16 個唔一致匹次逐個解釋（5 匹馬）：

| 馬 | 匹次 | 原因 | 評分影響 |
|---|---|---|---|
| K369、J75、K90、L301 | 9 | PDF 嗰仗名次寫 `*2/8`（勝出後被改名次），**PDF parser 個 regex 唔收 `*`，成仗跌咗**；fsc 照收。fallback 多咗一仗真賽績 | 有：呢幾匹喺 fallback 下多一仗海外往績。係 PDF parser 舊缺陷，唔係 fallback 錯 |
| K192 | 7 | 負磅 `112(+1)`，PDF 寫 111 | 冇：overseas `Weight` 只係顯示 |

顯示欄唔對照：`Racecourse`（fsc 係中文馬場名）、`Gear`（中文配備名）、非分級賽嘅
`Race_Type` 文字（例如「從未勝出馬賽」）。引擎唔讀。

## 對照 2：資格（邊啲馬有 rows）

每個場次所有出賽馬（排位表 烙號），比較「PDF 有冇列」同「三季規則＋fsc 有冇 rows」：

| 期間 | 場次 | PDF 有列＋規則有 | 規則有、PDF 冇列 | 其中 fsc 有 rows | 舊季（兩邊都冇） | PDF 有列、規則冇 |
|---|---|---|---|---|---|---|
| 2026-09-06 → 11-04 | 17 | 587 | 808 | **0**（全部 404） | 662 | **0** |
| 2026-05-24 → 07-15 | 15 | 674 | 953 | **0**（全部 404） | 311 | **0** |

即係：唔會有馬喺 fallback 下無端多咗／少咗成個海外表。404 嘅都係自購新馬／未出過賽，所以
Data_Health 唔將 404 當「攞唔到」，只將網絡錯誤同冇烙號（訪港馬）當。

## 對照 3：成條 pipeline A/B

ABAB_PLACEHOLDER

## Golden

`python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform hkjc` →
✅ 120 匹馬全部一致（評分 code 冇郁）。

## 已知風險

- **PDF parser 跌 `*N/M` 嗰仗**（上面 4 匹馬）：同一匹馬，PDF 喺度同唔喺度會差一仗海外往績。
  正確嘅修法係修 PDF parser（收 `*`），但會改現行排名，要另外過 model gate；今次唔郁。
- **PDF 失敗唔再觸發重試**：以前 exit 75 會自動重試到攞到 PDF；而家 ready 就照跑。官方傷患
  記錄（顯示用）同 dashboard 英文馬名會缺，直到下一次 prerace run 攞到 PDF。
- **烙號字母＝季度** 係實測規律，HKJC 如果跳字母，新季嘅馬會被當舊季 → 冇 fallback rows
  （少咗，唔會多咗）。
- **訪港馬冇 HK 烙號 → 冇 fsc**：fallback 下佢哋冇海外往績，Data_Health 會逐場報 `no_brand`。
- fsc 只喺 starter PDF 冇嘅時候先下載；第一次 fallback 一個場次大約 100+ 個請求
  （大部分係 404），之後全部 cache。

## 重跑命令

```bash
# 逐欄＋資格對照（喺 repo 根目錄跑）
python3 docs/audits/hkjc-starter-pdf-soft-gate-20261103/fsc_parity.py "$PWD" parity.json <場次…>
python3 docs/audits/hkjc-starter-pdf-soft-gate-20261103/fsc_eligibility.py "$PWD" elig.json <場次…>
# 單元測試
python3 -m pytest .agents/scripts/tests/test_hkjc_overseas_formsheet.py
```
