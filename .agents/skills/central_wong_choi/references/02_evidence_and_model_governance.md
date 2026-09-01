# Evidence and Model Governance

## Evidence Chain

`ModelRelease ← PredictionRecord ← DecisionRecord ← SettlementRecord`

每份 record 要有 canonical ID、timezone-aware timestamp、content hash、domain、parent links。Prediction 亦要有 source cutoff；artifact timestamp 唔可以遲過 record created time。正式推介、no-bet、blocked 同 shadow 都要記。

## Promotion States

`research → shadow → paper → limited → production → retired`

每級 promotion 都係新 immutable ModelRelease／decision event。唔可以覆寫舊 champion，亦唔可以跳級；rollback 建立新 release 指返上一個 known-good release。

## Evaluation Decision

1. 先用固定 contract 同同一語料量 baseline/candidate。
2. Gold/Good 有可靠改善且 guardrails 無回歸：`PRIMARY_WIN`。
3. Gold/Good 無回歸，而預先指定 ranking metrics 有足夠 out-of-sample／bootstrap 證據：`RANKING_WIN`。
4. Primary 回歸、ranking 證據弱、資料洩漏、改尺救候選或 holdout 調參：`REJECT`。
5. 多個 feature/weight 一齊改必須 ablation；失敗結果照寫入 `docs/experiments/`。

Holdout 只做最後確認。中央 registry 記錄 verdict，唔取代 AU/HKJC/Tennis/NBA 各自評估尺。
