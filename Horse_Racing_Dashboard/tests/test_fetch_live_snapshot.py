from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = DASHBOARD_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import fetch_live_snapshot  # noqa: E402


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_fetch_snapshot_validates_and_atomically_writes(monkeypatch, tmp_path: Path):
    payload = {
        "meetings": [{"date": "2026-08-30", "venue": "Wyong"}],
        "races": {"2026-08-30|Wyong": {}},
        "consensus": {},
    }
    seen = {}

    def fake_urlopen(request, *, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _Response(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(fetch_live_snapshot.urllib.request, "urlopen", fake_urlopen)
    output = tmp_path / "dashboard-data.json"

    result = fetch_live_snapshot.fetch_snapshot(
        "https://example.test/dashboard-data.json", output, timeout=7
    )

    assert result == payload
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert seen == {
        "url": "https://example.test/dashboard-data.json",
        "timeout": 7,
    }
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"meetings": {}, "races": {}},
        {"meetings": [], "races": []},
        {"meetings": [], "races": {}, "consensus": []},
    ],
)
def test_fetch_snapshot_rejects_invalid_projection(monkeypatch, tmp_path, payload):
    monkeypatch.setattr(
        fetch_live_snapshot.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(json.dumps(payload).encode("utf-8")),
    )
    output = tmp_path / "dashboard-data.json"

    with pytest.raises(ValueError):
        fetch_live_snapshot.fetch_snapshot("https://example.test", output)

    assert not output.exists()


def test_deploy_defaults_to_live_projection_and_full_scan_is_opt_in():
    deploy = (DASHBOARD_ROOT / "deploy.sh").read_text(encoding="utf-8")

    assert "scripts/fetch_live_snapshot.py" in deploy
    assert 'WC_ALLOW_DASHBOARD_FULL_RESCAN:-0' in deploy
    assert '--from-snapshot "$LIVE_SNAPSHOT"' in deploy
