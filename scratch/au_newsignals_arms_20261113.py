#!/usr/bin/env python3
"""EXP-20261113-23：騎練情境率（J1–J4）、長途段速（S1／S2）、短直路前置（L1–L3）—— 喺 BASE dump 離線砌 arm 再判決。

    au_newsignals_arms_20261113.py BASE.json OUTDIR

騎練情境率要由 Logic 攞騎師／練馬師名同 LY，再對 point-in-time 快照（captured_at 日期 < 賽日）。
LY 分離線重算同 dump 差 ≥ 0.01 嘅馬唔郁（即係唔係行 LY 統一率嗰條路）。
"""
import ast
import collections
import copy
import glob
import html
import json
import os
import re
import statistics
import subprocess
import sys
import unicodedata
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W / "scratch"))
import au_noise_judge_20261113 as nj  # noqa: E402  (ability() 同 judge 路徑)

ROOT = open(W / ".wongchoi_au_data_root").read().strip()
GEOM = json.load(open(W / ".agents/skills/au_racing/au_wong_choi_auto/resources/au_track_geometry.json"))["venues"]
K = 100.0
J_PRIOR, J_SPREAD = 0.1271, 247.0
P_PRIOR = {"jockey": 0.3564, "trainer": 0.3673}
P_SPREAD = 140.0


def norm(s):
    s = unicodedata.normalize("NFKD", html.unescape(str(s or ""))).lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def ly_rate(kind, ly):
    rides = float(ly.get("rides") or 0)
    if kind == "jockey" and ly.get("wins") is not None:
        return (float(ly["wins"]) + 20 * J_PRIOR) / (rides + 20), "win"
    return (float(ly.get("places") or 0) + 20 * P_PRIOR[kind]) / (rides + 20), "place"


def to_score(kind, r, basis):
    if basis == "win":
        return max(0.0, min(100.0, 60 + J_SPREAD * (r - J_PRIOR)))
    return max(0.0, min(100.0, 60 + P_SPREAD * (r - P_PRIOR[kind])))


def load_people():
    cache = json.load(open(ROOT + "/AU_Sportsbet_People_Cache.json"))
    ids = {}
    for key, rec in cache.items():
        ids[(rec.get("kind"), norm(rec.get("name")))] = rec.get("id")
    snaps = collections.defaultdict(list)
    for line in open(ROOT + "/AU_Sportsbet_People_Snapshots.jsonl"):
        r = json.loads(line)
        snaps[(r["kind"], str(r["id"]))].append((r["captured_at"][:10], r))
    for v in snaps.values():
        v.sort(key=lambda t: t[0])
    return ids, snaps


def pit(snaps, kind, pid, date):
    best = None
    for d, r in snaps.get((kind, str(pid)), ()):
        if d < date:
            best = r
        else:
            break
    return best


def going_bucket(g):
    g = str(g or "").lower()
    if "heavy" in g:
        return "Heavy"
    if "soft" in g:
        return "Soft"
    if "good" in g or "firm" in g:
        return "Good"
    return None


def dist_bucket(d):
    try:
        d = float(str(d).rstrip("m"))
    except (TypeError, ValueError):
        return None
    for hi, lab in ((1000, "0 - 1000m"), (1300, "1001m - 1300m"), (1500, "1301m - 1500m"),
                    (2000, "1501m - 2000m"), (2400, "2001m - 2400m")):
        if d <= hi:
            return lab
    return None


SPELL = {"first_up": "First Up", "second_up": "Second Up", "third_up": "Third Up"}


def ctx_counts(snap, arm, row, basis):
    """→ (hits, starts) 或 None。"""
    if snap is None:
        return None
    if arm == "J1":
        cell = (snap.get("stats") or {}).get("Last 100")
    else:
        table = {"J2": "Track Conditions", "J3": "Distance", "J4": "Spells"}[arm]
        key = {"J2": going_bucket(row.get("going")), "J3": dist_bucket(row.get("distance")),
               "J4": SPELL.get(row.get("prep_stage"))}[arm]
        if key is None:
            return None
        cell = (((snap.get("contextual_stats") or {}).get(table) or {}).get("Last 12 Months") or {}).get(key)
    if not cell or not cell.get("starts"):
        return None
    hits = cell.get("1st", 0) if basis == "win" else cell.get("1st", 0) + cell.get("2nd", 0) + cell.get("3rd", 0)
    return float(hits), float(cell["starts"])


