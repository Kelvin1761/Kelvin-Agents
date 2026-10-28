"""Bound, read-only launchd observations for transactional installer recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

if __package__:
    from .runtime_launchd import CENTRAL_LABELS, DOMAIN_LABELS
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shared_wong_choi.runtime_launchd import CENTRAL_LABELS, DOMAIN_LABELS

LABELS = frozenset(CENTRAL_LABELS) | frozenset(
    label for domain, labels in DOMAIN_LABELS.items() if domain != "au" for label in labels)
SCHEMA = "wong-choi-runtime-snapshot-state/v1"
PROOF = ".launchd-state.json"
MAX_PLIST_BYTES = 2 * 1024 * 1024


class SnapshotStateError(RuntimeError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_state(path: Path) -> dict:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"exists": False, "sha256": None, "mode": None}
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_PLIST_BYTES:
        raise SnapshotStateError("unsafe or oversized runtime plist")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        data = handle.read(MAX_PLIST_BYTES + 1)
        after = os.fstat(handle.fileno())
        final = path.lstat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size,
                             item.st_mtime_ns, item.st_ctime_ns)
    if (len(data) > MAX_PLIST_BYTES or identity(metadata) != identity(opened)
            or identity(opened) != identity(after) or identity(after) != identity(final)):
        raise SnapshotStateError("runtime plist changed during observation")
    return {"exists": True, "sha256": hashlib.sha256(data).hexdigest(),
            "mode": stat.S_IMODE(after.st_mode)}


def _probe(launchctl: str, *args: str):
    return subprocess.run([launchctl, *args], text=True, capture_output=True,
                          timeout=10, check=False)


def disabled_jobs(output: str) -> dict[str, bool]:
    match = re.fullmatch(r"\s*(?:disabled services\s*=\s*)?\{(.*)\}\s*", output, re.S)
    if not match:
        raise SnapshotStateError("cannot verify launchd disabled registry")
    values = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        item = re.fullmatch(r'\s*"([^"\\]+)"\s*=>\s*(true|false|disabled|enabled)\s*[;,]?\s*', line)
        if not item or item[1] in values:
            raise SnapshotStateError("invalid launchd disabled registry")
        values[item[1]] = item[2] in {"true", "disabled"}
    return values


def job_loaded(launchctl: str, domain: str, label: str) -> bool:
    value = _probe(launchctl, "print", f"{domain}/{label}")
    if value.returncode and "Could not find service" not in value.stderr:
        raise SnapshotStateError("launchd loaded-state probe failed")
    return value.returncode == 0


def observe(agents: Path, *, launchctl: str, domain: str, labels: tuple[str, ...]) -> dict:
    if set(labels) != LABELS or len(labels) != len(LABELS) or not re.fullmatch(r"gui/\d+", domain):
        raise SnapshotStateError("snapshot must bind the exact unified installer labels/domain")
    registry = _probe(launchctl, "print-disabled", domain)
    if registry.returncode:
        raise SnapshotStateError("launchd disabled-state probe failed")
    disabled = disabled_jobs(registry.stdout)
    jobs = {}
    for label in sorted(labels):
        jobs[label] = {"file": file_state(agents / (label + ".plist")),
                       "loaded": job_loaded(launchctl, domain, label), "disabled": disabled.get(label, False)}
        if jobs[label]["loaded"] and not jobs[label]["file"]["exists"]:
            raise SnapshotStateError("loaded runtime job has no restorable plist")
    return {"schema_version": SCHEMA, "agents_root": str(agents.resolve()),
            "domain": domain, "jobs": jobs}


def save_observation(snapshot: Path, agents: Path, **kwargs) -> None:
    value = observe(agents, **kwargs)
    for label, job in value["jobs"].items():
        if file_state(snapshot / (label + ".plist")) != job["file"]:
            raise SnapshotStateError("copied runtime snapshot differs from installed state")
    value["content_hash"] = _digest(value)
    fd = os.open(snapshot / PROOF, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())


def load_observation(snapshot: Path, agents: Path, *, domain: str, labels: tuple[str, ...]) -> dict:
    path = snapshot / PROOF
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PLIST_BYTES:
        raise SnapshotStateError("missing or unsafe runtime snapshot proof")
    value = json.loads(path.read_text(encoding="utf-8"))
    digest = value.pop("content_hash")
    if (digest != _digest(value) or value.get("schema_version") != SCHEMA
            or value.get("agents_root") != str(agents.resolve()) or value.get("domain") != domain
            or set(labels) != LABELS or len(labels) != len(LABELS)
            or set(value.get("jobs", {})) != LABELS):
        raise SnapshotStateError("runtime snapshot binding/hash mismatch")
    for label, job in value["jobs"].items():
        if (type(job.get("loaded")) is not bool or type(job.get("disabled")) is not bool
                or file_state(snapshot / (label + ".plist")) != job.get("file")
                or (job["loaded"] and not job["file"]["exists"])):
            raise SnapshotStateError("runtime snapshot backup/proof mismatch")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("capture", "unchanged", "changed-jobs", "job-state", "loaded-now"), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--agents", type=Path, required=True)
    parser.add_argument("--launchctl", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--job")
    args = parser.parse_args(argv)
    binding = {"domain": args.domain, "labels": tuple(args.label)}
    try:
        if args.mode == "capture":
            save_observation(args.snapshot, args.agents, launchctl=args.launchctl, **binding)
            return 0
        before = load_observation(args.snapshot, args.agents, **binding)
        if args.mode in {"job-state", "loaded-now"}:
            job = before["jobs"][args.job]
            if args.mode == "job-state":
                print(int(job["loaded"]), int(job["disabled"]))
            else:
                print(int(job_loaded(args.launchctl, args.domain, args.job)))
            return 0
        current = observe(args.agents, launchctl=args.launchctl, **binding)
        if args.mode == "changed-jobs":
            print("\n".join(label for label in sorted(LABELS)
                            if current["jobs"][label] != before["jobs"][label]))
            return 0
        return 0 if current == before else 2
    except (OSError, ValueError, TypeError, KeyError, SnapshotStateError, subprocess.SubprocessError):
        # Do not print launchctl's output: it may include private environment.
        print("runtime snapshot state unverified; recovery blocked", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
