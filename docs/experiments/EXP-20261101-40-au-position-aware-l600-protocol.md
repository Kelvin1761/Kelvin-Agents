# EXP-20261101-40 預先登記：速度重建 2b —— 用 800m／400m 位置估本駒末段 600m

> 量度之前寫。結果另寫 `EXP-20261101-40-au-position-aware-l600-results.md`。計劃：`docs/plans/2026-11-01-au-speed-rebuild.md`。

- **日期**：2026-11-01；**平台**：AU；**baseline**：main（`speed.py` A/A 39,745／39,745 一致，近期加權已上線）。
- **用戶**：「rebuild the speed section … speed … should be reflecting a horse's ability」；「go ahead … it would be good if we can have better performance」。
- **前因**：可行性（3,055 場 RQ × Sportsbet 配對、11,840 匹次）：現行「賽事 L600 + 輸距 × 0.17」場內同真實末段 600m 相關 0.599
  （= 純粹按輸距排）；加 800m／400m 位置學出嚟嘅估算式，後半段 1,179 場測試 0.906。
- **搜索過**：EXP-20261013-10（位置 × 0.877 馬位人手常數，差過現行 —— 今次係由真值學）、EXP-20261101-39（換標準唔加分；
  需要新資訊）、2026-07 QLD shadow（只有 6 場）。

## 候選（單一改動）

只改每仗嘅本駒末段估算，標準、聚合（近期加權 0.8^k）、同場比較全部唔變：

```
現行   own_i = l600_delta_i + 0.17 × margin_i
候選   own_i = l600_delta_i + g_D(x_i)
x_i = [1, margin, margin², p400, p800, p400 × margin, finish, 冇位置]
      p400 = (400m 位置 − 1) / (馬數 − 1)；p800 同理；finish = (名次 − 1) / (馬數 − 1)；冇位置 → 0.5 同旗號 1
g_D = 對「RQ 真實本駒末段 600m − Sportsbet 賽事 L600」做 OLS，只用往績日期 < 目標日 D 嘅 RQ × Sportsbet 配對（point-in-time）
```

- 配對：RQ XML（`AU_Racing_Time_Evidence/*.zip`，逐駒 200m 分段，末段 600m = 最後 3 段）同 Formguide 往績行，
  按（場地、日期、場次、馬名）。賽事原秒用 EXP-31 賽事表（可靠 = 最新來源 ≥ 2026-08-24）。
- 訓練少過 2,000 匹次 → 該日用現行公式（fallback，照報次數）。
- 冇馬數或者冇名次嘅往績行 → 現行公式。

## 判決

1. replica：baseline 同引擎一致。
2. 報告：RQ 時間 holdout（每個目標日只見之前數據）末段估算場內 Spearman；leaf AUC；EXP-39 式逐匹 walk-forward logistic
   增量資訊（只報告）。
3. **v3 `walk_forward_oos`** 全紀錄（2026-08-05 起）+ **§8** 四 arm（refit 程序 `f92c8377…`）。單一 arm，冇 Holm。
4. 上線規則：過閘 → 上；唔過 → 交 Kelvin（佢 AU 取捨：Good 點估計 ≥ 0、Gold 跌喺雜訊內）。
5. 分層：馬匹數、首選 SP、今仗路程、跑法（前置／守中／後上）。

**Leakage**：g_D 只用目標日之前嘅 RQ 賽事；特徵只用往績行本身（賽前已知）。
**限制**：估算式喺昆士蘭學，套落其他州。冇其他州真值，照寫。

## 唔准做

睇完結果加特徵、改 2,000 門檻、改配對規則、加 arm。
