import csv
import json
import sys
import collections
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING, au_historical_results_csv
CSV_PATH = str(au_historical_results_csv(AU_RACING))
# Racenet results backfill (scratch/au_results_backfill_driver.py) — same schema.
# Every backfill batch densifies the draw matrix; the engine's n/(n+25)
# shrinkage then automatically trusts the venue cells more as they grow.
BACKFILL_CSV_PATH = str(AU_RACING / "AU_Backfill_Race_Results.csv")
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

def canonical_distance(value) -> str:
    """距離鍵一定要同引擎查表嗰刻嘅寫法一致。

    2026-08-31：`au_results_ingest` 寫嘅係 `"1200.0"`，而 `_pace_map_score` 查表
    前做 `re.sub(r"[^0-9]", "", "1200m")` → `"1200"`。兩邊唔同鍵，即係逐距離
    cell 全部查唔到，靜靜跌返 track 總體。同 2026-07-03 嗰個「'm' 後綴 vs 純數字」
    BUGFIX 係同一個撞鍵，只係方向調轉。

    ⚠️ 改呢個函數就等於改咗表嘅鍵 —— 一定要同 `_pace_map_score` 嗰行一齊睇。
    """
    digits = re.sub(r"[^0-9]", "", str(value or "").split(".")[0])
    return digits


