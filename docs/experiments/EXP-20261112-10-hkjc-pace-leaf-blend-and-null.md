# EXP-20261112-10 HKJC 步速修正等級：P3／P0–P2／表現數字加權混合，leaf 層篩選，同隨機擾動 null

- **日期**：2026-11-12 ｜ **平台**：HKJC
- **觸發**：Kelvin：「P2 同現行差少少，應該係正確方向；加埋輸頭馬幾多秒做 P3，或者調 P0／P1／P2 比重。」
  另問馬會「馬匹評分／體重／名次」頁有冇訊號。
- **假設**：(a) P2（或 P0／P1）同 P3 加權混合，排名贏現行；(b) 負磅應該加喺「輸頭馬距離」上面；
  (c) 改呢個 leaf 跌 Gold 係候選本身差，唔係任何改動都會咁
- **搜索過嘅舊記錄**：EXP-20261112-06／-07／-08／-09
- **改到嘅檔案／組件**：冇 live 改動。`hkjc_pace_blend_sim.py`、`hkjc_margin_weight_screen.py`、`hkjc_leaf_null_perturbation.py`；
  `hkjc_std_pace_table.py` 加咗 3 仗診斷欄（唔影響 arm）

## 馬會「馬匹評分／體重／名次」頁
每仗：當時評分、名次／出馬數、馬匹體重、場地、跑道、路程、賽道、場地狀況、班次。**冇負磅、冇時間。**
Logic `rating_trend`（近 6 仗評分）同賽績檔（體重、名次）已經有大部分；對呢個問題冇新訊號，冇砌爬蟲。

## 一、加權混合（離線模擬，預先登記喺 `hkjc_pace_blend_sim.py` docstring）
- 只改「有現行等級又有新數值」嘅馬（段速訊號數目唔變）；b = w·z(新) + (1−w)·z(P3)；dev 分位數分四級；加減分照現行
- 離線等價：段速分 → raw 傳導 r 由 EXP-09 真回放逐匹量（中位 0.1292）；k=0 逐場重現 baseline；w=0 同現行等級 99.4% 一致
- dev（203 場）揀，Gold、Good 都 ≥0 先合格

| 混合 | w | dev Gold | dev Good | dev NDCG |
|---|---|---|---|---|
| P2 | 0.25／0.5／0.75 | −0.49／−0.99／−1.48 | −0.99／0.00／+0.99 | +0.001～+0.005 |
| P1 | 0.25／0.5／0.75 | −0.49／−0.49／−1.48 | −0.99／−0.49／0.00 | +0.004～+0.006 |
| P0 | 0.25／0.5／0.75 | −0.99／−1.48／−1.48 | +0.49／0.00／+0.49 | +0.005～+0.007 |
| 表現數字 W | 0.5／0.75／1.0 | −0.99／−1.97／−2.46 | +1.48／+0.99／+1.48 | +0.004～+0.009 |
| 表現數字 U | 0.5／0.75／1.0 | −1.48／−0.99／−1.48 | +0.49／+0.99／+0.99 | +0.008～+0.010 |

**冇一個合格 → REJECT，holdout 冇開。**

## 二、leaf 層篩選（4,095 匹，同一 population，場內 AUC）
| 數值 | 全部 | dev | holdout |
|---|---|---|---|
| P3 現行（近 3 仗輸頭馬秒數，margin × 0.17） | 0.648 | 0.673 | 0.624 |
| M 賽果庫實際輸頭馬秒數 | 0.651 | 0.676 | 0.627 |
| MW／MF 輸頭馬按負磅換算（對頭馬／對全場） | 0.646／0.646 | | |
| MFT 再加今仗相對全場負磅 | 0.640 | | |
| P0／P1／P2 對馬會標準（另一 population，3 仗 0.625／0.607／0.600） | 0.630／0.613／0.612 | | |
| 表現數字 U（扣賽事效應，近 6 仗） | 0.660 | 0.683 | 0.638 |
| **表現數字 W（再按今仗負磅換算）** | **0.669** | **0.692** | **0.647** |

