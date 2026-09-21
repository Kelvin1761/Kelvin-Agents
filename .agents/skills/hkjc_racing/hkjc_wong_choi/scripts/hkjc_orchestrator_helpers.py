#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING
PYTHON = sys.executable


def parse_url_for_details(url: str) -> tuple[str, str, str]:
    match = re.search(r"RaceDate=(\d{4})/(\d{2})/(\d{2}).*?&Racecourse=([A-Za-z]+)", url, re.IGNORECASE)
    if not match:
        print("🔍 [Auto-Discovery] URL lacks explicit RaceDate. Fetching HTML to resolve next meeting date...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8")
            html_match = re.search(
                r"racedate=(\d{4})/(\d{2})/(\d{2})&amp;Racecourse=([A-Za-z]+)",
                html,
                re.IGNORECASE,
            )
            if not html_match:
                html_match = re.search(
                    r"racedate=(\d{4})/(\d{2})/(\d{2})&Racecourse=([A-Za-z]+)",
                    html,
                    re.IGNORECASE,
                )
            if not html_match:
                raise ValueError("Invalid HKJC URL format and could not auto-discover from HTML.")
            print(
                "✅ [Auto-Discovery] Found next meeting:"
                f" {html_match.group(1)}/{html_match.group(2)}/{html_match.group(3)} at {html_match.group(4)}"
            )
            match = html_match
        except Exception as exc:
            raise ValueError(f"Failed to auto-discover date from URL: {exc}") from exc

    date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    venue_code = match.group(4).upper()
    venue_map = {"ST": "ShaTin", "HV": "HappyValley"}
    venue = venue_map.get(venue_code, venue_code)
    resolved_url = (
        "https://racing.hkjc.com/zh-hk/local/information/racecard"
        f"?racedate={match.group(1)}/{match.group(2)}/{match.group(3)}&Racecourse={venue_code}&RaceNo=1"
    )
    return venue, date_str, resolved_url


def get_target_dir(venue: str, formatted_date: str, auto_create: bool = False) -> str | None:
    prefix = f"{formatted_date}_{venue}"
    dirs = sorted(
        (path for path in HK_RACING.iterdir() if path.is_dir() and path.name.startswith(prefix)),
        key=lambda path: path.name,
    )
    if dirs:
        return str(dirs[0].resolve())
    if not auto_create:
        return None
    new_dir = (HK_RACING / prefix).resolve()
    new_dir.mkdir(parents=True, exist_ok=True)
    return str(new_dir)


def _fetch_text_with_retry(url: str, *, timeout: int = 8, attempts: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)
    assert last_error is not None
    raise last_error


def detect_total_races_from_url(url: str) -> int | None:
    try:
        html = _fetch_text_with_retry(url)
        race_nos = {int(match) for match in re.findall(r"RaceNo=(\d+)", html)}
        if race_nos:
            max_race = max(race_nos)
            print(f"✅ [Auto-Detection] 從 HKJC 頁面偵測到 {max_race} 場賽事 (RaceNo: {sorted(race_nos)})")
            return max_race
    except Exception as exc:
        print(f"⚠️ [Auto-Detection] 無法偵測場數: {exc}")

    print("⏳ [Readiness] 未能由官方 racecard 確認完整場數；唔會用 9/11 場估算。")
    return None


def cached_expected_races(target_dir: str | Path, url: str) -> int | None:
    """Return a previously official-confirmed count for this exact meeting.

    This is deliberately not inferred from files on disk. The readiness
    manifest is written only after a run has received an explicit race range,
    and its date must match the current official URL before it can be reused.
    """
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    racedate = query.get("racedate", [""])[0]
    if not racedate:
        return None
    manifest_path = Path(target_dir) / "Extraction_Readiness.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = int(payload.get("expected_races"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if payload.get("meeting_date") != racedate or not 1 <= expected <= 14:
        return None
    return expected


def trigger_extractor(url: str, target_dir: str) -> None:
    print("🚀 [Orchestrator] 啟動 HKJC Race Extractor 提取全日數據...")
    script_path = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "scripts" / "batch_extract.py"
    if not script_path.exists():
        print(f"❌ [Error] 找不到爬蟲腳本: {script_path}")
        raise SystemExit(1)
    total = detect_total_races_from_url(url)
    if total is None:
        total = cached_expected_races(target_dir, url)
        if total is None:
            # Exit 75 tells the unattended scheduler this is a source-readiness
            # condition, not a permanent code failure. The recovery job retries.
            raise SystemExit(75)
        print(
            "♻️ [Auto-Detection] Live 場數探測暫時失敗；沿用同一 meeting "
            f"readiness 已確認嘅 {total} 場。"
        )
    race_range = f"1-{total}"
    print(f"📋 [Orchestrator] 提取場次範圍: {race_range}")
    try:
        subprocess.run(
            [PYTHON, str(script_path), "--base_url", url, "--races", race_range, "--output_dir", target_dir],
            check=True,
            cwd=ROOT,
        )
    except subprocess.CalledProcessError as exc:
        print(f"❌ [Error] 數據提取腳本執行失敗: {exc}")
        raise SystemExit(exc.returncode) from exc
