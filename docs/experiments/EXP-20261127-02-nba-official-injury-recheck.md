# EXP-20261127-02 NBA 官方傷停報告重新量度（大細盤精選時代）

- 日期：2026-11-27（Kelvin：「重新量」）。類型：只量度，**唔改模型、唔接返生產**。
- 起因：改善空間清單見到 NBA `availability.official_level` 由 11-03 起 0%。查明係 EXP-20261101-60（11-02，Kelvin 決定）剷走官方報告嘅殘留欄。
  當時只量 5 日、只睇 SGM 穩膽（0 張改變）；而家主力係大細盤精選（11-10 起），最怕打得少（11-25 有一注精選上陣 8 分鐘輸）。
- 腳本：`docs/experiments/patches/nba_official_recheck/measure.py`（官方 PDF 解析照搬 11-02 剷走嘅 `nba_official_injuries.py`）；
  結果 `result.json`。官方 PDF（`ak-static.cms.nba.com/referee/injury/Injury-Report_<日>_<時>.pdf`）舊檔仲攞得到。

## 預先登記（結果出之前寫死，見 measure.py docstring）
- 2026-11-03 → 11-26；每場兩個時間點：bet = 21:00 production 快照（精選凍結），late = 開波前最後一份快照；官方報告 = 嗰刻或之前最新一份。
- 球員 = 嗰個快照有開盤嘅球員；ESPN／官方級別（冇列 = ok）；bad = DNP（所有腿 void）或者上陣 < 15 分鐘。
- 判斷：「官方有標、ESPN 冇標」bad 率高過兩邊都 ok ≥ 20pp、CI 唔包 0，**而且**影響開盤腿 ≥ 1% 或者精選 ≥ 3 注 → 建議重新接返做精選安全欄；否則確認停用。

## 結果
| 時間點 | 開盤球員 | 官方有標、ESPN 冇標 | 佢哋 bad | 兩邊 ok bad | 佔開盤腿 | 受影響精選 |
|---|---|---|---|---|---|---|
| bet（21:00） | 1,976 | **0** | — | 6.1% | 0% | **0** |
| late（開波前） | 2,444 | 5 | 2/5 | 6.1% | 0.23% | 0 |

其他格（late）：ESPN 未定＋官方 Out 4/4 bad；ESPN 未定＋官方未定 21/41；ESPN 未定＋官方 ok 1/27（3.7%）；兩邊 ok 144/2,367。

## 判決：**唔達標 → 確認停用**
官方報告喺精選凍結嗰刻冇提供 ESPN 以外嘅資訊；開波前先多出嘅少數（9 個球員、0.4%）精選已經凍結，影響唔到。
`availability.official_level` 已加入 `shared_wong_choi/resources/known_retired_fields.json`（改善空間清單唔再列）。

## 旁證（**唔喺預先登記範圍，只係假設**）
- ESPN「Day-To-Day」但官方「Available／Probable」嘅球員，late 27 個得 1 個 bad（3.7%），bet 32 個 6 個（18.8%）；
  ESPN DTD 整體 ~50% bad。即係 **ESPN 可能標得太緊**：穩膽規則「ESPN DTD → 唔入穩膽」可能剔走咗會正常上陣嘅球員。
  要驗證就要新登記（用之後嘅新數據），而且 SGM 而家只追蹤（AGENTS.md：NBA SGM 唔再開研究）→ 記低，唔開。
