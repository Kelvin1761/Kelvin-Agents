"""EXP-20261116-17 post-hoc DESCRIPTIVE (not part of the verdict): F4 buckets and a close-price bet sim.
usage: python3 describe_f4.py <data dir>"""
import runpy, sys
import numpy as np
g = runpy.run_path(sys.argv[0].replace("describe_f4.py", "study.py"), run_name="study")
df, fit, lg, boot = g["df"], g["fit"], g["lg"], g["boot"]
ho = df[~df.dev]
print("\nholdout by F4 (matches in last 7 days, A minus B):")
for lo, hi in ((-9, -3), (-2, -1), (0, 0), (1, 2), (3, 9)):
    s = ho[(ho.F4 >= lo) & (ho.F4 <= hi)]
    print(f"  F4 in [{lo},{hi}]: n={len(s)} actual {s.y.mean():.3f} fair {s.fair.mean():.3f} gap {s.y.mean()-s.fair.mean():+.3f}")
# "the busier player" side, any |F4|>=2: actual vs fair of the busier player
for d, nm in ((df[df.dev], "dev"), (ho, "holdout")):
    s = d[d.F4.abs() >= 2]
    yb = np.where(s.F4 > 0, s.y, 1 - s.y); fb = np.where(s.F4 > 0, s.fair, 1 - s.fair)
    m, l, h = boot(yb - fb)
    print(f"  {nm} busier player (|F4|>=2) n={len(s)} actual {yb.mean():.3f} fair {fb.mean():.3f} gap {m:+.3f} [{l:+.3f},{h:+.3f}]")
