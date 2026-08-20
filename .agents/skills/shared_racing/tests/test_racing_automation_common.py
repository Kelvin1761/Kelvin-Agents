from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from racing_data_health import EXPECTED_FEATURES, scan_meeting, status_line, write_report  # noqa: E402
from racing_telegram import _chunks, send_message  # noqa: E402


def _meeting(tmp_path: Path, *, broken: bool = False) -> Path:
    meeting = tmp_path / "2026-08-13 Test"
    meeting.mkdir()
    (meeting / "Test Race 1 Facts.md").write_text(
        "### 馬匹 #1 Alpha\n\n### 馬匹 #2 Beta\n", encoding="utf-8"
    )
    (meeting / "Test Race 1 Racecard.md").write_text(
        "1. Alpha\n2. Beta\n", encoding="utf-8"
    )
    ranks = [1, 1] if broken else [1, 2]
    horses = {}
    for index, name in enumerate(("Alpha", "Beta"), start=1):
        horses[str(index)] = {
            "horse_name": name,
            "python_auto": {
                "ability_score": 70 - index,
                "rank": ranks[index - 1],
                "feature_scores": {key: 60 for key in ("speed", "form", "class", "pace", "weight", "draw")},
                "data_coverage": {"coverage_pct": 88.0},
            },
        }
    (meeting / "Race_1_Logic.json").write_text(json.dumps({"horses": horses}), encoding="utf-8")
    (meeting / "Race_1_Auto_Analysis.md").write_text("ok", encoding="utf-8")
    with (meeting / "Race_1_Auto_Scoring.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["horse_number"])
        writer.writeheader()
        writer.writerows([{"horse_number": "1"}, {"horse_number": "2"}])
    return meeting


def test_health_ok_and_writes_reports(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path)
    report = scan_meeting("au", meeting)
    assert report["status"] == "ok"
    assert report["deploy_allowed"] is True
    assert report["summary"]["average_coverage_pct"] == 88.0
    assert "0 errors" in status_line(report)
    write_report(report)
    assert (meeting / "Data_Health.json").exists()
    assert (meeting / "Data_Health.md").exists()


def test_health_blocks_bad_rank(tmp_path: Path) -> None:
    report = scan_meeting("au", _meeting(tmp_path, broken=True))
    assert report["status"] == "error"
    assert report["deploy_allowed"] is False
    assert any(issue["code"] == "RANK_NOT_PERMUTATION" for issue in report["issues"])


def test_hkjc_health_accepts_chinese_racecard_and_derives_coverage(tmp_path: Path) -> None:
    meeting = tmp_path / "2026-09-06_ShaTin"
    meeting.mkdir()
    (meeting / "09-06 Race 1 Facts.md").write_text(
        "### 馬號 1 — 測試甲\n", encoding="utf-8"
    )
    (meeting / "09-06 Race 1 排位表.md").write_text(
        "馬號: 1\n馬名: 測試甲\n", encoding="utf-8"
    )
    provenance = {key: "fixture" for key in EXPECTED_FEATURES["hkjc"]}
    logic = {
        "horses": {
            "1": {
                "horse_name": "測試甲",
                "python_auto": {
                    "ability_score": 68.0,
                    "rank": 1,
                    "feature_scores": {
                        key: 60.0 for key in EXPECTED_FEATURES["hkjc"]
                    },
                    "score_provenance": provenance,
                },
            }
        }
    }
    (meeting / "Race_1_Logic.json").write_text(
        json.dumps(logic, ensure_ascii=False), encoding="utf-8"
    )
    (meeting / "Race_1_Auto_Analysis.md").write_text("ok", encoding="utf-8")
    with (meeting / "Race_1_Auto_Scoring.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["horse_number"])
        writer.writeheader()
        writer.writerow({"horse_number": "1"})

    report = scan_meeting("hkjc", meeting)
    assert report["status"] == "ok"
    assert report["summary"]["average_coverage_pct"] == 100.0


def test_hkjc_health_blocks_missing_score_provenance(tmp_path: Path) -> None:
    meeting = tmp_path / "2026-09-06_ShaTin"
    meeting.mkdir()
    (meeting / "09-06 Race 1 Facts.md").write_text(
        "### 馬號 1 — 測試甲\n", encoding="utf-8"
    )
    (meeting / "09-06 Race 1 排位表.md").write_text(
        "馬號: 1\n馬名: 測試甲\n", encoding="utf-8"
    )
    logic = {
        "horses": {
            "1": {
                "horse_name": "測試甲",
                "python_auto": {
                    "ability_score": 68.0,
                    "rank": 1,
                    "feature_scores": {
                        key: 60.0 for key in EXPECTED_FEATURES["hkjc"]
                    },
                },
            }
        }
    }
    (meeting / "Race_1_Logic.json").write_text(
        json.dumps(logic, ensure_ascii=False), encoding="utf-8"
    )
    (meeting / "Race_1_Auto_Analysis.md").write_text("ok", encoding="utf-8")
    with (meeting / "Race_1_Auto_Scoring.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["horse_number"])
        writer.writeheader()
        writer.writerow({"horse_number": "1"})

    report = scan_meeting("hkjc", meeting)
    assert report["deploy_allowed"] is False
    assert any(issue["code"] == "NO_PROVENANCE" for issue in report["issues"])


def test_hkjc_health_blocks_racecard_name_drift(tmp_path: Path) -> None:
    meeting = tmp_path / "2026-09-06_ShaTin"
    meeting.mkdir()
    (meeting / "09-06 Race 1 Facts.md").write_text(
        "### 馬號 1 — 測試甲\n", encoding="utf-8"
    )
    (meeting / "09-06 Race 1 排位表.md").write_text(
        "馬號: 1\n馬名: 官方另一匹馬\n", encoding="utf-8"
    )
    auto = {
        "ability_score": 68.0,
        "rank": 1,
        "feature_scores": {key: 60.0 for key in EXPECTED_FEATURES["hkjc"]},
        "score_provenance": {key: "fixture" for key in EXPECTED_FEATURES["hkjc"]},
    }
    (meeting / "Race_1_Logic.json").write_text(
        json.dumps({"horses": {"1": {"horse_name": "測試甲", "python_auto": auto}}}),
        encoding="utf-8",
    )
    (meeting / "Race_1_Auto_Analysis.md").write_text("ok", encoding="utf-8")
    with (meeting / "Race_1_Auto_Scoring.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["horse_number"])
        writer.writeheader()
        writer.writerow({"horse_number": "1"})
    report = scan_meeting("hkjc", meeting)
    assert report["deploy_allowed"] is False
    assert any(issue["code"] == "SOURCE_NAME_MISMATCH" for issue in report["issues"])


def test_telegram_dry_run_and_chunking() -> None:
    parts = _chunks("a" * 5000)
    assert [len(part) for part in parts] == [4096, 904]
    result = send_message("測試", dry_run=True)
    assert result == {"ok": True, "status": "dry_run", "sent_parts": 1, "parts": ["測試"]}
