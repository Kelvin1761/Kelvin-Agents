# HKJC 引擎重建審計（2026-11-09）

實驗記錄：[EXP-20261109-01](../experiments/EXP-20261109-01-hkjc-rebuild.md)。branch `claude-hkjc-rebuild-20261109`。

## 1. 重建咗乜

| 之前 | 之後 |
|---|---|
| `engine_core.py` 4,243 行、一個 class 145 個 method，計分同文字混埋 | `engine_core.py` 223 行（`analyze_horse`）＋ `_facts.py`（讀資料）、`_leaves.py`（leaf 分＋合成）、`_shadows.py`（shadow registry）、`_explain.py`（文字）、`summary.py`（白話重點） |
| `sys.path.append(features/)` → `draw`／`speed` 等變 top-level module，同一個 class 兩個身份 | `from .features.speed import SpeedScorer`（AGENTS.md 第 3 條） |
| shadow 名單散喺 orchestrator 兩個 set、validation、DEFAULT 清單 | `_shadows.SHADOW_PROFILES` 一個 registry，6 個仍然有 forward 測試 |
| 合成分靠三個過渡 shim 逐位還原舊式（7D 拆分、負磅搬家、同程舊級數重砌）＋三個加總次序 tuple | 每個維度 = Σ leaf × 份額；同程 = 固定原始分 ±(4／1.55) × 0.75 × 0.1428 |
| 引擎 package 約 8,600 行 | 約 7,740 行；另刪 19 個冇任何入口嘅 script（約 2,900 行） |

驗證方法同逐步結果見實驗記錄。總結：排名喺 434 場入面只有 7 場相鄰打和對調（頭三以外），KPI 不變。

## 2. 審計發現

### 已修（今次 commit）

| # | 發現 | 影響 | 修法 |
|---|---|---|---|
| A1 | `engine_core` 將 `features/` 目錄插上 `sys.path`（禁止做法） | 同一個 scorer 兩個 class 身份；arm patch 要特登 patch `engine_core.X` | package import |
| A2 | 7 個 shadow 已判決或由來冇喺預設清單（`race_shape_v2_legacy_hv`、`pre_race_draw_context_v1_generic` 10-27 已判；`consistency_context`、`incident_reliability_m/_r`、`race_shape_v3_hv(_t02)` 從未跑） | 每匹馬多計 2 個 shadow；報告印「Consistency Shadow: 未啟用」 | 剷走，連 HV V2 環境變數回退 |
| A3 | `validation.py` 驗緊三個唔存在嘅 health-slot profile | 死碼 | 剷走 |
| A4 | 三個合成 shim＋加總次序 tuple | 改一個權重要明白四層還原 | 直寫；7 場打和次序對調 |
| A5 | HKJC golden 冇抽 derived leaf，`race_shape` 靠 `draw_score` fallback | golden 量緊一個唔存在嘅模型 | 抽埋 derived；剷 fallback；重錄 golden |
| A6 | `_apply_health_only_v2`／`_apply_trainer_signal_v3` 係 `round(clip(x))` of 已 round 嘅值；3 個 method 冇 caller | 死碼 | 剷走 |
| A7 | `_consistency_shadow_detail` 其實係 80% 馬嘅 live 穩定性公式 | 名唔對實 | 改名 `_consistency_from_runs` |
| B1 | Logic 有、排位表冇嘅馬（建 Logic 後退出）令成場拒評 | 存檔 7/441 場冇分；live 靠排程重建 Logic 先避過 | 照排位表剔走，記入 `race_analysis.scratched_after_logic` |
| T1 | 「主要優勢」= 原始分最高 3 個 leaf，包括唔入模型嘅「資料完整度」 | 讀者以為資料完整係優勢 | 改用 summary：按 impact 排 |
| T2 | 「核心判讀」用原始尺揀最強／最弱維度 | 賽績線（原始中位 80）差唔多次次「最強」 | 用 impact |
| T3 | 「主要風險」只睇原始分 <55 嘅 leaf | 休 210 日、骨盆受傷記錄都寫「無重大風險標記」 | 加「👀 留意」：長休、官方傷患、醫療、換騎、初出 |
| T4 | 「今仗路程」將（勝-亞季-未上名）印成「冠/亞/季」，全敗唔亮 ⚠️ | 「1冠/2亞/1季」實為 1 勝 2 亞季 1 未上名 | 改正標籤同判定 |
| T5 | AWT 提示將（冠-亞-季-其餘）第四格當出賽次數 | 全勝／全上名嘅馬列做「未跑過」 | 出賽 = 四格總和 |
| T6 | 「季終時年屆八歲或以上」（年齡例行檢查）當傷患加 ⚠️ | 健康判讀誤導 | 顯示改「賽會年齡例行檢查」；**計分分類唔郁**（官方傷患 B1 forward 測試用緊） |

### 量過、冇問題

- 數據覆蓋（PIT 回放 5,429 匹）：騎師／練馬師中性 ≤0.4%；段速中性 25/26 季 29.9%（舊存檔）→ 26/27 季 2.5%；`track_going_score`、`trackwork_trend_score` 100% 中性係政策（場地冇數據；晨操 EXP-20261029-02 退出排名）。
- 排序：`official_ranking_score`（顯示尺 2 位小數）先、原始分後，等同按原始分排。
- 回放 vs live：PIT 回放首選同真實賽前快照 92/99 場一樣（10 月起）。

### 已知、未修（要你決定或者要實驗）

| # | 發現 | 點解唔即刻修 |
|---|---|---|
| K1 | `class_score` 唔睇評分／班次，只睇經驗（≥20 仗 +5.12、已建立 +4、季內上名） | 改即係改模型；官方評分差距 forward（EXP-20261029-30）30/60 進行中 |
| K2 | 賽績線「(強組比例…)」入面個「強」令弱組當 strong（EXP-20261018-08） | 修正兩次 REJECT，記錄做已知缺陷 |
| K3 | SIP-C 用實際負磅（扣減磅）計場中位，`weight_score` 用宣佈負磅 | SIP-C EXP-20261029-30 決定保留；改即係改模型 |
| K4 | 晨操維度權重 1%、恒定 60，條 bar 喺 dashboard 印紅色 −0.0 | 拆走會令初出／非初出常數唔同 → 排名改；交文字層處理 |
| K5 | 「資料完整度」（`confidence_score`）同「風險分」（其實越高越健康）仍然喺排名表 | 改欄名會郁 dashboard parser，下一輪文字改版一齊做 |
| K6 | 段速「海外賽績替代」唔過濾本地重複行；5,429 匹觸發 0 次，但 12 月國際賽（外地馬冇本地段速）先會用 | 冇語料可驗；建議國際賽前補測試 |
| K7 | `hkjc_reflector/scripts/review_auto_weighting.py`（2,581 行）同 `walk_forward_auto_backtest.py` 仍用 7D 時代公式（例如 `track_going` 0.25） | 每週 review 仍然 call 佢做 Reference 摘要；要另外重寫 |
| K8 | `incident_reliability`、`distance_suitability_v2` 兩個 shadow 喺預設清單但冇登記入 `FORWARD_TESTS` | 違反「forward 測試一律登記」；要你揀登記定撤 |

## 3. Win focus

答案：主 KPI 維持 Good。理由同數字見實驗記錄。每週 review 由 2026-11-11 起報首選 vs 熱門頭馬率同上名率。冇 ROI，因為 ROI 只可以經統一板發佈。
