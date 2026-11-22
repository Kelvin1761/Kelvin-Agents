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


# ── v2（2026-11-23，EXP-20261123-01）：校準加 logit(3/N)、護欄改場內 AUC ──

def corpus_mixed(days=45, races_per_day=12, seed=2):
    """馬匹數 5–16 混合：v2 嘅 γ 先有嘢 fit。"""
    rng = random.Random(seed)
    out = []
    for d in range(days):
        date = f"2026-09-{1 + d % 30:02d}" if d < 30 else f"2026-10-{d - 29:02d}"
        for r in range(races_per_day):
            n = rng.randint(5, 16)
            ab = [rng.gauss(60, 8) for _ in range(n)]
            noisy = sorted(range(n), key=lambda i: -(ab[i] + rng.gauss(0, 9)))
            pos = {i: k + 1 for k, i in enumerate(noisy)}
            out.append({"date": date, "meeting": f"m{d}", "race": r,
                        "rows": [{"ability": ab[i], "pos": pos[i]} for i in range(n)]})
    return L.eligible(out)


def test_default_is_v2_and_v1_reproducible():
    base = corpus_mixed()
    assert L.evaluate(base, base, nnull=0)["version"] == "v2"
    v1 = L.evaluate(base, base, nnull=0, version="v1")
    assert v1["version"] == "v1" and "gold_good_guardrail" in v1["checks"]


def test_v2_field_size_term_improves_calibration():
    base = corpus_mixed()
    tot = {}
    for ver in ("v1", "v2"):
        cal = L.calibrations(base, ver)
        s = n = 0
        for r in base:
            if r["date"] in cal:
                a, b = L._nll(r, cal[r["date"]], version=ver)
                s, n = s + a, n + b
        tot[ver] = s / n
    assert tot["v2"] < tot["v1"]
    assert len(L.calibrations(base, "v2")[max(L.calibrations(base, "v2"))]) == 3


def test_v2_aa_noise_real():
    base = corpus_mixed(); rng = random.Random(5)
    assert L.evaluate(base, base, nnull=0)["verdict"] == "REJECT"
    noise = [dict(r, rows=[dict(x, ability=x["ability"] + rng.gauss(0, 2)) for x in r["rows"]]) for r in base]
    assert L.evaluate(base, noise, nnull=30)["verdict"] == "REJECT"
    real = [dict(r, rows=[dict(x, ability=x["ability"] + (3.0 if x["pos"] <= 3 else 0.0)) for x in r["rows"]]) for r in base]
    v = L.evaluate(base, real, nnull=30)
    assert v["verdict"] == "PASS" and v["auc_delta"][1] > 0


def test_v2_auc_guard_catches_ranking_harm():
    """同幅度場內洗牌（冇資訊）→ AUC 護欄一定唔過。"""
    base = corpus_mixed(); rng = random.Random(9)
    shuffled = []
    for r in base:
        d = [rng.gauss(0, 6) for _ in r["rows"]]
        shuffled.append(dict(r, rows=[dict(x, ability=x["ability"] + e) for x, e in zip(r["rows"], d)]))
    v = L.evaluate(base, shuffled, nnull=0)
    assert v["checks"]["auc_guardrail"] is False


def test_unknown_version_raises():
    base = corpus()
    try:
        L.evaluate(base, base, nnull=0, version="v9")
    except ValueError:
        return
    raise AssertionError("未知版本要拋錯")
