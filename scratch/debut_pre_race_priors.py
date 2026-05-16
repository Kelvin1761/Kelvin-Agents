"""
Generate debut-horse pre-race priors from archived HKJC race results.

Focuses on features known before the race:
- trainer / jockey debut uplift
- jockey-trainer combo edge
- draw x field-size priors
- class x distance priors
- trainer deployment priors by class/distance
- weight and month deployment priors
- clean base table for downstream analysis
"""

from pathlib import Path

import pandas as pd


FULL_RESULTS = Path("archive race analysis/comprehensive_stats/Full/race_results_Full.csv")
OUTPUT_NAME = "debut_pre_race_priors"
CONFIGS = [
    ("Full", None),
    ("24_25", "24/25"),
    ("25_26", "25/26"),
]


def pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 2)


def prep_full_results():
    full = pd.read_csv(FULL_RESULTS)
    numeric_cols = ["RaceNo", "Distance", "Draw", "Rank", "Win", "Place", "Odds", "Profit", "ActualWt", "HorseWt"]
    for col in numeric_cols:
        full[col] = pd.to_numeric(full[col], errors="coerce")

    full["Date"] = pd.to_datetime(full["Date"], errors="coerce")
    full = full.sort_values(["Date", "RaceNo", "HorseID", "Horse"])

    race_sizes = (
        full.groupby(["Date", "Venue", "RaceNo"])
        .size()
        .rename("FieldSize")
        .reset_index()
    )
    full = full.merge(race_sizes, on=["Date", "Venue", "RaceNo"], how="left")

    first_race = full.drop_duplicates(subset="HorseID", keep="first").copy()
    first_race["FieldSizeBucket"] = first_race["FieldSize"].apply(field_size_bucket)
    first_race["DrawBand"] = first_race.apply(
        lambda row: draw_band(row["Draw"], row["FieldSize"]), axis=1
    )
    first_race["DrawBucket"] = first_race["Draw"].apply(draw_bucket)
    return full, first_race


def field_size_bucket(field_size):
    if pd.isna(field_size):
        return "Unknown"
    if field_size <= 11:
        return "small<=11"
    if field_size <= 13:
        return "med12-13"
    return "large14+"


def draw_band(draw, field_size):
    if pd.isna(draw) or pd.isna(field_size) or field_size <= 0:
        return "Unknown"
    if draw <= field_size / 3:
        return "Inside"
    if draw <= (field_size * 2) / 3:
        return "Middle"
    return "Outside"


def draw_bucket(draw):
    if pd.isna(draw):
        return "Unknown"
    if draw <= 3:
        return "1-3"
    if draw <= 6:
        return "4-6"
    if draw <= 9:
        return "7-9"
    return "10+"


def agg_basic(df, group_cols, include_roi=True, include_avg_odds=True):
    agg = {
        "Wins": ("Win", "sum"),
        "Starts": ("Win", "count"),
        "Places": ("Place", "sum"),
    }
    if include_roi:
        agg["Profit"] = ("Profit", "sum")
    if include_avg_odds:
        agg["AvgOdds"] = ("Odds", "mean")

    out = df.groupby(group_cols).agg(**agg).reset_index()
    out["WinRate"] = (out["Wins"] / out["Starts"] * 100).round(2)
    out["PlaceRate"] = (out["Places"] / out["Starts"] * 100).round(2)
    if include_roi:
        out["ROI"] = (out["Profit"] / out["Starts"] * 100).round(2)
    if include_avg_odds:
        out["AvgOdds"] = out["AvgOdds"].round(2)
    return out


def build_feature_base(df):
    cols = [
        "Date",
        "Month",
        "Season",
        "RaceNo",
        "RaceClass",
        "Venue",
        "Track",
        "Course",
        "Going",
        "Distance",
        "FieldSize",
        "FieldSizeBucket",
        "Horse",
        "HorseID",
        "Jockey",
        "Trainer",
        "Draw",
        "DrawBand",
        "DrawBucket",
        "ActualWt",
        "WtBucket",
        "HorseWt",
        "Odds",
        "OddsBucket",
        "Rank",
        "Win",
        "Place",
    ]
    out = df[cols].copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    return out


