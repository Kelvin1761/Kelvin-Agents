---
name: model-regression-gate
description: 'Enforce measured evidence before any Wong Choi model change is kept. Use this skill whenever scoring, ranking, feature weighting, dimension gains, calibration, ML weights or prediction logic change, or when the user asks to "improve the model", optimise, tune weights, add a signal, or make predictions more accurate — in au_racing_engine, hkjc_racing_engine, tennis_wc pricing, or the NBA engine. Establishes a baseline first, compares candidate against baseline on the same corpus and window, and returns KEEP / REJECT / NEEDS MORE TESTING.'
---

# model-regression-gate

呢個 repo 已經有一把尺同一堆 harness。呢個 skill **唔係** 新砌一套評估，而係
強制你行返現有嘅路，唔准另開一個「睇落好啲」嘅量度方式。

## 第一件事：定住把尺

AU 嘅唯一判決規則寫死喺 `au_eval.py` 個 docstring 度，照跟：

> **頭 K 位（K=5）配對嘅場內 AUC，holdout 上 95% 配對 bootstrap 區間唔過 0。
> dev 唔准係負（點估計）。**

點解唔用場數指標（Gold / Good位 / Pass / champion）做主裁判：2026-08-04 校準過，
對 leaf 加 ±0.3 **確定中性** 嘅隨機擾動跑 40 次，dev 5-fold + walk-forward +
holdout 三道閘全過嘅係 **0/40**。假陽性 0 好，但同時代表真 +1pp 嘅改動大機會
過唔到 —— 用佢做裁判會系統性拒絕所有細改善。場數指標照要報，但係**次要**。

HKJC 用 `hkjc_no_regression_gate.py`。tennis 用 `tennis_wc` 自己嘅 backtest／
settlement，並且**一定要** `MIN(id)` 取賠率快照（詳見 leakage-audit）。

## 流程（次序唔可以調）

1. **先寫落 baseline，改之前。**
   ```bash
   ./檢查.sh --quick                       # 確認起步係綠燈
   python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /tmp/leaves.json
   ```
   `au_dump_engine_leaves.py` 會用**現行引擎**重評全 archive。舊 dump 唔可以
   混住用 —— leaf 標尺同矩陣權重都改過，舊 A/B 數字唔作準。

2. **清 bytecode。** macOS 系統 Python 將 `.pyc` 放喺
   `~/Library/Caches/com.apple.python`，靠 `(mtime, 檔案大細)` 判斷。權重由
   `0.08037` 改做 `0.09037` **位元組數一樣**，同一秒改完再跑 = 靜靜行舊 code。
   `./檢查.sh` 第 0 步做咗；手動跑要 `export PYTHONDONTWRITEBYTECODE=1`。
   **「A/B 結果同 baseline 一模一樣」唔等於「呢個改動冇效果」** —— 先查係唔係
   冇接通（見 `ab-identical-means-unwired`）。

3. **同一份語料、同一個時間窗。** baseline 同 candidate 都行同一份
   `leaves.json` / 同一個 archive 掃描。跨 harness 攞數字互相比 = 錯結論。

4. **量。** 揀對嘅工具：
   | 你改咩 | 用邊個 |
   |---|---|
   | 加一個候選特徵入排名分 | `au_feature_ab.py`（dev 85% / holdout 15%，z-score 場內做） |
   | 改維度權重 / display gain | `au_matrix_refit.py`（先 `verify`，未 verify 過唔好信搜索結果） |
   | 改 leaf 公式 | `au_eval.py --swap-leaf` 快查，再 `au_rescore_and_eval.py` 全跑 |
   | 想知兩個版本嘅差距係咪真 | `au_paired_significance.py`（McNemar，唔係兩獨立比例） |
   | HKJC | `hkjc_no_regression_gate.py` + `walk_forward_auto_backtest.py` |

5. **睇分層，唔係只睇總數。** 至少睇：短賠 vs 長賠、馬群大細、場地／going、
   班次、初出馬 / 久休。一個總數升但短賠段跌嘅改動係退步（見
   `au-missed-favourites-cohort`）。

6. **跑 golden + 數據合約。** 評分路徑一動就會連累三個維度：
   ```bash
   python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform au
   python3 .agents/skills/shared_racing/scripts/data_contract.py  --platform au --check
   ```
   golden 會逐匹馬印出邊度變咗。**未睇過 golden diff 唔准 `--record`。**

## 硬規矩

- **holdout 唔准調參。** `au_feature_ab.py` / `au_matrix_refit.py` 已經幫你切好
  時間排序 dev 85% / holdout 15%。唔准手動改切法去令個候選靚啲。
- **唔准改量度方式去救個候選。** 換指標、換窗、換語料、換 top-K —— 一律當
  REJECT。要改把尺就當一個獨立改動，先單獨論證。
- **唔准取 argmax。** 取閘後候選嘅逐維度中位數（共識）。argmax 係教科書級
  overfit：實測 dev good_pos +3.80 但 holdout −5.61。
- **冇量到改善，默認唔留。** 「code 睇落合理啲」唔係證據。
- **一個 cohort gap 唔等於一個可上線嘅收益**（`au-cohort-gap-is-not-a-gain`）。
  先問模型係咪已經另有路捉到同一件事。
- **保住可以退返嘅 baseline。** 改之前 `git stash` / 開分支，`golden_scoring`
  舊 snapshot 唔准同 code 一次過覆蓋。
- **唔准因為「理論上好啲」就 commit / push。**

## 輸出格式

```
候選：<一句講改咗咩>
改到嘅檔案：<路徑>
語料：<archive 掃描範圍> ｜ 窗口：<dev 日期範圍 / holdout 日期範圍>
樣本：<場數> 場 / <匹數> 匹 / <配對數> 對

主裁判 —— 頭5位場內 AUC（holdout）
  baseline   0.xxxx
  candidate  0.xxxx
  差         +0.xxxx   95% 配對 bootstrap [lo, hi]   → 過 / 唔過

dev 點估計：+x.xxxx（唔准負）
5 個時間 fold：x/5 唔輸

次要（場數指標，語料 N 場）
  Gold      xx.x% → xx.x%   (+x.xpp,  +x.x%)
  Good位    xx.x% → xx.x%   (+x.xpp)
  Pass      xx.x% → xx.x%   (+x.xpp)

分層
  短賠 $1–3    xx.x% → xx.x%   (+x.xpp)
  長賠 $21+    xx.x% → xx.x%   (−x.xpp)   ⚠️ 退步
  ...

退步：<逐條列，冇就寫「冇」>
golden diff：<有冇馬匹分數郁到、郁咗邊個維度>
可重現：<命令 + leaves.json 路徑 + commit hash>

決定：KEEP / REJECT / NEEDS MORE TESTING
理由：<一兩句>
```

跟住去 `experiment-review` 落底。
