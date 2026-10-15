#!/usr/bin/env python3
"""Contextual measured GPS speed: prior-only benchmarks, total-L800, OOS fits."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time
from zipfile import ZipFile
from io import BytesIO
import xml.etree.ElementTree as ET

import numpy as np

from au_measured_runner_time_20261015 import (  # noqa: E402
    BASE,
    condition_key,
    get,
    parse_csv,
    seconds,
)
from au_result_identity import normalize_venue_name  # noqa: E402
from au_unused_field_power import RE_HDR_DIST, RE_RUNNER, norm  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402

COMPONENTS = ("A", "B", "C")
ARMS = ("A", "B", "C", "AB", "AC", "ABC")
GAIN_GRID = (0.0, 0.25, 0.5, 1.0, 2.0)
RUN = re.compile(r"^(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\S+)")


def fetch(cache, prior):
    cache.mkdir(parents=True, exist_ok=True)
    index = (prior / "index.html").read_bytes()
    (cache / "index.html").write_bytes(index)
    links = sorted(set(re.findall(r'href="([^"]+\.csv)"', index.decode())))
    links = [
        link for link in links if (match := re.search(r"/(\d{8})_", link)) and "20250101" <= match[1] <= "20261014"
    ]

    def download(link):
        name = link.split("/")[-1]
        path = cache / name
        if not path.exists():
            old = prior / name
            path.write_bytes(old.read_bytes() if old.exists() else get(BASE + link))
            if not old.exists():
                time.sleep(0.2)
        raw = path.read_bytes()
        if not raw.lstrip().startswith(b"Date,RaceNumber,"):
            raise ValueError("bad source CSV " + name)
        return {"url": BASE + link, "file": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for record in pool.map(download, links):
            records.append(record)
            if len(records) % 50 == 0:
                print("sources", len(records), flush=True)
    (cache / "manifest.json").write_text(json.dumps(records, indent=2))
    print("complete sources", len(records), sum(r["bytes"] for r in records), flush=True)


def fetch_xml(cache):
    records = json.loads((cache / "manifest.json").read_text())
    linked = set(re.findall(r'href="([^"]+\.zip)"', (cache / "index.html").read_text()))

    def download(record):
        name = record["file"].replace(".csv", ".zip")
        path = cache / name
        url = record["url"].replace(".csv", ".zip")
        if url.split(BASE, 1)[1] not in linked:
            return {
                "file": name,
                "url": url,
                "status": "not_published_in_official_index",
                "csv_file": record["file"],
                "csv_url": record["url"],
            }
        if not path.exists():
            path.write_bytes(get(url))
            time.sleep(0.2)
        raw = path.read_bytes()
        with ZipFile(BytesIO(raw)) as archive:
            assert all(name.lower().endswith(".xml") for name in archive.namelist())
        return {"file": name, "url": url, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    result = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for record in pool.map(download, records):
            result.append(record)
            if len(result) % 50 == 0:
                print("XML sources", len(result), flush=True)
    (cache / "xml_manifest.json").write_text(json.dumps(result, indent=2))
    print("complete XML", len(result), sum(r.get("bytes", 0) for r in result), flush=True)


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


def load_xml_sources(cache, metadata):
    records = json.loads((cache / "xml_manifest.json").read_text())
    events = {}
    quality = Counter()
    for record in records:
        if record.get("status") == "not_published_in_official_index":
            quality["csv_only_meetings"] += 1
            rows, _ = source_rows((cache / record["csv_file"]).read_text(encoding="utf-8-sig"), record["csv_url"])
            grouped = defaultdict(list)
            for row in rows:
                key = (row["track"], row["date"], row["race"], row["distance"])
                grouped[key].append(row)
            for key, rows in grouped.items():
                quality["source_races"] += 1
                if len(rows) < 3:
                    quality["incomplete_or_trial_races"] += 1
                    continue
                fields = metadata.get(key, {"going": "unknown", "class": "unknown"})
                events[key] = {
                    "key": key,
                    "track": key[0],
                    "date": key[1],
                    "distance": key[3],
                    **fields,
                    "rating": "unknown",
                    "rail": "unknown",
                    "rows": rows,
                    "total": statistics.median(r["time"] for r in rows),
                    "early": statistics.median(r["early"] for r in rows),
                }
                quality["valid_runners"] += len(rows)
            continue
        raw = (cache / record["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
        with ZipFile(BytesIO(raw)) as archive:
            for name in archive.namelist():
                quality["source_races"] += 1
                event = parse_xml(archive.read(name), record["url"] + "#" + name)
                if event is None:
                    quality["incomplete_or_trial_races"] += 1
                    continue
                if event["key"] in events:
                    raise ValueError("duplicate official event")
                events[event["key"]] = event
                quality["valid_runners"] += len(event["rows"])
                quality["exact_rating_events"] += event["rating"] != "unknown"
    quality["valid_events"] = len(events)
    quality["source_meetings"] = len(records)
    return sorted(events.values(), key=lambda event: event["date"]), quality


def load_form(root):
    blocks, metadata = {}, defaultdict(lambda: {"going": set(), "class": set()})
    source_hashes = []
    for meeting in meeting_dirs(root):
        for path in sorted(meeting.glob("*Formguide.md")):
            raw = path.read_bytes()
            source_hashes.append((str(path), hashlib.sha256(raw).hexdigest()))
            text = raw.decode("utf-8", errors="replace")
            header = RE_HDR_DIST.search(text)
            matches = list(RE_RUNNER.finditer(text))
            for i, match in enumerate(matches):
                block = text[match.start() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
                runs = []
                for line in block.splitlines():
                    run = RUN.match(line)
                    if run is None or re.search(r"\*\*\(TRIAL\)\*\*|\$0\s|(?:TRIAL|TRL|JUMP.?OUT)", line, re.I):
                        continue
                    key = (normalize_venue_name(run[1]), run[3], int(run[2]), int(run[4]))
                    going = condition_key(run[5])
                    metadata[key]["going"].add(going)
                    category = class_key(line)
                    if category != "unknown":
                        metadata[key]["class"].add(category)
                    runs.append(key)
                if header:
                    blocks[(meeting.name, int(header[1]), norm(match[2]))] = sorted(
                        set(runs), key=lambda k: k[1], reverse=True
                    )
    resolved = {}
    for key, fields in metadata.items():
        if len(fields["going"]) == 1:
            resolved[key] = {
                "going": next(iter(fields["going"])),
                "class": next(iter(fields["class"])) if len(fields["class"]) == 1 else "unknown",
            }
    return blocks, resolved, source_hashes


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


def track_variants(events, total, early):
    residuals = defaultdict(list)
    for event in events:
        pair = (
            math.log(event["total"] / event["distance"]) - total.predict(event),
            math.log(event["early"] / (event["distance"] - 800)) - early.predict(event),
        )
        residuals[(event["track"], event["date"])].append((event["key"], pair))
    variants = {}
    for members in residuals.values():
        for key, _ in members:
            others = [pair for other, pair in members if other != key]
            variants[key] = tuple(
                float(np.clip(statistics.median(pair[j] for pair in others), -0.05, 0.05))
                * len(others)
                / (len(others) + 3)
                if len(others) >= 3
                else 0.0
                for j in (0, 1)
            )
    return variants


def tempo_coefficients(events, total, early, variants):
    by_horse = defaultdict(list)
    for event in events:
        vt, ve = variants[event["key"]]
        pace = float(
            np.clip(-(math.log(event["early"] / (event["distance"] - 800)) - early.predict(event) - ve) / 0.03, -3, 3)
        )
        predicted_total = total.predict(event)
        for row in event["rows"]:
            y = -(math.log(row["time"] / row["distance"]) - predicted_total - vt) * 1000
            by_horse[row["horse"]].append((pace, pace * pace, y))
    centred = []
    for rows in by_horse.values():
        if len(rows) >= 2:
            matrix = np.array(rows)
            centred.extend(matrix - matrix.mean(axis=0))
    if len(centred) < 100:
        return np.zeros(2), len(centred)
    matrix = np.array(centred)
    return np.linalg.solve(matrix[:, :2].T @ matrix[:, :2] + 100 * np.eye(2), matrix[:, :2].T @ matrix[:, 2]), len(
        centred
    )


def date_features(events, target_date):
    history = [event for event in events if event["date"] < target_date]
    if len(history) < 100:
        return {}, {"events": len(history), "ready": False}
    total, early = ContextStandard(history, "total"), ContextStandard(history, "early")
    variants = track_variants(history, total, early)
    beta, repeats = tempo_coefficients(history, total, early, variants)
    lookup = {}
    for event in history:
        vt, ve = variants[event["key"]]
        fieldpace = float(
            np.clip(-(math.log(event["early"] / (event["distance"] - 800)) - early.predict(event) - ve) / 0.03, -3, 3)
        )
        correction = -float(beta @ np.array([fieldpace, fieldpace * fieldpace]))
        total_par = total.predict(event, True)
        early_par = early.predict(event, True)
        for row in event["rows"]:
            lookup[(event["key"], row["horse"])] = {
                "A": -(math.log(row["time"] / row["distance"]) - total_par - vt) * 1000,
                "B": -(math.log(row["early"] / (row["distance"] - 800)) - early_par - ve) * 1000,
                "C": correction if repeats >= 100 else None,
                "going": event["going"],
            }
    return lookup, {
        "events": len(history),
        "ready": True,
        "repeat_observations": repeats,
        "tempo_beta": beta.tolist(),
        "variant_nonzero": sum(any(v) for v in variants.values()),
    }


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


def build(args):
    blocks, metadata, hashes = load_form(args.root)
    events, quality = load_xml_sources(args.cache, metadata)
    races = json.loads(args.baseline.read_text())["races"]
    races = [
        race
        for race in races
        if "2026-08-05" <= race["date"] <= "2026-10-14"
        and sum(row["pos"] <= 3 for row in race["rows"]) >= 3
        and any(row["pos"] == 1 for row in race["rows"])
    ]
    grouped = defaultdict(list)
    for race in races:
        grouped[race["date"]].append(race)
    states = []
    for target_date, daily in sorted(grouped.items()):
        lookup, state = date_features(events, target_date)
        states.append({"date": target_date, **state})
        for race in daily:
            race["rows"].sort(key=lambda row: row["n"])
            for row in race["rows"]:
                distance = int(re.search(r"\d+", str(row["distance"]))[0])
                going = condition_key(row.get("going") or "")
                row["context_speed"], row["gps_runs"], row["gps_reliability"] = aggregate(
                    blocks.get((race["meeting"], race["race"], norm(row["name"])), []),
                    norm(row["name"]),
                    target_date,
                    distance,
                    going,
                    lookup,
                )
            for component in COMPONENTS:
                for row, z in zip(race["rows"], zscores([row["context_speed"][component] for row in race["rows"]])):
                    # Shrink AFTER race z-scoring; otherwise a uniformly sparse
                    # field would have its low-confidence scale inflated back.
                    row["context_speed"][component + "_z"] = z * row["gps_reliability"][component]
            for row in race["rows"]:
                for arm in ARMS:
                    row[arm] = statistics.mean(row["context_speed"][c + "_z"] for c in arm)
        print("features", target_date, state["events"], flush=True)
    args.out.write_text(
        json.dumps(
            {
                "races": races,
                "states": states,
                "source_quality": quality,
                "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                "form_manifest_sha256": hashlib.sha256(json.dumps(hashes).encode()).hexdigest(),
                "source_manifest_sha256": hashlib.sha256((args.cache / "xml_manifest.json").read_bytes()).hexdigest(),
            }
        )
    )


def diagnostic_features(races):
    from au_leaf_power import within_race_auc

    report = {}
    for component in COMPONENTS:
        concordant = comparable = covered = races_compared = 0
        by_date = defaultdict(lambda: np.zeros(2))
        signal_concordant = signal_comparable = 0
        xs, ps, fs, qs = [], [], [], []
        for race in races:
            rows = [row for row in race["rows"] if row["context_speed"][component] is not None]
            covered += len(rows)
            c, n = within_race_auc([(row["context_speed"][component], row["pos"] <= 3) for row in rows])
            concordant += c
            comparable += n
            races_compared += bool(n)
            by_date[race["date"]] += [c, n]
            sc, sn = within_race_auc([(row["context_speed"][component + "_z"], row["pos"] <= 3) for row in rows])
            signal_concordant += sc
            signal_comparable += sn
            if len(rows) >= 2:
                xs.extend(zscores([row["context_speed"][component] for row in rows]))
                ps.extend(zscores([row["features"]["pace_figure_score"] for row in rows]))
                fs.extend(zscores([row["features"]["form_score"] for row in rows]))
                qs.extend(zscores([row["features"]["performance_quality_score"] for row in rows]))
        daily = np.array(list(by_date.values()))
        chosen = np.random.default_rng(7).integers(0, len(daily), (2000, len(daily)))
        sampled = daily[chosen].sum(axis=1)
        boot = sampled[:, 0] / np.maximum(sampled[:, 1], 1)
        report[component] = {
            "covered": covered,
            "comparable_races": races_compared,
            "within_race_auc_pair_weighted": concordant / comparable if comparable else None,
            "within_race_auc_date_ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
            "confidence_shrunk_signal_auc": signal_concordant / signal_comparable if signal_comparable else None,
            "pearson_within_race_z": {
                name: float(np.corrcoef(xs, values)[0, 1]) for name, values in (("pace", ps), ("form", fs), ("PQ", qs))
            },
        }
    return report


def fit_gain(races, arm):
    from au_trial_cutoff_refit_20261015 import metric_table

    rows = [row for race in races for row in race["rows"]]
    base = np.array([row["ability"] for row in rows])
    signal = np.array([row[arm] for row in rows])
    scores = np.array([np.round(base + gain * signal, 4) for gain in GAIN_GRID])
    metrics = metric_table(races, scores)
    means = metrics.mean(axis=1)
    fold_dates = np.array_split(sorted({r["date"] for r in races}), 5)
    fold_wins = np.zeros(len(GAIN_GRID), dtype=int)
    for dates in fold_dates:
        indices = [i for i, race in enumerate(races) if race["date"] in dates]
        value = metrics[:, indices, :].mean(axis=(1, 2))
        fold_wins += value >= value[0]
    eligible = (means[:, 0] >= means[0, 0]) & (means[:, 1] >= means[0, 1]) & (fold_wins >= 4)
    qualified = [gain for i, gain in enumerate(GAIN_GRID) if gain > 0 and eligible[i]]
    return (statistics.median(qualified) if qualified else 0.0), {
        "qualified_gains": qualified,
        "training_races": len(races),
        "train_through": max(r["date"] for r in races),
        "fold_wins": fold_wins.tolist(),
    }


def effects(races, baseline_key, candidate_key):
    from au_eval import _counts, _counts_by_field, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record

    bm = _stage4_metric_rows(races, lambda row: row[baseline_key])
    cm = _stage4_metric_rows(races, lambda row: row[candidate_key])
    names = (
        "gold",
        "good_positional",
        "top3_capture_at5",
        "mean_top3_model_rank",
        "competitive_recall_at5",
        "ndcg_at5",
        "top5_pairwise_auc",
    )
    evidence = {}
    days = sorted({r["date"] for r in races})
    indices = {d: [i for i, r in enumerate(races) if r["date"] == d] for d in days}
    rng = np.random.default_rng(7)
    chosen = rng.integers(0, len(days), (2000, len(days)))
    for name in names:
        deltas = np.array(
            [
                float(c[name]) - float(b[name]) if c.get(name) is not None and b.get(name) is not None else np.nan
                for b, c in zip(bm, cm)
            ]
        )
        sums = np.array([np.nansum(deltas[indices[d]]) for d in days])
        counts = np.array([sum(np.isfinite(deltas[indices[d]])) for d in days])
        boot = sums[chosen].sum(axis=1) / np.maximum(1, counts[chosen].sum(axis=1))
        evidence[name] = {
            "delta": float(np.nanmean(deltas)),
            "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
            "p_two_sided": float(min(1.0, 2 * min(np.mean(boot <= 0), np.mean(boot >= 0)))),
            "six_blocks": [
                float(np.nanmean([deltas[i] for d in chunk for i in indices[d]])) for chunk in np.array_split(days, 6)
            ],
        }
    cohorts = {}
    for cohort, keyer in (
        ("going", lambda r: condition_key(r["rows"][0].get("going") or "unknown")),
        ("venue", lambda r: re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", r["meeting"]).split(" Race ")[0]),
        (
            "distance",
            lambda r: (
                "sprint"
                if int(re.search(r"\d+", str(r["rows"][0]["distance"]))[0]) <= 1300
                else ("mile" if int(re.search(r"\d+", str(r["rows"][0]["distance"]))[0]) <= 1700 else "staying")
            ),
        ),
        (
            "career",
            lambda r: (
                "has_0to5"
                if any(row.get("career_starts") is not None and row["career_starts"] < 6 for row in r["rows"])
                else "all_6plus_or_unknown"
            ),
        ),
    ):
        groups = defaultdict(list)
        for race in races:
            groups[str(keyer(race))].append(race)
        cohorts[cohort] = {
            key: {
                "races": len(subset),
                "baseline": _counts(subset, lambda row: row[baseline_key]),
                "candidate": _counts(subset, lambda row: row[candidate_key]),
            }
            for key, subset in groups.items()
        }
    return {
        "races": len(races),
        "days": len(days),
        "baseline": _counts(races, lambda row: row[baseline_key]),
        "candidate": _counts(races, lambda row: row[candidate_key]),
        "evidence": evidence,
        "field_buckets": {
            "baseline": _counts_by_field(races, lambda row: row[baseline_key]),
            "candidate": _counts_by_field(races, lambda row: row[candidate_key]),
        },
        "cohorts": cohorts,
        "decision": evaluate_full_record(
            domain="au",
            mode="walk_forward_oos",
            dates=[r["date"] for r in races],
            baseline_rows=bm,
            candidate_rows=cm,
            leakage_audit_passed=False,
        ),
    }


def evaluate(args):
    from au_eval import _counts, default_scorer
    from au_trial_cutoff_refit_20261015 import metric_table
    from model_evaluation_decision import holm_adjust

    obj = json.loads(args.features.read_text())
    races = obj["races"]
    rows = [row for race in races for row in race["rows"]]
    assert max(abs(default_scorer(row) - row["ability"]) for row in rows) < 0.00011
    base = np.array([row["ability"] for row in rows])
    fast = metric_table(races, base[None, :])[0].mean(axis=0) * 100
    canonical = _counts(races, lambda row: row["ability"])
    assert np.max(np.abs(fast - np.array([canonical[k] for k in ("gold", "good_positional", "pass", "t3prec")]))) < 1e-8
    dates = sorted({r["date"] for r in races})
    oos, windows = [], []
    for start in range(30, len(dates), 7):
        test = set(dates[start : start + 7])
        train = [r for r in races if r["date"] < dates[start]]
        daily = [r for r in races if r["date"] in test]
        state = {"test_dates": sorted(test), "fits": {}}
        for arm in ARMS:
            gain, metadata = fit_gain(train, arm)
            state["fits"][arm] = {"gain": gain, **metadata}
            assert metadata["train_through"] < min(test)
            for race in daily:
                for row in race["rows"]:
                    row["candidate_" + arm] = round(row["ability"] + gain * row[arm], 4)
        windows.append(state)
        oos.extend(daily)
        print("OOS", sorted(test), "gains", {a: state["fits"][a]["gain"] for a in ARMS}, flush=True)
    report = {
        "baseline_commit": "7a962be562ecb0af461daa71114b1dddf66ec8cd",
        "baseline_sha256": obj["baseline_sha256"],
        "features_sha256": hashlib.sha256(args.features.read_bytes()).hexdigest(),
        "source_manifest_sha256": obj["source_manifest_sha256"],
        "source_quality": obj["source_quality"],
        "feature_diagnostics_all": diagnostic_features(races),
        "feature_diagnostics_oos": diagnostic_features(oos),
        "windows": windows,
        "comparisons": {arm: effects(oos, "ability", "candidate_" + arm) for arm in ARMS},
        "ablations": {
            pair: effects(oos, "candidate_" + pair.split(":")[0], "candidate_" + pair.split(":")[1])
            for pair in ("A:AB", "A:AC", "AB:ABC", "AC:ABC")
        },
        "source_availability": "FLAG: historical publication/capture not certified",
        "promotion_authorized": False,
        "first_oos": min(r["date"] for r in oos),
        "last_oos": max(r["date"] for r in oos),
    }
    report["family_holm_primary_p"] = holm_adjust(
        {
            arm + ":" + metric: report["comparisons"][arm]["evidence"][metric]["p_two_sided"]
            for arm in ARMS
            for metric in ("gold", "good_positional")
        }
    )
    report["a_a"] = effects(oos, "ability", "ability")
    assert report["a_a"]["baseline"] == report["a_a"]["candidate"]
    assert all(v["delta"] == 0 for v in report["a_a"]["evidence"].values())
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    args.out.with_suffix(".predictions.json").write_text(json.dumps({"races": oos, "states": obj["states"]}))
    print("saved", args.out, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "fetch-xml", "build", "evaluate"))
    for flag in ("cache", "prior", "root", "baseline", "out", "features"):
        parser.add_argument("--" + flag, type=Path)
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(args.cache, args.prior)
    elif args.command == "fetch-xml":
        fetch_xml(args.cache)
    elif args.command == "build":
        build(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
