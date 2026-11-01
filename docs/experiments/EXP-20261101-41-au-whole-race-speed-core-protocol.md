# EXP-20261101-41 預先登記：速度重建 2c —— 全程速度做速度分核心（取代 L600）

> 量度之前寫。結果另寫 `EXP-20261101-41-au-whole-race-speed-core-results.md`。計劃：`docs/plans/2026-11-01-au-speed-rebuild.md`。

- **日期**：2026-11-01；**平台**：AU；**baseline**：main 現行（近期加權已上線；`speed.py` A/A 一致）。
- **用戶**：「Ok go ahead. As long as we can see improve in analysis performance」。
- **前因**：EXP-40 —— 速度分有用係因為佢實質量「輸頭馬幾遠」（全程表現），唔係末段速度。
- **搜索過**：EXP-20260831-07（簡單標準 WinningTime）、EXP-20261009-05（WinningTime 近期加權，盲測中，terminal 09-27 起）、
  **EXP-20261016-02**（Sportsbet 全程速度 A_sb：AUC 0.6193 vs pace_figure 0.6010；S2 = 50/50 入 pace_perf，refit
  `RANKING_WIN` 但 Holm p 0.078）、**EXP-20261016-03**（S2 forward shadow，2026-10-17 起，15/41 日）。

## 同 S2 嘅分別

S2 係「L600 同全程各一半」；今次係**全程取代 L600**（重建原則：速度 = 能力 = 全程表現），同時拆走同一份資訊嘅
`full_time_speed` overlay（EXP-02 G1：官方逐駒時間 = 頭馬時間 + 輸距，r 1.0000）。

## 窗口（保護兩個進行中嘅 holdout）

- **只用 2026-08-05 → 2026-10-16**。2026-10-17 起係 S2 forward 窗，一場都唔讀（arm 建立時已經剔走）。
- 09-27 → 10-16 同 EXP-20261009-05 terminal 重疊（EXP-02 都用過）；呢個窗已經被 EXP-02 用嚟發展 S2，
  所以今次結果係**同一段數據嘅第二次使用**，證據等級低過真正 holdout，報告會照寫。

## 候選

A_sb 照 EXP-02 構造（`au_sb_total_speed_20261016.compute_asb`，`ContextStandard` 情境標準、point-in-time、
近期加權聚合、可靠度），唯一輸入係 Sportsbet 頭馬時間 + 輸距 × 0.17。

- **W（判決 arm）**：場內 ≥ 3 匹有 A_sb → `pace_figure_score = clip(60 + 20 × z(A_sb), 0, 100)`，冇 A_sb 嘅馬 = 60；
  少過 3 匹 → 原封用現行 pace_figure。`full_time = 0`（拆 overlay）。權重、係數全部唔變。
- **W_keep（只報告，消融）**：同 W 但保留 `full_time` overlay —— 量拆 overlay 嘅邊際。
- **S2_ref（只報告）**：EXP-02 S2 公式喺現行 baseline 上重現，對照用；**唔作判決**（S2 嘅判決係 forward）。

## 判決

1. replica：baseline 由 dump 重算 `ability` 同引擎一致。
2. 報告：A_sb leaf AUC 對 pace_figure（同一批馬）；覆蓋率。
3. **v3 `walk_forward_oos`**（08-05 → 10-16）+ **§8** 四 arm（refit `f92c8377…`）。單一判決 arm W，冇 Holm。
4. 上線規則：過閘 → 準備上線（仍然要 S2 forward 結果先決定點樣合併）；唔過 → REJECT，交 Kelvin。
5. 分層：馬匹數、首選 SP、今仗路程、首選跑法。

**Leakage**：A_sb 只用目標日之前嘅往績事件；標準只用 < 目標日嘅事件（EXP-02 已審）。
**限制**：數據第二次使用；冇 RQ 以外真值；窗短（約 50 日）。

## 唔准做

睇完結果改 z 尺度（20）、改 3 匹門檻、改 fallback、加 arm、伸延窗口入 10-17 之後。
