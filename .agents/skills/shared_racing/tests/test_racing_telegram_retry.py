"""send_message must survive transient connection resets (NBA card lost 2026-10-21)."""
import io
import json
import sys
import urllib.error
from pathlib import Path

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
