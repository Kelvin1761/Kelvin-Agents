#!/usr/bin/env python3
"""Harvest racenet starting prices for the scored archive meetings.

Kelvin does not use Betfair, so every strategy number has to be settled at a
price he can actually get on racenet. Locally we only had 34 races of racenet
SP, which is far too few to judge a strategy — this fills the archive.

Same timid pattern as au_extract_more_positions.py: one request at a time,
random 9-16s gaps, resume on every success, abort on the first block signal or
after 3 consecutive misses.

Caveat that must travel with the numbers: startingPrice is the CLOSING price.
It is the right settle price for an at-SP bet, but it does not prove the same
price was showing the day before when the analysis is published.
"""
import json, random, re, sys, time
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing")
from racenet_transport import fetch_nuxt_data, RacenetBlockedError

SCRATCH = Path("/Users/imac/Antigravity-repo/scratch")
OUT = SCRATCH / "au_racenet_sp.json"
DONE = SCRATCH / "au_racenet_sp_done.json"
TOTE = SCRATCH / "au_racenet_tote_sample.json"


def slug(meeting_dir):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.*?)(?:\s+Race\s|$)", meeting_dir)
    if not m:
        return None
    track = re.sub(r"[^a-z0-9 ]", "", m.group(4).lower()).strip().replace(" ", "-")
    return f"{track}-{m.group(1)}{m.group(2)}{m.group(3)}"


def deref(apollo, ref):
    return apollo.get(ref.get("id") or ref.get("__ref"), {}) if isinstance(ref, dict) else {}


def harvest(apollo):
    """{race_no: {horse_no: {name, pos, sp}}} — walks Event.selections, which is
    the only correct race->runner link (Selection keys carry no Event prefix)."""
    out = {}
    for value in apollo.values():
        if not (isinstance(value, dict) and value.get("__typename") == "Event"):
            continue
        rno = value.get("eventNumber")
        sels = value.get("selections") or []
        if not rno or not isinstance(sels, list):
            continue
        race = {}
        for ref in sels:
            sel = deref(apollo, ref)
            if not sel:
                continue
            num = sel.get("competitorNumber")
            if num is None:
                continue
            result = deref(apollo, sel.get("selectionResult")) or deref(apollo, sel.get("result"))
            try:
                pos = int((result or {}).get("finishPosition"))
            except (TypeError, ValueError):
                pos = None
            try:
                sp = float(sel.get("startingPrice"))
            except (TypeError, ValueError):
                sp = None
            comp = deref(apollo, sel.get("competitor"))
            if pos is not None and pos <= 0:
                pos = None            # -1 = scratched
            if sp is not None and sp <= 1.0:
                sp = None
            if pos is None and sp is None:
                continue
            race[str(num)] = {"name": comp.get("name"), "pos": pos, "sp": sp}
        if race:
            out[str(rno)] = race
    return out


def tote_sample(apollo):
    """Keep one raw tote-ish object so we can see whether place dividends exist."""
    for key, value in apollo.items():
        if isinstance(value, dict) and "tote" in json.dumps(value).lower()[:400]:
            return {key: value}
    return {}


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()

    meetings = json.loads((SCRATCH / "au_archive_meetings.json").read_text())
    targets = []
    for name in sorted(meetings, reverse=True):
        s = slug(name)
        if s and s not in done and s not in data:
            targets.append((name, s))

    print(f"候選 {len(targets)} 個存檔馬會日;本次上限 {budget} 個請求", flush=True)
    used = hits = misses = 0
    for name, s in targets:
        if used >= budget:
            print(f"\n達到上限 {budget},正常停止。", flush=True)
            break
        if used:
            time.sleep(random.uniform(9, 16))
        used += 1
        try:
            payload = fetch_nuxt_data(
                f"https://www.racenet.com.au/results/horse-racing/{s}/all-races")
        except RacenetBlockedError as exc:
            print(f"\n⛔ 被封訊號,立即停止:{exc}", flush=True)
            break
        except Exception as exc:
            misses += 1
            print(f"  ✗ {s} ({type(exc).__name__})", flush=True)
            if misses >= 3:
                print("\n⛔ 連續 3 次失敗,停止。", flush=True)
                break
            done.add(s)
            DONE.write_text(json.dumps(sorted(done)))
            continue

        apollo = ((payload.get("apollo") or {}).get("defaultClient")) or {}
        rows = harvest(apollo) if apollo else {}
        done.add(s)
        if rows:
            misses = 0
            hits += 1
            data[s] = {"meeting": name, "races": rows}
            OUT.write_text(json.dumps(data, ensure_ascii=False))
            if not TOTE.exists():
                sample = tote_sample(apollo)
                if sample:
                    TOTE.write_text(json.dumps(sample, ensure_ascii=False)[:20000])
            with_sp = sum(1 for r in rows.values() for h in r.values() if h.get("sp"))
            total = sum(len(r) for r in rows.values())
            print(f"  ✓ {s}: {len(rows)} 場、{total} 匹,其中 {with_sp} 匹有 SP", flush=True)
        else:
            misses += 1
            print(f"  – {s}: 冇數據", flush=True)
            if misses >= 3:
                print("\n⛔ 連續 3 次無數據,停止。", flush=True)
                break
        DONE.write_text(json.dumps(sorted(done)))

    sp_total = sum(1 for m in data.values() for r in m["races"].values()
                   for h in r.values() if h.get("sp"))
    print(f"\n用咗 {used} 個請求,成功 {hits};累計 {len(data)} 個馬會日、{sp_total} 個 SP")


if __name__ == "__main__":
    main()
