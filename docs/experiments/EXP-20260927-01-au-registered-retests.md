# EXP-20260927-01 — AU 預註冊重測到期：speed REJECT；class 舊候選失效

**狀態：`speed_fig_best3` REJECT／NOT SHIPPED；`class_score` OBSOLETE／NOT SHIPPED**
**日期：** 2026-09-27 ・ **平台：** AU

## 觸發

`au_retest_watch.py` 量到：

- 乾淨 point-in-time 場次（2026-06-06 起）：**2,095**
- 至少三條 `WinningTime` 嘅 runner：**62.7%**（37,103 匹）

兩個數都過咗 `EXP-20260826-04/06` 預先登記嘅門檻。

## 先修量度：舊命令冇食到到期語料，而且拆開同一賽日

原登記命令初跑只得 **1,390 場**，日期止於 **2026-08-21**。根因係
`au_feature_ab.py` 用靜態 `sb_archive_meeting_ids.json`（181 個 meeting）做入口；
watch 就用現行完整資料根目錄，所以「覆蓋到期」同「A/B 語料」其實係兩份資料。

另外舊 85/15 切點將 **2026-08-15** 拆成 dev 70 場／holdout 1 場，違反
`docs/model-evaluation-contract.md` 嘅完整賽日規則。嗰次初跑結果作廢。

修正只改資料對齊同 split 正確性，冇改 feature、k 搜索範圍、指標或 fold 門檻：

- `AU_Historical_Raw_Race_Results.csv` 對齊完整 scored meeting
- `--clean-from 2026-06-06` 鎖 point-in-time 起點
- dev／terminal 同 5 folds 全部以完整賽日切分

正式命令：

```bash
AU_SPEED_STD_ROOT="<data root>" PYTHONDONTWRITEBYTECODE=1 \
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_feature_ab.py \
  --scored "<data root>" --features speed_fig_best3 --min-depth 0 \
  --clean-from 2026-06-06
```

## `speed_fig_best3` 正式結果

**2,090 場**可評（dev 1,662／terminal 428），日期 2026-06-06 至 2026-09-26；
terminal 由 2026-09-16 起。乾淨總數同可評數差 5 場，係 scoring／formguide／
賽果 runner 對齊後不足四匹，冇為補齊而放寬規則。

| k | dev t3prec | dev winner@3 | dev champion | folds |
|---:|---:|---:|---:|---:|
| 0.25 | −0.10pp | −0.12pp | +0.06pp | 2/5 |
| **0.50** | **+0.04pp** | **+0.30pp** | **0.00pp** | **4/5** |
| 1.00 | −0.16pp | +0.24pp | 0.00pp | 2/5 |
| 1.50 | −0.44pp | −0.42pp | −0.18pp | 1/5 |
| 2.00 | −0.46pp | −0.24pp | −0.30pp | 1/5 |
| 3.00 | −0.76pp | −0.84pp | −1.08pp | 1/5 |

`k=0.5` 喺 dev 揀定後先開 terminal：

| terminal 指標 | Δ |
|---|---:|
| Gold | +1.17pp |
| Good positional | **−0.23pp** |
| Pass | 0.00pp |
| Champion | +0.23pp |
| Winner in Top 3 | **−0.23pp** |
| Top-3 precision | **−0.23pp** |

### 判決

**REJECT／NOT SHIPPED。** 合約 Stage 4 要求 Gold／Good 喺 dev 同 terminal 都無
回歸；terminal Good 已經回歸。舊 harness 自己嘅三個主排序指標亦只得 1/3 向上，
所以唔存在「換一把尺就過」嘅情況。冇改任何 live scoring code。

## `class_score`：門檻到，但原候選已經唔存在

`EXP-20260826-06` 登記嘅候選係 `rating .70 + class .60`，並要求 display gain
喺 dev 重 fit；命令指向 `scratchpad/class_revival.py`。

到期審核發現：

1. `scratchpad/class_revival.py` 從未入 git，現役 workspace 亦不存在，無法核對原
   sample hash、split、gain fit 同 bootstrap 實作。
2. 2026-09-02 架構重整已正式退役 display gains；現行 engine 只准直接 fit component
   weights。即使今日重砌一個 script，都會係**另一個候選**。
3. `EXP-20260831-09` 曾喺其後配置重測直接 `class_score` bonus：單獨 AUC 0.5620，
   最佳 k=0.6，dev +0.0001、holdout −0.0026 [−0.0071,+0.0016]，亦冇支持上線；
   但佢唔係原登記嘅 class-weight 架構，唔用佢冒充到期重測。

所以原登記改為 **OBSOLETE／NOT SHIPPED**。如果再追 `class_score`，要用現行無 gain
架構另開一個預註冊實驗，先鎖候選公式、日期 split、功效同 terminal 判決，唔可以
沿用已失效候選嘅「七個 dev 全正」作先驗通行證。

## 改動範圍

- 修正研究 harness 嘅完整語料入口同完整賽日切分
- 加 regression tests，防止同一日期再被拆開
- 清走已處理／失效嘅 watch alert
- **零 live model、weight、golden、data-contract 改動**
