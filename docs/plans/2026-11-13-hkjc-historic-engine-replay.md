# HKJC 歷史引擎回放計劃（2019–2026，約 6,000 場）

- **日期**：2026-11-13 ｜ **狀態**：進行中 ｜ **觸發**：EXP-20261113-09 —— 389 場引擎語料判唔到段速（Gold 跌幅 = 隨機 null），Kelvin 揀「歷史引擎回放」
- **目標**：喺 2019–2026 全部歷史場次跑**真引擎**（唔改評分 code），用夠大樣本判 Gold／Good；之後用同一份回放語料做段速 A/B 同 refit

## 1. 原則
1. **唔改引擎**：回放走 `hkjc_eval_harness run`／`score_race` 同一條路；只係砌輸入。
2. **每個欄位都要 as-of**：只用賽日之前嘅資料；「今日快照」類（現時評分、總獎金、tier 表、標準時間快照）一律唔用或者證明唔影響。
3. **先證明忠實先用**：喺有真 Logic 嘅 2026 場次（449 場）砌一份歷史版，逐維度、逐匹對真版；過唔到忠實度閘就唔准用回放做判決。
4. **大檔放外置碟**：生成嘅賽日資料夾寫 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/replay/`；TMPDIR 同樣。

## 2. 引擎實際讀乜（盤點結果）
引擎由 `Race_N_Logic.json` 嘅 `horses[n]` 同 `_data` 文字欄計分（格式敏感）；`score_race` 另外讀 `排位表.md`（評分、評分+/-、騎師、負磅、檔位、班次、賽道）、`賽績.md`（逐仗分段、負磅、名次）同 `Facts.md`（賽績線表）。
做法：**直接生成 `_data`（同 `create_hkjc_logic_skeleton.py` 一樣嘅字串格式）＋ 最小 `排位表.md`／`賽績.md`／`Facts.md`／`全日賽果.json`**，唔行要即時爬網嘅 `inject_hkjc_fact_anchors.py`。

## 3. 每個維度嘅歷史來源
| 維度（權重） | 欄位 | 歷史來源 | 覆蓋 |
|---|---|---|---|
| stability (0.088) | 近六場、`recent_6_detail`（名次＋輸距） | 馬匹頁逐仗 | 齊 |
| trainer_signal (0.236) | PIT 騎練評分、組合、同程、換騎、人馬歷史 | 賽果庫 2019 起（`_research_old_season_results` 440 日 + DB）；要將 `pit_backtest.load_all_rows` 擴展去舊季 | 齊（要改 loader，只係 harness） |
| sectional (0.129) | raw_l400、l400_last_run、finish_time_adj_level、l400_trend、engine_type、best_distance | 分段頁 + 馬匹頁 | **energy_trend（SpeedPRO 能量）冇** —— 6 個訊號少 1 個 |
| race_shape (0.274) | 檔位、跑道／賽道、走位 fit／PI、position_window 消耗、跑馬地 surface 分 | 賽果庫檔位、分段頁賽道、馬匹頁沿途走位 | **短評 XW 消耗冇** → trip 60；rail_draw 2024-09 前要由賽果庫自己砌 |
| horse_health (0.025) | medical_flags、相隔日數、體重趨勢 | 賽果庫競賽事件報告、馬匹頁體重 | 大致齊（事件報告關鍵字對短評關鍵字要核對） |
| distance_fit (0.02) | 同程紀錄、best_distance | 馬匹頁逐仗 | 齊 |
| form_line (0.080) | 賽績線（對手之後表現）、強度字串 | 分段頁＋賽果庫全部馬全部賽事，as-of 計 | 齊（字串格式要照抄，包括「中弱」含「強」嘅怪癖） |
| class_advantage (0.159) | 生涯標記、出賽數、季內紀錄、rating_gap | 馬匹頁逐仗評分 | 齊 |
| trackwork (0.010) | 常數 60 | — | 唔使 |

已知缺口：SpeedPRO 能量、短評 XW 消耗、海外（來港前）往績。缺口會令回放偏「保守」；忠實度閘會量出影響有幾大。

## 4. 步驟
1. **PIT 騎練**：`pit_backtest` 加舊季賽果（只喺 harness，唔郁 live）。
2. **歷史輸入生成器** `hkjc_history_replay_build.py`：每個賽日生成資料夾（`YYYY-MM-DD_ShaTin|HappyValley`）連 Logic／排位表／賽績／Facts／全日賽果。
3. **忠實度閘**（2026 重疊 449 場）：逐維度相關、raw 排序 Spearman、首選一致率、Gold／Good baseline 差。預先登記門檻：raw 場內 Spearman 中位數 ≥ 0.90、首選一致 ≥ 80%、baseline Gold／Good 同真版差 ≤ 2pp；唔過就逐欄搵原因，唔准調門檻。
4. **全量回放 baseline**：2020/21 起（第一季做騎練／標準 burn-in），約 5,200 場；記錄每場 dump-matrix。
5. **段速 A/B**：EXP-09 三個 arm 喺回放語料重跑（同一把尺 + 洗牌 null），預先登記判準：Gold、Good 都 ≥ 0，capture@5／頭二選有中 CI 下界 > 0。
6. **（之後）權重 refit**：dev／holdout 按季切，walk-forward。

## 5. 風險
- 回放唔等於 live：缺口欄位會令維度分佈唔同；所以 A/B 用回放語料對回放 baseline（同一份輸入），唔同 live 數字比。
- 格式敏感：生成器要有 golden 測試（拎 2026 真 Logic 嘅欄位逐字比對）。
- 工作量：預計 3–5 日；馬匹頁要先抓完（預計 2026-11-14 凌晨）。
