"""Exact-commit gates with live stderr, retained logs and in-process receipts."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

GATE_TIMEOUT_SECONDS = 7200
GATE_PROGRESS_SECONDS = 30


@dataclass(frozen=True)
class GateReceipt:
    commit: str
    check: str
    environment: str
    finished: float
    elapsed_seconds: float
    log: str

    def reusable(self, repo: Path, commit: str, check: str) -> bool:
        # Never deserialize receipts: resumed releases must run a new full gate.
        try:
            return (bool(self.environment) and self.commit == commit and self.check == check
                    and 0 <= time.monotonic() - self.finished < 900
                    and self.environment == environment_fingerprint(repo))
        except (OSError, ValueError, subprocess.SubprocessError):
            return False


def environment_fingerprint(repo: Path) -> str:
    """Bind both the gate interpreter and run_tests.sh's optional venv."""
    interpreters = [os.environ.get("PYTHON_BIN", "python3")]
    venv = repo / ".venv/bin/python3"
    if venv.exists() and "PYTHON_BIN" not in os.environ:
        interpreters.append(str(venv))
    probe = (
        "import importlib.metadata as m,json,sys; "
        "print(json.dumps([sys.executable,sys.version,"
        "sorted((d.metadata.get('Name',''),d.version,str(d.locate_file(''))) "
        "for d in m.distributions())],sort_keys=True))"
    )
    details = []
    for interpreter in interpreters:
        result = subprocess.run([interpreter, "-c", probe], cwd=repo, text=True,
                                capture_output=True, timeout=30, check=True)
        details.append(result.stdout)
    # Exclude only shell bookkeeping and private snapshot index state.
    env = {k: v for k, v in os.environ.items()
           if k not in {"PWD", "OLDPWD", "SHLVL", "_", "GIT_INDEX_FILE"}}
    markers = {p.name: p.read_text() for p in repo.glob(".wongchoi_*root")}
    return hashlib.sha256(json.dumps([details, env, markers], sort_keys=True).encode()).hexdigest()


def run_gate(repo: Path, check: str, *, commit: str = "working-tree", attest: bool = True) -> GateReceipt:
    """One gate, one log; stdout stays available for the CLI's JSON result."""
    from .release_manager import ReleaseError

    try:
        before = environment_fingerprint(repo) if attest else ""
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ReleaseError(f"cannot fingerprint gate environment: {exc}") from exc
    directory = Path(tempfile.gettempdir()) / "wc-release-gate-logs"
    directory.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f"{commit[:12]}-{check}-", suffix=".log", dir=directory)
    command = ["./檢查.sh"] + (["--quick"] if check == "quick" else [])
    started = time.monotonic()
    print(f"▶ gate {check} · {commit[:12]} · log {raw}", file=sys.stderr, flush=True)
    with os.fdopen(fd, "w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, start_new_session=True,
                                   env={**os.environ, "PYTHONUNBUFFERED": "1"})
        def relay():
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="", file=sys.stderr, flush=True)
        reader = threading.Thread(target=relay, daemon=True)
        reader.start()
        try:
            while True:
                try:
                    code = process.wait(timeout=GATE_PROGRESS_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - started
                    print(f"⏱ gate {check} · {commit[:12]} · {elapsed:.0f}s · log {raw}",
                          file=sys.stderr, flush=True)
                    if elapsed >= GATE_TIMEOUT_SECONDS:
                        raise ReleaseError(f"{check} gate timed out; log: {raw}")
        finally:
            # Include descendants: a timed-out pytest must not keep running.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            reader.join(timeout=5)
        elapsed = time.monotonic() - started
    if code != 0:
        raise ReleaseError(f"{check} gate failed (exit {code}); no files were staged; log: {raw}")
    try:
        after = environment_fingerprint(repo) if attest else ""
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ReleaseError(f"cannot recheck gate environment; log: {raw}") from exc
    if before != after:
        raise ReleaseError(f"gate environment changed during execution; log: {raw}")
    print(f"✅ gate {check} · {commit[:12]} · {elapsed:.1f}s", file=sys.stderr, flush=True)
    return GateReceipt(commit, check, before, time.monotonic(), round(elapsed, 3), raw)
