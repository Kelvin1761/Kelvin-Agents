"""NBA official injury report (league PDF, published every 15 minutes). Supplementary source.

ESPN's roster feed only says "Out" or "Day-To-Day"; the league report separates Out,
Doubtful, Questionable, Probable and Available, and lists teams that have not yet
submitted. Callers combine it with ESPN by taking the MORE severe level, so this
source can only make availability stricter, never relax it. Failures are recorded,
never raised into the pipeline.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_schedule import canonical_team_abbr

CONTRACT = "nba-official-injuries/v1"
CACHE_SECONDS = 600
INDEX_URL = "https://official.nba.com/nba-injury-report-{season}-season/"
PDF_RE = re.compile(r"https://ak-static\.cms\.nba\.com/referee/injury/"
                    r"Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})(AM|PM)\.pdf")
COLUMNS = ("GameDate", "GameTime", "Matchup", "Team", "PlayerName", "CurrentStatus", "Reason")
# Severity used by callers: out > dtd > ok (same vocabulary as nba_availability).
STATUS_LEVEL = {"out": "out", "doubtful": "out", "questionable": "dtd", "probable": "ok", "available": "ok"}
NOT_SUBMITTED = "NOTYETSUBMITTED"
SUFFIXES = ("jr", "sr", "ii", "iii", "iv", "v")
EASTERN = ZoneInfo("America/New_York")
TEAM_NICKNAMES = {
    "76ers": "PHI", "Bucks": "MIL", "Bulls": "CHI", "Cavaliers": "CLE", "Celtics": "BOS", "Clippers": "LAC",
    "Grizzlies": "MEM", "Hawks": "ATL", "Heat": "MIA", "Hornets": "CHA", "Jazz": "UTA", "Kings": "SAC",
    "Knicks": "NYK", "Lakers": "LAL", "Magic": "ORL", "Mavericks": "DAL", "Nets": "BKN", "Nuggets": "DEN",
    "Pacers": "IND", "Pelicans": "NOP", "Pistons": "DET", "Raptors": "TOR", "Rockets": "HOU", "Spurs": "SAS",
    "Suns": "PHX", "Thunder": "OKC", "Timberwolves": "MIN", "TrailBlazers": "POR", "Warriors": "GSW",
    "Wizards": "WAS",
}


def name_key(name):
    """Comparable identity for 'First Last' and the PDF's space-stripped 'Last,First'.

    The PDF glues suffixes onto the surname ("JacksonJr.", "WalkerIV"); they are only
    recognised case-sensitively right after a lowercase letter, so a surname that merely
    ends in 'v' or 'ii' is never cut.
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    if "," in text:
        last, first = text.split(",", 1)
        last = re.sub(r"(?<=[a-z])(Jr\.?|Sr\.?|III|II|IV|V)$", "", last.strip())
        text = f"{first} {last}"
    tokens = re.sub(r"[^a-z0-9 ]", "", text.casefold()).split()
    while len(tokens) > 1 and tokens[-1] in SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def team_abbr(cell):
    text = re.sub(r"\s+", "", str(cell or ""))
    matches = [abbr for nick, abbr in TEAM_NICKNAMES.items() if text.endswith(nick)]
    return matches[0] if len(matches) == 1 else None


def parse_words(pages):
    """pages: list of word lists (pdfplumber extract_words). Returns rows and not-submitted entries.

    A report covers several game days; every row and not-submitted entry keeps its own
    GameDate so a team playing back-to-back is never matched to the wrong game.
    """
    rows, not_submitted = [], []
    carry = {"GameDate": None, "GameTime": None, "Matchup": None, "Team": None}
    bounds = None
    for words in pages:
        header = {w["text"]: w["x0"] for w in words if w["text"] in COLUMNS}
        if len(header) == len(COLUMNS):
            xs = [header[c] - 2 for c in COLUMNS] + [10 ** 6]
            bounds = [(COLUMNS[i], xs[i], xs[i + 1]) for i in range(len(COLUMNS))]
            header_top = max(w["top"] for w in words if w["text"] in COLUMNS)
        elif bounds is None:
            raise ValueError("injury report header not found")
        else:
            header_top = -1
        lines = {}
        title_top = min((w["top"] for w in words if w["text"] == "Report:"), default=None)
        for w in words:
            # Every page repeats the title ("Injury Report: <time>") whose words fall inside the
            # data columns, and ends with "PageNofM"; neither is a row.
            if (w["top"] <= header_top + 1 or (title_top is not None and abs(w["top"] - title_top) < 2)
                    or re.fullmatch(r"Page\d+of\d+", w["text"])):
                continue
            lines.setdefault(round(w["top"], 0), []).append(w)
        for top in sorted(lines):
            cells = {}
            for w in sorted(lines[top], key=lambda w: w["x0"]):
                col = next((c for c, lo, hi in bounds if lo <= w["x0"] < hi), None)
                if col:
                    cells[col] = (cells.get(col, "") + w["text"])
            for col in carry:
                if cells.get(col):
                    carry[col] = cells[col]
            player = cells.get("PlayerName", "")
            if NOT_SUBMITTED in cells.values():
                if team_abbr(carry["Team"]):
                    not_submitted.append({"team": team_abbr(carry["Team"]), "game_date": carry["GameDate"],
                                          "matchup": carry["Matchup"]})
                continue
            status = cells.get("CurrentStatus", "").strip().lower()
            if player and status in STATUS_LEVEL and "," in player:
                rows.append({"game_date": carry["GameDate"], "matchup": carry["Matchup"],
                             "team": team_abbr(carry["Team"]), "player": player, "name_key": name_key(player),
                             "status": status.capitalize(), "level": STATUS_LEVEL[status],
                             "reason": cells.get("Reason", "")})
    return rows, not_submitted


