# EXP-20261025-08: HKJC 同程最佳時間（對全場）＋最快 L400，預先登記

- **登記日期**：2026-10-25，喺跑任何 arm 之前 commit 同 push
- **平台**：HKJC，**Stage 4 v3 `fixed_rule`**（分段同 K 都固定，冇 fit）
- **觸發**：Kelvin 覺得「全場馬同程最佳時間同埋最快末段」呢部分睇得太少。2026-10-25 做咗篩選（只係篩選，唔係判決），結果寫喺下面「篩選證據」。
- **前置修正**：賽果庫 2026-05-13 之後嘅 rows 原本冇完成時間（0%），已經同日以 §7 正確性修正補返，見 `build_comprehensive_stats.result_row`。冇呢個修正，同程時間喺語料後半段全部會係空。

## 篩選證據（同一語料，所以有偏差，見「已知偏差」）

| 特徵 | 覆蓋 | 場內 AUC | 對模型 ρ | 增量 ΔΔLL [95% CI] | 5 fold |
|---|---:|---:|---:|---|---|
| 同程最佳時間（扣場地 variant） | 75% | 0.605 | +0.29 | +0.0081 [+0.0001, +0.0160] | 5 正 |
| 近 6 仗最快末段 | 93% | 0.584 | +0.30 | +0.0010 [+0.0002, +0.0018] | 4 正 1 負 |
| 上仗 L400（現行） | 93% | 0.593 | +0.33 | — | — |

- 方法同 EXP-20261016-51 一樣：場內 conditional logit，模型分係數唔固定，60/40 日期切分，364 場 harness replay。
- 賽果庫 1,510 場：同程時間全場最快嗰匹上名率 37.5%，期望 24.6%。同全場最快差距同上名率：0–0.3s 34.0%、0.3–0.6s 28.5%、0.6–1.0s 23.8%、1.0–1.5s 18.4%、≥1.5s 14.2%。
- 對市場（log odds）冇增量（+0.0001），即係市場已經食咗呢個資訊，但模型未有。

## 候選（固定，唔准改）

### Arm A：同程最佳時間，K ∈ {3, 6, 9}

- **輸入**：`build_comprehensive_stats.load_all_completed_rows()` 每匹馬（`horse_code`）喺賽日**之前**、同場地、同跑道（草地／全天候）、同路程嘅完成時間，再扣走嗰日嘅場地 variant：
  - 標準 = 嗰場賽日之前同（場地、跑道、路程、班次）頭馬時間嘅中位數；要 ≥8 場，唔夠就退返用同路程（唔分班次）。
  - variant（日、場地、跑道）= 當日每場頭馬時間減標準，再取中位數。
  - adj = 完成時間 − variant；b = 每匹馬 adj 嘅最細值。
- **gap** = b − 全場 b 最細值（秒）。全場有 b 嘅馬少過 3 匹 → 成場唔加減；冇同程紀錄嘅馬 → 0。
- **分段**（加落 `speed_score`，clip 0–100）：

| gap（秒） | 加減 |
|---|---:|
| < 0.3 | +K |
| 0.3 ～ 0.6 | +K/2 |
| 0.6 ～ 1.0 | 0 |
| 1.0 ～ 1.5 | −K/2 |
| ≥ 1.5 | −K |

- **實作**：`docs/experiments/patches/hkjc_arm_same_course_best_time.py`，用 `WC_SAME_COURSE_K=3|6|9` 揀 K。
- **K 嘅理由**：e1_best 家族係 {2, 4, 6}；呢個訊號篩選時強過 e1_best（ΔΔLL 相若，但 5/5 fold），所以家族中位數揀高一級（6）。K 係跑之前定嘅，唔係由結果揀。

### Arm B：L400 由「上仗」改做「近 6 仗最快」（Kelvin 建議）

- `raw_l400` 換成 Facts「完整賽績檔案」近 6 仗 L400 嘅最細值。SpeedScorer 門檻同權重完全唔變；冇 L400 就唔郁。
- **實作**：`docs/experiments/patches/hkjc_arm_best_l400.py`。
- **登記預期**：篩選顯示佢喺模型之上增量好細，而且單獨 AUC 低過上仗 L400。登記佢係為咗用把尺答 Kelvin 個問題，唔係因為預期會贏。

