"""Read-only verifier for a control-plane deployment in another checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence


DOMAIN_RUNTIME_FILES = {
    "au": (
        ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh",
    ),
    "hkjc": (
        ".agents/skills/hkjc_racing/hkjc_daily_auto/run_hkjc_daily_schedule.sh",
    ),
    "tennis": (
        "tennis-wong-choi/scripts/run_tennis_daily_schedule.sh",
    ),
    "nba": (
        ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_paths(source: Path, domain: str) -> tuple[Path, ...]:
    package = source / ".agents/skills/shared_wong_choi"
    shared = tuple(
        path.relative_to(source)
        for path in sorted(package.glob("*.py"))
        if path.name != "deployment_verify.py"
    )
    if not shared:
        raise FileNotFoundError(f"shared control-plane package missing: {package}")
    runtime = tuple(Path(value) for value in DOMAIN_RUNTIME_FILES[domain])
    return shared + runtime


def _git_output(root: Path, *args: str) -> str | None:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def verify_deployment(source: Path, target: Path, domain: str) -> dict:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError("source and target checkout must be different")
    if not target.is_dir():
        raise FileNotFoundError(f"target checkout missing: {target}")

    files = []
    for relative in required_paths(source, domain):
        source_path = source / relative
        target_path = target / relative
        if not source_path.is_file():
            state = "source_missing"
            source_hash = None
            target_hash = sha256(target_path) if target_path.is_file() else None
        elif not target_path.is_file():
            state = "target_missing"
            source_hash = sha256(source_path)
            target_hash = None
        else:
            source_hash = sha256(source_path)
            target_hash = sha256(target_path)
            state = "aligned" if source_hash == target_hash else "different"
        files.append(
            {
                "path": relative.as_posix(),
                "state": state,
                "source_sha256": source_hash,
                "target_sha256": target_hash,
            }
        )

    target_status = _git_output(target, "status", "--porcelain") or ""
    required = {item["path"] for item in files}
    dirty_overlap = []
    for line in target_status.splitlines():
        candidate = line[3:].strip()
        if " -> " in candidate:
            candidate = candidate.rsplit(" -> ", 1)[-1]
        if candidate in required:
            dirty_overlap.append(candidate)

    counts: dict[str, int] = {}
    for item in files:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    aligned = bool(files) and all(item["state"] == "aligned" for item in files)
    return {
        "schema_version": "wong-choi-deployment-verification/v1",
        "domain": domain,
        "source": str(source),
        "target": str(target),
        "source_commit": _git_output(source, "rev-parse", "HEAD"),
        "target_commit": _git_output(target, "rev-parse", "HEAD"),
        "status": "aligned" if aligned else "out_of_sync",
        "safe_to_activate": aligned and not dirty_overlap,
        "counts": counts,
        "target_dirty_overlap": sorted(dirty_overlap),
        "files": files,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--domain", choices=tuple(DOMAIN_RUNTIME_FILES), required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_deployment(args.source, args.target, args.domain)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{result['domain']}: {result['status']} "
            f"({result['counts']}); safe_to_activate={result['safe_to_activate']}"
        )
        for item in result["files"]:
            if item["state"] != "aligned":
                print(f"  {item['state']}: {item['path']}")
        for path in result["target_dirty_overlap"]:
            print(f"  target_dirty_overlap: {path}")
    return 0 if result["safe_to_activate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
