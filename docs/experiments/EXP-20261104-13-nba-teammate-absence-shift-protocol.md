# EXP-20261104-13 NBA：主力缺陣／復出嘅「缺陣變化」—— 模型要唔要調？接手球員同主力復出腿抵唔抵買？（協議，喺計任何結果前寫）

- **日期**：2026-11-04
- **平台**：NBA
- **假設**：
  - **H1（模型）**：live 機率（`nba_engine` 嘅 `p_final`：MS，S 計唔到就 C）冇反映「今日缺陣同最近幾場唔同」。加一個「缺陣變化」項會令機率更準。主力今日缺陣而之前有打 → 隊友應該估高；主力最近缺陣、今日返嚟 → 隊友應該估低。
  - **H2（揀腿）**：缺陣變化大嘅腿（接手球員、主力復出時嘅隊友），莊家定價跟唔上，平注有正回報。
- **搜索過嘅舊記錄**：EXP-20261025-16（S_v3：隊友缺陣 γ，賽前名單，dev 上限 −0.0034，只計「今日缺陣」，冇計「最近缺陣」）、EXP-20261026-01（S_v3 shadow，已中止）、EXP-20261104-12 H2（21:00 後臨場缺陣，全隊所有線，冇效應）、EXP-20261103-15（MS）。今次嘅分別：計「今日 − 最近」嘅變化，包括主力復出（負方向）。
- **改到嘅檔案**：冇改 production code。harness：`docs/experiments/patches/nba_usage_shift/`。

## 語料
- 每個歸檔分析日（10-22…11-03）嘅 `Sportsbet_Odds_<tag>.json` + `nba_game_data_<tag>.json`，用 `nba_engine.legs.build_legs` 砌腿（即係 live 引擎）；基準機率 = `p_final`。
- 結果：ledger `settlement`（hit／miss，void 剔走）。價：package 入面嘅 Sportsbet 價（最後賽前刷新；EXP-20261104-12 量到 21:00 到收市價基本唔郁）。
- **缺陣變化**（每條腿，按項目 s）：
  - 隊友 k = 同隊、L10 平均分鐘 ≥ 20 嘅球員（唔包括本人）。
  - `今日_k` = package `injuries` 入面 k 係 Out／Doubtful／Suspension（開波前名單）→ 1，否則 0。
  - `最近_k` = 球隊對上 5 場（日期 < 美東比賽日）入面，k 冇出場嘅比例（球隊比賽日來自 11-03 `NBA_Team_Context.json`，按 cutoff 過濾；k 嘅出場日來自佢最新 `season_log` 截到 cutoff，同 EXP-20261103-15 修訂 1 一樣嘅重建）。
  - `份額_k,s` = k 最近 10 場平均 s ÷ 球隊每場平均 s（同一 cutoff）。
  - **shift_s = Σ_k 份額_k,s × (今日_k − 最近_k)**。正 = 今日少咗人；負 = 有人復出。
- **切分**：dev = 10-22…10-28；holdout = 10-29、11-01、11-02、11-03。holdout 只跑一次。

## H1：模型
- **候選**：`logit p = logit(p_final) + δ_s × shift_s`，δ 每個項目一個（4 個參數），只用 dev 擬合。
- **度量**：holdout log-loss，Δ（候選 − 基準），按比賽日 cluster bootstrap 2,000 次、seed 20261104。另報 shift ≥ +0.10 同 ≤ −0.10 兩組各自嘅 Δ。
- **判決**：holdout Δ 上限 ≤ 0 **而且** dev Δ < 0 **而且** δ 方向啱（正）→ 「值得做 forward 候選」（唔即時上線；要再過 model-regression-gate）。否則 REJECT／NEEDS MORE TESTING。

## H2：揀腿
- **接手組**：shift_s ≥ +0.10 嘅 over 腿；**復出組**：shift_s ≤ −0.10 嘅 over 腿；對照：其餘腿。
- **度量**：平注 ROI、校準（實際 − 1/價），組別 − 對照嘅差，日 cluster CI。
- **判決**：接手組 ROI 嘅 95% CI 下限 > 0 先算「抵買」；復出組 ROI 差 CI 上限 < 0 = 市場高估復出時嘅隊友（可以避開）。dev／holdout 分開報，樣本細就只報描述。

## 功效
- 缺陣變化 ≥ 0.10 嘅腿預計幾百條，ROI CI 大約 ±15pp；**細過呢個嘅效應量唔到**。log-loss 有約 7,000 條 holdout 腿，功效較好。

## 結果
見 `EXP-20261104-13-nba-teammate-absence-shift-results.md`。
