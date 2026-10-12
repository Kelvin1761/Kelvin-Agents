# EXP-20261012-31 AU 試閘污染、`10` 解析、往績行缺失 —— Tamworth R4 Platinum Card 個案

- **日期**：2026-10-12
- **平台**：AU
- **觸發**：Kelvin 指出 2026-10-12 Tamworth R4 #2 Platinum Card（生涯 1 場、跑第 10）被排第 2，結果跑尾。
- **base**：origin/main `1dc706a1` + Codex AU 審計未 commit 改動（已搬入同一 worktree，`./檢查.sh` 全綠）
- **判決尺**：Stage 4 v3 `fixed_rule`（冇由數據 fit 任何數值），全紀錄、賽日 bootstrap、6 個時間塊
- **搜索過嘅舊記錄**：EXP-20260831-03（個體化 L600）、EXP-20260905-02、au-unplaced-runs-scored-as-neutral、
  au-field-size-extraction-gap、EXP-20261012-07（Codex：兩行試閘被當正式賽果，屬賽果 CSV 層，唔同一個缺陷）

## 個案拆解（修正前）

| leaf | 值 | 點嚟 |
|---|---:|---|
| pace_figure | 84.1 | 唯一一場 PF 係 **2025-11-04 試閘**嘅場級 L600；單場樣本 z −1.2 |
| performance_quality | 69.8 | 冇正式賽 → 用 consistency；consistency 解 `10` 做 [1, 10] → 一場虛構頭馬 +7 |
| form | 60 | Sportsbet 往績頁本身冇嗰場正式賽（只有 3 場試閘）→ 當「冇證據」 |

## 四個缺陷（全部可獨立證明係錯，如果數字相反都仍然要改）

| # | 缺陷 | 規模（2026-08-05 起） | 修法 |
|---|---|---|---|
| F1 | `inject_fact_anchors.is_trial_venue` 將所有 600–950m 賽事當試閘 | **2,188 場正式賽**被標試閘（900m 1,077、800m 549、950m 539），1,363 個馬匹段落 | 有 `RaceClass:[…]` 嘅 Sportsbet 往績行只信 `(TRIAL)` 標記／Barrier Trial 班次／$0 獎金；冇 RaceClass 嘅舊格式先保留估算 |
| F2 | pace_figure 收集 PF 冇排除試閘 | PF 行 **14.3%** 嚟自試閘；39.0% 馬混入；**745 匹（2.7%）全靠試閘** | `_is_trial_form_line` 過濾 |
| F3 | `parse_recent_finishes("10")` → [1, 10] | Facts 近績序列 `10`（單場第 10+）131 匹 | 已解碼序列嘅 `10` = 一場第 10 |
| F4 | 生涯有正式賽但往績行缺失 → form 中性 60 | 待量 | 用 Facts 近績序列（官方 Last 10，已跳過試閘）以絕對名次階梯計，班次乘數 1.0 |

## 鎖定（寫喺睇結果之前）

- **語料**：2026-08-05 起 358 個場次，抄去 scratch，用同一份 code 由 Racecard／Formguide **重新生成 Facts 同 Logic**
  （因為 F1 改嘅係 Facts 生成），再 `au_dump_engine_leaves.py`。
- **Arms**：`base`（四個開關全關）、`all`、`−F1`、`−F2`、`−F3`、`−F4`（leave-one-out）。
- **判決**：`all` vs `base` 用 v3 `fixed_rule`。屬 §7 正確性修正：要求零顯著退步（primary 全紀錄點估計
  不得 <0、6 塊至少 4 塊 ≥0、冇 ranking metric CI 全負）；唔要求 WIN；記錄要寫明「唔係已證實改善」。
- **消融**：每個 leave-one-out arm 報 Gold／Good 差，用嚟講邊個修正郁到排名，唔用嚟揀留邊個
  （四個都係正確性修正，冇得揀）。
- **今日（10-12）賽果**只做個案描述，唔入判決（單日冇功效）。

## 結果（2,436 場 / 23,490 匹 / 68 賽日，v3 fixed_rule，賽日 bootstrap）

| 比較 | top-4 有變 | Gold | Good | Pass | 判決 |
|---|---:|---:|---:|---:|---|
| 全部 F1–F4 vs base | 764 場 | −0.45 [−1.11,+0.21] | −0.16 | −0.78 | REJECT primary_regression |
| F2 邊際（all vs −F2） | 723 | −0.37 | −0.21 | −1.03 | **F2 係拉低嘅主因** |
| F2 窄版邊際（只剔走冇正式 PF 嘅試閘） | 151 | −0.29 | +0.00 | −0.29 | 都係負 |
| F1 邊際（all vs −F1） | 91 | −0.04 | +0.04 | +0.04 | 中性 |
| **F1+F3+F4 vs base（最終）** | 123 | **−0.08 [−0.31,+0.13]**（4/6 塊 ≥0） | **+0.04 [−0.17,+0.26]** | +0.25 | 冇顯著退步 |

ranking 指標（最終）：top3_capture +0.04、ndcg +0.03、top5_auc +0.04，CI 全部跨零。

### 讀法

- **F2 撤回**：試閘嘅 PF（race-level L600 環境）**平均有預測力**，連「全靠試閘」嗰批都係。
  「試閘唔應該入 pace_figure」係直覺，唔係事實；Platinum Card（單場試閘 → 84.1）係個別例外。
  code 已剷走，留低註釋解釋點解刻意保留。
- **F1、F3、F4 按 §7 上**：可獨立證明係錯（900m 正式 Maiden 被當試閘、`10` 變頭馬、往績行缺失當冇證據），
  全紀錄冇顯著退步、leakage PASS。**唔係已證實嘅改善**（Gold 點估計 −0.08pp ≈ 2 場）。
- Platinum Card（F1+F3+F4 之後，實測）：64.85 → **62.2**，form 60 → 53.3、PQ 69.8 → 61.9，pace_figure 照用試閘 84.1。首選 Halcyon Belle 退出之後，修正前佢等於頭號推介；修正後排喺 Boa Vista（實際第 2）之後。

## 決定

- F1、F3、F4：**SHIP（§7 正確性修正，唔係已證實改善）**
- F2：**REJECT**（兩個版本都令 Gold 跌）
