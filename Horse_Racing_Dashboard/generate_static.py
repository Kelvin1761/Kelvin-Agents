"""
Generate Static Dashboard — Produces a self-contained HTML file
that works without any server. Just double-click to open.
"""
import argparse
import sys, os, json, io, re
import warnings
from pathlib import Path
from datetime import datetime

# Fix the legacy Windows console encoding without replacing pytest/caller-owned
# streams when this module is imported for tests or library use.
if os.name == "nt" and __name__ == "__main__" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Silence known third-party compatibility warning during static generation.
warnings.filterwarnings(
    "ignore",
    message=r"Numbers version .* not tested with this version",
    category=UserWarning,
)

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.meeting_detector import discover_meetings, load_meeting_races
from services.consensus import find_consensus_horses, find_rating_disagreements, get_betting_suggestions
from services.summary_importer import get_summary_roi
from services.race_display_metadata import (
    enrich_au_display_metadata as _enrich_au_silks,
    enrich_hkjc_display_metadata as _enrich_hkjc_silks,
    enrich_race_display_metadata,
    parse_au_racecard_silks as _parse_au_racecard_silks,
    parse_hkjc_pdf_english_names as _parse_hkjc_pdf_english_names,
    parse_hkjc_racecard_silks as _parse_hkjc_racecard_silks,
)
from models.race import AnalystName, Meeting, Region


CACHE_VERSION = 3
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "meeting-snapshot-cache.json"
AU_MEETING_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+?)(?:\s+Race\s+\d+-\d+)?$")


def _serialize_race(race):
    payload = race.model_dump()
    payload["horses"] = [h.model_dump() for h in race.horses]
    payload["top_picks"] = [p.model_dump() for p in race.top_picks]
    if race.scenario_top_picks:
        payload["scenario_top_picks"] = {
            label: [p.model_dump() for p in picks]
            for label, picks in race.scenario_top_picks.items()
        }
    payload["horses_count"] = len(race.horses)
    return payload


def _build_hkjc_consensus_payload(meeting, kelvin_race, heison_race):
    consensus = find_consensus_horses(kelvin_race, heison_race)
    disagreements = find_rating_disagreements(kelvin_race, heison_race)
    suggestions = get_betting_suggestions(consensus)
    all_horses = {h.horse_number: h for h in kelvin_race.horses}
    all_horses.update({h.horse_number: h for h in heison_race.horses})
    for horse_data in consensus.get("consensus_horses", []):
        horse = all_horses.get(horse_data["horse_number"])
        if horse:
            horse_data["jockey"] = horse.jockey
            horse_data["trainer"] = horse.trainer
            horse_data["horse_name_en"] = horse.horse_name_en
            horse_data["horse_code"] = horse.horse_code
            horse_data["hkjc_horse_id"] = horse.hkjc_horse_id
            horse_data["horse_profile_url"] = horse.horse_profile_url
            horse_data["silk_url"] = horse.silk_url
    for suggestion in suggestions:
        horse = all_horses.get(suggestion["horse_number"])
        if horse:
            suggestion["jockey"] = horse.jockey
            suggestion["trainer"] = horse.trainer
            suggestion["horse_name_en"] = horse.horse_name_en
            suggestion["horse_code"] = horse.horse_code
            suggestion["hkjc_horse_id"] = horse.hkjc_horse_id
            suggestion["horse_profile_url"] = horse.horse_profile_url
            suggestion["silk_url"] = horse.silk_url
    return {
        "race_number": kelvin_race.race_number,
        "region": meeting.region.value,
        "consensus": consensus,
        "disagreements": disagreements,
        "betting_suggestions": suggestions,
    }


