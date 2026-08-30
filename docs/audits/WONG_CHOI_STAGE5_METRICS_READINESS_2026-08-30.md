# Wong Choi Stage 5 Metrics Readiness — 2026-08-30

## Verdict

**Task 1 ruler engineering checkpoint pass，等待evaluation-risk release人手批准；domain performance maturity保持原狀。** 四線已有獨立、versioned、machine-readable ruler；platform baseline固定於Stage 4 close commit `6c1528c08585ba2185c1d5e04344db87095245a9`，現役model release另行固定於`8b149c85aafa96d199eb838241d9a4958ec5d9b6`及各自canonical release ID／stage。呢個checkpoint冇candidate model、weight、holdout結果或promotion。

## Frozen Rulers

| Domain | Ruler | Decision mode | Primary | Current restriction |
|---|---|---|---|---|
| AU | `au-v2` | promotion gate | Gold、Good positional | Gold／Good任何dev或terminal回歸即reject；ranking-only path仍要paired CI同cohort guardrails |
| HKJC | `hkjc-v2` | promotion gate | Gold、Good positional | 同AU共用判決次序但語料、engine同baseline分開；HKJC forward corpus仍要成熟 |
| Tennis | `tennis-v1` | family-specific promotion gate | Brier gain、log-loss gain vs de-vig market | 只准earliest verified pre-match PIT rows；每family floor 600＋power；現役model仍shadow |
| NBA | `nba-v1` | descriptive only | Brier gain、log-loss gain vs de-vig market | 首30個forward settlements只係live baseline gate；獨立ruler release前禁止promotion |

所有ruler都固定metric direction、holdout strategy、bootstrap unit／trials／seed、cohorts、sample policy、review cadence，同win／regression／noise fixture classes。Hit rate、AUC或ROI任何單一metric都冇promotion權。

## Known Truth Debt Preserved

- AU舊dev／terminal有point-in-time regime差異，field-size／venue／going必報；唔會用pooled Gold掩蓋composition。
- HKJC語料較薄，唔會借AU數字或跨domain比較Gold百分比。
- Tennis歷史有post-start overwrite／replay contamination，非PIT row全部排除；現有holdout ROI／Brier未過，完成平台唔等於model成熟。
- NBA未有2026–27 live prediction＋settled archive；歷史／synthetic分析只可描述，唔可冒充forward evidence。

## Machine Gates

- `evaluation_rulers.py`要求每個domain恰好一份frozen ruler，schema、full baseline SHA、primary metrics、holdout tuning ban、bootstrap、review cadence同fixture coverage缺一即fail。
- Release policy將`evaluation_ruler*`歸類evaluation risk，必須full check且不可auto-merge。
- 同一scope同時包含evaluation ruler同candidate model會直接拒絕，確保「改把尺」同「測候選」係兩個release。
- Targeted ruler／release-policy tests：22 passed。
- Full repo gate：1,353個Python tests通過（另2 xfailed、4 skipped），Dashboard Node 69 checks通過；AU／HKJC golden各120匹一致。
- Production `./健康.sh`：exit 0、冇嚴重問題；WARM 883 GiB、COLD 5/5。HOT約24 GiB係既有warning，所以heavy research未有production-safe queue前唔會啟動。
- Task 1 engineering checkpoint已完成；scoped evaluation release只會push，獲人手批准merge後先可開始Task 2。
