# EXP-20260826-02 — pace_perf 權重重新驗證：現值已經係最優，唔改

**狀態：REJECT（三個方向、三個語料、四種量法都唔支持郁佢）**
**日期：** 2026-08-26 ・ **平台：** AU ・ **commit：** 1dbc4b5e

## 起因

Kelvin 覆核 2026-08-22 Randwick R1 / R2 / R3 / R9 之後嘅假設：「啲問題全部指向
pace_perf」。R1 Gunroom（$31，跑第 9）同 R3 Captain Fenkel（PF 90.07，跑 14/15）
都係俾 pace_perf 推上頭位。

`MATRIX_WEIGHTS` 上次設定係 2026-08-22（edc4c2c0），而且係 race_shape 退場之後
**按比例歸一**，唔係量出嚟嘅。之後仲有三個影響 leaf 分佈嘅改動落咗地
（08-23 名次修正改咗 65.9% form 行、08-23 濕地 overlay、08-25 高班實績證明）。
所以重新 fit 本身係到期嘅 —— 代碼註釋本身都寫住「等乾淨語料儲夠三個月要重驗」。

## 先修正一個量度錯誤：pooled AUC 呃咗人

`pace_figure_score` 全樣本場內 AUC 0.5392，睇落好弱。但按**場內 PF 覆蓋**分層：

| 場內 PF 覆蓋 | 場次 | PF AUC | form AUC |
|---|---:|---:|---:|
| 0–25% | 480 (29.9%) | **0.5000** | 0.6174 |
| 50–75% | 34 | 0.5869 | 0.6051 |
| 75–100% | 1082 (67.4%) | **0.5558** | 0.5957 |

AUC 啱啱好 0.5000 = 全部配對平手 = 成場都係 60。呢 480 場**全部係 2026-05 之前
嘅舊歸檔**（2025-08 至 2026-04 每個月 100% 死；2026-06 之後 0.0%–1.0%）——
嗰批場次抽取嗰陣段速抽取仲未存在。即係話：

* **PF 覆蓋唔係一個 live 問題**，2026-06 之後接近 100%。
* pooled 0.5392 係「死咗嘅 30%」溝「健康嘅 67%」嘅平均，**低估咗**個 leaf。
* 一個場內常數維度對排名**零影響**，所以嗰 480 場對 pace_perf 權重零資訊，
  但對其餘四維嘅相對權重有全額資訊 → 喺全語料 fit pace_perf 權重係有偏嘅。

所以下面每樣嘢都喺三個語料各做一次：全語料 1611 場、PF 可表達 1033 場
（2026-06+）、乾淨 point-in-time 809 場（2026-08-05+）。

## leaf 本身健康（按馬匹數修正嘅超額上名率）

| PF 區間 | n | 超額 |
|---|---:|---:|
| 0–30 | 863 | −7.83pp |
| 30–45 | 1630 | −3.95pp |
| 45–55 | 1724 | −3.07pp |
| 55–60 | 980 | +1.93pp |
| **60.0（冇證據）** | 5284 | **−0.23pp** |
| 60–70 | 2098 | −0.13pp |
| 70–80 | 1888 | +4.12pp |
| 80–90 | 1128 | +3.49pp |
| 90–100 | 634 | **+10.38pp** |

單調（只有 70–80 / 80–90 一對倒轉 0.63pp），而且**中性點喺 60 係啱嘅**
（冇證據 cohort −0.23pp）。呢個唔係一個壞 leaf。

## 量度一：權重掃描（合約主裁判，頭 5 位配對 AUC）

| 目標權重 | 全語料 1611 | PF 1033 | 乾淨 809 |
|---|---|---|---|
| 0.00 | dev −0.0049 ❌ | dev −0.0081 ❌ | — |
| 0.05 | dev −0.0016 ❌ | dev −0.0050 ❌ | — |
| 0.09 | dev −0.0001 ❌ | holdout 跨 0 ❌ | — |
| **0.12205（現值）** | — | — | — |
| 0.15 | holdout 跨 0 ❌ | dev −0.0005 ❌ | dev −0.0016 ❌ |
| 0.18 | dev −0.0002 ❌ | holdout [−0.0179,−0.0006] ❌ | holdout [−0.0234,−0.0013] ❌ |
| 0.22 | holdout [−0.0170,−0.0030] ❌ | holdout [−0.0278,−0.0049] ❌ | holdout [−0.0314,−0.0046] ❌ |

