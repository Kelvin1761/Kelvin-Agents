"""EXP-20261113-09 引擎 A/B：歷史標準段速（EXP-20261113-08）放入段速維度。

預先登記（跑之前寫死）：
  值      sect_features.pkl（EXP-08）：first_v（前段對 6 季 PIT 標準、扣當日快慢）、total_v（全程，同樣）
          經 parsed/sectionals.jsonl.gz 嘅 (日期, 沙田/跑馬地, 場次, 馬號) → 烙號 接返引擎語料
  標準化  mean／SD 只用引擎語料**之前**（< 2026-04-01，2020–2025 季）嘅歷史行 —— 唔喺評估場次學任何嘢
  組件    z = clip((x − mean)/SD, ±2.5)；speed' = clip(speed + b × 9.45 × z)，0–100；冇值唔郁
          MATRIX_WEIGHTS 唔郁 → 段速維度份量上升，冇任何維度被減（Kelvin「段速最重要」）
  arm     主：FT = (z_first + z_total)/2，b = 0.5
          副：F（first_v）b = 0.5；T（total_v）b = 0.5（全報，唔揀最好嗰個）
  計分    picks = sort(raw + 0.1285 × Δspeed)；449／449 場 raw 排序 = 引擎 picks 已核對（EXP-05）
  判決    hkjc_eval_harness compare --stage4 fixed_rule（389 場）；Gold、Good 都唔可以負（Kelvin）；
          另做 null：同一組 z 喺場內隨機洗牌 200 次（同幅度、冇資訊），候選要高過 null 分佈
用法：python3 hkjc_arm_hist_sectional.py <labels_final.jsonl> <sect_features.pkl> <parsed sectionals.jsonl.gz> <outdir>
"""
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
from eval_metrics import race_metrics  # noqa: E402
from hkjc_racing_engine import scoring  # noqa: E402

W_SECT = scoring.MATRIX_WEIGHTS["sectional"]
SPEED_SD = 9.45
FIELDS = ("gold", "gold_strict", "good_positional", "champion", "top3_capture_at5", "ndcg_at5",
          "competitive_recall_at5", "top2_any_hit")


def main():
    lab, featp, secp, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(lab)]
    F = pd.read_pickle(featp)
    F["date"] = F.race.str[:10]
    hist = F[F.date < "2026-04-01"]
    st = {c: (hist[c].mean(), hist[c].std()) for c in ("first_v", "total_v")}
    print("標準化（2026-04 之前歷史）：", {k: (round(m, 4), round(s, 4)) for k, (m, s) in st.items()})
    feat = {(r.race, r.code): r for r in F.itertuples()}
    code_of = {}
    for line in gzip.open(secp, "rt", encoding="utf-8"):
        r = json.loads(line)
        ven = "HV" if "跑馬地" in str(r.get("venue")) or "Happy" in str(r.get("venue")) else "ST"
        for h in r["horses"]:
            if str(h.get("horse_no") or "").isdigit():
                code_of[(r["date"], ven, r["race_no"], int(h["horse_no"]))] = h["code"]

    def z(row, c):
        v = getattr(row, c, None) if row is not None else None
        if v is None or pd.isna(v):
            return None
        m, s = st[c]
        return max(-2.5, min(2.5, (v - m) / s))

    arms = {"FT_b50": ("FT", 0.5), "F_b50": ("F", 0.5), "T_b50": ("T", 0.5)}
    prepared, n_hit, n_all = [], 0, 0
    for x in rows:
        if "horses" not in x:
            continue
        ven = "HV" if "跑馬地" in x["venue"] else "ST"
        zs = {}
        for h in x["horses"]:
            n_all += 1
            code = code_of.get((x["date"], ven, x["race"], h["n"]))
            row = feat.get((f"{x['date']}|{ven}|{x['race']}", code)) if code else None
            zf, zt = z(row, "first_v"), z(row, "total_v")
            zs[h["n"]] = {"F": zf, "T": zt, "FT": None if zf is None or zt is None else (zf + zt) / 2}
            n_hit += zf is not None
        prepared.append((x, zs))
    zmap = {id(x): zs for x, zs in prepared}
    # null 同 harness 一樣剔走 speed_score 死咗嘅場次
    prepared = [(x, zs) for x, zs in prepared if "speed_score" not in (x.get("meeting_dead_fields") or [])]
    print(f"null 場次 {len(prepared)}；覆蓋：{n_hit}/{n_all} 匹（{n_hit / n_all * 100:.1f}%）有 first_v")

    def score(x, zs, kind, b, perm=None):
        hs = x["horses"]
        ns = [h["n"] for h in hs]
        zz = [zs[n][kind] for n in ns]
        if perm is not None:
            zz = list(np.array(zz, dtype=object)[perm])
        s = []
        for h, zv in zip(hs, zz):
            sp = h["f"]["speed_score"]
            sp2 = sp if zv is None else max(0.0, min(100.0, sp + b * SPEED_SD * zv))
            s.append(h["raw"] + W_SECT * (sp2 - sp))
        s, ns = np.array(s), np.array(ns)
        return [int(v) for v in ns[np.lexsort((ns, -s))]]

    def metrics(x, picks):
        pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}
        top = [k for k, p in pos.items() if p <= 3]
        m = race_metrics(picks, top, actual_pos=pos)
        m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
        return m

    for arm, (kind, b) in arms.items():
        moved = 0
        with open(out / f"lab_hist_{arm}.jsonl", "w") as fh:
            for x in rows:
                if "horses" not in x:
                    fh.write(json.dumps(x, ensure_ascii=False) + "\n")
                    continue
                zs = zmap[id(x)]
                picks = score(x, zs, kind, b)
                moved += picks != x["picks"]
                m = metrics(x, picks)
                y = dict(x, arm=arm, picks=picks, **{k: m.get(k) for k in FIELDS},
                         mean_top3_model_rank=m["mean_top3_model_rank"])
                fh.write(json.dumps(y, ensure_ascii=False) + "\n")
        print(f"{arm}：{moved} 場排名有郁")

    # null：場內洗牌 z（主 arm）
    rng = np.random.default_rng(11)
    keys = ("gold", "good_positional", "top3_capture_at5", "top2_any_hit")
    base = np.array([[float(bool(x[k])) if isinstance(x[k], bool) else float(x[k]) for k in keys] for x, _ in prepared])
    def arm_mat(kind, b, perm_fn=None):
        out_ = []
        for x, zs in prepared:
            perm = perm_fn(len(x["horses"])) if perm_fn else None
            m = metrics(x, score(x, zs, kind, b, perm))
            out_.append([float(m[k]) for k in keys])
        return np.array(out_)
    res = {}
    for arm, (kind, b) in arms.items():
        cand = arm_mat(kind, b).mean(0) - base.mean(0)
        null = np.array([arm_mat(kind, b, rng.permutation).mean(0) - base.mean(0) for _ in range(200)])
        res[arm] = {"cand": (cand * 100).round(2).tolist(),
                    "null_mean": (null.mean(0) * 100).round(2).tolist(),
                    "pct_null_below_cand": [float((null[:, i] < cand[i]).mean() * 100) for i in range(4)]}
        print(arm, "候選−基礎（Gold, Good, capture@5, 頭二）", res[arm]["cand"], "｜null 均值", res[arm]["null_mean"],
              "｜null 低過候選 %", res[arm]["pct_null_below_cand"], flush=True)
    json.dump(res, open(out / "hist_null.json", "w"), indent=1)


if __name__ == "__main__":
    main()
