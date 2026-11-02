# EXP-20261102-04 結果：AU 班次部分重建 —— 一個模組、剷兩條冇訊號規則、修一個代理 bug（排名幾乎唔郁）

- **預先登記**：[protocol](EXP-20261102-04-au-class-rebuild-protocol.md)（`bcd1fc67` 第 1／2 步；逐條消融 `29309d9b`，兩次都喺量度之前）。
- **語料**：全語料重評 4,086 場（`au_dump_engine_leaves.py`）；判決用 2026-08-05 起 3,283 場（v3 `fixed_rule` 全紀錄，bootstrap 以賽日 2000 次）。
- **用戶**：要正路處理級數分、重建成最簡單 code、清 bug 同死 code；中途加「test again if the 級數分 items still have signals, if not maybe just remove them」。

## 第 1 步：結構 —— A/A byte-identical

計算全部搬入 `au_racing_engine/class_rating.py`（級數分、評分分、負磅代理、代理分、負磅分、高班實績 z）。
引擎方法只砌說明。全語料重評同 baseline **4,086 場 byte-identical**（`cmp`）—— 連 08-05 之前都一樣，
即係 RT 豁免喺成個語料由來冇觸發過。

同時剷／修（排名零變化）：
- 剷：省賽轉都會「RT ≥ 68 唔扣」豁免、`_latest_l600_rt_metrics`／`_latest_l600_rt_brief` 同錨點「最新PF/RT」（Facts `L600/RT` 欄 08 月起 436k 行 0 有值）、`_class_score` 冇用嘅 `race_bucket`。
- 修顯示：負磅分「基礎分 62」→ 60；維度判語唔再寫「級數分…參考（不入排名）」（佢 10-09 起入排名）、唔再寫「負磅分 ≥63（降班配輕磅）」呢類永遠唔成立嘅句；
  `_class_move_today` 註釋（今場獎金有來源）。

## 第 2 步：判決（3,283 場；Δ 單位 pp）

| arm | 郁咗場數 | Gold | Good | top3 capture | top5 AUC | v3 | 分層 CI 全負 |
|---|---:|---|---|---|---|---|---|
| **F1** 負磅代理唔扣級數（vs baseline） | 26 | +0.00 | +0.00 | +0.00 | +0.00 | 中性 | — |
| C1 剷降班＋省轉都會 | 1,013 | +0.06 [−0.06, +0.18] | **−0.03** | −0.02 | −0.01 | primary_regression | — |
| C2 高班實績搬入級數分 | 2,153 | **−0.06**（塊 3/6） | −0.03 | +0.04 | −0.02 | primary_regression | 首選前置 Gold |
| C3 C1＋C2 | 2,372 | −0.03（塊 3/6） | −0.06 | +0.00 | −0.05 | primary_regression | 首選前置 Gold |
| R0 剷初出馬 | 668 | +0.03 | **−0.03** | −0.04 | −0.05 | primary_regression | — |
| **R2** 剷兩歲初出 | 1 | +0.00 | +0.00 | +0.00 | +0.00 | 中性 | — |
| R5 剷出賽 ≤5 場兩條 | 1,929 | +0.03 | +0.06 | −0.05 | +0.00 | too_weak | **首選守中 Good** |
| RD 剷降班 | 601 | +0.03 | **−0.06** [−0.15, 0.00] | +0.01 | +0.01 | primary_regression | — |
| **RM** 剷省賽轉都會 | 530 | +0.03 [−0.06, +0.14] | +0.03 [−0.09, +0.19] | −0.03 | −0.02 | too_weak | — |
| RALL 全部剷（級數分 = 60） | 2,390 | +0.00 | +0.00 | **−0.16 [−0.27, −0.05]** | **−0.07 [−0.14, −0.00]** | ranking_metric_harm | — |
| **採用組合** F1＋R2＋RM（真引擎 dump，vs baseline） | 543 | +0.03 [−0.06, +0.14] | +0.03 [−0.09, +0.19] | −0.03 [−0.08, +0.02] | −0.02 [−0.06, +0.02] | too_weak | — |

（C1–RALL 都係 vs F1。）採用組合：Gold 21.14% → 21.17%、Good 26.17% → 26.20%（各 +1 場）。

## 決定

- **F1 上線（§7 正確性修正）**：R2x 本意「代理用咗級數分先扣」，但淨用負磅代理嗰批（混合讓磅場冇評分馬）都照扣，
  令佢哋維度入面嘅級數份額變零。錯處獨立於績效；26 場郁、指標零差、冇分層 CI 全負。**唔係已證實改善。**
- **剷「兩歲初出 +0.84」**：3,283 場只觸發 1 場（Sportsbet 賽名好少寫「2yo」），等同死 code。
- **剷「省賽轉都會 −5.48」**：剷走 Gold、Good 都 +0.03pp，冇 ranking CI 全負、冇分層 CI 全負 → 冇代價簡化。
- **保留**：初出馬（R0 Good 跌）、出賽 ≤5 場兩條（R5 守中首選 Good CI 全負）、降班（RD Good −0.06）。
  三條加埋有明確訊號：全部剷走 top3 capture CI 全負。
- **C2／C3 REJECT**：高班實績搬入級數分（經代理對冇評分馬放大 4.67 倍）Gold 時間塊只 3/6、首選前置 Gold CI 全負。
  overlay 0.5 × z 原樣保留。今日診斷見到「加重 proven_class +0.0019」嘅方向，要另開 walk-forward 擬合候選先試，唔可以由呢度推。
- **採用組合仍然係 REJECT 級證據（too_weak）**，上線理由係「少兩條規則、修一個 bug、冇代價」，**唔係改善**。

## 對進行中測試嘅影響

EXP-20261009-04（級數分 0.15 份額，11-09 forward 檢討）嘅回退影子 `class_score_live_delta` 由新級數分計，
即係檢討嘅係「新級數分值唔值 0.15」。省賽轉都會剷走之後級數分少咗最大嗰條負項。

## 負磅（同日診斷，記錄）

評分場內同負磅 corr 0.90；讓磅賽評分＋負磅 +0.0017 CI 跨零、綜合分＋實際負磅 +0.0009 CI 跨零、非讓磅 −0.0045 CI 全負；
負磅分 leaf 單獨 AUC 0.497。負磅分繼續只做顯示，唔加返。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/class-rebuild"
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out $S/final_code.json   # 定稿 = FINAL arm，cmp 一樣
zsh scratch/au_class_rebuild_arms_20261102.sh        # 要先將 evidence/class_rating_arms.py 放返原位（見檔頭）
python3 scratch/au_class_rebuild_judge_20261102.py $S/base.json $S/final_code.json out.json
```

baseline `348049dc`。證據：`EXP-20261102-04-evidence/`（每個 arm 嘅判決 JSON 連分層）。
golden 120 匹全部一致（樣本冇中改動）；AU tests 1,242 passed；data contract 已重新 calibrate。