def build_trainer_uplift(full_df, debut_df):
    overall = agg_basic(full_df, ["Trainer"])
    overall = overall.rename(
        columns={
            "Wins": "OverallWins",
            "Starts": "OverallStarts",
            "Places": "OverallPlaces",
            "Profit": "OverallProfit",
            "AvgOdds": "OverallAvgOdds",
            "WinRate": "OverallWinRate",
            "PlaceRate": "OverallPlaceRate",
            "ROI": "OverallROI",
        }
    )

    debut = agg_basic(debut_df, ["Trainer"])
    debut = debut.rename(
        columns={
            "Wins": "DebutWins",
            "Starts": "DebutStarts",
            "Places": "DebutPlaces",
            "Profit": "DebutProfit",
            "AvgOdds": "DebutAvgOdds",
            "WinRate": "DebutWinRate",
            "PlaceRate": "DebutPlaceRate",
            "ROI": "DebutROI",
        }
    )

    out = debut.merge(overall, on="Trainer", how="left")
    out["WinRateUplift"] = (out["DebutWinRate"] - out["OverallWinRate"]).round(2)
    out["PlaceRateUplift"] = (out["DebutPlaceRate"] - out["OverallPlaceRate"]).round(2)
    out["ROIUplift"] = (out["DebutROI"] - out["OverallROI"]).round(2)
    return out.sort_values(["DebutStarts", "WinRateUplift"], ascending=[False, False])


def build_jockey_uplift(full_df, debut_df):
    overall = agg_basic(full_df, ["Jockey"])
    overall = overall.rename(
        columns={
            "Wins": "OverallWins",
            "Starts": "OverallStarts",
            "Places": "OverallPlaces",
            "Profit": "OverallProfit",
            "AvgOdds": "OverallAvgOdds",
            "WinRate": "OverallWinRate",
            "PlaceRate": "OverallPlaceRate",
            "ROI": "OverallROI",
        }
    )

    debut = agg_basic(debut_df, ["Jockey"])
    debut = debut.rename(
        columns={
            "Wins": "DebutWins",
            "Starts": "DebutStarts",
            "Places": "DebutPlaces",
            "Profit": "DebutProfit",
            "AvgOdds": "DebutAvgOdds",
            "WinRate": "DebutWinRate",
            "PlaceRate": "DebutPlaceRate",
            "ROI": "DebutROI",
        }
    )

    out = debut.merge(overall, on="Jockey", how="left")
    out["WinRateUplift"] = (out["DebutWinRate"] - out["OverallWinRate"]).round(2)
    out["PlaceRateUplift"] = (out["DebutPlaceRate"] - out["OverallPlaceRate"]).round(2)
    out["ROIUplift"] = (out["DebutROI"] - out["OverallROI"]).round(2)
    return out.sort_values(["DebutStarts", "WinRateUplift"], ascending=[False, False])


def build_combo_edge(debut_df, trainer_uplift_df, jockey_uplift_df):
    combo = agg_basic(debut_df, ["Jockey", "Trainer"], include_roi=False)
    trainer_cols = trainer_uplift_df[["Trainer", "DebutWinRate", "DebutPlaceRate"]].rename(
        columns={
            "DebutWinRate": "TrainerDebutWinRate",
            "DebutPlaceRate": "TrainerDebutPlaceRate",
        }
    )
    jockey_cols = jockey_uplift_df[["Jockey", "DebutWinRate", "DebutPlaceRate"]].rename(
        columns={
            "DebutWinRate": "JockeyDebutWinRate",
            "DebutPlaceRate": "JockeyDebutPlaceRate",
        }
    )
    out = combo.merge(trainer_cols, on="Trainer", how="left").merge(jockey_cols, on="Jockey", how="left")
    out["WinEdgeVsMean"] = (
        out["WinRate"] - (out["TrainerDebutWinRate"] + out["JockeyDebutWinRate"]) / 2
    ).round(2)
    out["PlaceEdgeVsMean"] = (
        out["PlaceRate"] - (out["TrainerDebutPlaceRate"] + out["JockeyDebutPlaceRate"]) / 2
    ).round(2)
    return out.sort_values(["Starts", "WinEdgeVsMean"], ascending=[False, False])


