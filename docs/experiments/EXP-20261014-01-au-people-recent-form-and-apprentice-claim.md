# EXP-20261014-01 騎練近期狀態（每月統計）＋見習騎師減磅

- **日期**：2026-10-14
- **平台**：AU
- **狀態**：**REJECT ×4（dev 已唔合格，terminal 未碰）**｜預先登記喺量度之前寫
- **來源**：2026-10-13 Sportsbet 欄位盤點 —— 兩個「而家測得」嘅剩餘機會
- **搜索過嘅舊記錄**：`au-jockey-trainer-fully-checked`（六個騎練公式方向 REJECT，收益嚟自補數據）；
  `au-people-stats-have-lookahead`（profile 快照前視 —— 今次只用**已完結月份**避開）；
  EXP-20260901-02（people database）；騎練連續性三項剷走（`au-jockey-continuity-terms-removed`）；
  引擎見習減磅只係報告文字（`engine_core` 2279、3366）

## 事實（量度前已確認）
- Sportsbet 顯示嘅係**分配負磅**，減磅另列：Rosehill R8 60.0／59.5／59.5（Anna Roper a-1.5）／59.0／59.0（Jacob Stiff a-3）。
  我哋 Formguide 剝走減磅（只剩 0.5% 騎師名帶 `A2` 等標記），所以見習騎師嘅馬一直記錄做多揹 1.5–4kg。
- People 快照 `Monthly Breakdown` 有過去 12 個月逐月 starts／1st／2nd／3rd。

## 預先登記嘅特徵
- **J1 `jockey_recent_delta`** = 騎師最近 3 個**已完結月份**（賽事月份之前）上名率 − 佢自己 12 個月上名率
  （同一份月表，只用賽事月份之前），近期部分用 α=20 收縮向 12 個月率。
- **J2 `trainer_recent_delta`**：同上，練馬師。
- **J3** = J1 + J2（各自場內 z 相加）。
- **A1 `claim_kg`**：見習減磅公斤數（冇減磅 = 0；對唔到頁面 = 冇值）。方向未知（揹輕 vs 騎師較弱），
  所以 k 網格包負值：{−3, −2, −1, −0.5, 0.5, 1, 2, 3}。
- 名字配對：Formguide `J:`／`T:` 名 → people cache（已補名）；同名多人就當對唔到。

## 判決（同 EXP-20261013-10，唔改尺）
- 語料：`leaves_baseline.json`（3,461 場）；candidate = `default_scorer + k × 場內z`；冇值 = 0
- J*：k ∈ {0.5,1,1.5,2,3}；只用 dev 揀合格 k（dev Gold、Good 唔負且頭5 AUC > 0）中位數；然後一次 Stage 4 v2
- 先報覆蓋、單獨 AUC、同 `jockey_score`／`trainer_score` 嘅 ρ（診斷）

## 結果

前置：people cache 補名之後（2,567/2,568 有名）先做；月表 2,358 人（同名撞 1 個剔走）；
減磅 index 43,676 匹次（cache 賽事頁）；語料 runner 34,043。

| 特徵 | 覆蓋 | 場內上名 AUC | ρ vs 現有 |
|---|---:|---:|---|
| jockey_recent_delta | 96.6% | 0.5083 | jockey_score −0.028 |
| trainer_recent_delta | 92.5% | 0.5144 | trainer_score −0.040 |
| claim_kg | 91.9%（當中 21.6% 有減磅） | **0.4833** | jockey_score −0.148 |

### 判決（dev 掃描 gold / good / 頭5 AUC）
| 候選 | 最好嘅 dev 點 | 結果 |
|---|---|---|
| J1 jockey_recent_delta | k0.5 −0.15/−0.15/−0.0012（全部負） | **REJECT** |
| J2 trainer_recent_delta | k0.5 −0.30/+0.23/−0.0001 | **REJECT**（gold 全負） |
| J3 J1+J2 | k0.5 −0.53/+0.34/+0.0009 | **REJECT**（gold 全負） |
| A1 claim_kg | k−1 +0.15/−0.08/+0.0017；k−0.5 −0.19/+0.08/+0.0006 | **REJECT**（冇一點 gold、good 同時唔負） |

## 檢查
- **leakage-audit**：PASS —— 騎練只用賽事月份**之前**已完結月份；減磅喺賽前已公佈（post-race 頁面同一值）
- **golden_scoring**：冇郁（零 engine 改動）

## 結論
**點失敗：**
1. **騎練近期狀態係真正交**（ρ ≈ −0.03），但幾乎冇資訊（0.508–0.514）—— 「近三個月熱／冷」主要係雜訊，
   12 個月率已經係較好嘅估計。同 `au-jockey-trainer-fully-checked`「收益嚟自補數據唔係改公式」一致。
2. **見習減磅淨效應係負**（0.4833）：減磅多 = 新手騎師，佢嘅弱蓋過揹輕。ρ −0.148 對 jockey_score，
   即係已經俾 jockey_score 捉咗一部分；加落去 dev 冇一點同時唔傷 Gold 同 Good。

**附帶正確性問題（未修，記低）：** Sportsbet 負磅係**分配負磅**（Rosehill R8：60.0／59.5／59.5 a-1.5／59.0／59.0 a-3），
Formguide 剝走減磅，所以見習騎師嘅馬記錄做多揹 1.5–4kg。負磅只經 rating fallback／讓磅 proxy 入分，影響細；
要修就係 extraction 層保存 claim 同 carried weight，屬 §7 正確性修正，另開一單。

**決定**：REJECT（J1、J2、J3、A1）
**commit**：未 commit（零 model code）

## 重跑
```bash
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_people_recent_probe.py build $S/leaves_baseline.json $S/feats_people.json   # ~10 分鐘
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_people_recent_probe.py diag  $S/leaves_baseline.json $S/feats_people.json
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_people_recent_probe.py judge $S/leaves_baseline.json $S/feats_people.json claim_kg
```
