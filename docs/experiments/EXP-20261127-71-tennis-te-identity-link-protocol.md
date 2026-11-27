# EXP-20261127-71 協議：tennisexplorer 縮寫名球員連結 —— 預先登記（睇結果之前寫）

- **日期**：2026-11-27 · **平台**：Tennis · **決定人**：Kelvin 2026-11-27「go」（EXP-20261127-70 建議第 1 項）
- **起因**：EXP-20261127-70：TE 往績掛喺「姓 + 縮寫」player（如「Amarilla R.」），`plan_merges` 只合併完全同名，所以冇連到 Sportsbet 全名 player；ITF 有往績 46% → 連結後上限 ~84%、UTR 23% → ~80%。

## 假設
**H1**：連結之後，勝負模型嘅往績 nudge（recent_form、tournament_level、round、H2H、fatigue）喺受影響場次開始運作，令模型勝負機率 log-loss 改善。
（背景：EXP-20261027-06 消融 nudge 冇貢獻 —— 可能因為一半球員根本冇往績，nudge 一直係中性。）

## 連結規則（實作前凍結；睇結果之後唔准改，改 = 新協議）
TE player 名格式 `<姓（一個或多個字）> <首字母>.`；全名 player（任何 provider，非縮寫、非雙打、非 placeholder）。正規化：NFKD 去重音、細楷、連字符當空格。
1. **配對鍵**：全名嘅最後 k 個字（k ≥ 1）== TE 姓，而且全名第一個字首字母 == TE 首字母。
2. **雙向唯一**：該 TE player 只配到一個全名「人」（同名重複紀錄如兩個「Ramiro Amarilla」當同一個人，一齊併入），該全名「人」亦只配到一個 TE player。
3. **共同出場證據（必需）**：最少一次 —— TE player 喺日期 D 有往績對手 X，而全名 player 喺 D ± 1 日有 Sportsbet 場次，對手名同 X 相容（X 嘅姓 + 首字母同 Sportsbet 對手全名相容，規則同 1）。
4. **反證即拒**：兩者曾經對賽（`_played_each_other`）；或者兩者都有排名而排名唔一致（沿用 `plan_merges` 嘅排名守衛）。
5. 經現有 `apply_merges` 執行（canonical 沿用佢嘅規則）。

## 評估
- **語料**：生產 DB 一致備份（外置碟），兩份：A0（唔連結）、A1（連結）。
- **母體**：Sportsbet 場次 2026-10-01 … 2026-11-25，有賽果（`match_results` winner）、有開賽前獨贏價（兩邊、最早報價 MIN(id)）。
- **方法**：兩個 arm 都用同一份 code `assemble_match_feature_snapshot(match_id, persist_derived=False)` 按比賽日 as-of 重建特徵，再 `predict_match_probability`。
- **受影響場次** = 兩個 arm 特徵 JSON（剔走時間戳）有任何唔同。
- **主指標**：受影響場次上 mean log-loss(A1) − mean log-loss(A0)；按比賽日 cluster bootstrap 2,000 次，seed 20261127。
- **KEEP 候選**：主指標 95% CI 上限 < 0 → 交 Kelvin 決定上線，並過 `model-regression-gate`。
- **次要（只報告）**：按級別（ITF／UTR／Challenger／其他）；模型 vs 去水市場 log-loss 差距嘅變化；Brier；窗口內精選有幾多注嘅場次受影響。
- **連結準確度**：Claude 人手抽 30 個連結核對（TE 往績同 Sportsbet 場次對得上），錯 ≥ 2 個就唔上線、改規則另開協議。

## 限制（預先講明）
- 按 match_date as-of 重建，唔係真正 point-in-time（TE 往績入庫時間未必早過開賽）；兩個 arm 用同一方法，所以 A1 − A0 比較公平，但對市場嘅絕對差距唔係 PIT 證據。
- 只評勝負機率；props（讓局、贏一盤）另案。
