#!/usr/bin/env python3
"""Deepen the per-horse in-running history so the settling-habit feature can
cover more than 37.8% of big-field runners.

Kelvin's standing instruction: racenet is extremely fragile, must not get
blocked. So this is deliberately timid:
  * one request at a time, never concurrent;
  * random 9-16s gap between requests;
  * hard cap on requests per invocation (argv[1], default 20);
  * resumable — every success is written to disk immediately;
  * ABORTS on the first RacenetBlockedError, and also after 3 consecutive
    misses of any kind (a 404 storm means our slug guesses are wrong, and
    hammering wrong URLs is exactly what looks like scraping).

One meeting request carries every race's CompetitorPositionSummary, i.e. ~120
in-running records — vastly cheaper per record than per-horse pages, which
would need ~4,300 requests for the same job.
"""
import json, random, re, sys, time
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing")
from racenet_transport import fetch_nuxt_data, RacenetBlockedError

sys.path.insert(0, "/Users/imac/Antigravity-repo/scratch")
from au_extract_positions import harvest

SCRATCH = Path("/Users/imac/Antigravity-repo/scratch")
OUT = SCRATCH / "au_extra_positions.json"      # {slug: {race_no: {num: {...}}}}
NAMES = SCRATCH / "au_extra_positions_names.json"  # {slug: {race_no: {num: name}}}
DONE = SCRATCH / "au_extra_positions_done.json"    # attempted slugs (hit or miss)

# Metro slugs our archive horses actually rotate through.
SLUGS = ("randwick", "rosehill-gardens", "flemington", "caulfield",
         "moonee-valley", "warwick-farm", "sandown-lakeside", "eagle-farm")


def candidate_slugs():
    """Real (venue, date) meetings ranked by how many of OUR horses ran there.

    Built by au_extra_targets.json from the Betfair BSP archive: menu_hint gives
    the venue, event_dt the date, selection_name the runners — so both the
    meeting list and the yield ranking cost ZERO racenet requests. Guessing
    track/date combinations was the earlier mistake: it produced empty pages
    (and the wrong slug form, e.g. rosehill-gardens instead of rosehill).
    """
    targets = json.loads((SCRATCH / "au_extra_targets.json").read_text())
    return [t["slug"] for t in targets]


def already_covered():
    """Slugs we must not re-request: the 82 archive meetings plus prior attempts."""
    covered = set(json.loads(DONE.read_text())) if DONE.exists() else set()
    pos = json.loads((SCRATCH / "au_positions_map.json").read_text())
    for meeting in pos:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.*?)(?:\s+Race\s|$)", meeting)
        if m:
            track = re.sub(r"[^a-z0-9 ]", "", m.group(4).lower()).strip().replace(" ", "-")
            covered.add(f"{track}-{m.group(1)}{m.group(2)}{m.group(3)}")
    return covered


def harvest_names(ap):
    """{race_no: {competitor_number: horse_name}} so the join can verify identity."""
    events = {str(v.get("id")): v.get("eventNumber") for v in ap.values()
              if isinstance(v, dict) and v.get("__typename") == "Event" and v.get("eventNumber")}
    out = {}
    for key, value in ap.items():
        if not (isinstance(value, dict) and value.get("__typename") == "Selection"):
            continue
        num = value.get("competitorNumber")
        if num is None:
            continue
        m = re.search(r"Event:(\d+)", key)
        rno = events.get(m.group(1)) if m else None
        name = value.get("name") or value.get("competitorName")
        if rno and name:
            out.setdefault(str(rno), {})[str(num)] = name
    return out


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    names = json.loads(NAMES.read_text()) if NAMES.exists() else {}
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
    skip = already_covered()

    targets = [s for s in candidate_slugs() if s not in skip and s not in done]

    print(f"候選 {len(targets)} 個馬會日;本次上限 {budget} 個請求", flush=True)
    used = hits = consecutive_misses = 0
    for key in targets:
        if used >= budget:
            print(f"\n達到本次上限 {budget},正常停止。", flush=True)
            break
        if used:
            time.sleep(random.uniform(9, 16))
        used += 1
        url = f"https://www.racenet.com.au/results/horse-racing/{key}/all-races"
        try:
            payload = fetch_nuxt_data(url)
        except RacenetBlockedError as exc:
            print(f"\n⛔ 被封訊號,立即停止:{exc}", flush=True)
            break
        except Exception as exc:
            consecutive_misses += 1
            print(f"  ✗ {key} ({type(exc).__name__})", flush=True)
            if consecutive_misses >= 3:
                print("\n⛔ 連續 3 次失敗 — 停止(避免亂打錯 URL 似爬蟲)。", flush=True)
                break
            done.add(key)
            DONE.write_text(json.dumps(sorted(done)))
            continue

        apollo = ((payload.get("apollo") or {}).get("defaultClient")) or {}
        rows = harvest(apollo) if apollo else {}
        done.add(key)
        if rows:
            consecutive_misses = 0
            hits += 1
            data[key] = rows
            names[key] = harvest_names(apollo)
            records = sum(len(v) for v in rows.values())
            OUT.write_text(json.dumps(data))
            NAMES.write_text(json.dumps(names, ensure_ascii=False))
            print(f"  ✓ {key}: {len(rows)} 場、{records} 條跑位記錄", flush=True)
        else:
            consecutive_misses += 1
            print(f"  – {key}: 冇跑位數據（可能當日冇賽事）", flush=True)
            if consecutive_misses >= 3:
                print("\n⛔ 連續 3 次無數據 — 停止。", flush=True)
                break
        DONE.write_text(json.dumps(sorted(done)))

    total = sum(sum(len(v) for v in m.values()) for m in data.values())
    print(f"\n用咗 {used} 個請求,成功 {hits} 個;累計 {len(data)} 個馬會日、{total} 條跑位記錄")


if __name__ == "__main__":
    main()
