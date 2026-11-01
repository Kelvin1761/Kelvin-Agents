# Tennis 身份修復及 Elo generation 執行合約

2026-11-02；接續統一研究計劃，隔離prototype已實作／未部署。實驗證據見 [EXP-20261102-02](../experiments/EXP-20261102-02-tennis-identity-elo-cache.md)。模型準確度尚未證實改善。

## 已確認的問題

history 的 ACTIVE 篩選與 Elo 的 as-of 讀取是兩條路。只為新 history 加 availability 日期，仍會讓 `rating_as_of` 讀到沒有生成時鐘的 Elo。現役 builder 又同時更新 current player Elo、history opponent Elo、legacy pre-match cache 及 shadow post-match cache；legacy `INSERT OR IGNORE` 保留上一輪已有 key，不能把「已重跑」當成「已清走錯身份」。

本輪固定修復候選仍只限 Christian Sigsgaard 四場／八個 history perspective，及兩個 source mapping。五個 Sportsbet fixture 的 normalized 名稱支持 Jumpei，不能把它們一起搬到 Christian。原始獨立身份證據、mapping beforeimage 及完整影響範圍未過關前不改 live。

## 決策

採用明示、可回退的資料／衍生 Elo generation，先實作隔離版。每個 generation 固定 input digest、來源資格、canonical mapping 版本、模型版本、build 時間及實際 available 時間；history 與四條衍生輸出綁同一 generation。完成建置及驗證後，才原子切換 active pointer。保留舊 generation；rollback 是當刻新增的 activation event，不能把修正或回退的可用時間倒填到賽日。

讀取必須同時有 event cutoff（哪些賽果早於目標比賽）及 knowledge cutoff（該次決策實際已知哪些 generation）。歷史決策早於 generation available 時間時，不能使用該 generation。沒有合格歷史版本就明示 unavailable；不能靜靜改讀 current player Elo、最新 history 或 shadow v2。歷史原 prediction／ledger 不改寫。

本次不改 legacy pre-match 公式、K、同日先後政策或 v2 的 shadow 身份。重建 cache 的工程效果與身份修正的效果分開比較；已有 v2 模型判決不重開。只加 history guard、只清整個 legacy cache、或者直接把 v2 接上 production，均不能獨立滿足本合約。

## 執行次序及驗收

1. **固定 baseline 與影響範圍（隔離四臂已完成）**：保存同一 frozen input 的未修正 cold／warm control、八行修正 warm／cold；記錄實際寫入行與唯一 key 數，四條輸出逐項比對。全量 replay 仍不能代替 live cache beforeimage 或完整 runtime 重建。
2. **來源及身份資格**：對四場逐對保存原文 hash、來源 namespace、雙方身份及 target registry 證據。只接受雙側一致與精確 beforeimage；任何不符整批停止。全 provider mapping、所有 Elo 對手依賴及 current player cache 須列入影響範圍；fixture 不靠共享 player ID 推斷一起搬移。
3. **隔離 generation 實作（memory prototype已驗證，persistent及native接線未完成）**：新增 immutable generation metadata／版本化 Elo rows／activation observations；builder 在非 active generation 寫入。完整 input digest 相同時可重現；更改 input 必須產生新 generation。更動的預計模組為 `database/history_observations.py`、`history/elo_history.py`、`modelling/elo_builder.py`、`features/feature_builder.py` 及其直接 consumers；實際改動前重新掃描 import／SQL readers。
4. **時間及失敗測試**：修正前一瞬不能讀到修正後身份／Elo；切換後可讀；同日 event cutoff 不變；refresh、source reference 改變及再次 ingestion 不能抹走 availability；失敗 build 不切 active pointer；rollback 保留時間；歷史 fallback 必須 fail closed。對手後續 Elo 依賴也要驗證，不能只測兩名主角。
5. **同語料工程比較**：未修正 legacy cold control 對修正 legacy cold，另與實際舊 cache 分開報告。保留完整 lineage／row-flow／受影響與未受影響數，不能把 cache 政策改變的差異算成身份改善；清 bytecode、執行 repo quick／full gate。
6. **正式資料 apply**：先 dry-run exact-plan，驗證 live source／beforeimage 及 runtime SHA；所有新 rows、mapping、generation pointer 與 rollback 記錄必須有一致 transaction／可復原邊界。失敗不留半份已搬身份。正式動作仍經現有 Central gate，不以本設計文件代替通過證據。
7. **量度準確度**：只有來源／決策時鐘合格的新資料才可預先登記新候選，在固定 tennis-v1、同樣本／時間 folds／paired LL、Brier 及市場控制下評估。holdout 只最後確認；十五個 REJECT_DEV 不變。合格樣本不足就累積 forward，不能降低資格或挑選成功子集。

其他莊家的歷史 odds／回報可按已保存協議作 training／研究，但 ROI 是模型／選注／賠率共同結果，不能單獨當成球員實力標籤。必須有當時可得的賠率、賽果及選注定義；訓練窗算出的 ROI 不能洩漏進驗證窗。Sportsbet 的正式 out-of-sample／forward 評估另行保留。

## 當前執行證據

[EXP-20261102-03](../experiments/EXP-20261102-03-tennis-memory-elo-generations.md)：共用核心在401046行四臂對照保留全部原投影；memory generation在45場公開cluster以實際時計切換／refresh／回退，47針對測試通過。這沒有完成第2步live來源資格、第3步persistent indexed store／native接線、第4步production ingestion覆蓋，或第6–7步正式apply／準確度判決。

## 完成定義

來源與時間合約、可重現 generation、實際安全交付及準確度判決是四個分開的驗收。測試通過、身份修好或 cache 能重建，均不自動代表準確度提高。若新候選不過 frozen gate，記錄失敗，保持 known-good production。
