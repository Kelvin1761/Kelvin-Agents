# EXP-20261127-71 結果：tennisexplorer 縮寫名連結 —— KEEP 候選（ITF／UTR）；開關未開，等 Kelvin 決定

- **日期**：2026-11-27 · **平台**：Tennis · 協議（連修訂 1、2）：`EXP-20261127-71-tennis-te-identity-link-protocol.md`，全部喺結果之前 commit。
- **分工**：Claude 寫連結同評估、判決；Codex Sol 覆核兩次（code 一次、結果一次，無人值守 runner 派）；Terra 嘗試實作冇交貨（redo）。
- **生產冇郁**：`TENNIS_ABBREV_LINK` 預設關。

## 連結
`identity.plan_abbreviated_merges`：TE「姓 + 首字母」player ↔ 全名 player，要雙向唯一 ＋ 同日（±1）同對手共同出場（TE 往績對 Sportsbet 場次）＋ 冇曾經對賽 ＋ 排名巡迴唔衝突。
外置碟 A1 副本：1,404 組、76,776 行 repoint、self-match 0。人手抽 60 個（兩次各 30）**0 錯**。合併後刪走縮寫拼法嘅全域別名（`apply_abbreviated_merges`）。

## 判決項（預先登記）
母體 2,714 場（Sportsbet 2026-10-01…11-25，有賽果同開賽前獨贏價）；兩邊各 72 場身份爭議 error 剔走 → 2,642 場；受影響（特徵 hash 唔同）2,340 場（89%）。

| | log-loss A1 − A0 [95% CI，按日 bootstrap 2,000] |
|---|---|
| **主指標（受影響場次）** | **−0.0249 [−0.0302, −0.0199] → KEEP 候選** |
| ITF（1,294） | −0.0221 [−0.0314, −0.0142] |
| UTR（370） | −0.0791 [−0.0988, −0.0613] |
| Challenger（618） | −0.0005 [−0.0019, +0.0006] |
| 其他（58） | −0.0016 [−0.0066, +0.0041] |

絕對值：A0 0.6833 → A1 0.6585；**市場 0.5469** —— 模型準咗，但仍然大幅輸市場（差距收窄約 18%）。Brier 0.2445 → 0.2328（市場 0.1843）。

## 事後敏感度（只報告，唔重判；回應 Sol「高」級意見）
1. **連結喺比賽日之前已經可以成立**（生產做得到嘅情況）：1,051 場，−0.0221 [−0.0292, −0.0153]；ITF −0.0200、UTR −0.0525、Challenger +0.0030（跨零）。
   要靠今場或之後證據先成立嘅 361 場：−0.0959（大得可疑，見 2）。
2. **重播日期洩漏（新發現）**：TE 有時將比賽記早一日，按 match_date as-of 重建特徵時，**今場賽果會以「前一日」出現喺往績**（H2H／近況偷睇）。A0 188 場、A1 391 場中招。
   **剔走兩邊任何一邊有洩漏嘅場次**：乾淨 1,952 場 **−0.0219 [−0.0281, −0.0165]**；ITF −0.0190 [−0.0280, −0.0113]、UTR −0.0666 [−0.0915, −0.0436]、Challenger −0.0003（跨零）。
   → 效果唔係靠洩漏；同生產可行子集（−0.0221）一致。**以後所有網球 as-of 重播都要剔走「同對手、日期 = D−1」嘅往績**。
3. 跨來源重複計算（Challenger／巡迴賽 TE＋TML／Sackmann）：Challenger 冇改善亦冇變差。

## Sol 覆核（摘要，`patches/tennis_te_link/results/sol_review.md`）
計法重算吻合；89% 場次 hash 變、1,867 場機率變；ITF＋UTR 佔淨改善 99.3%；最大保留係實時可用性（已用敏感度 1、2 回應）。

## 決定
**KEEP 候選（ITF／UTR），交 Kelvin 決定開唔開 `TENNIS_ABBREV_LINK`。** 理由：主指標過、生產可行子集同乾淨子集都過、人手 60 個 0 錯。
保留：(1) 只改善模型勝負機率，**模型仍輸市場 ~0.12 log-loss**，對精選／ROI 嘅影響未量（精選大部分係 Challenger，呢度冇效果）；(2) props（讓局、贏一盤）未評；(3) 開咗之後要 forward 監察。
開嘅方法：生產 launchd 環境加 `TENNIS_ABBREV_LINK=1`（`merge_identities` 每日 run 會自動連，idempotent）。

## 重跑
```bash
X=<外置碟資料夾>; python3 docs/experiments/patches/tennis_te_link/evaluate.py apply --db $X/A1.db
SHARD=i/3 python3 .../evaluate.py score --db $X/A0.db --out $X/A0_i.json   # A1 同樣
python3 .../evaluate.py compare "$X/A0_0.json+..." "$X/A1_0.json+..."
```
