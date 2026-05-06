"""
racing_content_guard.py — Production-grade dummy/placeholder prevention layer.

Provides scan, assert, and quarantine functions to ensure no synthetic,
placeholder, or auto-generated content survives into final pipeline outputs.

Allowed:
  - [FILL] in pending Race_X_Logic.json before a horse is completed
  - [FILL] in WorkCard instructions

Not allowed in final outputs:
  - [FILL] in completed horse entry
  - [FILL] in Analysis.md
  - [FILL] in verdict
  - final_rating-only horse (matrix must be present)
  - matrix inferred from final_rating
  - generic fluff phrases
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

# ── Markers that indicate placeholder / synthetic content ──
DUMMY_MARKERS = [
    "[FILL]", "[AUTO]", "TODO", "placeholder", "dummy", "stub",
    "待補", "暫無資料",
    "自動生成", "批量填充", "auto_fill", "auto_expert", "自動法醫分析",
    "自動匹配系統法則", "分析中", "待分析",
]

# ── Phrases that indicate generic / empty LLM generation ──
FLUFF_PHRASES = [
    "具備一定競爭力", "值得留意", "有望爭勝", "不容忽視",
    "實力不俗", "表現平穩", "近期走勢", "狀態有待觀察", "可爭一席",
    "尚算理想", "仍有機會",
]


def scan_text_for_dummy(content: str) -> list[str]:
    """Scan a raw string for dummy markers or fluff phrases.
    Returns a list of human-readable error strings (empty = clean).
    """
    errors = []
    if not content:
        return errors

    for marker in DUMMY_MARKERS:
        if marker in content:
            errors.append(f"Found dummy marker: {marker}")

    for fluff in FLUFF_PHRASES:
        if fluff in content:
            errors.append(f"Found generic fluff phrase: {fluff}")

    return errors


def scan_json_for_dummy(
    data,
    allow_pending_fill: bool = False,
    path: str = "",
    context: str = "",
) -> list[str]:
    """Recursively scan a JSON structure for dummy content.

    Args:
        data: The JSON-like object to scan (dict, list, str, etc.).
        allow_pending_fill: If True, [FILL] markers are permitted
            (e.g. in pending skeletons / WorkCards).
        path: Internal — tracks the current field path for error messages.
        context: Optional top-level context label (used in first call).

    Returns:
        A list of error strings with precise object paths (empty = clean).
    """
    if context and not path:
        path = context

    errors = []

    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}" if path else str(k)
            errors.extend(scan_json_for_dummy(v, allow_pending_fill, new_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]"
            errors.extend(scan_json_for_dummy(item, allow_pending_fill, new_path))
    elif isinstance(data, str):
        for marker in DUMMY_MARKERS:
            if marker == "[FILL]" and allow_pending_fill:
                continue
            if marker in data:
                errors.append(f"Field '{path}' contains dummy marker: {marker}")

        for fluff in FLUFF_PHRASES:
            if fluff in data:
                errors.append(f"Field '{path}' contains generic fluff phrase: {fluff}")

    return errors


def assert_no_dummy_text(content: str, context: str) -> None:
    """Raise ValueError if text contains any dummy content."""
    errors = scan_text_for_dummy(content)
    if errors:
        raise ValueError(
            f"Dummy check failed for {context}:\n"
            + "\n".join(f"- {e}" for e in errors)
        )


def assert_no_dummy_json(
    data: dict, context: str, allow_pending_fill: bool = False
) -> None:
    """Raise ValueError if JSON object contains any dummy content."""
    errors = scan_json_for_dummy(data, allow_pending_fill)
    if errors:
        raise ValueError(
            f"Dummy check failed for {context}:\n"
            + "\n".join(f"- {e}" for e in errors)
        )


def quarantine_file(filepath: str, reason: str) -> str:
    """Move a bad file to .runtime/quarantine/ and create a .reason.txt.

    Uses atomic move where possible (shutil.move).
    Returns the quarantine destination path, or '' if source missing.
    """
    if not os.path.exists(filepath):
        return ""

    src_path = Path(filepath)
    base_dir = src_path.parent
    quarantine_dir = base_dir / ".runtime" / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{timestamp}_{src_path.name}"
    dest_path = quarantine_dir / dest_name

    # Atomic move
    shutil.move(str(src_path), str(dest_path))

    # Write reason file
    reason_path = quarantine_dir / f"{timestamp}_{src_path.stem}_reason.txt"
    with open(reason_path, "w", encoding="utf-8") as f:
        f.write(f"File {src_path.name} quarantined at {timestamp}.\n")
        f.write(f"Reason:\n{reason}\n")

    print(f"🚨 [QUARANTINE] {src_path.name} moved to {dest_path}")
    return str(dest_path)
