# EXP-20261125-01 HKJC 市場尺接駁（今仗最終獨贏賠率做評估基準）

- 日期：2026-11-25　平台：HKJC　類型：評估工具（唔郁模型、唔郁排名）
- 起因：Kelvin「幫我做哂你講既升級」；市場尺 m1（EXP-20261124-90）只接咗 AU。
- 改動：`market_ruler.py --platform hkjc BASE.jsonl [CAND.jsonl]`；賠率來源 = `hkjc_history_replay_pit.load_all_rows_extended()`
  （同「上仗賠率」表同一個來源），按 (日期, 場次, 名次) 配，平頭馬 key 剔走。
- **今仗賠率只做評估基準**：唔入模型、唔揀注。模型只准用上仗賠率（AGENTS.md HKJC 明文例外）呢條冇郁。

## 配對檢查
- 回放 6,047 場：5,873 場每匹都配到賠率；剔走 186 場（`missing_price`）。
- 熱門（最低賠率）頭馬率 30.4%；平均 overround 1.225（≈ HKJC 獨贏彩池抽水）→ 配對正確。

## 結果（`base_live_20261122.jsonl`，walk-forward 5,679 場／614 賽日）

| | Δll（每場） | 判 |
|---|---|---|
| 獨贏 | −0.00029 [−0.00066, +0.00005] | 冇市場以外資訊 |
| 入頭三 | +0.00046 [−0.00098, +0.00195] | 冇 |

模型係數 β（獨贏，最後一次 fit）= −0.029。

## 讀法
- 同 AU 一樣：HKJC 模型排名改善好多，但係嗰啲資訊最終賠率已經有。HKJC 冇落注定義，所以呢個結論唔影響任何注單；
  但係如果將來要定 HKJC 落注規則，要先過市場尺 A（合約「市場尺 m1」用途 2）。
- HKJC 回放 6 季，樣本大過 AU 好多，CI 窄過 AU 一半。

## 可重現
```bash
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform hkjc \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/analysis/replay_all/v4/cons/base_live_20261122.jsonl"
```
