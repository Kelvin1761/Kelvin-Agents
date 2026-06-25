import csv
import json
import collections
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
CSV_PATH = str(AU_RACING / "AU_Historical_Raw_Race_Results.csv")
OUTPUT_JSON = str(Path(__file__).resolve().parent / "au_draw_bias_matrix.json")

def get_bucket(barrier):
    if barrier <= 4:
        return "inside"
    elif barrier <= 8:
        return "middle"
    elif barrier <= 12:
        return "outside"
    else:
        return "wide"

def parse_pos(pos_str):
    pos_str = str(pos_str).strip()
    match = re.search(r'\d+', pos_str)
    if match:
        return int(match.group())
    return 99

def compute_rates(bucket_counts, bucket_wins, bucket_places):
    result = {}
    for b in ["inside", "middle", "outside", "wide"]:
        total = bucket_counts.get(b, 0)
        wins = bucket_wins.get(b, 0)
        places = bucket_places.get(b, 0)
        if total > 0:
            result[b] = {
                "win_rate": round(wins / total, 3),
                "place_rate": round(places / total, 3),
                "sample_size": total
            }
        else:
            result[b] = {
                "win_rate": 0.0,
                "place_rate": 0.0,
                "sample_size": 0
            }
    return result

def main():
    if not Path(CSV_PATH).exists():
        print(f"Error: {CSV_PATH} not found.")
        return

    # 1. Read all rows and determine field sizes
    races = collections.defaultdict(list)
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("Date", "").strip()
            track = row.get("Track", "").strip().title()
            race_num = row.get("Race", "").strip()
            distance = row.get("Distance", "").strip()
            barrier_str = row.get("Barrier", "").strip()
            pos_str = row.get("Pos", "").strip()

            if not barrier_str.isdigit():
                continue
            barrier = int(barrier_str)
            if barrier <= 0:
                continue

            pos = parse_pos(pos_str)
            race_id = f"{date}_{track}_{race_num}"
            races[race_id].append({
                "track": track,
                "distance": distance,
                "barrier": barrier,
                "pos": pos
            })

    # 2. Accumulate stats
    # global_stats: field_size_category -> bucket -> stats
    global_counts = collections.defaultdict(lambda: collections.defaultdict(int))
    global_wins = collections.defaultdict(lambda: collections.defaultdict(int))
    global_places = collections.defaultdict(lambda: collections.defaultdict(int))

    # track_stats: track -> bucket -> stats
    track_counts = collections.defaultdict(lambda: collections.defaultdict(int))
    track_wins = collections.defaultdict(lambda: collections.defaultdict(int))
    track_places = collections.defaultdict(lambda: collections.defaultdict(int))

    # distance_stats: track -> distance -> bucket -> stats
    dist_counts = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(int)))
    dist_wins = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(int)))
    dist_places = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(int)))

    for race_id, runners in races.items():
        field_size = len(runners)
        if field_size <= 8:
            field_cat = "field_1_8"
        elif field_size <= 12:
            field_cat = "field_9_12"
        else:
            field_cat = "field_13_plus"

        for r in runners:
            trk = r["track"]
            dst = r["distance"]
            bkt = get_bucket(r["barrier"])
            pos = r["pos"]

            is_win = (pos == 1)
            is_place = (pos <= 3)

            # Global
            global_counts[field_cat][bkt] += 1
            if is_win: global_wins[field_cat][bkt] += 1
            if is_place: global_places[field_cat][bkt] += 1

            # Track General
            track_counts[trk][bkt] += 1
            if is_win: track_wins[trk][bkt] += 1
            if is_place: track_places[trk][bkt] += 1

            # Track + Distance Specific
            dist_counts[trk][dst][bkt] += 1
            if is_win: dist_wins[trk][dst][bkt] += 1
            if is_place: dist_places[trk][dst][bkt] += 1

    # 3. Build JSON structure
    matrix = {
        "global_general": {},
        "tracks": {}
    }

    # Populate global
    for f_cat in ["field_1_8", "field_9_12", "field_13_plus"]:
        matrix["global_general"][f_cat] = compute_rates(global_counts[f_cat], global_wins[f_cat], global_places[f_cat])

    # Populate tracks
    for trk, t_counts in track_counts.items():
        matrix["tracks"][trk] = {
            "track_general": compute_rates(t_counts, track_wins[trk], track_places[trk]),
            "distances": {}
        }
        for dst, d_counts in dist_counts[trk].items():
            matrix["tracks"][trk]["distances"][dst] = compute_rates(d_counts, dist_wins[trk][dst], dist_places[trk][dst])

    out_path = Path(OUTPUT_JSON)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(matrix, f, indent=4, ensure_ascii=False)

    print(f"✅ Successfully generated Draw Bias Matrix at {OUTPUT_JSON}")
    print(f"Processed {len(races)} races across {len(track_counts)} tracks.")

if __name__ == "__main__":
    main()
