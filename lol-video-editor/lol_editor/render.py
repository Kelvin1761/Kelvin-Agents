from datetime import datetime, timezone
from pathlib import Path
import shutil

from .common import digest, load, lock, probe, project_analysis, run, save, validate_selection


def srt_time(seconds):
    ms = max(0, round(seconds * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def subtitles(transcript, clips):
    cues, offset = [], 0.
    for clip in clips:
        for segment in transcript:
            a, b = max(clip["start"], segment["start"]), min(clip["end"], segment["end"])
            if b > a:
                text = segment["text"].replace("\r", " ").replace("\n", " ")
                cues.append(f"{len(cues) + 1}\n{srt_time(offset + a - clip['start'])} --> "
                            f"{srt_time(offset + b - clip['start'])}\n{text}\n")
        offset += clip.get("timeline_duration", clip["end"] - clip["start"])
    return "\n".join(cues)


def video_filter(kind, layout, height):
    width = int(height * 16 / 9) // 2 * 2 if kind == "highlights" else int(height * 9 / 16) // 2 * 2
    if kind == "shorts" and layout == "crop":
        fit = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    else:
        fit = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x10141c")
    return fit + ",setsar=1,fps=30,format=yuv420p", width


def render(project, layout="fit", subtitles_mode="off", height=720, preset="fast", export_root=None, only="all"):
    project = Path(project).resolve()
    with lock(project):
        manifest, analysis = project_analysis(project)
        selection = validate_selection(load(project / "selection.json"), manifest["media"]["duration"])
        if not selection["highlights"] or (not selection["shorts"] and selection.get("mode") != "conversation"):
            raise ValueError("No usable highlight/Shorts selection. Review scores or select with a lower threshold")
        if subtitles_mode != "off" and not analysis["transcript"]:
            raise ValueError("Subtitles requested but no transcript exists; run transcribe first")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        config = dict(layout=layout, subtitles=subtitles_mode, height=height, preset=preset, only=only)
        transcript = analysis["transcript"]
        if subtitles_mode != "off":
            from .captions import export_segments
            transcript = export_segments(project, manifest, analysis)
        root = Path(export_root) if export_root else project / "renders"
        export = root / (stamp + "-" + digest(dict(selection=selection, config=config)))
        export.mkdir(parents=True, exist_ok=False)
        save(export / "selection.json", selection)
        framing = load(project / "framing.json") if (project / "framing.json").exists() else None
        if framing:
            save(export / "framing.json", framing)
        if subtitles_mode != "off":
            save(export / "captions.json", dict(segments=transcript))
        save(export / "render.json", dict(status="rendering", config=config, source=manifest["source"],
                                         analysis_file=manifest["analysis_file"]))
        outputs = []
        try:
            groups = [("youtube", "highlights", sorted(selection["highlights"], key=lambda c: c["start"]))]
            groups += [(f"short_{i:02}", "shorts", c.get("clips", [c])) for i, c in enumerate(selection["shorts"], 1)]
            if only!="all":
                groups=[g for g in groups if g[1]==("highlights" if only=="youtube" else "shorts")]
            if not groups:
                raise ValueError("No clips for requested export")
            for name, kind, clips in groups:
                if framing:
                    from .framing import split
                    clips = split(clips, framing)
                work = export / ("work_" + name)
                work.mkdir()
                # Shorts use 720x1280 by default; --height controls the horizontal height.
                output_height = height if kind == "highlights" else int(height * 16 / 9) // 2 * 2
                vf, output_width = video_filter(kind, layout, output_height)
                parts, timed_clips = [], []
                print(f"Rendering {name}: {len(clips)} clip(s)", flush=True)
                for i, c in enumerate(clips):
                    from .framing import prefix
                    clip_filter = prefix(c) + vf
                    part = work / f"part_{i:04}.mp4"
                    # Keep every original audio track; do not replace, normalize or mute audio.
                    # Decode/re-encode audio for accurate cuts: AAC stream-copy can retain
                    # keyframe preroll and shift the entire clip when seeking before input.
                    run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-ss", c["start"], "-i",
                         manifest["source"]["path"], "-t", c["end"] - c["start"],
                         "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0", "-vf", clip_filter,
                         "-c:v", "libx264", "-preset", preset, "-crf", "21", "-c:a", "aac", "-b:a", "192k",
                         "-avoid_negative_ts", "make_zero", part])
                    parts.append(part)
                    timed_clips.append(dict(c, timeline_duration=probe(part)["duration"]))
                    print(f"  {name} clip {i + 1}/{len(clips)} complete", flush=True)
                # Generated ASCII basenames avoid concat escaping problems with source paths.
                playlist = work / "concat.txt"
                playlist.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
                final = export / (name + ".mp4")
                run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "concat", "-safe", "1", "-i",
                     playlist, "-map", "0", "-c", "copy", "-movflags", "+faststart", final])
                if subtitles_mode != "off":
                    srt = export / (name + ".srt")
                    subtitle_text = subtitles(transcript, timed_clips)
                    srt.write_text(subtitle_text, encoding="utf-8")
                    if subtitles_mode == "soft" and subtitle_text:
                        muxed = work / "subtitled.mp4"
                        run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", final, "-i", srt,
                             "-map", "0", "-map", "1:0", "-c", "copy", "-c:s", "mov_text",
                             "-metadata:s:s:0", "language=yue", "-movflags", "+faststart", muxed])
                        muxed.replace(final)
                    elif subtitles_mode == "burn" and subtitle_text:
                        import imageio_ffmpeg
                        local_srt = work / "captions.srt"
                        shutil.copyfile(srt, local_srt)
                        burned = work / "burned.mp4"
                        run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-nostdin", "-n", "-i", final,
                             "-vf", "subtitles=filename=captions.srt:force_style='FontName=PingFang HK,FontSize=20,Outline=1.5,MarginV=24'",
                             "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", preset,
                             "-crf", "21", "-c:a", "copy", "-movflags", "+faststart", burned], cwd=work)
                        burned.replace(final)
                actual = probe(final)
                expected = sum(c["end"] - c["start"] for c in clips)
                if abs(actual["duration"] - expected) > max(1.0, len(clips) * .15):
                    raise RuntimeError(f"{name} duration differs: {actual['duration']} vs {expected}")
                if (actual["width"], actual["height"]) != (output_width, output_height):
                    raise RuntimeError(f"Unexpected dimensions for {name}")
                if len(actual["audio"]) != len(manifest["media"]["audio"]):
                    raise RuntimeError(f"Audio tracks lost in {name}")
                outputs.append(dict(file=final.name, duration=actual["duration"],
                                    width=actual["width"], height=actual["height"],
                                    audio_tracks=len(actual["audio"])))
                shutil.rmtree(work)
            save(export / "render.json", dict(status="complete", config=config, source=manifest["source"],
                                              analysis_file=manifest["analysis_file"], outputs=outputs))
        except Exception as error:
            save(export / "render.json", dict(status="failed", config=config, error=str(error), outputs=outputs))
            raise
        print(f"Export complete: {export}", flush=True)
        return export