def _build_au_consensus_payload(meeting, race):
    horse_lookup = {horse.horse_number: horse for horse in race.horses}
    candidates = []
    seen = set()

    if race.scenario_top_picks:
        for label, picks in race.scenario_top_picks.items():
            for pick in (picks or []):
                if pick.rank > 2:
                    continue
                key = (pick.horse_number, label)
                if key in seen:
                    continue
                seen.add(key)
                horse = horse_lookup.get(pick.horse_number)
                candidates.append({
                    "horse_number": pick.horse_number,
                    "horse_name": pick.horse_name,
                    "kelvin_rank": pick.rank,
                    "heison_rank": None,
                    "kelvin_grade": pick.grade,
                    "heison_grade": None,
                    "is_top2_consensus": True,
                    "jockey": horse.jockey if horse else None,
                    "trainer": horse.trainer if horse else None,
                    "silk_url": horse.silk_url if horse else None,
                    "scenario": label,
                    "consensus_type": f"{label} Top {pick.rank}",
                })

    if not candidates:
        for pick in race.top_picks[:2]:
            horse = horse_lookup.get(pick.horse_number)
            candidates.append({
                "horse_number": pick.horse_number,
                "horse_name": pick.horse_name,
                "kelvin_rank": pick.rank,
                "heison_rank": None,
                "kelvin_grade": pick.grade,
                "heison_grade": None,
                "is_top2_consensus": True,
                "jockey": horse.jockey if horse else None,
                "trainer": horse.trainer if horse else None,
                "silk_url": horse.silk_url if horse else None,
                "scenario": None,
                "consensus_type": "Top 2 精選",
            })

    return {
        "race_number": race.race_number,
        "region": meeting.region.value,
        "consensus": {
            "consensus_horses": candidates,
            "kelvin_only": [],
            "heison_only": [],
            "consensus_count": len(candidates),
            "top4_overlap_count": len(candidates),
        },
        "disagreements": [],
        "betting_suggestions": [
            {
                "horse_number": candidate["horse_number"],
                "horse_name": candidate["horse_name"],
                "consensus_type": candidate.get("consensus_type") or "Top 2 精選",
                "scenario": candidate.get("scenario"),
                "min_odds_required": 2.0,
                "kelvin_grade": candidate.get("kelvin_grade"),
                "heison_grade": None,
                "jockey": candidate.get("jockey"),
                "trainer": candidate.get("trainer"),
                "silk_url": candidate.get("silk_url"),
            }
            for candidate in candidates
        ],
    }


def _build_snapshot_meta(data):
    region_summary = {
        Region.HKJC.value: {"meetings": 0, "unique_races": 0, "analyst_race_entries": 0},
        Region.AU.value: {"meetings": 0, "unique_races": 0, "analyst_race_entries": 0},
    }
    total_unique_races = 0
    total_analyst_race_entries = 0

    for meeting in data["meetings"]:
        bucket = region_summary.setdefault(meeting["region"], {"meetings": 0, "unique_races": 0, "analyst_race_entries": 0})
        bucket["meetings"] += 1

    for meeting_key, races_data in data["races"].items():
        region = races_data.get("meeting", {}).get("region")
        bucket = region_summary.setdefault(region, {"meetings": 0, "unique_races": 0, "analyst_race_entries": 0})
        unique_race_numbers = {
            race["race_number"]
            for races in races_data.get("races_by_analyst", {}).values()
            for race in races
        }
        analyst_race_entries = sum(
            len(races)
            for races in races_data.get("races_by_analyst", {}).values()
        )
        bucket["unique_races"] += len(unique_race_numbers)
        bucket["analyst_race_entries"] += analyst_race_entries
        total_unique_races += len(unique_race_numbers)
        total_analyst_race_entries += analyst_race_entries

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "meeting_count": len(data["meetings"]),
        "unique_race_count": total_unique_races,
        "analyst_race_entry_count": total_analyst_race_entries,
        "consensus_entry_count": len(data["consensus"]),
        "regions": region_summary,
    }


def _cache_key(meeting):
    paths = "|".join(
        f"{analyst}:{path}"
        for analyst, path in sorted(meeting.folder_paths.items())
    )
    return f"{meeting.region.value}|{meeting.date}|{meeting.venue}|{paths}"


def _analysis_files(meeting):
    """Return the output files whose changes require a meeting re-parse."""
    files = []
    for folder_path in meeting.folder_paths.values():
        folder = Path(folder_path)
        if meeting.region == Region.HKJC:
            patterns = ("*_Auto_Analysis.md", "*_Analysis.md", "*_Analysis.txt")
            search_dirs = (folder,)
        else:
            race_analysis_dir = folder / "Race Analysis"
            search_dirs = (race_analysis_dir, folder) if race_analysis_dir.exists() else (folder,)
            patterns = ("*Analysis*.md", "*Analysis*.txt")
        for search_dir in search_dirs:
            for pattern in patterns:
                files.extend(search_dir.glob(pattern))
        if meeting.region == Region.HKJC:
            files.extend(folder.glob("*Race * 排位表.md"))
            files.extend(folder.glob("*全日出賽馬匹資料*.md"))
        else:
            files.extend(folder.glob("*Racecard.md"))
        files.extend(folder.glob("Race_*_MC_Results.json"))
    return sorted(set(files), key=lambda path: str(path))


