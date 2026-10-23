"""A failed Chrome launch must not poison the next Playwright startup."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sb_browser_fetch import BrowserFetcher  # noqa: E402


@pytest.mark.parametrize("failure", ["launch", "retry_launch", "new_page", "close"])
def test_failed_startup_releases_playwright_before_next_attempt(tmp_path, failure):
    active = []
    started = []

    def start():
        if active:
            raise RuntimeError("Playwright Sync API inside the asyncio loop")
        pw = MagicMock()
        active.append(pw)
        pw.stop.side_effect = lambda: active.remove(pw)
        started.append(pw)
        return pw

    manager = SimpleNamespace(start=start)
    sync_api = SimpleNamespace(sync_playwright=lambda: manager)
    broken, healthy = MagicMock(), MagicMock()
    broken.new_page.side_effect = RuntimeError("new page failed")
    if failure == "close":
        broken.close.side_effect = RuntimeError("context already closed")
    launch_error = TimeoutError("BrowserType.launch_persistent_context: Timeout 180000ms exceeded")
    launches = ([launch_error, launch_error, healthy] if failure == "retry_launch"
                else [launch_error, healthy] if failure == "launch"
                else [broken, healthy])
    fetcher = BrowserFetcher(profile_dir=tmp_path, verbose=False, log=lambda _: None)
    with patch.dict(sys.modules, {"playwright.sync_api": sync_api}), \
         patch.object(fetcher, "_launch", side_effect=launches), \
         patch.object(fetcher, "_clear_stale_profile_lock", return_value=failure == "retry_launch"):
        try:
            with pytest.raises((RuntimeError, TimeoutError)):
                fetcher._ensure_page()
            assert not active
            assert fetcher._pw is fetcher._ctx is fetcher._page is None
            started[0].stop.assert_called_once()
            assert fetcher._ensure_page() is healthy.new_page.return_value
            assert len(started) == 2
        finally:
            fetcher.close()
    assert not active
