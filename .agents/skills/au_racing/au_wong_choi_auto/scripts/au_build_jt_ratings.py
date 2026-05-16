#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
ANALYST_RESOURCES = SCRIPT_DIR.parents[1] / "au_horse_analyst" / "resources"
AUTO_RESOURCES = SCRIPT_DIR.parent / "resources"

JOCKEY_MD = ANALYST_RESOURCES / "07_jockey_profiles.md"
TRAINER_MD = ANALYST_RESOURCES / "07b_trainer_signals.md"
ENGINE_CORE = SCRIPT_DIR / "racing_engine" / "engine_core.py"

JOCKEY_CSV = AUTO_RESOURCES / "AU_Jockey_Ratings.csv"
TRAINER_CSV = AUTO_RESOURCES / "AU_Trainer_Ratings.csv"
REPORT_MD = ARCHIVE_ROOT / "AU_JT_Profile_Gap_Report.md"

JOCKEY_ALIAS_MAP = {
    "James McDonald": "James McDonald (J-Mac)",
    "Joshua Parr": "Josh Parr",
}

TRAINER_ALIAS_MAP = {
    "Annabel & Rob Archibald": "Annabel Neasham",
    "Annabel Neasham & Rob Archibald": "Annabel Neasham",
    "Ciaron Maher": "Ciaron Maher & David Eustace",
    "Joseph Pride": "Joe Pride",
    "Michael, John & Wayne Hawkes": "Hawkes Racing",
    "Mick Price & Michael Kent Jnr": "Mick Price & Michael Kent Jr",
    "Mick Price & Michael Kent (Jnr)": "Mick Price & Michael Kent Jr",
    "Ben, Will & Jd Hayes": "Ben, Will & JD Hayes",
    "Chris & Corey Munce": "Chris Munce",
    "Peter Snowden": "Peter & Paul Snowden",
    "John O'Shea & Tom Charlton": "John O'Shea",
    "Tom Charlton": "John O'Shea",
    "Peter Moody & Katherine Coleman": "Peter G Moody & Katherine Coleman",
}

