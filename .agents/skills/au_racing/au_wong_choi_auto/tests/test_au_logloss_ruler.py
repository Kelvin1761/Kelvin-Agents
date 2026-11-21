"""AU log-loss 尺（Kelvin 2026-11-21，EXP-20261121-35）：A/A、噪音、真改善、護欄。"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_logloss_ruler as L  # noqa: E402


def corpus(days=45, races_per_day=12, seed=1):
    rng = random.Random(seed)
    out = []
    for d in range(days):
        date = f"2026-09-{1 + d % 30:02d}" if d < 30 else f"2026-10-{d - 29:02d}"
        for r in range(races_per_day):
            ab = [rng.gauss(60, 8) for _ in range(10)]
            noisy = sorted(range(10), key=lambda i: -(ab[i] + rng.gauss(0, 9)))
            pos = {i: k + 1 for k, i in enumerate(noisy)}
            out.append({"date": date, "meeting": f"m{d}", "race": r,
                        "rows": [{"ability": ab[i], "pos": pos[i]} for i in range(10)]})
    return L.eligible(out)


def test_aa_rejects():
    base = corpus()
    assert L.evaluate(base, base, nnull=0)["verdict"] == "REJECT"


def test_noise_rejects():
    base = corpus(); rng = random.Random(3)
    cand = [dict(r, rows=[dict(x, ability=x["ability"] + rng.gauss(0, 2)) for x in r["rows"]]) for r in base]
    assert L.evaluate(base, cand, nnull=30)["verdict"] == "REJECT"


def test_real_improvement_passes():
    base = corpus()
    cand = [dict(r, rows=[dict(x, ability=x["ability"] + (3.0 if x["pos"] <= 3 else 0.0)) for x in r["rows"]]) for r in base]
    v = L.evaluate(base, cand, nnull=30)
    assert v["verdict"] == "PASS" and v["dlogloss"][2] < 0


def test_mismatched_races_raise():
    base = corpus()
    try:
        L.evaluate(base, base[1:], nnull=0)
    except ValueError:
        return
    raise AssertionError("場次唔一致要拋錯")
