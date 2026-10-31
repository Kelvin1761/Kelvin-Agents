"""
Generate Static Dashboard — Produces a self-contained HTML file
that works without any server. Just double-click to open.
"""
import argparse
import base64
import gzip
import sys, os, json, io, re
import copy
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

from services.meeting_detector import (
    HKJC_DATE_RE,
    discover_meetings,
    load_meeting_races,
)
from services.consensus import find_consensus_horses, find_rating_disagreements, get_betting_suggestions
from services.summary_importer import compute_side_roi, get_summary_roi
from services.race_display_metadata import (
    enrich_au_display_metadata as _enrich_au_silks,
    enrich_hkjc_display_metadata as _enrich_hkjc_silks,
    enrich_race_display_metadata,
    parse_au_racecard_silks as _parse_au_racecard_silks,
    parse_hkjc_pdf_english_names as _parse_hkjc_pdf_english_names,
    parse_hkjc_racecard_silks as _parse_hkjc_racecard_silks,
)
from services.multisport_exporter import build_multisport_feed, sydney_today
from services.au_display_policy import apply_au_display_policy
from services.nba_tracking import TRACKING_START_DATE
from services.au_market_odds import enrich_au_market_odds
from models.race import AnalystName, Meeting, Region


# Bump whenever the parsed per-horse shape changes. The cache keys on
# (mtime, size) of the source markdown, so a parser that starts emitting new
# fields over UNCHANGED files would otherwise keep serving the old shape
# forever -- the fields would read as empty in production with nothing failing.
# 4: AU structured fields (rank / ability_score / confidence_score /
#    evidence_dimensions / dimension_details) added 2026-09-02.
# 5: HKJC full score ledger + official-vs-shadow ranking fields added 2026-10-08.
# 6: AU registry metadata is part of the parsed race payload. Unchanged
# report bytes must not reuse a cache made before the parser carried the spec.
# 7: AU modern panorama class is parsed from its third component; invalidate
# unchanged-report cache entries carrying the old "Race N" class value.
CACHE_VERSION = 9  # AU captured full-time speed metadata
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "meeting-snapshot-cache.json"
AU_MEETING_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+?)(?:\s+Race\s+\d+-\d+)?$")


