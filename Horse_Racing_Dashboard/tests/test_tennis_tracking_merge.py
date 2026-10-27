from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generate_static import _merge_sports_feed


def feed(tracking, status="valid"):
    return {
        "schema_version": 2,
        "sports": {
            "tennis": {
                "validation_status": status,
                "analysis_run_id": "tennis:2026-10-27",
                "recommendations": [],
                "tracking": tracking,
            }
        },
    }


def test_other_domain_publish_preserves_tennis_history_as_stale():
    old = feed({"status": "valid", "records": [{"id": "a", "day": "2026-10-25"}], "actual_bets": [{"id": "live"}]})
    result = _merge_sports_feed(old, {"schema_version": 2, "sports": {}})
    assert result["sports"]["tennis"]["tracking"]["records"] == [{"id": "a", "day": "2026-10-25"}]
    assert result["sports"]["tennis"]["tracking"]["status"] == "stale"


def test_partial_local_dates_cannot_erase_saved_history():
    old = feed(
        {
            "status": "valid",
            "records": [{"id": "old", "day": "2026-10-25"}, {"id": "replace", "day": "2026-10-26"}],
            "actual_bets": [{"id": "live"}],
        }
    )
    new = feed(
        {
            "status": "valid",
            "records": [{"id": "new", "day": "2026-10-26"}],
            "covered_dates": ["2026-10-26"],
            "source_counts": {},
            "actual_bets": [],
        }
    )
    result = _merge_sports_feed(old, new)["sports"]["tennis"]["tracking"]
    assert {r["id"] for r in result["records"]} == {"old", "new"}
    assert result["actual_bets"] == [{"id": "live"}]


def test_authoritative_native_actual_table_can_report_no_actual_bets():
    old = feed({"status": "valid", "records": [], "actual_bets": [{"id": "live"}]})
    new = feed({"status": "valid", "records": [], "actual_bets": [], "source_counts": {"prop_live_bets": 0}})
    assert _merge_sports_feed(old, new)["sports"]["tennis"]["tracking"]["actual_bets"] == []
