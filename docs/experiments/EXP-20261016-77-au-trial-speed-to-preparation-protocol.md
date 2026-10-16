# EXP-20261016-77 預先登記：試閘速度由 L600 環境分搬去試閘備戰

> 量度之前寫。結果另寫 `EXP-20261016-77-au-trial-speed-to-preparation-results.md`。

- **日期**：2026-10-16；**平台**：AU；**baseline**：main（EXP-20261016-75 P2 上線後）。
- **用戶指示**：「照呢個設計預先登記 EXP-20261016-77：L600 環境分只用正式賽，試閘速度分做新 leaf 放入試閘備戰（0.5/0.5，維持 6 場門檻），用 §8 兩邊都 refit 判。」
- **前因**：
  - 現行 `pace_figure_score`（L600 環境分）對少過 6 場正式賽嘅馬，將試閘 PF 行同正式賽一齊平均（`performance_pf_metrics`）。
    例：Gatton 2026-10-16 R2 Bellouise，1 場正式賽 +2.49 秒同 1 課試閘 +0.95 秒平均 +1.72 → 76 分。
  - EXP-20261016-01 F6c **剷走**試閘 PF 行：Top3@5 −0.0036、NDCG −0.0035、Top5 AUC −0.0027（CI 全負）—— 試閘速度有資訊，
    但嗰次冇搬去其他地方。今次係**搬**，唔係剷。

## 候選（單一、固定）

1. **L600 環境分只用正式賽**：`performance_pf_metrics` 對所有馬剔走 `run_kind == "trial"` 行（runner 同場內標準化同一份證據）。
2. **新 leaf `trial_speed_score`（試閘速度分）**：
   - 適用：同現行一樣，`trial_performance_applies`（正式賽少過 6 場，或者未知）。
   - 原始值 = 該馬試閘 PF 行嘅個體 L600 平均（`l600_delta + margin × 0.17`，同 `pace_figure` 一樣嘅個體化；冇 margin 嘅行用 `l600_delta`）。
   - 場內：有原始值嘅馬 ≥ 3 匹先計，z = (值 − 場均) / 場內 SD（population），分數 = clip(60 − 20z)；否則 60。
3. **試閘備戰維度** = 0.5 × `preparation_score` + 0.5 × `trial_speed_score`；係數維持 0.2524（fixed arm）。

## 判決（合約 §8，判決器 `evaluate_with_refit_arms`，用 ruler 分支模組）

- A0 = baseline + live 權重；A1 = 候選 + live 權重；B0／B1 = 各自用 refit 程序 `f92c8377…` walk-forward refit（OOS 1,482 場／41 日）。
- fixed arm（A1 vs A0）WIN → 用 live 權重上線。否則 refit arm（B1 vs B0）WIN，**而且** live guard（B1 vs A0）唔係 `primary_regression`／`ranking_metric_harm`
  → 候選連 refit 權重一齊上線。兩個 arm 做 Holm。其他一律 REJECT。
- 另報：v3 fixed_rule 全紀錄（2,485 場）、頭兩名 $15+ 跑尾三分一、Bellouise 呢類（1–4 場、試閘 PF 有）嘅分數變化。

## 限制（照寫）

- §8 判決器未發佈去 main；候選贏嘅話要先發佈 §8 把尺，再發模型。
- 同一 41 日窗已經重用多次；今日改動另有 EXP-20261016-74 forward 確認（凍結喺 `2d7ec14c`，唔包括呢個候選）。

## 唔准做

改 0.5／0.5、6 場門檻、0.17、20、≥3 匹；改成剷走（F6c 已測）；睇完結果加候選。
