import argparse
from pathlib import Path
import sys

from .common import load, lock, project_analysis, save


def positive(value):
    value = float(value)
    if not 0 < value < 100000:
        raise argparse.ArgumentTypeError("Must be positive and below 100000")
    return value


def parser():
    p = argparse.ArgumentParser(description="Local LoL editing: analyze → transcribe → select → review → render")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="Analyze an MP4 once; cache visual/audio signals")
    a.add_argument("recording", type=Path)
    a.add_argument("--output", type=Path, default=Path("output"))
    a.add_argument("--audio-track", type=int, default=0, help="Audio stream index used for scoring and ASR")
    t = sub.add_parser("transcribe", help="Add local Cantonese speech scores; no uploads")
    t.add_argument("project", type=Path)
    speech_arguments(t)
    s = sub.add_parser("select", help="Select from saved scores; replaces current reviewed selection")
    s.add_argument("project", type=Path)
    selection_arguments(s)
    r = sub.add_parser("render", help="Versioned export from saved selection, without analysis")
    r.add_argument("project", type=Path)
    render_arguments(r)
    review = sub.add_parser("review", help="Local browser preview + timestamp editing")
    review.add_argument("project", type=Path)
    review.add_argument("--port", type=int, default=8765)
    frame = sub.add_parser("frame", help="Detect client-only crops and hide desktop")
    frame.add_argument("project", type=Path)
    b = sub.add_parser("batch", help="Process folder; continue other recordings if one fails")
    b.add_argument("input", type=Path)
    b.add_argument("--output", type=Path, default=Path("output"))
    b.add_argument("--audio-track", type=int, default=0)
    b.add_argument("--asr", action="store_true", help="Run local speech recognition before selection")
    b.add_argument("--analyze-only", action="store_true", help="Prepare selections for review without encoding")
    speech_arguments(b)
    selection_arguments(b)
    render_arguments(b)
    return p


def speech_arguments(p):
    p.add_argument("--model", default="large-v3-turbo", help="Model name or local model directory/.pt path")
    p.add_argument("--backend", choices=["faster-whisper", "whisper"], default="faster-whisper")
    p.add_argument("--language", default="yue", help="yue for v3 Cantonese; zh for small multilingual Whisper")
    p.add_argument("--speech-budget", type=positive, default=600, help="Seconds of high-scoring candidates to transcribe")
    p.add_argument("--full", action="store_true", help="Transcribe whole recording; slower, complete subtitle coverage")
    p.add_argument("--selected", action="store_true", help="Transcribe all selected long-video and Shorts intervals")
    p.add_argument("--prompt", default="廣東話遊戲對話：LOL、英雄聯盟、巴龍、團戰、閃現、反殺。")
    p.add_argument("--model-cache", type=Path, help="Model download/cache folder; use external disk for large models")
    p.add_argument("--download-model", action="store_true", help="Explicitly allow model download; inference stays local")


def selection_arguments(p):
    p.add_argument("--mode", choices=["action", "conversation"], default="conversation")
    p.add_argument("--target-minutes", type=positive, default=28)
    p.add_argument("--short-seconds", type=positive, default=30)
    p.add_argument("--threshold", type=float, default=.43)


def render_arguments(p):
    p.add_argument("--only", choices=["all", "youtube", "reels"], default="all")
    p.add_argument("--export-root", type=Path, help="External render folder for large exports")
    p.add_argument("--layout", choices=["fit", "crop"], default="fit", help="Shorts framing: keep full frame or crop center")
    p.add_argument("--subtitles", choices=["off", "srt", "soft", "burn"], default="off")
    p.add_argument("--height", type=int, choices=[360, 720, 1080], default=720)
    p.add_argument("--preset", choices=["ultrafast", "fast", "medium"], default="fast")


def choose(project, args, replace=True):
    from .selection import select
    with lock(project):
        manifest, analysis = project_analysis(project)
        path = project / "selection.json"
        if not replace and path.exists():
            return
        if args.mode == "conversation":
            from .conversation import voice_regions, select_conversation
            from .captions import document
            result = select_conversation(analysis, voice_regions(project), manifest["media"]["duration"],
                                         document(project, manifest, analysis)["segments"])
        else:
            result = select(analysis["rows"], manifest["media"]["duration"],
                            target=args.target_minutes * 60, short_seconds=args.short_seconds,
                            threshold=args.threshold)
        pins_path = project / "pins.json"
        if pins_path.exists():
            from .conversation import merge
            pins = load(pins_path)
            result["highlights"] = merge(result["highlights"] + pins.get("highlights", []))
            pinned_shorts = pins.get("shorts", [])
            from .selection import overlap
            result["shorts"] = (pinned_shorts + [c for c in result["shorts"]
                                                 if all(not overlap(c,p,15) for p in pinned_shorts)])[:5]
            result["selected_seconds"] = sum(c["end"] - c["start"] for c in result["highlights"])
        if args.mode=="conversation":
            from .conversation import budget
            required=load(pins_path).get("highlights",[]) if pins_path.exists() else []
            result=budget(result,analysis,args.target_minutes*60,required)
        if path.exists():
            current = load(path)
            save(project / "history" / f"selection-{current['revision']:06}.json", current)
            result["revision"] = current.get("revision", 0) + 1
        save(path, result)
        print(f"Selected {result['selected_seconds'] / 60:.1f} min ({args.mode}), "
              f"{len(result['shorts'])}/5 Shorts", flush=True)


def speech(project, args):
    from .analysis import transcribe
    transcribe(project, args.model, args.backend, args.language, args.speech_budget,
               args.download_model, args.full, args.selected, args.prompt, args.model_cache)


def export(project, args):
    from .render import render
    return render(project, args.layout, args.subtitles, args.height, args.preset, args.export_root, args.only)


def main():
    args = parser().parse_args()
    try:
        if args.command == "analyze":
            from .analysis import analyze
            print(analyze(args.recording, args.output, args.audio_track))
        elif args.command == "transcribe":
            speech(args.project, args)
        elif args.command == "select":
            choose(args.project, args)
        elif args.command == "render":
            export(args.project, args)
        elif args.command == "review":
            from .review import serve
            serve(args.project, args.port)
        elif args.command == "frame":
            from .framing import build
            build(args.project)
        elif args.command == "batch":
            from .analysis import analyze
            if not args.input.is_dir():
                raise ValueError("Input must be a folder")
            files = sorted(p for p in args.input.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")
            if not files:
                raise ValueError("No MP4 recordings in input folder")
            failures = []
            args.output.mkdir(parents=True, exist_ok=True)
            for recording in files:
                try:
                    project = analyze(recording, args.output, args.audio_track)
                    # Preserve reviewed choices on subsequent batch runs.
                    reviewed = load(project / "selection.json").get("reviewed", False)
                    if args.asr:
                        speech(project, args)
                    if not reviewed:
                        choose(project, args)
                    if not args.analyze_only:
                        export(project, args)
                except Exception as error:
                    print(f"FAILED {recording.name}: {error}", file=sys.stderr, flush=True)
                    failures.append(dict(recording=str(recording), error=str(error)))
            save(args.output / "batch-report.json", {"recordings": len(files), "failures": failures})
            return 1 if failures else 0
        return 0
    except (RuntimeError, ValueError, OSError, ImportError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
