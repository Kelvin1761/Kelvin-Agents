import json,sys
import numpy as np
rows=[json.loads(l) for l in open(sys.argv[1])]; rows=[r for r in rows if "horses" in r]
D=["stability","trainer_signal","sectional","race_shape","horse_health","trackwork","distance_fit","form_line","class_advantage"]
L=["form_score","consistency_score","jockey_score","trainer_score","speed_score","race_shape_context_score","risk_score","weight_score","class_score","formline_strength_score","trackwork_trend_score","distance_score","same_distance_signal_score","margin_trend_score","confidence_score","draw_score"]
def demeaned(keys,src):
    X=[];raw=[]
    for r in rows:
        hs=[h for h in r["horses"] if not h.get("debut") and h.get("pos")]
        if len(hs)<4: continue
        M=np.array([[h[src][k] for k in keys]+[h["raw"]] for h in hs],float)
        X.append(M-M.mean(0))
    return np.vstack(X)
from scipy.stats import spearmanr
for keys,src in ((D,"m"),(L,"f")):
    X=demeaned(keys,src); C=spearmanr(X).correlation
    names=keys+["RAW"]
    print("      "+" ".join(f"{n[:6]:>6s}" for n in names))
    for i,n in enumerate(names): print(f"{n[:6]:>6s}"+" ".join(f"{C[i,j]:6.2f}" for j in range(len(names))))
    print()
