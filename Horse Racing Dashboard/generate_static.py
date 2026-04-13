"""
Generate Static Dashboard — Produces a self-contained HTML file
that works without any server. Just double-click to open.
"""
import sys, os, json, io
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.meeting_detector import discover_meetings, load_meeting_races
from services.consensus import find_consensus_horses, find_rating_disagreements, get_betting_suggestions
from services.summary_importer import get_summary_roi
from models.race import Region


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
                rd = race.model_dump()
                # Convert horses and top_picks
                rd["horses"] = [h.model_dump() for h in race.horses]
                rd["top_picks"] = [p.model_dump() for p in race.top_picks]
                # Dual-track: alt_top_picks (SIP-1 per-horse grades sorted)
                if race.alt_top_picks:
                    rd["alt_top_picks"] = [p.model_dump() for p in race.alt_top_picks]
                rd["is_dual_track"] = race.is_dual_track
                rd["primary_condition"] = race.primary_condition
                rd["alt_condition"] = race.alt_condition
                # Serialize dual-scenario picks (SIP-RR01) if present
                if race.scenario_top_picks:
                    rd["scenario_top_picks"] = {
                        label: [p.model_dump() for p in picks]
                        for label, picks in race.scenario_top_picks.items()
                    }
                rd["horses_count"] = len(race.horses)

                races_data["races_by_analyst"][analyst_name].append(rd)

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
                        consensus = find_consensus_horses(kr, hr)
                        disagreements = find_rating_disagreements(kr, hr)
                        suggestions = get_betting_suggestions(consensus)
                        # Enrich consensus horses with jockey/trainer from analysis
                        all_horses = {h.horse_number: h for h in kr.horses}
                        all_horses.update({h.horse_number: h for h in hr.horses})
                        for ch in consensus.get("consensus_horses", []):
                            horse = all_horses.get(ch["horse_number"])
                            if horse:
                                ch["jockey"] = horse.jockey
                                ch["trainer"] = horse.trainer
                        for sg in suggestions:
                            horse = all_horses.get(sg["horse_number"])
                            if horse:
                                sg["jockey"] = horse.jockey
                                sg["trainer"] = horse.trainer
                        result["consensus"][c_key] = {
                            "race_number": kr.race_number,
                            "consensus": consensus,
                            "disagreements": disagreements,
                            "betting_suggestions": suggestions,
                        }
                    except Exception:
                        pass

    # Collect ROI data from .numbers summary files
    try:
        result["roi"] = get_summary_roi(region=None)
    except Exception as e:
        print(f"   ⚠️ ROI data not available: {e}")
        result["roi"] = {}

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


def main():
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
    
    output_path = Path(__file__).resolve().parent / "Open Dashboard.html"
    
    from backend.utils.safe_writer import safe_write
    safe_write(str(output_path), html, mode="w")
    
    size_kb = output_path.stat().st_size / 1024
    print(f"✅ Dashboard generated: {output_path.name} ({size_kb:.0f} KB)")
    print(f"   Just double-click to open — no server needed!")


if __name__ == "__main__":
    main()
