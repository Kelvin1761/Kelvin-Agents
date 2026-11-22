"""EXP-20261123-06 判決：v2 尺（null 200），Holm（arm 數），連 wiring 檢查（幾多匹馬分數郁咗）。"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(W / ".agents/skills/shared_racing"))
import au_logloss_ruler as R  # noqa: E402

D = Path(sys.argv[1]); arms = sys.argv[2:]
raw = lambda n: json.loads((D / f"{n}.json").read_text())["races"]  # noqa: E731
B0 = raw("BASE"); base = R.eligible(B0)
res = {}
for a in arms:
    C0 = raw(a)
    moved = sum(abs(x["ability"] - y["ability"]) > 1e-6 for rb, rc in zip(B0, C0) for x, y in zip(rb["rows"], rc["rows"]))
    v = R.evaluate(base, R.eligible(C0), nnull=200)
    v["wiring_horses_moved"] = moved
    res[a] = v
# Holm：用 null 份額做單邊 p（1 − share），同 log-loss bootstrap 一樣方向
ps = sorted(((1 - (res[a]["beats_null_share"] or 0), a) for a in arms))
for i, (p, a) in enumerate(ps):
    res[a]["holm_p"] = min(1.0, p * (len(arms) - i))
for a in arms:
    v = res[a]
    print(f"{a}: {v['verdict']}/{v['reason']} 郁 {v['wiring_horses_moved']} 匹｜Δ {v['dlogloss'][0]:+.5f} [{v['dlogloss'][1]:+.5f},{v['dlogloss'][2]:+.5f}]"
          f"｜AUC {v['auc_delta'][0]:+.4f} [{v['auc_delta'][1]:+.4f}]｜Gold {v['gold_pp'][0]:+.2f}({v['gold_pp'][1]:+.2f}) Good {v['good_pp'][0]:+.2f}({v['good_pp'][1]:+.2f})"
          f"｜top2 {v['top2_any_hit_pp']:+.2f}｜null {v['beats_null_share']}｜Holm {v['holm_p']:.3f}")
(D / "judge.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))