JOCKEY_SUPPLEMENTS = [
    ("Adam Hyeronimus", "T2", 66, "provisional", "Racing Australia NSW metro active rider"),
    ("Jamie Melham", "T2", 66, "provisional", "High-frequency VIC metro rider"),
    ("Chad Schofield", "T2", 65, "provisional", "Regular NSW metro rider"),
    ("Daniel Stackhouse", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Tom Sherry", "T2", 65, "provisional", "Regular NSW metro rider"),
    ("John Allen", "T2", 66, "provisional", "Nationally active metro rider"),
    ("Harry Coffey", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Jordan Childs", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Beau Mertens", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Luke Currie", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Declan Bates", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Ben Allen", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Alysha Collett", "T2", 65, "provisional", "Regular metro/provincial rider"),
    ("Jay Ford", "T2", 65, "provisional", "Regular NSW rider"),
    ("Winona Costin", "T2", 65, "provisional", "Regular NSW rider"),
    ("Lachlan Neindorf", "T2", 65, "provisional", "Regular SA metro rider"),
    ("Billy Egan", "T2", 65, "provisional", "Regular VIC metro rider"),
    ("Ashley Morgan", "T2", 65, "provisional", "Regular metro/provincial rider"),
    ("Andrew Adkins", "T2", 65, "provisional", "Regular NSW rider"),
    ("Anna Roper", "T3", 61, "provisional", "Apprentice / lighter-claim profile"),
    ("Luke Cartwright", "T3", 61, "provisional", "Developing rider"),
    ("Braith Nock", "T3", 61, "provisional", "Developing rider"),
    ("Siena Grima", "T3", 61, "provisional", "Developing rider"),
    ("Logan Bates", "T3", 61, "provisional", "Developing rider"),
    ("Molly Bourke", "T3", 61, "provisional", "Developing rider"),
    ("Reece Jones", "T3", 61, "provisional", "Developing rider"),
]

TRAINER_SUPPLEMENTS = [
    ("Ben, Will & JD Hayes", "T2", 66, "provisional", "High-volume metro barn"),
    ("Peter G Moody & Katherine Coleman", "T2", 66, "provisional", "Established VIC metro barn"),
    ("John Thompson", "T2", 65, "provisional", "Regular NSW metro trainer"),
    ("Matthew Smith", "T2", 65, "provisional", "Regular NSW metro trainer"),
    ("Grahame Begg", "T2", 65, "provisional", "Regular VIC metro trainer"),
    ("John Sargent", "T2", 64, "provisional", "Regular NSW metro trainer"),
    ("Phillip Stokes", "T2", 65, "provisional", "Regular VIC/SA metro trainer"),
    ("Trent Busuttin & Natalie Young", "T2", 64, "provisional", "Regular VIC metro trainer"),
    ("Matt Laurie", "T2", 64, "provisional", "Regular VIC metro trainer"),
    ("Nick Ryan", "T2", 64, "provisional", "Regular VIC metro trainer"),
    ("Leon & Troy Corstens & Will Larkin", "T2", 64, "provisional", "Regular VIC metro trainer"),
    ("Michael Freedman", "T2", 66, "provisional", "Regular NSW metro trainer"),
    ("Tony & Calvin McEvoy", "T2", 66, "provisional", "Regular VIC/SA metro trainer"),
    ("Richard & Will Freedman", "T2", 64, "provisional", "Regular NSW metro trainer"),
    ("Gary Portelli", "T3", 61, "provisional", "Secondary NSW metro trainer"),
    ("Gavin Bedggood", "T3", 61, "provisional", "Secondary VIC metro trainer"),
    ("Brad Widdup", "T3", 61, "provisional", "Secondary NSW metro trainer"),
    ("Nathan Doyle", "T3", 61, "provisional", "Developing metro trainer"),
    ("Matthew Dale", "T3", 61, "provisional", "Secondary NSW metro trainer"),
    ("Kerry Parker", "T3", 61, "provisional", "Secondary NSW metro trainer"),
    ("Mark Walker", "T3", 61, "provisional", "Visiting / mixed metro trainer"),
    ("Richard Litt", "T3", 61, "provisional", "Secondary NSW metro trainer"),
    ("Greg Eurell", "T3", 61, "provisional", "Secondary VIC metro trainer"),
    ("Dominic Sutton", "T3", 61, "provisional", "Developing trainer"),
    ("Robbie Griffiths", "T3", 61, "provisional", "Secondary VIC metro trainer"),
    ("Danny Williams", "T3", 61, "provisional", "Secondary NSW trainer"),
]

JOCKEY_TIER_SCORE = {"T1": 72, "T2": 66, "T3": 60}
TRAINER_TIER_SCORE = {"T1": 72, "T2": 66, "T3": 60}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_name(value: str) -> str:
    text = clean_text(value)
    text = text.replace("(J-Mac)", "").strip()
    text = text.replace(" (dw)", "")
    return text


def parse_archive_counts() -> tuple[Counter, Counter]:
    jockeys = Counter()
    trainers = Counter()
    for logic_path in ARCHIVE_ROOT.rglob("Race_*_Logic.json"):
        try:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for horse in logic.get("horses", {}).values():
            jockey = clean_text(horse.get("jockey"))
            trainer = clean_text(horse.get("trainer"))
            if jockey:
                jockeys[jockey] += 1
            if trainer:
                trainers[trainer] += 1
    return jockeys, trainers


def parse_jockey_profiles() -> list[dict]:
    lines = JOCKEY_MD.read_text(encoding="utf-8").splitlines()
    current_tier = ""
    rows: list[dict] = []
    for line in lines:
        if line.startswith("## 🥇 Tier 1"):
            current_tier = "T1"
            continue
        if line.startswith("## 🥈 Tier 2"):
            current_tier = "T2"
            continue
        match = re.match(r"^\*\*(.+?)\*\*", line)
        if not match or not current_tier:
            continue
        name = clean_text(match.group(1))
        rows.append(
            {
                "name": name,
                "canonical_name": normalize_name(name),
                "tier": current_tier,
                "base_score": JOCKEY_TIER_SCORE[current_tier],
                "confidence": "analyst_profile",
                "source": "07_jockey_profiles.md",
                "notes": "",
            }
        )
    return rows


def parse_trainer_profiles() -> list[dict]:
    text = TRAINER_MD.read_text(encoding="utf-8")
    if "## 12.B" in text:
        text = text.split("## 12.B", 1)[0]
    rows: list[dict] = []
    for line in text.splitlines():
        match = re.match(r"^\| \*\*Tier ([123]).*?\| (.+?) \|", line)
        if not match:
            continue
        tier = f"T{match.group(1)}"
        names = [clean_text(part) for part in match.group(2).split(",")]
        for name in names:
            if not name or "其他練馬師" in name or "基礎" in name:
                continue
            rows.append(
                {
                    "name": name,
                    "canonical_name": normalize_name(name),
                    "tier": tier,
                    "base_score": TRAINER_TIER_SCORE[tier],
                    "confidence": "analyst_profile",
                    "source": "07b_trainer_signals.md",
                    "notes": "",
                }
            )
    return rows


def apply_aliases(name: str, alias_map: dict[str, str]) -> str:
    normalized = normalize_name(name)
    return normalize_name(alias_map.get(normalized, normalized))


def build_rows(base_rows: list[dict], alias_map: dict[str, str], supplements: list[tuple[str, str, int, str, str]]) -> list[dict]:
    rows_by_name = {row["canonical_name"]: row for row in base_rows}
    for alias, canonical in alias_map.items():
        canonical_name = normalize_name(canonical)
        if canonical_name not in rows_by_name:
            continue
        row = dict(rows_by_name[canonical_name])
        row["name"] = normalize_name(alias)
        row["canonical_name"] = canonical_name
        row["source"] = f"{row['source']} + alias"
        row["notes"] = f"Alias of {canonical_name}"
        rows_by_name[normalize_name(alias)] = row
    for name, tier, base_score, confidence, notes in supplements:
        canonical_name = normalize_name(name)
        if canonical_name in rows_by_name:
            continue
        rows_by_name[canonical_name] = {
            "name": canonical_name,
            "canonical_name": canonical_name,
            "tier": tier,
            "base_score": base_score,
            "confidence": confidence,
            "source": "archive supplement",
            "notes": notes,
        }
    return sorted(rows_by_name.values(), key=lambda row: (row["tier"], row["name"]))


def parse_engine_tokens() -> dict[str, list[str]]:
    text = ENGINE_CORE.read_text(encoding="utf-8")
    groups = {}
    for key in ("elite_tokens", "solid_tokens", "strong_tokens"):
        match = re.search(rf"{key} = \((.*?)\)", text, re.S)
        values = []
        if match:
            values = [item.strip().strip("\"'") for item in match.group(1).split(",") if item.strip()]
        groups[key] = values
    return groups


def token_matches_name(token: str, name: str) -> bool:
    return token.lower() in normalize_name(name).lower()


def coverage_stats(counts: Counter, rows: list[dict], alias_map: dict[str, str], top_n: int = 40) -> tuple[int, int, list[tuple[str, int]]]:
    covered = set()
    for row in rows:
        covered.add(normalize_name(row["name"]))
        covered.add(normalize_name(row["canonical_name"]))
    top = counts.most_common(top_n)
    hits = sum(count for name, count in top if apply_aliases(name, alias_map) in covered)
    total = sum(count for _, count in top)
    missing = [(name, count) for name, count in top if apply_aliases(name, alias_map) not in covered]
    return hits, total, missing


def pct(part: int, total: int) -> str:
    if not total:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "canonical_name", "tier", "base_score", "confidence", "source", "notes"],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_report(
    jockey_counts: Counter,
    trainer_counts: Counter,
    jockey_rows_before: list[dict],
    trainer_rows_before: list[dict],
    jockey_rows_after: list[dict],
    trainer_rows_after: list[dict],
) -> str:
    engine_tokens = parse_engine_tokens()
    jockey_before_hits, jockey_before_total, jockey_before_missing = coverage_stats(
        jockey_counts, jockey_rows_before, JOCKEY_ALIAS_MAP
    )
    jockey_after_hits, jockey_after_total, jockey_after_missing = coverage_stats(
        jockey_counts, jockey_rows_after, JOCKEY_ALIAS_MAP
    )
    trainer_before_hits, trainer_before_total, trainer_before_missing = coverage_stats(
        trainer_counts, trainer_rows_before, TRAINER_ALIAS_MAP
    )
    trainer_after_hits, trainer_after_total, trainer_after_missing = coverage_stats(
        trainer_counts, trainer_rows_after, TRAINER_ALIAS_MAP
    )

    lines = [
        "# AU JT Profile Gap Report",
        "",
        "## Summary",
        "",
        f"- Jockey archive uniques: **{len(jockey_counts)}**",
        f"- Trainer archive uniques: **{len(trainer_counts)}**",
        f"- Jockey Top40 coverage before supplement: **{jockey_before_hits}/{jockey_before_total} = {pct(jockey_before_hits, jockey_before_total)}**",
        f"- Jockey Top40 coverage after supplement: **{jockey_after_hits}/{jockey_after_total} = {pct(jockey_after_hits, jockey_after_total)}**",
        f"- Trainer Top40 coverage before supplement: **{trainer_before_hits}/{trainer_before_total} = {pct(trainer_before_hits, trainer_before_total)}**",
        f"- Trainer Top40 coverage after supplement: **{trainer_after_hits}/{trainer_after_total} = {pct(trainer_after_hits, trainer_after_total)}**",
        "",
        "## Current Engine Mismatches",
        "",
        "- `James McDonald` 目前喺 engine 只係 generic elite token；AU analyst 則明確係 Tier 1 王者級。",
        "- `Zac Lloyd` 目前喺 engine 同 elite token 同級處理，但 AU analyst 將佢放喺 Tier 2 新星。",
        "- `Tim Clark`、`Jason Collett`、`Tyler Schiller` 目前都被 engine 當成 elite token，但 analyst 層級都係 Tier 2。",
        "- `Jamie Melham`、`Adam Hyeronimus`、`Chad Schofield` 呢批 archive 高頻名字，原 analyst profile 未完整覆蓋，需要補齊。",
        "",
        "## Engine Token Snapshot",
        "",
        f"- `elite_tokens`: {', '.join(engine_tokens['elite_tokens'])}",
        f"- `solid_tokens`: {', '.join(engine_tokens['solid_tokens'])}",
        f"- `strong_tokens`: {', '.join(engine_tokens['strong_tokens'])}",
        "",
        "## Top Missing Jockeys Before Supplement",
        "",
    ]

    for name, count in jockey_before_missing[:15]:
        lines.append(f"- {name}: {count}")

    lines.extend(
        [
            "",
            "## Top Missing Trainers Before Supplement",
            "",
        ]
    )
    for name, count in trainer_before_missing[:15]:
        lines.append(f"- {name}: {count}")

    lines.extend(
        [
            "",
            "## Remaining Top Missing Jockeys After Supplement",
            "",
        ]
    )
    for name, count in jockey_after_missing[:15]:
        lines.append(f"- {name}: {count}")

    lines.extend(
        [
            "",
            "## Remaining Top Missing Trainers After Supplement",
            "",
        ]
    )
    for name, count in trainer_after_missing[:15]:
        lines.append(f"- {name}: {count}")

    return "\n".join(lines) + "\n"


def main() -> None:
    jockey_counts, trainer_counts = parse_archive_counts()
    jockey_rows_before = parse_jockey_profiles()
    trainer_rows_before = parse_trainer_profiles()
    jockey_rows_after = build_rows(jockey_rows_before, JOCKEY_ALIAS_MAP, JOCKEY_SUPPLEMENTS)
    trainer_rows_after = build_rows(trainer_rows_before, TRAINER_ALIAS_MAP, TRAINER_SUPPLEMENTS)

    write_csv(JOCKEY_CSV, jockey_rows_after)
    write_csv(TRAINER_CSV, trainer_rows_after)
    REPORT_MD.write_text(
        build_report(
            jockey_counts,
            trainer_counts,
            jockey_rows_before,
            trainer_rows_before,
            jockey_rows_after,
            trainer_rows_after,
        ),
        encoding="utf-8",
    )
    print(f"Saved: {JOCKEY_CSV}")
    print(f"Saved: {TRAINER_CSV}")
    print(f"Saved: {REPORT_MD}")


if __name__ == "__main__":
    main()
