import json

from services.parser_hkjc import parse_hkjc_analysis


REPORT = """## [第二部分]
**【No.2】 測試馬** | 騎師:測試 | 練馬師:測試 | 負磅:131 | 檔位:2
#### 🔢 評分總覽（7D 加權計算 · Python Auto 引擎）
| 維度 | 維度分（顯示尺） | 原始分 | 權重 | 貢獻 | 判定 |
|:---|---:|---:|---:|---:|:---:|
| 狀態與穩定性 | 82.1 | 80.5 | 9.8% | 7.92 | ✅ |
| 檔位與走位 | 54.9 | 57.8 | 27.4% | 15.82 | ❌ |
**【No.3】 對照馬** | 騎師:測試 | 練馬師:測試 | 負磅:131 | 檔位:3
"""


def test_missing_sidecar_transparency_reads_report_raw_ranking_matrix(tmp_path):
    path = tmp_path / "Race_1_Auto_Analysis.md"
    path.write_text(REPORT, encoding="utf-8")
    path.with_name("Race_1_Logic.json").write_text(
        json.dumps({"horses": {"2": {"horse_name": "測試馬"}}}), encoding="utf-8"
    )
    horse = parse_hkjc_analysis(str(path)).horses[0]
    assert [(d.score, d.weight_pct, d.contribution) for d in horse.dimension_details] == [
        (80.5, 9.8, 7.92), (57.8, 27.4, 15.82)
    ]


def test_report_fallback_works_without_sidecar_and_preserves_legacy_shape(tmp_path):
    path = tmp_path / "Race_1_Auto_Analysis.md"
    path.write_text(REPORT.replace("82.1 | 80.5 |", "80.5 |").replace(
        "54.9 | 57.8 |", "57.8 |"
    ), encoding="utf-8")
    horse = parse_hkjc_analysis(str(path)).horses[0]
    assert [d.score for d in horse.dimension_details] == [80.5, 57.8]


def test_sidecar_matrix_remains_authoritative(tmp_path):
    path = tmp_path / "Race_1_Auto_Analysis.md"
    path.write_text(REPORT, encoding="utf-8")
    row = {"label": "狀態與穩定性", "score": 81.0, "weight": 0.1,
           "contribution": 8.1, "band": "✅"}
    path.with_name("Race_1_Logic.json").write_text(json.dumps({"horses": {
        "2": {"python_auto": {"grade_transparency": {"rows": [row]}}}
    }}, ensure_ascii=False), encoding="utf-8")
    horse = parse_hkjc_analysis(str(path)).horses[0]
    assert [(d.score, d.contribution) for d in horse.dimension_details] == [(81.0, 8.1)]


def test_missing_matrix_does_not_fabricate_scores(tmp_path):
    path = tmp_path / "Race_1_Auto_Analysis.md"
    path.write_text("\n".join(line for line in REPORT.splitlines() if line.startswith("**【")),
                    encoding="utf-8")
    assert not parse_hkjc_analysis(str(path)).horses[0].dimension_details
