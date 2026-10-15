"""Captured immutable public RQ runner-time evidence for prospective AU scoring."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
import hashlib
import gzip
import os
import tempfile

try:
    import fcntl
except ImportError:  # Windows runtime
    fcntl = None
import json
import re
from zoneinfo import ZoneInfo

from au_racing_engine.full_time_speed import MODEL_VERSION, default_bundle_path, parse_xml, read_bundle
from au_racing_engine.io_utils import write_json_atomic

BASE = "https://www.racingqueensland.com.au"
INDEX = BASE + "/industry/thoroughbred/thoroughbred-sectionals"


def get(url):
    with urlopen(Request(url, headers={"User-Agent": "WongChoi-TimeEvidence/1.0"}), timeout=25) as response:
        return response.read()


def publish_bundle(events, sources, path, *, valid_from=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("capture time must have timezone")
    now = now.astimezone(timezone.utc)
    ordered = sorted(events, key=lambda e: (e["date"], e["track"], e["key"][2], e["distance"]))
    keys = [tuple(e["key"]) for e in ordered]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate time evidence events")
    payload = json.dumps(ordered, separators=(",", ":"), sort_keys=True).encode()
    digest = hashlib.sha256(payload).hexdigest()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(path.read_text()) if path.exists() else {}
    obj = {
        "model_version": MODEL_VERSION,
        "captured_at": now.isoformat(),
        "valid_from": valid_from
        or old.get("valid_from")
        or (now.astimezone(ZoneInfo("Australia/Sydney")).date() + timedelta(days=1)).isoformat(),
        "events_sha256": digest,
        "events": ordered,
        "sources": sources,
        "historical_availability": "not_certified; prospective capture only",
        "latest_event": max(e["date"] for e in ordered) if ordered else None,
    }
    # Snapshot name includes capture time: same payload can have a different
    # publication record without replacing either prior immutable snapshot.
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = path.parent / f"{stamp}-{digest[:16]}.json.gz"
    obj["snapshot_file"] = snapshot.name
    payload = gzip.compress(json.dumps(obj, ensure_ascii=False).encode(), mtime=0)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".time-", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, snapshot)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    write_json_atomic(path, obj)
    return obj


def refresh(path=None):
    path = Path(path or default_bundle_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / "refresh.lock").open("a+b") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            return _refresh_locked(path)
        import msvcrt

        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            return _refresh_locked(path)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _refresh_locked(path):
    path = Path(path or default_bundle_path())
    if not path.exists():
        raise FileNotFoundError("AU runner-time cache has not been provisioned")
    info = path.stat()
    old = read_bundle(str(path), info.st_mtime_ns, info.st_size)
    since = (datetime.fromisoformat(old["latest_event"]).date() - timedelta(days=7)).strftime("%Y%m%d")
    index = get(INDEX).decode()
    links = sorted(set(re.findall(r'href="([^"]+\.zip)"', index)))
    known = {record["url"] for record in old["sources"]}
    events = {tuple(e["key"]): e for e in old["events"]}
    sources = list(old["sources"])
    for link in links:
        match = re.search(r"/(\d{8})_", link)
        if not match or match[1] < since or BASE + link in known:
            continue
        url = BASE + link
        raw = get(url)
        source_file = path.parent / (hashlib.sha256(raw).hexdigest() + ".zip")
        if not source_file.exists():
            source_file.write_bytes(raw)
        with ZipFile(BytesIO(raw)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".xml"):
                    continue
                event = parse_xml(archive.read(name), url + "#" + name)
                if event:
                    if tuple(event["key"]) in events:
                        raise ValueError("overlapping new time source: refusing silent replacement")
                    events[tuple(event["key"])] = event
        sources.append(
            {
                "url": url,
                "file": source_file.name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    if len(sources) == len(old["sources"]):
        return {"status": "unchanged", "events": len(events), "latest_event": old["latest_event"]}
    obj = publish_bundle(list(events.values()), sources, path)
    return {"status": "updated", "events": len(events), "latest_event": obj["latest_event"]}
