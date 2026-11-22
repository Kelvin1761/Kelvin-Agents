# EXP-20261122-02 AU 騎師／練馬師「剩餘表現」（扣咗坐騎質素同對手）入分 —— 預先登記（2026-11-22，跑之前寫）

- 起因：Kembla 11-21 R7（Fire Star 騎練分 68 > Earn To Burn 63.8，靠 Rachel King 勝率 15% vs Kerrin McEvoy 11%；
  ETB 贏）。現行騎師分 = 去年勝率收縮，冇按坐騎質素／賽事級數調整 —— 跑大賽嘅騎師勝率天然低。Kelvin 2026-11-22「go ahead」。
- Sportsbet「Prize Money」表係按該仗贏到嘅獎金分（賽果本身），唔係賽事級數 → 唔用。平均賠率／ROI 係市場 proxy → 唔用。
- 特徵（walk-forward，只用之前賽日；唔用市場價）：
  1. 每場 p = σ(a + α·(綜合分 − 場均))，(a, α) 用 `au_logloss_ruler.calibrations`（只用之前賽日）。
  2. 騎師 j 喺賽日 d 前所有策騎：R_j = Σ(入三甲 − p) ÷ (策騎數 + 50)（收縮 k = 50，固定）。練馬師同樣（k = 50）。
  3. 候選 = 綜合分 + β·R（β walk-forward：logistic `入三甲 ~ a + b·(綜合分 − 場均) + c·(R − 場均)`，β = c/b，限 [−40, 40]，頭 20 日 0）。
- arm：**JRES** 騎師；**TRES** 練馬師。Holm 2。
- 騎師／練馬師名：canonical 賽果 CSV（`AU_Historical_Raw_Race_Results.csv`）按（日期、場號、正規化馬名）join；對唔到 = R 0。
- 判決：`au_logloss_ruler.evaluate`，語料 `au-noise-20261113/BASE.json`。PASS 都唔直接上線（Kelvin 決定 + forward）。
- 唔准：改 k、改 β 範圍、改語料或尺。

---

# 結果

| arm | Δlog-loss [95% CI] | 單邊 p | Holm p | Gold／Good Δpp（下界） | 判決 |
|---|---|---:|---:|---|---|
| **TRES 練馬師剩餘表現** | **−0.000571 [−0.001011, −0.000130]** | 0.005 | **0.010** | +0.27 (−0.40)／+0.40 (−0.42) | **PASS** |
| JRES 騎師剩餘表現 | −0.000170 [−0.000446, +0.000125] | 0.13 | 0.13 | +0.33 (−0.21)／+0.13 (−0.40) | REJECT |

騎練名 join 率 100%。證據：`EXP-20261122-02-evidence/results.json`；命令：`patches/au_people_residual/run.py BASE.json AU_Historical_Raw_Race_Results.csv OUT`。

## 點讀

- **練馬師**：喺現行騎練分之上，「佢啲馬過去跑得好過／差過模型預期」有剩餘資訊 —— 即係練馬師對馬匹狀態嘅把握，模型冇完全捉到。
- **騎師**：方向正（Gold +0.33），但 CI 跨零 —— Kembla R7 嗰種「大賽騎師勝率被低估」有跡象但未夠證據；語料再長啲可以重測。
- 洩漏：剩餘表現只用之前賽日賽果、校準只用之前賽日；騎練名賽前已知。語料 3.5 個月，練馬師樣本仍然細（k = 50 收縮）。
- 冇上線。下一步：Kelvin 決定開唔開 forward shadow（幅度凍結，新賽日先計）。

## Kelvin 決定（2026-11-22）：實驗性上線 + forward 退回監察

「上左先，跟住 forward 再測試要唔要拎走」；老馬（EXP-20261121-37 PASS）一齊。

- 引擎 `au_racing_engine/people_overlays.py`：綜合分 + 40 ×（練馬師 R − 全場平均）＋ 老馬（8 歲以上）−3.46。
  回退：`WC_AU_TRAINER_RESIDUAL_LIVE=0`、`WC_AU_OLD_HORSE_LIVE=0`。β 40 = 測試凍結值（walk-forward 撞上限，無上限中位約 46）；
  β 40 下 90% 馬調整喺 −1.4 至 +1.6 分，極端 ±4–5（樣本少嘅練馬師，k 50 已收縮）。
- 練馬師表 `au_trainer_residual_table.py` 每晚賽果摺入之後重建（`<資料根>/AU_Trainer_Residual.json`），逐日累積；
  引擎只用**賽日之前**最後一筆 → 重評分舊場次唔前視。
- 顯示：場次分析「按維度合計」＋overlay 表（老馬調整 → 狀態與穩定性、練馬師剩餘表現 → 騎練訊號）；
  標籤「N 歲老馬」轉做入分、新增「練馬師近期跑贏／跑輸模型預期」。
- Kembla 11-21 開／關對比：32 匹排名有變，頭二選上名 13 → 13；R7 Earn To Burn +2.4、Fire Star −1.9（拉近 4.3 分，次序冇變）。
