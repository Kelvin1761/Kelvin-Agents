import csv
import math
from pathlib import Path
import subprocess
import tempfile
import time
import wave

import numpy as np

from .common import digest, identity, load, lock, probe, run, save
from .selection import score_rows, select

VERSION = 2


def audio_features(source, cache, track, duration, window):
    wav = cache / "audio.wav"
    if not wav.exists():
        tmp = cache / "audio.partial.wav"
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", source, "-map", f"0:a:{track}",
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", tmp])
        tmp.replace(wav)
    rows = []
    with wave.open(str(wav), "rb") as stream:
        for i in range(math.ceil(duration / window)):
            a = np.frombuffer(stream.readframes(int(window * 16000)), dtype="<i2").astype(float) / 32768
            rows.append((float(np.sqrt(np.mean(a * a))) if a.size else 0,
                         float(np.max(np.abs(a))) if a.size else 0))
    return rows


def visual_features(source, duration, window=5, sample_fps=1):
    import cv2
    width, height = 320, 180
    frame_size = width * height * 3
    frames_per_window = int(window * sample_fps)
    rows, bucket, previous = [], [], None
    # FFmpeg decodes sequentially; OpenCV calculates signals without full-resolution storage.
    with tempfile.TemporaryFile() as err:
        command = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(source), "-an",
                   "-vf", f"fps={sample_fps},scale={width}:{height}", "-pix_fmt", "bgr24",
                   "-f", "rawvideo", "pipe:1"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err)
        count = 0
        try:
            while True:
                raw = process.stdout.read(frame_size)
                if not raw:
                    break
                if len(raw) != frame_size:
                    raise RuntimeError("Incomplete decoded video frame")
                frame = np.frombuffer(raw, np.uint8).reshape(height, width, 3)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                # Ignore bottom HUD + minimap and upper scoreboard for central activity.
                center = gray[25:140, 35:270]
                effect = (hsv[25:140, 35:270, 1] > 130) & (hsv[25:140, 35:270, 2] > 180)
                terrain = ((hsv[:, :, 0] >= 25) & (hsv[:, :, 0] <= 105)
                           & (hsv[:, :, 1] > 45) & (hsv[:, :, 2] > 25))
                feed = gray[25:90, 265:320]
                minimap_edges = np.mean(cv2.Canny(gray[138:174, 273:315], 60, 120) > 0)
                health = hsv[161:172, 115:222]
                health_green = np.mean((health[:, :, 0] > 35) & (health[:, :, 0] < 85)
                                       & (health[:, :, 1] > 90) & (health[:, :, 2] > 75))
                hud = float(minimap_edges > .16 or health_green > .045)
                if previous is None:
                    motion, feed_change, effects = 0., 0., 0.
                else:
                    motion = np.mean(cv2.absdiff(center, previous[0])) / 255
                    feed_change = np.mean(cv2.absdiff(feed, previous[1])) / 255
                    effects = np.mean(effect != previous[2])
                bucket.append((float(motion), float(feed_change), float(effects), float(terrain.mean()), hud))
                previous = (center.copy(), feed.copy(), effect.copy())
                count += 1
                if len(bucket) == frames_per_window:
                    values = np.mean(bucket, axis=0)
                    start = (count - len(bucket)) / sample_fps
                    rows.append(dict(start=start, end=min(duration, count / sample_fps),
                                     motion=values[0], feed_change=values[1], effects=values[2],
                                     gameplay=values[3], hud=values[4]))
                    bucket = []
                if count % int(300 * sample_fps) == 0:
                    print(f"Visual analysis: {count / sample_fps / 60:.0f}/{duration / 60:.0f} min", flush=True)
            if bucket:
                values = np.mean(bucket, axis=0)
                rows.append(dict(start=(count - len(bucket)) / sample_fps, end=duration,
                                 motion=values[0], feed_change=values[1], effects=values[2], gameplay=values[3], hud=values[4]))
            if process.wait():
                err.seek(0)
                raise RuntimeError(err.read().decode(errors="replace")[-4000:])
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if not rows:
        raise RuntimeError("No frames decoded")
    return rows


