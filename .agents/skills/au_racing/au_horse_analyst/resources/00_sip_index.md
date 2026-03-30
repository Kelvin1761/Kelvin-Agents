# AU Horse Analyst — SIP 索引 (Systemic Improvement Proposals Index)

> **用途：** 集中追蹤所有 SIP 的定義位置、觸發條件摘要、及跨檔案引用。
> 避免 SIP 分散導致遺漏或重複定義。Reflector 覆盤時應參考此索引。

---

## 引擎核心 SIP（定義於 `02_algorithmic_engine.md`）

| SIP ID | 名稱 | Step | 摘要 | 定義位置 |
|:---|:---|:---|:---|:---|
| SIP-1 | 場地預測容錯 | Step 4 | 雙軌敏感度分析（預測 vs ±1級） | `02` Step 4 |
| SIP-2 | 場地 EEM 乘數 | Step 7 | 外疊懲罰按掛牌 ×0.6-1.6 調整 | `02` Step 7 |
| SIP-3 | 後追馬場地懲罰調節 | Step 7 | 後追馬 EEM ❌ 按場地等級分級 | `02` Step 7 |
| SIP-4 | 場地敏感度標籤 | Step 4 | 強制為每匹馬輸出場地敏感度標籤 | `02` Step 4 |
| SIP-5 | 動力因素 | Step 12 | 連勝動力獨立評估（3連勝=升一級） | `02` Step 12 |
| SIP-6 | 降班馬有效期 | Step 3 | 高班賽績時效限制（90/180日） | `02` Step 3 |
| SIP-7 | 見習騎師減磅優化 | Step 3 | ≥3kg 減磅 → 自動 ✅ Strong | `02` Step 3 |
| SIP-8 | 頂級後追豁免 | Step 7 | 全場最快末段 + ≥1200m + 非Crawl → 豁免外檔❌ | `02` Step 7 |
| SIP-9 | S級純度必備 | Step 14.E | S/S- 必須有段速或級數硬性✅ | `02` Step 14.E |
| SIP-10 | 進口馬寬容機制 | Step 13 | 頂級馬房進口馬首/次戰豁免封頂 | `02` Step 13 |

## 覆盤衍生 SIP（定義於 `02_algorithmic_engine.md` 的 SIP-R/C 系列）

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
| — | 直線衝刺模組 | `02b_straight_sprint_engine.md` + `04c_straight_sprint.md` | 風向能量模型、跑道側方偏差、覆蓋規則（Leader's Graveyard 等） |

## 騎師 Profiles

| 資源 | 位置 | 摘要 |
|:---|:---|:---|
| Tier 分級 | `07_jockey_profiles.md` | 22 名騎師，4 Tier，與 SIP-R14-2 互動 |

## Rosehill 2026-03-21 覆盤衍生 SIP（SIP-RR 系列）

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RR01 | 雙軌場地評級制度 | `02` Step 4 + `06` Part 3 | Good 4/Soft 5 並行雙評級+雙 Top 4 輸出 |
| SIP-RR02 | Soft 場地專家雷達 | `02` Step 4 | Soft WR≥40% 自動標籤+B+保底+場地維度升半核心 |
| SIP-RR03 | 大規模退出應急協議 | `06` Part 4 | Top 4 中≥2匹退出→迷你重新分析+重排 |
| SIP-RR04 | Soft 場地輕磅優勢加成 | `04d` Rule 4 | Soft 5+：≤54kg +0.5級 / ≥58kg -0.5級 / ≥59kg -1.0級 |
| SIP-RR05 | 頂級騎練聲望溢價交叉檢查 | `02` Step 11 | JMcD/Waller 加成按場地限制：Soft WR<30%→減半+上限+0.5級 |
| SIP-RR06 | G1 亞季軍自動保底 | `02` Step 13 | G1 Top 3 + Place≥75% → 後續賽事最低 A-、2yo 跨州減折 |
| SIP-RR07 | 爆冷潛力賽事預警 | `06` Part 4 | 爆冷指數≥6→降信心+擴大冷門掃描至$10+ |
| SIP-RR08 | Soft 場地分級排序 | `02` Step 4 | Soft 專家>受惠>免疫>未知>風險，禁止免疫排在專家前 |
| SIP-RR09 | Place Rate Soft 場折扣 | `02` Step 4 | Soft 0% + Place≥80% → 保底上限從 B+ 降至 B |
| SIP-RR10 | 精英練馬師跨州突襲訊號 | `02` Step 13 | T1 遠征+WR≥35% → 首次場地折扣取消+前領型重磅豁免 |
| SIP-RR11 | 急彎短途大場外檔處罰 | `02` Step 7 | 急彎≤1200m+≥14匹+後追型+檔≥10 → EEM 自動❌ |
| SIP-RR12 | 超高歷史衰減 | `02` Step 1 | Place Rate≥85% + First-up≥90天/距離首嘗 → 穩定指數✅降➖ + 保底降一檔 |
| SIP-RR13 | Caulfield Good 後追馬偏差降級 | `02` Step 7 | Caulfield+Good+Rail True+後追(≥6th) → EEM❌ + 微調降級 |
| SIP-RR14 | Good 地勝率封頂 | `02` Step 14.E | Good 3-4+樣本≥8場+勝率≤15% → 硬性封頂 B |
| SIP-RR15 | 距離全勝專精 | `02` Step 2 | 特定距離100%W+≥3場 → 裝備與距離✅ + 微調升半級 |
| SIP-RR16 | 冷門馬偏差自動升位 | `02` Step 14.F | 前領偏差冷門馬+Good+Rail True+≥B- → 替換Top4第4選 |

## Rosehill 2026-03-28 覆盤衍生 SIP（SIP-RF 系列）

| SIP ID | 名稱 | 定義位置 | 摘要 |
|:---|:---|:---|:---|
| SIP-RF01 | Soft 入位率雙軌篩選 | `02` Step 4 | Soft WR<20% 但 PR≥60%（樣本≥3）→ Tier 2.5 + 場地適性≥➖ + SIP-RR09 折扣豁免 |
| SIP-RF02 | 濕地未知風險封頂 | `02` Step 14.E | Soft 5+ 場地，Tier 4 (未知) 封頂 A-，Tier 5 (風險) 封頂 B+，賦予場地維度強制否決權 |

---

> **維護規則：** 每次 Reflector 覆盤產出新 SIP 時，必須同步更新此索引。
