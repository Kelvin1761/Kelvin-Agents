# EXP-20261008-05 — HKJC pure 7D official ranking

- **日期**：2026-10-08
- **平台**：HKJC
- **假設**：complete-strength 與 7D 大量重疊；即使 15% overlay 有歷史排序增益，正式架構應回復純 7D，並完整移除 overlay 計算、開關及 shadow。
- **搜索過嘅舊記錄**：EXP-20260928-06、EXP-20260928-07-HK、EXP-20260928-09、EXP-20261007-02、EXP-20261008-04
- **改到嘅組件**：HKJC final ranking、run contract、shadow monitor、CSV／Markdown、Dashboard scoring ledger

## 配置

- **baseline**：commit `25b220903fa6a623c043f93adc3e25e4e0bc7c46`；85% robust 7D百分位 + 15% complete-strength百分位。
- **candidate**：正式次序只按 robust 7D；不再計算、輸出或監察原15%公式，亦冇環境開關可以靜靜重啟。

## 已知表現取捨

今次係用戶基於模型結構及重複訊號風險揀嘅 rollback，**唔係績效 promotion**。直接使用 EXP-20261008-04 同一份340場、同一 locked split 嘅配對結果；純7D係該實驗 baseline，因此移除overlay嘅差係原結果倒號：

| 窗口 | Gold | Good | Capture@5 | Recall@5 | NDCG@5 |
|---|---:|---:|---:|---:|---:|
| development 280 | −0.71pp | −0.36pp | −0.12pp | −0.04pp | −0.00124 |
| terminal 60 | 0.00pp | −1.67pp | −2.22pp | −2.00pp | −0.01207 |
| 全340場 | −0.59pp | −0.59pp | −0.49pp | −0.39pp | −0.00315 |

按 Stage-4，呢個唔係一個可聲稱「改善」嘅候選。採用理由係避免兩層重複 evidence、令正式分數可完全拆解，以及回到用戶指定嘅 7D 架構。舊公式同結果只留喺 immutable 歷史實驗紀錄，唔留喺現役 runtime。

## 點解唔直接將15%塞返入7D

- speed、class、form、consistency、form-line、distance 已經喺現有 feature／7D path；原封搬入只係隱藏 double count。
- previous outer-weight refit、hierarchical refit、shape reallocation 都出現 primary regression；單改7D outer weight 冇證明可複製 overlay 收益。
- 下一個可接受實驗必須做 grouped ablation：速度→sectional、評分／班次→class、近績／負距→stability、form-line→form-line、distance維持獨立可見調整；每組先對現有 leaf residualize，再逐組量邊際。

## 檢查

- **leakage-audit**：PASS；冇新資料源或賽後欄位。
- **排名一致性 smoke**：2026-10-07 HV R3，正式次序與 `ability_score` 降序逐匹一致；Logic／CSV／Dashboard 冇 complete-strength runtime 欄位。
- **targeted tests**：38 passed；Dashboard static tests 62 passed。
- **退步**：上表已完整披露；唔聲稱表現改善。

## 結論

正式排名改回純 7D。complete-strength 已從計算、run contract、shadow、CSV、Markdown 同 Dashboard 移除；歷史實驗檔仍保留作審計。

**決定**：USER-SELECTED ARCHITECTURE ROLLBACK／NOT A PERFORMANCE WIN

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 WC_DISABLE_POST_SUCCESS_DEPLOY=1 \
python3 .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py \
  /private/tmp/hkjc-pure7d-smoke/Race_3_Logic.json
```
