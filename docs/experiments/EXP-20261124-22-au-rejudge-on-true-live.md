# EXP-20261124-22 AU 用真 live dump 重判 R2、練馬師剩餘表現、表現評分（-05）、實力重新設計（-07）

- 日期：2026-11-24　平台：AU　類型：重判（冇改 live）
- 起因：EXP-20261123-06 發現 `au_dump_engine_leaves.py` 之前冇傳 `field_trainers`，dump 嘅 baseline 冇「練馬師剩餘表現」；
  EXP-20261122-04／-05／-07 用 11-13 舊 dump（`au-noise-20261113/BASE.json`）再人手加「live 代理」。Kelvin 2026-11-24 要求重判。
- 尺：AU log-loss 尺 v2（`au_logloss_ruler.evaluate` 預設）。
- dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-rejudge-20261124/`，code = 分支 `claude-au-review-20261124`
  （main `64476758` + F1 SD 下限，EXP-20261124-20）；5,049 場／49,323 匹。`BASE`（全部 live）、`NO_R2`（`WC_AU_PEOPLE_PRIZE_LEAF_LIVE=0`）、
  `NO_TRES`（`WC_AU_TRAINER_RESIDUAL_LIVE=0`）。腳本：`patches/au_rejudge_20261124/`（`rollback.py`、`live_lib.py`、`ability_rerun.py`）；
  -05 直接用原 `patches/au_perf_rating/features.py` + `judge.py` 喺新 BASE 跑（BASE 本身已經係真 live，唔使代理）。

## 結果

### 已上線嘅改動（baseline = 關咗嗰個開關，candidate = live）

| arm | 郁咗嘅馬 | Δlog-loss [95%] | Gold Δpp（下界） | Good Δpp（下界） | 頭二選有中 | v2 |
|---|---|---|---|---|---|---|
| **R2**（EXP-20261122-04） | 38,524 | **−0.00211 [−0.00273, −0.00154]** | +0.99 (+0.34) | +0.82 (+0.03) | +0.93 | **PASS** |
| TRES（EXP-20261122-02） | 33,237 | −0.00023 [−0.00067, +0.00027] | +0.71 (−0.06) | +0.45 (−0.18) | +0.17 | REJECT（CI 跨零） |

### -05 表現評分疊喺真 live 之上（walk-forward β）

| arm | Δlog-loss [95%] | β 中位 | Gold Δpp（下界） | Good Δpp（下界） | 頭二選有中 | Holm | v2 |
|---|---|---|---|---|---|---|---|
| PR1 | −0.00005 [−0.00025, +0.00013] | 0.087 | −0.14 (−0.49) | −0.03 (−0.39) | +0.06 | 0.52 | REJECT |
| PR2 | −0.00056 [−0.00084, −0.00028] | 0.201 | −0.40 (−0.88) | −0.40 (−0.92) | +0.17 | <0.001 | PASS |
| PR3 | −0.00034 [−0.00060, −0.00008] | 0.132 | −0.14 (−0.56) | −0.51 (−0.97) | +0.14 | 0.017 | PASS |
| PR4（取代近績質素分） | +0.00491 [+0.00329, +0.00642] | 0.456 | −2.48 | −2.96 | −1.02 | 1.0 | REJECT（有害） |

### -07 實力重新設計（近績質素分混入表現評分），疊喺真 live

| arm | Δlog-loss [95%] | Gold Δpp（下界） | Good Δpp（下界） | 頭二選有中 | Holm | v2 |
|---|---|---|---|---|---|---|
| S1（PR2 五五混） | −0.00056 [−0.00130, +0.00012] | −1.27 (−1.98) | −0.96 (−1.81) | +0.31 | 0.06 | REJECT |
| S2（PR3） | +0.00029 | −1.21 | −1.30 | +0.37 | 1.0 | REJECT |
| S3（PR1） | +0.00119 | −1.21 | −1.10 | +0.03 | 1.0 | REJECT |
| S4（walk-forward 兩欄） | −0.00068 [−0.00136, +0.00001] | −0.93 (−1.60) | −0.85 (−1.65) | +0.37 | 0.046 | REJECT |

## 讀法

- **R2 喺真 live 上更強**（舊判 Δ −0.00178、Gold +0.20／Good +0.60 → 而家 −0.00211、+0.99／+0.82，Gold CI 全正）。上線決定站得住。
- **練馬師剩餘表現喺真 live 上唔再有支持**：點估計仲係正（Gold +0.71、Good +0.45），但 log-loss CI 跨零。
  合理解釋：R2（騎練分一半總獎金）同佢量緊重疊嘅嘢（好馬房），R2 上咗之後佢嘅邊際貢獻縮細。**唔建議即刻剷**（冇證據有害、點估計正），
  由 EXP-20261121-37 forward 嘅 TRES rollback arm 判（1,000 場）；如果 Kelvin 想簡化，`WC_AU_TRAINER_RESIDUAL_LIVE=0` 即刻回退。
- **-05 PR2／PR3 喺 v2 PASS，但唔建議上**：機率準咗少少，但 Gold／Good 點估計都係負（−0.40／−0.40；PR3 Good −0.51）；
  Kelvin 2026-11-22 定嘅門檻（PR1 shadow：Good 同頭二選有中 CI 下界都要 > 0）一樣都唔達到。PR1 shadow forward（EXP-20261122-05）照跑。
  另外 PR1／PR2／PR3 係睇過同一份語料先揀嘅，有選擇偏差。
- **-07 冇翻案**：四個 arm Gold 點估計跌 0.9–1.3pp，同原結論一致，表現評分「改 leaf」路線維持暫停。

## 唔確定／限制

- dump 嘅 trainer residual／R2 用每晚重建嘅表（只用賽日之前資料），同 live 一樣；但舊場次用而家嘅表重評分 ≠ 當日 live（表會因後來賽果補齊而唔同），
  所以呢個係「現行 code 喺歷史上」嘅判決，唔係當日表現。
- 研究工具舊 bug：`patches/au_people_redesign/run.py` 嘅 `REPO = parents[3]` 其實指去 `docs/`，靠先 import `au_people_prize/run.py` 先湊啱 sys.path；
  新 `live_lib.py` 自己插路徑。
