# EXP-20261016-77 結果：試閘速度由 L600 環境分搬去試閘備戰 —— REJECT

- **預先登記**：[protocol](EXP-20261016-77-au-trial-speed-to-preparation-protocol.md)（`79ec71f9`，rebase 後 `14a83f67`，量度之前）。
- **語料**：`scratch/au_ts_split_dump_20261016.py` @ `b4b90dfb`；候選用研究開關 `TRIAL_SPEED_SPLIT` + 變體 `ts_split`
  （研究碼喺分支 `claude-au-trial-speed-split-20261016`，**冇入 main**）。乾淨窗 2,485 場；兩邊 `exact_score` 同引擎一致。
  證據：`EXP-20261016-77-evidence/`。
- 第一次候選 dump 有錯：引擎輸出只帶 `FEATURE_KEYS`，`trial_speed_score` 冇輸出（ability 啱，但 refit 會當 60）。
  修正後重出；用嚟判嘅係修正後嗰份。

## 候選

L600 環境分只用正式賽（9,430 匹 pace_figure 改變）；試閘速度分（3,381 匹非中性）以 0.5 入試閘備戰。

## 結果

| | Gold | Good | 備註 |
|---|---|---|---|
| v3 fixed（2,485 場） | −0.04pp [−0.53, +0.45] | +0.16pp [−0.43, +0.73] | 排名指標 CI 跨零；11–12 匹 Good CI 全負 |
| §8 fixed（OOS 1,482 場） | −0.27pp [−0.81, +0.27] | +0.20pp [−0.55, +0.95] | |
| §8 refit | +0.07pp [−0.65, +0.83] | −0.34pp [−1.08, +0.36] | |

研究判決 **both_arms_reject**；live guard primary_regression；Holm p 1.0／1.0；`baseline_weights_stale = False`。
頭兩名 $15+ 跑尾三分一 156 → 153 [−16, +9]。

## 解讀

- 搬走（今次）同剷走（EXP-01 F6c：Top3@5 −0.0036、NDCG −0.0035、AUC −0.0027，CI 全負）唔同：今次排名指標冇顯著跌，
  即係**試閘速度嘅資訊搬咗去試閘備戰都保得住**，但分開計冇帶嚟改善。
- 所以維持現行：少過 6 場嘅馬，試閘 PF 行繼續喺 L600 環境分入面同正式賽一齊平均。唔再試其他比例（登記唔准）。
