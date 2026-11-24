# EXP-20261124-70 結果：NBA `p_final` 事後校準 —— NEEDS MORE TESTING（再校準成立，抽水曲線未獨立證實）

- **日期**：2026-11-24 · **平台**：NBA · 協議（連修訂 1）：`EXP-20261124-70-nba-ms-vig-recalibration-protocol.md`，喺結果之前分兩次 commit。
- **分工**：Codex Terra 寫 `build_dataset.py`（Claude 核對 join）；Claude 寫判決腳本同判決；Codex Sol 獨立覆核（見最後）。
- **冇改任何上線 code。**

## 數據
`patches/nba_ms_recal/build_dataset.py` → 每條已結算 milestone 腿一行（最早開波前 production model_obs ＋ 結算）。
MS 模型（`nba_engine:ms:a140747bfae0c724`）逐日核對過：dev 11-05…11-11 7,903 腿／7 日；holdout 11-12…11-24 13,991 腿／12 日（11-19 冇 production 紀錄，見下）。

## 判決項（`evaluate.py`，按日 bootstrap 2,000，seed 20261124）
dev LODO（揀形式）：p_final 0.4494；R1 +0.0012、**R2 −0.0001**、R3 +0.0009 → 揀 R2。

| holdout | log-loss Δ [95% CI] |
|---|---|
| R2 − p_final | **−0.0035 [−0.0048, −0.0021]** |
| R2 − R1 | −0.0018 [−0.0032, −0.0004] |
| R1 − p_final | −0.0017 [−0.0022, −0.0012] |

按協議字面兩個條件都過（= KEEP 候選）。逐 stat：PTS −0.0045、REB −0.0022、AST −0.0058 顯著；3PM −0.0018 跨零。穩膽區（p_final ≥ 0.7）−0.0039 [−0.0070, −0.0005]。

### 校準（holdout）
| p_final 段 | 腿 | 實際 | p_final | R2 |
|---|---|---|---|---|
| 0–0.2 | 6,206 | 0.096 | 0.088 | 0.090 |
| 0.2–0.4 | 2,402 | 0.351 | **0.292** | 0.322 |
| 0.4–0.6 | 1,722 | 0.551 | **0.495** | 0.526 |
| 0.6–0.8 | 1,638 | 0.687 | 0.702 | 0.709 |
| 0.8–0.9 | 918 | 0.844 | 0.849 | 0.830 |
| 0.9–1.0 | 1,105 | 0.911 | **0.945** | 0.915 |

- 中間段（主 O/U 線附近）低估約 5–6pp → 解釋咗精選 v1「永遠揀細」（O/U 主線 1,612 腿：實際大 0.499、p_final 0.460、R2 0.487、去水價 0.489）。
- 頂段（穩膽腿）高估約 3.4pp；3 腳 SGM 疊埋大約高估 9pp，同 `nba-banker-overconfidence` 舊記錄方向一致。

## 點解唔係 KEEP（Sol 覆核指出，Claude 同意）
1. **假設嘅來源同 holdout 重疊**：呢個假設係由 EXP-20261120-60 `bias_check`（11-05…11-19 O/U 線）啟發，同 holdout 11-12…11-19 重疊。係數只喺 dev 擬合，但「去搵呢個形狀」本身睇過 holdout 部分數據。
2. **乾淨子集**（11-20…11-24，啟發數據之後，5,665 腿；次要、唔係重判）：
   | | 全 holdout | 11-20…24 |
   |---|---|---|
   | R2 − p_final | −0.0035 | **−0.0027 [−0.0041, −0.0010]** |
   | R2 − R1 | −0.0018 | −0.0009 [−0.0022, +0.0013] |
   | 只加線性項 − p_final | −0.0019 | −0.0020 [−0.0030, −0.0014] |
   | R2 − 只加線性項（二次項嘅貢獻） | −0.0016 | −0.0007 [−0.0021, +0.0016] |
   → 「再校準 p_final」喺乾淨數據都成立；「抽水曲線（二次項）」未能獨立證實。
3. dev LODO 本身冇改善 —— 偏差係 11-12 之後先出現／變大（季初 drift 嘅可能）。逐日 12/12 日都係負數。
4. Sol 其他意見：O/U 次指標有 303/906 dev 腿用咗模型之後嘅價（只影響次要數字）；`p_final` 額外 clip 0.02–0.98，拎走後 dev Δ −0.00008，冇影響。

## 決定
**NEEDS MORE TESTING。** 建議：將 R2（dev 係數凍結）同「只加線性項」兩個 arm 做 forward（target_date ≥ 2026-11-25），主指標 log-loss 對 p_final。
**要等 S2 forward（EXP-20261111-05，約 11-26 判）出咗先開**：MS2 都係換 p_final，兩個要一齊諗，唔好疊兩層校準。由 Kelvin 決定開唔開。

## 另外發現（數據管線）
- 2026-11-18 晚（target 11-19）21:00 run 因為 UTA_LAL 球員盤未開，四次重試都 `partial`，**成晚冇 production 發佈**（其餘 11 場一齊冇咗）。MS 上線以嚟只呢一晚。建議改做「準備好嘅場次先發」，未改。
- Sol 引擎覆核（`model.py`／`legs.py`／`featured.py`）：只搵到壞數據先觸發嘅邊界 bug（NaN 線令 `featured` crash、FG3A>FGA 會壓低得分均值、0+ 線）；NB 尾、單位、clip 次序、stat 鍵、半線互補全部冇錯。唔係表現問題。

## 重跑
```bash
python3 docs/experiments/patches/nba_ms_recal/build_dataset.py --out <csv>
/usr/bin/python3 docs/experiments/patches/nba_ms_recal/evaluate.py <csv> dev
/usr/bin/python3 docs/experiments/patches/nba_ms_recal/evaluate.py <csv> holdout R2
/usr/bin/python3 docs/experiments/patches/nba_ms_recal/sensitivity.py <csv>
```

## 補充（同日，設計 forward 時量；描述性）
- 每週重擬合 walk-forward（`rolling_sim.py`）：R2 用晒之前數據 −0.0036，每日或每週重擬合冇分別；只用最近 7 日差啲（−0.0028）。
- **淨係用市場價去水曲線**（`market_only.py`，唔用 `p_final`）−0.0033，同 R2 一樣；R2 − 純市場 +0.0001 [−0.0000, +0.0003]。
  → 而家 `p_final` 喺「去水去得啱嘅市場價」之上冇加到資訊；改善全部嚟自去水形狀。精選嘅 edge 好可能大部分係去水誤差。
- forward 登記：EXP-20261124-61（RW 主 arm，另有 R2F／R1W／MKT 對照）。
