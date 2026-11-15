# EXP-20261116-01 結果：AU 上仗賠率 —— 三個 arm 全部 REJECT（Gold 跌）

- **預先登記**：[protocol](EXP-20261116-01-au-prior-odds-protocol.md)（`f1ffecf3`，跑之前 commit）。Kelvin 2026-11-16 明文批准測試。
- BASE = `FINAL.json`（BASE.commit `d59f67e6`），2026-08-05 起 3,736 場，v3 `walk_forward_oos`，賽日 bootstrap 2000。
- 接通：P 郁咗 28,843 匹（3,012 場排名變），P1 27,346 匹，P2 6,185 匹。冇 model code 改動（純離線 arm）。

| arm | Gold | Good 位置 | top3 capture@5 | NDCG@5 | top5 AUC | 分層 CI 全負 | 判決 |
|---|---|---|---|---|---|---|---|
| **P** 上仗賠率＋冇往績 | **−1.02 [−1.96, −0.16]**（b 1/6） | +0.32 [−0.55, +1.12] | 0.00 | +0.22 | +0.03 | 細場 ≤8、1201–1600m、首選前置（Gold） | **REJECT** |
| P1 只上仗賠率 | **−0.91 [−1.83, −0.09]** | +0.38 [−0.47, +1.14] | +0.03 | +0.27 | +0.03 | 1201–1600m、首選前置（Gold） | REJECT |
| P2 只冇正式賽往績 | −0.13 [−0.33, +0.05] | 0.00 | +0.01 | **−0.05 [−0.10, −0.003]** | +0.02 | — | REJECT |

場數（P）：Gold 21.49% → 20.48%、Good 27.03% → 27.36%、Pass 50.29% → 50.51%、冠軍 25.64% → 26.50%。

## 擬合出嚟嘅幅度

- 上仗賠率 β1（walk-forward 中位）**−3.77 分／log 單位**（賠率 ×2.7 → 扣 3.8 綜合分），最後一日 −3.18。逐日穩定、符號同 HKJC 一樣，
  但相對 AU 綜合分嘅分散大過 HKJC（HKJC −1.36 raw 分）—— 即係 logistic 認為上仗賠率喺 AU 有好強嘅入位資訊。
- 冇正式賽往績 β2 中位 −0.89（最後 −2.14）：同 HKJC 一樣，模型對初出馬偏高估，但幅度細。

## 點解入位資訊強但 Gold 跌

- 加咗之後**冠軍 +0.86pp、Good +0.33pp**，但 Gold（頭四揀中頭三）跌 1pp。即係首選更似市場熱門（贏多咗），但頭四嘅覆蓋變窄：
  上仗短價嘅馬互相擠入頭四，同市場重疊嘅程度升，模型原本獨立揀中嘅位置馬被擠走。
- 首選短價（$1–3）嘅場 Gold −1.62pp（CI 上界 +0.15）最傷；首選休 ≥90 日 −1.40pp（HKJC 都見到休後過度追熱門）。
- HKJC 用 v4 回放尺（主指標 log-loss）判 PASS；AU 把尺係 v3（Gold／Good primary）。logistic 優化嘅係逐匹入位機率（同 log-loss 一致），
  唔係頭四覆蓋，所以兩邊把尺唔同係判決唔同嘅部分原因。按 AU 現行把尺，呢個係清楚嘅 REJECT。

## 決定

唔用。三個 arm 都唔符合上線條件，亦唔係「冇代價」（Gold 點估計負，P／P1 CI 全負）。按預先登記，EXP-20261116-02 嘅 RP arm 唔跑。
`AGENTS.md` 唔使加 AU 賠率例外。

## 可重現

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_prior_odds_20261116.py \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-prior-odds-20261116"
```
判決 JSON、逐日 β、覆蓋：`EXP-20261116-01-evidence/`。
