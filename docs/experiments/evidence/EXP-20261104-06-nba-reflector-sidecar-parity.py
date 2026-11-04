"""EXP-20261104-06: reflector settlement before/after (no DB writes).

For every archived day with a Results_Brief: run verify_props_hits (Props_Verification JSON)
and build the reflector rows with that verification attached.

  PYTHONDONTWRITEBYTECODE=1 python3 <this> dump <repo_root> out.json
  python3 <this> compare before.json after.json
"""
import importlib.util, json, subprocess, sys, tempfile, collections
from pathlib import Path


def dump(repo, out_path):
    repo = Path(repo).resolve()
    scripts = repo / ".agents/skills/nba/nba_reflector/scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("refl", scripts / "nba_reflector_orchestrator.py")
    refl = importlib.util.module_from_spec(spec); spec.loader.exec_module(refl)
    root = Path.home() / "WongChoiData" / "Wong Choi NBA Analysis"
    out, tmp = {}, Path(tempfile.mkdtemp())
    for folder in sorted(root.glob("????-??-?? NBA Analysis")):
        day = folder.name[:10]
        us = refl.analysis_to_us_date(day)
        results = folder / f"Results_Brief_{us}.json"
        if not results.is_file():
            continue
        verification = tmp / f"{day}.json"
        subprocess.run([sys.executable, str(scripts / "verify_props_hits.py"), "--results", str(results),
                        "--predictions", str(folder), "--output", str(verification)], capture_output=True, text=True)
        payload = json.loads(verification.read_text())
        payload["legs"] = sorted(payload["legs"], key=lambda l: json.dumps(l, sort_keys=True, ensure_ascii=False))
        rows = refl.attach_verification(refl.load_prediction_rows(str(folder), day, us),
                                        refl.load_verification_index(str(verification)))
        out[day] = {"verification": payload, "rows": rows, "no_combos": refl.verified_no_combo_reports(str(folder))}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1, default=str))


def compare(before_path, after_path):
    a, b = json.load(open(before_path)), json.load(open(after_path))
    key = lambda r: (r["game_tag"], r["combo_id"], r["player_name"], r["prop_stat"], r["line"])  # noqa: E731
    fields, rows = collections.Counter(), 0
    for day in a:
        print(day, "verification identical" if a[day]["verification"] == b[day]["verification"] else "VERIFICATION DIFFERS",
              a[day]["verification"]["summary"]["hits"], "/", a[day]["verification"]["summary"]["total_legs"])
        left, right = {key(r): r for r in a[day]["rows"]}, {key(r): r for r in b[day]["rows"]}
        assert set(left) == set(right), f"{day}: different legs"
        for k, row in left.items():
            rows += 1
            fields.update(f for f in row if row[f] != right[k][f])
    print(rows, "rows; fields that differ:", dict(fields))


if __name__ == "__main__":
    {"dump": dump, "compare": compare}[sys.argv[1]](*sys.argv[2:])
