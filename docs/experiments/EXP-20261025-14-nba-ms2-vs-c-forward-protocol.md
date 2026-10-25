# EXP-20261025-14 「市場＋S_v2」（MS2）對 Layer C 嘅 forward 判決協議（未有數據之前凍結）

- **日期**：2026-10-25（Claude Code，用戶要求同 S_v2 shadow 接線一齊凍結）
- **承接**：EXP-20261025-13（S_v2 開發）。同 EXP-20261025-12（MS1）**並行**，用**同一把尺**；兩個測試互不影響，兩個 config 都有 SHA 釘住。
- **凍結時狀態**：ledger 入面帶 `season_rate_v2_*` 嘅腿 = 0（呢個 commit 之前冇任何 code 寫呢啲欄位）。評估工具實測 `AWAITING_DATA`。
- **工具**：`nba_ms_forward.py --model v2`；凍結設定 `nba_ms_forward_v2.json`，SHA256 `cbc78f1e03662d22bdd6aff39549482223ca758013189d398da54156f020f96a`。

## 1. 假設

喺同一批 live 腿、同一個報價時刻，`MS2: logit p = a_s + b_m·logit(clip(1/price,.02,.98)) + b_S·logit(clip(S_v2,.005,.995))` 嘅 Brier 好過現役 C（`calibrated:C-2026-10-22:06bc5c85…`）。

## 2. 凍結嘅 MS2 係數

S_v2 嘅常數全部喺 2025-26 例行賽 TUNE（12-01 至 02-28）揀，冇用季後賽。MS2 本身就 fit 喺 verified_dataset_v2 嗰 19 個 dev 日（04-15 至 05-15），5 個 terminal 日冇開。

| Stat | 截距 | 市場 | S_v2 |
|---|---:|---:|---:|
| PTS | −0.1909 | 0.7500 | 0.0930 |
| REB | −0.1339 | 0.3828 | 0.6092 |
| AST | −0.3416 | 0.7861 | 0.0768 |
| 3PM | −0.1570 | 0.4567 | 0.5592 |

開發證據：MS2 − C_refit = −0.00027 [−0.00117, +0.00068]（5 fold 依次 +0.0015、+0.0003、−0.0012、−0.0013、−0.0019）；MS2 − MS1 = −0.00027 [−0.00048, −0.00005]。

## 3. 樣本、功效、檢查點、判決、數據守則

**全部同 EXP-20261025-12 §3–§7 一字不改**，唯一分別係讀 `season_rate_v2_*` 欄位：

- 最新已發佈、開賽前快照；只計 Over、整數線；settlement `y ∈ {0,1}`；只計上面嗰個 C 版本；梯級權重 1。
- 檢查點：150 場（只可以因傷害而停）、400 場（第一次可以 KEEP）、800 場（最終；未 KEEP 即 REJECT）。
- KEEP 要以下全部成立：
  - Brier 差嘅 97.5% 比賽日 cluster CI 上限 < 0；
  - log-loss 差 < 0；
  - slope 喺 [0.85, 1.15]；
  - p ≥ 0.70 偏差嘅 95% CI 包 0；
  - S_v2 覆蓋率 ≥ 85%；
  - 零洩漏。
- 快照冇 `season_rate_v2_status` 欄位（部署前 code 寫嘅）就當 epoch 之前，唔計入覆蓋率。
- **額外守則**：S_v2 需要對手數據（`opponent_context`）。`no_opponent_context` 會計入覆蓋率分母，所以來源斷咗會令覆蓋率跌穿 85%，報 `INVALID_DATA`，唔會靜靜咁縮細樣本。

**功效現實**：開發效應（0.00027）細過 400 場嘅 MDE（≈0.00046），所以大有可能要去到 800 場（MDE ≈0.00033），而且有相當機會 REJECT。呢點喺睇數據之前已經寫低。

## 4. 同 MS1 嘅關係

兩個測試各自判決，唔會揀「邊個先過就用邊個」：如果兩個都 KEEP，要另外寫一份 MS1 對 MS2 嘅比較協議先揀。兩個測試同時進行，係多重比較，所以喺切換 live 之前，`model-regression-gate` 要用 Holm 調整兩個 p 值。

## 5. 唔准做嘅嘢

同 EXP-12：forward 期間唔改係數、S_v2 常數（`nba_season_rate_S_v2`）、檢查點或門檻；唔喺檢查點以外判決；KEEP 唔等於自動上線。S_v2 之後再有改良，要用新 model id 同新協議，唔可以改呢個。

## 6. 執行

```bash
cd .agents/skills/nba/nba_daily_auto
PYTHONDONTWRITEBYTECODE=1 python3 nba_ms_forward.py --model v2 --until YYYY-MM-DD
```
