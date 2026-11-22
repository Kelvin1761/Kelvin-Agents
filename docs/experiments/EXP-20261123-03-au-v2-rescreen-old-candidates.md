# EXP-20261123-03 AU 舊候選用 v2 尺重跑 —— **F1（近績 SD 下限）喺現行 live 上 PASS；SPG PASS 但細到冇實際意義**

- 日期：2026-11-23　平台：AU　類型：重篩＋重建（冇改 live；上唔上線係 Kelvin 決定）
- 起因：Kelvin 2026-11-23「所有舊判決當新候選重新跑，目標係更好嘅模型」；把尺 v2 已獨立上線（`fcedd248`，EXP-20261123-01）。
- 腳本：`patches/au_v2_rescreen/`（`screen.py` 篩、`run.sh` 重建 dump、`judge.py` 判）。dump：
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-v2-rescreen-20261123/{BASE,F1,SPG}.json`。

## 第一步：篩（舊 dump，v2，null 0）

外置碟 24 對 base／arm 目錄、81 個 arm（`EXP-20261123-03-evidence/screen.txt`）。v2 下 log-loss CI 上界 < 0 而且 AUC 護欄過：

| arm | 狀態 | 處理 |
|---|---|---|
| fq-prize SHIP／C1 | C2 系列已上線（EXP-20261105-05） | 唔使重跑 |
| draw-bigfield R8／Z8／Z10／ZD8 | 大場次檔位已實驗性上線（EXP-20261102-08） | 唔使重跑 |
| class-rebuild F1／R2 | Δ = 0（冇郁） | — |
| exp-20261028 A2（獎金 z 封頂 ±1.567） | 概念已被 C2「跑得好先攞獎金分」取代 | 唔重跑 |
| **fq-scale F1**（EXP-20261111-31 近績 SD 下限） | v1 REJECT（Good 下界 −1.00） | **重建** |
| **track-specialism SPG**（EXP-20261103-01 好地日讀好地往績） | v3 REJECT（ranking 證據唔夠） | **重建** |

其餘 70 個 arm v2 照 REJECT（log-loss 冇改善或者變差）。限制：只係外置碟仲有 dump 嘅候選；冇 dump、喺記憶體內判嘅舊候選
（例如 EXP-20261122-03 獎金 T3、-05／-07 表現評分）要逐個重砌 —— T3 已被上線嘅 R2 取代；-07 四個 arm Gold 點估計跌 > 1pp，v2 一樣 REJECT。

## 第二步：喺現行 live（`fcedd248`）重建

研究開關（預設關，live 唔郁）：`WC_AU_FQ_SCALE=floor`（`stability.field_z` 除數 = max(場內 SD, 0.3065)，EXP-20261111-31 原樣，
0.3065 係量度前凍結、只用賽前 raw）；`WC_AU_TRACK_SPECIALISM_ARM=SPG`（好地日照舊乾地規則讀好地往績，EXP-20261103-01 原樣）。
兩個都係 fixed_rule（冇由賽果 fit），唔需要 walk-forward 預測。

**研究工具修正**：第一次重建發現 `au_dump_engine_leaves.py` 冇傳 `field_trainers`／`field_jockeys` → dump 入面
「練馬師剩餘表現」（live，2026-11-22 上線）永遠係 0，即係 baseline 唔係 live。已補（同 `au_auto_orchestrator` 一致）；
修正後 81.5% 馬有練馬師剩餘表現。⚠️ EXP-20261122-04／-05／-07 之後用呢個 dump 工具嘅 AU 實驗，baseline 都少咗呢個 overlay
（佢哋有啲人手加返「live 代理」）。

| arm | 郁咗嘅馬 | Δlog-loss [95%] | 場內 AUC Δ [下界] | Gold Δpp（下界） | Good Δpp（下界） | 頭二選有中 | null | Holm | v2 |
|---|---|---|---|---|---|---|---|---|---|
| **F1** | 20,835 | **−0.00171 [−0.00225, −0.00120]** | **+0.0013 [+0.0001]** | +0.17 (−0.22) | +0.26 (−0.22) | +0.28 | 1.00 | <0.001 | **PASS** |
| SPG | 23,904 | −0.00006 [−0.00012, −0.00001] | −0.0001 [−0.0005] | −0.03 (−0.21) | +0.11 (−0.09) | −0.09 | 0.995 | 0.005 | PASS |

（修正前嘅 baseline：F1 −0.00181、AUC +0.0010、Gold +0.11／Good −0.17；SPG −0.00006 —— 方向一樣，F1 喺真 live 上更好。）

## 讀法

- **F1**：細 SD 場（例：Warwick Farm R1 Shahaameh 94.6）以前會將細差距放大成大分；加 SD 下限之後機率準咗，
  排名指標全部正（AUC CI 全正、Gold／Good／頭二選點估計正）。11-11 用 v1 判 REJECT，係因為舊 Good 護欄冇靈敏度
  （EXP-20261123-01），同埋當時 live 冇練馬師剩餘表現。
- **SPG**：PASS 但 Δ 只有 −0.00006，排名冇改善。唔建議上 —— 加一條規則換咁細嘅改善，唔符合「簡單穩健 > 複雜邊際」。

## 建議（要 Kelvin 決定）

- **F1 上線**（`WC_AU_FQ_SCALE` 改為預設 floor，或者直接改常數），同時登記 forward 退回監察（`au_forward_tracker.FORWARD_TESTS`），
  更新 golden／data_contract／模型說明，dashboard 冇新標籤（係近績質素分內部尺度）。
- SPG 唔上。
- 研究開關 code 留喺分支 `claude-au-v2-rescreen-20261123`，未入 main。
