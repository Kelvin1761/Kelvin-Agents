"""User-requested contextual full-time overlay, EXP-20261015-04 arm A.

No trial times, winner clocks, margins, early-speed or L600 bonuses. Historical
availability is not certified: rollout is prospective from a captured bundle.
"""

from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
import csv
import hashlib
import gzip
import json
import math
import os
import re
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
import numpy as np
from au_result_identity import normalize_venue_name

MODEL_VERSION = "AU_CONTEXT_TOTAL_V1"
FULL_TIME_START_DATE = "2026-10-16"
FULL_TIME_SPEED_GAIN = 1.5  # Original consensus rule refit through 2026-10-14; qualified [1, 2].
COMPONENTS = ("A",)
RUN = re.compile(r"^(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\S+)")


def norm(name):
    text = unicodedata.normalize("NFKD", name or "").lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", text))


def condition_key(value):
    value = str(value).lower().strip()
    for label in ("good", "soft", "heavy", "firm", "synthetic"):
        if value.startswith(label):
            return label
    return {
        "1": "firm",
        "2": "firm",
        "3": "good",
        "4": "good",
        "5": "soft",
        "6": "soft",
        "7": "soft",
        "8": "heavy",
        "9": "heavy",
        "10": "heavy",
    }.get(value, value)


def seconds(value):
    parts = value.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) != 3:
        raise ValueError("expected H:M:S")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def parse_csv(text, source):
    """Whole-race GPS CSV. Never consume header time or use rank as a feature."""
    import csv

    context = None
    records, counts = [], Counter()
    for columns in csv.reader(text.splitlines()):
        if len(columns) < 3:
            continue
        payload = ",".join(columns[2:]).split(";")
        if columns[0] == "Date":
            match = re.search(r"([0-9]+)m(?:_TRACK)?$", payload[-1])
            date = re.search(r"\d{4}-\d{2}-\d{2}", payload[1])
            venue = re.sub(r"^\d{4}-\d{2}-\d{2}\s+|\s+QLD\s*-.*$", "", payload[1])
            context = (date[0], normalize_venue_name(venue), int(match[1]) if match else None) if date else None
            continue
        if context is None:
            counts["missing_header"] += 1
            continue
        counts["rows"] += 1
        if len(payload) < 5 or (len(payload) - 2) % 3:
            counts["bad_shape"] += 1
            continue
        date = datetime.strptime(columns[0], "%d/%m/%Y").date().isoformat()
        points = [float(payload[i]) for i in range(2, len(payload), 3)]
        speeds = [float(payload[i]) for i in range(3, len(payload), 3)]
        splits = [seconds(payload[i]) for i in range(4, len(payload), 3)]
        if points[-1] != context[2]:
            counts["template_distance_mismatch"] += 1
        if (
            date != context[0]
            or points != sorted(set(points))
            or not 0 < points[0] <= 400
            or any(b - a != 200 for a, b in zip(points, points[1:]))
            or any(s <= 0 for s in splits)
            or any(s <= 0 for s in speeds)
        ):
            counts["invalid_or_untracked"] += 1
            continue
        total = round(sum(splits), 3)
        # Some track-template labels disagree with actual endpoints (e.g.
        # ROCK_1100m_TRACK while complete sections end at 1050). The endpoint
        # must independently match the historical formguide distance at join.
        distance = int(points[-1])
        if not 8 < distance / total < 22:
            counts["invalid_average_speed"] += 1
            continue
        records.append(
            {
                "date": date,
                "track": context[1],
                "distance": distance,
                "race": int(columns[1]),
                "horse": norm(payload[0]),
                "time": total,
                "tab": int(payload[1]),
                "source": source,
            }
        )
    return records, counts


def source_rows(text, url):
    # Older official exports use "20250301 Eagle Farm" in the header while
    # actual run rows still carry 01/03/2025. Preserve the same explicit date.
    text = re.sub(r";(\d{4})(\d{2})(\d{2})(?=\s)", r";\1-\2-\3", text)
    rows, quality = parse_csv(text, url)
    valid = {(row["date"], row["race"], row["horse"]): row for row in rows}
    for columns in csv.reader(text.splitlines()):
        if len(columns) < 3 or columns[0] == "Date":
            continue
        payload = ",".join(columns[2:]).split(";")
        d, m, y = columns[0].split("/")
        key = (f"{int(y):04}-{int(m):02}-{int(d):02}", int(columns[1]), norm(payload[0]))
        row = valid.get(key)
        if row is None:
            continue
        split = [seconds(payload[i]) for i in range(4, len(payload), 3)]
        # Only whole final 800m: four complete final 200m intervals.
        if row["distance"] <= 800 or len(split) < 5:
            continue
        row["l800"] = sum(split[-4:])
        row["early"] = row["time"] - row["l800"]
        assert abs(row["early"] - sum(split[:-4])) < 1e-8
    return [row for row in rows if row.get("early", 0) > 0], quality


