# AU Horse Analyst — SIP 索引 (Systemic Improvement Proposals Index)

> **用途:** 集中追蹤所有 SIP 的定義位置、觸發條件摘要、及跨檔案引用。
> 避免 SIP 分散導致遺漏或重複定義。Reflector 覆盤時應參考此索引。

## SIP Quick Reference (Cross-Agent Alias Table)

> All sub-agents (Reflector, Validator, Compliance) reference SIPs by tag.
> If a SIP is renamed/merged/deprecated, update this table AND grep all files below:
> - `au_horse_race_reflector/SKILL.md`
> - `au_reflector_validator/SKILL.md`
> - `au_reflector_validator/resources/observation_log.md`
> - `au_compliance/SKILL.md`

| Current Tag | Status | Canonical Location | Notes |
|:--|:--|:--|:--|
| SIP-DA01 | 🟢 ACTIVE | Reflector + Validator (inline protocol) | 5-角度深度覆盤 |
| SIP-1 | 🟢 ACTIVE | `02c_track_and_gear.md` | 場地容錯 |
| SIP-2 | 🟢 ACTIVE | `02d_eem_pace.md` | EEM 場地係數 |
| SIP-3 | 🟢 ACTIVE | `02d_eem_pace.md` | 後追馬場地調節 |
| SIP-4 | 🟢 ACTIVE | `02c_track_and_gear.md` | Swamp Beast |
| SIP-5 | 🟢 ACTIVE | `02e_jockey_trainer.md` | 連勝動力 |
| SIP-6 | 🟢 ACTIVE | `02b_form_analysis.md` | 降班馬時效 |
| SIP-7 | 🟢 ACTIVE | `02b_form_analysis.md` | 見習騎師減磅 |
| SIP-8 | 🟢 ACTIVE | `02d_eem_pace.md` | 頂級後追豁免 |
| SIP-9 | 🟢 ACTIVE | `02f_synthesis.md` | S 級純度 |
| SIP-10 | 🟢 ACTIVE | `02e_jockey_trainer.md` | 進口馬寬容 |
| SIP-RR04 | 🔴 DEPRECATED | `04d_wet_track.md` | 由 SIP-RH02 取代 |
| SIP-AU09 | 🟡 OBSERVATION | Validator `observation_log.md` | 觀察中 |
| SIP-ST8 | 🟢 ACTIVE | Analyst `SKILL.md` | Anti-Laziness 錨定 |

---


---

## 引擎核心 SIP(定義於 `見上方 Alias Table 對應檔案`)

| SIP ID | 名稱 | Step | 摘要 | 定義位置 |
|:---|:---|:---|:---|:---|
| SIP-1 | 場地預測容錯 | Step 4 | 雙軌敏感度分析(預測 vs ±1級) | `02` Step 4 |
| SIP-2 | 場地 EEM 乘數 | Step 7 | 外疊懲罰按掛牌 ×0.6-1.6 調整 | `02` Step 7 |
| SIP-3 | 後追馬場地懲罰調節 | Step 7 | 後追馬 EEM ❌ 按場地等級分級 | `02` Step 7 |
| SIP-4 | 場地敏感度標籤 | Step 4 | 強制為每匹馬輸出場地敏感度標籤 | `02` Step 4 |
| SIP-5 | 動力因素 | Step 12 | 連勝動力獨立評估(3連勝=升一級) | `02` Step 12 |
| SIP-6 | 降班馬有效期 | Step 3 | 高班賽績時效限制(90/180日) | `02` Step 3 |
| SIP-7 | 見習騎師減磅優化 | Step 3 | ≥3kg 減磅 → 自動 ✅ Strong | `02` Step 3 |
| SIP-8 | 頂級後追豁免 | Step 7 | 全場最快末段 + ≥1200m + 非Crawl → 豁免外檔❌ | `02` Step 7 |
| SIP-9 | S級純度必備 | Step 14.E | S/S- 必須有段速或級數硬性✅ | `02` Step 14.E |
| SIP-10 | 進口馬寬容機制 | Step 13 | 頂級馬房進口馬首/次戰豁免封頂 | `02` Step 13 |

