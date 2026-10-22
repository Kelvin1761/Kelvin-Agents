"""send_message must survive transient connection resets (NBA card lost 2026-10-21)."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import racing_telegram as rt  # noqa: E402


class _Resp:
    def __init__(self, body):
        self._b = json.dumps(body).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _setup(monkeypatch, outcomes):
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request)
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return _Resp(out)

    monkeypatch.setattr(rt.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)
    monkeypatch.setattr(rt, "telegram_credentials", lambda: ("tok", "111"))
    monkeypatch.setattr(rt, "telegram_targets", lambda audience="primary": ["111"])
    monkeypatch.delenv("WC_TELEGRAM_DISABLE", raising=False)
    return calls


def test_connection_reset_is_retried(monkeypatch):
    calls = _setup(monkeypatch, [ConnectionResetError(54, "reset"), {"ok": True}])
    result = rt.send_message("hello")
    assert result["status"] == "sent" and len(calls) == 2


def test_gives_up_after_max_attempts_and_reports_errors(monkeypatch):
    calls = _setup(monkeypatch, [ConnectionResetError(54, "reset")] * rt.SEND_ATTEMPTS)
    result = rt.send_message("hello")
    assert result["status"] == "request_failed" and len(calls) == rt.SEND_ATTEMPTS
    assert "reset" in result["errors"][0]


def test_client_error_is_not_retried(monkeypatch):
    err = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"{}"))
    calls = _setup(monkeypatch, [err])
    result = rt.send_message("hello")
    assert result["status"] == "request_failed" and len(calls) == 1


def test_rate_limit_is_retried(monkeypatch):
    err = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"{}"))
    calls = _setup(monkeypatch, [err, {"ok": True}])
    assert rt.send_message("hello")["status"] == "sent" and len(calls) == 2


def test_single_attempt_cli_does_not_retry_uncertain_acceptance(monkeypatch, capsys):
    calls = _setup(monkeypatch, [ConnectionResetError(54, "accepted then reset"), {"ok": True}])
    assert rt.main(["--message", "research digest", "--single-attempt", "--json"]) == 1
    assert len(calls) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "request_failed"


@pytest.mark.parametrize("single_attempt", [False, True])
def test_document_cli_preserves_default_retry_and_honors_single_attempt(
    monkeypatch, tmp_path, capsys, single_attempt,
):
    document = tmp_path / "report.txt"
    document.write_text("research review")
    calls = _setup(monkeypatch, [ConnectionResetError("uncertain"), {"ok": True}])
    args = ["--document", str(document), "--json"]
    if single_attempt:
        args.append("--single-attempt")
    assert rt.main(args) == int(single_attempt)
    assert len(calls) == (1 if single_attempt else 2)
    assert json.loads(capsys.readouterr().out)["status"] == (
        "request_failed" if single_attempt else "sent"
    )
