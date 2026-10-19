# Stage 5 byte-reader release gate checkpoint — 2026-10-19

This audit is saved on a separate non-main evidence branch. It does not change
the frozen release input or authorize another release. Do not merge this audit
branch while the original controller's approval recheck is live: main must
remain equal to the captured rollback target.

## First-gate handoff inspection

The original controller completed its first full repository gate with exit 0,
committed/pushed the immutable nine-path research-only release, and started the
existing clean-checkout approval **full-gate recheck**. The following facts were
observed at that handoff; they are not a claim that the recheck, merge or
activation has completed. Effective later status must be read from append-only
release events, not inferred from this checkpoint or the immutable manifest.

```json
{
  "release_id": "wc-release:ea95996493ed:2026-10-19T054159.794232_0000",
  "manifest": "/Users/imac/WongChoiData/WongChoiControl/releases/wc-release%3Aea95996493ed%3A2026-10-19T054159.794232_0000.json",
  "manifest_sha256": "f603fe8abdaa57f5d8159d7108f7f2588d12469fe10cb7ee85ae21fa9ecec41e",
  "commit": "ea95996493ed58187bf6f219f63a0c4c02ac14ab",
  "rollback_target": "ffc9111118a08eab801f64ef5c3c3d11e92882eb",
  "input_snapshot": "7fdf00bb82d19e2ab16ea2fddd16073061535d6c",
  "tree": "f06e597afa2a46d71debaf3ba2b50143f068e1eb",
  "first_full_gate_exit": 0,
  "risk": "code",
  "scope_paths": 9,
  "remote_verified": "release branch equals commit; main equals rollback target",
  "pending_stage5_release_count": 1,
  "pending_inspection_at": "2026-10-19T05:43:52.781851+00:00",
  "approval_checkout": "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-vnua_o21/wc-release-approval-5zvfijli/checkout",
  "approval_checkout_verified": "clean; detached HEAD and tree equal immutable release",
  "controller_session": 17881,
  "controller_pid": 48488,
  "activation_plan": {
    "domains": [
      "au",
      "hkjc",
      "nba",
      "tennis"
    ],
    "installers": [],
    "dashboard_deploy": false,
    "manual_reasons": []
  }
}
```

Scope comprises five shared research reader/index/snapshot/inventory files,
two matching test files, the Stage 5 byte-reader audit and Stage 5 plan. No ruler,
evaluation-contract, scoring/feature/weight/domain engine, release-policy,
production adapter, scheduler/installer, Dashboard, credential, deletion,
ledger, bankroll or promotion path is included.

The branch and fresh remote main were independently read with ls-remote.
Exactly one Stage-5-named pending release was observed. The actual recheck pytest
cwd was read through lsof and its Git HEAD, tree and clean status verified.
No second approve or duplicate controller was started.

## First full-gate phase observations

These four native test-fixture phases were read while the first full gate ran.
All reported succeeded/receipt_verified, with the unchanged 600-second phase
limits. Sample counts are fixture labels, not production or pilot evidence.
The exact phase hashes were captured before later pytest sessions pruned old
temporary fixtures. These are contemporaneous observations, not a claim that
those ephemeral files are still available for a restore drill or model proof.

