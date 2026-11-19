# EXP-20261119-06 — HKJC：連續兩仗有藉口（塞車／走外疊／騎法被質疑）—— X1 名義 PASS、Holm 差少少；待 Kelvin

- **日期**：2026-11-19
- **平台**：HKJC
- **起因**：Kelvin 2026-11-19（11-18 R9 耀寶：潘頓，近三仗事件報告都有受困／難以望空／收慢避開，模型排 4、贏 $6.5）：
  「上兩仗以上連續唔係塞車、有意外就係跑法被質疑，呢場會唔會加番分？排第四係咪有少少太低？」
- **假設**：連續兩仗有藉口嘅馬，近績分俾連續扣咗，模型低估；加指標會改善入頭三 log-loss。
- **搜索過嘅舊記錄**：EXP-20261116-06（上仗走外疊＋醫療上線；受阻 +1.9／+0.9）、EXP-20261116-11（上仗受阻 +2.0／+1.0、上兩仗任一 +1.1／+1.3、
  騎法被查詢 +3.4／+3.0；R1、R2 入分 REJECT）、EXP-20261117-05／07（受阻做 joint shadow）。**「連續兩仗都有」未測過。**
- **改到嘅檔案／組件**：冇（research only）。腳本 `patches/hkjc_excuse_streak/`。

## 1. 耀寶近三仗事件報告
- 2026-11-01（巴度，第 5）：出閘緩慢；三百米至一百五十米「受困而未能望空」。
- 2026-10-07（艾兆禮，第 7）：收慢避開；二百至一百米「難以望空」；末段「受困之際未能被力策」。
- 2026-09-13（巴度，第 5）：收慢避開；一百五十米被碰撞。
live 只入分上仗走外疊（+）同醫療（−）；佢上仗事件報告 −0.10（場內置中）。

## 2. 殘差診斷（入頭三 − live 校準 p；base_venue_age；dev 2020–23／holdout 2024–25；**holdout 喺呢度已睇**）
嚴格藉口 = 受阻／搵唔到位｜走外疊冇遮擋｜騎法被質疑（`diag_round3` 嘅 INSTR｜RIDE_Q｜RIDE_WARN）。闊 = 嚴格＋碰撞／受擠迫＋出閘慢。
| 群組 | dev | holdout | 逐季 |
|---|---|---|---|
| **嚴格：上兩仗都有＋兩仗都未入位** | **+3.8 [+0.8,+6.9]** n 721 | **+4.2 [+1.2,+7.3]** n 649 | +2 +2 +4 +6 +2 +6 +6 |
| 嚴格：上兩仗都有 | +4.5 [+2.0,+7.2] n 1,131 | +2.4 [−0.4,+5.1] | +2 +6 +6 +5 +1 +4 +5 |
| 嚴格：上三仗都有 | +4.8（n 211） | +3.4（n 203） | |
| 嚴格：只係上仗有（對照） | +1.6 | +1.0 | |
| 嚴格：只係上上仗有（對照） | +0.8 | +1.5 | |
| **受阻：上兩仗都淨係受阻**（耀寶型） | **−0.9**（n 216） | +1.2 | 冇訊號 |
| 闊：上兩仗都有＋都未入位 | +2.6 [+1.1,+4.0] | +1.9 [+0.3,+3.5] | |
| 冇藉口：上兩仗都冇（對照） | −0.2 | −1.2 | |
讀法：連續兩仗有藉口，效果約係單一一仗嘅 2–3 倍；但淨係塞車（耀寶型）冇訊號 —— 訊號主要嚟自塞車、走外疊、騎法被質疑混合。

## 3. 候選（預先登記；Holm 家族 2；β 逐季 walk-forward，場內置中）
| 候選 | 馬次 | β 逐季（raw） | dev Δlog-loss | holdout Δlog-loss | 單邊 p dev／holdout | 其他 holdout | 判 |
|---|---|---|---|---|---|---|---|
| X1 上兩仗嚴格藉口＋都未入位 | 1,576 | −0.36、+0.53、+0.52、+0.98、+1.41、+1.25、**+1.69** | −0.00007 [−0.00014,−0.00000] | **−0.00020 [−0.00037,−0.00002]** | 0.0225／**0.0155** | AUC −0.0003、capture −0.16 [−0.31,−0.00]、Good +0.23 | 名義 PASS；**Holm holdout 唔過**（0.0155 > 0.0125） |
| X2 上兩仗嚴格藉口 | 2,401 | +0.01、+0.56、+1.17、+1.48、+1.59、+1.31、+1.40 | −0.00017 [−0.00031,−0.00003] | −0.00015 [−0.00039,+0.00009] | 0.0060／0.1305 | capture −0.19、Good +0.47 | REJECT（holdout） |

Holm（單邊 α 0.025，家族 2）：dev 兩個都過（0.0060 < 0.0125、0.0225 < 0.025）；holdout X1 0.0155 要細過 0.0125 → 差少少。

耀寶（11-18 R9，raw 66.28）：X1 +1.69 置中後約 +1.5 → ~67.8，**仍然第 4**（第 3 賢知友您 68.35）。

## 4. 結論
- 訊號真而且穩（dev、holdout 都正，逐季由 2021 起 β 一路正兼變大），但改善嘅係**機率準度**；排名（capture@5、AUC）輕微負。
- 預先登記嘅 Holm 判法下 X1 holdout 差少少唔過 → **唔可以話「已證實改善」**。
- 耀寶本身係「淨係塞車」型，呢一類冇訊號；就算上 X1 佢都仍然第 4。

**決定**：NEEDS MORE TESTING（X1）／REJECT（X2）—— 交 Kelvin：
1. 顯示標籤「連續兩仗有藉口（塞車／走外疊／騎法）· 未入分」；
2. 或者好似馬齡 A2 咁，以「改善機率準度、唔改善排名」嘅理由實驗性上線 X1，開 forward 退回監察。

**commit**：未 commit 任何 model code。

## 重跑
```bash
O="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/EXP-20261119-06"
B="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/analysis/replay_all/v4/cons/base_venue_age.jsonl"
I="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/analysis/old_incidents.json"
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_excuse_streak/diag_excuse_streak.py "$B" "$I"
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_excuse_streak/build_excuse_streak.py "$B" "$I" "$O/cand"
for w in dev holdout; do for a in X1 X2; do PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_replay_compare_v4.py "$B" "$O/cand_$a.jsonl" --window $w --null 200; done; done
```
