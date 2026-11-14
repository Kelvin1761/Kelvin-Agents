# EXP-20261114-02 HKJC 歷史引擎回放：忠實度閘

- **日期**：2026-11-14 ｜ **平台**：HKJC ｜ **決定**：**PASS（剔除真版降級賽日後）** → 開全量回放
- **計劃**：`docs/plans/2026-11-13-hkjc-historic-engine-replay.md` 第 3 步；門檻預先寫死喺 `hkjc_history_replay_fidelity.py`
- **對照**：「真版減能量」（Kelvin 2026-11-13）—— 回放冇 SpeedPRO 能量，真版先扣走能量小項

## 做法
歷史輸入生成器（`hkjc_history_replay_build.py`）→ 離線真流程（`hkjc_history_replay_run.py`：真 inject → skeleton，馬匹頁／賽果頁讀外置碟，未登記網址報錯）
→ harness dump（現行引擎，一行唔改）。2026-04-01..11-12：**488／488 場 Facts、Logic 全部成功**。
生成器同真 formguide 逐欄核對（2026-10-01）：修咗退出往績、第一仗日數、2026-05-03 新格式賽果。

## 結果
| 比較範圍 | 場數 | raw 場內 Spearman | 首選一致 | Gold 差 | Good 差 | capture@5 差 | 頭二差 |
|---|---|---|---|---|---|---|---|
| 全部共同場次 | 449 | 0.965 ✅ | 80.8% ✅ | −0.22 ✅ | **−2.67 ❌** | +0.07 | −1.11 |
| 剔真版段速死咗（harness 預設規則） | 389 | 0.972 ✅ | 81.7% ✅ | −0.77 ✅ | −2.57 ❌ | −0.51 | — |
| **再剔真版舊格式賽日**（`meeting_is_legacy_schema`） | **378** | **0.973 ✅** | **82.5% ✅** | **−0.79 ✅** | **−1.85 ✅** | −0.26 | −1.59 |

逐維度場內 Spearman（378 場）：stability 1.000、form_line 1.000、health 0.958、trainer 0.956、sectional 0.951、distance 0.930、shape 0.925、class 0.873。

## 點解剔除（唔係改門檻）
- 真版 2026-04 至 05 初有 7 個賽日係舊 pipeline：Logic `_data` 只得 ~8 欄（冇醫療、近六仗、賽績線表、體重趨勢、生涯標記；同程紀錄由 formguide 7 仗計）。
  嗰度係**真版降級**，回放反而完整；用佢量「回放忠唔忠實」係量錯嘢。規則同 `rescore_backtest.meeting_is_legacy_schema` 一樣，唔係新定。
- 段速死咗嘅賽日：harness `compare` 一向預設剔（`--exclude-dead speed_score`）。

## 要老實講
- Good（−1.85）同頭二選有中（−1.59）回放一致偏低，CI 跨零但方向一致 —— 似係冇能量、走位短評 (XW)、晨操。
  之後全部 A/B 係**回放對回放**（同一份輸入），所以固定偏差唔影響比較；但回放絕對數字唔可以同 live 直接比。
- 未剔除版本 Good 唔過，兩個版本都記低。
- 騎練分差異部分係回放用 2019 起舊季（`hkjc_history_replay_pit`），真版只用 2024 起；呢個係數據多咗。

**leakage-audit**：PASS —— 生成器每匹馬只取賽日之前嘅往績；馬匹頁按賽日切「近三季」再由 inject `filter_profile_as_of`；
騎練 PIT 由 harness 逐賽日 as-of；賽果頁（賽績線對手）只讀賽日之前。
