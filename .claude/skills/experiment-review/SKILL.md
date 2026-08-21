---
name: experiment-review
description: 'Search past model experiments before testing a hypothesis, and record every experiment afterwards so failed ideas are not retried and shipped changes stay explainable. Use this skill at the START of any model experiment (search first) and at the END (record the result), for the Wong Choi racing, tennis and NBA engines. Records live in docs/experiments/.'
---

# experiment-review

## 兩半，兩半都唔准跳

### 開始之前：搵返有冇人試過

呢個 repo 已經燒過好多次同一個想法。**未搜索過就開始試 = 重複燒錢。**

```bash
# 1. 實驗記錄
ls docs/experiments/
grep -ril "<關鍵詞>" docs/experiments/

# 2. 現有嘅 review / plan 檔（記錄喺實驗系統之前嘅結論）
grep -ril "<關鍵詞>" *.md Guides_and_Plans/ docs/ .agents/skills/*/*/REFIT_PLAN.md 2>/dev/null

# 3. 已經有 harness 嘅方向 —— 檔名本身就係一份「試過咩」清單
ls .agents/skills/au_racing/au_wong_choi_auto/scripts/ | grep -E "audit|test|probe|search|shadow|gate"
```

已知**已判死**嘅方向（唔准重試，除非有新數據源）：
sire signal（洩漏）、Sportsbet Speedmap、轉贏注、位賠 ≥2 門檻、當朝落注、
PF backfill、jockey/trainer 六個公式方向、layoff 做排名特徵、
自己 derive run style、trainer_signal、J/T combo 表入分。

### 做完之後：落底

一個實驗 = `docs/experiments/` 一個檔。命名：
`EXP-YYYYMMDD-NN-<短 slug>.md`

**唔准生成大檔。** 記錄係濃縮 Markdown。原始 dump（leaves.json、逐匹馬 CSV）
留喺 `/tmp` 或 scratchpad，記錄裡面只寫路徑同重跑命令。
`docs/experiments/INDEX.md` 一行一個實驗。

## 記錄模板

`docs/experiments/_TEMPLATE.md` 有一份可以 copy 嘅。必要欄位：

```markdown
# EXP-20260821-01 <一句標題>

- **日期**：2026-08-21
- **平台**：AU / HKJC / tennis / NBA
- **假設**：<一句，可以被證伪嘅>
- **搜索過嘅舊記錄**：<EXP id 或 "冇相關">
- **改到嘅檔案／組件**：<路徑>

## 配置
- **baseline**：<commit hash 或 weights 檔>
- **candidate**：<改咗咩，一句>

## 數據
- **語料**：<archive 範圍>
- **訓練／dev 窗**：<日期範圍>
- **驗證 fold**：<5 個時間 fold / walk-forward>
- **holdout 窗**：<日期範圍，如有>
- **樣本**：N 場 / N 匹 / N 對

## 結果
| 指標 | baseline | candidate | 差 | 顯著？ |
|---|---|---|---|---|
| 頭5位AUC (holdout) | | | | 95% CI [ , ] |
| Gold | | | | |
| Good位 | | | | |
| Pass | | | | |

### 分層
| Cohort | baseline | candidate | 差 |
|---|---|---|---|

## 檢查
- **leakage-audit**：PASS / FLAG / LEAK — <一句>
- **golden_scoring**：冇郁 / 郁咗 <邊幾個維度、幾多匹馬>
- **data_contract**：PASS / FAIL
- **退步**：<逐條，冇就「冇」>

## 結論
<兩三句。失敗要寫**點失敗**，唔係只寫「冇用」。>

**決定**：KEEP / REJECT / NEEDS MORE TESTING
**commit**：<hash，KEEP 而且真係 commit 咗先填；REJECT 就寫「未 commit」>

## 重跑
```bash
<完整命令>
```
```

## 硬規矩

- **失敗實驗一樣要記，而且要記得同成功一樣詳細。** 一個「我試過 X，
  因為 Y 所以唔 work」嘅記錄，價值等於一個成功改動 —— 佢省返下一次嘅時間。
- **唔准掩飾失敗。** 唔准改假設去啦返個結果、唔准只記「探索性」。
- **失敗實驗唔准自動 commit。** 記錄可以 commit（佢係有用資訊），
  **model code 唔准**。
- **KEEP 唔等於即刻 push。** 等 Kelvin 講。
- **一個實驗一個假設。** 想試三樣 → 三個記錄，或者行 `feature-ablation`。
- **記錄要令人重跑得到。** 冇重跑命令 = 唔算一份記錄。
- **證據弱就報唔確定，唔准砌一個結論。**