def _resolve_tennis_db_path():
    """Resolve the live Tennis DB without tying deploys to one checkout.

    AU/HKJC deploys can run from a versioned release checkout while the live
    Tennis SQLite database stays in its stable runtime directory.  The
    production runtime installer writes the pointer after validating the DB.
    An explicit environment override remains useful for one-off recovery runs.
    """
    explicit = os.environ.get("WC_TENNIS_DB_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    pointer = Path.home() / ".wongchoi_tennis_db"
    try:
        pointed = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(pointed).expanduser() if pointed else None


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
                    "market_win_odds": horse.market_win_odds if horse else None,
                    "market_place_odds": horse.market_place_odds if horse else None,
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
                "market_win_odds": horse.market_win_odds if horse else None,
                "market_place_odds": horse.market_place_odds if horse else None,
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
                "market_win_odds": candidate.get("market_win_odds"),
                "market_place_odds": candidate.get("market_place_odds"),
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
            files.extend(folder.glob("odds_history.json"))
        files.extend(folder.glob("Race_*_MC_Results.json"))
    return sorted(set(files), key=lambda path: str(path))


def _source_fingerprint(meeting):
    """A cheap metadata signature: unchanged files never need markdown parsing."""
    fingerprint = []
    for path in _analysis_files(meeting):
        stat = path.stat()
        fingerprint.append([str(path), stat.st_mtime_ns, stat.st_size])
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


# ── AU 賽道幾何（周長 / 直路 / 方向）──────────────────────────────────────
# 數據喺 `au_wong_choi_auto/resources/au_track_geometry.json`，兩個來源交叉核對，
# 96 個場地入面 85 個有齊（EXP-20260902-01）。
# ⚠️ **唔好喺呢度再抄一份場地名 alias 表** —— 抄咗就一定會有一日兩邊唔同步
# （`Rosehill Gardens` / `Sandown Hillside` / `Ballarat Synthetic` 呢啲就係靠 alias
# 對名）。一律行引擎嗰個 lookup。
_TRACK_GEOMETRY_LOOKUP = None


def _track_geometry_lookup():
    global _TRACK_GEOMETRY_LOOKUP
    if _TRACK_GEOMETRY_LOOKUP is None:
        repo_root = Path(__file__).resolve().parent.parent
        engine_scripts = repo_root / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
        if str(engine_scripts) not in sys.path:
            sys.path.insert(0, str(engine_scripts))
        try:
            from au_racing_engine.engine_core import _load_track_geometry
            _TRACK_GEOMETRY_LOOKUP = _load_track_geometry
        except Exception as exc:  # noqa: BLE001
            # ⚠️ 一定要出聲。靜靜返 None 就會變成「每個場次都冇賽道資料」，
            # 而畫面上同「呢個場地本來就冇數據」一模一樣。
            print(f"   ⚠️ 攞唔到賽道幾何（{type(exc).__name__}: {exc}）—— "
                  f"戰場全景唔會有賽道格")
            _TRACK_GEOMETRY_LOOKUP = False
    return _TRACK_GEOMETRY_LOOKUP or None


def _attach_track_geometry(meeting_data):
    """喺 meeting payload 加 `track_geometry`。冇數據就唔加個 key。

    ⚠️ 要喺**讀完 cache 之後**先叫 —— `_collect_meeting()` 嘅結果會入 cache，
    喺嗰度加就等於「已 cache 嘅場次永遠冇賽道資料」，而且 fingerprint 唔變
    佢哋唔會重新 parse。
    """
    if not isinstance(meeting_data, dict):
        return meeting_data
    if str(meeting_data.get("region") or "").upper() not in {"AU", "AUSTRALIA"}:
        return meeting_data
    lookup = _track_geometry_lookup()
    if not lookup:
        return meeting_data
    try:
        geometry = lookup(meeting_data.get("venue") or "")
    except Exception:  # noqa: BLE001
        return meeting_data
    if geometry and geometry.get("circumference_m"):
        meeting_data["track_geometry"] = {
            "circumference_m": geometry.get("circumference_m"),
            "straight_m": geometry.get("straight_m") or 0,
            "direction": geometry.get("direction") or "",
            "classification": geometry.get("classification") or "",
            "surface": geometry.get("surface") or "",
        }
    else:
        meeting_data.pop("track_geometry", None)
    return meeting_data


# ── 場次分級（AU）同開跑時間（AU + HKJC，dashboard 顯示用）──────────────────
# 星期六十幾個場次一齊出，首頁冇得分邊個係都會場、邊個幾點開跑（2026-10-31：
# 16 張一模一樣嘅卡）。分級來自各州官方定義，見 backend/services/au_venue_tiers.json；
# 開跑時間：AU 由排程喺抓 Sportsbet AllRacing 時寫落 Race_Start_Times.json
# （shared_racing/scripts/sportsbet_race_times.py）；HKJC 直接讀馬會排位表嘅「時間:」。
# 兩樣都喺讀完 cache 之後先貼（同 _attach_track_geometry 一樣）：時間會改，
# 但改時間唔應該觸發重新 parse 分析。
AU_VENUE_TIERS_PATH = Path(__file__).resolve().parent / "backend" / "services" / "au_venue_tiers.json"
RACE_START_TIMES_FILE = "Race_Start_Times.json"
_AU_VENUE_TIERS = None


def _au_venue_key(venue):
    """Engine's venue slug (with its alias table), so no second alias copy."""
    lookup = _track_geometry_lookup()          # also puts the engine on sys.path
    if lookup:
        try:
            from au_racing_engine.engine_core import _track_geometry_key
            return _track_geometry_key(venue)
        except Exception:  # noqa: BLE001
            pass
    return re.sub(r"[^a-z0-9]+", "-", str(venue or "").lower()).strip("-")


def au_venue_profile(venue):
    """{"state": "NSW", "tier": "metro" | "provincial" | "country"} for an AU venue."""
    global _AU_VENUE_TIERS
    if _AU_VENUE_TIERS is None:
        try:
            raw = json.loads(AU_VENUE_TIERS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"   ⚠️ 讀唔到 AU 場地分級（{type(exc).__name__}: {exc}）—— 全部當鄉鎮")
            raw = {}
        tables = {"state": {}, "tier": {}}
        for state, keys in (raw.get("states") or {}).items():
            tables["state"].update(dict.fromkeys(keys, state))
        for tier, field in (("provincial", "provincial"), ("metro", "metropolitan")):
            for state, keys in (raw.get(field) or {}).items():
                for key in keys:
                    tables["tier"][key] = tier
                    tables["state"].setdefault(key, state)
        _AU_VENUE_TIERS = tables
    key = _au_venue_key(venue)
    return {"state": _AU_VENUE_TIERS["state"].get(key, ""),
            "tier": _AU_VENUE_TIERS["tier"].get(key, "country")}


_HKJC_RACECARD_RE = re.compile(r"Race (\d+) 排位表\.md$")


def _read_hkjc_racecard_times(meeting):
    """HKJC jump times straight from the club's racecard (`日期:` / `時間:` in
    each `… Race N 排位表.md`, Hong Kong time). The HKJC pipeline already
    extracts these, so the board needs no extra request and no Sportsbet."""
    from zoneinfo import ZoneInfo
    hong_kong = ZoneInfo("Asia/Hong_Kong")
    starts = {}
    for folder in (getattr(meeting, "folder_paths", None) or {}).values():
        try:
            cards = sorted(Path(folder).glob("*排位表.md"))
        except OSError:
            continue
        for card in cards:
            number = _HKJC_RACECARD_RE.search(card.name)
            if not number or number.group(1) in starts:
                continue
            try:
                head = card.read_text(encoding="utf-8")[:1500]
            except OSError:
                continue
            day = re.search(r"^日期:\s*(\d{4}-\d{2}-\d{2})", head, re.M)
            clock = re.search(r"^時間:\s*(\d{1,2}):(\d{2})", head, re.M)
            if day and clock:
                local = datetime.strptime(f"{day.group(1)} {clock.group(1)}:{clock.group(2)}",
                                          "%Y-%m-%d %H:%M").replace(tzinfo=hong_kong)
                starts[number.group(1)] = int(local.timestamp())
        if starts:
            break
    return starts, set()


def _read_race_start_times(meeting):
    """→ ({"race number": epoch}, {abandoned race numbers}); empty when absent.
    AU: Race_Start_Times.json (Sportsbet, written by the scheduler). HKJC: the
    club's own racecard."""
    if getattr(meeting, "region", None) == Region.HKJC:
        return _read_hkjc_racecard_times(meeting)
    for folder in (getattr(meeting, "folder_paths", None) or {}).values():
        try:
            body = json.loads((Path(folder) / RACE_START_TIMES_FILE).read_text(encoding="utf-8"))
            starts = {str(k): int(v) for k, v in (body.get("races") or {}).items()}
            return starts, {str(n) for n in body.get("abandoned") or []}
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return {}, set()


def _attach_meeting_context(meeting, meeting_data, races_data):
    """`start_time` (epoch) on each race, both regions; state / tier for AU."""
    if str(meeting_data.get("region") or "").lower() in {"au", "australia"}:
        meeting_data.update(au_venue_profile(meeting_data.get("venue")))
    starts, abandoned = _read_race_start_times(meeting)
    for races in (races_data.get("races_by_analyst") or {}).values():
        for race in races:
            number = str(race.get("race_number"))
            race.pop("start_time", None)
            race.pop("abandoned", None)
            if number in starts:
                race["start_time"] = starts[number]
            elif number in abandoned:
                race["abandoned"] = True
    if starts:
        meeting_data["first_start"] = min(starts.values())
    else:
        meeting_data.pop("first_start", None)


def _ensure_au_venue_profiles(data):
    """Tier depends only on the venue, so every build fills meetings that were
    merged before tiers existed; start times need the folder and are not guessed."""
    for meeting_data in data.get("meetings") or []:
        if (str(meeting_data.get("region") or "").lower() in {"au", "australia"}
                and "tier" not in meeting_data):
            meeting_data.update(au_venue_profile(meeting_data.get("venue")))
    return data


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
    enrich_au_market_odds(meeting, all_races)
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


def _hkjc_meeting_from_directory(meeting_dir):
    """Resolve a standard HKJC output folder (`2026-09-06_ShaTin`)."""
    meeting_dir = Path(meeting_dir).resolve()
    match = HKJC_DATE_RE.match(meeting_dir.name)
    if not match:
        raise ValueError(f"Unsupported HKJC meeting folder name: {meeting_dir.name}")
    analyst = (match.group(3) or "Kelvin")
    return Meeting(
        date=match.group(1),
        venue=match.group(2).replace("_", ""),
        region=Region.HKJC,
        analysts=[AnalystName.HEISON if analyst == "Heison" else AnalystName.KELVIN],
        folder_paths={analyst if analyst == "Heison" else "Kelvin": str(meeting_dir)},
    )


def _meeting_from_directory(meeting_dir):
    """One fresh meeting folder -> a dashboard meeting, either region.

    The incremental path existed for AU only, and the HKJC scheduler never set
    `WC_DASHBOARD_BASE_SNAPSHOT`, so `deploy.sh` fell through to "re-publish the
    live projection unchanged" and no HKJC meeting analysed after 2026-07-12
    ever reached the board while every run reported a successful deploy.
    """
    meeting_dir = Path(meeting_dir).resolve()
    if AU_MEETING_DIR_RE.match(meeting_dir.name):
        return _au_meeting_from_directory(meeting_dir)
    if HKJC_DATE_RE.match(meeting_dir.name):
        return _hkjc_meeting_from_directory(meeting_dir)
    raise ValueError(f"Unsupported meeting folder name: {meeting_dir.name}")


def collect_incremental_au_data(base_snapshot_path, meeting_dir):
    """Merge one fresh meeting (AU or HKJC) into a published snapshot."""
    base_snapshot_path = Path(base_snapshot_path)
    data = load_snapshot(base_snapshot_path)
    meeting = _meeting_from_directory(meeting_dir)
    meeting_data, meeting_key, races_data, consensus = _collect_meeting(meeting)
    _attach_meeting_context(meeting, meeting_data, races_data)

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
    if meeting.region == Region.HKJC:
        # HKJC runs one card at a time and the board shows the latest, not an
        # archive. `meeting_detector` already keeps a settled meeting only until
        # a newer analysis is ready to replace it, but the incremental path does
        # not go through the detector -- it can only add or replace -- so
        # without this the previous card stayed on the board for ever. Measured
        # 2026-09-04: 2026-07-12 ShaTin was still live two months on.
        # Only meetings that are NOT newer are dropped, so re-publishing an old
        # meeting cannot wipe a newer card.
        stale = {
            f"{item['date']}|{item['venue']}"
            for item in data.get("meetings", [])
            if item.get("region") == Region.HKJC.value and item["date"] <= meeting.date
        }
        if stale:
            data["meetings"] = [
                item for item in data.get("meetings", [])
                if f"{item['date']}|{item['venue']}" not in stale
            ]
            data["races"] = {k: v for k, v in data.get("races", {}).items()
                             if k not in stale}
            data["consensus"] = {
                k: v for k, v in data.get("consensus", {}).items()
                if k.split("|")[0] + "|" + k.split("|")[1] not in stale
            }
            print(f"   Superseded HKJC meetings dropped: {sorted(stale)}")
    data["meetings"].append(meeting_data)
    data["meetings"].sort(key=lambda item: item["date"], reverse=True)
    data["races"][meeting_key] = races_data
    data["consensus"].update(consensus)
    data.setdefault("roi", {})
    data["meta"] = _build_snapshot_meta(data)
    print(f"   Incremental snapshot: refreshed {meeting.date} {meeting.venue}")
    return data


def drop_au_meetings(base_snapshot_path, keys):
    """Remove meetings from a published snapshot by `date|venue` key.

    The incremental path can only add or replace a meeting, so before this
    existed nothing could ever leave a published snapshot. Archiving a meeting
    moved its folder out of AU_RACING and the scheduler then refused to publish,
    because its own pre-publish check saw the archived meeting still listed --
    correctly. Every evening run from 2026-08-05 failed at that gate.

    Consensus keys are `{meeting_key}|...`, so they go by prefix.
    """
    base_snapshot_path = Path(base_snapshot_path)
    data = load_snapshot(base_snapshot_path)
    wanted = set(keys)
    kept_meetings = [
        item for item in data.get("meetings", [])
        if f"{item.get('date')}|{item.get('venue')}" not in wanted
    ]
    removed = len(data.get("meetings", [])) - len(kept_meetings)
    data["meetings"] = kept_meetings
    data["races"] = {k: v for k, v in data.get("races", {}).items() if k not in wanted}
    data["consensus"] = {
        k: v for k, v in data.get("consensus", {}).items()
        if not any(k == w or k.startswith(f"{w}|") for w in wanted)
    }
    data.setdefault("roi", {})
    data["meta"] = _build_snapshot_meta(data)
    print(f"   Dropped {removed} archived meeting(s); {len(data['meetings'])} remain")
    return data


def _ensure_region_side_roi(data: dict) -> dict:
    """HKJC and AU are separate tabs (2026-10-10); each needs its own side
    breakdowns. Recomputed from the snapshot's own bets so every build mode
    (full rescan, incremental merge, --from-snapshot) carries them — the
    incremental paths never re-read the ROI workbooks."""
    roi = data.get("roi")
    if not isinstance(roi, dict):
        return data
    bets = [b for b in roi.get("bets") or [] if isinstance(b, dict)]
    roi["side_roi_by_region"] = {
        region: compute_side_roi([b for b in bets if b.get("region") == region])
        for region in ("hkjc", "au")
    }
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
        _attach_meeting_context(m, entry["meeting"], entry["races_data"])
        result["meetings"].append(_attach_track_geometry(entry["meeting"]))
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


def _run_date(snapshot):
    """Comparable date suffix from ``sport:YYYY-MM-DD`` run identifiers."""
    run_id = str((snapshot or {}).get("analysis_run_id") or "")
    value = run_id.rsplit(":", 1)[-1]
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""


def _merge_sports_feed(cached, fresh, today=None):
    """Never let a checkout without one domain's data erase a valid live feed.

    AU and Tennis publish from different checkouts.  The AU scheduler has no
    Tennis database, so rebuilding every domain there used to replace a valid
    live Tennis card with ``tennis:unavailable``.  Fresh valid data remains the
    authority; an unavailable/blocked or older local view falls back to the
    already-published domain snapshot.
    """
    if not isinstance(cached, dict):
        return fresh
    merged = copy.deepcopy(fresh) if isinstance(fresh, dict) else {}
    merged.setdefault("schema_version", cached.get("schema_version", 2))
    merged.setdefault("sports", {})
    cached_sports = cached.get("sports") or {}
    for sport, old in cached_sports.items():
        new = merged["sports"].get(sport) or {}
        old_status = str((old or {}).get("validation_status") or "")
        new_status = str(new.get("validation_status") or "")
        old_is_good = old_status in {"valid", "partial"}
        new_is_good = new_status in {"valid", "partial"}
        older = old_is_good and new_is_good and _run_date(new) < _run_date(old)
        # NBA run dates are Sydney game dates.  A past one has tipped off, so
        # it must never be republished as the current feed -- that is how the
        # 10-15 preseason combos stayed on the page until 10-20.
        expired = sport == "nba" and _run_date(old) < (today or sydney_today())
        # The local checkout ran the publication firewall on this very date and
        # blocked it.  That verdict is authoritative: the cached live feed for
        # the same (or an older) date was published before the firewall was
        # consulted, so keeping it would republish exactly what was blocked.
        firewall_blocked = (
            sport == "nba"
            and new_status == "blocked"
            and any(str(w).startswith("nba_firewall_blocked")
                    for w in (new.get("warnings") or []))
            and _run_date(new) >= _run_date(old)
        )
        # The local checkout analysed this date and found NO validated combo (the
        # calibrated probability layer makes that the normal case: most days have no
        # +EV 穩膽).  That is a real answer, not a missing domain: source files exist
        # and the warning says so.  Without this, the combos published earlier on the
        # same date -- e.g. by an earlier, over-confident run -- stayed on the board
        # for ever (2026-10-23: +98.6% EV combos survived the honest re-run).
        no_validated_combos = (
            sport == "nba"
            and new_status == "blocked"
            and bool(new.get("source_files"))
            and "no_validated_nba_combos" in [str(w) for w in (new.get("warnings") or [])]
            and _run_date(new) >= _run_date(old)
        )
        old_latest = old.get("latest_analysis") or {}
        new_latest = new.get("latest_analysis") or {}
        # A domain-less checkout may publish racing; preserve already verified
        # NBA analysis without restoring any formal BET recommendations.
        if (sport == "nba" and old_latest.get("games") and not expired
                and (not new_latest.get("games")
                     or str(old_latest.get("event_date", "")) > str(new_latest.get("event_date", "")))):
            new = copy.deepcopy(new)
            new["latest_analysis"] = copy.deepcopy(old_latest)
            new["analysis_run_id"] = old.get("analysis_run_id")
            merged["sports"][sport] = new
        # Code releases can run from an older same-day checkout. Keep each
        # verified read-only report when that checkout has older inputs, while
        # leaving the fresh formal recommendation/firewall decision untouched.
        if (sport == "nba" and not expired and old_latest.get("games")
                and old_latest.get("event_date") == new_latest.get("event_date")):
            old_games = {g.get("game_tag"): g for g in old_latest["games"]}
            games = []
            for game in new_latest.get("games", []):
                saved = old_games.get(game.get("game_tag"), {})
                older_report = (game.get("status") == "analysed"
                                and str(saved.get("analysis_time", "")) > str(game.get("analysis_time", "")))
                missing_report = game.get("status") in {"awaiting_analysis", "waiting_player_markets", "data_insufficient"}
                games.append(copy.deepcopy(saved if saved.get("status") == "analysed"
                                           and (older_report or missing_report) else game))
            if games != new_latest.get("games", []):
                new = copy.deepcopy(new)
                latest = copy.deepcopy(new_latest)
                latest["games"] = games
                analysed = sum(g.get("status") == "analysed" for g in games)
                latest["coverage"] = {"scheduled_games": len(games), "analysed_games": analysed,
                                      "pending_games": len(games) - analysed,
                                      "review_candidates": sum(len(g.get("review_candidates", [])) for g in games),
                                      "formal_sgm_count": sum(g.get("formal_sgm_count", 0) for g in games)}
                new["latest_analysis"] = latest
                merged["sports"][sport] = new
        # Read-only, previously verified analysis survives a checkout without
        # this domain's files. Never restore BET recommendations through here.
        old_cards = [card for card in (old.get("analysis_cards") or [])
                     if isinstance(card, dict) and card.get("analysis_only") is True
                     and card.get("decision") == "OBSERVE"
                     and card.get("validation_status") == "analysis_only"]
        if (sport == "nba" and old_cards and not expired and not new.get("analysis_cards")
                and _run_date(old) >= _run_date(new)):
            new = copy.deepcopy(new)
            new["analysis_cards"] = copy.deepcopy(old_cards)
            if _run_date(old) > _run_date(new):
                new["analysis_run_id"] = old["analysis_run_id"]
            merged["sports"][sport] = new
        if (old_is_good and not expired and not firewall_blocked
                and not no_validated_combos and (not new_is_good or older)):
            kept = copy.deepcopy(old)
            warnings = list(kept.get("warnings") or [])
            marker = "preserved_from_live_snapshot:local_domain_unavailable_or_older"
            if marker not in warnings:
                warnings.append(marker)
            kept["warnings"] = warnings
            merged["sports"][sport] = kept
            print(f"   ⚠️ Preserved valid {sport} feed from live snapshot; "
                  f"local view was {new_status or 'missing'} / {_run_date(new) or 'undated'}")
    # Tracking has its own read-only evidence authority, independent of live BET status.
    old_tracking = (cached_sports.get('nba') or {}).get('tracking')
    fresh_tracking = ((fresh or {}).get('sports', {}).get('nba') or {}).get('tracking')
    nba = merged['sports'].setdefault('nba', {})
    if fresh_tracking and fresh_tracking.get('status') == 'valid':
        nba['tracking'] = copy.deepcopy(fresh_tracking)
        covered = set(fresh_tracking.get('covered_dates', []))
        # A different domain's checkout, or later cold archival, must not erase
        # already-published history. Locally covered dates remain authoritative.
        retained = [r for r in (old_tracking or {}).get('records', [])
                    if r.get('day') not in covered]
        by_id = {r['id']: r for r in retained}
        by_id.update({r['id']: r for r in fresh_tracking.get('records', [])})
        nba['tracking']['records'] = list(by_id.values())
        if retained:
            nba['tracking']['retained_dates'] = sorted({r['day'] for r in retained})
    elif old_tracking:
        nba['tracking'] = copy.deepcopy(old_tracking)
        nba['tracking']['status'] = 'stale'
    if nba.get('tracking'):
        nba['tracking']['inception_date'] = TRACKING_START_DATE
        nba['tracking']['records'] = [r for r in nba['tracking'].get('records', [])
                                      if isinstance(r.get('day'), str) and r['day'] >= TRACKING_START_DATE]
        for field in ('covered_dates', 'retained_dates'):
            if field in nba['tracking']:
                nba['tracking'][field] = [day for day in nba['tracking'][field] if day >= TRACKING_START_DATE]
    # Tennis model history has an independent authority from live BET gating.
    previous = (cached_sports.get('tennis') or {}).get('tracking')
    current = ((fresh or {}).get('sports', {}).get('tennis') or {}).get('tracking')
    if current or previous:
        tennis = merged['sports'].setdefault('tennis', {})
        if current and current.get('status') == 'valid':
            tennis['tracking'] = copy.deepcopy(current)
            covered = set(current.get('covered_dates', []))
            retained = [r for r in (previous or {}).get('records', []) if r.get('day') not in covered]
            by_id = {r['id']: r for r in retained}
            by_id.update({r['id']: r for r in current.get('records', [])})
            tennis['tracking']['records'] = list(by_id.values())
            if retained:
                tennis['tracking']['retained_dates'] = sorted({r.get('day', '') for r in retained})
            if previous and 'prop_live_bets' not in current.get('source_counts', {}):
                tennis['tracking']['actual_bets'] = copy.deepcopy(previous.get('actual_bets', []))
        elif previous:
            tennis['tracking'] = copy.deepcopy(previous)
            tennis['tracking']['status'] = 'stale'
    return merged


def generate_html(data):
    """Generate self-contained HTML dashboard."""
    apply_au_display_policy(data)
    # A base snapshot may already contain yesterday's sports_feed.  It is only
    # a transport/cache for race data, never the authority for NBA/Tennis.
    # Rebuild the feed on every deploy so completed domain analysis appears
    # immediately and stale recommendations cannot survive a snapshot reuse.
    cached_feed = data.get("sports_feed")
    try:
        tennis_db = _resolve_tennis_db_path()
        fresh_feed = build_multisport_feed(
            Path(__file__).resolve().parent.parent,
            tennis_db_path=tennis_db,
        )
        data["sports_feed"] = _merge_sports_feed(cached_feed, fresh_feed)
    except Exception as exc:
        print(f"   ⚠️ Live multi-sport feed not available: {exc}")
        blocked_feed = {
            "schema_version": 2,
            "validation_status": "blocked",
            "validation_errors": [str(exc)],
            "sports": {},
        }
        data["sports_feed"] = _merge_sports_feed(cached_feed, blocked_feed)
    history_path = Path(__file__).resolve().parent / "data" / "multisport_history.json"
    if "sports_history" not in data:
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            data["sports_history"] = {
                "schema_version": history.get("schema_version", 1),
                "generated_from": history.get("generated_from", ""),
                "nba": history.get("nba", []),
                "tennis": history.get("tennis", []),
            }
        except (OSError, ValueError) as exc:
            print(f"   ⚠️ Multi-sport history not available: {exc}")
            data["sports_history"] = {"schema_version": 1, "nba": [], "tennis": []}
    css_path = Path(__file__).resolve().parent / "frontend" / "src" / "index.css"
    css_content = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    
    # The page restores packed fields before its first render (unpackDashboardData).
    data_json = json.dumps(pack_for_transport(data), ensure_ascii=False, default=str).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    generated_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    html_template_path = Path(__file__).resolve().parent / "static_template.html"
    template = html_template_path.read_text(encoding="utf-8")
    
    # Replace placeholders
    html = template.replace("/* __CSS_PLACEHOLDER__ */", css_content)
    html = html.replace('"__DATA_PLACEHOLDER__"', data_json)
    html = html.replace("__GENERATED_TIME__", generated_time)
    
    return html


def meeting_slug(key):
    """Filesystem-safe name for a "date|venue" meeting key."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", key).strip("-").lower()


def extract_analysis_bundles(payload):
    """Pull `raw_text` out of the inlined payload into per-meeting side files.

    Measured 2026-09-02 on a six-meeting card: raw_text is 6.79 MiB of a 9.62
    MiB snapshot -- 70.5% -- and it is only read when the reader opens 完整分析
    on one horse. Inlining it meant every visitor downloaded six meetings of
    full analysis text to look at one race.

    Returns (payload_without_raw_text, {slug: {"race|horse": text}}). The caller
    writes the bundles beside the HTML; the page fetches one on first expand.

    IMPORTANT: only the HTML-inlined copy is stripped. `dashboard-data.json`
    stays complete, because it is the base snapshot that incremental merges
    build on -- stripping it would permanently lose raw_text for every meeting
    not re-parsed that day.
    """
    bundles = {}
    for key, entry in (payload.get("races") or {}).items():
        bundle = {}
        for analyst, races in (entry.get("races_by_analyst") or {}).items():
            for race in races:
                for horse in race.get("horses") or []:
                    raw = horse.pop("raw_text", None)
                    if not raw:
                        continue
                    bundle[f"{analyst}|{race.get('race_number')}|{horse.get('horse_number')}"] = raw
        if bundle:
            bundles[meeting_slug(key)] = bundle
    return payload, bundles


def _slim_for_transport(payload):
    """Drop per-horse fields that are verbatim duplicates of another field.

    Cloudflare Pages refuses any single file over 25 MiB. On 2026-08-07 the
    snapshot reached 32.5 MiB (nine Saturday meetings, 75 races) and the deploy
    failed three times, so a full night of analysis never reached the dashboard
    and the next morning's run could not recover it -- its recovery path only
    looks at meetings already published.

    `core_analysis` is a section extracted out of `raw_text` and then stored
    again beside it: measured across 1,067 horses in ten meetings, every single
    one was a substring of that horse's `raw_text` (HKJC carries none at all).
    Dropping it takes the snapshot from 28.1 MiB to 19.1 MiB. The frontend still
    shows the text -- both renderers derive their sections from `raw_text` when
    it is present.

    The substring is re-checked per horse rather than assumed, so a horse whose
    `core_analysis` is NOT contained in its `raw_text` keeps the field and
    nothing is lost.
    """
    if not isinstance(payload, dict) or "races" not in payload:
        return payload, 0
    dropped = 0
    for entry in (payload.get("races") or {}).values():
        for races in (entry.get("races_by_analyst") or {}).values():
            for race in races:
                for horse in race.get("horses") or []:
                    raw = horse.get("raw_text") or ""
                    core = (horse.get("core_analysis") or "").strip()
                    if core and core in raw:
                        horse.pop("core_analysis")
                        dropped += 1
                    dropped += _slim_dimension_prose(horse, raw)
    return payload, dropped


def _slim_dimension_prose(horse, raw):
    """Drop per-dimension prose that is already verbatim in `raw_text`.

    `dimension_details` costs 5.8 KiB per horse if kept whole, and merging it
    into the snapshot took one meeting from 1.50 MiB to 2.84 MiB (+89%) --
    projected 16.7 MiB for six meetings, which a nine-meeting Saturday would
    push past Cloudflare's 25 MiB per-file limit. That is the exact failure of
    2026-08-07: three nights of deploys rejected and a full night of analysis
    never reaching the dashboard.

    Measured across the same meeting: 0 of 588 verdicts and 0 of 588 evidence
    lines were absent from their horse's `raw_text`. They are pure duplication.
    The numbers -- score, weight, contribution, symbol, sample_counts -- are
    what the UI cannot reconstruct without re-parsing prose, and they cost only
    1.13 KiB per horse, so those stay.

    Membership is re-checked per string rather than assumed, so anything the
    renderer could not otherwise recover is kept.
    """
    removed = 0
    for detail in horse.get("dimension_details") or []:
        verdict = (detail.get("verdict") or "").strip()
        if verdict and verdict in raw:
            detail.pop("verdict")
            removed += 1
        evidence = detail.get("evidence") or []
        if evidence and all(line in raw for line in evidence):
            detail.pop("evidence")
            removed += 1
    return removed


# Cloudflare Pages rejects any SINGLE asset over 25 MiB. Warn well before that:
# on 2026-08-07 the deploy hit the limit and failed three nights running, and the
# next morning's run could not recover it (its recovery path only looks at
# meetings already published). 20 MiB is ~100 races at the current 205 KiB/race,
# i.e. two more record Saturdays of runway to react in.
CLOUDFLARE_ASSET_LIMIT = 25 * 1024 * 1024
CLOUDFLARE_WARN_AT = 20 * 1024 * 1024


def _size_breakdown(payload, limit=6):
    """Largest sections of a transport payload, for the size gate's message.

    The message used to hard-code "the biggest target is raw_text". On
    2026-10-31 it was tennis tracking (12.2 MiB), so the hint sent the reader
    after the wrong field. Measure instead of guessing.
    """
    def size(value):
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                              default=str).encode("utf-8"))
    if not isinstance(payload, dict):
        return []
    sections = {k: size(v) for k, v in payload.items() if k not in ("races", "sports_feed")}
    for key, entry in (payload.get("races") or {}).items():
        sections[f"races/{key}"] = size(entry)
    for sport, feed in (((payload.get("sports_feed") or {}).get("sports")) or {}).items():
        sections[f"sports_feed/{sport}"] = size(feed)
    return sorted(sections.items(), key=lambda kv: -kv[1])[:limit]


def _check_upload_size(path: Path, label: str, payload=None) -> None:
    """Report an artifact's size against the Cloudflare per-file limit.

    ⚠️ Must be called for the HTML too, not just the JSON snapshot. The HTML
    inlines the snapshot on top of the template, so it can be the larger of the
    two — measured 2026-08-22: JSON 15.08 MiB, HTML 15.63 MiB. Checking only
    the JSON (as this did until then) meant the warning fired when the HTML was
    already at ~24.3 MiB, with essentially no room left to act.

    `payload` (the packed transport form, or a callable producing it) lets the message name what is
    actually large once the warning threshold is reached.
    """
    size = path.stat().st_size
    pct = size / CLOUDFLARE_ASSET_LIMIT * 100
    print(f"   {label}: {size / (1024 * 1024):.2f} MiB "
          f"({pct:.0f}% of Cloudflare's 25 MiB per-file limit)")
    if size < CLOUDFLARE_WARN_AT:
        return
    if callable(payload):       # deferred: packing a copy is only worth it here
        payload = payload()
    biggest = "、".join(f"{name} {n / (1024 * 1024):.2f} MiB"
                        for name, n in _size_breakdown(payload)) or "（冇 payload 可量）"
    if size >= CLOUDFLARE_ASSET_LIMIT:
        raise SystemExit(
            f"❌ {path.name} 係 {size / (1024 * 1024):.2f} MiB，超過 Cloudflare "
            f"單檔 25 MiB 上限 —— 上傳一定會被拒。唔好白推一次：先瘦身。\n"
            f"   最大嘅部份：{biggest}\n"
            f"   只增唔減嘅內容要入 pack_for_transport（見 PACKED_HORSE_FIELDS）。"
        )
    print(f"   ⚠️ 逼近 25 MiB 上限（{pct:.0f}%）—— 再多幾個場次就會被拒收，"
          f"而 2026-08-07 同 2026-10-31 就係咁死。最大嘅部份：{biggest}")


def _write_analysis_bundles(directory: Path, bundles):
    """Write one JSON file per meeting and remove files for meetings that left.

    Stale files are deleted rather than left behind: a meeting dropped from the
    snapshot whose analysis file survived would keep serving text for a card
    that no longer exists.
    """
    if not bundles:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    expected = set()
    for slug, bundle in bundles.items():
        path = directory / f"{slug}.json"
        expected.add(path.name)
        path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        _check_upload_size(path, f"Analysis bundle {slug}")
        written.append(path)
    for existing in directory.glob("*.json"):
        if existing.name not in expected:
            existing.unlink()
    return written


def _snapshot_horses(payload):
    for entry in (payload.get("races") or {}).values():
        for races in (entry.get("races_by_analyst") or {}).values():
            for race in races:
                yield from race.get("horses") or []


# ── Transport packing ────────────────────────────────────────────────────────
# Cloudflare Pages refuses any single file over 25 MiB, and both the snapshot
# JSON and the HTML are single files. Everything below exists because content
# that only ever grows was stored as plain JSON inside them:
#
#   2026-08-07  32.5 MiB, nine meetings -> deploy refused three nights running
#   2026-10-17  full Saturday card over 25 MiB even with duplicates slimmed
#   2026-10-31  7 of 16 AU meetings refused: tennis tracking alone was
#               14,350 records / 12.2 MiB, and per-horse raw_text gzip could
#               not share a dictionary across horses (5.78 MiB for 812 horses)
#
# So the rule is: bulky, read-only content travels as ONE gzip blob per owner
# (per meeting for horse prose, per feed for tennis history), and the readers --
# load_snapshot here, unpackDashboardData() in the page -- restore it before
# anything looks at it. Scores, race numbers, odds and metadata stay as plain
# JSON, because the scheduler validates them with a bare json.loads.
# Measured on the 2026-10-31 live snapshot: horse prose 8.92 -> 2.32 MiB,
# tennis tracking 12.20 -> 0.57 MiB.
PACKED_HORSE_FIELDS = ("raw_text", "data_readout", "dimension_details")


def _gzip_b64(value):
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      default=str).encode("utf-8")
    return base64.b64encode(gzip.compress(body, 9, mtime=0)).decode("ascii")


def _gunzip_b64(encoded):
    try:
        return json.loads(gzip.decompress(base64.b64decode(encoded, validate=True)))
    except (ValueError, OSError, EOFError, TypeError) as exc:
        raise ValueError(f"packed snapshot field is corrupt: {exc}") from exc


def _pack_meeting_horse_fields(payload):
    """Move PACKED_HORSE_FIELDS of every horse into one blob per meeting.

    Mutates `payload`; callers hand it a copy. Keys are positional
    ("analyst|race_index|horse_index") so they cannot collide even if a card
    repeats a horse number.
    """
    for entry in (payload.get("races") or {}).values():
        bundle = {}
        for analyst, races in (entry.get("races_by_analyst") or {}).items():
            for ri, race in enumerate(races or []):
                for hi, horse in enumerate(race.get("horses") or []):
                    fields = {f: horse.pop(f) for f in PACKED_HORSE_FIELDS if f in horse}
                    if fields:
                        bundle[f"{analyst}|{ri}|{hi}"] = fields
        if bundle:
            entry["horse_fields_gzip"] = _gzip_b64(bundle)
    return payload


def _unpack_meeting_horse_fields(payload):
    for key, entry in (payload.get("races") or {}).items():
        encoded = entry.pop("horse_fields_gzip", None)
        if encoded is None:
            continue
        bundle = _gunzip_b64(encoded)
        try:
            for ref, fields in bundle.items():
                analyst, ri, hi = ref.rsplit("|", 2)
                horse = entry["races_by_analyst"][analyst][int(ri)]["horses"][int(hi)]
                horse.update(fields)
        except (KeyError, IndexError, ValueError, AttributeError) as exc:
            raise ValueError(f"{key}: horse_fields_gzip does not match its races: {exc}") from exc
    return payload


def _tennis_tracking(payload):
    sports = ((payload or {}).get("sports_feed") or {}).get("sports") or {}
    tracking = (sports.get("tennis") or {}).get("tracking")
    return tracking if isinstance(tracking, dict) else None


def _pack_tennis_tracking(payload):
    """Return `payload` with tennis tracking records packed; never mutates it.

    The history is deliberately uncapped (every model pick stays auditable),
    so it grows every day; packing keeps it at ~1/21 of its plain size.
    """
    tracking = _tennis_tracking(payload)
    if tracking is None or not isinstance(tracking.get("records"), list):
        return payload
    packed = {k: v for k, v in tracking.items() if k != "records"}
    packed["records_gzip"] = _gzip_b64(tracking["records"])
    packed["records_count"] = len(tracking["records"])
    # Copy only the path down to `tracking`; the races stay shared.
    feed = dict(payload["sports_feed"])
    feed["sports"] = dict(feed["sports"])
    feed["sports"]["tennis"] = dict(feed["sports"]["tennis"], tracking=packed)
    return dict(payload, sports_feed=feed)


def _unpack_tennis_tracking(payload):
    tracking = _tennis_tracking(payload)
    if tracking is None or "records_gzip" not in tracking:
        return payload
    records = _gunzip_b64(tracking.pop("records_gzip"))
    expected = tracking.pop("records_count", None)
    if not isinstance(records, list) or (expected is not None and len(records) != expected):
        raise ValueError("tennis tracking records_gzip is truncated")
    tracking["records"] = records
    return payload


def pack_for_transport(payload):
    """Packed copy of a snapshot for the JSON file or the page; input untouched."""
    if not isinstance(payload, dict) or "races" not in payload:
        return payload
    packed = dict(_pack_tennis_tracking(payload), races=copy.deepcopy(payload["races"]))
    return _pack_meeting_horse_fields(packed)


def load_snapshot(path):
    """Read legacy or packed snapshots, restoring every packed field.

    Invalid packed data raises rather than publishing incomplete analysis or
    silently dropping tracking history from the next merge base.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for horse in _snapshot_horses(payload):
        # Per-horse format written until 2026-10-31; still readable.
        encoded = horse.pop("raw_text_gzip", None)
        if encoded is not None:
            horse["raw_text"] = gzip.decompress(
                base64.b64decode(encoded, validate=True)).decode("utf-8")
    _unpack_meeting_horse_fields(payload)
    return _unpack_tennis_tracking(payload)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload, dropped = _slim_for_transport(payload)
    # ⚠️ No indent, compact separators. Pretty-printing this snapshot cost
    # 4 MiB of pure whitespace against a 25 MiB hard limit.
    transport = pack_for_transport(payload)
    body = json.dumps(transport, ensure_ascii=False, separators=(",", ":"),
                      default=str)
    path.write_text(body, encoding="utf-8")
    if dropped:
        print(f"   Slimmed {dropped} duplicate core_analysis fields")
    if "races" in (payload if isinstance(payload, dict) else {}):
        _check_upload_size(path, "Snapshot JSON", transport)


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
        help="Existing dashboard-data.json to preserve while incrementally updating one meeting.",
    )
    parser.add_argument(
        "--meeting-dir",
        "--au-meeting-dir",
        dest="au_meeting_dir",
        default="",
        help="Meeting folder (AU `2026-09-04 Wyong ...` or HKJC "
             "`2026-09-06_ShaTin`) to merge into --base-snapshot. The old "
             "`--au-meeting-dir` spelling still works.",
    )
    parser.add_argument(
        "--from-snapshot",
        default="",
        help="Render HTML/JSON from an already-built snapshot without rescanning "
             "local meeting folders. The scheduler builds its snapshot first; "
             "rescanning would both discard that work and require reading HK "
             "meetings from Google Drive, which launchd cannot do.",
    )
    parser.add_argument(
        "--output-analysis-dir",
        default="",
        help="Where to write the per-meeting 完整分析 bundles (default: an "
             "`analysis/` directory beside the HTML).",
    )
    parser.add_argument(
        "--drop-meeting",
        action="append",
        default=[],
        metavar="DATE|VENUE",
        help="Remove this meeting from --base-snapshot (repeatable). Used after "
             "a meeting is archived; without it nothing can leave the snapshot.",
    )
    return parser.parse_args(), parser


