# EXP-20261116-01 預先登記：AU 上仗賠率（HKJC EXP-20261115-07 嘅 AU 版）（睇判決結果之前寫）

觸發：HKJC EXP-20261115-07（上仗賠率，回放 holdout Δlog-loss −0.00315 Holm PASS、Good +1.11）。
**Kelvin 2026-11-16 明文批准**將「之前賽事嘅賠率」當 AU 候選模型特徵測試（「批准，測上仗賠率」）。今仗賠率（Formguide 頂部 `Flucs:`）永遠唔讀。
AU 以前冇測過（INDEX 冇記錄；`data_prep` 有解析 `last_flucs` 但只用嚟數「短價冇上名」，唔入分）。

## 特徵

來源：每場 `* Race N Formguide.md` 嘅往績行（`<場地> R<n> <YYYY-MM-DD> ... Flucs:$a $b ...`），取最後一個價做該仗最終賠率。
只計正式賽（`(TRIAL)`／`Barrier Trial` 剔走），只用日期**嚴格早過**今仗嘅往績。

- x1 = log(上仗最終賠率) − 場內平均；冇價嘅馬 = 0（中性）
- x2 = 冇正式賽往績（1／0）− 場內平均

綜合分 += β1·x1 + β2·x2。

## 覆蓋（只數，未睇結果）

判決窗 2026-08-05 起 3,736 場、35,819 匹：有上仗價 33,974（94.9%）、冇正式賽往績 1,838（5.1%）、有往績冇價 7、配對唔到 0。

## 洩漏審查（已做，未睇結果）

- 每 6 場抽 1 場（5,944 匹）：Formguide 冇一條往績同今仗同日（0）或者遲過今仗（0）；嚴格 `<` 過濾仲會再剔一次。
- 上仗日期同 dump 嘅 `days_since_last` 一致 5,553／5,611（99.0%）。賠率中位 $11、範圍 $1.1–$201，合理。
- 上仗最終賠率喺上仗賽後已公開 → 今仗賽前一定拎到。冇未來資訊。今仗 `Flucs` 唔讀。

## 幅度：walk-forward 擬合（同 EXP-20261113-41 一樣做法）

每個賽日 d：用 d 之前所有賽日（由 2026-08-05 起）嘅賽果擬合 logistic「入位 ~ a + b·(綜合分 − 場均) + c·x」，
β = c ÷ b（b ≤ 0 → β = 0），夾喺 [−10, 10]。頭 20 個賽日 warm-up，β = 0。即係每個賽日嘅 β 都冇睇過當日賽果。

| arm | 用咩 |
|---|---|
| **P**（主 arm） | x1 + x2 |
| P1 | 只 x1（上仗賠率） |
| P2 | 只 x2（冇正式賽往績） |

## 判決

BASE = `FINAL.json`（`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/`，BASE.commit `d59f67e6`；
之後 AU 引擎 commit 只係顯示／直路幾何（全語料排名零差）同 `au_eval` refactor）。2026-08-05 起 3,736 場。
v3 `evaluate_full_record` `walk_forward_oos`，ranking metric = top3 capture@5、NDCG@5、top5 AUC，賽日 bootstrap 2000。
分層：馬群、地況、首選 SP、路程、首選跑法，加**首選距上仗日數**（冇／<90／90+；HKJC EXP-20261115-09 發現休 ≥90 日會過度追熱門）。

- **上線條件**：PRIMARY_WIN 或 RANKING_WIN，三個 arm 做一個 family **Holm** 後 p < 0.05，冇分層 CI 全負。
- 「冇代價」：Gold、Good 點估計都 ≥ 0、冇分層 CI 全負 → 可以交 Kelvin 決定（同 EXP-20261113-24 一樣）。
- 其餘 REJECT。所有數值（warm-up、夾值、分層）喺睇結果之前定死，冇搜索。冇過嘅 arm 唔會 commit model code。
- 上線另外要：`AGENTS.md` 寫明 AU「上仗賠率」係模型 methodology 一部分（HKJC 例外只限 HKJC）；live 實作同 replica 逐匹對比。

## 命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_prior_odds_20261116.py \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-prior-odds-20261116"
```

結果：`EXP-20261116-01-au-prior-odds-results.md`；判決 JSON：`EXP-20261116-01-evidence/`。
