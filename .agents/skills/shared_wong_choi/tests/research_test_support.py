"""Explicit local review configuration for computational test fixtures.

No guard is mocked. Tests exercise the same mandatory cursor as real workers.
"""
from datetime import datetime

from shared_wong_choi.research_review_cursor import ResearchReviewCursorRunner


def pin_review(runtime, registry, spec, *, queue_root=None):
    root = runtime.state_root / 'research-review-cursors'
    root.mkdir(parents=True, exist_ok=True)
    path = root / (spec.domain.value + '.sqlite3')
    if not path.exists():
        release = datetime.fromisoformat(spec.created_at)
        ResearchReviewCursorRunner(runtime, registry).initialize(
            domain=spec.domain, initial_window_start=release,
            ruler_digest=spec.evaluation_ruler_digest, ruler_released_at=release,
            queue_root=queue_root)
    return path
