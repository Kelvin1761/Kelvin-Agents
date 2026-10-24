"""Read-only analysis from hash-verified, saved pre-tip NBA snapshots."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def _time(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def verified_published_reports(folder, target_date, firewall):
    root = Path(folder) / "_prediction_snapshots"
    seen = set()
    result = []
    for manifest_path in sorted(root.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text())
            captured = _time(manifest.get("created_at"))
            if (manifest.get("sport") != "nba"
                    or manifest.get("target_date") != target_date
                    or manifest.get("append_only") is not True
                    or manifest.get("snapshot_role") not in {"production", "final_refresh"}
                    or not captured or captured > datetime.now(timezone.utc)):
                continue
            files = {row["name"]: row for row in manifest["files"]}
            if len(files) != len(manifest["files"]):
                continue
            for tag in manifest.get("game_tags", []):
                if tag in manifest.get("blocked_game_tags", []):
                    continue
                if (tag in seen or not isinstance(tag, str)
                        or not all(c.isalnum() or c == "_" for c in tag)):
                    continue
                names = [f"Game_{tag}_Full_Analysis.md", f"Sportsbet_Odds_{tag}.json",
                         f"Game_{tag}_Full_Analysis.md.market_legs.json", f"nba_game_data_{tag}.json"]
                paths = [manifest_path.parent / name for name in names]
                if any(not path.resolve().is_relative_to(root.resolve()) or not path.is_file()
                       or hashlib.sha256(path.read_bytes()).hexdigest() != files[path.name]["sha256"]
                       or path.stat().st_size != files[path.name]["bytes"] for path in paths):
                    continue
                odds = json.loads(paths[1].read_text())
                tip = _time(odds.get("event_start_time"))
                if not tip or captured >= tip:
                    continue
                passed, _ = firewall(paths[0], paths[1], validation_time=captured)
                if passed is not True:
                    continue
                seen.add(tag)
                result.append((tag, paths[0], paths[1], captured.isoformat()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return result
