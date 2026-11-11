# EXP-20261111-07 HKJC 升班扣分（引擎 A/B）

- **日期**：2026-11-11（假設、arm、判決規則喺睇 A/B 結果之前寫）
- **平台**：HKJC
- **觸發**：Kelvin：「正路應該係有啲馬會降班去搏贏，反而升班要同更強嘅馬比賽會相對冇利」；揀咗先做升班扣分
- **搜索過嘅舊記錄**：EXP-20261111-06（順帶發現：升班原始 +8.13pp 係 form 影子）；EXP-20260904-09（匹馬升／降班單獨 AUC 死）；
  引擎現況：升降班**只喺文字層**（`_explain._class_move_note`），冇入分
- **改到嘅檔案／組件**：只有 arm `docs/experiments/patches/hkjc_arm_class_up_penalty.py`；冇改 production code

## 動機（screening，賽果庫 `load_all_rows`，相對場內期望嘅上名超額）

控制上仗名次之後（同一名次層之內對比同班），升班平均 **−4.10pp**，降班 +0.66pp：

| 上仗 | 升班 | 同班 | 降班 |
|---|---|---|---|
| 贏 | +15.91 (n=590) | +20.41 | n=21 |
| 2–3 | +6.78 (183) | +13.74 | +9.46 (102) |
| 4–6 | −1.28 (149) | +3.01 | +3.88 (363) |
| 7+ | −8.12 (181) | −8.35 | −7.27 (1,009) |

逐季：24/25 **−6.69pp [−11.27, −1.52]**（n=499）；25/26 −2.65pp [−7.23, +2.04]（n=508）；26/27 +0.79pp（n=59，冇功效）。
方向兩季一致，但第二季減弱、CI 跨零。⚠️ **方向係睇住同一段時間嘅數據揀出嚟**，同 A/B 語料重疊 —— 輕微 in-sample；
所以幅度唔 fit，用引擎現有 class 加減項嘅慣例值。

## Arm（只得一個）
- **baseline**：origin/main（未改）
- **UP4**：`class_score` 喺 `_class_move_note()` 判「升班」時 **−4**（同 `season_place_0_pen` 一樣大）；初出馬唔郁；
  降班唔郁（+0.66pp 太細，唔做）。傳導：class_score 份額 × class_advantage 權重，綜合分約 −0.4 分

## 判決規則（`docs/model-evaluation-contract.md`，`--stage4 fixed_rule`，只開一次）
- 全紀錄 Gold／Good 點估計 < 0，或 6 個時間塊少過 4 塊 ≥ 0 → **REJECT**
- Primary CI 下界 > 0 → PRIMARY_WIN；ranking metric CI 上界 < 0 → REJECT
- 過咗 primary 但 CI 跨零 → 唔聲稱改善，交 Kelvin 決定（可以 forward）
- 唔換幅度、唔加降班、唔換窗去救

## 結果（2026-11-11，按上面規則，只開一次）

- **語料**：`hkjc_eval_harness` PIT 回放 441 場 → 配對 **380 場**（排除死欄位／唔配對 60 場），38 個賽日
- **接通**：39 場排名有變（10.3%）—— arm 有接通，唔係零差

| 指標 | Δ | 95% CI | 6 塊 |
|---|---|---|---|
| Gold | **−0.26pp** | [−0.82, 0.00] | 5 塊 0、1 塊 −1.45 |
| Good 位置 | **−0.26pp** | [−1.10, +0.53] | 5 塊 0、1 塊 −1.41 |
| top3 capture@5 | −0.09pp | [−0.37, +0.18] | |
| NDCG@5 | −0.0004 | [−0.0035, +0.0025] | |
| competitive recall@5 | −0.10pp | [−0.35, +0.10] | |
| 實際頭三平均模型名次 | **+0.0079（變差）** | **[+0.0009, +0.0157]** | |

**判決：REJECT / primary_regression**（兩個 primary 點估計 < 0）。實際頭三嘅模型名次仲顯著推後。

## 點解賽果庫量到 −4.1pp，引擎就落唔到（解釋，未獨立量度）

- 賽果庫嘅 −4.1pp 只控制咗**上仗名次**。引擎控制嘅嘢多好多：form 近 6 仗、段速、騎練、負磅（升班馬評分升咗、
  負磅已經重咗，而負磅分本身已經按「重磅＝讓磅官評高」入分）。即係升班帶嚟嘅「對手強咗」，有一部分已經由
  負磅／班次份額反映；再扣 −4 係雙重計算，將真係會上名嘅升班馬推低（平均名次顯著變差就係呢個訊號）。
- 效應本身亦唔穩：24/25 −6.69pp CI 唔跨零，25/26 −2.65pp 跨零，26/27 樣本得 59。
- 同 `au-cohort-gap-is-not-a-gain` 同一個形狀：群體缺口量得清楚，但模型已經另有路捉到。

## 檢查
- **leakage-audit**：PASS —— 升降班只讀排位表 `recent_6_detail` 嘅上一仗班次（賽前資料）；arm 冇 fit 任何數值
- **golden_scoring**：冇郁（冇改 production code）
- **退步**：Gold、Good 各 −1 場；實際頭三平均模型名次 +0.0079 CI 全正

## 結論
Kelvin 嘅直覺喺**群體層面係啱嘅**（控制上仗名次之後升班 −4.1pp），但喺現行引擎之上再扣分會輸：
模型已經透過負磅／form 消化咗大部分，額外扣分將真係上名嘅升班馬推低。**唔上線。**
文字層仲寫緊「降班：對手淺咗，實際著數」—— 數據只係 +0.66pp，呢句應該改（純顯示，另開改動）。

**決定**：REJECT
**commit**：未 commit 任何 model code

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
PYTHONDONTWRITEBYTECODE=1 python3 $H run --out base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $H run --arm docs/experiments/patches/hkjc_arm_class_up_penalty.py --out up.jsonl
python3 $H compare base.jsonl up.jsonl --stage4 fixed_rule --leakage-audit-passed
```