def logic_people(meeting, race):
    dirs = glob.glob(f"{ROOT}/{meeting}") + glob.glob(f"{ROOT}/Archive/{meeting}")
    if not dirs:
        return {}
    p = Path(dirs[0]) / f"Race_{race}_Logic.json"
    if not p.exists():
        return {}
    out = {}
    for h in (json.load(open(p)).get("horses") or {}).values():
        d = h.get("_data") or {}
        rec = {}
        for kind in ("jockey", "trainer"):
            raw = d.get(f"{kind}_ly")
            try:
                ly = raw if isinstance(raw, dict) else ast.literal_eval(raw) if raw else None
            except (ValueError, SyntaxError):
                ly = None
            rec[kind] = (h.get(kind), ly)
        out[norm(h.get("horse_name"))] = rec
    return out


def venue_of(meeting):
    v = re.sub(r"^\d{4}-\d{2}-\d{2}[\s_]*", "", meeting).split(" Race")[0].split("_Race")[0]
    return v.strip()


def geom(venue):
    v = norm(venue)
    for key, g in GEOM.items():
        if norm(key) == v or norm(g.get("venue")) == v:
            return g
    return None


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    races = data["races"]
    ids, snaps = load_people()

    # 短直路門檻：判決窗場次嘅直路中位數（只用幾何）
    lens = [g["straight_m"] for r in races if r["date"] >= "2026-08-05"
            for g in [geom(venue_of(r["meeting"]))] if g and g.get("straight_m")]
    short = statistics.median(lens)
    print(f"short straight threshold (median of races) = {short} m; races with geometry {len(lens)}")

    stats = collections.Counter()
    people_cache = {}
    new_scores = {a: {} for a in ("J1", "J2", "J3", "J4")}
    for ri, race in enumerate(races):
        if race["date"] < "2026-08-05":
            continue
        lp = people_cache.setdefault((race["meeting"], race["race"]), logic_people(race["meeting"], race["race"]))
        for xi, row in enumerate(race["rows"]):
            rec = lp.get(norm(row["name"]))
            if not rec:
                stats["no_logic"] += 1
                continue
            for kind, leaf in (("jockey", "jockey_score"), ("trainer", "trainer_score")):
                name, ly = rec[kind]
                if not ly or float(ly.get("rides") or 0) < 10:
                    continue
                r_ly, basis = ly_rate(kind, ly)
                if abs(to_score(kind, r_ly, basis) - row["features"][leaf]) >= 0.01:
                    stats[f"{kind}_replica_mismatch"] += 1
                    continue
                stats[f"{kind}_ly_path"] += 1
                pid = ids.get((kind, norm(name)))
                snap = pit(snaps, kind, pid, race["date"]) if pid else None
                if snap is None:
                    stats[f"{kind}_no_pit_snapshot"] += 1
                    continue
                for arm in ("J1", "J2", "J3", "J4"):
                    if arm == "J4" and kind != "trainer":
                        continue
                    c = ctx_counts(snap, arm, row, basis)
                    if c is None:
                        continue
                    hits, starts = c
                    r = (hits + K * r_ly) / (starts + K)
                    new_scores[arm][(ri, xi, leaf)] = to_score(kind, r, basis)
                    stats[f"{arm}_{kind}_changed"] += 1
    print(json.dumps(stats, ensure_ascii=False, indent=0))

    def build(arm):
        d = copy.deepcopy(data)
        for ri, race in enumerate(d["races"]):
            g = geom(venue_of(race["meeting"]))
            is_short = bool(g and g.get("straight_m") and g["straight_m"] < short)
            try:
                dist = float(str(race["rows"][0].get("distance")).rstrip("m"))
            except (TypeError, ValueError):
                dist = None
            for xi, row in enumerate(race["rows"]):
                f = dict(row["features"])
                bonus = 0.0
                if arm in new_scores:
                    for leaf in ("jockey_score", "trainer_score"):
                        if (ri, xi, leaf) in new_scores[arm]:
                            f[leaf] = new_scores[arm][(ri, xi, leaf)]
                elif arm in ("S1", "S2"):
                    sec = f.get("sectional_score", 60.0)
                    if dist and dist > 1600 and abs(sec - 60.0) > 1e-9:
                        f["pace_figure_score"] = sec if arm == "S1" else 0.5 * (sec + f["pace_figure_score"])
                elif arm in ("L1", "L2", "L3"):
                    style = str(row.get("style") or "")
                    front = ("前領" in style) if arm == "L3" else ("前領" in style or "跟前" in style)
                    if is_short and front:
                        bonus = {"L1": 1.0, "L2": 2.0, "L3": 2.0}[arm]
                row["ability"] = nj.ability(row, f) + bonus
        return d

    for arm in ("J1", "J2", "J3", "J4", "S1", "S2", "L1", "L2", "L3"):
        p = out / f"{arm}.json"
        p.write_text(json.dumps(build(arm)))
        subprocess.run([sys.executable, str(W / "scratch/au_track_rebuild_judge_20261102.py"),
                        str(base_path), str(p), str(out / f"{arm}.verdict.json")], check=True)
        p.unlink()


if __name__ == "__main__":
    main()