### 家族同 Holm

4 個 arm（A3、A6、A9、B）× 6 個指標 = 24 次比較，做 Holm 調整。

## 接線證明（已做，2026-10-19 單日 smoke）

- A（K=6）：10 場有 9 場排序郁咗，1 場頭 4 變咗 → 接通。
- B：第一版 parser 冇接通（0 場郁，表頭前面有空行）。修好之後逐匹抽查：2026-10-19 R3 4 號馬 23.64 → 23.57。全紀錄 run 會報 `races_with_ranking_change`，如果係 0 = 冇接通，唔准當結果。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
python3 $H run --until 2026-10-21 --out base.jsonl
for K in 3 6 9; do WC_SAME_COURSE_K=$K python3 $H run --until 2026-10-21 \
  --arm $P/hkjc_arm_same_course_best_time.py --out a$K.jsonl; done
python3 $H run --until 2026-10-21 --arm $P/hkjc_arm_best_l400.py --out b.jsonl
for f in a3 a6 a9 b; do python3 $H compare base.jsonl $f.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```

- **全紀錄窗口**：由語料開始到 **2026-10-21**；用登記 commit 嘅 main。
- **判決**：`evaluate_full_record`，跟 v3 次序；Holm 調整之後先可以報 WIN。
- **分層（只報，唔可以用嚟救）**：沙田／跑馬地、馬匹數、路程段、首選 SP 五段。任何場地 Gold 或 Good 點估計 < 0 → ⚠️。

## §6 功效前置（量度之前寫低）

閘門 MDE 沿用 EXP-20261016-14 同語料嘅 CI 半寬：Gold ±1.96pp、Good ±1.76pp、top3_capture@5 ±1.51pp、NDCG@5 ±0.0101、competitive_recall@5 ±0.0101、平均名次 ±0.049。所有 arm 全部 |Δ| < MDE → `UNRESOLVABLE`。

## Leakage audit（PASS，附條件）

- 只用賽日**之前**嘅賽果行（`day < race_date`），當日同未來嘅行一律唔入。
- variant 用嗰個過往賽日自己所有場次嘅頭馬時間。佢只會套用喺過往賽事，而嗰日喺今仗之前已經完全知道。
- 標準係 expanding window，只用嗰場之前嘅賽日。
- 冇用賠率、今仗沿途位或者今仗賽果。
- Arm B：Facts「完整賽績檔案」係賽前檔案，L400 只嚟自過往賽事。
- 條件：賽果庫 2026-05-13 之後嘅完成時間係今日由 `full_day_results.json` 補返。嗰啲係官方賽果，都係喺目標賽日之前已經公佈。

## 已知偏差

篩選**已經睇過**同一份語料，分段門檻（0.3／0.6／1.0／1.5）係睇咗 gap 對上名率嗰張表先揀嘅。所以全紀錄結果只算篩選，WIN 一定要過 forward 先可以上線。

## Forward 確認（只開一次）

- **窗口**：2026-10-25 起嘅 HKJC 賽日（2026-10-25 沙田嗰日篩選時未有賽果），累積 ≥ 60 場先開。
- **K**：全紀錄有 WIN 嘅 A arm 入面取 K 中位數，唔准 argmax。B 有 WIN 就獨立做 forward。冇 WIN → 唔開 forward，記 REJECT／UNRESOLVABLE。
- **判決（寫死）**：Gold Δ ≥ 0、Good Δ ≥ 0、NDCG@5 Δ ≥ 0 → 可以提交上線；任何一項 < 0 → REJECT。唔准換指標、換窗口或者重開。
- 上線之前，live 要喺 `score_race` 由賽果庫計 `same_course_best_gap`，唔可以靠 arm 注入，而且要寫入 Logic `_data`。

## 結果

見 `EXP-20261025-08-hkjc-same-course-best-time-results.md`：**4 個 arm 全部 REJECT**（Holm 後冇 WIN），冇開 forward。
