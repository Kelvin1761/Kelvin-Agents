"""Editable captions remain separate from recognition and clip analysis."""
import math
from functools import lru_cache
from pathlib import Path

from .common import digest, load


@lru_cache(maxsize=1)
def converter():
    from opencc import OpenCC
    return OpenCC("s2hk")


def hk(text):
    return converter().convert(text)


def document(project, manifest, analysis):
    path = Path(project) / "captions.json"
    if path.exists():
        return load(path)
    segments = []
    for i, s in enumerate(analysis["transcript"]):
        segments.append(dict(s, id=digest(dict(index=i, start=s["start"], end=s["end"])),
                             raw_text=s["text"], text=hk(s["text"]), reviewed=False,
                             funny=False, uncertain=s.get("avg_logprob", -1) < -.75))
    return dict(revision=0, analysis_file=manifest["analysis_file"], segments=segments)


def validate(data, duration):
    if not isinstance(data.get("segments"), list) or len(data["segments"]) > 20000:
        raise ValueError("Invalid captions")
    ids = set()
    for s in data["segments"]:
        a, b = float(s["start"]), float(s["end"])
        if not all(math.isfinite(t) for t in (a, b)) or not 0 <= a < b <= duration:
            raise ValueError("Invalid caption timestamps")
        if not isinstance(s["text"], str) or len(s["text"]) > 5000:
            raise ValueError("Invalid caption text")
        if not isinstance(s.get("id"), str) or s["id"] in ids:
            raise ValueError("Caption IDs must be unique")
        ids.add(s["id"])
        s.update(start=a, end=b)
    data["segments"].sort(key=lambda s: (s["start"], s["end"]))
    return data


def export_segments(project, manifest, analysis):
    captions = document(project, manifest, analysis)
    if captions["analysis_file"] != manifest["analysis_file"]:
        raise ValueError("Recognition changed since caption editing; keep/merge your edits before export")
    return [s for s in captions["segments"] if s["text"].strip()]