**兩邊都輸。** 調低一律 dev 負，調高到 0.18/0.22 一律 holdout 顯著負。
現值坐喺最優點上。

## 量度二：完整重 fit（`au_matrix_refit refit --obj place`，共識非 argmax）

| 維度 | 現行 | 全語料共識 | PF 語料共識 |
|---|---:|---:|---:|
| stability | 0.38051 | 0.33105 | 0.34115 |
| jockey_trainer | 0.26535 | 0.28187 | 0.28565 |
| **pace_perf** | **0.12205** | **0.14952 ↑** | **0.14010 ↑** |
| class_weight | 0.13919 | 0.14247 | 0.14337 |
| track | 0.09290 | 0.06784 | 0.08538 |

兩個獨立語料嘅搜索**都想 pace_perf 升**，唔係跌。但兩個候選 holdout 都唔過
（全語料 gold −0.83 / good_pos −1.24；PF 語料 gold −0.65 / good_pos −0.65），
所以兩個都 REJECT —— 連帶證明現行權重冇過期。

## 量度三：剷走 pace_perf 再 fit（`--drop-dim pace_perf`）

基準 dev OBJ 由 **32.2803 跌到 31.2515**。即係 pace_perf 嘅邊際貢獻係正嘅。
剷走之後就算重新 fit（jockey_trainer 升到 0.376），都補唔返。

## 量度四：逐時間窗剷走 pace_perf（解 dev/holdout 符號衝突）

PF 語料上 `→0` 出現 dev −0.0081 但 holdout +0.0096 嘅符號衝突。逐月拆：

| 月份 | 場次 | 頭5位 ΔAUC | |
|---|---:|---:|---|
| 2025-11 → 2026-04 | 394 | ≈ 0 | PF 喺嗰度係常數 |
| 2026-05 | 116 | +0.0061 | |
| **2026-06** | 106 | **−0.0275 [−0.0536, −0.0017]** | ❌ |
| 2026-07 | 100 | +0.0019 | |
| 2026-08 | 827 | −0.0015 | |
| 2026-06+ | 1033 | −0.0042 | |

十個窗入面**唯一顯著嘅結果係反對剷走**。holdout 嗰個 +0.0096 係切片假象。

## 量度五：直接答 Kelvin 嘅觀察 —— 由 pace_perf 帶起嘅首選係咪特別差？

PF 可表達語料 1033 場，逐場計「邊個維度令首選跑出場內平均最多」：

| 帶起首選嘅維度 | 場次 | 首選上名率 | 馬匹數基準 | 超額 |
|---|---:|---:|---:|---:|
| stability | 600 | 55.83% | 32.40% | +23.43pp |
| jockey_trainer | 319 | 54.23% | 31.53% | +22.70pp |
| **pace_perf** | **84** | **54.76%** | 32.90% | **+21.86pp** |
| class_weight | 25 | 44.00% | 31.32% | +12.68pp |

**由 pace_perf 帶起嘅首選同其餘兩個大維度冇分別。** Gunroom / Captain Fenkel
係記得住嘅失敗，唔係一個 cohort 級嘅缺陷。

## 判決

**REJECT —— `MATRIX_WEIGHTS["pace_perf"]` 保持 0.12205。**

五種量法（權重掃描 × 3 語料、兩次完整重 fit、drop-dim、逐時間窗、首選歸因）
冇一個支持調低。兩次重 fit 反而想調高，但調高過 0.18 顯著變差。

順帶：呢次亦都完成咗 scoring.py 註釋要求嘅「乾淨語料儲夠再重驗」——
結論係現行權重照用。

## 附帶價值

* pooled leaf AUC 喺呢個 repo 唔可以直接信 —— 要先按「場內覆蓋」分層，
  否則舊歸檔嘅結構性空白會扮成「呢個 leaf 好弱」。
* `pace_perf` 而家係單 leaf 維度（94.2% PF + 5.8% trial）。
  距離條件組成見 [EXP-20260826-01](EXP-20260826-01-au-pace-perf-distance-crossover.md)。

## 可重現

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out leaves.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py verify --data leaves.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py refit  --data leaves.json --obj place
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py refit  --data leaves.json --obj place --drop-dim pace_perf
```
權重掃描用 `au_eval.compare(races, default_scorer, configured_scorer(weights=...))`。