def main():
    args, parser = parse_args()
    print("🏇 Generating static dashboard...")
    print("   Scanning for meetings...")
    # ⚠️ `parser` 以前唔喺 scope，所以呢個 guard 一觸發就 NameError 而唔係一個
    # 講得明嘅用法錯誤。
    if args.from_snapshot and (args.base_snapshot or args.au_meeting_dir
                               or args.drop_meeting):
        parser.error("--from-snapshot renders an existing snapshot; it cannot be "
                     "combined with the incremental-merge flags")
    if args.au_meeting_dir and not args.base_snapshot:
        parser.error("--au-meeting-dir requires --base-snapshot")
    if args.drop_meeting and not args.base_snapshot:
        parser.error("--drop-meeting requires --base-snapshot")
    if args.base_snapshot and not (args.au_meeting_dir or args.drop_meeting):
        parser.error("--base-snapshot needs --au-meeting-dir or --drop-meeting")
    if args.base_snapshot and args.au_meeting_dir and args.drop_meeting:
        parser.error("--drop-meeting and --au-meeting-dir are separate passes; "
                     "run the drop first, then merge from its output")
    if args.from_snapshot:
        data = load_snapshot(args.from_snapshot)
        data.setdefault("roi", {})
        data["meta"] = _build_snapshot_meta(data)
        print(f"   Rendering from prebuilt snapshot: "
              f"{len(data.get('meetings') or [])} meetings")
    elif args.drop_meeting:
        data = drop_au_meetings(args.base_snapshot, args.drop_meeting)
    elif args.base_snapshot:
        data = collect_incremental_au_data(args.base_snapshot, args.au_meeting_dir)
    else:
        data = collect_all_data(args.cache_path)
    
    apply_au_display_policy(data)
    _ensure_region_side_roi(data)
    _ensure_au_venue_profiles(data)
    meeting_count = len(data["meetings"])
    race_count = sum(
        len(races) 
        for rd in data["races"].values() 
        for races in rd["races_by_analyst"].values()
    )
    print(f"   Found {meeting_count} meetings, {race_count} race analyses")
    
    # Slim BEFORE building the HTML, not only on the JSON write path.
    # _slim_for_transport used to run inside _write_json alone, so the HTML --
    # which inlines the same payload and is always the LARGER artifact -- kept
    # every duplicated field. With the dimension breakdown added on 2026-09-02
    # that gap became 16.88 MiB of HTML against 9.43 MiB of JSON, i.e. 68% of
    # Cloudflare's 25 MiB per-file limit on a six-meeting card. A nine-meeting
    # Saturday would have been rejected, which is the 2026-08-07 failure again.
    # _write_json still calls it; on an already-slimmed payload it drops 0.
    data, slimmed = _slim_for_transport(data)
    if slimmed:
        print(f"   Transport slim: dropped {slimmed} duplicated fields")

    print("   Building HTML...")
    # The HTML gets a copy with raw_text lifted out; `data` keeps it so the
    # snapshot JSON written below stays a complete base for the next merge.
    html_payload = copy.deepcopy(data)
    html_payload, analysis_bundles = extract_analysis_bundles(html_payload)
    html = generate_html(html_payload)
    # generate_html rebuilds the live sports feed on the copy it is handed;
    # carry that back so the snapshot JSON does not ship yesterday's feed.
    for key in ("sports_feed", "sports_history", "meta"):
        if key in html_payload:
            data[key] = html_payload[key]
    
    output_path = Path(args.output_html)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    # The HTML is the biggest artifact we upload — check it, not just the JSON.
    _check_upload_size(output_path, "Dashboard HTML",
                       lambda: pack_for_transport(html_payload))

    analysis_dir = Path(args.output_analysis_dir or (output_path.parent / "analysis"))
    written = _write_analysis_bundles(analysis_dir, analysis_bundles)
    if written:
        total = sum(path.stat().st_size for path in written)
        print(f"   Analysis bundles: {len(written)} files, "
              f"{total / 1024 / 1024:.2f} MiB lifted out of the HTML")

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