def class_key(line):
    match = re.search(r"RaceClass:\[([^\]]+)\]", line)
    text = match[1].upper() if match else ""
    if "MDN" in text or "MAIDEN" in text:
        return "MDN"
    if match := re.search(r"BM\s*(\d+)", text):
        n = int(match[1])
        return "BM64" if n <= 64 else ("BM78" if n <= 78 else "BMhigh")
    if match := re.search(r"CL\s*(\d+)", text):
        return "CL3" if int(match[1]) <= 3 else "CLhigh"
    if re.search(r"\bG[123]\b|\bGROUP\s*[123]\b|\bLISTED\b", text):
        return "Group"
    return "Open" if text else "unknown"


def parse_xml(raw, source):
    """Actual horse FinishTime; never use RaceSummary/FinishTime."""
    root = ET.fromstring(raw)
    event_date = root.attrib["EventDate"][:10]
    course = normalize_venue_name(root.findtext("CourseName") or "")
    number = int(re.search(r"_R(\d+)\.xml$", source, re.I)[1])
    title = root.findtext("RaceName") or ""
    if re.search(r"\bTRIAL\b|JUMP.?OUT", title, re.I):
        return None
    raw_going = root.findtext("TrackCondition") or "unknown"
    going = condition_key(raw_going)
    rating = (re.search(r"(10|[1-9])\b", raw_going) or [None, "unknown"])[1]
    rail_raw = root.findtext("RailPosition") or "unknown"
    rail_match = re.search(r"(?:^|\+)\s*(\d+(?:\.\d+)?)\s*m", rail_raw, re.I)
    rail = str(int(float(rail_match[1]) // 2) * 2) if rail_match else ("0" if "true" in rail_raw.lower() else "unknown")
    clean_title = re.sub(r"BENCHMARK\s*(\d+)", r"BM\1", title, flags=re.I)
    clean_title = re.sub(r"CLASS\s*(\d+)", r"CL\1", clean_title, flags=re.I)
    category = class_key("RaceClass:[" + clean_title + "]")
    rows = []
    for horse in root.findall("./Horses/HorseSummary"):
        sections = horse.findall("./Sections/SectionSummary")
        if len(sections) < 5:
            continue
        points = [float(s.attrib["CumulatedDistance"]) for s in sections]
        if (
            points != sorted(set(points))
            or not 0 < points[0] <= 400
            or any(b - a != 200 for a, b in zip(points, points[1:]))
            or points[-1] <= 800
        ):
            continue
        try:
            splits = [seconds(s.find("SectionTime").attrib["Time"]) for s in sections]
            finish = seconds(horse.find("FinishTime").attrib["Time"])
        except (AttributeError, KeyError, ValueError):
            continue
        if any(t <= 0 for t in splits) or abs(sum(splits) - finish) > 0.05:
            continue
        distance = int(points[-1])
        if not 8 < distance / finish < 22:
            continue
        l800 = sum(splits[-4:])
        rows.append(
            {
                "horse": norm(horse.attrib["Name"]),
                "horse_code": horse.attrib.get("HorseCode"),
                "time": finish,
                "early": finish - l800,
                "l800": l800,
                "distance": distance,
                "finish_time_official": horse.attrib.get("IsFinishTimeOfficial"),
                "source": source,
            }
        )
    distances = {row["distance"] for row in rows}
    if len(rows) < 3 or len(distances) != 1:
        return None
    distance = next(iter(distances))
    key = (course, event_date, number, distance)
    for row in rows:
        row["key"] = key
    return {
        "track": course,
        "date": event_date,
        "distance": distance,
        "key": key,
        "going": going,
        "rating": str(rating),
        "rail": rail,
        "rail_raw": rail_raw,
        "class": category,
        "rows": rows,
        "total": statistics.median(r["time"] for r in rows),
        "early": statistics.median(r["early"] for r in rows),
    }


class ContextStandard:
    """Partially pooled log-time standards with class as an estimation nuisance."""

    def __init__(self, events, segment):
        self.segment = segment
        self.keys = []
        self.penalties = [1e-6, 1.0, 1.0]
        for kind, penalty in (
            ("track", 20.0),
            ("going", 40.0),
            ("track_band", 30.0),
            ("track_going", 40.0),
            ("rating", 20.0),
            ("track_rail", 40.0),
            ("class", 20.0),
        ):
            for key in sorted({self.category(event, kind) for event in events}):
                self.keys.append((kind, key))
                self.penalties.append(penalty)
        self.index = {key: i + 3 for i, key in enumerate(self.keys)}
        x = np.array([self.vector(event) for event in events])
        y = np.array([math.log(event[segment] / self.length(event)) for event in events])
        weights = np.ones(len(events))
        for _ in range(3):
            self.beta = np.linalg.solve(x.T @ (weights[:, None] * x) + np.diag(self.penalties), x.T @ (weights * y))
            residual = np.abs(y - x @ self.beta)
            weights = np.minimum(1.0, 0.03 / np.maximum(residual, 1e-9))

    def length(self, event):
        return event["distance"] if self.segment == "total" else event["distance"] - 800

    @staticmethod
    def category(event, kind):
        if kind == "track_band":
            return event["track"] + ":" + str(event["distance"] // 400)
        if kind == "track_going":
            return event["track"] + ":" + event["going"]
        if kind == "track_rail":
            return event["track"] + ":" + event.get("rail", "unknown")
        return event.get(kind, "unknown")

    def vector(self, event, common_class=False):
        logd = math.log(event["distance"] / 1400)
        vector = np.zeros(len(self.index) + 3)
        vector[:3] = [1.0, logd, logd * logd]
        for kind in ("track", "going", "track_band", "track_going", "rating", "track_rail", "class"):
            if kind == "class" and common_class:
                continue
            i = self.index.get((kind, self.category(event, kind)))
            if i is not None:
                vector[i] = 1.0
        return vector

    def predict(self, event, common_class=False):
        return float(self.vector(event, common_class) @ self.beta)


def aggregate(runs, name, target_date, distance, going, lookup):
    rows = []
    for key in runs:
        if key[1] >= target_date:
            continue
        observation = lookup.get((key, name))
        if observation is None:
            continue
        days = (date.fromisoformat(target_date) - date.fromisoformat(key[1])).days
        weight = 2 ** (-days / 90) * math.exp(-abs(math.log(key[3] / distance)) / 0.25)
        if going and observation["going"] != going:
            weight *= 0.5
        rows.append((weight, observation))
        if len(rows) == 6:
            break
    output = {}
    reliability = {}
    for component in COMPONENTS:
        usable = [(w, row[component]) for w, row in rows if row[component] is not None]
        total_weight = sum(w for w, _ in usable)
        output[component] = sum(w * v for w, v in usable) / total_weight if usable else None
        reliability[component] = total_weight / (total_weight + 3)
    return output, len(rows), reliability


def zscores(values):
    observed = [v for v in values if v is not None]
    if len(observed) < 2 or statistics.pstdev(observed) == 0:
        return [0.0] * len(values)
    centre, scale = statistics.mean(observed), statistics.pstdev(observed)
    return [float(np.clip((value - centre) / scale, -3, 3)) if value is not None else 0.0 for value in values]


def default_bundle_path():
    override = os.environ.get("WC_AU_TIME_BUNDLE")
    if override:
        return Path(override)
    repo = Path(__file__).resolve().parents[6]
    marker = repo / ".wongchoi_au_data_root"
    if marker.exists():
        return Path(marker.read_text().strip()).parent / "AU_Racing_Time_Evidence" / "latest.json"
    return repo / "data" / "au_time_evidence" / "latest.json"


@lru_cache(maxsize=4)
def read_bundle(path, modified, size):
    source_path = Path(path)
    raw = gzip.decompress(source_path.read_bytes()) if source_path.suffix == ".gz" else source_path.read_bytes()
    obj = json.loads(raw)
    if obj.get("model_version") != MODEL_VERSION:
        raise ValueError("AU time bundle model version mismatch")
    raw = json.dumps(obj["events"], separators=(",", ":"), sort_keys=True).encode()
    if hashlib.sha256(raw).hexdigest() != obj.get("events_sha256"):
        raise ValueError("AU time evidence hash mismatch")
    stamp = datetime.fromisoformat(obj["captured_at"])
    if stamp.tzinfo is None:
        raise ValueError("AU time capture requires timezone")
    for event in obj["events"]:
        event["key"] = tuple(event["key"])
        for row in event["rows"]:
            row["key"] = tuple(row.get("key") or event["key"])
    return obj


@lru_cache(maxsize=4)
def full_time_lookup(path, modified, size, target_date):
    obj = read_bundle(path, modified, size)
    if target_date < obj["valid_from"]:
        return {}, 0
    return context_lookup(obj["events"], target_date)


def context_lookup(events, target_date):
    """Pure prior-date transform; caller certifies prediction availability."""
    history = [e for e in events if e["date"] < target_date]
    if len(history) < 100:
        return {}, len(history)
    model = ContextStandard(history, "total")
    days = defaultdict(list)
    for e in history:
        residual = math.log(e["total"] / e["distance"]) - model.predict(e)
        days[e["track"], e["date"]].append((e["key"], residual))
    lookup = {}
    for e in history:
        others = [r for key, r in days[e["track"], e["date"]] if key != e["key"]]
        variant = (
            float(np.clip(statistics.median(others), -0.05, 0.05)) * len(others) / (len(others) + 3)
            if len(others) >= 3
            else 0
        )
        par = model.predict(e, True) + variant
        for row in e["rows"]:
            key = (e["key"], row["horse"])
            if key in lookup:
                raise ValueError("ambiguous AU time identity")
            lookup[key] = {
                "A": -(math.log(row["time"] / row["distance"]) - par) * 1000,
                "going": e["going"],
                "time": row["time"],
                "distance": row["distance"],
                "source": row.get("source", ""),
            }
    return lookup, len(history)


def prepare_field(logic_data, facts_path, *, bundle_path=None, prediction_at=None):
    """Clear stale overlays, compute the complete field before scoring any horse."""
    previous_audit = (logic_data.get("race_analysis") or {}).get("full_time_speed") or {}
    horses = logic_data.get("horses") or {}
    for horse in horses.values():
        horse.pop("full_time_speed", None)
    race = logic_data.setdefault("race_analysis", {})
    target = str((race.get("meeting_intelligence") or {}).get("date") or race.get("date") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target):
        match = re.search(r"\d{4}-\d{2}-\d{2}", str(facts_path.parent) if facts_path is not None else "")
        target = match[0] if match else ""
    audit = {
        "model_version": MODEL_VERSION,
        "gain": FULL_TIME_SPEED_GAIN,
        "status": "missing_source",
        "target_date": target,
        "covered": 0,
        "field_size": len(horses),
    }
    race["full_time_speed"] = audit
    if not target:
        audit["status"] = "missing_target_date"
        return audit
    path = Path(bundle_path or default_bundle_path())
    if bundle_path is None and previous_audit.get("target_date") == target:
        name = previous_audit.get("bundle_file") or ""
        if name and Path(name).name == name:
            path = path.parent / name
    if not path.exists():
        if target >= FULL_TIME_START_DATE:
            raise FileNotFoundError(
                "AU full-time evidence cache unavailable; refusing to publish a silent neutral overlay"
            )
        return audit
    info = path.stat()
    obj = read_bundle(str(path), info.st_mtime_ns, info.st_size)
    prediction_at = prediction_at or datetime.now(timezone.utc)
    if prediction_at.tzinfo is None:
        raise ValueError("prediction time must be timezone-aware")
    audit["prediction_at"] = prediction_at.isoformat()
    audit["bundle_file"] = obj.get("snapshot_file") or (
        datetime.fromisoformat(obj["captured_at"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + obj["events_sha256"][:16]
        + ".json"
    )
    captured = datetime.fromisoformat(obj["captured_at"])
    audit.update(
        {"source_hash": obj["events_sha256"], "captured_at": obj["captured_at"], "valid_from": obj["valid_from"]}
    )
    if (
        captured > prediction_at
        or target < obj["valid_from"]
        or target < captured.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()
    ):
        audit["status"] = "not_available_at_prediction"
        return audit
    if facts_path is None:
        audit["status"] = "missing_or_ambiguous_formguide"
        return audit
    facts_path = Path(facts_path)
    race_number = int(race.get("race_number") or 0)
    guides = sorted(facts_path.parent.glob(f"*Race {race_number} Formguide.md"))
    if len(guides) != 1:
        audit["status"] = "missing_or_ambiguous_formguide"
        return audit
    text = guides[0].read_text(encoding="utf-8")
    headers = list(re.finditer(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$", text, re.M))
    sections = {}
    for i, h in enumerate(headers):
        name = norm(h[2])
        if name in sections:
            raise ValueError("ambiguous horse in AU time formguide")
        sections[name] = text[h.start() : headers[i + 1].start() if i + 1 < len(headers) else len(text)]
    lookup, events = full_time_lookup(str(path), info.st_mtime_ns, info.st_size, target)
    audit["prior_events"] = events
    today_going = condition_key(
        (race.get("meeting_intelligence") or {}).get("going")
        or (race.get("speed_map") or {}).get("going")
        or race.get("going")
        or ""
    )
    distance_match = re.search(r"\d{3,5}", str(race.get("distance") or ""))
    if not distance_match:
        distance_match = re.search(r"^RACE\s+\d+\s*[—–-]\s*(\d{3,5})m", text, re.M)
        distance = int(distance_match[1]) if distance_match else 0
    else:
        distance = int(distance_match[0])
    if distance <= 0:
        audit["status"] = "missing_distance"
        return audit
    details = []
    for horse in horses.values():
        name = norm(horse.get("horse_name") or "")
        runs = []
        for line in sections.get(name, "").splitlines():
            run = RUN.match(line)
            if run and not re.search(r"\*\*\(TRIAL\)\*\*|\$0\s|(?:TRIAL|TRL|JUMP.?OUT)", line, re.I):
                runs.append((normalize_venue_name(run[1]), run[3], int(run[2]), int(run[4])))
        runs = sorted(set(runs), key=lambda k: k[1], reverse=True)
        values, n, reliability = aggregate(runs, name, target, distance, today_going, lookup)
        recent = next((lookup[(k, name)] for k in runs if k[1] < target and (k, name) in lookup), None)
        detail = {
            "model_version": MODEL_VERSION,
            "raw_index_log": values["A"],
            "runs": n,
            "reliability": reliability["A"],
            "contribution": 0.0,
            "context_index": round(100 * math.exp(values["A"] / 1000), 2) if values["A"] is not None else None,
            "latest_time": recent["time"] if recent else None,
            "latest_kmh": round(3.6 * recent["distance"] / recent["time"], 2) if recent else None,
            "latest_distance": recent["distance"] if recent else None,
            "source_url": recent["source"] if recent else None,
            "source_hash": obj["events_sha256"],
            "status": "observed" if values["A"] is not None else "no_matched_formal_runs",
        }
        details.append(detail)
        horse["full_time_speed"] = detail
    for detail, z in zip(details, zscores([d["raw_index_log"] for d in details])):
        detail["contribution"] = round(FULL_TIME_SPEED_GAIN * z * detail["reliability"], 8)
    audit.update(
        {
            "status": "ready",
            "covered": sum(d["status"] == "observed" for d in details),
            "formguide_sha256": hashlib.sha256(guides[0].read_bytes()).hexdigest(),
        }
    )
    return audit


def render_detail(detail):
    if not isinstance(detail, dict) or detail.get("status") != "observed":
        return "逐駒全程資料未覆蓋，今項中性 0 分；唔代表速度較差。"
    return (
        f"情境指數 {detail['context_index']:.2f}（同情境標準＝100）；"
        f"最近逐駒全程 {detail['latest_time']:.2f} 秒／{detail['latest_distance']} 米，"
        f"平均 {detail['latest_kmh']:.2f} km/h；"
        f"採用 {detail['runs']} 仗正式賽，證據權重 {detail['reliability']:.0%}；"
        f"綜合戰力貢獻 {detail['contribution']:+.4f} 分。"
    )


def contribution(horse, race):
    audit = race.get("full_time_speed") or {}
    detail = horse.get("full_time_speed") or {}
    if audit.get("status") != "ready" or detail.get("status") != "observed":
        return 0.0
    if (
        detail.get("model_version") != MODEL_VERSION
        or not detail.get("source_hash")
        or detail.get("source_hash") != audit.get("source_hash")
    ):
        return 0.0
    if not audit.get("target_date") or audit["target_date"] < audit.get("valid_from", "9999"):
        return 0.0
    value = float(detail.get("contribution") or 0)
    if not math.isfinite(value) or abs(value) > 3 * FULL_TIME_SPEED_GAIN:
        raise ValueError("invalid AU full-time contribution")
    return value
