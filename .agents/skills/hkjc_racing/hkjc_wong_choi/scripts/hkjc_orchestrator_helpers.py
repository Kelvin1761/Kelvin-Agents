#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[4]
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
        (path for path in ROOT.iterdir() if path.is_dir() and path.name.startswith(prefix)),
        key=lambda path: path.name,
    )
    if dirs:
        return str(dirs[0].resolve())
    if not auto_create:
        return None
    new_dir = (ROOT / prefix).resolve()
    new_dir.mkdir(parents=True, exist_ok=True)
    return str(new_dir)


def detect_total_races_from_url(url: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8")
        race_nos = {int(match) for match in re.findall(r"RaceNo=(\d+)", html)}
        if race_nos:
            max_race = max(race_nos)
            print(f"✅ [Auto-Detection] 從 HKJC 頁面偵測到 {max_race} 場賽事 (RaceNo: {sorted(race_nos)})")
            return max_race
    except Exception as exc:
        print(f"⚠️ [Auto-Detection] 無法偵測場數: {exc}")

    if "HV" in url.upper():
        print("⚠️ [Fallback] 跑馬地預設 9 場")
        return 9
    print("⚠️ [Fallback] 沙田預設 11 場")
    return 11


def trigger_extractor(url: str, target_dir: str) -> None:
    print("🚀 [Orchestrator] 啟動 HKJC Race Extractor 提取全日數據...")
    script_path = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "scripts" / "batch_extract.py"
    if not script_path.exists():
        print(f"❌ [Error] 找不到爬蟲腳本: {script_path}")
        raise SystemExit(1)
    total = detect_total_races_from_url(url)
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
        raise SystemExit(1) from exc
