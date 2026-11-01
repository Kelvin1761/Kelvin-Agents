#!/usr/bin/env python3
"""將資料根入面嘅舊檔原地轉做 APFS 透明壓縮。

點解：2026-11-01 Mac 內置碟淨 4.8GB。prediction snapshot 同場次檔大部分係
JSON／markdown，壓縮後細 ~78%，而 APFS 透明壓縮令路徑、內容、mtime 全部唔變 ——
讀檔嘅 code 一行都唔使改，manifest 嘅 sha256 照對得上。

逐個檔做：ditto --hfsCompression 去同一 volume 嘅 staging → 核對 sha256 →
os.replace 換入原位（原子操作，冇「檔案暫時唔見咗」嘅空窗）。
會原地寫嘅檔（DB、append log、lock）唔郁；啱啱寫完嘅檔（< --min-age-days）唔郁；
hardlink 唔郁。之後有人覆寫個檔，佢只係變返未壓縮，唔會壞。

  python3 compress_data_root.py ~/WongChoiData               # 真做
  python3 compress_data_root.py ~/WongChoiData --dry-run     # 只數
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import time
from pathlib import Path

UF_COMPRESSED = 0x20  # sys/stat.h；os.stat 冇匯出呢個常數
MIN_BYTES = 16 * 1024
STAGING_NAME = ".compress-staging"
SKIP_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".jsonl", ".log", ".lock", ".pid", ".tmp"}
SKIP_NAME_ENDINGS = ("-wal", "-shm", "-journal")
SKIP_DIRS = {".git", STAGING_NAME, "__pycache__", ".venv"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _eligible(path: Path, st: os.stat_result, cutoff: float) -> bool:
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        return False
    if st.st_size < MIN_BYTES or st.st_flags & UF_COMPRESSED or st.st_mtime > cutoff:
        return False
    name = path.name
    return path.suffix.lower() not in SKIP_SUFFIXES and not name.endswith(SKIP_NAME_ENDINGS)


def candidates(root: Path, cutoff: float):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                st = path.lstat()
            except OSError:
                continue
            if _eligible(path, st, cutoff):
                yield path, st


def compress_file(path: Path, before: os.stat_result, staging: Path) -> tuple[str, int]:
    """Return (outcome, allocated bytes after). Outcome: compressed / incompressible / changed / failed."""
    tmp = staging / f"{os.getpid()}-{before.st_ino}.part"
    tmp.unlink(missing_ok=True)
    try:
        if subprocess.run(["ditto", "--hfsCompression", str(path), str(tmp)],
                          capture_output=True).returncode != 0:
            return "failed", 0
        after = tmp.lstat()
        if not after.st_flags & UF_COMPRESSED:
            return "incompressible", 0
        if after.st_size != before.st_size or _sha256(tmp) != _sha256(path):
            return "failed", 0
        now = path.lstat()
        if (now.st_ino, now.st_size, now.st_mtime_ns) != (before.st_ino, before.st_size, before.st_mtime_ns):
            return "changed", 0
        os.replace(tmp, path)
        return "compressed", after.st_blocks * 512
    finally:
        tmp.unlink(missing_ok=True)


def run(root: Path, *, min_age_days: float, time_budget: float, dry_run: bool) -> dict:
    root = root.expanduser().resolve()
    summary = {"root": str(root), "dry_run": dry_run, "compressed": 0, "incompressible": 0,
               "changed": 0, "failed": 0, "bytes_before": 0, "bytes_after": 0, "budget_exhausted": False}
    if platform.system() != "Darwin" or shutil.which("ditto") is None:
        summary["skipped"] = "needs macOS ditto"
        return summary
    cutoff = time.time() - min_age_days * 86400
    deadline = time.monotonic() + time_budget
    staging = root / STAGING_NAME
    if not dry_run:
        staging.mkdir(exist_ok=True)
    try:
        for path, st in candidates(root, cutoff):
            if time.monotonic() > deadline:
                summary["budget_exhausted"] = True
                break
            if dry_run:
                summary["compressed"] += 1
                summary["bytes_before"] += st.st_blocks * 512
                continue
            outcome, allocated = compress_file(path, st, staging)
            summary[outcome] += 1
            if outcome == "compressed":
                summary["bytes_before"] += st.st_blocks * 512
                summary["bytes_after"] += allocated
    finally:
        if not dry_run:
            shutil.rmtree(staging, ignore_errors=True)
    if dry_run:
        summary["eligible_gib"] = round(summary["bytes_before"] / 2**30, 2)
    else:
        summary["saved_gib"] = round((summary["bytes_before"] - summary["bytes_after"]) / 2**30, 2)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--min-age-days", type=float, default=3)
    parser.add_argument("--time-budget", type=float, default=1800, help="秒；夠鐘就停，下次續做")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.root.expanduser().is_dir():
        print(json.dumps({"root": str(args.root), "skipped": "missing"}))
        return 0
    summary = run(args.root, min_age_days=args.min_age_days, time_budget=args.time_budget, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
