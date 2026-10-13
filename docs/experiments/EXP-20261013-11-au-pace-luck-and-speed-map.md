# EXP-20261013-11 步速運氣、步速形勢、speed map 準確度、PI 重審

- **日期**：2026-10-13
- **平台**：AU
- **狀態**：**C1–C3 全部 REJECT（dev 已唔合格，terminal 未碰）**｜預先登記喺量度之前寫
- **背景**：EXP-20261013-10 證明 Sportsbet 速度代理**直接**入排名唔得。今次問另一類問題：
  速度資料用嚟判斷**步速對匹馬有利定不利**（Kelvin：「有冇蝕步速同疊數」），同埋**預測今場步速形勢**。
- **搜索過嘅舊記錄**：EXP-20261013-10；EXP-20260902-02/-05（跑法、起步位 REJECT —— 冇用今場步速形勢）；
  EXP-20260822-02（末段跌位 REJECT）；EXP-20260901-01、EXP-20260831-16（PI 加權 REJECT）；
  EXP-20260824-03（Sportsbet pace attribution）；`au-sportsbet-speedmap-rejected`（SpeedPos ρ 0.20 vs 我哋標籤 0.49）；
  `au-run-style-mostly-unpredictable`；`au-race-shape-removed-from-ranking`。
- **疊數**：Sportsbet 冇資料（Formguide `Video/Note/Stewards` 53,308 欄全空；400 個原始頁「wide」只係馬名）→ 量唔到，唔做。

## 定義（只用賽日之前嘅非試閘往績；最近 4 仗平均）
- `f800` = (800m 名次 − 1)/(出賽數 − 1)，0 = 領放、1 = 包尾
- `early_z` = 場頭段速度 z（EXP-10 定義，標準格 < 2026-06-01）
- **蝕步速**（逐仗）`disadv` = early_z × (1 − 2·f800)：前置撞快步速、後追撞慢步速都係正
- PI（逐仗）= (800m 名次 − 終點名次)/出賽數

## 診斷（唔係判決）
- **D1 speed map**：預測今仗**實際** f800（由該馬之後 Formguide 嘅今仗行攞），場內 Spearman ρ：
  P0 Sportsbet `SpeedPos`；P1 過往 f800 平均；P2 本駒頭段速度（EXP-10 `early_speed_own`，取負）；P3 = z(P1) + z(P2)
- **D2 PI**：`pi_mean` 場內上名 AUC；分「往績頭段快／慢」兩半睇 PI 嘅 AUC

## 候選（判決同 EXP-10 一樣：k ∈ {0.5,1,1.5,2,3}，只用 dev 揀合格 k 中位數，Stage 4 v2）
- **C1 `pace_luck`** = mean(disadv)，大 = 過往被步速蝕
- **C2 `pace_adj_margin`** = −mean(負距 − β·disadv)，β = 標準期（< 2026-06-01）逐仗負距對 disadv 嘅 OLS 斜率
- **C3 `pace_scenario`**：今場用 D1 最好嘅預測器得出每匹預測 f800；
  `front` = 1 − 預測 f800 嘅場內百分位；`pressure` = 今場預測前 25% 嘅其他馬數目；
  特徵 **單騎領放分** = front × (1 − min(pressure, 3)/3)（今場其他預測前置馬越少越高）
  只喺 D1 最好預測器 ρ ≥ 0.30 先跑（預測唔準就冇意義）

## 結果

語料同 EXP-10：baseline leaves dump 3,461 場（dev 2,666）。G = 0.877 馬位／名次；**β = +0.267 馬位／單位蝕步速**；
有今仗實際走位（由之後 Formguide 攞）17,459 匹。

