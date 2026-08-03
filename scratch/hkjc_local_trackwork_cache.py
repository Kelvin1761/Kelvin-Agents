#!/usr/bin/env python3
"""Fetch compact official HKJC gallop/trial history for point-in-time research."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import threading

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
TRACKWORK = ROOT / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts/extract_trackwork.py"
DATASET = ROOT / "scratch/hkjc_ranking_dataset_current.csv"
CACHE = ROOT / "scratch/hkjc_local_trackwork_quality_cache.json"

spec = importlib.util.spec_from_file_location("hkjc_trackwork", TRACKWORK)
tw = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(tw)
_local = threading.local()


def session() -> requests.Session:
    value = getattr(_local, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update({
            "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.7",
        })
        _local.session = value
    return value


def fetch(brand: str) -> tuple[str, dict]:
    try:
        horseid = tw.brand_to_horseid(brand)
        response = session().get(tw.trackworkresult_url(horseid), timeout=25)
        response.raise_for_status()
        entries = tw.parse_trackwork_rows(
            response.text, {"horseid": horseid, "trainer": "", "jockey": ""},
            None, 9999,
        )
        compact = [
            {
                "date": entry["date"],
                "type": entry["type"],
                "location": entry["location"],
                "details": entry["details"],
                "sectionals": entry["sectionals"],
                "final_time": entry["final_time"],
            }
            for entry in entries if entry["type"] in {"trial", "gallop"}
        ]
        return brand, {"status": "ok", "entries": compact}
    except Exception as exc:
        return brand, {"status": "error", "error": str(exc), "entries": []}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    brands = sorted(pd.read_csv(DATASET).horse_id.dropna().astype(str).unique())
    payload = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {
        "source": "HKJC local trackworkresult", "horses": {}
    }
    horses = payload.setdefault("horses", {})
    missing = [brand for brand in brands if horses.get(brand, {}).get("status") != "ok"]
    print(f"cached={len(brands)-len(missing)} missing={len(missing)}", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch, brand): brand for brand in missing}
        for count, future in enumerate(as_completed(futures), 1):
            brand, result = future.result()
            horses[brand] = result
            if count % 25 == 0 or count == len(missing):
                payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                CACHE.write_text(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                print(f"fetched={count}/{len(missing)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
