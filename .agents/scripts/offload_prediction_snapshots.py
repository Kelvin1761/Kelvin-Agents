#!/usr/bin/env python3
"""Move settled AU meetings' pre-race snapshots to the external disk.

`<AU_RACING>/Archive/<meeting>/_prediction_snapshots/` is 3.1GB of the Mac's
6.5GB data root (2026-11-02) and only grows. Each offload:

  1. copies the folder to `<archive>/au/<meeting>/_prediction_snapshots/`
     through a staging name, then compares every file's name, size and sha256
     against the source;
  2. writes `<meeting>/_prediction_snapshots.offloaded.json` (the marker that
     `wongchoi_paths.prediction_snapshot_dir` follows);
  3. only then deletes the local folder.

Readers never see a gap: until step 3 the local folder wins, after it the
marker does. With the disk unplugged they raise `SnapshotArchiveOffline`
instead of reading an empty folder.

Only meetings already under `Archive/` qualify: those are settled, and their
production evidence paths already point at the pre-Archive location, so moving
them breaks no direct reference that worked before. `--verify` checks every
marker still resolves to a complete copy (健康.sh runs it); `--restore`
brings one meeting back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from wongchoi_paths import (  # noqa: E402
    AU_RACING,
    SNAPSHOT_ARCHIVE_ROOT,
    snapshot_offload_marker,
)

NAME = "_prediction_snapshots"
SCHEMA = "wong-choi-snapshot-offload/v1"
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")
MIN_ARCHIVE_FREE = 20 * 1024**3


def tree_digest(root: Path) -> dict:
    """Names, sizes and sha256 of every file, in a stable order."""
    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink()):
        if path.is_symlink():
            raise RuntimeError(f"symlink inside snapshot folder: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append((path.relative_to(root).as_posix(), path.stat().st_size, digest.hexdigest()))
    combined = hashlib.sha256(json.dumps(files).encode()).hexdigest()
    return {"files": len(files), "bytes": sum(f[1] for f in files), "tree_sha256": combined}


def mount_point(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    while not path.exists():
        path = path.parent
    while not os.path.ismount(path):
        path = path.parent
    return path


def archive_ready(archive_root: Path) -> str | None:
    """None when writable, else why not. A missing /Volumes disk must not
    turn into a folder on the Mac's own disk."""
    mount = mount_point(archive_root)
    if mount in (Path("/"), Path("/System/Volumes/Data")):
        return f"{archive_root} 唔喺外置碟上（mount point {mount}）—— 外置碟未掛載？"
    if shutil.disk_usage(mount).free < MIN_ARCHIVE_FREE:
        return f"外置碟 {mount} 可用空間少過 20GB"
    return None


def candidates(au_root: Path, min_age_days: int, today: date) -> list[Path]:
    cutoff = today - timedelta(days=min_age_days)
    out = []
    archive = au_root / "Archive"
    if not archive.is_dir():
        return out
    for meeting in sorted(archive.iterdir()):
        m = DATE_PREFIX.match(meeting.name)
        if not m or not (meeting / NAME).is_dir() or (meeting / NAME).is_symlink():
            continue
        if date.fromisoformat(m.group(1)) <= cutoff:
            out.append(meeting)
    return out


def offload(meeting: Path, archive_root: Path) -> dict:
    local = meeting / NAME
    relpath = Path("au") / meeting.name / NAME
    dest = archive_root / relpath
    source = tree_digest(local)
    if dest.exists():
        # A previous run copied but stopped before the marker: reuse only an exact copy.
        if tree_digest(dest) != source:
            shutil.rmtree(dest)
    if not dest.exists():
        staging = dest.with_name(f".{NAME}.partial-{os.getpid()}")
        if staging.exists():
            shutil.rmtree(staging)
        staging.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ditto", str(local), str(staging)], check=True)
        copied = tree_digest(staging)
        if copied != source:
            shutil.rmtree(staging)
            raise RuntimeError(f"{meeting.name}: copy differs from source ({copied} vs {source})")
        os.replace(staging, dest)
    if tree_digest(local) != source:
        raise RuntimeError(f"{meeting.name}: source changed during offload; left in place")
    marker = snapshot_offload_marker(meeting, NAME)
    payload = {
        "schema_version": SCHEMA,
        "archive_relpath": relpath.as_posix(),
        "offloaded_at": datetime.now(timezone.utc).isoformat(),
        **source,
    }
    temp = marker.with_name(marker.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, marker)
    trash = meeting / f".{NAME}.offload-trash"
    os.replace(local, trash)
    shutil.rmtree(trash)
    return payload


