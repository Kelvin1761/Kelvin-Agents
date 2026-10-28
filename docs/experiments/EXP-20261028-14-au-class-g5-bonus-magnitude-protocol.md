# EXP-20261028-14 預先登記：級數分「出賽 1–5 場、上仗頭 25%」加分幅度

> 量度之前寫。結果另寫 `EXP-20261028-14-au-class-g5-bonus-magnitude-results.md`。

- **提出**：用戶 2026-10-28（接 EXP-20261028-13）。該組加分馬喺模型頭 3 名剩餘超額 +23.4pp vs 冇觸發 +14.5pp ——
  方向啱，可能加得唔夠。描述唔等於因果，所以要 walk-forward 量。
- **語料**：`scratch/au_fq_weight_class_dump_20261028.py`，引擎 main `93f8050f`（已含 EXP-12 B1、EXP-13 C3），乾淨窗 2026-08-05 起。
- **mode**：`walk_forward_oos`（由數據揀數值）。合約 v3：fit 咗而冇 walk-forward 預測 → 直接 REJECT。

## 候選

只郁 `CLASS_MICRO_WEIGHTS["career5_placed_bonus"]`（live 2.31）。−0.82 未上名扣分唔郁。

- **網格**：{0, 1.0, 2.31, 3.5, 5.0, 7.0, 10.0}。每個值都用**真引擎**全語料重評一次（唔用 replica ——
  級數分跨 60 會觸發「近績分 ≥ 72 而級數分 < 60 → −4」，replica 喺 EXP-13 漏過）。
- **walk-forward**（同 `au_walkforward_refit.py` 一樣嘅窗）：乾淨賽日排序，頭 30 個賽日做 warmup，之後每 7 個賽日一個測試窗。
  每個窗只用**之前**嘅乾淨賽日揀值：
  - 合資格 = 訓練期 Gold ≥ anchor(2.31) **而且** Good ≥ anchor **而且** Gold + Good > anchor。
  - 揀合資格值嘅**中位數**（網格值，偶數個取較近 2.31 嗰個）；冇合資格 → 用 2.31。**唔取 argmax。**
- 候選預測 = 每個測試窗用嗰窗揀出嚟嘅值；baseline = 同一批測試場用 2.31。

## 判決

v3 `evaluate_full_record(mode="walk_forward_oos")`，只計測試窗場次（warmup 唔計）。
預先聲明分層：馬群大細 ×4、首選 SP ×5、**場內有冇 G5 加分馬**。任何一個分層 CI 全負 → 唔上線。
上線用嘅值 = 用同一規則、喺全部乾淨數據揀出嚟嘅值。冇 WIN → REJECT，維持 2.31。

## 唔准做嘅嘢

睇完結果改網格、改合資格規則、改窗、加候選（例如連 −0.82 一齊郁）。

## 已知限制

同一個 08-05 起嘅窗今日已經用過四次（EXP-11、12、13 同之前好多個）。
