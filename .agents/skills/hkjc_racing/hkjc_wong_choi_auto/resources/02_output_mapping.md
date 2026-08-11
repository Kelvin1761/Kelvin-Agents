# HKJC Auto Output Mapping

## User-Facing Labels

| Internal | User-facing |
|---|---|
| `MODEL_TOP_PICK` | `模型首選` |
| `WATCH` | `觀望` |
| `NO_PICK` | `報告內不展示` |
| `ability_score` | `綜合戰力分` |
| `rank_score` | internal full-field ordering score；CSV 保留作 audit，Markdown 解釋 70/30 合約 |
| `confidence_score` | `信心分` |
| `risk_score` | `風險分` |
| `draw_score` | `檔位分` |
| `reason_codes` | `原因代碼` |
| `risk_flags` | `風險標記` |

Markdown and report remarks must not directly display the English internal status names.

`ability_score` / Grade 仍顯示七維 Matrix 實分。報告次序、Top 2、Top 4
同模型首選跟 `rank_score`；CSV 必須保留 Matrix/ML percentile、權重同模型版本 provenance。

## Report Bans

Auto reports must not contain:

- `tick_count`
- `矩陣算術`
- `步速修正偏差`
- `走位-段速複合`
- `MODEL_TOP_PICK`
- `WATCH`
- `NO_PICK`
- `ability_score`
- `confidence_score`
- `risk_score`
- `odds`
- `賠率`
- `value`
- `值博率`
- `edge`
