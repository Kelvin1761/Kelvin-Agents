# HKJC Horse Analyst — SIP 索引 (Systemic Improvement Proposals Index)

> **用途：** 集中追蹤所有 SIP 的定義位置、觸發條件摘要、及跨檔案引用。
> 避免 SIP 分散導致遺漏或重複定義。Reflector 覆盤時應參考此索引。

---

## 引擎核心 SIP

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-1 | 評級矩陣量化門檻 | `06_rating_aggregation.md` | 穩定性/段速/EEM/練馬師的數字門檻 |
| SIP-2 | 路程否決權 | `04_engine_corrections.md` | 同程成績否決一切情境加分 |
| SIP-3 | 短途前速外檔豁免 | `04_engine_corrections.md` | 1000-1200m 前速馬外檔降格為⚠️ |
| SIP-4 | D級冷門掃描 | `06_rating_aggregation.md` | D級馬強制反問稀有正面訊號 |
| SIP-5 | 騎練訊號標準化 | `07c_jockey_profiles.md` | 騎練組合判定規則+冠軍騎師標準化 |

## 覆盤衍生 SIP（SIP-ST 系列，源自 Sha Tin 覆盤）

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-ST1 | 首出馬穩定性重置 | `06_rating_aggregation.md` | 首出馬穩定性 → ➖ Neutral（非❌）+ 複合升級 |
| SIP-ST2 | AWT 情境維度 | `06_rating_aggregation.md` + `10c_track_awt.md` | AWT 前速紅利 + 中群食沙懲罰 |
| SIP-ST3 | 四/五班輕磅反彈 | `04_engine_corrections.md` + `06_rating_aggregation.md` | ≤118lb + 近3仗有走勢 → 升級（不限檔位） |
| SIP-ST4 | 騎師反差配訊號 | `07a_signals_framework.md` | 次選騎師 ≠ 放棄；有走勢 + 次選騎師 → 中性/正面 |
| SIP-ST5 | 冷門冠軍安全網 | `06_rating_aggregation.md` | C/C-級馬強制掃描稀有正面訊號 → 升至 B- |
| SIP-ST6 | 步速量化閾值 | `06_rating_aggregation.md` | 龜速壟斷/自殺式後追/AWT前速等具體觸發條件 |
| SIP-ST7 | 級數壓倒豁免 | `06_rating_aggregation.md` | 近4仗勝率≥50% + 2核心✅ + 賠率≤4x → 死檔降格 |
| SIP-ST8 | 品質守門員 | `SKILL.md` | 堅持真實數據、反模板化、批次完整性 |

