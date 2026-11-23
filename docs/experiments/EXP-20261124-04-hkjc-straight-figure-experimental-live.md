# EXP-20261124-04 — HKJC：直路表現數字實驗性上線（Kelvin 2026-11-24）—— **未證實改善**

- 決定：Kelvin 2026-11-24「實驗性上線」（先例：EXP-20261119-06 連續藉口）。
- 證據（EXP-20261123-18 SF，六季直路 206 場，v5.2）：Δlog-loss −0.00100 [−0.00464,+0.00252]、AUC −0.0007 [−0.0088,+0.0073]、
  Gold +1.94、Good +2.91、頭二入頭三 +5 [−5,+15]、首選贏 −4 → **v5.2 REJECT（CI 跨零、AUC 護欄唔過）**；β 2021 起每季 +5.0～+6.8。
  直路組件（加檔號、經驗，EXP-20261124-03）更差，唔上。
- 上線：`hkjc_racing_engine/straight_figure.py`（只限沙田直路 1000 米）：raw' = raw + 5.04·(gap − 場均) − 0.16·(有 gap − 場均)；
  gap 由 `performance_figure.segment_gap`（唯一定義：最近 6 仗直路 ≥1 仗 − 最近 6 仗整體 ≥2 仗，換算今仗負磅）；標籤同入分共用。
  次序：初出馬練馬師之後、grade／排名之前。validation SCORE-004、manifest、grade_transparency、chip「直路表現好／差過平時（實驗性入分）」。
- 忠實度：40 場回放直路賽（sf_feats.pkl 最後 40 場；馬匹編號同負磅由賽果索引補，因為回放 Logic 冇 horse_code）逐匹 gap／has 同研究版最大差 0.0；11-22 live 模式（固定日期）R2 13 匹 −2.70～+1.31，其他場唔郁；
  頭二入位 16→16、頭二有頭馬 6→6、頭四 21→21。
- 標籤：之前（f359515a）「直路／泥地表現」用最近 6 仗入面嘅分段仗，改用同入分一樣嘅定義（最近 6 仗分段）。
- forward：`straight_figure_post_live`（退回 arm `patches/hkjc_arm_straight_figure_revert.py`），目標 40 場直路賽；退回版唔差就建議撤回。
- 已知差異：live 今仗負磅用排位表（`weight`），研究用賽後實際負磅（見習減磅／超磅會差 1–2 磅；表現數字 11-22 最大差 0.054 分）。
- Sol（Codex）覆核 2026-11-24：forward 原定 40 場（tracker 計全部賽事）會太早判 → 改 1,000 場；標籤顏色改跟入分方向；其餘（PIT、次序、SCORE-004、shadow、figure_w）冇問題。
