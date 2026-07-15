"""Enrich parsed Antigravity races with display metadata used by every UI.

Both the live static snapshot and the local/test FastAPI app call this module,
so horse colours and bilingual HKJC names cannot drift between builds.
"""
import re
from pathlib import Path

from models.race import Region


HKJC_SILK_BASE_URL = "https://racing.hkjc.com/racing/content/Images/RaceColor"
HKJC_RACECARD_RACE_RE = re.compile(r"Race\s+(\d+)\s+排位表\.md$", re.IGNORECASE)
HKJC_HORSE_CODE_RE = re.compile(r"^[A-Z]\d{3}$")
HKJC_HORSE_ID_RE = re.compile(r"^HK_\d{4}_[A-HJ-Z]\d{3}$")
HKJC_HORSE_REGISTRATION_YEARS = {
    "A": 2016, "B": 2017, "C": 2018, "D": 2019, "E": 2020,
    "G": 2021, "H": 2022, "J": 2023, "K": 2024, "L": 2025, "M": 2026,
}
HKJC_PDF_ENGLISH_NAME_RE = re.compile(
    r"^(?:(?:\d+|Standby)\s+)+(?P<zh>[\u3400-\u9fff]+)\s+(?P<en>[A-Z][A-Z0-9'&. -]+)$"
)
AU_RACECARD_RACE_RE = re.compile(r"\bRACE\s+(\d+)\b", re.IGNORECASE)
AU_SILK_URL_RE = re.compile(
    r"^https://images\.puntcdn\.com/silks/[A-Za-z0-9_./-]+\.svg(?:\?.*)?$"
)


def hkjc_horse_profile_metadata(horse_code, horse_id=None, profile_url=None):
    """Return a validated canonical HKJC horse id/profile pair."""
    code = str(horse_code or "").strip().upper()
    candidate = str(horse_id or "").strip().upper()
    if not candidate and profile_url:
        match = re.search(r"horseid=(HK_\d{4}_[A-HJ-Z]\d{3})", str(profile_url), re.I)
        candidate = match.group(1).upper() if match else ""
    if not HKJC_HORSE_ID_RE.fullmatch(candidate):
        year = HKJC_HORSE_REGISTRATION_YEARS.get(code[:1])
        candidate = f"HK_{year}_{code}" if year and HKJC_HORSE_CODE_RE.fullmatch(code) else ""
    if not HKJC_HORSE_ID_RE.fullmatch(candidate):
        return {"hkjc_horse_id": None, "horse_profile_url": None}
    return {
        "hkjc_horse_id": candidate,
        "horse_profile_url": (
            "https://racing.hkjc.com/zh-hk/local/information/horse"
            f"?horseid={candidate}"
        ),
    }


def parse_hkjc_racecard_silks(path):
    """Return HKJC display metadata keyed by horse number for one racecard."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    silks = {}
    for block in re.split(r"(?=^馬號:\s*)", text, flags=re.MULTILINE):
        number_match = re.search(r"^馬號:\s*(\d+)\s*$", block, re.MULTILINE)
        code_match = re.search(r"^烙號:\s*([^\s]+)\s*$", block, re.MULTILINE)
        english_match = re.search(r"^英文馬名:\s*(.+?)\s*$", block, re.MULTILINE)
        horse_id_match = re.search(r"^HKJC馬匹ID:\s*(\S+)\s*$", block, re.MULTILINE | re.I)
        profile_match = re.search(r"^官方馬匹資料:\s*(\S+)\s*$", block, re.MULTILINE)
        if not number_match or not code_match:
            continue
        horse_code = code_match.group(1).strip().upper()
        if not HKJC_HORSE_CODE_RE.fullmatch(horse_code):
            continue
        profile = hkjc_horse_profile_metadata(
            horse_code,
            horse_id_match.group(1) if horse_id_match else None,
            profile_match.group(1) if profile_match else None,
        )
        silks[int(number_match.group(1))] = {
            "horse_code": horse_code,
            "silk_url": f"{HKJC_SILK_BASE_URL}/{horse_code}.gif",
            "horse_name_en": (
                english_match.group(1).strip().upper() if english_match else None
            ),
            **profile,
        }
    return silks


def parse_hkjc_pdf_english_names(path):
    """Return ``Chinese name -> English name`` from bilingual starter text."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    names = {}
    for line in text.splitlines():
        match = HKJC_PDF_ENGLISH_NAME_RE.fullmatch(line.strip())
        if match:
            names[match.group("zh")] = " ".join(match.group("en").split())
    return names