## 覆盤衍生 SIP（SIP-HV 系列，源自 Happy Valley 覆盤）

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-HV1 | 沉睡專家回師豁免 | `04_engine_corrections.md` Step 5.6 | 近績差但同場地同路程有入三甲 → 穩定性覆蓋為➖ |
| SIP-HV2 | 大幅配備變動升級 | `04_engine_corrections.md` Step 6 | ≥2項配備變動+Tier1/2騎師 → 練馬師訊號觸發✅ |
| SIP-HV3 | 臨門一腳缺失 | `06_rating_aggregation.md` Step 14.2B | 近4仗全入前5但0勝 → Top4排序降半級 |
| SIP-HV4 | 晨操/試閘/從化輔助維度 | `04_engine_corrections.md` Step 6.5 | 近績差+正面訓練訊號 → 配合沉睡專家可升半級 |
| SIP-HV5 | 潘頓溢價穩定性收緊 | `04_engine_corrections.md` Step 4 | 旗標+穩定性❌+段速非前三 → 封頂B+ |
| SIP-HV6 | 醫療事故自動作廢 | `05_forensic_eem.md` Step 12 | 流鼻血/足行單一因素觸發「上仗不可作準」+ 穩定性排除 |
| SIP-HV7 | HV 1650m 外疊風險擴展 | `04_engine_corrections.md` Step 6 | 檔 8-9 + 非前領型 → Top4排序降半級 |
| SIP-HV8 | 極密出練馬師信心 | `04_engine_corrections.md` Step 6 | 上賽≤14日+穩定性❌ → 練馬師訊號✅+封頂放寬至A- |
| SIP-HV9 | 巔峰久休豁免 | `04_engine_corrections.md` Step 6 | 35-56日久休+休前≥2勝/≥3三甲 → 久休❌降為➖ |
| SIP-HV10 | HV長途外檔放寬 | `04_engine_corrections.md` Step 6 | HV 1800m/2200m 致命死檔門檻從≥10放寬至≥12 |
| SIP-HV11 | 入位常客降級 | `06_rating_aggregation.md` Step 14.2B | 近4仗≥3仗前6但0三甲 → 穩定性➖+降半級 |
| SIP-HV12 | 下行軌跡懲罰 | `06_rating_aggregation.md` Step 14.2B | 近3仗連續下滑 → 穩定性降一級 |
| SIP-HV13 | 全場最輕磅中長途冷門 | `06_rating_aggregation.md` Step 14.2C | ≥1650m+全場最輕磅+近績差 → 冷門掃描觸發 |
| SIP-HV14 | D級馬懶分析根因修正 | `08_output_templates.md` + `06_rating_aggregation.md` | 禁止預判D級+D級≥300字+完整8維度矩陣+D+級別引入 |
| SIP-HV15 | S-品質閘門 | `06_rating_aggregation.md` Step 14.2 | S-需通過微調零降級+風險≤1+場地經驗三重閘門 |
| SIP-HV16 | HV B賽道慢步速偏差 | `10b_track_happy_valley.md` | B賽道+慢步速：檔1-5前置→情境✅；檔≥9後追→致命死檔 |
| SIP-HV17 | 谷草磅差分級化 | `06_rating_aggregation.md` Step 14.3 | 15-17lb降半級/18-20lb封頂A-/≥21lb封頂B+，含距離修正 |
| SIP-HV18 | B+升級掃描 | `06_rating_aggregation.md` Step 14.2E | B+滿足≥2正面條件→升A-；僅1項→冷門馬訊號 |
| ~~SIP-HV19~~ | ~~已移除~~ | — | 已移除（2026-03-26）：與「沙田轉跑馬地優勢」正面規則矛盾，SIP-HV15 S-品質閘門已足夠防範 |
| SIP-HV20 | D級冷門掃描擴展 | `06_rating_aggregation.md` Step 14.2C | 新增HV B賽道內欄+一線騎師反差配觸發因子 |
| SIP-HV21 | 排序風險折扣HV擴展 | `06_rating_aggregation.md` SIP-RR20 | 谷草磅差≥15lb→有效✅-0.5；輕磅加成+0.25 |
| SIP-HV22 | B賽道內欄超級加權 | `10b_track_happy_valley.md` | B賽道慢步速：檔1-5→排序✅+0.5；檔1-3→排序✅+1.0 |
| SIP-HV23 | HV長途後追內欄豁免 | `10b_track_happy_valley.md` | ≥1800m+檔1-3+後追型→情境從❌降為➖ |
| SIP-HV24 | 頂磅好檔補償 | `10b_track_happy_valley.md` | HV+≥133lb+檔1-3→SIP-RR17降級減半 |
| SIP-HV24b | 頂磅外檔加罰 | `10b_track_happy_valley.md` | HV+≥133lb+檔≥6→額外降半級；磅差≥15lb+檔≥8→封頂B+ |
| SIP-HV25 | HV短途磅差折扣 | `10b_track_happy_valley.md` | HV≤1200m磅差門檻+3lb；+檔1-3+Tier1/2騎師→級數❌降為➖ |
| SIP-HV26 | ST→HV首跑路程豁免 | `10b_track_happy_valley.md` | 首跑HV→➖偏正面+排序+0.5；+ST同程入三甲→路程✅；+檔≥10→➖ |