### D1 speed map（預測今仗實際 800m 位置，場內 Spearman）
| 預測器 | ρ | 場 / 匹 |
|---|---:|---|
| P0 Sportsbet `SpeedPos` | +0.163 | 751 / 5,039 |
| **P1 過往 f800 平均** | **+0.451** | 1,689 / 11,757 |
| P2 本駒頭段速度 | +0.219 | 1,479 / 10,144 |
| P3 P1 + P2 | +0.394 | 1,689 / 11,757 |

**本駒頭段速度幫唔到 speed map** —— 加落 P1 反而由 0.451 跌到 0.394。
（同 `au-sportsbet-speedmap-rejected` 一致：SpeedPos 仍然係最差。）

### D2 PI 同步速特徵（場內上名 AUC）
| 特徵 | 覆蓋 | AUC |
|---|---:|---:|
| pi_mean | 49.6% | 0.5547 |
| pi_fast（只計頭段快嘅往績） | 42.1% | 0.5325 |
| pi_slow（只計頭段慢嘅往績） | 45.0% | 0.5486 |
| pace_luck | 63.7% | **0.4928** |
| pace_adj_margin | 63.7% | 0.6158 |
| margin_raw | 81.3% | 0.6240 |

同一批馬：margin_raw **0.6207** > pace_adj_margin 0.6158 —— **步速調整令負距變差**。
PI 對 form ρ +0.380、PQ +0.351、ability +0.303 —— 同現有能力訊號重疊，而單獨又弱過純負距。

### 判決
| 候選 | dev 掃描（gold / good / 頭5 AUC） | 結果 |
|---|---|---|
| C1 pace_luck | k0.5 −0.19/−0.11/−0.0007 … k3 −1.16/−0.94/−0.0061 | **REJECT**（dev 全負） |
| C2 pace_adj_margin | k0.5 −0.45/−0.08/−0.0009；k1 −0.75/+0.41/−0.0012 … | **REJECT**（gold 全負） |
| C3 pace_scenario（P1 預測器，ρ 0.451 ≥ 0.30 符合前置） | k0.5 −0.45/+0.26/−0.0002 … k3 −1.09/−1.39/−0.0088 | **REJECT**（gold 全負） |

## 檢查
- **leakage-audit**：PASS —— 特徵只用 `date < 賽日` 往績；**D1 嘅答案**（今仗實際走位）來自之後嘅 Formguide，
  只用嚟做診斷標籤，冇入任何特徵
- **golden_scoring**：冇郁（零 engine 改動）
- **退步**：N/A（冇候選過 dev）

## 結論

**點失敗：**
1. **「蝕步速」效應真但細**：β +0.267 —— 一單位蝕步速只值 ¼ 個馬位。用佢修正負距反而蝕資訊
   （0.6207 → 0.6158），即係「頭段快 + 前置」嗰批馬輸得多**唔係純粹運氣**，有一部分係佢哋本身弱。
2. **被步速蝕過嘅馬下仗冇反彈**（pace_luck AUC 0.4928 < 0.5）。
3. **今場步速形勢（單騎領放）冇用**：預測走位最好都只係 ρ 0.451，用嚟估「今場邊個單騎」誤差太大，
   加落去 gold 全部跌。
4. **PI 唔係冇資訊，但冇淨價值**：0.5547 弱過純負距 0.6240，而且同 form 重疊 ρ 0.38 ——
   同 EXP-20260901-01、EXP-20260831-16 結論一致。快步速下 PI 更弱（0.5325），符合「快步速前置馬崩潰
   令後上馬 PI 虛高」。
5. **疊數**：Sportsbet 冇資料，量唔到。

**決定**：REJECT（C1、C2、C3）；D1／D2 係診斷
**commit**：未 commit（零 model code）

## 重跑
```bash
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_pace_scenario_probe.py build $S/leaves_baseline.json $S/feats_pace.json
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_pace_scenario_probe.py diag  $S/leaves_baseline.json $S/feats_pace.json
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_pace_scenario_probe.py judge $S/leaves_baseline.json $S/feats_pace.json pace_scenario
```
