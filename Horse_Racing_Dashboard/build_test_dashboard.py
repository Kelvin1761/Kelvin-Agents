"""Build the local test dashboard from the current Cloudflare live snapshot.

The test build intentionally contains only the active meetings published on
Cloudflare.  Matching Antigravity racecard folders are used only to overlay
runner colours and bilingual HKJC names.  ROI data remains the independent
ledger payload shipped by the live snapshot/API.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = DASHBOARD_DIR.parent
BACKEND_DIR = DASHBOARD_DIR / "backend"
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generate_static import _build_snapshot_meta, _write_json, generate_html
from models.race import AnalystName, Meeting, Region
from services.race_display_metadata import enrich_snapshot_display_metadata
from wongchoi_paths import AU_RACING, HK_RACING


LIVE_SNAPSHOT_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"
DEFAULT_CACHE = DASHBOARD_DIR / ".cache" / "live-dashboard-data.json"


def _download_live_snapshot(cache_path):
    request = urllib.request.Request(
        LIVE_SNAPSHOT_URL,
        headers={"User-Agent": "WongChoi-TestDashboard/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        json.loads(payload)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(payload)
        print(f"   Live snapshot refreshed: {len(payload) / 1024 / 1024:.1f} MB")
    except Exception as exc:
        if not cache_path.exists():
            raise RuntimeError(f"Live snapshot unavailable and no cache exists: {exc}") from exc
        print(f"   Live snapshot refresh unavailable; using cache: {exc}")
    return cache_path


def _normalise_venue(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _find_metadata_folder(meeting):
    root = HK_RACING if meeting["region"] == "hkjc" else AU_RACING
    wanted_date = meeting["date"]
    wanted_venue = _normalise_venue(meeting["venue"])
    candidates = []
    for folder in root.iterdir():
        if not folder.is_dir() or not folder.name.startswith(wanted_date):
            continue
        if wanted_venue in _normalise_venue(folder.name):
            candidates.append(folder)
    return sorted(candidates, key=lambda path: path.stat().st_mtime_ns, reverse=True)[0] if candidates else None


def _is_archived_au_meeting(meeting):
    """Return whether an AU meeting has been deliberately archived locally."""
    if meeting.get("region") != "au":
        return False
    archive_root = AU_RACING / "Archive"
    if not archive_root.is_dir():
        return False
    wanted_date = meeting["date"]
    wanted_venue = _normalise_venue(meeting["venue"])
    return any(
        folder.is_dir()
        and folder.name.startswith(wanted_date)
        and wanted_venue in _normalise_venue(folder.name)
        for folder in archive_root.iterdir()
    )


def _remove_archived_au_meetings(data):
    archived = [item for item in data.get("meetings", []) if _is_archived_au_meeting(item)]
    if not archived:
        return []
    archived_keys = {f"{item['date']}|{item['venue']}" for item in archived}
    data["meetings"] = [
        item for item in data["meetings"]
        if f"{item['date']}|{item['venue']}" not in archived_keys
    ]
    data["races"] = {
        key: value for key, value in data.get("races", {}).items()
        if key not in archived_keys
    }
    data["consensus"] = {
        key: value for key, value in data.get("consensus", {}).items()
        if not any(key.startswith(f"{meeting_key}|") for meeting_key in archived_keys)
    }
    return archived


def build(
    base_snapshot,
    output_html,
    output_json="",
    output_manifest="",
    overlay_metadata=True,
):
    data = json.loads(Path(base_snapshot).read_text(encoding="utf-8"))
    archived = _remove_archived_au_meetings(data)
    coverage = []
    if overlay_metadata:
        for item in data.get("meetings", []):
            folder = _find_metadata_folder(item)
            if not folder:
                coverage.append((item, None, None))
                continue
            region = Region.HKJC if item["region"] == "hkjc" else Region.AU
            meeting = Meeting(
                date=item["date"],
                venue=item["venue"],
                region=region,
                analysts=[AnalystName.KELVIN],
                folder_paths={"Kelvin": str(folder)},
            )
            counts = enrich_snapshot_display_metadata(data, meeting)
            coverage.append((item, folder, counts))

    data["meta"] = _build_snapshot_meta(data)

    output_path = Path(output_html)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_html(data), encoding="utf-8")
    if output_json:
        _write_json(Path(output_json), data)
    if output_manifest:
        _write_json(Path(output_manifest), data["meta"])
    print(f"✅ Active-meeting dashboard generated: {output_path.name}")
    print(f"   Active meetings only: {len(data.get('meetings', []))}")
    for item in archived:
        print(f"   {item['date']} {item['venue']}: excluded (archived)")
    for item, folder, counts in coverage:
        label = f"{item['date']} {item['venue']}"
        if counts:
            print(
                f"   {label}: {counts['silks']}/{counts['horses']} silk rows"
                f" · source {folder.name}"
            )
        else:
            print(f"   {label}: no matching local metadata folder")


def main():
    parser = argparse.ArgumentParser(description="Build active-meeting test dashboard.")
    parser.add_argument("--base-snapshot", default="")
    parser.add_argument(
        "--output-html",
        default=str(DASHBOARD_DIR / "Open Dashboard.html"),
    )
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-manifest", default="")
    parser.add_argument(
        "--skip-metadata-overlay",
        action="store_true",
        help="Use display metadata already present in the base snapshot.",
    )
    args = parser.parse_args()
    base = Path(args.base_snapshot) if args.base_snapshot else _download_live_snapshot(DEFAULT_CACHE)
    build(
        base,
        args.output_html,
        args.output_json,
        args.output_manifest,
        overlay_metadata=not args.skip_metadata_overlay,
    )


if __name__ == "__main__":
    main()
