import json
import os
import pandas as pd
from pathlib import Path
import re

# ── Helpers ──────────────────────────────────────────────────────────────

def get_season(date_str):
    """Determine HKJC season from date string (YYYYMMDD)"""
    try:
        clean = "".join(filter(str.isdigit, str(date_str)))
        if len(clean) < 8:
            return "Unknown"
        d = int(clean[:8])
        if d >= 20250901: return "25/26"
        if d >= 20240901: return "24/25"
        if d >= 20230901: return "23/24"
        return "Older"
    except Exception:
        return "Unknown"


def get_month(date_str):
    """Extract YYYY-MM from date string"""
    try:
        clean = "".join(filter(str.isdigit, str(date_str)))
        return f"{clean[:4]}-{clean[4:6]}"
    except Exception:
        return "Unknown"


def classify_running_style(rp_str, rank):
    """Classify running style from running_positions string like '8 8 1'"""
    try:
        positions = [int(x) for x in str(rp_str).strip().split()]
        if not positions:
            return "Unknown"
        early = positions[0]
        if early <= 3:
            return "Frontrunner"
        elif early <= 7:
            return "Midpack"
        else:
            return "Closer"
    except Exception:
        return "Unknown"


def parse_finish_time(ft_str):
    """Parse finish time string like '0:57.87' or '1:09.28' to seconds"""
    try:
        parts = str(ft_str).split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    except Exception:
        pass
    return None


def parse_race_metadata(sectional_rows):
    """Extract race_class, going, course from sectional_times rows"""
    race_class = "Unknown"
    going = "Unknown"
    course = "Unknown"

    for row in sectional_rows:
        text = " ".join(str(c) for c in row)

        # Race class: "第四班", "新馬賽", "第三班", "第一班", etc.
        if "新馬" in text:
            race_class = "Griffin"
        elif "第一班" in text:
            race_class = "Class 1"
        elif "第二班" in text:
            race_class = "Class 2"
        elif "第三班" in text:
            race_class = "Class 3"
        elif "第四班" in text:
            race_class = "Class 4"
        elif "第五班" in text:
            race_class = "Class 5"
        elif "一級賽" in text or "國際" in text:
            race_class = "Group 1"
        elif "二級賽" in text:
            race_class = "Group 2"
        elif "三級賽" in text:
            race_class = "Group 3"

        # Going (場地狀況)
        if "場地狀況" in text:
            for cell in row:
                cell_s = str(cell).strip()
                if cell_s and "場地狀況" not in cell_s and cell_s != ":":
                    going = cell_s
                    break

        # Course (賽道)
        if "賽道" in text:
            for cell in row:
                cell_s = str(cell).strip()
                if "賽道" not in cell_s and cell_s and cell_s != ":":
                    course = cell_s
                    break

    return race_class, going, course


def classify_odds(odds):
    """Classify odds into buckets"""
    if odds < 3:    return "Hot Fav (<3)"
    if odds < 6:    return "Fav (3-6)"
    if odds < 10:   return "Contender (6-10)"
    if odds < 20:   return "Mid (10-20)"
    if odds < 50:   return "Longshot (20-50)"
    return "Outsider (50+)"


def classify_weight(wt):
    """Classify actual weight into brackets"""
    try:
        w = int(wt)
        if w <= 115:   return "Light (<=115)"
        if w <= 120:   return "Med-Light (116-120)"
        if w <= 126:   return "Medium (121-126)"
        if w <= 130:   return "Med-Heavy (127-130)"
        return "Heavy (131+)"
    except Exception:
        return "Unknown"


# ── Main Aggregation ─────────────────────────────────────────────────────