## 覆盤衍生 SIP（SIP-RR 系列，源自 Race Reflector 覆盤）

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RR15 | 質新馬進步曲線升格 | `04_engine_corrections.md` Step 5.7 | 質新馬≤5場近3仗連續改善≥3位 → 穩定性 ➖→✅ + Rising Star微調 |
| SIP-RR16 | 密出信心訊號擴展 | `04_engine_corrections.md` SIP-HV8 擴展 | HV8觸發條件擴展至質新馬穩定性➖但近仗有入三甲 |
| SIP-RR17 | 頂磅壓力 | `06_rating_aggregation.md` 14.2B | ≥133lb + ≥1400m + 加磅≥6lb → 降半級。ST7豁免不覆蓋 |
| SIP-RR18 | 大場最外檔後追致命 | `04_engine_corrections.md` Step 7 | 最外檔+≥12匹+後追型 → 致命死檔+封頂B+ |
| SIP-RR19 | 中長途輕磅冷門掃描 | `06_rating_aggregation.md` 14.2C | ≥1400m+中位數-5lb+檔≤6 → D/C升C-。+HV13 → 升B- |
| SIP-RR20 | 排名風險折扣 | `06_rating_aggregation.md` Step 14 | 同等第間頂磅/外檔/弱騎師 → 有效✅數折扣排序 |
| SIP-RR21 | 轉倉因素 | `07b_trainer_signals.md` 8.2f | 轉倉首戰+0.5輔助✅；Tier升級額外+0.25；輔助維度 |
| SIP-RR22 | 5-6歲突然贏馬回落 | `06_rating_aggregation.md` 14.2B | 5-6歲+上仗勝出+近10仗入三甲≤2次 → 降半級。豁免：近10仗入三甲≥4次（長期上名） |

## 覆盤衍生 SIP（SIP-ST30 系列，源自 2026-04-01 Sha Tin AWT 覆盤）

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-ST30 | AWT 呼吸道風險升級 | `10c_track_awt.md` + Step 7 | AWT+喘鳴近4仗≥1次→風險標記×2；≥2次→封頂B+ |
| SIP-ST31 | AWT S-/A+ 品質閘門加強 | `10c_track_awt.md` + SIP-HV15 擴展 | AWT需≥1勝或≥3入前四才可維持S-/A+；後追型S-需L400前20% |
| SIP-ST32 | AWT 老馬輕磅回師冷門升級 | `10c_track_awt.md` + Step 14.5 | ≥6歲+AWT紀錄+最輕磅+久休≥35日→升至B/B+ |
| SIP-ST33 | AWT 排序風險加強修正 | `10c_track_awt.md` + SIP-RR20 擴展 | 後追外檔/加磅/見習/醫療風險=AWT排序額外折扣，共用-1.5上限 |

## 資源模組

| 資源 | 位置 | 與 SIP 互動 |
|:---|:---|:---|
| AWT 跑道模組 | `10c_track_awt.md` | SIP-ST2, **SIP-ST30, SIP-ST31, SIP-ST32, SIP-ST33** |
| 沙田草地模組 | `10a_track_sha_tin_turf.md` | 場地偏差參考 |
| 跑馬地模組 | `10b_track_happy_valley.md` | SIP-HV16 場地偏差, SIP-HV22 內欄超級加權, SIP-HV23 長途後追豁免, SIP-HV24 頂磅補償 |
| 騎師戰術特徵 | `07c_jockey_profiles.md` | SIP-5、SIP-ST4 |
| 練馬師訊號框架 | `07a_signals_framework.md` | SIP-ST4 |
| 練馬師出擊訊號 | `07b_trainer_signals.md` | SIP-RR21 轉倉因素 |

---

> **維護規則：** 每次 Reflector 覆盤產出新 SIP 時，必須同步更新此索引。
> **最後更新：** 2026-04-01 (SIP-ST30~ST33 新增，AWT 覆盤衍生)
