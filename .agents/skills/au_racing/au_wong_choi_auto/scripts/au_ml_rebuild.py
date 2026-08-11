#!/usr/bin/env python3
"""Rebuild the complete AU Wong Choi ML research program from archive inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_commands(
    *,
    python: str,
    archive_root: Path,
    results_csv: Path,
    work_dir: Path,
    report_dir: Path,
    require_complete: bool = True,
    materialize_on_demand: bool = False,
    prefetch_workers: int = 4,
    skip_training: bool = False,
) -> tuple[list[list[str]], dict[str, Path]]:
    outputs = {
        "runtime_audit_json": work_dir / "au_ml_runtime_audit.json",
        "runtime_audit_md": work_dir / "au_ml_runtime_audit.md",
        "runtime_dataset": work_dir / "au_ml_runtime_dataset.json",
        "ml_dataset": work_dir / "au_ml_dataset.json",
        "readiness_audit": work_dir / "au_ml_readiness_audit.json",
        "readiness_report": report_dir / "au_ml_readiness_report.md",
        "experiment_results": report_dir / "au_ml_experiment_results.json",
        "experiment_report": report_dir / "au_ml_experiment_report.md",
    }
    runtime = [
        python,
        str(SCRIPT_DIR / "au_runtime_failure_audit.py"),
        "--archive-root", str(archive_root),
        "--results-csv", str(results_csv),
        "--prefetch-workers", str(prefetch_workers),
        "--output-json", str(outputs["runtime_audit_json"]),
        "--output-md", str(outputs["runtime_audit_md"]),
        "--dataset-json", str(outputs["runtime_dataset"]),
    ]
    if require_complete:
        runtime.append("--require-complete")
    if materialize_on_demand:
        runtime.append("--materialize-on-demand")
    dataset = [
        python,
        str(SCRIPT_DIR / "au_ml_dataset.py"),
        "--runtime-dataset", str(outputs["runtime_dataset"]),
        "--dataset-output", str(outputs["ml_dataset"]),
        "--audit-json", str(outputs["readiness_audit"]),
        "--readiness-md", str(outputs["readiness_report"]),
    ]
    commands = [runtime, dataset]
    if not skip_training:
        commands.append([
            python,
            str(SCRIPT_DIR / "au_ml_program.py"),
            "--dataset", str(outputs["ml_dataset"]),
            "--readiness-audit", str(outputs["readiness_audit"]),
            "--output-json", str(outputs["experiment_results"]),
            "--output-md", str(outputs["experiment_report"]),
        ])
    return commands, outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("/private/tmp/au_ml_program"))
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--materialize-on-demand", action="store_true")
    parser.add_argument("--prefetch-workers", type=int, default=4)
    parser.add_argument("--skip-training", action="store_true")
    args = parser.parse_args()

    archive_root = args.archive_root.expanduser().resolve()
    results_csv = args.results_csv.expanduser().resolve()
    if not archive_root.is_dir():
        raise SystemExit(f"Archive root not found: {archive_root}")
    if not results_csv.is_file():
        raise SystemExit(f"Results CSV not found: {results_csv}")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    commands, outputs = build_commands(
        python=sys.executable,
        archive_root=archive_root,
        results_csv=results_csv,
        work_dir=args.work_dir.resolve(),
        report_dir=args.report_dir.resolve(),
        require_complete=not args.allow_incomplete,
        materialize_on_demand=args.materialize_on_demand,
        prefetch_workers=max(1, args.prefetch_workers),
        skip_training=args.skip_training,
    )
    manifest_path = args.work_dir / "au_ml_rebuild_manifest.json"
    manifest = {
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "inputs": {
            "archive_root": str(archive_root),
            "results_csv": str(results_csv),
            "results_csv_sha256": sha256_file(results_csv),
        },
        "commands": commands,
        "outputs": {key: str(path) for key, path in outputs.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    try:
        for command in commands:
            print("RUN:", " ".join(command), flush=True)
            subprocess.run(command, check=True)
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = repr(exc)
        manifest["completed_at"] = datetime.now().astimezone().isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise
    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now().astimezone().isoformat()
    manifest["output_sha256"] = {
        key: sha256_file(path) for key, path in outputs.items() if path.is_file()
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
