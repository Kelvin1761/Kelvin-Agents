"""Per-race dataset from pre-race snapshots (2026-08-05..): model vs market by venue tier, plus race features."""
import csv, json, re, sys, datetime, collections
from pathlib import Path

REPO = "/Users/imac/Antigravity-repo/.agents/skills/shared_racing"
sys.path.insert(0, REPO); sys.path.insert(0, REPO + "/race_reflector/scripts")
from eval_metrics import race_metrics  # noqa: E402
from unified_reflector_core import load_structured_results, select_prerace_snapshot  # noqa: E402

AU = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing")
OUT = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/8642939c-b0ef-4bdf-8853-73c9f334012f/scratchpad/tier_rows.json")
METRO = {"flemington", "caulfield", "moonee valley", "the valley", "sandown", "sandown hillside", "sandown lakeside",
         "randwick", "royal randwick", "rosehill", "rosehill gardens", "warwick farm", "canterbury", "canterbury park",
         "eagle farm", "doomben", "morphettville", "morphettville parks", "ascot", "belmont", "belmont park"}
SCORING = ("form_quality_score", "pace_figure_score", "jockey_score", "trainer_score", "jockey_horse_fit_score",
           "rating_score", "track_score", "trial_score", "preparation_score", "class_score", "form_score",
           "performance_quality_score")


def tier(track, date, prize):
    t = track.lower().replace(" poly", "").replace(" synthetic", "").strip()
    sat = datetime.date.fromisoformat(date).weekday() == 5
    if t in METRO:
        return "metro_sat" if sat else "metro_mid"
    return "provincial" if prize >= 35000 else "country"


rows = []
dirs = [d for d in list(AU.iterdir()) + list((AU / "Archive").iterdir()) if d.is_dir() and re.match(r"2026-\d\d-\d\d ", d.name)]
for m in sorted(dirs):
    date = m.name[:10]
    if date < "2026-08-05":
        continue
    res_file = m / "Race_Results_Reflector.md"
    if not res_file.exists():
        continue
    snap, _c, _p = select_prerace_snapshot(m, platform="au")
    if snap is None:
        continue
    track = re.match(r"\d{4}-\d\d-\d\d (.+?) Race", m.name)
    track = track.group(1) if track else m.name[11:]
    early = {}
    try:
        od = json.loads((m / "Odds.json").read_text())
        snaps = sorted(od.get("snapshots") or [], key=lambda x: x.get("captured_at") or "")
        for sn in snaps:  # earliest price per race wins
            for rk, hs in (sn.get("races") or {}).items():
                if rk in early: continue
                early[rk] = {int(h): v.get("Sportsbet-FixedWin") for h, v in hs.items() if str(h).isdigit() and v.get("Sportsbet-FixedWin")}
    except Exception:
        pass
    try:
        results = load_structured_results("au", res_file)
    except Exception:
        continue
    for logic_path in snap.glob("Race_*_Logic.json"):
        try:
            L = json.loads(logic_path.read_text())
        except Exception:
            continue
        ra = L.get("race_analysis") or {}
        rn = int(ra.get("race_number") or re.search(r"Race_(\d+)", logic_path.name).group(1))
        info = results.get(rn) or {}
        res = info.get("results") or []
        if len(res) < 3:
            continue
        scratched = set(info.get("scratched_horse_numbers") or [])
        pos = {r["horse_no"]: int(r["placing"]) for r in res if str(r.get("placing", "")).isdigit()}
        top3 = {h for h, p in pos.items() if p <= 3}
        horses = []
        for num, h in (L.get("horses") or {}).items():
            try:
                num = int(num)
            except ValueError:
                continue
            if num in scratched or num not in pos:
                continue
            pa = h.get("python_auto") or {}
            fs = pa.get("feature_scores") or {}
            score = pa.get("final_rank_score") or pa.get("composite_score") or pa.get("ability_score")
            if score is None:
                continue
            defaults = sum(1 for k in SCORING if k in fs and abs(float(fs[k]) - 60.0) < 0.005)
            starts = h.get("career_race_starts")
            horses.append({"no": num, "score": float(score), "defaults": defaults,
                           "starts": int(starts) if isinstance(starts, (int, float)) else None, "pos": pos[num]})
        if len(horses) < 4:
            continue
        horses.sort(key=lambda x: -x["score"])
        picks = [x["no"] for x in horses]
        sp = {}
        for r in res:
            try:
                sp[r["horse_no"]] = float(str(r.get("odds") or "").replace("$", ""))
            except ValueError:
                pass
        mkt = sorted((h for h in pos if h in sp), key=lambda h: sp[h])
        if len(mkt) < 4:
            continue
        a = race_metrics(picks, top3, actual_pos=pos)
        b = race_metrics(mkt, top3, actual_pos=pos)
        try:
            prize = float(ra.get("prize") or 0)
        except (TypeError, ValueError):
            prize = 0.0
        scores = [x["score"] for x in horses]
        rows.append({
            "date": date, "meeting": m.name, "track": track, "race": rn, "tier": tier(track, date, prize),
            "prize": prize, "cls": str(ra.get("race_class") or ""), "dist": str(ra.get("distance") or ""),
            "going": str(ra.get("going") or ""), "field": len(horses),
            "fav_sp": sp[mkt[0]], "win_sp": sp.get(next(h for h, p in pos.items() if p == 1), None),
            "gap13": scores[0] - scores[2], "gap12": scores[0] - scores[1],
            "field_defaults_mean": sum(x["defaults"] for x in horses) / len(horses),
            "top3_defaults": [x["defaults"] for x in horses[:3]],
            "first_starters": sum(1 for x in horses if x["starts"] == 0),
            "low_exp": sum(1 for x in horses if x["starts"] is not None and x["starts"] <= 3),
            "model": {k: a[k] for k in ("gold", "exclusive_label", "top3_capture_at4", "pick_positions", "hits")},
            "market": {k: b[k] for k in ("gold", "exclusive_label", "top3_capture_at4", "pick_positions", "hits")},
            "top1_sp": sp.get(picks[0]), "picks": picks[:4],
            "early": {str(k): v for k, v in (early.get(str(rn)) or {}).items() if k in pos},
        })
json.dump(rows, open(OUT, "w"))
print(len(rows), "races", len({r["meeting"] for r in rows}), "meetings", collections.Counter(r["tier"] for r in rows))
