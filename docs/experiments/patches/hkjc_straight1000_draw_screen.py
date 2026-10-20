import sys, random
import pandas as pd
df = pd.read_pickle(sys.argv[1])
df = df[df["Draw"].notna() & df["Rank"].notna()].copy()
df["Race"] = df["Date"] + "_" + df["RaceNo"].astype(str)
df["field"] = df.groupby("Race")["Horse"].transform("count")
df["placed"] = (df["Rank"] <= 3).astype(float)
df["exp"] = 3.0 / df["field"]
def bucket(r):
    d = int(r.Draw)
    if r.straight: return "8+" if d >= 8 else ("5-7" if d >= 5 else "1-4")
    return "1-4" if d <= 4 else ("5-8" if d <= 8 else "9+")
df["straight"] = (df["Venue"] == "沙田") & (df["Track"] == "Turf") & (df["Distance"] == 1000)
df["b"] = [bucket(r) for r in df.itertuples()]
def ci(sub, B=2000):
    dates = list(sub["Date"].unique()); by = {d: s for d, s in sub.groupby("Date")}; rng = random.Random(7); xs = []
    for _ in range(B):
        s = pd.concat([by[rng.choice(dates)] for _ in dates]); xs.append(s["placed"].sum() / s["exp"].sum())
    xs.sort(); return xs[int(B*.025)], xs[int(B*.975)]
def table(sub, name, order):
    print(f"\n== {name}: races {sub['Race'].nunique()}  meetings {sub['Date'].nunique()}  runners {len(sub)}")
    for b in order:
        s = sub[sub["b"] == b]; lo, hi = ci(s)
        print(f"  {b:4s} n={len(s):5d} place {s['placed'].mean():.3f} exp {s['exp'].mean():.3f}  ratio {s['placed'].sum()/s['exp'].sum():.2f} [{lo:.2f},{hi:.2f}]")
st = df[df["straight"]]
table(st, "沙田直路 1000（引擎：8+=77.45 / 5-7=65 / 1-4=50）", ["8+", "5-7", "1-4"])
print("  逐檔 ratio:", {int(d): round(s['placed'].sum()/s['exp'].sum(), 2) for d, s in st.groupby("Draw")})
# paired difference outside(8+) minus inside(1-4), meeting bootstrap
dates = list(st["Date"].unique()); by = {d: s for d, s in st.groupby("Date")}; rng = random.Random(11); xs = []
for _ in range(2000):
    s = pd.concat([by[rng.choice(dates)] for _ in dates])
    o = s[s.b == "8+"]; i = s[s.b == "1-4"]
    xs.append(o["placed"].sum()/o["exp"].sum() - i["placed"].sum()/i["exp"].sum())
xs.sort(); print(f"  外(8+) − 內(1-4) ratio 差 {sorted(xs)[1000]:+.2f} [{xs[50]:+.2f},{xs[1950]:+.2f}]")
for season, s in st.groupby("SeasonTag"):
    print("  season", season, {b: round(g['placed'].sum()/g['exp'].sum(), 2) for b, g in s.groupby("b")}, "races", s["Race"].nunique())
for (v, t), sub in df[~df["straight"]].groupby(["Venue", "Track"]):
    table(sub, f"{v} {t} 彎道（引擎：1-4=75 / 5-8=65 / 9+=49）", ["1-4", "5-8", "9+"])
