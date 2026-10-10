# EXP-20261010-05 — HKJC 手調規則方向審計（4 個 removal arm，一個家族）

- **日期**：2026-10-10；平台：HKJC；**Stage 4 v3 `fixed_rule`**（只剷規則，冇 fit）
- **語料**：main `8171436a`，harness（production 路徑 + PIT），286 場（剔走 04 月 speed_score 死日）
- **Arms**：`docs/experiments/patches/hkjc_arm_no_{jockey_change,gear_removed,finish_trend,sip}.py`
- **多重比較**：4 個 arm × 4 指標當一個家族，Holm 調整

| 剷走 | 變動場數 | Gold Δ | Good Δ | NDCG@5 Δ (CI) | v3 判決 | Holm p（最強指標） |
|---|---:|---:|---:|---|---|---:|
| 換騎 −1.5 | 115 | 0.00 | **−1.40pp [−2.81, −0.34]** | −0.0014 | REJECT | 0.315（Good） |
| **配備「除去」−3** | 47 | 0.00（6/6 塊 0） | 0.00（6/6 塊 0） | **+0.0021 [+0.0002, +0.0048]** | **RANKING_WIN** | **0.016**（NDCG） |
| 完成時間趨勢 ±5 | 191 | +0.35pp | +1.40pp [−1.06, +3.52] | −0.0012 | REJECT | 1.000 |
| SIP +1 | 79 | 0.00 | 0.00 | −0.0014 | REJECT | 1.000 |

## 解讀

- **換騎 −1.5 有用，留**：剷走 Good 跌 1.4pp（CI 全負，Holm 後唔顯著但方向清楚）。EXP-20261010-02
  擴大語料話換騎 cohort 差距被騎師評分食晒 —— 喺全模型入面呢條規則仍然有獨立貢獻。
  「一刀切」嘅分類改良（換返熟手唔扣）留待 trainer_signal 審計，唔可以直接剷。
- **配備「除去」−3 冇用而且有害**：剷走後 Gold／Good 每個時間塊都零差，三個排名指標每塊都
  ≥ 0，NDCG CI 清零，Holm 後仍然顯著。原本 2026-07-10 用 v1 回測加入。
- **完成時間趨勢、SIP**：證據唔夠，維持現狀。

## 下一步（按 v3 規則）

配備 −3 剷走係 RANKING_WIN，要用**未睇過嘅 forward 賽日**（2026-10-11 沙田起）做一次性最終確認：
同一個 arm、同一個 harness，攢夠約 60 場先開。確認前唔改 live。

## Forward 確認：預先登記（2026-10-10 補充，未開）

- **窗口**：2026-10-11 起，有賽果嘅 HKJC 賽日；累積到 ≥ 60 場（大約 6 個賽日）先開，**只開一次**。
- **命令**（同一個 harness、同一個 arm，唔准改）：
  ```bash
  export PYTHONDONTWRITEBYTECODE=1
  H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
  python3 $H run --since 2026-10-11 --out fwd_base.jsonl
  python3 $H run --since 2026-10-11 --arm docs/experiments/patches/hkjc_arm_no_gear_removed.py --out fwd_gear.jsonl
  python3 $H compare fwd_base.jsonl fwd_gear.jsonl --stage4 fixed_rule --leakage-audit-passed
  ```
- **判決規則**（預先寫死）：Gold 同 Good 嘅 Δ 都 ≥ 0，同埋 NDCG@5 Δ ≥ 0 → 剷走 `GEAR_SIGNAL_WEIGHTS["gear_removed_pen"]`。
  任何一項 < 0 → 維持 −3，記錄 forward 失敗。唔准換指標、換窗口或者重開。
- 每週 Telegram review 會報 forward 進度，夠數就提示。
