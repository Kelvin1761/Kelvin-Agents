"""Speech-first long edit and comedy-first Reels; no fixed long-video budget."""
from pathlib import Path
import wave

import numpy as np

from .common import load, save


def voice_regions(project):
    project = Path(project)
    saved = project / "cache" / "vad-v1.json"
    if saved.exists():
        return load(saved)
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    with wave.open(str(project / "cache" / "audio.wav"), "rb") as stream:
        audio = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768
    parts = get_speech_timestamps(audio, vad_options=VadOptions(min_speech_duration_ms=250,
                                                              min_silence_duration_ms=650, speech_pad_ms=0))
    regions = [dict(start=s["start"] / 16000, end=s["end"] / 16000) for s in parts]
    save(saved, regions)
    return regions


def merge(clips, gap=0):
    merged = []
    for c in sorted(clips, key=lambda c: c["start"]):
        if merged and c["start"] <= merged[-1]["end"] + gap:
            merged[-1]["end"] = max(merged[-1]["end"], c["end"])
            merged[-1]["reasons"] = sorted(set(merged[-1]["reasons"] + c["reasons"]))
        else:
            merged.append(dict(c))
    return merged


def select_conversation(analysis, voice, duration, funny_segments=(), gap=.3):
    from .selection import REACTIONS, overlap
    clips = [dict(start=max(0, c["start"] - .35), end=min(duration, c["end"] + .5),
                  score=0, reasons=["voice conversation (VAD, unverified)"]) for c in voice]
    # Retain strong gameplay even where no one speaks; menus can still host conversation.
    for row in analysis["rows"]:
        if (row["active"] and row["score"] >= .72 and row["effects_norm"] > .65
                and row["motion_norm"] > .6):
            clips.append(dict(start=max(0, row["start"] - 12), end=min(duration, row["end"] + 18),
                              score=row["score"], reasons=["intense gameplay context"]))
    for s in funny_segments:
        if any(w in s["text"].lower() for w in ("巴龍", "食龍", "小龍", "大龍", "baron", "dragon")):
            clips.append(dict(start=max(0, s["start"] - 12), end=min(duration, s["end"] + 15),
                              score=0, reasons=["spoken objective; review event"]))
    rows = analysis["rows"]
    for i, row in enumerate(rows[1:], 1):
        if rows[i-1].get("gameplay_present") and not row.get("gameplay_present"):
            upcoming = rows[i:i+4]
            recent = rows[max(0,i-4):i]
            if (len(upcoming) == 4 and not any(r.get("gameplay_present") for r in upcoming)
                    and any(r["score"] >= .72 for r in recent)):
                clips.append(dict(start=max(0,row["start"]-15), end=min(duration,row["start"]+15),
                                  score=0, reasons=["possible match ending; review Victory/Defeat"]))
    highlights = merge(clips, gap)
    jokes = []
    for s in funny_segments:
        text = s["text"].lower()
        confirmed = s.get("funny", False)
        if confirmed or (s.get("reviewed",False) and any(w in text for w in REACTIONS)):
            jokes.append(dict(peak=(s["start"] + s["end"]) / 2,
                              score=1 if confirmed else .5,
                              reasons=["reviewer marked funny" if confirmed else "reaction phrase; review joke"],
                              text=s["text"]))
    shorts = []
    for j in sorted(jokes, key=lambda j: (-j["score"], j["peak"])):
        if duration < 30:
            continue
        start = max(0, min(duration - 30, j["peak"] - 12))
        clip = dict(j, start=start, end=start + 30)
        if all(not overlap(clip, old, 15) for old in shorts):
            shorts.append(clip)
        if len(shorts) == 5:
            break
    return dict(revision=1, mode="conversation", highlights=highlights, shorts=shorts,
                target_seconds=None, selected_seconds=sum(c["end"] - c["start"] for c in highlights),
                notes=["Keep speech in any phase; trim long speech gaps; retain intense gameplay.",
                       "Reels use funny/reaction candidates only; no action-only padding to five.",
                       "VAD on mixed game audio is approximate; review missed/false speech."])


def budget(selection, analysis, target, required=()):
    """Rank coherent conversation blocks; keep pinned moments and outcome context."""
    blocks, current = [], []
    for clip in selection["highlights"]:
        if current and (clip["start"]-current[0]["start"]>=60 or clip["start"]-current[-1]["end"]>15):
            blocks.append(current);current=[]
        current.append(clip)
    if current:
        blocks.append(current)
    keep=list(required)
    # First five minutes establish the pregame conversation; outcome candidates get priority.
    for clip in selection["highlights"]:
        if clip["start"]<300 or "possible match ending; review Victory/Defeat" in clip["reasons"]:
            keep.append(clip)
    keep=merge(keep)
    used=sum(c["end"]-c["start"] for c in keep)
    ranked=[]
    for block in blocks:
        a,b=block[0]["start"],block[-1]["end"]
        rows=[r for r in analysis["rows"] if a<=r["start"]<b]
        if not rows:
            continue
        score=(.45*np.mean([r["audio_rms_norm"] for r in rows])+
               .30*np.mean([r["audio_peak_norm"] for r in rows])+
               .15*max(r["score"] for r in rows)+
               .10*min(1,sum(c["end"]-c["start"] for c in block)/max(1,b-a)))
        ranked.append((score,a,block))
    for _,_,block in sorted(ranked,key=lambda item:(-item[0],item[1])):
        from .selection import overlap
        fresh=[c for c in block if all(not overlap(c,old) for old in keep)]
        length=sum(c["end"]-c["start"] for c in fresh)
        if length and used+length<=target:
            keep=merge(keep+fresh);used=sum(c["end"]-c["start"] for c in keep)
    selection.update(highlights=keep,selected_seconds=used,target_seconds=target,
                     notes=selection["notes"]+["Budget coherent conversation blocks; never truncate a pinned joke to fit."])
    return selection
