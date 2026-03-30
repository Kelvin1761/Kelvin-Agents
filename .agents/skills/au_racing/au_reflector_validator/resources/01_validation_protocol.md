# AU 驗證協議 (Validation Protocol)

> 同 HKJC 版本大致相同，以下為 AU 特有差異。

## 成功門檻

### 黃金標準
- Top 2 入 Top 3；Top 3 包含實際前三名全部

### 最低門檻 (2-of-3 Rule)
- 預測 Top 3 中至少 2 匹入前三名

### 豁免條件
同 HKJC 版本 + 額外：
- 🌧️ 極端濕地爆冷（場地突然升至 Heavy 9+）

## 一致性覆核標準
- 穩定（3/3 Top 3 相同）→ ✅
- 大致穩定（2/3 相同）→ ⚠️
- 不穩定（<2/3 相同）→ ❌

## 缺口分析模板
同 HKJC 版本（見 `hkjc_reflector_validator/resources/01_validation_protocol.md`）。

## 熔斷機制
同一場連續失敗 3 次 → 強制停止 → 通知用戶。
