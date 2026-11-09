# EXP-20261109-02 HKJC 級數分用「賽前 365 日」往績代替「季內」—— REJECT

- **日期**：2026-11-09（睇結果之前寫）
- **平台**：HKJC
- **上游**：EXP-20261109-01（重建）、EXP-20260910-01（季初零出賽唔扣分）、EXP-20260929-03（新季多維度漂移）
- **搜索過嘅舊記錄**：冇用滾動窗代替「季內」嘅 HKJC 實驗

## 診斷（觸發呢個假設）

PIT 回放，場內上名 AUC：

| | 25/26（4–7 月，261 場） | 26/27 9/6–10/6（78 場） | 26/27 10/7–11/8（98 場） |
|---|---|---|---|
| 綜合分 | 0.7174 | 0.6655 | 0.6693 |
| 市場（收市賠率） | 0.7664 | 0.7594 | 0.7446 |
| `class_score` | 0.6179 | 0.5359 | 0.5394 |
| 季內上名率（覆蓋） | 0.6583（93%） | 0.5787（28%） | 0.6178（80%） |

市場跌 ~0.02，模型跌 ~0.05。`class_score` 跌最多（−0.080，CI [−0.114, −0.052]）。
佢嘅資訊主要嚟自「季內」上名次數（≥3 次 +4.39、0 次 −4）；新季開頭季內冇樣本，季中仍然薄。

## 假設

將 `class_score` 讀嘅「季內 (冠-亞-季-其餘)」換成**同一匹馬喺賽日之前 365 日**（`Date < 賽日`）嘅正式賽紀錄，
門檻同加減分完全唔變，Gold／Good 唔會跌，而且今季（9/6 起）`class_score` AUC 回升。

## Arm（只得一個，冇調參）

- **baseline**：重建後 production（branch `claude-hkjc-rebuild-20261109`）
- **R365**：`HorseFacts._season_record()` 回傳 PIT 賽果庫（`pit_backtest.load_all_rows()`，HorseID 對 `horse_code`）
  365 日窗內嘅 {starts, places, wins…}；搵唔到 HorseID 或者窗內冇出賽 → 回傳 None（同「冇季內紀錄」一樣，中性）。
  其他維度、權重、門檻全部不變。顯示文字照樣跟住變（純顯示）。

## 洩漏檢查

- 只用 `Date < 賽日` 嘅賽果；同日賽果唔入。
- `load_all_rows` 已經係 harness PIT priors 用緊嘅同一份資料（EXP-20261015-02 修過日期守衛）。
- 欄位只係名次，賽前一定拎得到。

## 判決規則（`docs/model-evaluation-contract.md`，`--stage4 fixed_rule`）

- 全紀錄 Gold／Good 點估計 < 0，或 6 個時間塊少過 4 塊 ≥ 0 → **REJECT**。
- 過咗 primary 但 CI 跨零 → 唔聲稱改善；記錄同埋交 Kelvin 決定。
- 次要（唔判決）：26/27 子集 `class_score` AUC、首選上名率。
- 唔換指標、唔換窗、唔試第二個窗長度去救。

## 命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --out base.jsonl --dump-matrix
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --arm docs/experiments/patches/hkjc_arm_rolling_class_record.py --out r365.jsonl --dump-matrix
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare base.jsonl r365.jsonl --stage4 fixed_rule --leakage-audit-passed
```

## 結果（2026-11-09，按上面規則，只開一次）

- 380 場配對（排除死欄位場次），252 場排名有變。
- **REJECT / primary_regression**：Gold −0.26pp [−2.03, +1.07]、Good −0.26pp [−1.36, +1.04]；
  6 塊入面 Gold 4 塊 ≥0、Good 3 塊 ≥0。今季（26/27，177 場）Gold／Good 各 −1.13pp，首選頭馬 −1.69pp。
- 次要：`class_score` 今季 AUC 0.5381 → 0.5536（有回升），上季 0.6189 → 0.6094。
- 解讀：365 日往績修好咗 leaf 本身，但同近六場名次（`form_score`／`consistency_score`）重疊，
  綜合排名冇得益 —— 同 AU「準、覆蓋闊、正交先有用」嘅教訓一致。唔試第二個窗長度。

## 今季下跌嘅結論

- 市場 AUC 都跌（0.766 → 0.745），所以有一部分係今季場次本身難估。
- 模型跌多約 0.03：最大係 `class_score`（季內往績新季冇料），其次同程、檔位；但檔位**原始號碼**嘅 AUC
  本身都由 0.592 跌到 0.551 —— 今季跑道對檔位冇咁敏感，唔係模型錯。
- 數據管線冇斷：`field_health --trend` 冇欄位變差，今季中性率低過上季。
- 用滾動往績補級數分 REJECT。冇證據支持即時改模型；跟進官方評分差距 forward（EXP-20261029-30，30/60）。
