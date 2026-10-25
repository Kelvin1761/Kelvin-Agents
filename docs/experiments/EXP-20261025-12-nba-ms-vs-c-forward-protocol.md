# EXP-20261025-12 「市場＋S」對 Layer C 嘅 forward 判決協議（未有數據之前凍結）

- **日期**：2026-10-25（Claude Code，用戶要求喺未有 forward 數據之前凍結）
- **承接**：EXP-20261025-11（離線：MS − C_refit = −0.00043 [−0.00122, +0.00021]，CI 跨零，3/5 fold）。S shadow 由 cf3c2960 開始寫入 ledger。
- **凍結時狀態**：ledger 入面帶 S 欄位嘅已結算腿 = 0（10-26 production 快照喺部署前寫，冇 S 欄位；評估工具實測 `AWAITING_DATA`）。
- **工具**：`.agents/skills/nba/nba_daily_auto/nba_ms_forward.py`；凍結設定 `nba_ms_forward_v1.json`，SHA256 `e4a1c1594e48bfcfacf7c2229259a93f5bfcfbb9bd910126e72a6fdd92f8f694`（測試釘住，改一個字都會紅）。

## 1. 假設

喺同一批 live 腿、同一個報價時刻，將 C 入面嘅 L10 命中率換成獨立模型 S，即
`MS: logit p = a_s + b_m·logit(clip(1/price,.02,.98)) + b_S·logit(clip(S,.005,.995))`，
機率準確度（Brier）好過現役 C（`calibrated:C-2026-10-22:06bc5c85…`）。

## 2. 凍結嘅 MS 係數（只用歷史，唔用 forward 數據 fit）

fit 喺 verified_dataset_v2 19 個 dev 日（2026-04-15..05-15，季後賽／附加賽）；5 個 terminal 日冇開。逐 stat logistic（C=1），每個 event×球員×stat 梯級權重 1。

| Stat | 截距 | 市場 | S |
|---|---:|---:|---:|
| PTS | −0.1991 | 0.7516 | 0.0986 |
| REB | −0.1537 | 0.4542 | 0.5835 |
| AST | −0.3398 | 0.7031 | 0.1882 |
| 3PM | −0.2056 | 0.5924 | 0.3911 |

C 同樣係季後賽 fit，兩邊同樣要面對例行賽 regime 轉移，所以呢個比較係公平嘅。forward 期間**兩邊係數都唔准改**。

## 3. 樣本

- **來源**：NBA market ledger 嘅 `model_obs`，沿用 ledger 規則：每隻腿取最新、已發佈、開賽前嘅快照（排除 warmup、post-tip、late write、no_prediction、季前賽），只計 Over、整數 milestone。
- **結果**：只計 settlement `y ∈ {0,1}`；void 或未結算唔計。
- **C 版本**：`probability_model_id` 一定要係上面嗰個 C。live C 一換，之後嘅腿唔再計入（唔會混版本）。
- **S 狀態**：`season_rate_status = ok` 同埋版本 `nba_season_rate_S_v1`。快照冇 S 欄位（部署前嘅 code）就當 epoch 之前，唔計入覆蓋率。
- **配對**：MS 同 C 用同一隻腿、同一個 `price_at_model`，兩邊永遠係同一批行。
- **權重**：每個 event×球員×stat 梯級總權重 1，避免梯級多嘅球員主導結果。

## 4. 功效同檢查點（喺睇 forward 數據之前計好）

用離線 OOF 估計：每場比賽（event）嘅加權 Brier 差 SD ≈ **0.00301**（32 場）。例行賽每晚大約 7–10 場，所以用場次做計數單位；CI 就按比賽日 cluster（同一晚嘅腿有相關，較保守）。

| 檢查點 | 最少已結算場次 | 最少比賽日 | 用途 | MDE（80% 功效） |
|---|---:|---:|---|---:|
| 傷害檢查 | 150 | 15 | 只可以因為「MS 明顯差」而停（95% CI 下限 > 0 → REJECT_HARM）；**唔可以因為好而提早採用** | — |
| 主要分析 | 400 | 30 | 第一次可以判 KEEP | ≈0.00046 |
| 最終分析 | 800 | 60 | 最後一次；未 KEEP 即 REJECT，唔再延長 | ≈0.00033 |

兩次成功判斷各用 **97.5% 雙尾**區間（兩次 look 共用 α≈0.05）。離線效應 0.00043 大約喺主要分析嘅 MDE 邊緣，即係**頗大機會要等到最終分析**，而離線估計通常偏樂觀（winner's curse），所以結果係 REJECT 都唔出奇。按例行賽節奏，400 場大約喺 12 月中，800 場大約喺 2 月。

## 5. 判決（喺主要／最終分析時，全部要成立先 KEEP）

1. 加權 Brier(MS) − Brier(C) 嘅比賽日 cluster bootstrap 97.5% CI 上限 < 0（4,000 次，seed 20261026）；
2. log-loss 差點估計 < 0；
3. MS 校準 slope 喺 [0.85, 1.15]；
4. MS 高機率區（p ≥ 0.70）`mean(p) − 命中率` 嘅 95% CI 包 0（穩膽區唔可以系統性高估）；
5. 數據守則通過（見 §6）。

- **REJECT**：CI 下限 > 0、點估計 ≥ 0，或者最終分析都未 KEEP。
- **NEEDS_MORE_TESTING**：只可以喺主要分析出現，即係等到 800 場再判。
- 分 stat、選中腿（`picked`）、跨季 S、價帶全部只係**描述**，唔可以用嚟揀「只換 REB」之類嘅子集；要做就另開新協議、用新數據。

## 6. 數據守則（唔過就報 `INVALID_DATA`，先修 pipeline，唔判模型）

- S 覆蓋率（S ok ÷ 帶 S 欄位嘅 C 腿）≥ 85%；
- 洩漏：`season_rate_inputs.last_game_date` 一定要早過賽事 US 日，命中數一定要係 0。

## 7. 唔准做嘅嘢

- 唔准喺 forward 期間改 MS 係數、S 公式（`nba_season_rate_S_v1`）、檢查點、門檻或 bootstrap 設定。要改就另開新協議，已經睇過嘅數據唔可以當新證據。
- 唔准喺 150／400／800 以外嘅時間做判決；日常可以睇 `ACCUMULATING` 狀態同描述數字，但唔准因為描述數字而行動。
- **KEEP 唔等於自動上線**：切換 live 機率層仲要再行 `model-regression-gate`，同埋用戶批准。

## 8. 執行

```bash
cd .agents/skills/nba/nba_daily_auto
PYTHONDONTWRITEBYTECODE=1 python3 nba_ms_forward.py --until YYYY-MM-DD [--output <路徑>]
```

只讀 ledger，唔寫任何嘢，亦唔影響任何機率或選腿。