def parse_barrier(value) -> "int | None":
    """檔位可能係 `"7"`、`"7.0"`、`7` 或者空白。一律轉成 int，唔得就 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != int(number):
        return None
    return int(number)


RACES_FILENAME = "au_draw_bias_races.json"


def collect_races(csv_paths) -> list[dict]:
    """結果 CSV → 逐場 `{date, track, distance, runners: [[barrier, pos], …]}`。

    呢個係矩陣嘅**唯一**輸入形狀。`main()` 同引擎嘅 as-of 重砌
    （`engine_core._load_draw_bias_matrix_as_of`，EXP-20261015-04）都行
    `build_matrix(collect_races(...))`，所以 live 表同歷史表係同一條公式。
    """
    races: dict[str, dict] = {}
    for csv_path in csv_paths:
        if not Path(csv_path).exists():
            continue
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                date = row.get("Date", "").strip()
                track = row.get("Track", "").strip().title()
                race_num = row.get("Race", "").strip()
                distance = canonical_distance(row.get("Distance"))
                # 2026-08-31：`isdigit()` 太嚴。`au_results_ingest` 寫嘅係浮點格式
                # （`"2.0"`），而 `"2.0".isdigit()` 係 **False** —— 18,564 行主 CSV
                # 一行都讀唔到，成個表只靠 backfill 嗰 703 行。同一族缺陷嘅第八次
                # （見 [[scraper-silent-drop-failure-mode]]）：一個嚴格 pattern
                # 靜靜丟掉一整類數據，而唔會拋錯。
                barrier = parse_barrier(row.get("Barrier", "").strip())
                if barrier is None or barrier <= 0:
                    continue
                pos = parse_pos(row.get("Pos", "").strip())
                race_id = f"{date}_{track}_{race_num}"
                # 同一場第一行嘅 distance 定義成場（同舊版逐 runner 記錄等價：
                # 同一場所有行嘅 Distance 一樣）。
                entry = races.setdefault(race_id, {"date": date, "track": track,
                                                   "distance": distance, "runners": []})
                entry["runners"].append([barrier, pos])
    return list(races.values())


def build_matrix(races) -> dict:
    """逐場記錄 → 檔位矩陣（舊 `main()` 第 2、3 步，邏輯一字不改）。"""
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

    for race in races:
        runners = race["runners"]
        field_size = len(runners)
        if field_size <= 8:
            field_cat = "field_1_8"
        elif field_size <= 12:
            field_cat = "field_9_12"
        else:
            field_cat = "field_13_plus"

        trk = race["track"]
        dst = race["distance"]  # "" = CSV 冇距離，只計 track 總體同全域
        for barrier, pos in runners:
            bkt = get_bucket(barrier)
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

            # Track + Distance Specific（距離缺失就唔砌 "" cell —— 一個空鍵
            # 會扮成一個真 cascade 層，而引擎永遠查唔到佢）
            if not dst:
                continue
            dist_counts[trk][dst][bkt] += 1
            if is_win: dist_wins[trk][dst][bkt] += 1
            if is_place: dist_places[trk][dst][bkt] += 1

    matrix = {
        "global_general": {},
        "tracks": {}
    }
    for f_cat in ["field_1_8", "field_9_12", "field_13_plus"]:
        matrix["global_general"][f_cat] = compute_rates(global_counts[f_cat], global_wins[f_cat], global_places[f_cat])
    for trk, t_counts in track_counts.items():
        matrix["tracks"][trk] = {
            "track_general": compute_rates(t_counts, track_wins[trk], track_places[trk]),
            "distances": {}
        }
        for dst, d_counts in dist_counts[trk].items():
            matrix["tracks"][trk]["distances"][dst] = compute_rates(d_counts, dist_wins[trk][dst], dist_places[trk][dst])
    return matrix


def write_races_sidecar(races) -> Path:
    """逐場 sidecar：引擎歷史場次按 `date < 賽事日期` 過濾後重砌（EXP-20261015-04）。"""
    path = Path(OUTPUT_JSON).with_name(RACES_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(races, key=lambda r: (r["date"], r["track"], r["distance"]))
    path.write_text(json.dumps({"version": 1, "races": ordered}, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    return path


def main():
    if not Path(CSV_PATH).exists():
        print(f"Error: {CSV_PATH} not found.")
        return 1

    # 1. Read all rows grouped by race
    race_list = collect_races((CSV_PATH, BACKFILL_CSV_PATH))
    # `--index-only`：只更新逐場 sidecar，唔郁 live 矩陣（加 as-of 嗰次用，
    # 令 live 表同 golden 唔會因為「順手重建」而郁）。
    if "--index-only" in sys.argv:
        path = write_races_sidecar(race_list)
        print(f"✅ Wrote {len(race_list)} races to {path}")
        return 0

    # 2./3. Accumulate stats + build JSON structure
    matrix = build_matrix(race_list)
    track_counts = matrix["tracks"]
    races = race_list

    out_path = Path(OUTPUT_JSON)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 退化守衛（2026-08-31）。呢個表係 `pace_map_score` 唯一嘅經驗基礎，而佢
    # 靜靜塌過一次：`Barrier` 欄由 2026-08 起 0% 覆蓋 + `isdigit()` 太嚴，令主
    # CSV 讀到 0 行。當時個表凍結喺 2026-08-22 冇人察覺 —— 因為重建成功、
    # 輸出結構正常、零錯誤。一個「成功」但薄過現行版本嘅重建，唔可以覆蓋。
    new_races = len(races)
    if out_path.exists() and "--force" not in sys.argv:
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(old, dict) or not isinstance(old.get("tracks"), dict):
                raise ValueError("existing matrix tracks must be an object")
            tracks = old["tracks"]
            if any(
                not isinstance(track, dict)
                or not isinstance(track.get("distances"), dict)
                for track in tracks.values()
            ):
                raise ValueError("existing matrix distance cells must be objects")
            old_cells = sum(len(track["distances"]) for track in tracks.values())
            new_cells = sum(
                1
                for trk in matrix["tracks"].values()
                for _ in trk["distances"]
            )
            if old_cells and new_cells < old_cells * 0.8:
                print(
                    f"❌ 唔寫入：新表得 {new_cells} 個距離 cell，現行有 {old_cells} 個"
                    f"（跌 {1 - new_cells / old_cells:.0%}）。\n"
                    f"   幾乎一定係上游 CSV 有欄位死咗 —— 查 `Barrier` 欄覆蓋率，"
                    f"唔好用 --force 蓋過去。"
                )
                return 1
        except (OSError, ValueError) as exc:
            print(f"❌ 唔寫入：無法核對現行檔位表（{type(exc).__name__}: {exc}）")
            return 1

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(matrix, f, indent=4, ensure_ascii=False)
    write_races_sidecar(race_list)

    print(f"✅ Successfully generated Draw Bias Matrix at {OUTPUT_JSON}")
    print(f"Processed {new_races} races across {len(track_counts)} tracks.")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