def _load_hkjc_english_name_map(meeting):
    names = {}
    seen_paths = set()
    for folder_path in meeting.folder_paths.values():
        for pdf_text_path in Path(folder_path).glob("*全日出賽馬匹資料*.md"):
            if pdf_text_path in seen_paths:
                continue
            seen_paths.add(pdf_text_path)
            names.update(parse_hkjc_pdf_english_names(pdf_text_path))
    return names


def _load_hkjc_silk_map(meeting):
    silk_map = {}
    seen_paths = set()
    for folder_path in meeting.folder_paths.values():
        folder = Path(folder_path)
        for racecard_path in sorted(folder.glob("*Race * 排位表.md")):
            if racecard_path in seen_paths:
                continue
            seen_paths.add(racecard_path)
            race_match = HKJC_RACECARD_RACE_RE.search(racecard_path.name)
            if not race_match:
                continue
            parsed = parse_hkjc_racecard_silks(racecard_path)
            if parsed:
                silk_map.setdefault(int(race_match.group(1)), {}).update(parsed)
    return silk_map


def enrich_hkjc_display_metadata(meeting, all_races):
    """Attach official HKJC colours and English names to every analyst."""
    silk_map = _load_hkjc_silk_map(meeting)
    english_names = _load_hkjc_english_name_map(meeting)
    if not silk_map and not english_names:
        return
    for races in all_races.values():
        for race in races:
            race_silks = silk_map.get(race.race_number, {})
            for horse in race.horses:
                silk = race_silks.get(horse.horse_number)
                if silk:
                    horse.horse_code = silk["horse_code"]
                    horse.hkjc_horse_id = silk.get("hkjc_horse_id")
                    horse.horse_profile_url = silk.get("horse_profile_url")
                    horse.silk_url = silk["silk_url"]
                    horse.horse_name_en = (
                        silk.get("horse_name_en") or horse.horse_name_en
                    )
                if not horse.horse_name_en:
                    horse.horse_name_en = english_names.get(horse.horse_name)


