# EXP-20261113-23 預先登記：新計分組件（騎練情境率、試閘覆蓋、長途段速、短直路前置）（睇任何結果之前寫）

觸發：Kelvin 2026-11-13：「有冇新嘅計分組件可以加？go ahead and test all」＋「有啲馬場直路短，應唔應該加分落預計放頭馬？」

## 語料、判決

- BASE = `FINAL.json`（`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/`），即係 main `1c33b058` 嘅評分
  （EXP-20261113-22 用新 code 重評，對 `BASE − proven_class` 最大差 0.0001）。
- 判決窗 2026-08-05 起（3,736 場）。v3 `evaluate_full_record` `fixed_rule`，ranking metric = top3 capture@5、NDCG@5、top5 AUC，賽日 bootstrap 2000；
  分層同 EXP-20261113-21（馬群、地況、首選 SP、路程、首選跑法）。
- **上線條件**：PRIMARY_WIN 或 RANKING_WIN，而且全部 arm 做一個 family **Holm** 調整後 p < 0.05，冇分層 CI 全負。其餘 REJECT。
  所有數值（K、門檻、加分）喺睇結果之前定死，冇搜索。改 leaf 資訊量嘅 arm 只做 §8 fixed arm（AU walk-forward refit 工具未整理），
  唔過唔代表特徵冇用。

## Arm

### A. 騎練情境率（point-in-time）

來源：`AU_Sportsbet_People_Snapshots.jsonl`（2026-08-09 起，21,915 個快照）。每匹馬用**賽日之前**（`captured_at` 日期 < 賽日）
最近一個騎師／練馬師快照；冇就唔郁。人名 → id 用 `AU_Sportsbet_People_Cache.json`（HTML unescape 後比對）。
只改用緊「LY 統一率」嗰條路嘅馬（離線重算 LY 分同 dump 差 < 0.01 先算）；情境率收縮去本人 LY 率，K = 100：
`r = (情境勝／上名 + 100 × r_LY) ÷ (情境場數 + 100)`，再用現行尺（騎師勝率 60 + 247 ×（r − 0.1271）；練馬師上名率 60 + 140 ×（r − 0.3673））。

| arm | 情境 |
|---|---|
| J1 近期狀態 | 騎師＋練馬師 `Last 100` |
| J2 地況 | 騎師＋練馬師 `Track Conditions / Last 12 Months` 對今場地況（Good／Soft／Heavy；Firm 當 Good） |
| J3 路程 | 騎師＋練馬師 `Distance / Last 12 Months` 對今場路程組 |
| J4 練馬師休後 | 練馬師 `Spells / Last 12 Months` 對匹馬今仗係休後第一／二／三仗（其他唔郁） |

### B. 試閘覆蓋擴闊

| T3 | 試閘 L600 分取消「正式賽 ≥6 場唔計」門檻，保留全部試閘（研究開關重 dump） |

### C. 長途段速（Kelvin：段速係核心）

| S1 | 路程 > 1600m：速度考驗背景個 leaf 由 L600 環境分換做段速分（段速分 = 60 冇證據就照用 L600） |
| S2 | 路程 > 1600m：速度考驗背景 = L600 環境分同段速分平均（段速分 = 60 就照用 L600） |

### D. 短直路 × 預計放頭

「短直路」= 直路長度低過語料場次嘅中位數（`au_track_geometry.json`，只用幾何，冇用賽果定門檻）；「預計放頭」=
Sportsbet 跑法標籤 `前領` 或 `跟前`（`running_style_line`，賽前）。冇幾何嘅場地唔郁。

| L1 | 短直路 ＋ 前領／跟前 → 綜合分 +1.0 |
| L2 | 短直路 ＋ 前領／跟前 → 綜合分 +2.0 |
| L3 | 短直路 ＋ 只限前領 → 綜合分 +2.0 |

背景：EXP-20260902-01（928 場，只量 AUC 冇 arm）話「跑法 × 直路」加咗反而差；今次語料大 4 倍、用正式 arm。

## 唔測

競賽主任報告：EXP-20261107-01 已量（受阻後冇反彈；大外冇遮擋 +5.79pp 但市場已計入）；
Sportsbet 年代冇評語，要先寫 RA PDF 抓取先有 2026-08 起嘅 point-in-time 數據 —— 工程項目，唔喺呢個實驗。

## 記錄

結果：`EXP-20261113-23-au-new-components-results.md`；判決 JSON：`EXP-20261113-23-evidence/`。冇過嘅 arm 唔會 commit model code。
