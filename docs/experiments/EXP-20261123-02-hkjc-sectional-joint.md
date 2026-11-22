# EXP-20261123-02 — HKJC：段速／場地訊號一齊入（L400 標準化＋泥地＋直路）—— SJ／SJ0 dev REJECT

- 日期：2026-11-23｜Kelvin：「測 L400 同其他段速改動一齊試」
- 協議（寫喺跑之前）：`patches/hkjc_sectional_joint/build_sect_joint.py` docstring。尺：v5（log-loss）。base = live ＋ J3（`scratch/joint_plus/jl_J3.jsonl`；J3 最後冇上線，但 SJ／SJ0 對 J3 嘅 Δ 已經量唔到改善，結論唔變）。
- 特徵：L1 回放 raw Δ（EXP-20261122-29）；A1 泥地相對草地、A2 泥地前段對標準、S3 直路 1000 往績（EXP-20261114-11 篩選 dev／holdout 都過；
  `patches/hkjc_replay_segment_screen.py --dump`）。做法同 J3：線性 L2 C=0.1、逐季 walk-forward、場內置中。

| 候選 | 內容 | β（2026：A1／A2／S3） | dev Δlog-loss | 其他 | 判 |
|---|---|---|---|---|---|
| SJ | L1 ＋ A1 ＋ A2 ＋ S3 | +6.34／+1.12／+2.06 | −0.00003 [−0.00039,+0.00034] | Good +0.36、AUC −0.0002 | REJECT |
| SJ0 | A1 ＋ A2 ＋ S3（冇 L1） | +6.67／+1.11／+2.21 | +0.00006 [−0.00028,+0.00041] | Good +0.16、AUC +0.0003 | REJECT |
holdout 冇開。

## 讀法
- 一齊入都量唔到：三個場地特徵只喺泥地（~10% 場次）／直路 1000（~5%）起作用，覆蓋太窄；同 J3 嘅 17 項（大部分場次都有）唔同。
- L1 喺 J3 之上冇邊際貢獻（SJ vs SJ0 只差 0.00009）。
- 呢啲訊號留喺顯示層（泥地／直路往績標籤），段速維度維持現狀。