def parse_pdf(data):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return parse_words([page.extract_words() for page in pdf.pages])


def report_time(url):
    match = PDF_RE.fullmatch(url)
    if not match:
        return None
    day, hour, minute, half = match.groups()
    hour = int(hour) % 12 + (12 if half == "PM" else 0)
    local = datetime.fromisoformat(day).replace(hour=hour, minute=int(minute), tzinfo=EASTERN)
    return local.astimezone(timezone.utc)


def fetch_latest(season, cache_path, *, now=None, get=None):
    """Latest published report at or before `now`, cached briefly. Never raises."""
    now = now or datetime.now(timezone.utc)
    path = Path(cache_path)
    if os.environ.get("WC_NBA_OFFICIAL_INJURIES", "1") == "0":
        return {"contract": CONTRACT, "status": "disabled"}
    try:
        cached = json.loads(path.read_text())
        captured = datetime.fromisoformat(cached["captured_at"])
        if cached.get("contract") == CONTRACT and 0 <= (now - captured).total_seconds() <= CACHE_SECONDS:
            return cached
    except (OSError, ValueError, KeyError, TypeError):
        pass
    bundle = {"contract": CONTRACT, "season": season, "status": "unavailable"}
    try:
        if get is None:
            import requests
            get = requests.get
        headers = {"User-Agent": "Mozilla/5.0"}
        index = get(INDEX_URL.format(season=season), headers=headers, timeout=15)
        urls = sorted({m.group(0) for m in PDF_RE.finditer(index.text)},
                      key=lambda u: report_time(u) or datetime.min.replace(tzinfo=timezone.utc))
        urls = [u for u in urls if report_time(u) and report_time(u) <= now]
        if not urls:
            raise ValueError("no published report")
        response = get(urls[-1], headers=headers, timeout=20)
        if response.status_code != 200:
            raise ValueError(f"report HTTP {response.status_code}")
        rows, not_submitted = parse_pdf(response.content)
        if not rows:
            raise ValueError("report parsed to zero rows")
        bundle.update(status="available", url=urls[-1], report_time=report_time(urls[-1]).isoformat(),
                      pdf_sha256=hashlib.sha256(response.content).hexdigest(), rows=rows,
                      not_submitted=not_submitted)
    except Exception as exc:  # recorded, never raised
        bundle["error"] = f"{type(exc).__name__}: {exc}"
    bundle["captured_at"] = datetime.now(timezone.utc).isoformat()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(bundle, ensure_ascii=False))
        os.replace(temporary, path)
    except OSError:
        pass
    return bundle


def for_team(bundle, team, game_date):
    """{name_key: row} for one team's game on `game_date` (US date, a datetime.date)."""
    if not isinstance(bundle, dict) or bundle.get("status") != "available":
        return {"status": (bundle or {}).get("status") or "unavailable"}
    target, day = canonical_team_abbr(team), game_date.strftime("%m/%d/%Y")
    rows = [r for r in bundle.get("rows", []) if r.get("team") == target and r.get("game_date") == day]
    pending = any(e.get("team") == target and e.get("game_date") == day for e in bundle.get("not_submitted") or [])
    listed = rows or pending
    return {"status": "available" if listed else "team_not_in_report", "report_time": bundle.get("report_time"),
            "url": bundle.get("url"), "game_date": day, "submitted": not pending,
            "players": {r["name_key"]: {k: r[k] for k in ("player", "status", "level", "reason")} for r in rows}}


def level_for(team_report, player_name):
    """Official availability level for one player: 'out', 'dtd', 'ok' or None (not listed / no data)."""
    if not isinstance(team_report, dict) or team_report.get("status") != "available":
        return None
    row = (team_report.get("players") or {}).get(name_key(player_name))
    return row["level"] if row else None
