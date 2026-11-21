# EXP-20261120-87 預先登記：Lpos 歷史回填測試（08-05 → 11-05）

> 寫喺任何回填數據之前（原本以 EXP-20261120-60 喺分支 `claude-au-mobile-backfill-20261120` `2e5afb6a` commit；同 NBA 撞號，改為 -87，內容不變）。結果另寫 `EXP-20261120-87-au-lpos-historical-backfill-results.md`。

- **提出**：用戶 2026-11-20「好，回填」—— Lpos forward（EXP-20261116-20）要 2,500 場，照現時速度要到約 1 月中；
  用歷史場次即刻有足夠功效。
- **同 forward 嘅關係**：forward 照跑、規格唔郁。今次係**另一個獨立判決**，用 forward 開始之前嘅場次。

## 數據

- 範圍：賽日 **2026-08-05 → 2026-11-05**（93 日、我哋語料 3,974 場）。
  **唔包 11-06 之後**：EXP-20261116-19／-22 用咗 11-08 → 11-15 嘅 370 版嚟定 `Lpos` 常數同 0.10 權重，11-06／-07 夾喺中間，一齊剔走。
- 來源：`sportsbetform.com.au/mobile/{eventId}/1/`，event ID 由 `AllRacing/{day}`；**只抓我哋有分析（有 `Race_N_Logic.json`）嘅場次**。
- 抓取規矩同每日 job 一樣（Kelvin 定）：每版隔 ≥ 25 秒、非 200／逾時／內容唔似 Speed 分頁即停、唔重試、唔用繞過偵測手法、
  只喺 03:00–09:00 開工。回填排喺每日 04:30 forward 抓取**之後**、同一個 job 入面；**09:00 一到即停**，每晚最多 500 版。
  預計約 8 晚。
- 儲存：同 forward 一樣（`<AU 資料根>/AU_Mobile_Sectionals/<賽日>/`）；每日另存 `_events.json`（AllRacing 場次表）做完整度證據。
- 賽後抓係安全：EXP-19 證實舊頁固定喺賽事日期（370 版 0 行 ≥ 賽日）；特徵只用日期 < 今仗嘅行。每版會再查一次，見到 ≥ 賽日嘅行就記低並剔走嗰場。

## 特徵、分數、判決（同 EXP-20261116-20 一模一樣，凍結）

- `Lpos` 定義、常數（−1.1008497873571432、−0.10976351609298357）、`Lpos.avg4`、冇值 = 場內 z 0。
- baseline = 儲存 Logic 特徵 → `exact_score`；candidate = baseline + **0.10** × 場內 pstdev(baseline) × 場內 z(`Lpos.avg4`)。
- 母體：有手機版、有 Logic、賽果齊（頭三同頭馬）；馬只計對到賽果嘅。
- 判決：`evaluate_full_record(domain="au", mode="fixed_rule")`，ranking `top3_capture_at5`／`ndcg_at5`／`top5_pairwise_auc`。
  **全部合資格場次判一次並凍結**（唔係頭 2,500 場）。另報短途 ≤1200m／>1200m 嘅 Gold／Good（描述）。
- **觸發**：回填完成（93 日全部抓齊，或者剩低嘅場次連續 3 晚抓唔到）先判；之前 status 只寫場數同覆蓋率，**唔睇賽果指標**。
  夠數由 `au_forward_tracker` 推 primary Telegram。
- PRIMARY_WIN／RANKING_WIN → 交 Kelvin 決定係咪上線（另一個改動，連 golden／data_contract）。其他 → 唔上線。
- 同 forward（EXP-20261116-20）係同一個假設兩個獨立樣本：**上線要兩個都唔係 REJECT**；任何一個 primary_regression → 唔上線。

## 已知限制（寫低，唔係藉口）

- `Lpos` 兩個常數係 EXP-22 用 11-08 → 11-15 頁入面「11-06 前」嘅往績行 fit（Lr 對 800m 位置），嗰批行包括今次範圍入面嘅賽事。
  常數只描述「末段速度同位置」嘅關係，冇用任何今仗名次；當輕微、已知嘅重用。
- 08-05 → 11-05 呢個窗已經用過好多次（其他候選），但 `Lpos` 從來冇喺呢度量過。

## 唔准做嘅嘢

改權重、常數、avg 窗、母體範圍；未完成就睇賽果；判完之後換窗口再判。
