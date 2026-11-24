"""-07 重判：同 au_ability_redesign/pr_over_live_lib.py 一樣嘅介面（LIVE, base, by, L, J），
但 base = LIVE = 真 live dump（入面已經有練馬師剩餘表現、R2、老馬、F1），唔再人手加代理。"""
import collections, importlib.util, json, os, sys
from pathlib import Path
S = Path(__file__).resolve().parent
SC = S.parents[3] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
spec = importlib.util.spec_from_file_location("jtre", S.parent / "au_people_redesign/run.py"); J = importlib.util.module_from_spec(spec); spec.loader.exec_module(J)
L = J.L
base = L.eligible(json.loads(Path(os.environ["WC_REJUDGE_BASE"]).read_text())["races"])
LIVE = base
by = collections.defaultdict(list)
for i, r in enumerate(base):
    by[r["date"]].append(i)
