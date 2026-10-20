import sys
sys.path[:0] = [".agents/skills/hkjc_racing/hkjc_reflector/scripts", ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts", ".", ".agents/scripts", ".agents/skills/shared_racing"]
import pit_backtest as p
df = p.load_all_rows()
print(df.shape); print(list(df.columns))
print(df["Date"].min(), df["Date"].max(), df["Date"].nunique())
for c in ("Venue","Track","Distance","Draw","Barrier","Course"):
    if c in df: print(c, df[c].astype(str).value_counts().head(8).to_dict())
df.to_pickle(sys.argv[1])
