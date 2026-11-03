# EXP-20261103-13 NBA 重寫：「模型先揀腿、再睇賠率」對現行 B2（協議，喺計任何結果前寫）

- **日期**：2026-11-03
- **平台**：NBA
- **假設**：一條唔睇價嘅 ESPN 模型（S_v4 季度產出率：預計分鐘 × 每分鐘產出，NB 分佈）揀腿、再用賠率做價值檢查，喺同一批賽前腿上嘅（a）單腿機率準確度唔差過現行 C 層，（b）每場穩膽組合命中率唔差過現行 B2 規則。**可證偽**：holdout 上 S 嘅 log-loss 顯著差過 C（CI 下限 > 0），或者組合命中率顯著低過 B2。
- **搜索過嘅舊記錄**：EXP-20261022-01／02／03（規則揀腿冇邊際優勢；莊家價每個 stat 都贏 L10；C 層 PASS）、EXP-20261025-11／13（S_v1／S_v2：REB／AST／3PM 追平市場、PTS 落後）、EXP-20261026-07／08（S_v4 季初權重）、EXP-20261024-02、EXP-20261027-21（B2 正式穩膽，模型預期 EV 負）、EXP-20261101-02／60（ESPN 單一來源）。
- **改到嘅檔案**：記錄階段冇改 production code。harness：`docs/experiments/patches/nba_rebuild/`。

## 語料
- 今季每個已歸檔分析日（`~/WongChoiData/Wong Choi NBA Analysis/<日> NBA Analysis/`），用當日資料夾嘅 `Sportsbet_Odds_<tag>.json` 同 `nba_game_data_<tag>.json`（最後一次賽前刷新；已開賽場次唔會被改寫）。
- **舊系統 baseline**：`replay_legacy.py` 用現行 `generate_nba_reports.py`（commit = 本分支起點 `144d5ef6`）逐場重跑，記低全部 candidate 腿同 B2 揀出嘅組合。SGM 真價重報唔到（已開賽），**≥2.0 門檻改用單腿價乘積**；兩邊（baseline／candidate）用同一個代用價，所以比較公平，但 ROI 唔係真實 SGM ROI。
- 結果：`~/WongChoiData/NBA_Market_Eval/ledger/*.jsonl` 嘅 `settlement` 行（hit=1、miss=0；void 剔走），以（日、球員、stat、線）配對。
- 機率欄（每條腿已記喺歸檔 `*.market_legs.json`）：`p_final`（C）、`season_rate_v4_prob_S`（S_v4）。新引擎要逐腿重現 S_v4 同 C（parity），否則唔准用新引擎數字。
- **切分**：dev ＝ 2026-10-21…10-28（7 日）；holdout ＝ 10-29、11-01、11-02、11-03（4 日）。holdout 只評估一次。

## Arm（固定，唔准加）
**機率（單腿，全部 milestone over 腿）**
| Arm | 定義 | 擬合 |
|---|---|---|
| M | `1/price` | 無（基準） |
| C | 現行 live：`a_s + 0.755·logit(M) + 0.140·logit(L10)` | 已凍結 |
| S | S_v4（唔睇價） | 已凍結 |
| MS | `a_s + β·logit(M) + γ·logit(S)` | 只用 dev |

**揀腿（每場一個組合，穩膽產品）**
| Arm | 定義 |
|---|---|
| B2 | 現行規則（replay） |
| K-C | 按 C 機率由高至低，同 B2 一樣嘅結構限制（唔同球員、同隊 PTS ≤2、同隊 ≤3、2–4 腿），逐腿加到乘積 ≥2.0；取聯合機率（獨立相乘）最高、乘積 ≤4.0 嘅組合 |
| K-S | 同 K-C，但排序同聯合機率用 S（「模型先揀腿」）；再加價值檢查：每條腿 `S ≥ 1/price` |
| K-MS | 同 K-C，用 MS |

## 度量同判決（預先登記）
- **機率 primary**：holdout log-loss；Δ（arm − C），按比賽日 cluster bootstrap 2,000 次、seed 20261103。另報 Brier、穩膽區（p ≥ 0.7）實際 − 預測。
- **揀腿 primary**：holdout 組合命中率同出手場數；secondary：代用價 flat ROI。Δ vs B2，同一 bootstrap。
- **判決**：機率層換成 arm X 要 holdout Δlog-loss 上限 ≤ 0（唔差過 C）**而且** dev Δ < 0。揀腿換成 arm Y 要 holdout 組合命中率 Δ 下限 > −5pp（non-inferior）**而且**出手場數 ≥ B2 嘅一半。都過唔到就用最簡單而唔差嘅版本（C + B2 規則嘅乾淨重寫）。
- **功效**：holdout 大約 40 場；組合命中率 SE ≈ 7–8pp，**細過 ~15pp 嘅差異量唔到**。單腿 ~7,000 行，log-loss 有功效。「量唔到」唔等於「冇差」。
- 只跑一次；唔准因結果加 arm、換指標、換窗。

## 結果
見 `EXP-20261103-13-nba-rebuild-formula-results.md`（跑完先寫）。

## 修訂 1（2026-11-03，跑 holdout 之前；只睇過 dev-only 除錯輸出）
- **發現**：歸檔 package 只有 10-28、10-29、11-03（同 10-27 部分）先計得到 S：10-22～10-26 冇存 `season_log`，10-27 冇逐場球隊欄，11-01／11-02 對手表係 `source_unavailable`（ESPN 轉換期）。照原協議 S／MS／K-S 只有 3 日數據，冇功效。
- **改法（只改 S 嘅輸入來源，唔改 arm、指標、切分、判決）**：S 一律用 as-of 重建輸入：
  - 每個球員嘅 `season_log` 取所有歸檔 package 入面最新、最長嗰份（ESPN），截到該場 `history_cutoff_day`（美東比賽日）之前；
  - 對手表用 11-03 嘅 `NBA_Team_Context.json`（ESPN，history_date_to 11-01）經 `nba_team_context.opponent_context(bundle, 對手, cutoff_day)` —— 函數本身按 cutoff_day 過濾，所以等同當日 as-of。
  - 洩漏檢查：截斷後最大日期一定 < cutoff_day（harness assert）；box score 終場數字唔會事後改。限制：只有喺最新 package 出現過嘅球員先有 log（轉隊／離隊球員可能缺），C／B2 照用歸檔 package 原值。
- 重建後 S 喺有歸檔 S_v4 嘅腿上要同歸檔值一致（parity），唔一致就唔准用。

## 修訂 2（2026-11-03，跑 holdout 之前）
- 修訂 1 嘅重建 S 同歸檔 S_v4 唔係逐腿一致（10-29 抽查：330 個球員 59 個 ESPN 賽績多咗／少咗一場、38 個數字有更正；機率最大差 0.0227）。原因係 ESPN 事後修訂，唔係 code。按修訂 1 自己嘅規則，重建值唔可以取代歸檔值。
- **改法**：有歸檔 S_v4 嘅腿用歸檔值（即 live 當時見到嘅數）；冇嘅（10-22～10-27、11-01、11-02）先用重建值。重疊腿嘅重建誤差（median／p95／max）同結果一齊報。arm、指標、切分、判決不變。
