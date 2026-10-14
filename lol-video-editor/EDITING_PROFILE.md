# Current editing profile — 12 October 2026

User-approved direction, latest steering takes precedence over earlier duration requests:

- Long video aims for **25–30 minutes**, default target 28 minutes.
- Dialogue is the main story: pregame, queue, champion selection and in-game chat all qualify.
- Remove longer empty pauses while protecting word endings and context. Rank coherent conversation blocks instead of filling the time with all detected speech.
- Gameplay emphasizes important fights, objectives and match endings. These are heuristic candidates until reviewed.
- Queue/picking footage shows the **League client only**. Desktop footage without a confidently detected client is hidden; gameplay remains full-frame. Client detection is sampled and needs boundary review.
- Reels prioritize comedy. User-pinned jokes come first; unreviewed ASR reaction phrases are not automatically exported as comedy.
- Keep original audio; no speaker names on captions.
- Caption drafts use Hong Kong Traditional Chinese and preserve editable source times. Recognition errors must be corrected before burning captions into a publishable version.
- All renders are versioned. Models and large video work/export files go on the external disk.

For the 10.11 recording, `pins.json` protects the 芝心批 conversation (75–145s) in the long video. Its dedicated Reel retains dialogue and reactions from 78–143s, with longer gaps shortened to about 58s. Two game outcomes are also pinned (3720–3760s and 6651–6691s).

Recommended repeatable flow:

```bash
./run.sh analyze /path/to/recording.mp4 --output output
./run.sh select "$PROJECT" --mode conversation --target-minutes 28
./run.sh frame "$PROJECT"
./run.sh review "$PROJECT"
./run.sh render "$PROJECT" --export-root /Volumes/Kelvin\ Hardisk\ 1/WongChoi-Archive/scratch/session/renders
```

Explicit must-keep moments go in `PROJECT/pins.json` as `highlights` and `shorts`; Shorts may include ordered `clips` to trim internal gaps. Reselection always retains pins. Avoid rerunning `select` over a reviewed edit unless intentionally replacing it.

The first five minutes of 10.11 have 52 raw ASR draft segments. Prompt echoes and wrong words were observed; drafts are for editing, not verified captions. The full long video is not fully transcribed. The client-cropped long video and pinned Reel export without those draft subtitles.

When the user is happy with the actual cut, package this profile and the tested CLI sequence as a repository skill. Keep detection/rendering in Python, persist pins/caption corrections, check output duration/aspect/audio/framing, and explicitly report missing joke candidates or incomplete caption coverage. A skill standardizes execution; it does not guarantee ASR accuracy or subjective joke quality.
