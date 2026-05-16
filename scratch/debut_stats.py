"""
Debut Horse Analysis — identifies every horse's FIRST race appearance
across all data, not just Griffin races. Generates targeted stats.
"""
import pandas as pd
from pathlib import Path

def run():
    full = pd.read_csv("archive race analysis/comprehensive_stats/Full/race_results_Full.csv")
    print(f"Total records loaded: {len(full)}")

    # Sort by date to find each horse's first race
    full["DateSort"] = full["Date"].apply(lambda x: "".join(filter(str.isdigit, str(x)))[:8])
    full = full.sort_values("DateSort")

    # Identify each horse's first appearance
    first_race = full.drop_duplicates(subset="Horse", keep="first")
    print(f"Total unique horses (debut races): {len(first_race)}")
    print(f"  24/25 debuts: {len(first_race[first_race['Season']=='24/25'])}")
    print(f"  25/26 debuts: {len(first_race[first_race['Season']=='25/26'])}")
    print()

    # Also tag Griffin races separately
    griffin = full[full["RaceClass"] == "Griffin"]
    print(f"Griffin-only races: {len(griffin)}")
    print()

    # Process for Full + each season
    configs = [
        ("Full", first_race),
        ("24_25", first_race[first_race["Season"] == "24/25"]),
        ("25_26", first_race[first_race["Season"] == "25/26"]),
    ]

    for label, df in configs:
        if df.empty:
            print(f"Skipping {label} - no debut data")
            continue

        out_dir = Path(f"archive race analysis/comprehensive_stats/{label}")
        out_dir.mkdir(parents=True, exist_ok=True)

        def save(frame, name):
            frame.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8-sig")

        n = len(df)
        wins = df["Win"].sum()
        places = df["Place"].sum()
        print(f"--- {label}: {n} debuts, {wins} wins ({wins/n*100:.1f}%), {places} places ({places/n*100:.1f}%) ---")

        # D1. Debut Jockey Stats
        dj = df.groupby("Jockey").agg(
            Wins=("Win","sum"), Starts=("Win","count"),
            Places=("Place","sum"), Profit=("Profit","sum"),
            AvgOdds=("Odds","mean")
        ).reset_index()
        dj["WinRate"] = (dj["Wins"] / dj["Starts"] * 100).round(1)
        dj["PlaceRate"] = (dj["Places"] / dj["Starts"] * 100).round(1)
        dj["ROI"] = (dj["Profit"] / dj["Starts"] * 100).round(1)
        dj["AvgOdds"] = dj["AvgOdds"].round(1)
        save(dj.sort_values("Wins", ascending=False), "debut_jockey_stats")

        # D2. Debut Trainer Stats
        dt = df.groupby("Trainer").agg(
            Wins=("Win","sum"), Starts=("Win","count"),
            Places=("Place","sum"), Profit=("Profit","sum"),
            AvgOdds=("Odds","mean")
        ).reset_index()
        dt["WinRate"] = (dt["Wins"] / dt["Starts"] * 100).round(1)
        dt["PlaceRate"] = (dt["Places"] / dt["Starts"] * 100).round(1)
        dt["ROI"] = (dt["Profit"] / dt["Starts"] * 100).round(1)
        dt["AvgOdds"] = dt["AvgOdds"].round(1)
        save(dt.sort_values("Wins", ascending=False), "debut_trainer_stats")

        # D3. Debut Jockey-Trainer Combo
        djt = df.groupby(["Jockey","Trainer"]).agg(
            Wins=("Win","sum"), Starts=("Win","count"),
            Places=("Place","sum"), AvgOdds=("Odds","mean")
        ).reset_index()
        djt["WinRate"] = (djt["Wins"] / djt["Starts"] * 100).round(1)
        djt["AvgOdds"] = djt["AvgOdds"].round(1)
        save(djt.sort_values("Wins", ascending=False), "debut_jockey_trainer_combo")

        # D4. Debut Draw Bias
        dd = df.groupby("Draw").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dd["WinRate"] = (dd["Wins"] / dd["Starts"] * 100).round(1)
        dd["PlaceRate"] = (dd["Places"] / dd["Starts"] * 100).round(1)
        save(dd.sort_values("Draw"), "debut_draw_bias")

        # D5. Debut Distance Stats
        ddist = df[df["Distance"] > 0].groupby("Distance").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        ddist["WinRate"] = (ddist["Wins"] / ddist["Starts"] * 100).round(1)
        save(ddist, "debut_distance_stats")

        # D6. Debut Running Style
        drs = df[df["RunStyle"] != "Unknown"].groupby("RunStyle").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        drs["WinRate"] = (drs["Wins"] / drs["Starts"] * 100).round(1)
        drs["PlaceRate"] = (drs["Places"] / drs["Starts"] * 100).round(1)
        save(drs, "debut_running_style")

        # D7. Debut Going Performance
        dg = df[df["Going"] != "Unknown"].groupby("Going").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dg["WinRate"] = (dg["Wins"] / dg["Starts"] * 100).round(1)
        save(dg, "debut_going_stats")

        # D8. Debut Odds Distribution (what odds do winners come from?)
        dob = df.groupby("OddsBucket").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dob["WinRate"] = (dob["Wins"] / dob["Starts"] * 100).round(1)
        save(dob, "debut_odds_distribution")

        # D9. Debut Venue + Track
        dvt = df.groupby(["Venue","Track"]).agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dvt["WinRate"] = (dvt["Wins"] / dvt["Starts"] * 100).round(1)
        save(dvt, "debut_venue_track")

        # D10. Debut Race Class Distribution
        drc = df.groupby("RaceClass").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        drc["WinRate"] = (drc["Wins"] / drc["Starts"] * 100).round(1)
        save(drc, "debut_race_class")

        # D11. Debut Weight Analysis
        dwb = df[df["WtBucket"] != "Unknown"].groupby("WtBucket").agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dwb["WinRate"] = (dwb["Wins"] / dwb["Starts"] * 100).round(1)
        save(dwb, "debut_weight_stats")

        # D12. Debut Trainer by Distance
        dtd = df[df["Distance"] > 0].groupby(["Trainer","Distance"]).agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dtd["WinRate"] = (dtd["Wins"] / dtd["Starts"] * 100).round(1)
        save(dtd.sort_values("Wins", ascending=False), "debut_trainer_distance")

        # D13. Debut Course (A/B/C)
        dc = df[df["Course"] != "Unknown"].groupby(["Course","Draw"]).agg(
            Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
        ).reset_index()
        dc["WinRate"] = (dc["Wins"] / dc["Starts"] * 100).round(1)
        save(dc.sort_values(["Course","Draw"]), "debut_course_draw")

        # ── Pedigree & Origin Stats for Debut Horses ──
        # Need to load metadata map
        import json
        metadata = {}
        if Path("scratch/horse_metadata_cache.json").exists():
            with open("scratch/horse_metadata_cache.json", "r", encoding="utf-8-sig") as f:
                metadata = json.load(f)

        def get_id(h):
            if "(" in h and ")" in h: return h.split("(")[-1].split(")")[0].strip()
            return h

        df_meta = df.copy()
        df_meta["HorseID"] = df_meta["Horse"].apply(get_id)
        df_meta["Sire"] = df_meta["HorseID"].apply(lambda x: metadata.get(x, {}).get("sire", "Unknown"))
        df_meta["Dam"] = df_meta["HorseID"].apply(lambda x: metadata.get(x, {}).get("dam", "Unknown"))
        df_meta["DamSire"] = df_meta["HorseID"].apply(lambda x: metadata.get(x, {}).get("dam_sire", "Unknown"))
        df_meta["Origin"] = df_meta["HorseID"].apply(lambda x: metadata.get(x, {}).get("origin", "Unknown"))
        df_meta["ImportClass"] = df_meta["HorseID"].apply(lambda x: metadata.get(x, {}).get("import_class", "Unknown"))

        # D14-D18. Pedigree, Origin, ImportClass
        for field in ["Sire", "Dam", "DamSire", "Origin", "ImportClass"]:
            p_stats = df_meta[df_meta[field] != "Unknown"].groupby(field).agg(
                Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum")
            ).reset_index()
            if not p_stats.empty:
                p_stats["WinRate"] = (p_stats["Wins"] / p_stats["Starts"] * 100).round(1)
                p_stats["PlaceRate"] = (p_stats["Places"] / p_stats["Starts"] * 100).round(1)
                save(p_stats.sort_values("Wins", ascending=False), f"debut_{field.lower()}_stats")

        print(f"  -> {label}: 18 debut reports saved.")

    print()
    print("Done! All debut stats saved.")

if __name__ == "__main__":
    run()
