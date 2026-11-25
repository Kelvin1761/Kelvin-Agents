# EXP-20261126-22 — HKJC 三項跟進：退出馬計分、intraday 取消場、市場啱模型錯（頂尖組別）

- 日期：2026-11-26
- 平台：HKJC
- 觸發：Kelvin「仲有冇嘢可以改善…唔想做太多額外加潘頓分嘅嘢」→「go ahead on all 3」
- 判決：兩個管線修正上線（計分／shadow，唔郁排名）；快照時間冇缺口；頂尖組別扣分 T1 dev REJECT、T2 dev PASS 但 holdout REJECT

## 3. 賽前快照時間有冇缺口

最近 4 個有快照嘅 live 賽日（39 場；10 月嗰批快照已 offload 未計）：快照之後先退出而模型排頭四嘅只得 **1 匹**
（11-22 R3 滿利時，模型 #1，**入閘後**豎立被著令退出 —— 賽前冇可能知）；轉騎 2 次（模型 #6、#8）。
`lineup` 排程（每 30 分鐘掃名單、變咗就重跑）運作正常；成日有「掃唔到 N 場」（log 51 次），設計上唔當名單變咗。
→ **唔使加刷新**。

## 計分修正：退出馬唔再當模型揀咗（`unified_reflector_core`）

HKJC 賽果頁退出馬嗰行名次、馬號都係空白，`load_structured_results` 以前直接 skip，所以 `scratched_horse_numbers` 永遠空：
退出咗嘅模型首選照計落頭三（11-22 R3 記做 Pass；剔走之後頭三 = 包裝醒目、盈俊天下、遨遊首領）。
而家記低 `scratched_horse_names`（名次空白或 W 開頭；拉停／墮馬有起步唔算），`scratched_numbers()` 經預測檔馬名對返馬號，
覆盤同失手體檢共用。138 場有快照嘅 live 場次入面只影響 1 場 —— 罕見但係計分錯，會靜靜拉低紀錄。

**Sol 覆核（Codex review）後加**：平頭馬名次係「3 平頭馬」（舊格式 3DH），以前 `int()` 失敗成行丟走 ——
平頭入位嘅馬唔計入實際頭三（例：11-14 R7 實力股、小霸王平頭第三）；而家攞開頭數字。`WV／WV-A`、「退出」「---」當退出（有馬號就直接記馬號）；
馬名配對只接受唯一配對。資料根名次字串：空白 47、WV 20、WV-A 8、「N 平頭馬」16、PU 2、DNF 1、UR 1。

## 2. intraday 遇取消場停低（`hkjc_daily_schedule.live_results_prefix`＋`hkjc_reverse_bias_shadow.completed_prefix`）

EXP-20261120-01 已記：只取連續 R1..Rn，11-14 R6 取消之後成日 intraday reverse-bias shadow 停。
而家 live poller 已經放棄（`gave_up`）嘅場次跳過、繼續；仲等緊嘅場次照舊係終點。
Sol 覆核指出 `reverse_bias_shadow.completed_prefix` 自己都喺缺口停 —— 淨改 prefix 會令已跑完嘅 R7、R8 變返「未跑目標」
（賽後先做嘅賽前決定）。而家已跑 = 最後一場有賽果之前（含）有賽果嘅場次；目標只係最後一場之後。只影響 shadow。

## 1. 市場啱、模型錯（EXP-20261125-06 §6 HKJC 簡版嘅正式版）

`patches/hkjc_top_tail/hk_resid_screen.py`：base `scratch/j3-refine-20261123/e5_E5.jsonl`（live：表現數字＋初出馬練馬師＋返首本；
冇直路表現數字），v5 校準（計 N）逐季 walk-forward，賽日 bootstrap 600。兩窗 CI 都唔跨零嘅只有：

| 組別（場內 z） | dev | holdout |
|---|---|---|
| 狀態與穩定性 z≥1 | −2.6 [−3.5, −1.6] n=7,160 | −1.3 [−2.4, −0.2] n=4,221 |
| 評分與經驗 z≥1 | −2.3 [−3.2, −1.3] n=7,044 | −1.6 [−2.7, −0.5] n=4,095 |

（騎練 z≥1 冇偏差；Kelvin 唔要再加潘頓分，騎練唔郁。）

入分（`build_top_tail.py`，預先登記，Holm 家族 2；**holdout 殘差開工前已睇 → holdout 唔獨立**；
T2 同 EXP-20261115-05「班次優勢單參數扣分」同家族，嗰次 holdout −0.00023 跨零 REJECT —— 今次換 base／尺／形式重測，披露）：

| arm | β（逐季） | dev v5.2 | holdout v5.2 |
|---|---|---|---|
| T1 穩定性 z≥1 指標 | −1.47 … −0.86 | Δll −0.00011 [−0.00032, +0.00010] → **REJECT** | 冇開 |
| T2 評分與經驗 z≥1 指標 | −1.04 … −0.64 | Δll −0.00021 [−0.00043, −0.00002]、頭二 PL −0.0026 [−0.0042, −0.0013] → PASS | Δll −0.00018 [−0.00042, +0.00008]、Gold −0.12、Good −0.18 → **REJECT** |

結論：頂尖組別被高估係真（兩窗殘差一致、β 穩定），但入分改善細過把尺，同 11-15 一樣。live 唔改。
