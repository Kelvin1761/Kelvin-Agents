"""
Generate Static Dashboard — Produces a self-contained HTML file
that works without any server. Just double-click to open.
"""
import argparse
import sys, os, json, io
import warnings
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
from models.race import Region


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
    for suggestion in suggestions:
        horse = all_horses.get(suggestion["horse_number"])
        if horse:
            suggestion["jockey"] = horse.jockey
            suggestion["trainer"] = horse.trainer
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


def collect_all_data():
    """Collect all meeting/race data using existing backend parsers."""
    meetings = discover_meetings()
    result = {"meetings": [], "races": {}, "consensus": {}, "roi": {}}

    for m in meetings:
        m_key = f"{m.date}|{m.venue}"
        result["meetings"].append({
            "date": m.date, "venue": m.venue,
            "region": m.region.value,
            "analysts": [a.value for a in m.analysts],
        })

        # Load all races
        all_races = load_meeting_races(m)
        races_data = {"meeting": {"date": m.date, "venue": m.venue, "region": m.region.value, "analysts": [a.value for a in m.analysts]}, "races_by_analyst": {}}
        
        for analyst_name, races in all_races.items():
            races_data["races_by_analyst"][analyst_name] = []
            for race in races:
                races_data["races_by_analyst"][analyst_name].append(_serialize_race(race))

        result["races"][m_key] = races_data

        # Consensus for HKJC (dual analyst)
        if m.region == Region.HKJC and len(all_races) >= 2:
            kelvin_races = all_races.get("Kelvin", [])
            heison_races = all_races.get("Heison", [])
            
            for kr in kelvin_races:
                hr = next((r for r in heison_races if r.race_number == kr.race_number), None)
                if hr:
                    c_key = f"{m_key}|{kr.race_number}"
                    try:
                        result["consensus"][c_key] = _build_hkjc_consensus_payload(m, kr, hr)
                    except Exception:
                        pass
        elif m.region == Region.AU:
            kelvin_races = all_races.get("Kelvin", [])
            for race in kelvin_races:
                c_key = f"{m_key}|{race.race_number}"
                result["consensus"][c_key] = _build_au_consensus_payload(m, race)

    # Collect ROI data from .numbers summary files
    try:
        result["roi"] = get_summary_roi(region=None)
    except Exception as e:
        print(f"   ⚠️ ROI data not available: {e}")
        result["roi"] = {}

    result["meta"] = _build_snapshot_meta(result)
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
    return parser.parse_args()


def main():
    args = parse_args()
    print("🏇 Generating static dashboard...")
    print("   Scanning for meetings...")
    data = collect_all_data()
    
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