def markers(au_root: Path) -> list[Path]:
    return sorted((au_root / "Archive").glob(f"*/{NAME}.offloaded.json"))


def verify(au_root: Path, archive_root: Path, deep: bool) -> list[str]:
    problems = []
    for marker in markers(au_root):
        meeting = marker.parent
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            dest = archive_root / payload["archive_relpath"]
        except (OSError, ValueError, KeyError) as exc:
            problems.append(f"{meeting.name}: marker unreadable ({exc})")
            continue
        if not dest.is_dir():
            problems.append(f"{meeting.name}: archive copy missing at {dest}")
            continue
        if deep:
            got = tree_digest(dest)
            want = {k: payload[k] for k in ("files", "bytes", "tree_sha256")}
            if got != want:
                problems.append(f"{meeting.name}: archive copy differs from marker")
        else:
            count = sum(1 for p in dest.rglob("*") if p.is_file())
            if count != payload.get("files"):
                problems.append(f"{meeting.name}: {count} files on disk, marker says {payload.get('files')}")
    return problems


def restore(meeting: Path, archive_root: Path) -> None:
    marker = snapshot_offload_marker(meeting, NAME)
    payload = json.loads(marker.read_text(encoding="utf-8"))
    dest = archive_root / payload["archive_relpath"]
    local = meeting / NAME
    if local.exists():
        raise RuntimeError(f"{local} already exists")
    staging = meeting / f".{NAME}.restore-{os.getpid()}"
    subprocess.run(["ditto", str(dest), str(staging)], check=True)
    if tree_digest(staging)["tree_sha256"] != payload["tree_sha256"]:
        shutil.rmtree(staging)
        raise RuntimeError(f"{meeting.name}: restored copy differs from marker")
    os.replace(staging, local)
    marker.unlink()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--au-root", type=Path, default=AU_RACING)
    ap.add_argument("--archive-root", type=Path, default=SNAPSHOT_ARCHIVE_ROOT)
    ap.add_argument("--min-age-days", type=int, default=14)
    ap.add_argument("--time-budget", type=float, default=1800, help="seconds; stop starting new meetings after this")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true", help="check every marker resolves to a complete copy")
    ap.add_argument("--deep", action="store_true", help="with --verify: re-hash every archived file")
    ap.add_argument("--restore", metavar="MEETING", help="bring one meeting's snapshots back to the Mac")
    args = ap.parse_args(argv)
    archive_root = args.archive_root

    if args.verify:
        problems = verify(args.au_root, archive_root, args.deep)
        n = len(markers(args.au_root))
        print(json.dumps({"offloaded_meetings": n, "problems": problems}, ensure_ascii=False))
        return 1 if problems else 0
    if args.restore:
        restore(args.au_root / "Archive" / args.restore, archive_root)
        print(f"restored {args.restore}")
        return 0

    todo = candidates(args.au_root, args.min_age_days, date.today())
    if args.dry_run:
        size = sum(p.stat().st_size for m in todo for p in (m / NAME).rglob("*") if p.is_file())
        print(json.dumps({"eligible_meetings": len(todo), "eligible_gib": round(size / 1024**3, 2)}))
        return 0
    reason = archive_ready(archive_root)
    if reason:
        print(json.dumps({"skipped": reason}, ensure_ascii=False))
        return 0
    started = time.monotonic()
    done, failed, moved = 0, [], 0
    for meeting in todo:
        if time.monotonic() - started > args.time_budget:
            break
        try:
            moved += offload(meeting, archive_root)["bytes"]
            done += 1
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            failed.append(f"{meeting.name}: {exc}")
    print(json.dumps({"offloaded": done, "remaining": len(todo) - done - len(failed),
                      "moved_gib": round(moved / 1024**3, 2), "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
