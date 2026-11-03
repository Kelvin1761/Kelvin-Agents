# EXP-20261103-15 結果：「模型先揀腿」唔贏市場錨定；機率層換 MS，揀腿保留 B2（乾淨重寫）

- **日期**：2026-11-03
- **平台**：NBA
- **協議**：`EXP-20261103-15-nba-rebuild-formula-protocol.md`（commit `da82be32`，修訂 1–3：`46bd0b44`、`5fa1475c`、`7257c01c`，全部喺跑 holdout 之前）
- **評估 commit**：`6f1871f8`；holdout 只跑咗一次。

## 語料
- 今季 10 個分析日、89 場、16,934 條 milestone 腿；有結算 13,968 條。
- baseline B2：現行 `generate_nba_reports.py` 逐場 replay（`replay_legacy.py`，0 錯誤），SGM 真價以單腿價乘積代替。
- S 來源（修訂 2）：歸檔 S_v4 5,768 條；重建 9,650 條；冇 1,516 條。重疊 5,341 條重建誤差 median 0.0000、p95 0.0013、max 0.0227。
- dev ＝ 10-22…10-28（6 日有數）；holdout ＝ 10-29、11-01、11-02、11-03（4 日）。

## 結果 1：單腿機率（holdout n=4,876）
| Arm | log-loss | Brier | Δ log-loss vs C [95% CI] | p≥0.7 實際−預測 |
|---|---|---|---|---|
| M（1/price） | 0.4091 | 0.1301 | +0.0117 [+0.0042, +0.0236] | −8.9pp |
| **C（現行）** | 0.3975 | 0.1269 | — | −2.3pp |
| S（唔睇價，「模型先揀腿」） | 0.4025 | 0.1301 | **+0.0051 [+0.0020, +0.0090]** | −3.3pp |
| **MS（市場＋S）** | **0.3936** | **0.1265** | **−0.0039 [−0.0049, −0.0026]** | −5.0pp |

dev：M −0.0144、S −0.0112、MS −0.0238 [−0.0534, −0.0025]（vs C）。
MS 係數（只用 dev 擬合）：a = PTS −0.4057、REB −0.2735、AST −0.4232、3PM −0.0624；β(市場) 0.9264、γ(S) 0.1099。

**判決**：MS 過閘（holdout 上限 ≤ 0、dev < 0）→ **KEEP**。S 單獨 holdout 顯著差過 C → 唔睇價嘅模型唔可以做主機率。

## 結果 2：揀腿（每場一個組合，代用價）
| Arm | dev 組合 | dev 命中 | holdout 組合 | holdout 命中 | holdout Δ vs B2 [95% CI] |
|---|---|---|---|---|---|
| **B2（現行）** | 32 | 28.1% | 27 | 48.1% | — |
| K-C | 40 | 47.5% | 38 | 42.1% | −6.0% [−37.5%, +13.1%] |
| K-S（模型先揀＋價值檢查） | 37 | 32.4% | 21 | 42.9% | −5.3% [−37.5%, +3.8%] |
| K-MS | 41 | 43.9% | 38 | 44.7% | −3.4% [−16.9%, +16.7%] |

**判決**：冇一個 K arm 過 non-inferiority（下限 > −5pp）→ 按協議保留 B2 規則。dev 同 holdout 方向相反，CI 闊過 ±15pp —— 同協議預先講嘅一樣，59–79 場分唔出揀法；**「量唔到」唔等於「一樣」**。代用價 ROI（B2 holdout +21.4%、dev −26.5%）只係描述，唔係真 SGM ROI。

## 新引擎同舊引擎嘅對齊（parity）
- 腿層（`parity_legs.py`）：16,934/16,934 條腿逐欄一樣；C 有 3 條差 ≤0.1pp（舊版將 <10 場嘅命中率先四捨五入到 1 位小數；新版用準確分數）。
- 模型層（`parity_model.py`）：21,164 條歸檔腿 S_v4 同 C 0 差。
- B2（`parity_b2.py`）：89 場 88 場逐腿一樣。唯一差異（11-03 CHI_PHI）來自 AST 中位數守門：舊版問 Monte Carlo 嘅 edge，新版問 S − 市場 ≥ 3pp（Maxey 嗰條 S 計唔到，新版擋咗）。
- 發佈防火牆（新 `nba_engine.publish` vs 舊 FW-01…14）：113 個歷史正式組合判決 100% 一致。

## 檢查
- **leakage-audit**：PASS —— 重建 S 嘅 season_log 截到美東比賽日之前（harness assert）；對手表經 `opponent_context(cutoff_day)` 過濾；MS 只用 dev 擬合。限制：重建數據係 11-03 先抓（ESPN 事後修訂，見誤差）。
- **退步**：S 單獨做主機率會變差（已唔採用）。holdout 只有 4 個比賽日，日 cluster bootstrap 嘅 CI 可能偏窄。
- **未測**：MS 接入 B2 嘅排序（B2 照用 C 算 edge 排序，同評估一樣）；MS 喺 S 缺失時退回 C（約 10% 腿）。

## 結論
用戶想要「模型先揀腿、再睇賠率支唔支持」。實測：唔睇價嘅 ESPN 季度模型 S 喺 holdout 顯著輸畀市場錨定嘅 C（+0.0051 log-loss），所以 S 只可以做市場嘅修正項，唔可以做主角。最好嘅機率公式係 **MS = 市場 ＋ 少量 S**（β 0.93、γ 0.11）。揀腿方面，簡單嘅「聯合機率最高」同 B2 喺今季數據分唔出高低，按協議保留 B2，但用乾淨 code 重寫（冇 MC、冇 ML、冇 10 因子引擎）。

**決定**：機率層 MS → KEEP；揀腿 K arm → NEEDS MORE TESTING（B2 保留）。
**commit**：見 `./保存.sh` 結果。

## 重跑
```bash
SP=<scratch>; R="$HOME/WongChoiData/Wong Choi NBA Analysis"; P=docs/experiments/patches/nba_rebuild
PYTHONDONTWRITEBYTECODE=1 python3 $P/replay_legacy.py $PWD "$R" $SP/replay/all.jsonl   # 舊引擎 replay（~1.5 分鐘／場）
PYTHONDONTWRITEBYTECODE=1 python3 $P/evaluate.py $SP/replay "$R" ~/WongChoiData/NBA_Market_Eval/ledger
PYTHONDONTWRITEBYTECODE=1 python3 $P/parity_legs.py $PWD "$R" $SP/replay/*.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $P/parity_b2.py $PWD "$R" $SP/replay/*.jsonl
```
