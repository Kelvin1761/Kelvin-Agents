# EXP-20261016-07 預先登記：eq2_N6 + S2 一齊（ablation）同上線決定

> 跑之前寫。用戶 2026-10-16 要求將 eq2_N6（EXP-20261016-06）同 S2（EXP-20261016-02）推入正式模型；
> Claude 建議先測兩個一齊，用戶同意「照呢個次序開始」。

## 比較（同一套 refit 程序、同一個 41 日 OOS）

| 比較 | 問題 |
|---|---|
| C vs base | 兩個一齊，對現行好唔好？ |
| C vs eq2_N6 | 喺 eq2_N6 之上再加 S2，有冇邊際？（S2 嘅功勞） |

C = eq2_N6 dump 再套 S2 嘅 pace_figure 轉換（同 EXP-02 一樣：0.5 × PF + 0.5 × (60 + 10 × z(A_sb))）。
兩個都用 `evaluate_with_refit_arms`（§8），研究診斷（來源 FLAG）。

## 決定規則（預先定）

1. **C vs eq2_N6 唔係 WIN** → 只推 eq2_N6；S2 繼續等 forward（EXP-20261016-03）。
2. **C vs eq2_N6 係 WIN** → 將證據交返用戶揀：推 C，定只推 eq2_N6。
3. 任何情況下，如果 C vs base 係 `primary_regression`／`ranking_metric_harm` → 唔推 C。

上線用嘅權重：揀中嘅配置用同一 refit 程序、喺全部乾淨數據（08-05 → 10-15）fit 出嚟嘅 pooled 共識。
呢個係用戶接受嘅研究證據上線，**唔係正式 v3 WIN**；兩個 forward shadow 照跑做上線後確認。
