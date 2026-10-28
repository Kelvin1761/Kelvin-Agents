# EXP-20261025-11 獨立模型核心：L10 → 全季「分鐘 × 每分鐘產出」

- **日期**：2026-10-25（Claude Code）
- **基準**：origin/main a84e44d7；比較對象係 EXP-20261025-04 研究分支 `codex-nba-independent-shadow-20261025` 嘅 `study_v1_repair1/OOF.csv`（同一 5,305 行／32 場／15 日／同一 5 個 expanding fold）。
- **狀態**：**NEEDS MORE TESTING。** 開發日期已經俾之前研究睇過，唔係 holdout；冇改 live code、冇開 terminal 5 日。
- **已搜**：EXP-20261021-05、20261022-03、20261023-06、20261025-04／05／07，研究分支 EXP-06（L10 offset）、EXP-08（prop challenger 工具，`awaiting_new_data`）。

## 假設

EXP-04 嘅獨立核心只用 L10（extractor 每個球員只存 10 場 game log）。10 場估均值噪音大。改用 2025-26 全季 game log（nba_api PlayerGameLogs，常規賽＋附加賽＋季後賽，只取 `GAME_DATE <` 賽日、`MIN > 0`）：

- 分鐘 m = 指數加權平均（half-life 6 場）
- 每分鐘產出 r = 加權（half-life 15 場），以 30 分鐘 prior 收縮到球員全季產出率
- μ = m × r；X ~ NB(μ, k_s)，k_s 每 stat 一個，**只用常規賽（全部早過評估日）** 用矩估計
- p = P(X ≥ line)

協議（`Protocol.md` SHA256 `6c7cf054…be37`）同附加協議（`Protocol_Addendum1.md` `1e924dfc…8b71`）都喺睇對應結果之前寫低。

## 結果（OOF Brier，越低越好）

| 模型 | Brier |
|---|---:|
| Codex core（L10 Poisson/NB＋命中率） | 0.17516 |
| Codex full | 0.17624 |
| **S_raw（完全唔 fit 數據集）** | **0.17283** |
| **S_cal（逐 stat logistic 校準）** | **0.17308** |
| 市場 1/price（含水） | 0.17177 |
| 現役 C（擬合日期重疊，唔獨立） | 0.16834 |

主要比較 S_cal − core = **−0.00208，95% CI [−0.00470, +0.00039]**，5 fold 有 4 個負。按預登記規則（CI 上限 < 0 同 ≥4/5 fold）**未過**——方向清楚但 CI 跨零。

分 stat（S_cal／core／市場）：AST 0.1863／0.1881／0.1888；3PM 0.1657／0.1706／0.1663；PTS 0.1765／0.1765／0.1685；REB 0.1683／0.1703／0.1704。**REB、AST、3PM 單獨已經追平或贏市場；PTS 輸市場 0.008，係最大缺口。**

敏感度（預登記，只作描述，唔用嚟揀）：分鐘 HL {4,6,10} × 產出 HL {10,15,25} 九格全部係負方向（−0.0005 到 −0.0031）；越短 half-life 越好，m4_r10 CI 唔跨零，但係睇完先揀就係擇參，唔採用。

### 附加：S 有冇市場冇嘅資訊？（同 fold 重新 fit）

| 比較 | ΔBrier [95% CI] |
|---|---|
| 市場＋S（MS）− 市場＋L10（C_refit，即 live C 結構） | −0.00043 [−0.00122, +0.00021]，fold 3/5 負 |
| 市場＋S＋L10 − C_refit | −0.00002 [−0.00083, +0.00070] |
| MS − 市場 | −0.00221 [−0.00514, +0.00053] |

Fold 5 係數 [市場, S]：REB [0.54, **0.50**]、3PM [0.63, **0.41**]、AST [0.75, 0.12]、PTS [0.79, 0.07]。對比 C_refit 嘅 L10 係數得 0.03–0.14。**喺 REB 同 3PM，S 攞到嘅權重係 L10 嘅 4–5 倍**——即係獨立模型喺呢兩類 prop 有市場未完全反映嘅資訊；PTS 幾乎冇。

## 解讀

1. 獨立模型最大嘅單一改善位係**數據長度**，唔係加 context：只係由 L10 換全季加權產出率，就贏晒 Codex full 嘅所有 context block（EXP-04 嘅 block 消融全部 CI 跨零）。
2. 單獨做主模型仲未得：整體 S_cal 輸市場 +0.0013（CI 跨零），PTS 明顯輸。
3. 最有希望嘅路線係**將 C 入面嘅 L10 換成 S**（尤其 REB／3PM），而唔係直接用 S 取代市場。
4. 季後賽語料；季初例行賽、轉會、傷後復出未驗證。

## 下一步（未做）

- live extractor 加存全季 game log（或者每日跑一次 PlayerGameLogs，2 個 call），令 S 可以喺 forward 賽前快照入面計，綁 C 同一時刻價錢。
- 凍結 MS 對 C 嘅 forward 比較（同一批腿、同一報價時刻），先睇 REB／3PM。
- PTS 要另外處理：分鐘／出手量（FGA、FTA）分解，或者承認市場喺 PTS 有我哋冇嘅資訊。

## 接線（2026-10-25，shadow only）

- `nba_extractor.compact_season_log`：extractor 本來已經攞咗球員成季 log（同一個 fetch，冇新增 API call），之前只存 L10 同 `fit_inputs` 總數就丟咗。而家 `gamelog["season_log"]` 存晒每場（已喺賽事 US 日之前截斷、newest-first）嘅 MIN／PTS／REB／AST／FG3M／FGA／FG3A／FTA 同日期、季度、類型。
- `nba_season_rate.py`（`nba_season_rate_S_v1`）：上面凍結公式，`S_raw`（唔校準），剔季前賽／DNP，<5 場 null。
- line_analysis、sidecar、ledger `model_obs` 新增 `season_rate_prob_S／_version／_status／_inputs`。**唔入 `MODEL_VARIANTS`，冇任何選腿／EV／C 讀佢。** 開關 `NBA_SEASON_RATE_SHADOW_ENABLED`（預設 1）。測試釘住開／關 line_analysis 除新欄位外完全相同。
- 季初 extractor 只會喺本季 <10 場時補上季，所以 S 季初會混上季數據（研究冇測過跨季），`season_rate_inputs.seasons` 有記錄，評估時要分層。
- 下一步：累積 forward 腿後，同 C 同一時刻、同一批腿比較 MS（市場＋S）對 C；判決規則同功效要喺睇數據之前另行凍結。

## 重現

外置根 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-nba-individual-20261025/`：`gamelogs_2025_26.csv`、`rate_core.py <min_hl> <rate_hl>`、`blend.py <tag>`、各 `Summary_*.json`／`OOF_*.csv`。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 rate_core.py 6 15
PYTHONDONTWRITEBYTECODE=1 python3 blend.py m6_r15
```
