# EXP-20261012-34 AU：jockey 冇記錄預設值、見習減磅（正式路徑），Platinum Card production 核實

- **日期**：2026-10-12
- **判決尺**：Stage 4 v3 `walk_forward_oos`，經正式 artifact 路徑。
  - 用同 EXP-20261012-33 一樣嘅 manifest：2,295 場，provenance 規則係來源 ≤ 開跑日 12:00，暖身期 300 場／14 日。
  - 披露同 EXP-33 一樣：兩個家族都喺描述性量度之後先登記。
- **Harness**：scratchpad `harness/official_family.py`（arm `jky_noev`、`claim`）。

## 1. jockey「冇記錄」預設值（之前 v2 邊緣 RANKING_WIN，EXP-20261010-01 B7）

- 每個賽日用之前賽日，喺 {60, 55, 50, 46.86, 45, 40} 入面揀預設值（60 = 現狀）。
- 最終語料入面受影響嘅有 371 匹（1.58%）。
- **判決：REJECT（ranking_evidence_too_weak）**：
  - Gold、Good、top3_capture、top5_auc 全部 Δ = 0.00。
  - ndcg Δ ≈ −0.00。
  - 候選 ability 有變（唔係 `identical_predictions`），但冇郁到任何結果。
- **結論**：v2 嗰次邊緣過閘係噪音。46.86 唔發佈（本身只喺舊 worktree，從未上線）。

## 2. 見習減磅（`(a-2)` 等，頁面有但 `parse_overview` 剷咗）

描述性殘差（控制模型名次後，20,262 匹配到）：

| 減磅 | 匹數 | 殘差 | CI |
|---|---:|---:|---|
| 冇減磅 | 15,468 | +0.64pp | [+0.29, +0.97] |
| a1–1.5 | 1,496 | −0.86pp | [−2.95, +1.31] |
| a2–2.5 | 1,698 | −3.22pp | [−5.06, −1.44] |
| a3+ | 1,600 | −1.92pp | [−3.91, +0.14] |

正式路徑（殘差表，分層到距離段，c ∈ {0, 10, 20, 40}）：

- **判決：UNRESOLVABLE（all_registered_ranking_metrics_noninformative）**，即係 §6：三個排序指標嘅部件預算全部細過 MDE。
- primary：Gold +0.04 [−0.27, +0.39]、Good +0.09 [−0.25, +0.39]。
- 冇 cohort 傷害。

**結論**：

- 個訊號係真嘅：見習騎師嘅馬表現差過模型預期，雖然佢哋輕咗磅。
- 但落到排名嘅影響細過閘門判得到嘅最細效應。冇可量度收益，所以**唔接入 production**。
- 抽取層保留現狀：`parse_overview` 照剷 claim。如果將來要用，喺 `claw_sportsbet_form.parse_overview` 保留 `(a-N)` 就得。

## 3. Platinum Card：production code 核實

- 用 production 排程 worktree（`/Users/imac/wongchoi-scheduler` @ `16c028ab`）嘅 code，喺 2026-10-12 Tamworth 嘅 scratch 副本重新生成 Facts／Logic 同評分。

| 項目 | 修正前（live 10-12 12:08） | production 現行 code |
|---|---:|---:|
| Platinum Card ability | 64.85（第 2；首選退出後 = 實際首選） | **62.2（第 3；退出後排 Boa Vista 之後）** |
| form | 60（當冇證據） | 53.3（官方 Last 10：第 10） |
| performance_quality | 69.8（虛構頭馬） | 61.9 |
| pace_figure | 84.1 | 84.1（保留：全靠試閘嘅 681 匹，≥70 分 +10.5pp、<50 分 −12.3pp） |
| Smashit Scone 900m | 標「試閘」 | 標「正式」5/8 |
