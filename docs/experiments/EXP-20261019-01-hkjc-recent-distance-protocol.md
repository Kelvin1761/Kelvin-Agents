# EXP-20261019-01 — 同程上名只計近 N 仗：預先登記

- **登記日期**：2026-10-19，喺跑任何 arm **之前** commit
- **平台**：HKJC；**Stage 4 v3 `fixed_rule`**（固定 N，冇 fit）
- **觸發**：EXP-20261018-13 —— 完整往績（現行 live）對比舊截斷版，回放 Good −1.45pp CI 全負；推斷「近期同程」好過「生涯同程」。
  Kelvin 2026-10-19：以現行 live（完整往績）做 baseline，N 用細家族加 Holm。

## Baseline 同候選

- **Baseline**：branch `claude-hkjc-recent-distance-20261019` 嘅引擎（EXP-13 code，rebase 到 main `a58081a4`），
  回放用 PIT 完整往績 —— 等同現行 live（10-07 起 Facts 完整版；10-19 實測 144 匹只有 1 匹出入）。
- **候選**：同一個 PIT 賽果庫，每匹馬只留 `Date < 賽日` 嘅**最近 N 仗（任何路程）**，再數今仗路程嘅出賽／上名。
  有賽果庫紀錄就用（唔取大）；近 N 仗冇今仗路程 → 同程 0 仗。之後嘅計分（有上名 +4、跑過冇上名 −1.55、路程分、
  同程訊號）全部不變。
- **家族**：N ∈ {6, 10, 15}，三個 arm；Holm（3 × 6 指標）。實作：`docs/experiments/patches/hkjc_arm_recent_distance.py`，`WC_RECENT_N`。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --out base.jsonl
for N in 6 10 15; do WC_RECENT_N=$N python3 $H run --arm docs/experiments/patches/hkjc_arm_recent_distance.py --out n$N.jsonl; done
for N in 6 10 15; do python3 $H compare base.jsonl n$N.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```

全紀錄（剔 04-12、04-15）。分層照報：馬匹數 ×4、首選 SP ×5、10-07 前後。

## §6 功效

閘門 MDE（EXP-20261016-14 同語料 CI 半寬）：Gold ±1.96pp、Good ±1.76pp、NDCG ±0.0101。全部 arm |Δ| < MDE → UNRESOLVABLE。

## Leakage

賽果庫 `Date < 賽日`（同騎練 PIT 一樣）；只用名次同路程。PASS。

## 已知偏差

EXP-13 已經見過「截斷版好過完整版」嘅方向；截斷版大約等於「賽績頁列出嗰十幾仗」。N 家族喺睇數之前揀，冇按截斷深度調。

## 判決後

- **WIN（Holm 後）** → 2026-10-19 起 forward ≥ 60 場一次性確認（Gold、Good、NDCG@5 Δ ≥ 0），先上線；上線要做 live 版近 N 仗表。
- **REJECT** → live 維持完整往績。
- 冇 WIN 但冇顯著退步 → 交 Kelvin。

## 結果

見 `EXP-20261019-01-hkjc-recent-distance-results.md`（跑完先寫）。