def _source_fingerprint(meeting):
    """A cheap metadata signature: unchanged files never need markdown parsing."""
    fingerprint = []
    for path in _analysis_files(meeting):
        stat = path.stat()
        fingerprint.append((str(path), stat.st_mtime_ns, stat.st_size))
    return fingerprint


def _load_cache(cache_path):
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("version") == CACHE_VERSION and isinstance(cache.get("entries"), dict):
            return cache
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"version": CACHE_VERSION, "entries": {}}


def _write_cache(cache_path, entries):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps({"version": CACHE_VERSION, "entries": entries}, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temp_path.replace(cache_path)


def _collect_meeting(meeting):
    meeting_data = {
        "date": meeting.date,
        "venue": meeting.venue,
        "region": meeting.region.value,
        "analysts": [analyst.value for analyst in meeting.analysts],
    }
    meeting_key = f"{meeting.date}|{meeting.venue}"
    all_races = load_meeting_races(meeting)
    enrich_race_display_metadata(meeting, all_races)
    races_data = {
        "meeting": meeting_data,
        "races_by_analyst": {
            analyst: [_serialize_race(race) for race in races]
            for analyst, races in all_races.items()
        },
    }
    consensus = {}
    if meeting.region == Region.HKJC and len(all_races) >= 2:
        kelvin_races = all_races.get("Kelvin", [])
        heison_races = all_races.get("Heison", [])
        for kelvin_race in kelvin_races:
            heison_race = next((race for race in heison_races if race.race_number == kelvin_race.race_number), None)
            if heison_race:
                try:
                    consensus[f"{meeting_key}|{kelvin_race.race_number}"] = _build_hkjc_consensus_payload(
                        meeting, kelvin_race, heison_race
                    )
                except Exception:
                    pass
    elif meeting.region == Region.AU:
        for race in all_races.get("Kelvin", []):
            consensus[f"{meeting_key}|{race.race_number}"] = _build_au_consensus_payload(meeting, race)
    return meeting_data, meeting_key, races_data, consensus


def _au_meeting_from_directory(meeting_dir):
    """Resolve a standard AU output folder into one dashboard meeting."""
    meeting_dir = Path(meeting_dir).resolve()
    match = AU_MEETING_DIR_RE.match(meeting_dir.name)
    if not match:
        raise ValueError(f"Unsupported AU meeting folder name: {meeting_dir.name}")
    return Meeting(
        date=match.group(1),
        venue=match.group(2).strip(),
        region=Region.AU,
        analysts=[AnalystName.KELVIN],
        folder_paths={"Kelvin": str(meeting_dir)},
    )


def collect_incremental_au_data(base_snapshot_path, meeting_dir):
    """Merge one fresh AU meeting into an existing published snapshot."""
    base_snapshot_path = Path(base_snapshot_path)
    data = json.loads(base_snapshot_path.read_text(encoding="utf-8"))
    meeting = _au_meeting_from_directory(meeting_dir)
    meeting_data, meeting_key, races_data, consensus = _collect_meeting(meeting)

    data["meetings"] = [
        item
        for item in data.get("meetings", [])
        if not (item.get("date") == meeting.date and item.get("venue") == meeting.venue)
    ]
    data["races"] = {
        key: value
        for key, value in data.get("races", {}).items()
        if key != meeting_key
    }
    data["consensus"] = {
        key: value
        for key, value in data.get("consensus", {}).items()
        if not key.startswith(f"{meeting_key}|")
    }
    data["meetings"].append(meeting_data)
    data["meetings"].sort(key=lambda item: item["date"], reverse=True)
    data["races"][meeting_key] = races_data
    data["consensus"].update(consensus)
    data.setdefault("roi", {})
    data["meta"] = _build_snapshot_meta(data)
    print(f"   Incremental snapshot: refreshed {meeting.date} {meeting.venue}")
    return data


def collect_all_data(cache_path=DEFAULT_CACHE_PATH):
    """Collect all meetings, reusing parsed entries when their source files are unchanged."""
    meetings = discover_meetings()
    result = {"meetings": [], "races": {}, "consensus": {}, "roi": {}}
    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)
    updated_entries = {}
    cache_hits = 0

    for m in meetings:
        key = _cache_key(m)
        fingerprint = _source_fingerprint(m)
        entry = cache["entries"].get(key)
        if entry and entry.get("fingerprint") == fingerprint:
            cache_hits += 1
        else:
            meeting_data, meeting_key, races_data, consensus = _collect_meeting(m)
            entry = {
                "fingerprint": fingerprint,
                "meeting": meeting_data,
                "meeting_key": meeting_key,
                "races_data": races_data,
                "consensus": consensus,
            }
        updated_entries[key] = entry
        result["meetings"].append(entry["meeting"])
        result["races"][entry["meeting_key"]] = entry["races_data"]
        result["consensus"].update(entry["consensus"])

    # Collect ROI data from .numbers summary files
    try:
        result["roi"] = get_summary_roi(region=None)
    except Exception as e:
        print(f"   ⚠️ ROI data not available: {e}")
        result["roi"] = {}

    result["meta"] = _build_snapshot_meta(result)
    _write_cache(cache_path, updated_entries)
    print(f"   Meeting cache: {cache_hits} reused, {len(meetings) - cache_hits} refreshed")
    return result


