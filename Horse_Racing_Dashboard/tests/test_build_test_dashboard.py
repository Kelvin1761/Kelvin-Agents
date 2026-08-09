import sys
import tempfile
import unittest
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import build_test_dashboard  # noqa: E402


def _snapshot():
    return {
        "meetings": [
            {"date": "2026-08-01", "venue": "Flemington", "region": "au"},
            {"date": "2026-07-15", "venue": "HappyValley", "region": "hkjc"},
        ],
        "races": {
            "2026-08-01|Flemington": {"meeting": {"region": "au"}},
            "2026-07-15|HappyValley": {"meeting": {"region": "hkjc"}},
        },
        "consensus": {
            "2026-08-01|Flemington|1": {},
            "2026-07-15|HappyValley|1": {},
        },
    }


class _DeniedArchive:
    def is_dir(self):
        return True

    def iterdir(self):
        raise PermissionError(1, "Operation not permitted", "/GoogleDrive/AU_Racing/Archive")

    def __str__(self):
        return "/GoogleDrive/AU_Racing/Archive"


class BuildTestDashboardTests(unittest.TestCase):
    def test_unreadable_metadata_root_preserves_live_metadata(self):
        meeting = {"date": "2026-08-01", "venue": "Flemington", "region": "au"}

        folder, warning = build_test_dashboard._find_metadata_folder(
            meeting,
            root=_DeniedArchive(),
        )

        self.assertIsNone(folder)
        self.assertIn("metadata overlay unavailable", warning)

    def test_unreadable_archive_preserves_current_live_snapshot(self):
        data = _snapshot()

        archived, warning = build_test_dashboard._remove_archived_au_meetings(
            data,
            archive_root=_DeniedArchive(),
        )

        self.assertEqual(archived, [])
        self.assertIn("archive filter unavailable", warning)
        self.assertEqual(len(data["meetings"]), 2)
        self.assertIn("2026-08-01|Flemington", data["races"])

    def test_readable_archive_removes_matching_au_meeting_only(self):
        data = _snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp)
            (archive_root / "2026-08-01 Flemington").mkdir()

            archived, warning = build_test_dashboard._remove_archived_au_meetings(
                data,
                archive_root=archive_root,
            )

        self.assertEqual(warning, "")
        self.assertEqual([item["venue"] for item in archived], ["Flemington"])
        self.assertEqual([item["venue"] for item in data["meetings"]], ["HappyValley"])
        self.assertNotIn("2026-08-01|Flemington", data["races"])
        self.assertNotIn("2026-08-01|Flemington|1", data["consensus"])


if __name__ == "__main__":
    unittest.main()