## 覆盤衍生 SIP(定義於 `見上方 Alias Table 對應檔案` 的 SIP-R/C 系列)

| SIP ID | 名稱 | Step | 摘要 | 定義位置 |
|:---|:---|:---|:---|:---|
| SIP-R14-2 | 頂級騎師檔位豁免 | Step 7/14.E | Tier 1 騎師 + 評分≥85 → 外檔降半級 | `02` Step 7 |
| SIP-R14-3 | 內檔被困風險 | Step 7 | 1-2檔 + 非領放 + ≥10匹 → -0.5級 | `02` Step 7 |
| SIP-R14-4 | Good場地Group前領下調 | Step 10 | Good 3-4 + G1/G2/G3/Listed → 前領紅利下調50% | `02` Step 10 |
| SIP-R14-5 | 中高班輕磅加成 | Step 3 | BM72+ + ≤54kg + ≤5檔 → +0.5升級 | `02` Step 3 |
| SIP-R14-6 | 超班馬距離容忍 | Step 2 | Rating≥105 → ±200m內不判❌ | `02` Step 2 |
| SIP-C14-1 | C欄大場懲罰分級 | Step 7 | C欄/外移欄 + ≥13匹 → 外檔懲罰×0.4 | `02` Step 7 |
| SIP-C14-2 | 卡士碾壓防崩潰 | Step 14.E | Rating差≥12 + ≥90 → 風險封頂2項 | `02` Step 14.E |
| SIP-C14-3 | 2YO 外檔懲罰減半 | Step 0.5 | 2歲馬外檔降級效果減半 | `02` Step 0.5 |
| SIP-C14-4 | 距離強制核實 | Step 2 | 雙源交叉比對距離數據 | `02` Step 2 |
| SIP-C14-6 | 步速互燒警報 | Step 10 | C欄 + ≥12匹 + ≥3前置引擎 → 步速上調 | `02` Step 10 |
| SIP-CH18-1 | 負重交叉核實協議 | Step 3 | 見習騎師claim雙源核實+紅旗觸發(≥2kg差) | `02` Step 3 |
| SIP-CH18-2 | 場地勝率門檻降級 | Step 4 | 場地勝率≤15%(≥5場)→強制❌+微調降半級 | `02` Step 4 |
| SIP-CH18-3 | 退出馬名單最終核實 | 數據收集 | 分析前強制鎖定出賽名單+早期數據警告 | `06a` |
| SIP-CH18-4 | 1000m標準彎道短途模組 | Step 0.2 | 慢閘降級+後追風險+前速加成+負重放大+見習陷阱 | `02` Step 0.2 |

