# 10.11 recording — conversation cut and 芝心批 Reel

Trial date: 12 October 2026, Sydney. Source: `/Users/imac/Desktop/今晚十點 ｜ LOL 之夜 10.11.mp4`, 6,699.607075 seconds, 1280×720, stereo audio, 924,008,991 bytes.

Source identity still matches the pre-analysis snapshot. SHA256: `a89e0561044ff4216438226265f5ce7f46a5eefe9c0c6a1a30c34f70a919c478`. The input is read only throughout this pipeline. Repo base HEAD: `0116c740330db7f02f9d04d2884e211b1d494517`; changes remain local/uncommitted.

## Latest user preferences

The user first requested retaining more conversation without a time limit, then revised the requirement to **25–30 minutes with fast pacing and focus**. The final selection therefore aims for 28 minutes, with dialogue in any phase and selected intense gameplay. Mandatory pins protect the complete 芝心批 conversation and both match endings.

The source conversation around 79–143 seconds discusses stuffed-crust pizza, money/principle and recording the moment as a highlight. The long-video pin is 75–145s. The dedicated Reel uses 78–143s, shortening longer gaps to approximately 58s while retaining dialogue and reactions. This is user-confirmed comedy; other unreviewed ASR reactions were not exported as additional Reels.

Game endings are pinned at 3720–3760s and 6651–6691s. Visual inspection confirmed Victory at 3743.4s and Defeat around 6673s, plus Nexus destruction and postgame transitions. Other fight/objective candidates remain heuristics; full event recall was not annotated.

Final framing-v3 export: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/lol-1011-edit/renders/20261012T114803.106892Z-ef4c55b50ce269ba/`. `youtube.mp4` is **1685.055404s (28:05)** at 1280×720; `short_01.mp4` is **57.985669s** at 720×1280. Both retain the audio stream and pass duration/aspect/audio validation. Sampled final output frames at 25, 90, 300, 900, 1500 and 1670s show hidden desktop, cropped client, gameplay and the Defeat screen as intended. Source identity was rechecked unchanged, and `latest-export.json` points to this corrected export.

## Client cropping evaluation

Initial detected client rectangles worked for the 芝心批 Reel, but sampled long-video frames exposed a flaw: remembered rectangles could crop wallpaper after the client closed, and some rectangles included narrow desktop strips. The first long-video candidate was marked superseded.

Framing version 3 checks dark window edges, trims bright outer edges, rejects wallpaper inside remembered boxes, and hides short visual intervals around mode/window transitions. If no safe client window is found on the desktop, the output shows a dark canvas with original audio. Gameplay retains the full frame. This can make client-open/close moments visually plain, but avoids intentionally displaying the desktop.

Rechecked source frames at 39s and 4661s now hide the wallpaper; source frames at 465s, 987s and 3925s show client-only crops. Victory/Defeat samples remain visible. Detection is sampled at 1fps and the entire output was not watched; this is sampled evidence, not a guarantee that every unusual overlay or window movement is classified correctly.

## Subtitles

Local CPU/int8 large-v3-turbo recognition was tested on the first five minutes and produced 52 draft segments. Cantonese mixed speech still yielded wrong words, long/poorly aligned cues, Mandarin-like phrasing, repeated filler, and glossary prompt echoes. In particular, glossary words appeared in a draft at 0s, so keyword presence alone was not treated as proof of a joke. The user-provided timestamp and surrounding dialogue established the mandatory clip.

These drafts are converted to Hong Kong Traditional Chinese and exposed in the review editor for replay, text/time correction, reviewed/funny marks and versioned saves. Caption edits are separate from raw recognition. **The full long video has not been fully transcribed; neither output burns these uncorrected drafts into the video.** Cantonese recognition quality is not considered solved.

The subtitle-capable bundled FFmpeg supports optional burn-in after correction. Tests also cover SRT timestamp remapping across cuts, actual multi-track exports and persistence of caption edits without changing raw analysis. Re-rendering does not repeat visual analysis or ASR. Each minute of recognition is separately cached to resume later.

## Reproduction

From the repo root:

```bash
PROJECT="lol-video-editor/output/今晚十點 ｜ LOL 之夜 10.11-58b7e6ff181046c2"
lol-video-editor/run.sh analyze "/Users/imac/Desktop/今晚十點 ｜ LOL 之夜 10.11.mp4" --output lol-video-editor/output
lol-video-editor/run.sh select "$PROJECT" --mode conversation --target-minutes 28
lol-video-editor/run.sh frame "$PROJECT"
lol-video-editor/run.sh review "$PROJECT" --port 8767
lol-video-editor/run.sh render "$PROJECT" \
  --export-root "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/lol-1011-edit/renders"
```

`pins.json`, `selection.json`, `framing.json`, source identity and active analysis are retained in the project. Each export freezes its selection and framing. Models and large render files are on the external disk; internal free space remained above 10GB.

## Validation

The 13 editor tests pass, including conversation budgeting with an uncut pin, nested Reel cut validation, wallpaper rejection, phase splitting, actual FFmpeg rendering/burn-in, source byte preservation, batch recovery, review seeking, caption saves and stale revisions. Review JavaScript syntax also passes.

Both `./檢查.sh --quick` and `./檢查.sh` were run. Quick checks passed. Full repo checks failed in the separate AU Wong Choi and HKJC daily-auto suites, as in the preceding trial. No racing code was changed and no commit/push was performed.

The stable editing preferences are recorded in `EDITING_PROFILE.md`. A repository skill can wrap those preferences and the tested commands after the user approves the cut; it should report incomplete captions and unverified joke/event candidates explicitly.
