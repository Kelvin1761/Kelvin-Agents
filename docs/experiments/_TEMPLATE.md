# EXP-YYYYMMDD-NN <一句標題>

- **日期**：YYYY-MM-DD
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
| | | | |

## 檢查
- **leakage-audit**：PASS / FLAG / LEAK — <一句>
- **golden_scoring**：冇郁 / 郁咗 <邊幾個維度、幾多匹馬>
- **data_contract**：PASS / FAIL
- **退步**：<逐條，冇就「冇」>

## 結論
<兩三句。失敗要寫**點失敗**，唔係只寫「冇用」。>

**決定**：KEEP / REJECT / NEEDS MORE TESTING
**commit**：<hash，或「未 commit」>

## 重跑
```bash
<完整命令>
```
