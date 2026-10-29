"""Arm: trackwork rebuilt from point-in-time rows only (EXP-20261029-01 A, §7).

The 晨操 table mixes in race rows (type_raw 出賽): previous races inside the
21-day window, and — when the file was extracted after the meeting — today's
race itself.  Those rows made 「賽日騎師有參與操練」 fire for riding a race,
and counted race days as work days.  Treadmill rows whose details mention
快操／踱步 were counted as gallops／trotting.

Fixed rule, nothing fitted: keep rows dated before race day that are not race
rows; treadmill by type_raw; old-format rows (no final_time, 2026-05) re-parsed
from details; recompute digest／summary／the three text lines.
"""
import datetime as dt
import re
import sys
from pathlib import Path

ARM_NAME = "trackwork_pit_clean"

REPO = Path(__file__).resolve().parents[3]
for sub in ("hkjc_race_extractor/scripts", "hkjc_wong_choi/scripts"):
    p = str(REPO / ".agents/skills/hkjc_racing" / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def clean_entries(entries, race_date):
    out = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("type_raw") or "") == "出賽":
            continue
        if race_date and str(e.get("date") or "") >= race_date:
            continue
        e = dict(e)
        if "final_time" not in e:  # 2026-05 舊格式：times 係段速同總時間撈埋一齊
            import extract_trackwork as xt
            timing = xt.parse_work_times(e.get("details") or "")
            e["sectionals"] = e["times"] = timing["sectionals"]
            e["final_time"] = timing["final_time"]
        if "跑步機" in str(e.get("type_raw") or ""):
            e["type"] = "treadmill"
        out.append(e)
    return out


def rebuild(horse_obj, race_date):
    import extract_trackwork as xt
    import create_hkjc_logic_skeleton as sk

    tw = horse_obj.get("trackwork")
    if not isinstance(tw, dict) or not tw.get("entries"):
        return False
    data = horse_obj.get("_data") if isinstance(horse_obj.get("_data"), dict) else {}
    if not data.get("trackwork_digest"):
        return False  # 原本冇 digest 嘅唔好喺呢個 arm 憑空加
    entries = clean_entries(tw["entries"], race_date)
    window = int((tw.get("stability_digest") or {}).get("window_days") or 21)
    jockey = horse_obj.get("jockey") or tw.get("jockey") or ""
    digest = xt.make_digest(tw, entries, window, jockey)
    new = dict(tw)
    new["entries"] = entries
    new["stability_digest"] = digest
    new["summary"] = xt.summarize_trackwork(tw, entries, digest)
    new["status"] = "ok" if entries else "missing"
    finishes = data.get("last_6") or horse_obj.get("last_6_finishes") or ""
    is_debut = bool(horse_obj.get("is_debut"))
    new = sk.normalize_trackwork_category(
        new, {"last_6": finishes, "wins": horse_obj.get("wins", 0)}, is_debut)
    horse_obj["trackwork"] = new
    if isinstance(horse_obj.get("_data"), dict):
        horse_obj["_data"]["trackwork_digest"] = sk.format_trackwork_line(new)
        horse_obj["_data"]["trackwork_trainer"] = sk.format_trackwork_trainer_line(new)
        horse_obj["_data"]["trackwork_health"] = sk.format_trackwork_health_line(new)
    return True


def apply():
    import hkjc_auto_orchestrator as orch
    # 喺 harness redirect_stdout 之外 import：兩個 module import 時會包 sys.stdout.buffer
    import extract_trackwork  # noqa: F401
    import create_hkjc_logic_skeleton  # noqa: F401

    original = orch._align_runner_headers

    def patched(race_file, race_context, horses):
        result = original(race_file, race_context, horses)
        m = re.match(r"(\d{4}-\d{2}-\d{2})", Path(race_file).parent.name)
        race_date = m.group(1) if m else ""
        for horse in (horses or {}).values():
            if isinstance(horse, dict):
                rebuild(horse, race_date)
        return result

    orch._align_runner_headers = patched
