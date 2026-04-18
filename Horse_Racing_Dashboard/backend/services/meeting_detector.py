"""
Meeting Detector — Scans Antigravity root for race meeting folders.
Pairs HKJC Kelvin + Heison folders and detects AU racing folders.
"""
import re
from pathlib import Path
from typing import Optional
from models.race import Meeting, Region, AnalystName, RaceAnalysis
from services.parser_hkjc import parse_hkjc_analysis
from services.parser_au import parse_au_analysis, parse_mc_results_json
import config


# HKJC folder patterns:
#   Kelvin: "2026-03-22_ShaTin (Kelvin)" or "2026-04-04 Sha Tin (Kelvin)"
#   Heison: "2026-03-22_ShaTin (Heison)" or "2026-04-04 Sha Tin (Heison)"
HKJC_DATE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_(\w+)(?:\s*\((Kelvin|Heison)\))?$')

# Space-separated HKJC folders with analyst tag:
#   "2026-04-04 Sha Tin (Heison)" or "2026-04-06 Happy Valley (Kelvin)"
HKJC_SPACE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+(.+?)\s*\((Kelvin|Heison)\)$')

# AU folder pattern: "2026-03-21 Rosehill Gardens Race 1-10" or "2026-03-28 Flemington"
AU_FOLDER_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+(.+?)(?:\s+Race\s+(\d+)-(\d+))?$')

# Keywords that indicate non-racing folders (should be skipped)
NON_RACING_KEYWORDS = ['NBA', 'NFL', 'Soccer', 'Cricket', 'Tennis', 'Game Archieve']


def discover_meetings(root_dir: Optional[str] = None) -> list[Meeting]:
    """Scan the Antigravity root directory for race meetings.
    Returns a list of Meeting objects with folder paths."""
    
    root = Path(root_dir) if root_dir else config.ANTIGRAVITY_ROOT
    if not root.exists():
        return []
    
    meetings = []
    hkjc_groups = {}  # (date, venue) -> dict with kelvin_path, heison_path
    
    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.startswith('.'):
            continue
        
        # Skip non-racing folders
        if any(kw.lower() in item.name.lower() for kw in NON_RACING_KEYWORDS):
            continue
        
        # Check HKJC space-separated pattern FIRST
        # e.g. "2026-04-04 Sha Tin (Heison)" — analyst tag means it's always HKJC
        hkjc_space_match = HKJC_SPACE_RE.match(item.name)
        if hkjc_space_match:
            folder_date = hkjc_space_match.group(1)
            venue = hkjc_space_match.group(2).strip().replace(' ', '')
            analyst_tag = hkjc_space_match.group(3)
            
            # Try to extract actual meeting date from filenames inside
            # Files are named like "04-06_Race_1_Analysis.md" or "04-06 Race 1 Analysis.md"
            actual_date = _extract_meeting_date_from_files(item, folder_date)
            
            key = (actual_date, venue)
            if key not in hkjc_groups:
                hkjc_groups[key] = {"kelvin_path": None, "heison_path": None}
            
            if analyst_tag == "Kelvin":
                hkjc_groups[key]["kelvin_path"] = str(item)
            elif analyst_tag == "Heison":
                hkjc_groups[key]["heison_path"] = str(item)
            continue
        
        # Check AU folder pattern
        au_match = AU_FOLDER_RE.match(item.name)
        if au_match:
            date = au_match.group(1)
            venue = au_match.group(2).strip()
            # Verify it's actually an AU venue (not HKJC) by checking
            # that the folder name uses space-separated date format (not underscore)
            # and doesn't match HKJC underscore pattern
            if '_' not in item.name.split(' ')[0]:  # AU uses "2026-03-28 Venue"
                # Verify the folder actually contains analysis files
                search_dir = item / "Race Analysis" if (item / "Race Analysis").exists() else item
                has_analysis = (
                    list(search_dir.glob("*Analysis*.md")) or
                    list(search_dir.glob("*Analysis*.txt")) or
                    list(item.glob("*Analysis*.md")) or
                    list(item.glob("*Analysis*.txt"))
                )
                if has_analysis:
                    meetings.append(Meeting(
                        date=date,
                        venue=venue,
                        region=Region.AU,
                        analysts=[AnalystName.KELVIN],  # AU has single analyst
                        folder_paths={"Kelvin": str(item)},
                    ))
            continue
        
        # Check HKJC folder pattern
        hkjc_match = HKJC_DATE_RE.match(item.name)
        if hkjc_match:
            date = hkjc_match.group(1)
            venue = hkjc_match.group(2).replace('_', '')
            analyst_tag = hkjc_match.group(3)  # 'Kelvin', 'Heison', or None
            key = (date, venue)
            
            if key not in hkjc_groups:
                hkjc_groups[key] = {"kelvin_path": None, "heison_path": None}
            
            if analyst_tag == "Kelvin" or "(Kelvin)" in item.name:
                hkjc_groups[key]["kelvin_path"] = str(item)
            elif analyst_tag == "Heison" or "(Heison)" in item.name:
                # Folder explicitly tagged as Heison
                hkjc_groups[key]["heison_path"] = str(item)
            else:
                # Check if it has Heison-prefixed files
                heison_files = list(item.glob("Heison_*"))
                if heison_files:
                    hkjc_groups[key]["heison_path"] = str(item)
                elif not hkjc_groups[key]["kelvin_path"]:
                    # It's a Kelvin folder without the (Kelvin) suffix
                    hkjc_groups[key]["kelvin_path"] = str(item)
    
    # Build HKJC meetings
    for (date, venue), paths in sorted(hkjc_groups.items()):
        analysts = []
        folder_paths = {}
        
        if paths["kelvin_path"]:
            analysts.append(AnalystName.KELVIN)
            folder_paths["Kelvin"] = paths["kelvin_path"]
        
        if paths["heison_path"]:
            analysts.append(AnalystName.HEISON)
            folder_paths["Heison"] = paths["heison_path"]
        
        if analysts:
            meetings.append(Meeting(
                date=date,
                venue=venue,
                region=Region.HKJC,
                analysts=analysts,
                folder_paths=folder_paths,
            ))
    
    return sorted(meetings, key=lambda m: m.date, reverse=True)