def parse_au_racecard_silks(path):
    """Return ``(race_number, {horse_number: silk_url})`` from Racenet markdown."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, {}
    race_match = AU_RACECARD_RACE_RE.search(text[:500]) or AU_RACECARD_RACE_RE.search(
        Path(path).name
    )
    if not race_match:
        return None, {}
    current_horse = None
    silks = {}
    for line in text.splitlines():
        horse_match = re.match(r"^(\d+)\.\s+", line.strip())
        if horse_match:
            current_horse = int(horse_match.group(1))
            continue
        silk_match = re.match(r"^Silk:\s*(\S+)\s*$", line.strip(), re.IGNORECASE)
        if current_horse is not None and silk_match:
            silk_url = silk_match.group(1)
            if AU_SILK_URL_RE.fullmatch(silk_url):
                silks[current_horse] = silk_url
    return int(race_match.group(1)), silks


def enrich_au_display_metadata(meeting, all_races):
    """Attach Racenet colours to all parsed AU analyst rows."""
    silk_map = _load_au_silk_map(meeting)
    for races in all_races.values():
        for race in races:
            for horse in race.horses:
                horse.silk_url = (
                    silk_map.get(race.race_number, {}).get(horse.horse_number)
                    or horse.silk_url
                )


def _load_au_silk_map(meeting):
    silk_map = {}
    seen_paths = set()
    for folder_path in meeting.folder_paths.values():
        folder = Path(folder_path)
        for racecard_path in folder.glob("*Racecard.md"):
            if racecard_path in seen_paths:
                continue
            seen_paths.add(racecard_path)
            race_number, parsed = parse_au_racecard_silks(racecard_path)
            if race_number and parsed:
                silk_map.setdefault(race_number, {}).update(parsed)
    return silk_map


def enrich_race_display_metadata(meeting, all_races):
    """Apply region-specific display metadata to one parsed meeting in place."""
    if meeting.region == Region.HKJC:
        enrich_hkjc_display_metadata(meeting, all_races)
    elif meeting.region == Region.AU:
        enrich_au_display_metadata(meeting, all_races)


def enrich_snapshot_display_metadata(data, meeting):
    """Overlay local racecard metadata onto one already-built dashboard meeting.

    This keeps the live/test analysis snapshot intact while adding HKJC/AU
    colours and HKJC English names from the matching Antigravity racecard files.
    """
    meeting_key = f"{meeting.date}|{meeting.venue}"
    races_payload = data.get("races", {}).get(meeting_key)
    if not races_payload:
        return {"horses": 0, "silks": 0, "english_names": 0}

    if meeting.region == Region.HKJC:
        race_metadata = _load_hkjc_silk_map(meeting)
        english_names = _load_hkjc_english_name_map(meeting)
    else:
        race_metadata = {
            race_number: {
                horse_number: {"silk_url": silk_url}
                for horse_number, silk_url in horses.items()
            }
            for race_number, horses in _load_au_silk_map(meeting).items()
        }
        english_names = {}

    race_horses = {}
    horse_count = silk_count = english_count = 0
    for races in races_payload.get("races_by_analyst", {}).values():
        for race in races:
            race_number = int(race.get("race_number") or 0)
            horse_lookup = {}
            for horse in race.get("horses", []):
                horse_count += 1
                horse_number = int(horse.get("horse_number") or 0)
                metadata = race_metadata.get(race_number, {}).get(horse_number, {})
                for field in ("horse_code", "hkjc_horse_id", "horse_profile_url", "silk_url", "horse_name_en"):
                    if metadata.get(field):
                        horse[field] = metadata[field]
                if not horse.get("horse_name_en"):
                    horse["horse_name_en"] = english_names.get(horse.get("horse_name"))
                silk_count += bool(horse.get("silk_url"))
                english_count += bool(horse.get("horse_name_en"))
                horse_lookup[horse_number] = horse
                race_horses.setdefault(race_number, {})[horse_number] = horse

            pick_groups = [race.get("top_picks", []), race.get("alt_top_picks", [])]
            pick_groups.extend((race.get("scenario_top_picks") or {}).values())
            for picks in pick_groups:
                for pick in picks or []:
                    horse = horse_lookup.get(int(pick.get("horse_number") or 0))
                    if horse:
                        _copy_display_fields(pick, horse)

    consensus_prefix = f"{meeting_key}|"
    for key, payload in data.get("consensus", {}).items():
        if not key.startswith(consensus_prefix):
            continue
        try:
            race_number = int(key.rsplit("|", 1)[1])
        except (ValueError, IndexError):
            continue
        horses = race_horses.get(race_number, {})
        groups = [
            (payload.get("consensus") or {}).get("consensus_horses", []),
            payload.get("betting_suggestions", []),
        ]
        for group in groups:
            for item in group:
                horse = horses.get(int(item.get("horse_number") or 0))
                if horse:
                    _copy_display_fields(item, horse)

    return {
        "horses": horse_count,
        "silks": silk_count,
        "english_names": english_count,
    }


def _copy_display_fields(target, horse):
    for field in (
        "horse_name_en",
        "horse_code",
        "hkjc_horse_id",
        "horse_profile_url",
        "silk_url",
        "jockey",
        "trainer",
    ):
        if horse.get(field):
            target[field] = horse[field]