def analyze(source, output, audio_track=0):
    source_id = identity(source)
    folder = Path(output).resolve() / (Path(source).stem[:60] + "-" + digest(source_id))
    folder.mkdir(parents=True, exist_ok=True)
    with lock(folder):
        old_analysis = None
        if (folder / "project.json").exists():
            old = load(folder / "project.json")
            if old["audio_track"] != audio_track:
                raise ValueError("Audio track changed; use a different output root for a new analysis")
            old_analysis = load(folder / old["analysis_file"])
            if old_analysis["config"]["version"] == VERSION:
                print(f"Reusing saved analysis: {folder}", flush=True)
                return folder
        started = time.monotonic()
        meta = probe(source)
        if meta["audio"] and not 0 <= audio_track < len(meta["audio"]):
            raise ValueError("Audio track index does not exist")
        cache = folder / "cache"
        cache.mkdir(exist_ok=True)
        config = {"version": VERSION, "window": 5, "sample_fps": 1, "audio_track": audio_track}
        raw_path = cache / f"visual-v{VERSION}.json"
        if raw_path.exists():
            rows = load(raw_path)
        else:
            print(f"Analyzing {Path(source).name}: {meta['duration'] / 60:.1f} minutes", flush=True)
            rows = visual_features(source, meta["duration"])
            save(raw_path, rows)
        if meta["audio"]:
            audio = audio_features(source, cache, audio_track, meta["duration"], 5)
        else:
            audio = [(0, 0)] * len(rows)
        for i, row in enumerate(rows):
            row.update(audio_rms=audio[i][0], audio_peak=audio[i][1])
        transcript = old_analysis["transcript"] if old_analysis else []
        rows = score_rows(rows, transcript)
        analysis_name = "analysis-" + digest(config) + ".json"
        save(folder / analysis_name, {"config": config, "rows": rows, "transcript": transcript,
                                      "speech": old_analysis["speech"] if old_analysis else {"status": "not run"},
                                      "analysis_seconds": round(time.monotonic() - started, 2)})
        save(folder / "project.json", {"schema": 1, "source": source_id, "media": meta,
                                       "audio_track": audio_track, "analysis_file": analysis_name})
        selection_path = folder / "selection.json"
        if not selection_path.exists() or not load(selection_path).get("reviewed"):
            selection = select(rows, meta["duration"])
            if selection_path.exists():
                selection["revision"] = load(selection_path)["revision"] + 1
            save(selection_path, selection)
        export_scores(folder, rows)
        return folder