## 場地/血統資源 SIP

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| — | 直線衝刺模組 | `02b_straight_sprint_engine.md` + `04c_straight_sprint.md` | 風向能量模型、跑道側方偏差、覆蓋規則(Leader's Graveyard 等) |

## 騎師 Profiles

| 資源 | 位置 | 摘要 |
|:---|:---|:---|
| Tier 分級 | `07_jockey_profiles.md` | 22 名騎師,4 Tier,與 SIP-R14-2 互動 |

## Rosehill 2026-03-21 覆盤衍生 SIP(SIP-RR 系列)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RR01 | 雙軌場地評級制度 | `02` Step 4 + `06` Part 3 | Good 4/Soft 5 並行雙評級+雙 Top 4 輸出 |
| SIP-RR02 | Soft 場地專家雷達 | `02` Step 4 | Soft WR≥40% 自動標籤+B+保底+場地維度升半核心 |
| SIP-RR03 | 大規模退出應急協議 | `06` Part 4 | Top 4 中≥2匹退出→迷你重新分析+重排 |
| SIP-RR04 | Soft 場地輕磅優勢加成 | `04d` Rule 4 | Soft 5+:≤54kg +0.5級 / ≥58kg -0.5級 / ≥59kg -1.0級 |
| SIP-RR05 | 頂級騎練聲望溢價交叉檢查 | `02` Step 11 | JMcD/Waller 加成按場地限制:Soft WR<30%→減半+上限+0.5級 |
| SIP-RR06 | G1 亞季軍自動保底 | `02` Step 13 | G1 Top 3 + Place≥75% → 後續賽事最低 A-、2yo 跨州減折 |
| SIP-RR07 | 爆冷潛力賽事預警 | `06` Part 4 | 爆冷指數≥6→降信心+擴大冷門掃描至$10+ |
| SIP-RR08 | Soft 場地分級排序 | `02` Step 4 | Soft 專家>受惠>免疫>未知>風險,禁止免疫排在專家前 |
| SIP-RR09 | Place Rate Soft 場折扣 | `02` Step 4 | Soft 0% + Place≥80% → 保底上限從 B+ 降至 B |
| SIP-RR10 | 精英練馬師跨州突襲訊號 | `02` Step 13 | T1 遠征+WR≥35% → 首次場地折扣取消+前領型重磅豁免 |
| SIP-RR11 | 急彎短途大場外檔處罰 | `02` Step 7 | 急彎≤1200m+≥14匹+後追型+檔≥10 → EEM 自動❌ |
| SIP-RR12 | 超高歷史衰減 | `02` Step 1 | Place Rate≥85% + First-up≥90天/距離首嘗 → 穩定指數✅降➖ + 保底降一檔 |
| SIP-RR13 | Caulfield Good 後追馬偏差降級 | `02` Step 7 | Caulfield+Good+Rail True+後追(≥6th) → EEM❌ + 微調降級 |
| SIP-RR14 | Good 地勝率封頂 | `02` Step 14.E | Good 3-4+樣本≥8場+勝率≤15% → 硬性封頂 B |
| SIP-RR15 | 距離全勝專精 | `02` Step 2 | 特定距離100%W+≥3場 → 裝備與距離✅ + 微調升半級 |
| SIP-RR16 | 冷門馬偏差自動升位 | `02` Step 14.F | 前領偏差冷門馬+Good+Rail True+≥B- → 替換Top4第4選 |

## Rosehill 2026-03-28 覆盤衍生 SIP(SIP-RF 系列)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RF01 | Soft 入位率雙軌篩選 | `02` Step 4 | Soft WR<20% 但 PR≥60%(樣本≥3)→ Tier 2.5 + 場地適性≥➖ + SIP-RR09 折扣豁免 |
| SIP-RF02 | 濕地未知風險封頂 | `02` Step 14.E | Soft 5+ 場地,Tier 4 (未知) 封頂 A-,Tier 5 (風險) 封頂 B+,賦予場地維度強制否決權 |

## Flemington 2026-03-28 覆盤衍生 SIP(SIP-FL 系列)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-FL01 | 內檔輕磅半核心乘數 | `02` Step 3 | Barrier 1-3 + ≥3kg 輕磅差 → EEM +半級 + 微調升半級。T1 騎師可升一級 |
| SIP-FL02 | S- 超配組合稅 | `02` Step 14.E | T1 練馬師 + T1 騎師 + 大熱門三重疊加 → 步速圖審查,陷入 Traffic 則封頂 A- |
| SIP-FL03 | Exotic 組合投注池建議 | `06` Part 3 | Top 4 評級密集(≤1 級差)→ Box Trifecta/First 4 組合投注建議 |
| SIP-FL04 | 2YO/初出馬配備懲罰軟化 | `02` Step 0.5 | 初出/2YO 馬嘅 Hoof Filler/Lugging Bit/Nose Roll 懲罰減半,精英馬房完全取消 |
| SIP-FL05 | 禁止練馬師主打猜測 | `02` Step 12 | 嚴禁推測同門馬「主打/副打」,每匹馬獨立評級 |
| SIP-FL06 | 濕地專家前領崩潰懲罰軟化 | `02` Step 10 | 有 Soft/Heavy 勝績≥1 場嘅前領馬:Heavy 崩潰懲罰減半;≥3 場+WR≥33%:完全取消 |

## Rosehill 2026-03-28 覆盤衍生 SIP(SIP-RH 系列 — Reflector Rosehill Horses)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RH01 | 省賽升班市場錨定保護 | `02` Step 3 | 省賽升班馬符合 ≥3/4 正面條件(場地專家+輕磅+好檔+升騎)→ Class Jump Penalty 取消。SP≤$5 → 禁止低於 B+ |
| SIP-RH02 | Soft 場超輕磅爆發器 | `02` Step 3 (SIP-R14-5 擴闊) | Soft 5+ 場地:≤56kg + ≤8 檔 → +0.5 級。場地專家條件同時成立 → +1.0 級。取代 SIP-RR04 同類規則 |
| SIP-RH03 | JMcD×Waller 品牌溢價封頂 (Brand Trap) | `02` Step 11 (SIP-RR05 修訂) | T1×T1 組合 + SP≤$3 + 後追 + ≥10匹 → 品牌溢價歸零 + `[BRAND TRAP]` 標記。場地專家豁免 |
| SIP-RH04 | 🐴⚡ 冷門馬強制升位協議 | `02` Step 14.F (SIP-RR16 強化) | 🐴⚡ 信號 + ≥3 正面條件 → 強制升至 B+ + 替換 Top 4 末位。與 SIP-RR16 合併並擴闊觸發範圍 |
| SIP-RH05 | NZ 遠征馬光環折扣 | `02` Step 13 (SIP-RR06 修訂) | NZ G1 加分封頂 +0.5 級。首次 AU 出賽 → 再減半至 +0.25 級。AU 出賽≥2場+入位 → 取消折扣 |
| SIP-RH06 | 上仗勝出單因子修正 | `02` Step 12 | 「上仗贏」升級需滿足同場/同距/同場地中 ≥2 項。不滿足 → 僅作 ➖。G2+ 低班上仗贏 → +0.25 降折 |

## Warwick Farm 2026-04-01 覆盤衍生 SIP(SIP-WF 系列)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-WF01 | 嚴格讀寫隔離 (Anti-Hallucination) | `01` Rule 2 | 嚴禁捏造 Career/Distance 等數據,無表列證據視為幻覺並終止執行 |
| SIP-WF02 | WF 急彎極速賽道鎖定 | `04b` (WF) | 確立WF為 1937m 狹長急彎,1000/1100m 嚴禁標示為直路賽,外檔 EEM ❌ |
| SIP-WF03 | 模版獎牌榜鎖定 + 邏輯錨點 | `06` 模版防呆 | 強制 [第三部分] 用 🥇/🥈 等圖標 List;CSV `P19_Rank=1` 對齊🥇第一選 |

## Gosford 2026-04-02 覆盤衍生 SIP(SIP-GF 系列)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-GF02 | Good 地泥地馬護體 | `02` Step 4 | Good 地勝率≤15%但有降班/T1騎師 → 降級減半,D 級保底 C-。樣本≥10+PR≤20% 失效 |

## Randwick 2026-04-04 覆盤衍生 SIP(SIP-RR17 系列)

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RR17 | Soft 7+ 爛地負磅與動能重新校準 | `02` Step 14.E + `04d` Rule 4/7/8 | 三項子修改:(1) ≥59kg 在 Soft 7+/Heavy 處罰從 -1.0 加重至 -1.5(Soft 專家豁免後仍 -1.0,卡士碾壓最多減至 -0.5);(2) 連勝動力馬在 Soft 7+/Heavy 最低保底 B+;(3) S/S+ 級馬若為全場最重(≥59kg)且 Soft 7+/Heavy,強制封頂 A+ |

---

> **維護規則:** 每次 Reflector 覆盤產出新 SIP 時,必須同步更新此索引。
