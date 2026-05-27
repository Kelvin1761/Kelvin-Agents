#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEPLOY_SCRIPT = PROJECT_ROOT / "deploy.sh"
DISABLE_ENV = "WC_DISABLE_POST_SUCCESS_DEPLOY"
TIMEOUT_ENV = "WC_POST_SUCCESS_DEPLOY_TIMEOUT_SEC"
DEFAULT_TIMEOUT_SEC = 1800


def run_post_success_cloudflare_deploy(
    *,
    source: str,
    target_dir: Path | None = None,
    skip: bool = False,
    allow_failure: bool = True,
) -> bool:
    if skip:
        print(f"⏭️ Cloudflare deploy skipped for {source} (--skip-cloudflare-deploy)")
        return False

    if _env_truthy(DISABLE_ENV):
        print(f"⏭️ Cloudflare deploy skipped for {source} ({DISABLE_ENV}=1)")
        return False

    if not DEPLOY_SCRIPT.exists():
        message = f"⚠️ Cloudflare deploy hook missing: {DEPLOY_SCRIPT}"
        if allow_failure:
            print(message)
            return False
        raise FileNotFoundError(message)

    timeout_sec = _deploy_timeout_seconds()
    target_hint = f" [{target_dir}]" if target_dir else ""
    print("=" * 68)
    print(f"☁️ Post-Success Cloudflare Deploy — {source}{target_hint}")
    print("=" * 68)

    try:
        result = subprocess.run(
            [str(DEPLOY_SCRIPT)],
            cwd=PROJECT_ROOT,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        message = f"⚠️ Cloudflare deploy timed out after {timeout_sec}s"
        if allow_failure:
            print(message)
            return False
        raise SystemExit(message)

    if result.returncode == 0:
        print(f"✅ Cloudflare deploy finished for {source}")
        return True

    message = f"⚠️ Cloudflare deploy failed for {source} (exit {result.returncode})"
    if allow_failure:
        print(message)
        return False
    raise SystemExit(result.returncode)


def _env_truthy(name: str) -> bool:
    value = str(os.environ.get(name, "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _deploy_timeout_seconds() -> int:
    raw = str(os.environ.get(TIMEOUT_ENV, "")).strip()
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SEC
    return max(parsed, 30)


if __name__ == "__main__":
    run_post_success_cloudflare_deploy(source="manual")
