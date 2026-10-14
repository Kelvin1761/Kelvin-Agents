# First real-recording evaluation — 12 October 2026 (Sydney)

MVP implementation and one-recording trial completed. This is a functional and sampled visual evaluation, not a measured precision/recall benchmark. No additional detector features were added after this trial.

## Input and reproducibility

- Original: `/Users/imac/Desktop/今晚十點 ｜ LOL 之夜 09.05.mp4`
- 8,226.737052 seconds (2:17:06.74), 1280×720, 30fps, stereo AAC.
- Original size: 1,513,411,339 bytes. Size and nanosecond mtime match the source identity captured before analysis and checked at render.
- SHA256 recorded after export: `2b9c82eefc19d52c4bbc20cea591eecb3fe7fa827f51de6eea5a4d5376e62727`. This is a future verification reference, not a before/after checksum comparison.
- Repo base HEAD at trial: `0116c740330db7f02f9d04d2884e211b1d494517`; implementation remains uncommitted in `lol-video-editor/`.
- Python environments: repo `.video_env` (Python 3.14, OpenCV 5.0, NumPy 2.5.3, local OpenAI Whisper) and isolated `/private/tmp/lol-video-venv` (Python 3.9, OpenCV 5.0, NumPy 2.0.2, faster-whisper 1.2.1).
- Analysis algorithm version: 2; active analysis `analysis-1910233dc6c5e2c6.json`.

Project:

`output/今晚十點 ｜ LOL 之夜 09.05-5990a7290112dd68/`

Export:

`output/今晚十點 ｜ LOL 之夜 09.05-5990a7290112dd68/renders/20261011T151518.813562Z-8766783ca3f77142/`

Folder timestamps use UTC; the evaluation date above uses Sydney time.

Commands (run from repo root unless stated):

```bash
lol-video-editor/run.sh analyze "/Users/imac/Desktop/今晚十點 ｜ LOL 之夜 09.05.mp4" \
  --output lol-video-editor/output

# Existing cached small.pt; no model download or audio upload.
PYTHONPATH=lol-video-editor .video_env/bin/python -m lol_editor.cli transcribe \
  "lol-video-editor/output/今晚十點 ｜ LOL 之夜 09.05-5990a7290112dd68" \
  --backend whisper --model /Users/imac/.cache/whisper/small.pt \
  --language zh --speech-budget 180

lol-video-editor/run.sh render \
  "lol-video-editor/output/今晚十點 ｜ LOL 之夜 09.05-5990a7290112dd68"

lol-video-editor/run.sh review \
  "lol-video-editor/output/今晚十點 ｜ LOL 之夜 09.05-5990a7290112dd68"
```

Analysis v1 ran first; after sampled review exposed post-game tails, v2 regenerated visual signals and selection while retaining the cached speech transcript. Audio cache was reused. No full-recording transcription was attempted.

## Results

| Check | Result |
|---|---|
| Full-recording coverage | 1,646 five-second feature windows |
| Analysis time | v1: 116.54s; v2: 125.71s (includes reused audio cache) |
| Selection | 25 source intervals, total exactly 1,500s |
| YouTube export | 1,500.580499s, 1280×720, one audio stream |
| Shorts | Five distinct source intervals; 30.023242s each, 720×1280, one audio stream each |
| Export status | Complete; dimensions, duration tolerance and audio stream count validated |
| Source preservation | No source write operations; identity unchanged; synthetic test also compares source bytes |
| Speech trial | 180s of source context, 25 transcript segments |
| Subtitles | Disabled for the trial due to noisy recognition and partial coverage |
| Browser review | Loaded actual source; seeking to Short 2 at 5185s displayed gameplay and ACE announcement |
| Rerendering | Tested on a synthetic recording: second export in a new folder, no analysis repeated |

Shorts source timestamps:

| Short | Start (s) | End (s) | Sampled content |
|---|---:|---:|---|
| 1 | 1735.5 | 1765.5 | Approach, turret event, then visible combat/spell activity |
| 2 | 5185.0 | 5215.0 | ACE/base fight and match-ending effects |
| 3 | 8090.5 | 8120.5 | Multiple champions and combat effects near mid lane |
| 4 | 4915.5 | 4945.5 | Combat around the Baron area |
| 5 | 7700.5 | 7730.5 | Combat context followed by a grey death view |

These descriptions are visual observations from sampled frames, not automated event labels or verified kill counts. Each source interval is separate from the others. Shorts may intentionally reuse moments included in the long highlight video.

## What the trial changed

The first selection caught high-activity gameplay but two of the five selected Shorts extended into the macOS desktop/client after a match. This exposed a flaw in relying on terrain colours and motion alone. The MVP now measures minimap edge structure and the health HUD, suppresses client/desktop windows, and bounds context to likely gameplay runs. In the revised selection, Short 2 shifts earlier to end at 5215s; the other former match-end Short is replaced by another fight. Sampled final frames at 28s of each exported Short show gameplay rather than the prior desktop tails.

An integration test also exposed a separate FFmpeg issue: audio stream-copy after input seeking retained keyframe preroll, making two synthetic clips total about 20s instead of 11s. Rendering now re-encodes audio to AAC while retaining every track and its content/volume. The corrected timing passes actual FFmpeg tests and the real export checks.

Speech recognition is functional but the cached small model is unreliable for this voice chat. It produced recognizable Cantonese fragments such as `唔係守到呀嘛` and `反殺番個人咩玩`, mixed with nonsensical or Mandarin-looking text. This is insufficient evidence for publishable captions or dependable comedy detection. The v3 Cantonese path is implemented using faster-whisper, but **large-v3-turbo/yue quality was not evaluated in this trial**. Its model must be provided locally or downloaded explicitly.

The padded vertical layout keeps all gameplay visible but makes the action small on a phone. Center crop is available for manual review; it was not used in this export because it can hide off-center action and HUD information.

## Test status

The dedicated eight-test suite passes, including real FFmpeg exports with two audio tracks, accurate timing, sidecar/soft subtitles (including untranscribed clips), analysis reuse, source byte preservation, versioned rerenders, batch continuation after a corrupt MP4, preservation of reviewed choices, changed-source refusal, review byte ranges, token checks and stale-revision rejection.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lol-video-editor \
  /private/tmp/lol-video-venv/bin/python -m unittest discover -s lol-video-editor/tests -v
./檢查.sh --quick
./檢查.sh
```

The HTTP test needs loopback binding access. It passed with that permission. Repo quick check passed. The full repository check failed in AU Wong Choi and HKJC daily-auto suites; the other listed suites passed. A focused follow-up reproduced a missing BeautifulSoup `lxml` parser in the repo test environment and `PermissionError` writing HKJC scheduler logs in the sandbox. These are outside this editor's files; they were not repaired here. AU data-contract checks also emitted the existing stale-baseline/new-field warnings. No commit or push was performed.

## Limits and next evaluation

Only one recording was analyzed; visual review sampled clips and inspected export metadata, rather than watching the entire 25-minute output or annotating every event. Kill recall, teamfight precision, voice excitement accuracy and joke detection remain unmeasured. Some normal movement can score highly and some low-volume jokes will be missed. The HUD heuristic assumes a conventional 16:9 LoL gameplay layout; overlays or different UI scales need review.

Before expanding features, watch the six exports and use the review interface to mark keeper/removal decisions. Next evaluate a local v3 Cantonese model on the same short speech samples and compare its text against what was actually spoken. Better verified kill detection or automatic vertical tracking should follow only after those editing-quality issues are assessed.
