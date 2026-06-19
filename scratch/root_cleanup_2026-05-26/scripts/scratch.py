import csv
from pathlib import Path

csv_path = Path("Archive_Race_Analysis/AU_Racing/AU_Historical_Raw_Race_Results.csv")
with open(csv_path, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    print(f"Total rows in Historical CSV: {sum(1 for _ in reader)}")
    f.seek(0)
    reader = csv.DictReader(f)
    races = set()
    for row in reader:
        if row.get("Date") and row.get("Race"):
            races.add((row["Date"], row["Race"]))
    print(f"Unique Races in Historical CSV: {len(races)}")
