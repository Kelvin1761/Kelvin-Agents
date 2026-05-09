#!/usr/bin/env python3
"""
Racing Content Guard
====================
Python-first dummy / placeholder prevention for racing outputs.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


DUMMY_MARKERS = [
    "[FILL]",
    "[AUTO]",
    "TODO",
    "placeholder",
    "dummy",
    "stub",
    "待補",
    "暫無資料",
    "自動生成",
    "批量填充",
    "auto_fill",
    "auto_expert",
    "自動法醫分析",
    "自動匹配系統法則",
    "分析中",
    "待分析",
]

FLUFF_PHRASES = [
    "具備一定競爭力",
    "值得留意",
    "有望爭勝",
    "不容忽視",
    "實力不俗",
    "表現平穩",
    "近期走勢",
    "狀態有待觀察",
    "可爭一席",
    "尚算理想",
    "仍有機會",
    "good profile",
    "looks suitable",
    "positive setup",
    "strong chance",
]

AUTO_ALLOWED_SUFFIXES = {
    "base_rating",
    "final_rating",
    "computed_rating",
    "rating",
    "rating_score",
}


class RacingContentError(ValueError):
    """Raised when racing content contains dummy or placeholder material."""


def _normalise_marker(marker: str) -> str:
    return marker.lower() if marker.isascii() else marker


def _contains_marker(text: str, marker: str) -> bool:
    if marker == "[FILL]":
        return bool(re.search(r"\[FILL(?:[:\]\s])", text, re.IGNORECASE))
    if marker == "[AUTO]":
        return bool(re.search(r"\[AUTO(?:[:\]\s])", text, re.IGNORECASE))
    if marker.isascii():
        return marker.lower() in text.lower()
    return marker in text


def scan_text_for_dummy(content: str) -> list[str]:
    """Return dummy markers / fluff phrases found in plain text."""
    text = str(content or "")
    issues: list[str] = []
    for marker in DUMMY_MARKERS:
        if _contains_marker(text, marker):
            issues.append(f"text contains {marker}")
    for phrase in FLUFF_PHRASES:
        if _contains_marker(text, phrase):
            issues.append(f"text contains fluff phrase {phrase}")
    return issues


def _path_join(parent: str, key: Any) -> str:
    key_s = str(key)
    return key_s if not parent else f"{parent}.{key_s}"


def _is_auto_allowed(path: str) -> bool:
    leaf = path.rsplit(".", 1)[-1]
    return leaf in AUTO_ALLOWED_SUFFIXES


def _scan_scalar(value: Any, path: str, allow_pending_fill: bool) -> list[str]:
    if not isinstance(value, str):
        return []
    issues: list[str] = []
    for marker in DUMMY_MARKERS:
        if marker == "[FILL]" and allow_pending_fill:
            continue
        if marker == "[AUTO]" and _is_auto_allowed(path):
            continue
        if _contains_marker(value, marker):
            issues.append(f"{path} contains {marker}")
    for phrase in FLUFF_PHRASES:
        if _contains_marker(value, phrase):
            issues.append(f"{path} contains fluff phrase {phrase}")
    return issues


def scan_json_for_dummy(
    data: dict,
    allow_pending_fill: bool = False,
    context: str = "",
    path: str | None = None,
) -> list[str]:
    """Recursively scan JSON-like data and return precise field paths."""
    root = path if path is not None else context
    issues: list[str] = []

    def walk(value: Any, current_path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, _path_join(current_path, key))
            return
        if isinstance(value, list):
            for idx, child in enumerate(value):
                walk(child, _path_join(current_path, idx))
            return
        issues.extend(_scan_scalar(value, current_path or "<root>", allow_pending_fill))

    walk(data, root)
    return issues


def assert_no_dummy_text(content: str, context: str) -> None:
    issues = scan_text_for_dummy(content)
    if issues:
        raise RacingContentError(
            f"Dummy content detected in {context}:\n"
            + "\n".join(f"- {issue}" for issue in issues)
        )


def assert_no_dummy_json(
    data: dict,
    context: str,
    allow_pending_fill: bool = False,
) -> None:
    issues = scan_json_for_dummy(
        data,
        allow_pending_fill=allow_pending_fill,
        context=context,
    )
    if issues:
        raise RacingContentError(
            f"Dummy JSON detected in {context}:\n"
            + "\n".join(f"- {issue}" for issue in issues)
        )


def _runtime_dir_for(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if parent.name == ".runtime":
            return parent
    return path.parent / ".runtime"


def quarantine_file(path: str, reason: str) -> str:
    """Move a bad output into .runtime/quarantine and write a reason file."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(path)

    quarantine_dir = _runtime_dir_for(src) / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = quarantine_dir / f"{src.name}.{stamp}.quarantined"
    counter = 1
    while dest.exists():
        dest = quarantine_dir / f"{src.name}.{stamp}.{counter}.quarantined"
        counter += 1

    os.replace(src, dest)

    reason_path = dest.with_suffix(dest.suffix + ".reason.txt")
    tmp_reason = reason_path.with_suffix(reason_path.suffix + ".tmp")
    payload = {
        "source": str(src),
        "quarantined_to": str(dest),
        "reason": reason,
        "timestamp": stamp,
    }
    tmp_reason.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_reason, reason_path)
    return str(dest)
