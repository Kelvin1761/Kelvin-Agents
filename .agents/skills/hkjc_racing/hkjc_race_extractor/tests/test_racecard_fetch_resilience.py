from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_racecard.py"
SPEC = importlib.util.spec_from_file_location("extract_racecard_resilience", SCRIPT)
assert SPEC and SPEC.loader
racecard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(racecard)


class _Response:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_fetch_html_retries_a_timeout_with_a_bounded_socket_timeout() -> None:
    with (
        mock.patch.object(
            racecard.urllib.request,
            "urlopen",
            side_effect=[TimeoutError("slow"), _Response("ready")],
        ) as urlopen,
        mock.patch.object(racecard.time, "sleep") as sleep,
    ):
        assert racecard.fetch_html("https://example.test", timeout=8, attempts=3) == "ready"
    assert urlopen.call_count == 2
    assert all(call.kwargs["timeout"] == 8 for call in urlopen.call_args_list)
    sleep.assert_called_once()


def test_critical_chinese_page_is_fetched_before_optional_english() -> None:
    url = (
        "https://racing.hkjc.com/zh-hk/local/information/racecard"
        "?racedate=2026/09/23&Racecourse=HV&RaceNo=3"
    )
    with mock.patch.object(racecard, "fetch_html", side_effect=["<html></html>", "<html></html>"]) as fetch:
        racecard.extract_racecard(url)
    assert fetch.call_args_list[0].args[0] == url
    assert fetch.call_args_list[0].kwargs == {"timeout": 8, "attempts": 3}
    assert "/en-us/" in fetch.call_args_list[1].args[0]
    assert fetch.call_args_list[1].kwargs == {"timeout": 5, "attempts": 1}
