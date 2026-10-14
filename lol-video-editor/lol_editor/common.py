import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile


def run(args, **kwargs):
    result = subprocess.run([str(a) for a in args], capture_output=True, **kwargs)
    if result.returncode:
        error = result.stderr
        if isinstance(error, bytes):
            error = error.decode(errors="replace")
        raise RuntimeError(f"{args[0]} failed: {error[-4000:]}")
    return result.stdout


def probe(source):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", source]))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise ValueError("Input has no video stream")
    return {"duration": float(data["format"]["duration"]), "width": video["width"],
            "height": video["height"], "audio": [s for s in data["streams"]
                                                  if s["codec_type"] == "audio"]}


def identity(source):
    path = Path(source).resolve(strict=True)
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2, allow_nan=False)
        tmp.write("\n")
        name = tmp.name
    os.replace(name, path)


@contextlib.contextmanager
def lock(project):
    """Exclusive writer lock; stale locks must be removed after checking the PID."""
    path = Path(project) / ".writer.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError(f"Project is busy ({path}); inspect its PID before removing a stale lock")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def validate_selection(data, duration):
    if not isinstance(data, dict):
        raise ValueError("Selection must be an object")
    for kind in ("highlights", "shorts"):
        clips = data.get(kind)
        if not isinstance(clips, list):
            raise ValueError(f"{kind} must be a list")
        if kind == "shorts" and len(clips) > 5:
            raise ValueError("Choose at most five Shorts")
        previous_end = -1.0
        for c in sorted(clips, key=lambda c: float(c["start"])):
            start, end = float(c["start"]), float(c["end"])
            if not all(math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= duration:
                raise ValueError(f"Invalid {kind} interval {start}–{end}")
            if start < previous_end:
                raise ValueError(f"Overlapping {kind} clips; duplicate moments are disallowed")
            previous_end = end
            if "clips" in c:
                last = start
                if not isinstance(c["clips"],list) or not c["clips"]:
                    raise ValueError("Shorts subclips must be a non-empty list")
                for part in c["clips"]:
                    a,b=float(part["start"]),float(part["end"])
                    if not all(math.isfinite(t) for t in (a,b)) or not last <= a < b <= end:
                        raise ValueError("Invalid Shorts subclip bounds or order")
                    last=b
    return data


def project_analysis(project):
    manifest = load(Path(project) / "project.json")
    if identity(manifest["source"]["path"]) != manifest["source"]:
        raise ValueError("Source changed since analysis; analyze the recording again")
    return manifest, load(Path(project) / manifest["analysis_file"])
