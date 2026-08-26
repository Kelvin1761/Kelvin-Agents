# EXP-20260825-03 Sportsbet 精確班次 × 實際表現

- **日期**：2026-08-25
- **平台**：AU Wong Choi（Sportsbet-only）
- **基準**：`main@0172211b`；評分語料沿用 `/private/tmp/au_main_6356a7ab_leaves.json`
  （`0172211b` 只 transport 原始班次，排名同 `6356a7ab` 完全相同）
- **前置實驗**：EXP-20260825-02 嘅純平均班次加分及低班次 PF 收縮均 REJECT。
- **假設**：班次唔應單獨加分；「曾經喺較高班跑得有競爭力」可能係現役能力矩陣
  未完整表達嘅 residual signal。
- **判決**：**PROMISING／暫不 ship**。dev 及 holdout 點估計均向上，但 terminal
  95% CI 輕微跨 0；亦修唔到 Randwick R2，正式排名保持不變。

## 語義修正與 point-in-time 邊界

EXP-20260825-02 嘅研究 mapping 先判 generic `HCP`、後判 `MDN`，令 `MDN HCP`
錯當成一般高級 Handicap。今次改為 Maiden 優先；production engine 從未食過該舊
mapping，所以呢個只係研究修正，唔係 live bug。

- historical run date 必須 `< target meeting date`；
- 試閘不入 class feature；
- odds／SP 完全不入 scorer；
- target result 只作 label；
- 缺 class runner 係中性，唔當最低班；
- 場內 z-score，避免跨場 class level 冒充馬匹能力。

Matrix replica 先驗證：

```text
1591 races / 16062 runners
true-engine max |delta| 0.0091; mapper max |delta| 0.0039; >0.01 = 0
```

## 三個替代 encoding（不疊加）

固定測試三個互斥版本，k 只喺 dev grid `0.25,0.5,1,1.5,2,3` 選：

1. `average_class`：近四仗 decay-weighted 平均班次；
2. `proven_class`：班次強度只按該仗 field-relative finish quality 提供證據；
3. `today_proof`：過往於今日班次或以上嘅最佳完成質素。

Sportsbet cache：179 meetings／1,490 race pages／53,142 個歷史 class rows；11,459
runner 對齊。可作場內比較：average 1,248 場、proven 1,127 場、today-proof 736場。
三者至少一個有分散嘅完整評估窗共 1,286 場。

## Development 選擇

最佳係 `proven_class, k=0.5`：

- top-5 paired AUC：`+0.003050`；
- all-field AUC：`+0.002936`；
- 五個 whole-date folds：`-0.00201, +0.00569, +0.01010, +0.00118, +0.00269`
  （4/5 非負）；
- dev Gold `+1.23pp`、Good positional `+0.37pp`、Pass `+0.49pp`、
  t3 precision `+0.45pp`；
- dev winner-in-top3 `-0.12pp`、Champion `-0.25pp`，所以唔係全面向上。

## Locked terminal holdout

開 holdout 前已鎖 `proven_class, k=0.5`：

| 指標 | Delta | 95% CI |
|---|---:|---:|
| Top-5 paired AUC | +0.003005 | **[-0.000662, +0.006798]** |
| All-field AUC | +0.000544 | [-0.002131, +0.003357] |

全窗場數指標：Gold `+0.78pp`、Good positional `+0.23pp`、Pass `0.00pp`、
winner-in-top3 `+0.31pp`、t3 precision `+0.21pp`。方向比 EXP-20260825-02 清晰，
但 canonical gate 要求 holdout lower CI `> 0`；本候選仍未通過。

## Randwick R2 case replay

鎖定候選唔改 R2 排名：

- Lovecats：class z `+0.954`，約 `+0.48` 分，仍第 8；
- Zubba Storm：class z `-0.549`，約 `-0.27` 分，仍第 3；
- Dee Dee Express：class z `+0.269`，約 `+0.13` 分，仍第 2。

DDE 最近有 `F&M BM64` 表現，因此一個語義合理嘅「班次 × 表現」feature 本身唔應
將佢大幅打落。R2 target title 只保存到 sponsor／截斷文字
`BUY YOUR KOSCIUSZKO TICKETS AT TAB HIGHWAY HA`，冇穩定 `CL/BM` level；所以
`today_proof` 覆蓋亦不足，唔可以靠猜今日 class 硬修。

## 決定與下一步

- raw `Sportsbet原始班次` transport 繼續 KEEP，供 daily forward data 累積；
- production ranking **不接入**任何 class candidate；
- 等新增一段完整 Sportsbet forward window 後，原封不動重驗鎖定
  `proven_class, k=0.5`，唔再用目前 terminal holdout 調參；
- R2 的 DDE／Zubba／Lovecats 問題要繼續由其他獨立訊號處理，唔可聲稱 class 已修復。

重播：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_exact_class_quality_eval_20260825.py \
  --dataset /private/tmp/au_main_6356a7ab_leaves.json \
  --extract-cache /private/tmp/au_exact_class_quality_extract_20260825.json \
  --case-html .agents/skills/au_racing/.sportsbet_cache/8ef63d72bbec4f61f1a158749f1c226ca324e289.html \
  --case-date 2026-08-22 \
  --output /private/tmp/au_exact_class_quality_eval_20260825.json
```
