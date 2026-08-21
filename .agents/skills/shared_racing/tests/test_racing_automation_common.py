from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

import racing_telegram  # noqa: E402
from racing_data_health import EXPECTED_FEATURES, scan_meeting, status_line, write_report  # noqa: E402
from racing_telegram import (  # noqa: E402
    _chunks,
    _multipart_document,
    send_document,
    send_message,
    telegram_credentials,
    telegram_targets,
)


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
                # ⚠️ 一定要用 AU Logic 檔**真正**嘅 key 名。呢行本來寫住
                # ("speed","form","class","pace","weight","draw") —— 六個假名，
                # 同 EXPECTED_FEATURES["au"] 嗰六個假名一模一樣，所以 test 綠燈，
                # 但 scan_meeting 對**真**AU 場次每匹馬都報 MISSING_FEATURES。
                # 一個自己餵 input 嘅 test 睇唔到常數同現實脫節 —— 所以下面
                # 加咗 test_au_expected_features_match_the_engine 去捉。
                "feature_scores": {
                    key: 60
                    for key in (
                        "form_score", "performance_quality_score", "pace_figure_score",
                        "trial_score", "pace_map_score", "jockey_score", "trainer_score",
                        "jockey_horse_fit_score", "rating_score", "track_score",
                    )
                },
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


def test_hkjc_health_blocks_incomplete_extraction_manifest(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path)
    (meeting / "Extraction_Readiness.json").write_text(
        json.dumps(
            {
                "status": "waiting_source",
                "expected_races": 2,
                "racecards_ready": 2,
                "formguides_ready": 1,
                "starter_pdf_ready": True,
            }
        ),
        encoding="utf-8",
    )
    report = scan_meeting("hkjc", meeting)
    assert report["deploy_allowed"] is False
    codes = {issue["code"] for issue in report["issues"]}
    assert "SOURCE_NOT_READY" in codes
    assert "INCOMPLETE_RACE_SET" in codes


def test_telegram_dry_run_and_chunking() -> None:
    parts = _chunks("a" * 5000)
    assert [len(part) for part in parts] == [4096, 904]
    result = send_message("測試", dry_run=True)
    assert result == {"ok": True, "status": "dry_run", "sent_parts": 1, "parts": ["測試"]}


def test_telegram_reuses_au_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_TOKEN", "au-token")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_CHAT", "12345")
    assert telegram_credentials() == ("au-token", "12345")


def test_load_env_reads_explicit_file_without_overwriting(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / "notify.env"
    env_file.write_text(
        "export WC_NOTIFY_TELEGRAM_TOKEN=file-token\n"
        "export WC_NOTIFY_TELEGRAM_CHAT=999\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_TOKEN", "existing-token")
    monkeypatch.delenv("WC_NOTIFY_TELEGRAM_CHAT", raising=False)
    racing_telegram.load_env(env_file)
    assert racing_telegram.os.environ["WC_NOTIFY_TELEGRAM_TOKEN"] == "existing-token"
    assert racing_telegram.os.environ["WC_NOTIFY_TELEGRAM_CHAT"] == "999"


def test_telegram_content_includes_extra_targets_without_duplicates(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_CHAT", "111")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_EXTRA", "111, 222;333")
    assert telegram_targets() == ["111"]
    assert telegram_targets("content") == ["111", "222", "333"]


def test_telegram_content_is_sent_to_primary_and_extra(monkeypatch) -> None:
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_CHAT", "111")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_EXTRA", "222")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b'{"ok": true}'
    with mock.patch.object(
        racing_telegram.urllib.request, "urlopen", return_value=response
    ) as request:
        result = send_message("analysis done", audience="content")
    assert result["ok"] is True
    assert result["sent_targets"] == 2
    assert request.call_count == 2


def test_telegram_document_dry_run_and_missing_file(tmp_path: Path) -> None:
    missing = send_document(tmp_path / "missing.pdf", dry_run=True)
    assert missing["ok"] is False
    assert missing["status"] == "missing_document"

    report = tmp_path / "monthly.pdf"
    report.write_bytes(b"%PDF-1.4 fixture")
    result = send_document(report, caption="月報", dry_run=True)
    assert result["ok"] is True
    assert result["status"] == "dry_run"
    assert result["document"] == str(report)


def test_telegram_document_builds_multipart_utf8(tmp_path: Path) -> None:
    report = tmp_path / "月報.pdf"
    report.write_bytes(b"%PDF-1.4 fixture")
    payload, content_type = _multipart_document("123", report, "八月月報")
    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="chat_id"' in payload
    assert b"123" in payload
    assert "月報.pdf".encode("utf-8") in payload
    assert "八月月報".encode("utf-8") in payload
    assert b"%PDF-1.4 fixture" in payload


def test_telegram_document_is_sent_to_primary_only_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_CHAT", "111")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_EXTRA", "222")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    report = tmp_path / "monthly.pdf"
    report.write_bytes(b"%PDF-1.4 fixture")
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b'{"ok": true}'
    with mock.patch.object(
        racing_telegram.urllib.request, "urlopen", return_value=response
    ) as request:
        result = send_document(report, caption="monthly")
    assert result == {"ok": True, "status": "sent", "sent_targets": 1}
    assert request.call_count == 1
    sent_request = request.call_args.args[0]
    assert sent_request.full_url.endswith("/sendDocument")


def test_au_expected_features_match_the_engine() -> None:
    """`EXPECTED_FEATURES["au"]` 一定要係引擎真正出嘅 feature key。

    呢個 test 存在嘅唯一理由：2026-08-21 之前嗰六個名（speed/form/class/pace/
    weight/draw）**一個都唔存在**，於是 `scan_meeting("au", …)` 對每匹馬都報
    MISSING_FEATURES、`deploy_allowed` 永遠 False。冇 test 捉到，因為
    `_meeting()` fixture 用咗同一批假名。

    所以呢度**唔可以**同 fixture 比 —— 要同引擎比。
    """
    import sys as _sys
    engine_scripts = (
        Path(__file__).resolve().parents[2]
        / "au_racing" / "au_wong_choi_auto" / "scripts"
    )
    if not engine_scripts.is_dir():
        pytest.skip("AU 引擎唔喺呢個 checkout 度")
    _sys.path.insert(0, str(engine_scripts))
    try:
        from au_racing_engine.scoring import FEATURE_KEYS
    except ImportError as exc:                       # pragma: no cover
        pytest.skip(f"AU 引擎 import 唔到：{exc}")
    unknown = sorted(set(EXPECTED_FEATURES["au"]) - set(FEATURE_KEYS))
    assert not unknown, (
        f"EXPECTED_FEATURES['au'] 有 {len(unknown)} 個引擎唔認識嘅 key：{unknown}。"
        " 呢啲 key 會令每匹馬都報 MISSING_FEATURES。"
    )
