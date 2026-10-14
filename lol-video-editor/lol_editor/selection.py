"""Explainable heuristics: candidate signals are not verified kills/teamfights."""
import numpy as np

REACTIONS = ("嘩", "哈哈", "笑死", "痴線", "黐線", "救命", "好勁", "屌", "仆街",
             "唔係呀", "唔係啊", "what", "oh my", "lol", "哈哈哈")
EVENTS = ("擊殺", "击杀", "殺咗", "杀", "反殺", "五殺", "四殺", "三殺", "雙殺", "double kill",
          "triple kill", "quadra", "penta", "baron", "巴龍", "大龍", "大龙", "團戰", "团战")


def normalize(values):
    values = np.asarray(values, dtype=float)
    lo, hi = np.percentile(values, [20, 95])
    if hi - lo < 1e-8:
        return np.zeros_like(values)
    return np.clip((values - lo) / (hi - lo), 0, 1)


def score_rows(rows, transcript):
    for field in ("motion", "effects", "feed_change", "audio_rms", "audio_peak"):
        norm = normalize([r[field] for r in rows])
        for row, value in zip(rows, norm):
            row[field + "_norm"] = round(float(value), 4)
    for row in rows:
        speech = [s for s in transcript if s["end"] > row["start"] and s["start"] < row["end"]]
        text = " ".join(s["text"] for s in speech).lower()
        reaction = any(word in text for word in REACTIONS)
        event = any(word in text for word in EVENTS)
        # Terrain colour and HUD structure are only a gameplay likelihood proxy.
        present = row["gameplay"] >= .12 and row.get("hud", 1) >= .3
        active = present and row["motion"] > .006
        score = (.30 * row["motion_norm"] + .25 * row["effects_norm"]
                 + .08 * row["feed_change_norm"] + .15 * row["audio_rms_norm"]
                 + .10 * row["audio_peak_norm"] + .08 * reaction + .04 * event)
        # Voice-only funny moments survive, but quiet static/menu footage is suppressed.
        if not active:
            score *= .6 if reaction else .12
        if reaction and present and row["audio_rms_norm"] > .5:
            score = max(score, .43 + .10 * row["audio_peak_norm"])
        row.update(score=round(score, 4), active=bool(active), gameplay_present=bool(present), text=text,
                   reasons=[name for name, yes in (
                       ("visual action", active and row["motion_norm"] > .65),
                       ("spell/effect activity", active and row["effects_norm"] > .65),
                       ("kill-feed region change (unverified)", active and row["feed_change_norm"] > .8),
                       ("audio excitement (game + voice)", row["audio_peak_norm"] > .75),
                       ("reaction phrase", reaction), ("spoken gameplay event", event)) if yes])
    return rows


def overlap(a, b, margin=0):
    return a["start"] < b["end"] + margin and b["start"] < a["end"] + margin


def select(rows, duration, target=1500, short_seconds=30, threshold=.43):
    regions = []
    for r in rows:
        if r.get("gameplay_present", r.get("active", True)):
            if regions and r["start"] - regions[-1][1] <= 5:
                regions[-1][1] = r["end"]
            else:
                regions.append([r["start"], r["end"]])

    def bounds(peak):
        region = next((r for r in regions if r[0] <= peak <= r[1]), None)
        # Reaction-only moments can live outside gameplay; keep their immediate context.
        return region if region else [max(0, peak - 25), min(duration, peak + 35)]

    # Peaks separated by 60s prevent the same fight being reused in different Shorts.
    peaks = []
    for row in sorted(rows, key=lambda r: (-r["score"], r["start"])):
        if row["score"] < threshold:
            continue
        center = (row["start"] + row["end"]) / 2
        if all(abs(center - p["peak"]) >= 60 for p in peaks):
            peaks.append({"peak": center, "score": row["score"], "reasons": row["reasons"]})
    shorts = []
    if duration >= short_seconds:
        for p in peaks:
            lower, upper = bounds(p["peak"])
            if upper - lower < short_seconds:
                continue
            start = max(lower, min(upper - short_seconds, p["peak"] - short_seconds * .4))
            c = dict(p, start=round(start, 3), end=round(start + short_seconds, 3))
            if all(not overlap(c, old, 10) for old in shorts):
                shorts.append(c)
            if len(shorts) == 5:
                break
    chosen = []
    used = 0
    for p in peaks:
        if used >= target - 1:
            break
        # A minute around each peak retains approach + fight + outcome.
        lower, upper = bounds(p["peak"])
        start, end = max(lower, p["peak"] - 25), min(upper, p["peak"] + 35)
        if end - start < 20:
            continue
        c = dict(p, start=round(start, 3), end=round(end, 3))
        if any(overlap(c, old) for old in chosen):
            continue
        remaining = target - used
        if end - start > remaining:
            if remaining < 20:
                break
            start = max(lower, min(upper - remaining, p["peak"] - remaining * .4))
            c.update(start=round(start, 3), end=round(start + remaining, 3))
            if any(overlap(c, old) for old in chosen):
                continue
        chosen.append(c)
        used += c["end"] - c["start"]
    chosen.sort(key=lambda c: c["start"])
    # Adjacent highlights can be joined without a jump cut.
    merged = []
    for c in chosen:
        if merged and c["start"] - merged[-1]["end"] <= .05:
            merged[-1]["end"] = c["end"]
            merged[-1]["reasons"] = sorted(set(merged[-1]["reasons"] + c["reasons"]))
        else:
            merged.append(c)
    return {"revision": 1, "highlights": merged, "shorts": shorts,
            "target_seconds": target, "selected_seconds": round(used, 3),
            "notes": ["Selection uses heuristics; review context and vertical framing.",
                      "No low-scoring padding is added to meet a duration or Shorts count."]}