Common fixture prefix:
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-vnua_o21/pytest-of-imac/pytest-8/`

```json
[
  {
    "gate": "first",
    "scratch": "wc-run-vnua_o21",
    "fixture": "test_large_monitoring_corpus_a0",
    "domain": "au",
    "action": "racing-monitoring-corpus",
    "phase": "racing-monitoring-corpus-pahcaht1",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 491.04363820900005,
    "outcome_sha256": "c6f6dad5485a9ed74bdc93165250ed6da670863359dba78bf2843e3fa0ed4ed6",
    "completed_sha256": "b81d4550b9110b283fd5aa0dfafa01effaeed5235e8199e3363cc67f51851e20",
    "content_hash": "b385e25f259114951783319a19150f0660c11d1eec6eea01c770ad2af700d0eb",
    "fixture_samples": 1,
    "model_promotion_allowed": false,
    "reevaluate_promotion_allowed": false
  },
  {
    "gate": "first",
    "scratch": "wc-run-vnua_o21",
    "fixture": "test_large_monitoring_corpus_a0",
    "domain": "au",
    "action": "review",
    "phase": "review-xrucgajb",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 255.73148541700016,
    "outcome_sha256": "121b134ccd10150364b9aff02cd67aeae84d5983585879a5b7745820cf78a30d",
    "completed_sha256": "f11d45c4630c9cacf088ea58e1bfcc0cdf85b265d2be86809633bd3603fbc02c",
    "content_hash": "6129628c4509ed4cd171e274bbb6efdb78364adb36c22396de246140562457ec",
    "model_promotion_allowed": false,
    "telegram_delivery_confirmed": false
  },
  {
    "gate": "first",
    "scratch": "wc-run-vnua_o21",
    "fixture": "test_large_monitoring_corpus_a1",
    "domain": "hkjc",
    "action": "racing-monitoring-corpus",
    "phase": "racing-monitoring-corpus-_dumu1j7",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 550.227747166,
    "outcome_sha256": "dc114b9bc269ee409331dac608219a7a6e8a707df181acd406c4aac4d36e5f42",
    "completed_sha256": "07d70395234b1bd7d02e24fbf5d3fad75ce353ae6d33eac25f96acdfae96d800",
    "content_hash": "95244701d2821b78ec990a1e21422a62983067ac8046e00fc844a81719368746",
    "fixture_samples": 1,
    "model_promotion_allowed": false,
    "reevaluate_promotion_allowed": false
  },
  {
    "gate": "first",
    "scratch": "wc-run-vnua_o21",
    "fixture": "test_large_monitoring_corpus_a1",
    "domain": "hkjc",
    "action": "review",
    "phase": "review-bktjxecw",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 260.30840791699984,
    "outcome_sha256": "21ed514578df5339c1fc92f4eac9f0985e64334fd6263b67e3df359c442672c4",
    "completed_sha256": "ad9353e9739f82ad51164aac294a6f09c2aef1226094bf5743959549a401895d",
    "content_hash": "ac5bba60abb72ad5fd4b8578451df613f3ac27e8e337d9ba040efd0ef7d016d4",
    "model_promotion_allowed": false,
    "telegram_delivery_confirmed": false
  }
]
```

No complete-suite test totals are invented: the controller captures its full
output internally, while the manifest proves first full-gate exit 0. The earlier
standalone unchanged two-domain corpus/review test passed both cases at source
commit 558e9714; that evidence and the prior timeout remain in the candidate's
byte-reader audit. No model-performance improvement is claimed.

## Remaining work

Wait only on controller session 17881/PID 48488 and its actual current child.
Do not restart the terminated old gate 14598 or completed targeted test 86079.
After the clean immutable recheck, inspect terminal controller output, release
events, main/branch state and all configured production runtimes. Revalidate
every delegated approval condition; any changed main, scope, branch or gate is
blocking, never a reason to bypass controls.

Only after verified activation run a fresh native production research review
with the existing locks/resources/preemption guards and append a new receipt.
Tasks 6–10, real pilots, reviewed power profiles, central review scheduling,
Telegram/private Dashboard acceptance and Stage 5 exit remain incomplete.

Latest separate production snapshot was 2026-10-19T04:50:29Z: all four runtime
roots/labels aligned at ffc9111118a0; AU/HKJC/Tennis latest runs succeeded,
NBA dormant. AU/HKJC registry stages remained production, Tennis/NBA shadow.
D1 backup/local restore/WARM were verified; latest COLD proof/backlog, HOT
warning and missing central research-review label remained open. HOT had
24.22 GiB free and mounted WARM 817.79 GiB. These are timestamped observations,
not a new claim of all-green production or completed Stage 5.

## Clean approval gate: AU phase receipts observed

The same controller session 17881 / PID 48488 remains live. Its clean-checkout
approval gate (pytest PID 58575, `pytest-22`) completed both unchanged AU large
monitoring phases with `succeeded`, `receipt_verified`, return code 0:

| Phase | Wall seconds | Outcome SHA256 | Result content hash |
| --- | ---: | --- | --- |
| `racing-monitoring-corpus-nbcgwd93` | 503.71816150000006 | `b376da16e9737b1192aabd10fc482aeadbee5fb0c73233aab59b3b1525daef9a` | `ff177c2cc2b2a986d30d9897b2a2a7ed5cabca526bb4e53f0f74c5d4a55c39a2` |
| `review-x3w9y2n3` | 262.26235316600014 | `07b9aa243c740fe9a494b2ecefe05a6ee43a0c682bd915a4a3c46136ed5386ca` | `8af8c28b9bf5b4ee120ebeef39d2f9f25745c6987bb6e0dea6c1ad857fd05018` |

Both outcome files were read directly beneath
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-vnua_o21/pytest-of-imac/pytest-22/test_large_monitoring_corpus_a0/warm/research-phases/au/`.
The corpus reports exactly one fixture monitoring sample; both phases deny
model promotion, and review does not confirm Telegram delivery. No fixture
result is counted as real pilot evidence. The original separate 600-second
limits were unchanged. HKJC and the remaining suites are not yet proven by
these AU receipts. No merge or activation is claimed.

