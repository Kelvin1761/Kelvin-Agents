"""EXP-20261118-05 預先登記（Kelvin 2026-11-18「1/5 上名都加分？5/5 同 1/5 一樣？」；Holm 家族 2）
往績 = HKJC 馬匹頁存檔（parsed/horses.jsonl.gz），只用日期嚴格早過今仗；同程 = 準確同一路程（任何場地，同 live season_stats 同程）。
  S1  [同程 ≥2 戰 而且 上名率 > 2/3]
  S2  S1 ＋ [同程 0 戰（非初出）]（兩個 β）
β 逐季 walk-forward（只用之前季，2019/20 起），場內置中，加落 base raw（現行 live 同程三級保留）。base = v4/cons/base_fixed.jsonl。
判：hkjc_replay_compare_v4.py（Δlog-loss CI 上界 < 0、Gold／Good 下界 > −1.0pp、好過 null）；dev 唔過就唔開 holdout。
用法：python3 build.py <base.jsonl> <out_prefix>
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402

ARMS = {"S1": ["high"], "S2": ["high", "first"]}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def num(x):
    try: return float(str(x).strip())
    except ValueError: return None


def pos(x):
    s = str(x or "").strip(); return int(s) if s.isdigit() else None


def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    runs = defaultdict(list)
    for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        code = r["horse_id"].rsplit("_", 1)[-1]
        for q in r.get("runs") or []:
            try: runs[code].append((iso(q["date"]), num(q.get("distance")), pos(q.get("pos"))))
            except Exception: pass
    idx = b.load_index()
    code_of = {}
    for (d, n), race in idx["results"].items():
        for row in race.get("results", []):
            m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
            if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
    cover = [0, 0, 0, 0]
    F = {}
    for x in rows:
        mat = []
        for h in x["horses"]:
            hi = fi = 0.0
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            cover[0] += 1
            if c and c in runs:
                cover[1] += 1
                past = [t for t in runs[c] if t[0] < x["date"]]
                if past:
                    sd = [t for t in past if t[1] == x.get("distance")]
                    n = len(sd); pl = sum(1 for t in sd if t[2] and t[2] <= 3)
                    hi = float(n >= 2 and pl / n > 2 / 3)
                    fi = float(n == 0)
                    cover[2] += hi; cover[3] += fi
            mat.append([hi, fi])
        F[id(x)] = np.array(mat)
    print("馬次", cover[0], "有馬匹頁", cover[1], "high", int(cover[2]), "first", int(cover[3]), flush=True)
    by = defaultdict(list)
    for x in rows: by[season(x["date"])].append(x)
    for arm, keys in ARMS.items():
        cols = [["high", "first"].index(k) for k in keys]

        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep][:, cols]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z)
            sdv = Z.std(axis=0); sdv[sdv == 0] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / sdv]), Y).coef_[0]
            return (c[1:] / sdv) / (c[0] / R.std())
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, {s: [round(float(v), 2) for v in bb] for s, bb in betas.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"samedist_{arm}")
                if bb is not None:
                    add = F[id(x)][:, cols] @ bb; add = add - add.mean()
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