def build_draw_field_size(debut_df):
    out = agg_basic(
        debut_df[debut_df["DrawBand"] != "Unknown"],
        ["Venue", "Track", "FieldSizeBucket", "DrawBand"],
        include_roi=False,
    )
    return out.sort_values(["Venue", "Track", "FieldSizeBucket", "DrawBand"])


def build_distance_class(debut_df):
    out = agg_basic(
        debut_df,
        ["RaceClass", "Venue", "Track", "Distance"],
        include_roi=False,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_draw_bucket_distance_class(debut_df):
    out = agg_basic(
        debut_df[debut_df["DrawBucket"] != "Unknown"],
        ["RaceClass", "Venue", "Track", "Distance", "DrawBucket"],
        include_roi=False,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_trainer_class_distance(debut_df):
    out = agg_basic(
        debut_df,
        ["Trainer", "RaceClass", "Venue", "Track", "Distance"],
        include_roi=True,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_weight_priors(debut_df):
    out = agg_basic(
        debut_df[debut_df["WtBucket"] != "Unknown"],
        ["WtBucket"],
        include_roi=False,
    )
    return out.sort_values("WinRate", ascending=False)


def build_month_trend(debut_df):
    out = agg_basic(
        debut_df,
        ["Month"],
        include_roi=False,
    )
    return out.sort_values("Month")


def write_outputs(label, full_df, debut_df):
    out_dir = Path(f"archive race analysis/comprehensive_stats/{label}/{OUTPUT_NAME}")
    out_dir.mkdir(parents=True, exist_ok=True)

    trainer_uplift = build_trainer_uplift(full_df, debut_df)
    jockey_uplift = build_jockey_uplift(full_df, debut_df)
    combo_edge = build_combo_edge(debut_df, trainer_uplift, jockey_uplift)

    outputs = {
        "debut_feature_base.csv": build_feature_base(debut_df),
        "trainer_uplift.csv": trainer_uplift,
        "jockey_uplift.csv": jockey_uplift,
        "combo_edge.csv": combo_edge,
        "draw_field_size_priors.csv": build_draw_field_size(debut_df),
        "distance_class_priors.csv": build_distance_class(debut_df),
        "draw_bucket_distance_class_priors.csv": build_draw_bucket_distance_class(debut_df),
        "trainer_class_distance_priors.csv": build_trainer_class_distance(debut_df),
        "weight_priors.csv": build_weight_priors(debut_df),
        "month_trend.csv": build_month_trend(debut_df),
    }

    for filename, frame in outputs.items():
        frame.to_csv(out_dir / filename, index=False, encoding="utf-8-sig")

    print(f"{label}: wrote {len(outputs)} priors tables to {out_dir}")


def run():
    full, first_race = prep_full_results()
    print(f"Loaded {len(full)} rows, {len(first_race)} debut rows.")

    for label, season in CONFIGS:
        if season is None:
            subset_full = full.copy()
            subset_debut = first_race.copy()
        else:
            subset_full = full[full["Season"] == season].copy()
            subset_debut = first_race[first_race["Season"] == season].copy()

        if subset_debut.empty:
            print(f"{label}: skipped (no debut rows)")
            continue

        write_outputs(label, subset_full, subset_debut)


if __name__ == "__main__":
    run()