Separate read-only production inspections during this wait verified four
cursor database structures (`--status`, receipt null), but not a new review
pass or Telegram acceptance. Power applicability remains 0/4, all
`power_profile_missing`, content hash
`072d1b455e322d2ceab6378f9a1083f38b9e00631f372386f4681569a07e8f2f`.
Installed and loaded domain labels remain aligned; the central research-review
label is still missing. These observations do not authorize an installer or
change the pending engineering release scope.

## Terminal controller result and post-release continuation

Session 17881 is now terminal exit 0, not an active gate. The original controller
returned `merged`, `activation: succeeded`, `automation_status: completed` for
`ea95996493ed58187bf6f219f63a0c4c02ac14ab`, with the same nine paths, no
installers, no Dashboard deploy and all four configured domains aligned.
Its final Telegram result is `sent`, one part to one target. The append-only
release event files were independently read and SHA256 checked:

| Event | UTC time | File SHA256 |
| --- | --- | --- |
| approval_granted | 2026-10-19T06:33:39.580301Z | `c383913e290700ed14a07d696218d73113e331fbde64220d150c4182deba0198` |
| merged | 2026-10-19T06:33:41.626151Z | `c799090ffc2c41df1d7317f76134c306e1d0825bf4ee60764231a7298aee88d4` |
| activation_succeeded | 2026-10-19T06:33:48.904004Z | `8121a8f05da4e92c03bac6fab796702969078c222263acfee83dd7fabbf86bf4` |

At the next inspection remote main and production had advanced together to
`a99710261120d10bf4b76e9c81bcd79916b214e8`, a subsequent HKJC review-document
commit. `ea959964` remains an ancestor, the immutable reader branch still points
exactly to it, and the five released reader source files have no diff between
that release and current production. Two existing generated-data modifications
were preserved; no reset or overwrite was used.

A fresh native record-only review was launched through the existing production
wrapper and external scratch runner after confirming no other native review
was live, mounted WARM, and approximately 23 GiB HOT / 818 GiB WARM available.
Its session is 64823, scratch `wc-run-a0bf80v2`. The original production locks,
900-second per-domain limit, frozen rulers and no-promotion/no-notification
authority remain unchanged. Its result is still pending at this checkpoint;
neither real pilot acceptance nor Stage 5 completion is claimed.
