"""Capture the real NBA renderer against immutable archived inputs; never publishes.

This is a software replay, not proof of point-in-time predictive performance.
Input hashes, failed cases and temporal warnings are retained rather than hidden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(tag):
    aliases = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}
    return "_".join(aliases.get(part, part) for part in tag.upper().split("_"))


def captured_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Australia/Sydney"))
    except (ValueError, TypeError):
        return None


def discover(corpus):
    cases, missing = [], []
    for game in sorted(corpus.glob("*/nba_game_data_*.json")):
        payload = json.loads(game.read_text())
        meta = payload.get("meta", {})
        tag = canonical(game.stem.removeprefix("nba_game_data_"))
        candidates = [path for path in game.parent.glob("Sportsbet_Odds_*.json")
                      if canonical(path.stem.removeprefix("Sportsbet_Odds_")) == tag]
        if len(candidates) != 1:
            missing.append({"game": str(game), "reason": "odds_absent_or_ambiguous", "matches": len(candidates)})
            continue
        odds = candidates[0]
        price = json.loads(odds.read_text())
        warnings = []
        tip = captured_time(meta.get("date"))
        for name, value in (("game_data", meta.get("extracted_at")), ("odds", price.get("extraction_time"))):
            captured = captured_time(value)
            if not captured or not tip:
                warnings.append(name + "_timestamp_unknown")
            elif captured >= tip:
                warnings.append(name + "_captured_post_tip")
        if not price.get("event_start_time"):
            warnings.append("odds_event_start_unverified")
        case_id = game.parent.name.replace(" ", "_") + "__" + tag
        cases.append({"case_id": case_id, "game": str(game), "odds": str(odds),
                      "game_sha256": sha(game), "odds_sha256": sha(odds),
                      "game_date": str(meta.get("date", ""))[:10], "temporal_warnings": warnings})
    return {"cases": cases, "missing": missing}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if not os.path.ismount("/Volumes/Kelvin Hardisk 1"):
        raise SystemExit("external volume is not mounted")
    args.output.mkdir(parents=True, exist_ok=False)
    if args.manifest.exists():
        manifest = json.loads(args.manifest.read_text())
    else:
        manifest = discover(args.corpus)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    commit = subprocess.check_output(["git", "-C", str(args.code_root), "rev-parse", "HEAD"], text=True).strip()
    script = args.code_root / ".agents/skills/nba/nba_wong_choi/scripts/generate_nba_reports.py"
    results = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "WC_TELEGRAM_DISABLE": "1", "WC_DISABLE_POST_SUCCESS_DEPLOY": "1"}
    for case in manifest["cases"]:
        game, odds = Path(case["game"]), Path(case["odds"])
        if sha(game) != case["game_sha256"] or sha(odds) != case["odds_sha256"]:
            raise ValueError("immutable replay input changed")
        report = args.output / (case["case_id"] + ".md")
        run = subprocess.run([sys.executable, str(script), "--sportsbet", str(odds), "--extractor", str(game),
                              "--output", str(report)], capture_output=True, text=True, timeout=180, env=env)
        sidecar = Path(str(report) + ".market_legs.json")
        row = {"case_id": case["case_id"], "exit_code": run.returncode, "temporal_warnings": case["temporal_warnings"]}
        if run.returncode == 0 and sidecar.is_file():
            data = json.loads(sidecar.read_text())
            row.update({"legs": len(data["legs"]), "picked": sum(leg.get("picked", False) for leg in data["legs"]),
                        "combos": len(data["combos"]), "sidecar_sha256": sha(sidecar)})
        else:
            row["error_tail"] = (run.stderr + run.stdout)[-1500:]
        results.append(row)
        (args.output / "capture_summary.json").write_text(json.dumps({"code_commit": commit, "renderer_sha256": sha(script),
            "manifest_sha256": sha(args.manifest), "status": "running", "results": results}, indent=2) + "\n")
        print(json.dumps(row), flush=True)
    summary = {"code_commit": commit, "renderer_sha256": sha(script), "manifest_sha256": sha(args.manifest),
               "status": "complete", "results": results, "missing": manifest["missing"]}
    (args.output / "capture_summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
