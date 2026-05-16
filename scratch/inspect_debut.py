import pandas as pd

full = pd.read_csv("archive race analysis/comprehensive_stats/Full/race_results_Full.csv")
grif = full[full["RaceClass"] == "Griffin"]

print(f"Total Griffin/Debut records: {len(grif)}")
s24 = grif[grif["Season"] == "24/25"]
s25 = grif[grif["Season"] == "25/26"]
print(f"  24/25: {len(s24)}")
print(f"  25/26: {len(s25)}")
print()

print("Distances:", sorted(grif["Distance"].unique()))
print("Venues:", grif["Venue"].value_counts().to_dict())
print()

print("=== Top Jockeys in Griffin Races ===")
j = grif.groupby("Jockey").agg(Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")).reset_index()
j["WinRate"] = (j["Wins"] / j["Starts"] * 100).round(1)
j["PlaceRate"] = (j["Places"] / j["Starts"] * 100).round(1)
print(j.sort_values("Wins", ascending=False).head(15).to_string(index=False))

print()
print("=== Top Trainers in Griffin Races ===")
t = grif.groupby("Trainer").agg(Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")).reset_index()
t["WinRate"] = (t["Wins"] / t["Starts"] * 100).round(1)
t["PlaceRate"] = (t["Places"] / t["Starts"] * 100).round(1)
print(t.sort_values("Wins", ascending=False).head(15).to_string(index=False))

print()
print("=== Draw Bias in Griffin Races ===")
d = grif.groupby("Draw").agg(Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")).reset_index()
d["WinRate"] = (d["Wins"] / d["Starts"] * 100).round(1)
print(d.sort_values("Draw").to_string(index=False))

print()
print("=== Running Style in Griffin Races ===")
rs = grif[grif["RunStyle"] != "Unknown"].groupby("RunStyle").agg(
    Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")
).reset_index()
rs["WinRate"] = (rs["Wins"] / rs["Starts"] * 100).round(1)
print(rs.to_string(index=False))

print()
print("=== Jockey-Trainer Combo in Griffin (min 3 starts) ===")
jt = grif.groupby(["Jockey","Trainer"]).agg(Wins=("Win","sum"), Starts=("Win","count"), Places=("Place","sum")).reset_index()
jt["WinRate"] = (jt["Wins"] / jt["Starts"] * 100).round(1)
jt_f = jt[jt["Starts"] >= 3].sort_values("Wins", ascending=False)
print(jt_f.head(20).to_string(index=False))

print()
print("=== Odds Distribution in Griffin Wins ===")
wins = grif[grif["Win"] == 1]
print(f"Total debut winners: {len(wins)}")
print(f"Avg winning odds: {wins['Odds'].mean():.1f}")
print(f"Median winning odds: {wins['Odds'].median():.1f}")
print(wins["OddsBucket"].value_counts().to_string())