def _extract_meeting_date_from_files(folder: Path, fallback_date: str) -> str:
    """Extract actual meeting date from analysis filenames inside a folder.
    Files are named like '04-06_Race_1_Analysis.md' or '04-06 Race 1 Analysis.md'.
    Returns YYYY-MM-DD date string, using fallback_date's year prefix."""
    year_prefix = fallback_date[:5]  # e.g. '2026-'
    date_re = re.compile(r'^(\d{2})-(\d{2})[_ ]')
    
    for f in folder.iterdir():
        m = date_re.match(f.name)
        if m:
            month, day = m.group(1), m.group(2)
            return f"{year_prefix}{month}-{day}"
    
    return fallback_date


def load_meeting_races(meeting: Meeting) -> dict[str, list[RaceAnalysis]]:
    """Load all race analyses for a meeting, organized by analyst.
    Returns {analyst_name: [RaceAnalysis, ...]}."""
    
    results = {}
    
    for analyst_name, folder_path in meeting.folder_paths.items():
        folder = Path(folder_path)
        races = []
        
        if meeting.region == Region.HKJC:
            # HKJC: look for *_Analysis.md and *_Analysis.txt files (.md preferred)
            # Check if this is a dedicated Heison folder (has "(Heison)" in path)
            is_dedicated_heison_folder = "(Heison)" in folder.name
            if analyst_name == "Heison" and not is_dedicated_heison_folder:
                # Heison files mixed in with Kelvin — look for Heison_ prefix
                patterns = ["Heison_*Analysis.md", "Heison_*Analysis.txt"]
            else:
                # Kelvin folder, or dedicated Heison folder (files don't have Heison_ prefix)
                patterns = ["*Analysis.md", "*Analysis.txt"]
            
            seen_paths = set()
            analysis_files = []
            for pat in patterns:
                for f in folder.glob(pat):
                    if f not in seen_paths:
                        seen_paths.add(f)
                        analysis_files.append(f)
            
            # Filter out Heison files from Kelvin results
            if analyst_name != "Heison":
                analysis_files = [f for f in analysis_files if not f.name.startswith("Heison_")]
            
            for fpath in sorted(analysis_files):
                race = parse_hkjc_analysis(str(fpath))
                if race:
                    races.append(race)
        
        elif meeting.region == Region.AU:
            # AU: look in "Race Analysis/" subfolder for "* Analysis.md" and "* Analysis.txt"
            # Also check root folder (files may be in either location)
            race_analysis_dir = folder / "Race Analysis"
            search_dirs = []
            if race_analysis_dir.exists():
                search_dirs.append(race_analysis_dir)
            search_dirs.append(folder)  # Always also check root folder
            
            seen_files = set()
            for search_dir in search_dirs:
                for ext in ["*Analysis*.md", "*Analysis*.txt"]:
                    for fpath in sorted(search_dir.glob(ext)):
                        if fpath.name not in seen_files:
                            seen_files.add(fpath.name)
                            race = parse_au_analysis(str(fpath))
                            if race:
                                races.append(race)
            
            # Deduplicate: when multiple files parse to the same race number,
            # keep the one with the most horses (the complete file)
            seen = {}
            for race in races:
                rn = race.race_number
                if rn not in seen or len(race.horses) > len(seen[rn].horses):
                    seen[rn] = race
            races = list(seen.values())
            
            # Load standalone MC Results JSON files (Race_N_MC_Results.json)
            # These are produced by mc_simulator.py and contain Monte Carlo simulation data
            mc_pattern = re.compile(r'^Race_(\d+)_MC_Results\.json$')
            for mc_file in sorted(folder.glob("Race_*_MC_Results.json")):
                mc_match = mc_pattern.match(mc_file.name)
                if mc_match:
                    mc_race_num = int(mc_match.group(1))
                    mc_picks = parse_mc_results_json(str(mc_file))
                    if mc_picks:
                        # Find matching race and inject MC data
                        target_race = next((r for r in races if r.race_number == mc_race_num), None)
                        if target_race and not target_race.monte_carlo_simulation:
                            target_race.monte_carlo_simulation = mc_picks
                            # Enrich MC picks with horse numbers from parsed race data
                            horse_name_map = {h.horse_name.lower(): str(h.horse_number) for h in target_race.horses}
                            for pick in mc_picks:
                                if not pick.horse_number and pick.horse_name:
                                    pick.horse_number = horse_name_map.get(pick.horse_name.lower())
        
        # Sort by race number
        races.sort(key=lambda r: r.race_number)
        results[analyst_name] = races
    
    return results


def get_meeting_summary(meetings: list[Meeting]) -> list[dict]:
    """Return a lightweight summary of all meetings for the dashboard."""
    return [
        {
            "date": m.date,
            "venue": m.venue,
            "region": m.region.value,
            "analysts": [a.value for a in m.analysts],
            "folder_paths": m.folder_paths,
        }
        for m in meetings
    ]
