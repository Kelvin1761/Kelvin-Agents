"""Use the shared, model-independent SQLite payload storage format."""
from pathlib import Path
import sys

SHARED_SKILLS = Path(__file__).resolve().parents[4] / ".agents" / "skills"
if str(SHARED_SKILLS) not in sys.path:
    sys.path.insert(0, str(SHARED_SKILLS))

from shared_wong_choi.sqlite_payload_archive import (  # noqa: E402,F401
    PayloadArchiveError, PayloadArchiveLimit, compact_payloads, read_payload,
)
