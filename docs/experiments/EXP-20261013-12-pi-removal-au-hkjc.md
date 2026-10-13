# EXP-20261013-12 剷走 PI（位置增益）：AU 同 HKJC

- **日期**：2026-10-13
- **平台**：AU + HKJC
- **假設**（Kelvin）：PI 只係「比擲毫好少少」，剷走之後模型唔會差。
- **搜索過嘅舊記錄**：EXP-20261013-11（PI 場內 AUC 0.5547，同 form ρ 0.38）；EXP-20260901-01、EXP-20260831-16
  （AU PI 加權 REJECT）；`matrix_mapper.py` 2026-08-05 `sectional_score` 退出排名；EXP-20260904-07
  （HKJC 走位PI AUC 0.5697、同跑法糾纏）；`hkjc-race-shape-ablation-is-settled`

## AU：PI 已經冇排名權重 —— 冇嘢可以剷
- PI 只喺 `_sectional_breakdown` → `sectional_score`，而 `pace_perf` = pace_figure 0.941744 + trial 0.058256，
  **sectional 唔喺任何維度**；證據厚度安全欄 `THIN_EVIDENCE_SCORED_LEAVES` 亦唔計佢
- 實測 `au_eval.py --swap-leaf sectional_score=60`（3,461 場）：**所有指標 +0.0000**
- 剩低嘅只係報告文字（「位置增益（PI）…」）—— 顯示層，唔影響排名
- 「剷走再 refit」：冇權重 = 冇嘢 refit

## HKJC：PI 有權重，剷走 REJECT
PI 喺 `race_shape`（27.4%）：
- 沙田：`_draw_position_fit_score` ±5（上升軌／衰退）、±2（微升／微跌），佔 race_shape 25%
- 非沙田 legacy：context delta ±2；跑馬地 live 係 `v3_surface`，走位匹配**唔入分**

做法：`hkjc_pi_ablation_probe.py` 注入兩個模型行同一條路徑：`ctl_replay`（原封不動）vs `cand_no_pi`
（PI 權重全部 0 重跑引擎），Stage 4 v2 比較。⚠️ 對照組同 live 只有 274/362 場排名一致
（live 有 draw tiebreak 等後處理），所以比較係 cand vs ctl，唔係 vs live。

| 指標（362 場） | ctl_replay | cand_no_pi |
|---|---:|---:|
| gold | 20 | 19 |
| good | 87 | **83** |
| champion | 94 | 96 |
| min_threshold | 159 | 159 |
| mrr | 0.4561 | 0.4590 |
| avg_top4_hits | 2.017 | 2.017 |

排名有變 47 場。**Stage 4 v2：REJECT `primary_regression`（gold、good_positional）**。

## 結論
- **AU**：Kelvin 嘅直覺同 code 一致 —— PI 早喺 2026-08-05 已經剷出排名，量到零影響。
- **HKJC**：PI 細幅有用（good −4 場 = −1.1pp 如果剷走），方向同 EXP-20260904-07「AUC 0.5697 唔係噪音」
  一致。效應細、語料細（362 場），未至於可以話「PI 好有用」，但**冇證據支持剷走**，規則亦唔准。
- **refit**：唔做。HKJC 七維 refit 已經 REJECT（`hkjc-outer-weight-refit-rejected`），而 race_shape
  整個維度剷走都細過噪音底（`hkjc-race-shape-ablation-is-settled`）—— 362 場撐唔起一次 refit。

**決定**：AU 無需改動；HKJC REJECT（保留 PI）
**commit**：未 commit（零 model code；probe 腳本 + 記錄）

## 重跑
```bash
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_eval.py --data $S/leaves_baseline.json --swap-leaf sectional_score=60
cd ../../../hkjc_racing/hkjc_reflector/scripts
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 hkjc_pi_ablation_probe.py
```
