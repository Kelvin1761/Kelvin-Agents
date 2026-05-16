"""
Generate general-horse pre-race priors from archived HKJC race results.

Focus on reusable features that are known or inferable before the race:
- draw x field-size priors
- class / distance priors
- rest-cycle priors
- jockey / trainer venue-distance specialists
- jockey-trainer combo priors
- horse course-distance profiles
- running-style priors for established horses
- jockey-change effects
"""

from pathlib import Path

import pandas as pd


FULL_RESULTS = Path("archive race analysis/comprehensive_stats/Full/race_results_Full.csv")
OUTPUT_NAME = "general_pre_race_priors"
CONFIGS = [
    ("Full", None),
    ("24_25", "24/25"),
    ("25_26", "25/26"),
]


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


def rest_bucket(days):
    if pd.isna(days):
        return "First-up / No prior"
    if days <= 14:
        return "<=14d"
    if days <= 28:
        return "15-28d"
    if days <= 56:
        return "29-56d"
    if days <= 90:
        return "57-90d"
    return "91d+"


def pct_frame(df, include_roi=True, include_avg_odds=True):
    df["WinRate"] = (df["Wins"] / df["Starts"] * 100).round(2)
    df["PlaceRate"] = (df["Places"] / df["Starts"] * 100).round(2)
    if include_roi and "Profit" in df.columns:
        df["ROI"] = (df["Profit"] / df["Starts"] * 100).round(2)
    if include_avg_odds and "AvgOdds" in df.columns:
        df["AvgOdds"] = df["AvgOdds"].round(2)
    return df


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
    return pct_frame(out, include_roi=include_roi, include_avg_odds=include_avg_odds)


def prep_results():
    full = pd.read_csv(FULL_RESULTS)
    numeric_cols = [
        "RaceNo",
        "Distance",
        "Draw",
        "Rank",
        "Win",
        "Place",
        "Odds",
        "Profit",
        "ActualWt",
        "HorseWt",
        "FinishTimeSec",
    ]
    for col in numeric_cols:
        full[col] = pd.to_numeric(full[col], errors="coerce")

    full["Date"] = pd.to_datetime(full["Date"], errors="coerce")
    full = full.sort_values(["HorseID", "Date", "RaceNo"])

    race_sizes = (
        full.groupby(["Date", "Venue", "RaceNo"])
        .size()
        .rename("FieldSize")
        .reset_index()
    )
    full = full.merge(race_sizes, on=["Date", "Venue", "RaceNo"], how="left")
    full["FieldSizeBucket"] = full["FieldSize"].apply(field_size_bucket)
    full["DrawBand"] = full.apply(lambda row: draw_band(row["Draw"], row["FieldSize"]), axis=1)
    full["DrawBucket"] = full["Draw"].apply(draw_bucket)

    full["PrevDate"] = full.groupby("HorseID")["Date"].shift(1)
    full["DaysSinceLast"] = (full["Date"] - full["PrevDate"]).dt.days
    full["RestBucket"] = full["DaysSinceLast"].apply(rest_bucket)

    full["PrevJockey"] = full.groupby("HorseID")["Jockey"].shift(1)
    full["PrevTrainer"] = full.groupby("HorseID")["Trainer"].shift(1)
    full["JockeyChanged"] = (
        full["PrevJockey"].notna() & (full["PrevJockey"] != full["Jockey"])
    )
    full["TrainerChanged"] = (
        full["PrevTrainer"].notna() & (full["PrevTrainer"] != full["Trainer"])
    )
    full["CareerStartNo"] = full.groupby("HorseID").cumcount() + 1

    return full.sort_values(["Date", "RaceNo", "HorseID", "Horse"])


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
        "DaysSinceLast",
        "RestBucket",
        "CareerStartNo",
        "JockeyChanged",
        "TrainerChanged",
        "RunStyle",
        "Rank",
        "Win",
        "Place",
    ]
    out = df[cols].copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    return out


def build_draw_field_size(df):
    out = agg_basic(
        df[df["DrawBand"] != "Unknown"],
        ["Venue", "Track", "FieldSizeBucket", "DrawBand"],
        include_roi=False,
    )
    return out.sort_values(["Venue", "Track", "FieldSizeBucket", "DrawBand"])