def generate_html(data):
    """Generate self-contained HTML dashboard."""
    css_path = Path(__file__).resolve().parent / "frontend" / "src" / "index.css"
    css_content = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    
    data_json = json.dumps(data, ensure_ascii=False, default=str)
    generated_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    html_template_path = Path(__file__).resolve().parent / "static_template.html"
    template = html_template_path.read_text(encoding="utf-8")
    
    # Replace placeholders
    html = template.replace("/* __CSS_PLACEHOLDER__ */", css_content)
    html = html.replace('"__DATA_PLACEHOLDER__"', data_json)
    html = html.replace("__GENERATED_TIME__", generated_time)
    
    return html


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def parse_args():
    dashboard_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Generate static / Cloudflare-ready dashboard snapshot.")
    parser.add_argument(
        "--output-html",
        default=str(dashboard_dir / "Open Dashboard.html"),
        help="Target HTML output path.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional JSON snapshot output path.",
    )
    parser.add_argument(
        "--output-manifest",
        default="",
        help="Optional deployment manifest output path.",
    )
    parser.add_argument(
        "--cache-path",
        default=str(DEFAULT_CACHE_PATH),
        help="Persistent parsed-meeting cache; unchanged meetings are not re-parsed.",
    )
    parser.add_argument(
        "--base-snapshot",
        default="",
        help="Existing dashboard-data.json to preserve while incrementally updating one AU meeting.",
    )
    parser.add_argument(
        "--au-meeting-dir",
        default="",
        help="AU meeting folder to merge into --base-snapshot.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print("🏇 Generating static dashboard...")
    print("   Scanning for meetings...")
    if bool(args.base_snapshot) != bool(args.au_meeting_dir):
        parser.error("--base-snapshot and --au-meeting-dir must be used together")
    data = (
        collect_incremental_au_data(args.base_snapshot, args.au_meeting_dir)
        if args.base_snapshot
        else collect_all_data(args.cache_path)
    )
    
    meeting_count = len(data["meetings"])
    race_count = sum(
        len(races) 
        for rd in data["races"].values() 
        for races in rd["races_by_analyst"].values()
    )
    print(f"   Found {meeting_count} meetings, {race_count} race analyses")
    
    print("   Building HTML...")
    html = generate_html(data)
    
    output_path = Path(args.output_html)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    if args.output_json:
        json_path = Path(args.output_json)
        _write_json(json_path, data)
        print(f"   Snapshot JSON written: {json_path.name}")

    if args.output_manifest:
        manifest_path = Path(args.output_manifest)
        _write_json(manifest_path, data.get("meta") or _build_snapshot_meta(data))
        print(f"   Deploy manifest written: {manifest_path.name}")
    
    size_kb = output_path.stat().st_size / 1024
    print(f"✅ Dashboard generated: {output_path.name} ({size_kb:.0f} KB)")
    if data.get("meta"):
        hkjc_meetings = data["meta"]["regions"].get("hkjc", {}).get("meetings", 0)
        au_meetings = data["meta"]["regions"].get("au", {}).get("meetings", 0)
        print(f"   Region coverage: HKJC {hkjc_meetings} meetings · AU {au_meetings} meetings")
    print(f"   Just double-click to open — no server needed!")


if __name__ == "__main__":
    main()
