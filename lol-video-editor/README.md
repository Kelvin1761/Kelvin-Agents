# Local LoL video editor — MVP

Python, FFmpeg, OpenCV and local Whisper. No hosted inference, paid APIs, uploads, or changes to source recordings. Analysis and export are separate. See `EVALUATION.md` for the first real-recording trial.

**Latest profile:** [EDITING_PROFILE.md](EDITING_PROFILE.md) supersedes the first trial's action-heavy selection. Default reselection/batch now prioritizes coherent conversations, targets 28 minutes, and protects user-pinned jokes. `frame PROJECT` crops detected League client windows and hides desktop without a detected client. Inspect phase boundaries before publishing.

```bash
./run.sh select "$PROJECT" --mode conversation --target-minutes 28
./run.sh frame "$PROJECT"
./run.sh review "$PROJECT"     # 編輯字幕: edit text/time, replay, mark reviewed/funny, save
./run.sh render "$PROJECT" --only reels --export-root /path/on/external/disk
```

Caption edits live in `captions.json`, separately from recognition. `transcribe --selected` covers the chosen long-video/Reel intervals; `--full` covers the original recording. Recognition saves each minute separately for resumption. `--model-cache` must be supplied for large model downloads and should point to the external disk. `--subtitles burn` uses the bundled subtitle-capable FFmpeg; `srt` and `soft` remain available. Chinese font availability varies by OS. No speaker names are added. Captions from partial/uncorrected recognition remain drafts.

`pins.json` protects explicit must-keep moments through reselection; Reels can include ordered subclips to remove pauses. Comedy candidates require user pins, a funny mark, or reviewed reaction text. The 10.11 trial exports one confirmed 芝心批 Reel rather than filling five with unverified guesses.

## Setup

Install Python 3.9+ and FFmpeg (`ffmpeg` and `ffprobe` must be on PATH). On macOS: `brew install ffmpeg`. Then:

```bash
cd /Users/imac/Antigravity-repo/lol-video-editor
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run.sh --help
```

`run.sh` uses `.venv`, or the repo's existing `.video_env` if present. You can override the interpreter with `LOL_EDITOR_PYTHON`. The existing repo environment was used for the real speech trial. On Windows use `.venv\Scripts\python -m lol_editor.cli` instead of `./run.sh`.

## First recording

```bash
./run.sh analyze "/path/to/gameplay.mp4" --output output
```

The command prints its project folder. Use that path as `PROJECT` in these commands:

```bash
PROJECT="output/the-recording-project"

# Optional local voice analysis: first download needs internet; subsequent inference is local.
./run.sh transcribe "$PROJECT" --model large-v3-turbo --language yue --download-model
./run.sh select "$PROJECT" --target-minutes 25

# Preview source clips and edit start/end in seconds. Open the printed URL.
./run.sh review "$PROJECT"

# After saving and stopping review with Ctrl-C:
./run.sh render "$PROJECT"
```

Use a local CTranslate2 model directory with `--model /path/to/model` for fully offline speech recognition. Without `--download-model`, the tool only loads local/cached models. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) runs recognition locally; its named models are downloaded when allowed. `yue` is the Cantonese language code for the v3 models. Recognition uses CPU/int8 for portability; it can be slow on long recordings.

By default, speech recognition covers up to ten minutes of the highest-scoring contexts. This helps find reactions without transcribing two hours, but can miss jokes in quieter sections. Use `--speech-budget 180` for a short trial, or `--full` to scan everything and cover all subtitle timestamps. Model hallucinations, overlapping voices and game audio need review.

The optional alternative backend uses OpenAI Whisper: install `.venv/bin/python -m pip install -e '.[whisper]'`, then `transcribe "$PROJECT" --backend whisper --model /path/to/small.pt --language zh`. This smaller model does not have a native Cantonese language token. Its text quality is weaker; the first trial used a cached model this way.

`analyze` creates an initial audio/visual selection; speech and subtitles are optional. `transcribe` updates scores without replacing reviewed choices. Run `select` explicitly to choose again; it archives the previous selection. Batch also preserves any selection marked reviewed in the browser.

## Export and rerender

Default output is one `youtube.mp4` (1280×720, aiming for 25 minutes) and `short_01.mp4` through `short_05.mp4` (720×1280, about 30 seconds each). Highlights play chronologically. Shorts are ordered by score and separated in source time to prevent duplicate moments.

```bash
./run.sh render "$PROJECT" --layout crop           # Center crop; check that action/HUD stays visible
./run.sh render "$PROJECT" --subtitles srt         # Optional sidecar subtitles
./run.sh render "$PROJECT" --subtitles soft        # Selectable MP4 subtitles + SRT
./run.sh render "$PROJECT" --height 360 --preset ultrafast  # Quick preview export
```

