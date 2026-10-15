# EXP-20261015-20 改把尺：會改變 leaf 資訊量嘅候選要加「兩邊都 refit」arm

- **日期**：2026-10-15
- **平台**：AU / HKJC（把尺共用）
- **假設**：凍結現行權重嘅閘門會系統性低估「修好一個 leaf」類候選，因為現行權重係喺
  舊 leaf 之下 fit 出嚟。加一個「baseline 同 candidate 用同一程序各自 walk-forward refit」
  嘅 arm，可以分開「特徵冇用」同「舊權重聽唔到佢」。
- **搜索過嘅舊記錄**：EXP-20261010-06（HKJC 中性 vs walk-forward refit）、
  EXP-20261015-02（AU 試閘門檻 fixed vs refit）、EXP-20260821-02（聯合 refit）、
  EXP-20261012-32（walk-forward families）；memory `au-reallocating-dimension-shares-fails`、
  `au-trial-score-is-accurate-but-unheard`、`retest-orthogonality-changes`
- **改到嘅檔案／組件**：`docs/model-evaluation-contract.md`（新 §8）、
  `.agents/skills/shared_racing/model_evaluation_decision.py`（`evaluate_with_refit_arms`）、
  `.agents/skills/shared_racing/tests/test_refit_both_arms.py`

## 配置

- **baseline**：origin/main `60dfb701`，Stage 4 v3 規則
- **candidate**：**只改把尺**，冇任何 model／feature／weight 改動

## 起因

用戶提出：改進 sectional 之類嘅 leaf 之後，往績嘅最佳權重可能唔同咗，但之前所有測試都係
喺現行權重之下做。用戶原本建議「全部權重設中性」再測。

## 點解唔用「中性權重」

- 中性係另一個、差好多嘅模型。EXP-20261010-06：HKJC 中性權重 Good −6.99pp [−11.5, −2.6]、
  NDCG@5 −0.049，明顯差過現行權重。喺佢上面加分，唔代表喺 live 模型上面加分。
- AU 權重已經係合成係數（EXP-07 剷走 gain），各維度原始 SD 唔同，「權重相等」唔等於
  「影響力相等」。
- 所以中性只可以做診斷，唔做判決 arm。

## 規則設計（詳見合約 §8）

- 四個 arm：A0／A1（現行權重）、B0／B1（同一程序 walk-forward refit）。
- fixed arm A1 vs A0（`fixed_rule`）、refit arm B1 vs B0（`walk_forward_oos`）、
  live guard B1 vs A0、stale B0 vs A0（只報告）。
- 兩個判決 arm 當一個 family 做 Holm。
- refit 程序要用 hash 證明兩邊一樣。
- 候選功勞只係 B1 − B0；B0 贏 A0 嘅增益屬於 refit，要另外過閘。
- 唔追溯舊 REJECT；要重測舊候選，就揀短名單、預先登記成一個 family。

## 驗證把尺

`test_refit_both_arms.py`，8 個合成數據測試，全部 PASS：

| 情境 | 預期 | 結果 |
|---|---|---|
| A/A：四個 arm 一模一樣 | REJECT `both_arms_reject` | ✅ |
| 兩邊 refit 程序 hash 唔同 | 拒絕 `refit_procedure_not_symmetric` | ✅ |
| 冇 refit 程序 hash | 拒絕 | ✅ |
| 現行權重下已經贏 | `candidate_with_live_weights` | ✅ |
| 現行權重下聽唔到，refit 後贏（§8 存在嘅原因） | `candidate_with_refit_weights` | ✅ |
| 只係 refit 本身贏（B0 > A0，B1 = B0） | REJECT，`baseline_weights_stale` 舉旗 | ✅ |
| refit arm 贏但上線會差過 live | REJECT `refit_package_regresses_live` | ✅ |
| 兩個 arm 嘅 p 有 Holm 調整 | adjusted = min(1, 2p) | ✅ |

既有 `test_stage4_v3_full_record.py` 5 個測試照舊 PASS。

## 未做（之後要做）

1. AU walk-forward refit 預測產生器未整理成可重用工具；EXP-20261015-02 研究程式
   （分支 `codex-au-trial-cutoff-20261015`）係起點。
2. 未跑 B0 vs A0（現行 AU 權重係咪過時）。今日 EXP-20261015-02 嘅 refit 對固定權重
   打和（Gold +0.20pp CI [−0.39, +0.74]），所以預期打和，但之後 EXP-20261015-07 又上咗
   全程速度，要用最新 main 重新量。
3. 舊 REJECT 嘅重測短名單未登記，要用戶揀。
4. 冇真實語料測試；只係合成數據證明判決邏輯。

## 檢查

- **leakage-audit**：不適用（冇特徵改動）
- **golden_scoring**：冇郁
- **data_contract**：冇郁
- **退步**：冇；新增 function，冇改既有判決路徑

## 結論

把尺多咗一個 arm，只影響之後會改變 leaf 資訊量嘅候選。呢個改動本身冇證明任何模型改善。

**決定**：KEEP（把尺改動）
**commit**：見分支 `claude-refit-both-arms-20261015`

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest -q .agents/skills/shared_racing/tests/test_refit_both_arms.py \
  .agents/skills/shared_racing/tests/test_stage4_v3_full_record.py
```