def aggregate_stats():
    base_dirs = [
        "archive race analysis/hkjc results 2024 25",
        "archive race analysis/hkjc results 2025 26"
    ]

    all_data = []

    print("Starting data aggregation from 180+ meetings...")

    for base in base_dirs:
        if not os.path.exists(base):
            continue
        for date_dir in os.listdir(base):
            json_path = os.path.join(base, date_dir, "full_day_results.json")
            if not os.path.exists(json_path):
                continue
            try:
                with open(json_path, "r", encoding="utf-8-sig") as f:
                    day_data = json.load(f)

                for race_no, race_info in day_data.items():
                    venue = race_info.get("venue", "Unknown")
                    racedate = race_info.get("racedate", date_dir)
                    season = get_season(racedate)
                    month = get_month(racedate)

                    # Parse sectional_times for track/distance/class/going/course
                    track_type = "Unknown"
                    distance = 0
                    sect_rows = race_info.get("sectional_times", [])

                    for row in sect_rows:
                        if " - " in row[0] and "米" in row[0]:
                            parts = row[0].split(" - ")
                            if len(parts) >= 2:
                                dist_str = parts[1].replace("米", "").strip()
                                # Handle "(60-40)" suffix
                                dist_str = dist_str.split(" ")[0].strip("()")
                                if dist_str.isdigit():
                                    distance = int(dist_str)
                        for cell in row:
                            cs = str(cell)
                            if "草地" in cs:
                                track_type = "Turf"
                            elif "全天候" in cs or "泥地" in cs:
                                track_type = "AWT"

                    race_class, going, course = parse_race_metadata(sect_rows)

                    for runner in race_info.get("results", []):
                        try:
                            pos = runner.get("pos", "")
                            clean_pos = "".join(filter(str.isdigit, str(pos)))
                            rank = int(clean_pos) if clean_pos.isdigit() else 99

                            win = 1 if rank == 1 else 0
                            place = 1 if rank <= 3 else 0

                            odds = float(runner.get("win_odds", 0) or 0)
                            profit = (odds - 1) if win == 1 else -1

                            rp = runner.get("running_positions", "")
                            style = classify_running_style(rp, rank)
                            ft = parse_finish_time(runner.get("finish_time", ""))
                            odds_bucket = classify_odds(odds) if odds > 0 else "Unknown"
                            wt_bucket = classify_weight(runner.get("actual_wt", ""))

                            all_data.append({
                                "Date": racedate,
                                "Month": month,
                                "Season": season,
                                "RaceNo": race_no,
                                "RaceClass": race_class,
                                "Venue": venue,
                                "Track": track_type,
                                "Course": course,
                                "Going": going,
                                "Distance": distance,
                                "Horse": runner.get("horse_name", ""),
                                "Jockey": runner.get("jockey", ""),
                                "Trainer": runner.get("trainer", ""),
                                "Draw": runner.get("draw", ""),
                                "Rank": rank,
                                "Win": win,
                                "Place": place,
                                "Odds": odds,
                                "OddsBucket": odds_bucket,
                                "Profit": profit,
                                "ActualWt": runner.get("actual_wt", ""),
                                "WtBucket": wt_bucket,
                                "HorseWt": runner.get("horse_wt", ""),
                                "FinishTimeSec": ft,
                                "RunStyle": style,
                                "RunningPos": rp,
                            })
                        except Exception:
                            continue
            except Exception as e:
                print(f"Error reading {json_path}: {e}")

    if not all_data:
        print("No data found!")
        return

    full_df = pd.DataFrame(all_data)

    # Metadata loading
    metadata = {}
    metadata_path = "scratch/horse_metadata_cache.json"
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8-sig") as f:
            metadata = json.load(f)

    def get_id(horse_name):
        if "(" in horse_name and ")" in horse_name:
            return horse_name.split("(")[-1].split(")")[0].strip()
        return horse_name

    full_df["HorseID"] = full_df["Horse"].apply(get_id)
    full_df["Sire"] = full_df["HorseID"].apply(lambda x: metadata.get(x, {}).get("sire", "Unknown"))
    full_df["DamSire"] = full_df["HorseID"].apply(lambda x: metadata.get(x, {}).get("dam_sire", "Unknown"))
    full_df["Origin"] = full_df["HorseID"].apply(lambda x: metadata.get(x, {}).get("origin", "Unknown"))

    # ── Season splits ────────────────────────────────────────────────────
    process_configs = [
        ("Full", full_df),
        ("24_25", full_df[full_df["Season"] == "24/25"]),
        ("25_26", full_df[full_df["Season"] == "25/26"]),
    ]

    for label, df in process_configs:
        if df.empty:
            print(f"Skipping {label} - No data.")
            continue

        n = len(df)
        print(f"Generating reports for: {label} ({n} records)")

        out_dir = Path(f"archive race analysis/comprehensive_stats/{label}")
        out_dir.mkdir(parents=True, exist_ok=True)

        # Helper to save
        def save(frame, name):
            frame.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8-sig")

        # ── 1. Master Raw Data ───────────────────────────────────────────
        save(df, f"race_results_{label}")

        # ── 2. Jockey-Trainer Combination ────────────────────────────────
        jt = df.groupby(["Jockey", "Trainer"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"),
            Places=("Place", "sum"), Profit=("Profit", "sum")
        ).reset_index()
        jt["WinRate"] = (jt["Wins"] / jt["Starts"] * 100).round(1)
        jt["PlaceRate"] = (jt["Places"] / jt["Starts"] * 100).round(1)
        jt["ROI"] = (jt["Profit"] / jt["Starts"] * 100).round(1)
        save(jt.sort_values("Wins", ascending=False), "jockey_trainer_stats")

        # ── 3. Draw Bias (Venue + Track + Distance) ──────────────────────
        db = df.groupby(["Venue", "Track", "Distance", "Draw"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        db["WinRate"] = (db["Wins"] / db["Starts"] * 100).round(1)
        save(db, "draw_bias_stats")

        # ── 4. Jockey Master ─────────────────────────────────────────────
        jm = df.groupby("Jockey").agg(
            Wins=("Win", "sum"), Starts=("Win", "count"),
            Places=("Place", "sum"), Profit=("Profit", "sum")
        ).reset_index()
        jm["WinRate"] = (jm["Wins"] / jm["Starts"] * 100).round(1)
        jm["PlaceRate"] = (jm["Places"] / jm["Starts"] * 100).round(1)
        jm["ROI"] = (jm["Profit"] / jm["Starts"] * 100).round(1)
        save(jm.sort_values("Wins", ascending=False), "jockey_master_stats")

        # ── 5. Trainer Master ────────────────────────────────────────────
        tm = df.groupby("Trainer").agg(
            Wins=("Win", "sum"), Starts=("Win", "count"),
            Places=("Place", "sum"), Profit=("Profit", "sum")
        ).reset_index()
        tm["WinRate"] = (tm["Wins"] / tm["Starts"] * 100).round(1)
        tm["PlaceRate"] = (tm["Places"] / tm["Starts"] * 100).round(1)
        tm["ROI"] = (tm["Profit"] / tm["Starts"] * 100).round(1)
        save(tm.sort_values("Wins", ascending=False), "trainer_master_stats")

        # ── 6. Jockey Draw Performance ───────────────────────────────────
        jd = df.groupby(["Jockey", "Draw"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        jd["WinRate"] = (jd["Wins"] / jd["Starts"] * 100).round(1)
        jd["PlaceRate"] = (jd["Places"] / jd["Starts"] * 100).round(1)
        save(jd.sort_values(["Jockey", "Draw"]), "jockey_draw_performance")

        # ── 7. Trainer Draw Performance ──────────────────────────────────
        td = df.groupby(["Trainer", "Draw"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        td["WinRate"] = (td["Wins"] / td["Starts"] * 100).round(1)
        save(td.sort_values(["Trainer", "Draw"]), "trainer_draw_performance")

        # ── 8. Pedigree Stats ────────────────────────────────────────────
        for field in ["Sire", "DamSire", "Origin"]:
            ps = df[df[field] != "Unknown"].groupby(field).agg(
                Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
            ).reset_index()
            if not ps.empty:
                ps["WinRate"] = (ps["Wins"] / ps["Starts"] * 100).round(1)
                save(ps.sort_values("Wins", ascending=False), f"{field.lower()}_stats")

        # ── 9. Running Style Win Rate ────────────────────────────────────
        rs = df[df["RunStyle"] != "Unknown"].groupby("RunStyle").agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        rs["WinRate"] = (rs["Wins"] / rs["Starts"] * 100).round(1)
        rs["PlaceRate"] = (rs["Places"] / rs["Starts"] * 100).round(1)
        save(rs, "running_style_stats")

        # ── 10. Jockey Running Style Preference ─────────────────────────
        jrs = df[df["RunStyle"] != "Unknown"].groupby(["Jockey", "RunStyle"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        jrs["WinRate"] = (jrs["Wins"] / jrs["Starts"] * 100).round(1)
        save(jrs.sort_values(["Jockey", "RunStyle"]), "jockey_running_style")

        # ── 11. Going (Track Condition) Performance ─────────────────────
        gj = df[df["Going"] != "Unknown"].groupby(["Jockey", "Going"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        gj["WinRate"] = (gj["Wins"] / gj["Starts"] * 100).round(1)
        save(gj.sort_values(["Jockey", "Going"]), "jockey_going_performance")

        gt = df[df["Going"] != "Unknown"].groupby(["Trainer", "Going"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        gt["WinRate"] = (gt["Wins"] / gt["Starts"] * 100).round(1)
        save(gt.sort_values(["Trainer", "Going"]), "trainer_going_performance")

        # ── 12. Race Class Performance ──────────────────────────────────
        jc = df[df["RaceClass"] != "Unknown"].groupby(["Jockey", "RaceClass"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        jc["WinRate"] = (jc["Wins"] / jc["Starts"] * 100).round(1)
        save(jc.sort_values(["Jockey", "RaceClass"]), "jockey_class_performance")

        tc = df[df["RaceClass"] != "Unknown"].groupby(["Trainer", "RaceClass"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        tc["WinRate"] = (tc["Wins"] / tc["Starts"] * 100).round(1)
        save(tc.sort_values(["Trainer", "RaceClass"]), "trainer_class_performance")

        # ── 13. Course (A/B/C Track) Draw Bias ──────────────────────────
        cd = df[df["Course"] != "Unknown"].groupby(["Course", "Draw"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        cd["WinRate"] = (cd["Wins"] / cd["Starts"] * 100).round(1)
        save(cd.sort_values(["Course", "Draw"]), "course_draw_bias")

        # ── 14. Weight Bracket Analysis ─────────────────────────────────
        wb = df[df["WtBucket"] != "Unknown"].groupby("WtBucket").agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        wb["WinRate"] = (wb["Wins"] / wb["Starts"] * 100).round(1)
        save(wb, "weight_bracket_stats")

        # ── 15. Jockey Upset / Longshot Rate ────────────────────────────
        longshots = df[df["Odds"] >= 20]
        if not longshots.empty:
            lu = longshots.groupby("Jockey").agg(
                Wins=("Win", "sum"), Starts=("Win", "count"),
                Places=("Place", "sum"), AvgOdds=("Odds", "mean")
            ).reset_index()
            lu["WinRate"] = (lu["Wins"] / lu["Starts"] * 100).round(1)
            lu["AvgOdds"] = lu["AvgOdds"].round(1)
            save(lu.sort_values("Wins", ascending=False), "jockey_longshot_performance")

        # ── 16. Jockey Monthly Trend ────────────────────────────────────
        jmt = df.groupby(["Jockey", "Month"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        jmt["WinRate"] = (jmt["Wins"] / jmt["Starts"] * 100).round(1)
        save(jmt.sort_values(["Jockey", "Month"]), "jockey_monthly_trend")

        # ── 17. Trainer Monthly Trend ───────────────────────────────────
        tmt = df.groupby(["Trainer", "Month"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        tmt["WinRate"] = (tmt["Wins"] / tmt["Starts"] * 100).round(1)
        save(tmt.sort_values(["Trainer", "Month"]), "trainer_monthly_trend")

        # ── 18. Jockey-Venue-Track Combo ────────────────────────────────
        jvt = df.groupby(["Jockey", "Venue", "Track"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"),
            Places=("Place", "sum"), Profit=("Profit", "sum")
        ).reset_index()
        jvt["WinRate"] = (jvt["Wins"] / jvt["Starts"] * 100).round(1)
        jvt["ROI"] = (jvt["Profit"] / jvt["Starts"] * 100).round(1)
        save(jvt.sort_values(["Jockey", "Venue"]), "jockey_venue_track_stats")

        # ── 19. Trainer Distance Specialization ─────────────────────────
        tds = df[df["Distance"] > 0].groupby(["Trainer", "Distance"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        tds["WinRate"] = (tds["Wins"] / tds["Starts"] * 100).round(1)
        save(tds.sort_values(["Trainer", "Distance"]), "trainer_distance_stats")

        # ── 20. Jockey Distance Specialization ──────────────────────────
        jds = df[df["Distance"] > 0].groupby(["Jockey", "Distance"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        jds["WinRate"] = (jds["Wins"] / jds["Starts"] * 100).round(1)
        save(jds.sort_values(["Jockey", "Distance"]), "jockey_distance_stats")

        # ── 21. Favourite Conversion Rate ───────────────────────────────
        favs = df[df["Odds"] < 6]
        if not favs.empty:
            fc = favs.groupby("Jockey").agg(
                Wins=("Win", "sum"), Starts=("Win", "count"),
                Places=("Place", "sum"), AvgOdds=("Odds", "mean")
            ).reset_index()
            fc["WinRate"] = (fc["Wins"] / fc["Starts"] * 100).round(1)
            fc["PlaceRate"] = (fc["Places"] / fc["Starts"] * 100).round(1)
            fc["AvgOdds"] = fc["AvgOdds"].round(1)
            save(fc.sort_values("Wins", ascending=False), "jockey_favourite_conversion")

        # ── 22. Draw + Distance Combo ───────────────────────────────────
        dd = df[df["Distance"] > 0].groupby(["Distance", "Draw"]).agg(
            Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
        ).reset_index()
        dd["WinRate"] = (dd["Wins"] / dd["Starts"] * 100).round(1)
        save(dd.sort_values(["Distance", "Draw"]), "distance_draw_bias")

        # ── 23. Horse Master Stats ──────────────────────────────────────
        hm = df.groupby("Horse").agg(
            Wins=("Win", "sum"), Starts=("Win", "count"),
            Places=("Place", "sum"), AvgOdds=("Odds", "mean")
        ).reset_index()
        hm["WinRate"] = (hm["Wins"] / hm["Starts"] * 100).round(1)
        hm["AvgOdds"] = hm["AvgOdds"].round(1)
        save(hm.sort_values("Wins", ascending=False), "horse_master_stats")

        print(f"  -> {label}: 23 report types generated.")

    print("Done! All multi-season reports saved to archive race analysis/comprehensive_stats/")


if __name__ == "__main__":
    aggregate_stats()