def build_draw_bucket_distance_class(df):
    out = agg_basic(
        df[df["DrawBucket"] != "Unknown"],
        ["RaceClass", "Venue", "Track", "Distance", "DrawBucket"],
        include_roi=False,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_class_distance(df):
    out = agg_basic(
        df,
        ["RaceClass", "Venue", "Track", "Distance"],
        include_roi=False,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_rest_bucket(df):
    usable = df[df["CareerStartNo"] > 1].copy()
    overall = agg_basic(
        usable,
        ["RestBucket"],
        include_roi=False,
    )
    overall["Scope"] = "Overall"

    contextual = agg_basic(
        usable,
        ["RaceClass", "Venue", "Track", "Distance", "RestBucket"],
        include_roi=False,
    )
    contextual["Scope"] = "ClassVenueDistance"
    return overall, contextual.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_weight_class(df):
    usable = df[df["WtBucket"] != "Unknown"].copy()
    out = agg_basic(
        usable,
        ["RaceClass", "WtBucket"],
        include_roi=False,
    )
    return out.sort_values(["RaceClass", "WinRate"], ascending=[True, False])


def build_jockey_course_distance(df):
    out = agg_basic(
        df,
        ["Jockey", "Venue", "Track", "Distance"],
        include_roi=True,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_trainer_course_distance(df):
    out = agg_basic(
        df,
        ["Trainer", "Venue", "Track", "Distance"],
        include_roi=True,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_combo_priors(df):
    out = agg_basic(
        df,
        ["Jockey", "Trainer"],
        include_roi=True,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_horse_course_distance(df):
    out = agg_basic(
        df,
        ["HorseID", "Horse", "Venue", "Track", "Distance"],
        include_roi=True,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_horse_rest_cycle(df):
    usable = df[df["CareerStartNo"] > 1].copy()
    out = agg_basic(
        usable,
        ["HorseID", "Horse", "RestBucket"],
        include_roi=True,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_running_style_distance(df):
    usable = df[df["RunStyle"].fillna("Unknown") != "Unknown"].copy()
    out = agg_basic(
        usable,
        ["RunStyle", "Venue", "Track", "Distance"],
        include_roi=False,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_horse_running_style(df):
    usable = df[df["RunStyle"].fillna("Unknown") != "Unknown"].copy()
    out = agg_basic(
        usable,
        ["HorseID", "Horse", "RunStyle"],
        include_roi=False,
    )
    return out.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_jockey_change(df):
    usable = df[df["CareerStartNo"] > 1].copy()
    overall = agg_basic(
        usable,
        ["JockeyChanged"],
        include_roi=False,
    )
    overall["Scope"] = "Overall"

    contextual = agg_basic(
        usable,
        ["RaceClass", "Venue", "Track", "Distance", "JockeyChanged"],
        include_roi=False,
    )
    contextual["Scope"] = "ClassVenueDistance"
    return overall, contextual.sort_values(["Starts", "WinRate"], ascending=[False, False])


def build_month_trend(df):
    out = agg_basic(
        df,
        ["Month"],
        include_roi=False,
    )
    return out.sort_values("Month")


def write_outputs(label, df):
    out_dir = Path(f"archive race analysis/comprehensive_stats/{label}/{OUTPUT_NAME}")
    out_dir.mkdir(parents=True, exist_ok=True)

    rest_overall, rest_context = build_rest_bucket(df)
    jockey_change_overall, jockey_change_context = build_jockey_change(df)

    outputs = {
        "general_feature_base.csv": build_feature_base(df),
        "draw_field_size_priors.csv": build_draw_field_size(df),
        "draw_bucket_distance_class_priors.csv": build_draw_bucket_distance_class(df),
        "class_distance_priors.csv": build_class_distance(df),
        "rest_bucket_priors.csv": rest_overall,
        "rest_bucket_class_distance_priors.csv": rest_context,
        "weight_class_priors.csv": build_weight_class(df),
        "jockey_course_distance_priors.csv": build_jockey_course_distance(df),
        "trainer_course_distance_priors.csv": build_trainer_course_distance(df),
        "jockey_trainer_combo_priors.csv": build_combo_priors(df),
        "horse_course_distance_profile.csv": build_horse_course_distance(df),
        "horse_rest_cycle_profile.csv": build_horse_rest_cycle(df),
        "running_style_distance_priors.csv": build_running_style_distance(df),
        "horse_running_style_profile.csv": build_horse_running_style(df),
        "jockey_change_priors.csv": jockey_change_overall,
        "jockey_change_class_distance_priors.csv": jockey_change_context,
        "month_trend.csv": build_month_trend(df),
    }

    for filename, frame in outputs.items():
        frame.to_csv(out_dir / filename, index=False, encoding="utf-8-sig")

    print(f"{label}: wrote {len(outputs)} priors tables to {out_dir}")


def run():
    full = prep_results()
    print(f"Loaded {len(full)} rows across {full['HorseID'].nunique()} horses.")

    for label, season in CONFIGS:
        subset = full.copy() if season is None else full[full["Season"] == season].copy()
        if subset.empty:
            print(f"{label}: skipped (no rows)")
            continue
        write_outputs(label, subset)


if __name__ == "__main__":
    run()