def export_scores(project, rows):
    with (Path(project) / "scores.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def transcribe(project, model, backend="faster-whisper", language="yue", budget=600,
               download=False, full=False, selected=False, prompt="", model_cache=None):
    from .common import project_analysis
    project = Path(project)
    with lock(project):
        manifest, analysis = project_analysis(project)
        if not manifest["media"]["audio"]:
            raise ValueError("Recording has no audio")
        if full and selected:
            raise ValueError("Choose --full or --selected")
        clip_selection = load(project / "selection.json") if selected else None
        config = dict(model=model, backend=backend, language=language, budget=budget, full=full,
                      selected=digest(clip_selection) if selected else None, prompt=prompt, schema=2)
        cached = project / ("transcript-" + digest(config) + ".json")
        if cached.exists():
            speech = load(cached)
        else:
            duration = manifest["media"]["duration"]
            if full:
                intervals = [(0, duration)]
            elif selected:
                from .conversation import merge
                combined = merge(clip_selection["highlights"] + clip_selection["shorts"])
                intervals = [(c["start"], c["end"]) for c in combined]
            else:
                selection = select(analysis["rows"], duration, target=budget)
                intervals = [(c["start"], c["end"]) for c in selection["highlights"]]
            if not intervals:
                raise ValueError("No speech candidates found; use --full to transcribe the recording")
            intervals = [(a + i * 60, min(b, a + (i + 1) * 60)) for a, b in intervals
                         for i in range(math.ceil((b - a) / 60))]
            download_root = Path(model_cache) if model_cache else project / "models"
            if download and "large" in model and model_cache is None:
                raise ValueError("Large model downloads need --model-cache on the external disk")
            if backend == "faster-whisper":
                from faster_whisper import WhisperModel
                recognizer = WhisperModel(model, device="cpu", compute_type="int8",
                                          download_root=str(download_root),
                                          local_files_only=not download)
            else:
                import whisper
                if language == "yue" and "large-v3" not in model:
                    raise ValueError("For small/medium Whisper use --language zh; native yue needs large-v3")
                if not Path(model).is_file() and not download:
                    raise ValueError("Provide a local .pt model or allow download with --download-model")
                recognizer = whisper.load_model(model, device="cpu", download_root=str(download_root))
            transcript = []
            for number, (start, end) in enumerate(intervals, 1):
                print(f"Local speech recognition {number}/{len(intervals)}: {start:.1f}–{end:.1f}s", flush=True)
                piece = project / "cache" / ("asr-" + digest(dict(config, start=start, end=end)) + ".json")
                if piece.exists():
                    transcript.extend(load(piece))
                    continue
                recognized = []
                with tempfile.TemporaryDirectory(dir=project / "cache") as tmp:
                    wav = Path(tmp) / "speech.wav"
                    run(["ffmpeg", "-v", "error", "-nostdin", "-ss", start, "-i",
                         manifest["source"]["path"], "-t", end - start, "-map",
                         f"0:a:{manifest['audio_track']}", "-vn", "-ac", "1", "-ar", "16000", wav])
                    if backend == "faster-whisper":
                        # Read our own fixed-rate WAV, avoiding PyAV version-dependent APIs.
                        with wave.open(str(wav), "rb") as audio_stream:
                            waveform = np.frombuffer(audio_stream.readframes(audio_stream.getnframes()),
                                                     dtype="<i2").astype(np.float32) / 32768
                        segments, _ = recognizer.transcribe(waveform, language=language,
                                                           task="transcribe", vad_filter=True,
                                                           condition_on_previous_text=False, beam_size=5,
                                                           initial_prompt=prompt or None)
                        segments = [dict(start=s.start, end=s.end, text=s.text,
                                         avg_logprob=s.avg_logprob, no_speech_prob=s.no_speech_prob) for s in segments]
                    else:
                        segments = recognizer.transcribe(str(wav), language=language, task="transcribe",
                                                         fp16=False, condition_on_previous_text=False)["segments"]
                    for s in segments:
                        a, b = max(start, start + float(s["start"])), min(end, start + float(s["end"]))
                        if a < b:
                            recognized.append(dict(start=a, end=b, text=s["text"].strip(),
                                                   avg_logprob=float(s.get("avg_logprob", -1)),
                                                   no_speech_prob=float(s.get("no_speech_prob", 0))))
                save(piece, recognized)
                transcript.extend(recognized)
            speech = {"segments": sorted(transcript, key=lambda s: s["start"]), "config": config,
                      "coverage": intervals, "status": "complete"}
            save(cached, speech)
        # Keep original analysis immutable; selections change only through explicit `select`.
        updated = dict(analysis, transcript=speech["segments"], speech=speech)
        updated["rows"] = score_rows(updated["rows"], speech["segments"])
        name = "analysis-speech-" + digest(dict(config, analysis_version=analysis["config"]["version"])) + ".json"
        save(project / name, updated)
        manifest["analysis_file"] = name
        save(project / "project.json", manifest)
        export_scores(project, updated["rows"])
        print("Speech scores saved. Run select to update clips, or keep your reviewed selection.", flush=True)
