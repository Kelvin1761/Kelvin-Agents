# Wong Choi Instinct Registry（跨 Domain）

> **設計理念:** 受 ECC `continuous-learning-v2` Instinct 模型啟發。
> 將一次性嘅 SIP 修改升級為帶 confidence score 嘅長期學習機制。
> 每次覆盤/回測自動 re-evaluate 過往 SIP 嘅表現，追蹤佢哋嘅長期有效性。

---

## Instinct 格式

每個 Instinct 對應一個過往 SIP 或 improvement_log entry：

```yaml
---
id: SIP-RR17-wet-track-inflation
domain: au-racing           # au-racing / hkjc-racing / nba
category: track-condition   # 見下方分類表
confidence: 0.75            # 0.20 ~ 0.95
first_seen: 2026-03-15      # 首次建立日期
last_validated: 2026-04-04  # 最近一次覆盤驗證日期
hit_count: 12               # SIP 正確嘅次數
miss_count: 4               # SIP 錯誤嘅次數
status: active              # active / deprecated / merged / pending-review
source_sip: SIP-RR17        # 原始 SIP ID
target_file: 02d_eem_pace.md # 修改嘅檔案
notes: ""                   # 額外備註
---
```

---

## 分類表

### AU Racing 分類

| Category | 描述 | 例子 |
|----------|------|------|
| `track-condition` | 場地狀態判斷 | 濕地膨脹修正、場地預測偏差 |
| `pace-judgement` | 步速形勢預測 | 前速崩潰模式、步速類型判斷 |
| `eem-calibration` | EEM 能量判斷 | 高消耗馬崩潰判斷校準 |
| `jockey-signal` | 騎師/練馬師訊號 | 配備變動識別、首出馬訊號 |
| `draw-bias` | 檔位偏差 | 死檔規則、直線衝刺賽檔位 |
| `forgiveness` | 寬恕檔案 | 寬恕過度/不足校準 |
| `sire-bloodline` | 血統適性 | 濕地血統、距離血統 |
| `class-assessment` | 班次判斷 | 卡士碾壓、升班效應 |

### HKJC Racing 分類

| Category | 描述 | 例子 |
|----------|------|------|
| `track-condition` | 場地狀態判斷 | Going 條件、AWT 特殊判斷 |
| `pace-judgement` | 步速形勢預測 | ST vs HV 步速模式差異 |
| `class-assessment` | 班次升降判斷 | 卡士碾壓、升班效應 |
| `weight-loading` | 負重/減磅效應 | 頂磅判斷、見習騎師減磅 |
| `import-assessment` | 進口馬評估 | PPG/ISG 馬首出表現模式 |
| `jockey-signal` | 騎師/練馬師組合 | 騎練Win% 、換人效應 |
| `venue-pattern` | 場地特有偏差 | 沙田 vs 跑馬地偏差 |
| `body-weight` | 體重趨勢 | 增磅/減磅效應校準 |

### NBA 分類

| Category | 描述 | 例子 |
|----------|------|------|
| `player-props` | Props Line 校準 | 過高/過低 Line 識別模式 |
| `injury-impact` | 傷兵效應 | 傷兵對隊友 usage 率影響 |
| `matchup-pattern` | 對位防守 | 防守大閘效應校準 |
| `b2b-fatigue` | B2B 疲勞 | B2B 場次 Props 達標率 |
| `pace-environment` | 球隊節奏 | 節奏對 Props 影響校準 |
| `parlay-correlation` | 相關性風險 | SGP 相關性碰撞模式 |
| `props-volatility` | 波動率判斷 | CoV 門檻校準 |

---

## Confidence 演化規則

| 事件 | Confidence 變化 | 備註 |
|------|----------------|------|
| 覆盤/回測驗證正確 | +0.05 (cap 0.95) | |
| 覆盤/回測驗證錯誤 | -0.10 (floor 0.20) | |
| 連續 3 次正確 | +0.10 bonus | 額外獎勵穩定嘅 instinct |
| 連續 2 次錯誤 | 標記為 ⚠️ `pending-review` | 需要人手 review |
| Confidence < 0.30 | 自動建議 `deprecated` | 通知用戶決定 |
| Confidence > 0.85 | 建議升級為 Core Rule | 嵌入引擎嘅 resource 檔案 |

---

## 跨 Domain 遷移規則

| 條件 | 行動 |
|------|------|
| AU instinct confidence > 0.85 且 category 存在於 HKJC | 建議：「此 SIP 可能適用於 HKJC。」|
| HKJC instinct confidence > 0.85 且 category 存在於 AU | 建議：「此 SIP 可能適用於 AU。」|
| AU + HKJC 同一 category 嘅 instinct 同時 > 0.80 | 升級為 Cross-Domain Core Rule |
| NBA instinct | **不遷移**（完全唔同嘅運動） |

---

## 活躍 Instincts

> 以下為初始化時嘅空白紀錄。覆盤時由 `instinct_evaluator.py` 自動填充。

### AU Racing Instincts
_(暫無 — 首次覆盤後自動從 `00_sip_index.md` 遷移)_

### HKJC Racing Instincts
_(暫無 — 首次覆盤後自動從 SIP 記錄遷移)_

### NBA Instincts
_(暫無 — 首次回測後自動從 `_improvement_log.md` 遷移)_

---

## Deprecated Instincts

_(暫無)_

---

## 使用方法

```bash
# 覆盤後評估 instincts（AU/HKJC）
python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
  --registry ".agents/skills/shared_instincts/instinct_registry.md" \
  --domain au \
  --reflector-report "{覆盤報告路徑}"

# 回測後評估 instincts（NBA）
python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
  --registry ".agents/skills/shared_instincts/instinct_registry.md" \
  --domain nba \
  --backtest-report "{回測報告路徑}"
```