模型（扣走現行等級）之上同 P3 一齊放：表現數字 W **−0.360 [−0.494, −0.235]**，P3 跌到 −0.090 [−0.209, +0.036]；
P2 喺 P3 之上 −0.073 跨零；MW／MF 同 M 一齊放全部跨零。

- 對馬會標準嘅版本輸，因為標準時間唔知當日場地快慢（場地狀況、跑道、風），輸頭馬距離自動扣走；步速修正（ρ）令佢再差
- 負磅擺喺輸頭馬距離上面冇效果；擺喺表現數字上面兩半都 +0.009 AUC
- **表現數字 W 喺 leaf 層兩半都贏 P3，而且包含晒 P3 嘅資訊**

## 三、隨機擾動 null（200 次，同 P3 相關度相同但冇資訊，同樣分四級、同一 population）
| 候選 | 候選 − base：Gold／Good／NDCG | null 均值：Gold／Good／NDCG | 候選喺 null 百分位：Gold／Good／NDCG |
|---|---|---|---|
| 表現數字 W，w=1 | −1.78／+0.89／+0.0033 | −1.69／−1.22／+0.0005 | 38%／**100%**／81% |
| 表現數字 W，w=0.5 | −0.89／+0.45／+0.0043 | −1.12／−1.02／+0.0013 | 58%／96%／90% |
| P2，w=1 | −0.67／−0.45／+0.0021 | −1.69／−1.14／0.0000 | 90%／79%／74% |

- 同等幅度嘅隨機改動平均令 Gold 跌 1.1–1.7pp（95% 範圍 −2.9～−0.2）、Good 跌 1.0–1.2pp —— 即係失去 P3 部分資訊嘅代價
- 表現數字 W 喺 Good 贏晒 200 個隨機版本，但 Gold 同隨機一樣跌 —— 佢帶嚟嘅新資訊幫到 Good／NDCG，補唔返 Gold

## 檢查
- **leakage-audit**：PASS —— 表現數字 PIT（賽事效應只用之前賽果估，β 用評估窗之前）；賽果庫輸頭馬只用賽日之前；冇用賠率
- **golden_scoring**：冇郁；**退步**：live 冇改

## 結論
1. Kelvin 嘅方向（對標準、逐段步速修正）喺 leaf 層實測差過輸頭馬距離；真正贏嘅係「扣賽事效應」嘅表現數字，負磅換算喺佢上面有效。
2. 排名閘：表現數字 Good 升、Gold 跌，跌幅同隨機改動一樣。同一批 389 場已經跑咗 30 幾個 arm，喺呢批場次上已經分唔清。
3. 下一步唯一乾淨嘅判法係 forward：預先登記表現數字 W 取代（或 w=0.5 混合）做 harness_ab，用 2026-11-12 之後嘅新場次判。
   arm 要喺評分時即場由賽果庫計 PIT 表現數字（而家係預計算表），要改 code 先登記得到。

**決定**：混合 REJECT（dev 冇合格）；leaf 篩選 MEASUREMENT（表現數字 W 最好）；建議 forward
**commit**：未 commit 任何 model code

## 重跑
```bash
P=docs/experiments/patches; O=<上一輪 scratch>
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_pace_blend_sim.py $O/base.jsonl $O/stdP2.jsonl $O/stdtable.json blend/
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_pace_blend_sim.py $O/base.jsonl $O/stdP2.jsonl $O/stdtable.json blendfig/ $O/figtable.json
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_margin_weight_screen.py $O/base.jsonl $O/figtable.json marginw.json
PYTHONDONTWRITEBYTECODE=1 python3 $P/hkjc_leaf_null_perturbation.py $O/base.jsonl $O/stdP2.jsonl $O/stdtable.json $O/figtable.json
```
（`base.jsonl` = `hkjc_eval_harness run --dump-matrix`；`stdP2.jsonl` = EXP-09 P2 arm 回放；`stdtable.json` = `hkjc_std_pace_table.py`；
`figtable.json` = `hkjc_fig_level_table.py`）
