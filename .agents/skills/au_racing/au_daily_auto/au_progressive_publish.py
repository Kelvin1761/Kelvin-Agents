"""One run-owned publisher process; analysis only queues immutable local files.

The AU scheduler retains its normal shared lock until this child drains. The
child has a separate module/work directory and never fetches Sportsbet pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

COPY_SUFFIXES = {".md", ".json", ".csv"}
MAX_MEETING_BYTES = 64 * 1024 * 1024
MAX_QUEUE_BYTES = 512 * 1024 * 1024


def atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def freeze_meeting(source: Path, destination: Path, *, meeting_name: str | None = None) -> tuple[str, int]:
    """Only top-level publication inputs, never corpus/snapshots/cache trees."""
    if (source / ".analysis_pending").exists():
        raise ValueError(f"{source.name}: analysis validation is pending")
    match = re.search(r" Race 1-(\d+)$", meeting_name or source.name)
    if not match:
        raise ValueError(f"unrecognised meeting folder: {source.name}")
    expected = set(range(1, int(match.group(1)) + 1))
    for suffix in ("Logic.json", "Auto_Analysis.md", "Auto_Scoring.csv"):
        have = {int(p.name.split("_")[1]) for p in source.glob(f"Race_*_{suffix}")
                if p.is_file() and not p.is_symlink()}
        if not expected or have != expected:
            raise ValueError(f"{source.name}: incomplete {suffix}: {sorted(have)}")
    files = sorted(p for p in source.iterdir()
                   if p.is_file() and not p.is_symlink() and p.suffix in COPY_SUFFIXES)
    size = sum(p.stat().st_size for p in files)
    if size > MAX_MEETING_BYTES:
        raise ValueError(f"{source.name}: publication inputs exceed 64 MiB")
    manifest = read_json(source / "manifest.json", {})
    expected_hashes = {row["name"]: row["sha256"] for row in manifest.get("files", [])}
    destination.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    actual_size = 0
    for path in files:
        content = path.read_bytes()
        if path.name in expected_hashes and hashlib.sha256(content).hexdigest() != expected_hashes[path.name]:
            raise ValueError(f"{source.name}: immutable evidence hash changed: {path.name}")
        actual_size += len(content)
        if actual_size > MAX_MEETING_BYTES:
            raise ValueError(f"{source.name}: publication inputs grew beyond 64 MiB")
        digest.update(path.name.encode() + b"\0" + content)
        (destination / path.name).write_bytes(content)
    if (source / ".analysis_pending").exists():
        raise ValueError(f"{source.name}: analysis changed while freezing")
    return digest.hexdigest(), actual_size


def meeting_digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.iterdir()
                       if p.is_file() and p.suffix in COPY_SUFFIXES):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


class ProgressivePublisher:
    def __init__(self, schedule, runlog, archived):
        self.schedule = schedule
        self.runlog = runlog
        self.root = schedule.WORK_DIR / "progressive" / runlog.path.stem
        self.root.mkdir(parents=True, exist_ok=False)
        self.queue = {"review_day": runlog.data["review_day"],
                      "started_at": runlog.data["started_at"],
                      "archived": list(archived), "jobs": []}
        self.seen = set()
        self.copy_seconds = 0.0
        self.queue_seconds = 0.0
        self.evidence_seconds = 0.0
        self.copy_bytes = 0
        self.process = None
        atomic_json(self.root / "queue.json", self.queue)

    def _start(self):
        if self.process is not None:
            if self.process.poll() is not None:
                raise RuntimeError("progressive publisher exited before queue drained")
            return
        env = os.environ.copy()
        env.pop("_WC_DASHBOARD_PUBLICATION_LOCK_HELD", None)
        env["WC_AU_SCHED_LOG_DIR"] = str(self.root / "logs")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with (self.root / "worker.out").open("w") as output:
            self.process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--spool", str(self.root),
                 "--owner-pid", str(os.getpid())],
                cwd=self.schedule.PROJECT_ROOT, env=env, stdout=output,
                stderr=subprocess.STDOUT, start_new_session=True,
            )

    def submit(self, folder: Path):
        if folder.name in self.seen:
            return
        queue_started = time.monotonic()
        evidence_ok = self.schedule.step_prediction_evidence(self.runlog, [folder])
        self.evidence_seconds += time.monotonic() - queue_started
        if not evidence_ok:
            self.schedule.reject_publication(self.runlog, folder, "prediction evidence failed")
            self.queue_seconds += time.monotonic() - queue_started
            return
        snapshot = None
        for step in reversed(self.runlog.data["steps"]):
            if step.get("step") == "prediction-evidence" and step.get("status") == "ok":
                receipt = next((m for m in step.get("meetings", [])
                                if m.get("meeting") == folder.name), None)
                if receipt:
                    snapshot = Path(receipt["snapshot"])
                    break
        if snapshot is None:
            raise ValueError(f"{folder.name}: no immutable prediction evidence receipt")
        size = sum(p.stat().st_size for p in snapshot.iterdir()
                   if p.is_file() and not p.is_symlink() and p.suffix in COPY_SUFFIXES)
        if self.copy_bytes + size > MAX_QUEUE_BYTES:
            raise ValueError("publication input queue exceeds 512 MiB; no large internal scratch")
        started = time.monotonic()
        job_id = f"{len(self.queue['jobs']) + 1:04d}"
        target = self.root / "inputs" / job_id / folder.name
        digest, copied = freeze_meeting(snapshot, target, meeting_name=folder.name)
        self.copy_seconds += time.monotonic() - started
        self.copy_bytes += copied
        self.queue["jobs"].append({"id": job_id, "meeting": folder.name,
                                   "folder": str(target), "digest": digest,
                                   "bytes": copied, "queued_at": time.time(),
                                   "evidence_snapshot": str(snapshot)})
        atomic_json(self.root / "queue.json", self.queue)
        self.seen.add(folder.name)
        self._start()
        self.runlog.step("progressive-publication", "queued", meeting=folder.name,
                         input_bytes=copied, foreground_copy_seconds=round(self.copy_seconds, 4))
        self.queue_seconds += time.monotonic() - queue_started

    def abort(self):
        if self.process is None or self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=10)

    def finish(self) -> dict:
        self._start()
        (self.root / "done").touch()
        started = time.monotonic()
        timeout = float(os.environ.get("WC_AU_PUBLICATION_DRAIN_SECONDS", "3600"))
        try:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("progressive publication drain exceeded deadline")
                try:
                    self.process.wait(timeout=min(30, remaining))
                    break
                except subprocess.TimeoutExpired:
                    progress = read_json(self.root / "result.json", {})
                    self.runlog.step("progressive-publication", "draining",
                                     published=len(progress.get("published", {})),
                                     queued=len(self.queue["jobs"]))
        except BaseException:
            self.abort()
            raise
        result = read_json(self.root / "result.json", {})
        if self.process.returncode != 0 or not result.get("finished"):
            result["complete"] = False
            result["worker_error"] = f"publisher exit={self.process.returncode}; {self.root / 'worker.out'}"
        missing = [j["meeting"] for j in self.queue["jobs"]
                   if result.get("published", {}).get(j["meeting"]) != j["id"]
                   and j["meeting"] not in result.get("rejected", {})]
        result["pending"] = sorted(set(result.get("pending", [])) | set(missing))
        result["complete"] = bool(result.get("complete") and not result["pending"]
                                  and not result.get("rejected"))
        result.update(copy_seconds=round(self.copy_seconds, 4), input_bytes=self.copy_bytes,
                      foreground_queue_seconds=round(self.queue_seconds, 4),
                      evidence_seconds=round(self.evidence_seconds, 4),
                      foreground_drain_seconds=round(time.monotonic() - started, 4),
                      queue_path=str(self.root / "queue.json"))
        self.runlog.data["progressive_publication"] = result
        for key in ("cloudflare_deployment", "dashboard_validation"):
            if result.get(key) is not None:
                self.runlog.data[key] = result[key]
        for name, reason in result.get("rejected", {}).items():
            self.schedule.reject_publication(self.runlog, Path(name), reason)
        if result.get("worker_error"):
            self.runlog.error("progressive-publication", result["worker_error"])
        self.runlog.step("progressive-publication", "complete" if result.get("complete") else "partial",
                         published=len(result.get("published", {})),
                         queued=len(self.queue["jobs"]), batches=result.get("batch_count", 0))
        return result


def publish_batch(schedule, root, jobs, archived, number, review_day):
    """The worker exclusively owns these globals; the extractor is a process away."""
    work = root / "build"
    work.mkdir(exist_ok=True)
    schedule.WORK_DIR = work
    log = schedule.RunLog("evening", review_day, root / "batches" / f"{number:04d}.json",
                          notify=False)
    started = time.monotonic()
    ok = False
    try:
        valid = []
        for job in jobs:
            folder = Path(job["folder"])
            if meeting_digest(folder) != job["digest"]:
                schedule.reject_publication(log, folder, "frozen input digest changed")
            else:
                valid.append(folder)
        ok = schedule.step_dashboard(
            log, valid, archived,
            recover_unpublished=False, isolate_failures=True, retain_intermediates=False,
        )
    except Exception as exc:  # noqa: BLE001 — an upload must not kill extraction
        log.error("progressive-publication", f"{type(exc).__name__}: {exc}")
    log.data["status"] = "ok" if ok else "failed"
    log.flush()
    result = {"ok": ok, "elapsed_seconds": round(time.monotonic() - started, 4),
              "rejected": log.data.get("publication_rejected", {}),
              "cloudflare_deployment": log.data.get("cloudflare_deployment"),
              "dashboard_validation": log.data.get("dashboard_validation"),
              "errors": log.data.get("errors", []), "log": str(log.path)}
    # Frozen inputs and batch JSON are sufficient to reproduce the build.
    # Do not retain N cumulative HTML/JSON copies on the internal disk.
    shutil.rmtree(work)
    return result


def run_worker(root: Path, schedule=None, poll_seconds=1.0):
    if schedule is None:
        import au_daily_schedule as schedule
    from datetime import date, datetime

    state = {"published": {}, "rejected": {}, "pending": [], "batch_count": 0,
             "deployment_count": 0, "publication_seconds": 0.0, "finished": False}
    known = {}
    seen_ids = set()
    rejected_ids = set()
    attempted = False
    while True:
        # done is written only after the final atomic queue update. Read it
        # first, otherwise a stale queue read followed by done could lose a job.
        done = (root / "done").exists()
        queue = read_json(root / "queue.json", {})
        new = [j for j in queue.get("jobs", []) if j["id"] not in seen_ids]
        for job in new:
            known[job["meeting"]] = job
            seen_ids.add(job["id"])
        if new or (done and not attempted):
            jobs = [j for j in known.values() if j["id"] not in rejected_ids]
            state["batch_count"] += 1
            batch = publish_batch(schedule, root, jobs, queue.get("archived", []),
                                  state["batch_count"], date.fromisoformat(queue["review_day"]))
            attempted = True
            state["publication_seconds"] += batch["elapsed_seconds"]
            for key in ("cloudflare_deployment", "dashboard_validation"):
                if batch.get(key) is not None:
                    state[key] = batch[key]
            for name, reason in batch["rejected"].items():
                state["rejected"][name] = reason
                rejected_ids.add(known[name]["id"])
            if batch["ok"]:
                for job in jobs:
                    if job["meeting"] not in batch["rejected"]:
                        state["published"][job["meeting"]] = job["id"]
                dep = batch.get("cloudflare_deployment") or {}
                if not dep.get("skipped"):
                    state["deployment_count"] += 1
                if state["published"] and "first_live_delay_seconds" not in state:
                    state["first_live_delay_seconds"] = round(
                        time.time() - datetime.fromisoformat(queue["started_at"]).timestamp(), 4)
            else:
                state["last_error"] = batch["errors"]
            state["pending"] = [n for n, j in known.items()
                                if state["published"].get(n) != j["id"]
                                and j["id"] not in rejected_ids]
            atomic_json(root / "result.json", state)
            # Reload after upload: several meetings may have completed meanwhile.
            continue
        if done:
            state["complete"] = not state["pending"] and not state["rejected"]
            state["finished"] = True
            atomic_json(root / "result.json", state)
            return 0
        time.sleep(poll_seconds)


def guard_owner(owner_pid: int, interval: float = 1.0):
    """A killed scheduler must not leave a publisher waiting to upload later."""
    while True:
        time.sleep(interval)
        if os.getppid() != owner_pid:
            if os.getpgrp() == os.getpid():
                os.killpg(os.getpgrp(), signal.SIGTERM)
            os._exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--owner-pid", type=int, required=True)
    args = parser.parse_args()
    threading.Thread(target=guard_owner, args=(args.owner_pid,), daemon=True).start()
    return run_worker(args.spool)


if __name__ == "__main__":
    raise SystemExit(main())