The default Shorts layout fits the full gameplay frame inside a dark 9:16 canvas. It retains the HUD and off-center action, at the cost of smaller gameplay. Crop is an alternative, not automatic subject tracking. The review framing menu previews crop only; choose the corresponding `--layout` at export.

Every render gets a new folder under `PROJECT/renders/` with a frozen selection, settings, source identity and validated output metadata. Rerendering uses saved timestamps and never invokes OpenCV or speech recognition. All original audio tracks are retained, without volume changes or replacement music. Audio is re-encoded to AAC to ensure accurate cuts; it is not a bit-identical copy. Video is H.264 at 30fps. [FFmpeg's documentation](https://ffmpeg.org/ffmpeg-all.html) describes the stream mapping and encoding used here.

Subtitles are disabled by default. Candidate-only transcription produces partial subtitles; use `transcribe --full` before requesting full coverage. Soft subtitle mode skips clips without any transcribed speech. Player support for selectable subtitles varies; SRT is available separately. Burned-in subtitles are available with `--subtitles burn` after caption review.

## Batch

```bash
# Review-first pass over every MP4 directly in an input folder:
./run.sh batch /path/to/recordings --output output --analyze-only

# Automatic analysis + six exports per recording:
./run.sh batch /path/to/recordings --output output

# Include local Cantonese recognition before automatic selection/export:
./run.sh batch /path/to/recordings --output output --asr \
  --model /path/to/local-v3-model --language yue
```

Files are processed serially to bound memory and CPU use. A failure is reported in `batch-report.json`, other recordings continue, and the process exits nonzero if any failed. Existing analysis is reused. Re-running batch makes a fresh export, never overwriting previous videos. A changed source file gets a separate project. Subfolders are not scanned.

## What is selected

At one frame per second, OpenCV measures central motion, bright spell/effect changes, and activity in the kill-feed region. A HUD/minimap and terrain-colour heuristic suppresses loading/client/desktop footage. Five-second audio windows measure loudness and peaks. Local transcripts add Cantonese laughter/excitement and gameplay-event phrase signals.

These are **candidate signals**, not a trained teamfight detector, reliable kill counter, speaker emotion model or OCR. Camera pans can score highly, game effects can sound like excitement, HUD layouts differ, and a spoken kill may be speculation. The first trial identified fights and match-ending effects, and exposed desktop tails that were corrected by bounding clips to gameplay regions. Review the exported timing before publishing.

YouTube contexts normally retain 25 seconds before and 35 after a peak; Shorts retain around 12 seconds before and 18 after. Near match boundaries clips shift or shorten. Similar neighboring moments are suppressed by temporal separation. This prevents overlap but is not semantic detection of repeated footage. No quiet/low-scoring padding is added: a recording with too few usable moments may yield less than 25 minutes or fewer than five Shorts. The CLI and review page show the shortfall. Completely empty selections produce a clear error rather than empty videos.

## Saved data and review

- `project.json`: source path/size/mtime, media metadata and active analysis reference.
- `analysis-*.json`: versioned features, scores, reasons, speech coverage and source timestamps.
- `scores.csv`: five-second scores for inspection.
- `selection.json`: editable source timestamps and revision.
- `history/`: previous selections before manual saves or reselection.
- `transcript-*.json`: cached recognition results/configuration.
- `cache/`: mono analysis WAV and raw visual features.
- `renders/`: versioned exports and render manifests, with failed renders marked.

Source identity is checked before review/render. Use the same output root and audio track to reuse analysis; use a new output root to change the analysis audio track. `--audio-track` is the zero-based audio stream to analyze/transcribe (e.g. isolated voice chat). Every source audio track is still exported. The browser generally plays the first audio track.

Review is served on `127.0.0.1` with a per-run access token. It supports seeking into the original recording, previewing selected intervals, editing boundaries, adding/removing clips, inspecting scores/transcripts, and saving with validation. Edits reject out-of-range timestamps, overlapping clips and stale revisions. Invalid ranges are also rejected at export. Concurrent writers use an exclusive PID lock. If a process is killed, inspect the PID in `.writer.lock` before deleting a stale lock; do not delete a lock belonging to a running job.

The cache uses disk space: a 137-minute, 16kHz mono WAV is about 263MB, plus original-length ASR model downloads and video exports. Originals remain in their input folder.

## Validation

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

Tests exercise selection bounds, deduplication, quiet recordings, Cantonese keyword signals, timestamp validation, subtitle time remapping, concurrent writers, actual FFmpeg rendering with two audio tracks, cache reuse, source preservation, rerendering, and HTTP review seeking/saves. The HTTP test requires permission to bind a loopback port.
